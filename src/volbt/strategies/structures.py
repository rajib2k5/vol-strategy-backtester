"""The contracts of milestone 4's four structures (plan section 5): which listed options a position opens.

    short_straddle, long_straddle   a call and a put of one expiry at the ATM strike: the listed strike (with both a
                                    call and a put) nearest that expiry's parity forward; a tie goes to the lower
                                    strike (as the M3 reference strategy)
    short_strangle                  a call and a put of one expiry, each the listed contract whose SPOT delta is
                                    nearest +0.25 (call) or -0.25 (put): ADR-0005's delta, DF (F/S) N(d1) for a call
                                    and -DF (F/S) N(-d1) for a put, which is volbt.pricing.black76.greeks' "delta".
                                    A tie goes to the lower strike; a pick whose call strike is not above its put
                                    strike is no strangle (None)
    straddle_calendar               a short straddle on the front expiry and a long straddle on the back one at the
                                    SAME strike: of the strikes listed with a call and a put on both expiries, the one
                                    nearest the front's parity forward (tie: the lower)

Each pick returns the legs as LegIntents (ratio -1 short, +1 long, per package), or None when the chain cannot give
the structure. The expiries themselves are chosen by strategies.expiry (VolStrategy).

The delta's inputs are the engine's (volbt.engine.marks), read through the view, so the strangle is picked at the
deltas the book is hedged at: S = the session's SPY close; r = the last DGS3MO r_cc dated BEFORE the session (the
engine's step 1); F = the expiry's parity forward (view.forwards); tau = calendar days to the listed expiry / 365;
sigma by the engine's mark-IV rule (ADR-0004 as amended in M2): in quote mode a contract in the smile with a solved IV
uses it, any other contract the surface IV at its log-moneyness (smile.surface_iv over the session's usable smiles,
the same call as iv30); in surface mode every contract the surface IV at ln(K/F). A contract whose sigma is not a
finite number is not a candidate. Default taken 2026-11-09, owner can override.

May import (volbt): pricing, signals, view (ADR-0001 §4).
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np

from volbt.pricing import black76, smile
from volbt.signals.iv30 import usable_smiles
from volbt.strategies.base import LegIntent

STRUCTURES = ("short_straddle", "long_straddle", "short_strangle", "straddle_calendar")
# The side of the volatility each structure is: the entry gate and the signal exit follow it (plan section 5: the
# calendar is one of the three short-vol structures of the grid).
SIDES = {"short_straddle": "short", "long_straddle": "long", "short_strangle": "short", "straddle_calendar": "short"}
STRANGLE_DELTA = 0.25
DAYS_PER_YEAR = 365


def as_date(value) -> date:
    """A Timestamp or a date from a view's DataFrame, as a plain date."""
    return date(value.year, value.month, value.day)


def is_true(value) -> bool:
    """A frame's boolean cell: True only for a true value (None and NaN, a missing cell, are not)."""
    return value is not None and value == value and bool(value)


def atm_strike(strikes, forward: float) -> float | None:
    """The strike nearest `forward` (a tie goes to the lower strike); None for no strike or a forward that is not a
    finite number."""
    strikes = sorted(float(k) for k in strikes)
    if not strikes or not math.isfinite(forward):
        return None
    return min(strikes, key=lambda k: (abs(k - forward), k))


def straddle_strikes(symbols: dict) -> list[float]:
    """The strikes of one expiry's {strike: {right: osi_symbol}} listed with both a call and a put."""
    return sorted(k for k, sides in symbols.items() if "C" in sides and "P" in sides)


def atm_straddle(symbols: dict, forward: float, ratio: int) -> tuple[LegIntent, ...] | None:
    """The call and the put at the ATM strike of one expiry, each with `ratio` (-1 short, +1 long)."""
    if ratio not in (-1, 1):
        raise ValueError(f"a straddle's ratio is -1 (short) or +1 (long), not {ratio!r}")
    strike = atm_strike(straddle_strikes(symbols), forward)
    if strike is None:
        return None
    return (LegIntent(symbols[strike]["C"], ratio), LegIntent(symbols[strike]["P"], ratio))


def delta_strangle(candidates, delta: float = STRANGLE_DELTA) -> tuple[LegIntent, ...] | None:
    """The short strangle from one expiry's candidates [(strike, right, osi_symbol, spot_delta)]: the call nearest
    +delta and the put nearest -delta, ratio -1 each; None if a side has no candidate or the call strike is not above
    the put strike."""
    if not 0 < delta < 1:
        raise ValueError(f"the strangle's delta is in (0, 1), not {delta!r}")
    rows = [(float(k), r, s, float(d)) for k, r, s, d in candidates if math.isfinite(d)]
    calls = [row for row in rows if row[1] == "C"]
    puts = [row for row in rows if row[1] == "P"]
    if not calls or not puts:
        return None
    call = min(calls, key=lambda row: (abs(row[3] - delta), row[0]))
    put = min(puts, key=lambda row: (abs(row[3] + delta), row[0]))
    if call[0] <= put[0]:
        return None
    return (LegIntent(call[2], -1), LegIntent(put[2], -1))


def straddle_calendar(front: dict, back: dict, front_forward: float) -> tuple[LegIntent, ...] | None:
    """Short front straddle and long back straddle at one strike: of the strikes both expiries list with a call and a
    put, the one nearest the front's forward (tie: the lower). Legs: front C -1, front P -1, back C +1, back P +1."""
    strike = atm_strike(set(straddle_strikes(front)) & set(straddle_strikes(back)), front_forward)
    if strike is None:
        return None
    return (LegIntent(front[strike]["C"], -1), LegIntent(front[strike]["P"], -1),
            LegIntent(back[strike]["C"], 1), LegIntent(back[strike]["P"], 1))


class Chain:
    """One session's listed options as the picks read them, through the session's view (nothing dated after it).

    expiries      the expiries with a parity forward at tau > 0 (view.forwards)
    forward(e)    that forward
    symbols(e)    {strike: {"C" | "P": osi_symbol}} of the expiry's quotes (view.quotes)
    deltas(e)     [(strike, right, osi_symbol, spot delta)] by the module docstring's rule
    """

    def __init__(self, view, session: date, source: str, surface_mode: bool = False) -> None:
        self.view, self.session, self.source, self.surface_mode = view, session, source, surface_mode
        rows = view.forwards(session, source=source)
        rows = rows[rows["tau_years"] > 0]
        self.forwards = {as_date(e): float(f) for e, f in zip(rows["expiry"], rows["forward"])}
        self.expiries = sorted(self.forwards)
        self.by_expiry: dict | None = None

    def forward(self, expiry: date) -> float:
        return self.forwards[expiry]

    def symbols(self, expiry: date) -> dict:
        if self.by_expiry is None:
            quotes = self.view.quotes(self.session, source=self.source)
            listed: dict = {}
            for e, strike, right, symbol in zip(quotes["expiry"], quotes["strike"], quotes["call_put"],
                                                quotes["osi_symbol"]):
                listed.setdefault(as_date(e), {}).setdefault(float(strike), {})[str(right)] = str(symbol)
            self.by_expiry = listed
        return self.by_expiry.get(expiry, {})

    def spot_and_rate(self) -> tuple[float, float]:
        """The engine's S and r for the session (module docstring); NaN where the view has none."""
        bars = self.view.spy_bars()
        spot = float(bars["close"].iloc[-1]) if len(bars) and as_date(bars["date"].iloc[-1]) == self.session \
            else float("nan")
        rates = self.view.rates()
        dated = rates[(rates["date"] < np.datetime64(self.session)) & rates["r_cc"].notna()]
        rate = float(dated["r_cc"].iloc[-1]) if len(dated) else float("nan")
        return spot, rate

    def deltas(self, expiry: date) -> list[tuple[float, str, str, float]]:
        symbols = self.symbols(expiry)
        forward = self.forwards.get(expiry, float("nan"))
        spot, rate = self.spot_and_rate()
        tau = (expiry - self.session).days / DAYS_PER_YEAR
        if not symbols or not (math.isfinite(forward) and math.isfinite(spot) and math.isfinite(rate) and tau > 0):
            return []
        contracts = [(strike, right, symbol) for strike, sides in sorted(symbols.items())
                     for right, symbol in sorted(sides.items())]
        sigmas = self.sigmas(contracts, forward, tau)
        out = []
        for (strike, right, symbol), sigma in zip(contracts, sigmas):
            if math.isfinite(sigma) and sigma > 0:
                value = float(black76.greeks(spot, forward, strike, tau, rate, sigma, right == "C")["delta"])
                out.append((strike, right, symbol, value))
        return out

    def sigmas(self, contracts, forward: float, tau: float) -> list[float]:
        """The mark-IV rule's sigma of each (strike, right, osi_symbol), NaN where there is none."""
        smiles = usable_smiles(self.view.smiles(self.session, source=self.source))
        own: dict = {}
        if not self.surface_mode:
            ivs = self.view.quote_ivs(self.session, source=self.source)
            for symbol, k, in_smile, iv in zip(ivs["osi_symbol"], ivs["log_moneyness"], ivs["in_smile"], ivs["iv"]):
                own[str(symbol)] = (None if k is None else float(k), is_true(in_smile), None if iv is None else float(iv))
        sigma = [float("nan")] * len(contracts)
        need, ks = [], []
        for i, (strike, _, symbol) in enumerate(contracts):
            k_quote, in_smile, iv = own.get(symbol, (None, False, None))
            if not self.surface_mode and in_smile and iv is not None and math.isfinite(iv):
                sigma[i] = iv
                continue
            k = k_quote if k_quote is not None and math.isfinite(k_quote) else math.log(strike / forward)
            need.append(i)
            ks.append(k)
        if need and smiles:
            values, _ = smile.surface_iv(np.asarray(ks, dtype=float), tau, smiles)
            for i, value in zip(need, values):
                sigma[i] = float(value)
        return sigma
