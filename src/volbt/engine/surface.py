"""One session's surface: forwards, the smiles, h_model, read through that session's view.

    DaySurface.from_view(...)   the surface of a snapshot session t: the pricing build's de-Americanised
                                forwards and the usable smiles (5+ nodes), exactly as M2 stored them
    .forward(expiry)            the contract expiry's forward at the session: the parity forward if the
                                expiry is listed, else the dividend-schedule carry forward (ADR-0008 §3
                                fallback; ADR-0004 step 4 reads k on it)
    .iv(expiry, k)              smile.surface_iv at the contract's tau and k, with its SURFACE_* bits
    .stale(t, ...)              ADR-0004 rule 4 on a session with no snapshot: the PREVIOUS surface's IV at
                                the same log-moneyness, re-priced at today's spot and forward. The forward
                                (decision D10) is the carry forward at today's spot plus the previous
                                session's parity-minus-carry basis, which survives a dividend; FORWARD_CARRY
    .h_model(expiry, k)         ADR-0002 §7's model half-spread, from the surface's own snapshot (lazy: it
                                needs the whole chain, which a quote-mode day rarely does)

M2's surface_iv is used as it is (the calendar constraint and its SURFACE_CALENDAR_ADJUSTED bit included):
the open owner question of ADR-0004 amendment 5, stub quotes that still move a few nodes, is inherited.
"""

from __future__ import annotations

from datetime import date

import numpy as np

from volbt.data import flags as quality
from volbt.engine.fills import h_model as median_half_spread
from volbt.pricing import dividends, smile
from volbt.pricing.forward import carry_forward

DAYS_PER_YEAR = 365
# mark_flags bits the engine adds above M2's SURFACE_* bits 1, 2, 4 and 8 (smile.py).
IV_FAIL = 1 << 4             # the quote's own IV could not be solved: its greeks use the surface IV
MARK_JUMP = 1 << 5           # ADR-0004: > 50% in a day while spot and ATM vol barely moved; still used
GREEKS_OTM_IV = 1 << 6       # greeks at the surface IV of the strike (an ITM quote, or one not in the smile)
FORWARD_CARRY = 1 << 7       # the forward is a carry forward (D10, or an unlisted expiry's fallback)
ATTRIBUTION_BREAK = 1 << 8   # reserved for M6's P&L attribution; never set in M3
MARK_FLAG_NAMES = (*smile.SURFACE_FLAG_NAMES, "IV_FAIL", "MARK_JUMP", "GREEKS_OTM_IV", "FORWARD_CARRY",
                   "ATTRIBUTION_BREAK")
VALID_QUOTE = quality.BID_NULL | quality.ASK_NULL | quality.CROSSED | quality.STALE | quality.ZERO_BID


def as_date(value) -> date:
    return date(value.year, value.month, value.day)


class DaySurface:
    """See the module docstring. `day` is the snapshot the smiles come from; `session` the date it serves."""

    def __init__(self, day: date, session: date, spot: float, rate: float, forwards: dict, smiles: list,
                 paid: tuple[list, list], calendar: list[date], quotes_reader=None, stale: bool = False) -> None:
        self.day, self.session, self.spot, self.rate = day, session, spot, rate
        self.forwards = forwards            # expiry -> (forward, forward_carry) at `day`
        self.smiles = smiles                # [(tau at `day`, k_nodes, w_nodes)], usable, sorted by tau
        self.paid = paid                    # (ex_dates, amounts) of the dividends paid by `session`
        self.calendar = calendar
        self.stale = stale
        self._quotes_reader = quotes_reader
        self._h_quotes = None
        self._iv_memo: dict = {}

    @classmethod
    def from_view(cls, view, session: date, source: str, spot: float, rate: float, paid, calendar) -> DaySurface | None:
        forwards = view.forwards(session, source=source)
        if not len(forwards):
            return None
        rows = forwards[forwards["tau_years"] > 0]
        by_expiry = {as_date(e): (float(f), float(c)) for e, f, c in
                     zip(rows["expiry"], rows["forward"], rows["forward_carry"])}
        fits = view.smiles(session, source=source)
        smiles = sorted(((float(t), np.asarray(kn, dtype=float), np.asarray(wn, dtype=float))
                         for t, kn, wn, n in zip(fits["tau_years"], fits["k_nodes"], fits["total_var_nodes"],
                                                 fits["n_points"])
                         if t > 0 and n >= smile.MIN_NODES), key=lambda s: s[0])

        def reader():
            quotes = view.quotes(session, source=source)
            ivs = view.quote_ivs(session, source=source)
            return quotes, ivs

        return cls(session, session, spot, rate, by_expiry, smiles, paid, calendar, reader)

    @property
    def usable(self) -> bool:
        return bool(self.smiles)

    def stale_copy(self, session: date, spot: float, rate: float, paid) -> DaySurface:
        """The surface of this snapshot serving a later session with no snapshot (rule 4)."""
        twin = DaySurface(self.day, session, spot, rate, self.forwards, self.smiles, paid, self.calendar,
                          self._quotes_reader, stale=True)
        twin._h_quotes = self._h_quotes
        return twin

    def schedule(self, expiry: date) -> tuple[list, list]:
        """The projected dividends (drop times from the session, amounts) for a contract expiring `expiry`."""
        return dividends.schedule(self.paid[0], self.paid[1], self.session, expiry, self.calendar)

    def forward(self, expiry: date) -> tuple[float, int]:
        """(F at the session, flags): FORWARD_CARRY where the forward is not that day's parity forward."""
        tau = (expiry - self.session).days / DAYS_PER_YEAR
        if not self.stale and expiry in self.forwards:
            return self.forwards[expiry][0], 0
        times, amounts = self.schedule(expiry)
        carry = carry_forward(self.spot, self.rate, tau, times, amounts)
        if self.stale and expiry in self.forwards:
            forward, forward_carry = self.forwards[expiry]
            carry += forward - forward_carry
        return carry, FORWARD_CARRY

    def iv(self, expiry: date, k) -> tuple[np.ndarray, np.ndarray]:
        """(sigma, SURFACE_* flags) at log-moneyness k for the expiry, at the SURFACE's own tau for it.

        One float k at a time is memoised: marks, greeks and the early-exercise step read the same (expiry, k)."""
        tau = (expiry - self.day).days / DAYS_PER_YEAR
        ks = np.atleast_1d(np.asarray(k, dtype=float))
        if ks.size != 1:
            return smile.surface_iv(ks, tau, self.smiles)
        key = (expiry, float(ks[0]))
        if key not in self._iv_memo:
            self._iv_memo[key] = smile.surface_iv(ks, tau, self.smiles)
        return self._iv_memo[key]

    def atm_iv_30d(self) -> float:
        return float(smile.surface_iv(np.zeros(1), 30 / DAYS_PER_YEAR, self.smiles)[0][0]) if self.smiles else float("nan")

    def h_model(self, expiry: date, k: float, band: float) -> tuple[float | None, bool]:
        if self._h_quotes is None:
            self._h_quotes = {}
            if self._quotes_reader is not None:
                quotes, ivs = self._quotes_reader()
                joined = quotes.merge(ivs[["osi_symbol", "log_moneyness"]], on="osi_symbol", how="inner")
                bits = joined["quality_flags"].to_numpy(np.int64)
                bid, ask = joined["bid"].to_numpy(float), joined["ask"].to_numpy(float)
                ok = ((bits & VALID_QUOTE) == 0) & (bid > 0) & (ask >= bid) & np.isfinite(joined["log_moneyness"].to_numpy(float))
                for e, group in joined[ok].groupby("expiry", sort=True):
                    self._h_quotes[as_date(e)] = (group["log_moneyness"].to_numpy(float),
                                                  (group["ask"].to_numpy(float) - group["bid"].to_numpy(float)) / 2)
        return median_half_spread(self._h_quotes, expiry, k, band)
