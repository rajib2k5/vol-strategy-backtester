"""Made-up views, books and contexts for the milestone-4 strategy unit tests (not a test file: pytest does not collect it).

FakeView serves one session's chain the way volbt.view does (forwards, quotes, quote_ivs, smiles, spy_bars, rates),
from plain values. Made-up values only.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import MappingProxyType

import numpy as np
import pandas as pd

from volbt.data.osi import osi_symbol
from volbt.signals.base import SignalValue
from volbt.strategies.base import BookState, LotState, PendingOrderState, PositionState, SessionContext


def weekdays(first: date, last: date, holidays=()) -> frozenset:
    days, day = set(), first
    while day <= last:
        if day.weekday() < 5 and day not in holidays:
            days.add(day)
        day += timedelta(days=1)
    return frozenset(days)


def symbol(expiry: date, right: str, strike: float) -> str:
    return osi_symbol("SPY", expiry, right, strike)


class FakeView:
    """One session's chain: `forwards` {expiry: F}; every strike of `strikes` listed as a call and a put on each
    expiry except the (expiry, strike, right) in `missing`; `ivs` {osi_symbol: (in_smile, iv)} (default: not in the
    smile, no IV); flat smiles at `smile_sigma` on every expiry (5 nodes)."""

    def __init__(self, as_of: date, forwards: dict, strikes, spot: float = 400.0, rate: float = 0.04,
                 ivs: dict | None = None, smile_sigma: float = 0.20, missing=()) -> None:
        self.as_of, self.forward_by, self.spot, self.rate = as_of, dict(forwards), spot, rate
        self.strikes = [float(k) for k in strikes]
        self.ivs, self.smile_sigma, self.missing = dict(ivs or {}), smile_sigma, set(missing)
        self.reads: list[tuple[str, date | None]] = []

    def tau(self, expiry: date) -> float:
        return (expiry - self.as_of).days / 365

    def forwards(self, day: date, source: str = "optionsdx"):
        self.reads.append(("forwards", day))
        expiries = sorted(self.forward_by)
        return pd.DataFrame({"expiry": pd.to_datetime(expiries), "tau_years": [self.tau(e) for e in expiries],
                             "forward": [self.forward_by[e] for e in expiries],
                             "r_cc": [self.rate] * len(expiries)})

    def rows(self):
        return [(e, k, r, symbol(e, r, k)) for e in sorted(self.forward_by) for k in self.strikes for r in ("C", "P")
                if (e, k, r) not in self.missing]

    def quotes(self, day: date, osi_symbols=None, source: str = "optionsdx"):
        self.reads.append(("quotes", day))
        rows = self.rows()
        return pd.DataFrame({"expiry": pd.to_datetime([e for e, _, _, _ in rows]), "strike": [k for _, k, _, _ in rows],
                             "call_put": [r for _, _, r, _ in rows], "osi_symbol": [s for _, _, _, s in rows]})

    def quote_ivs(self, day: date, osi_symbols=None, source: str = "optionsdx"):
        self.reads.append(("quote_ivs", day))
        rows = self.rows()
        return pd.DataFrame({"osi_symbol": [s for _, _, _, s in rows],
                             "log_moneyness": [float(np.log(k / self.forward_by[e])) for e, k, _, _ in rows],
                             "in_smile": [self.ivs.get(s, (False, None))[0] for _, _, _, s in rows],
                             "iv": [self.ivs.get(s, (False, None))[1] for _, _, _, s in rows]})

    def smiles(self, day: date, source: str = "optionsdx"):
        self.reads.append(("smiles", day))
        expiries = sorted(self.forward_by)
        k = np.linspace(-0.3, 0.3, 5)
        return pd.DataFrame({"tau_years": [self.tau(e) for e in expiries], "k_nodes": [k for _ in expiries],
                             "total_var_nodes": [np.full(5, self.smile_sigma ** 2 * self.tau(e)) for e in expiries],
                             "n_points": [5] * len(expiries)})

    def spy_bars(self):
        self.reads.append(("spy_bars", None))
        return pd.DataFrame({"date": pd.to_datetime([self.as_of - timedelta(days=1), self.as_of]),
                             "close": [self.spot * 0.99, self.spot]})

    def rates(self):
        self.reads.append(("rates", None))
        return pd.DataFrame({"date": pd.to_datetime([self.as_of - timedelta(days=3), self.as_of - timedelta(days=1),
                                                     self.as_of]),
                             "r_cc": [self.rate - 0.01, self.rate, self.rate + 0.05]})


def signal_value(s: float, name: str = "vrp_har") -> MappingProxyType:
    value = SignalValue(value=s, iv30=0.2, iv30_flags=0, rv_forecast=0.18, rv_model="har", model_fit_date=None,
                        n_window=21, flags=0, vrp_spread=0.02, vix_bucket=None, vol_regime=None)
    return MappingProxyType({name: value})


def context(t: date, sessions: frozenset, s: float = float("nan"), has_snapshot: bool = True,
            source: str = "optionsdx", mode: str = "quote") -> SessionContext:
    later = sorted(d for d in sessions if d > t)
    return SessionContext(t, later[0] if later else None, has_snapshot, source, mode, sessions, signal_value(s))


def straddle_position(position_id: int, expiry: date, strike: float = 400.0, qty: int = -10, status: str = "open",
                      pnl: float = 0.0, premium: float = 10_000.0, structure: str = "short_straddle") -> PositionState:
    lots = () if status == "pending" else (
        LotState(2 * position_id, position_id, symbol(expiry, "C", strike), expiry, strike, "C", qty),
        LotState(2 * position_id + 1, position_id, symbol(expiry, "P", strike), expiry, strike, "P", qty))
    return PositionState(position_id, structure, status, None if status == "pending" else date(2015, 1, 2), lots,
                         None if status == "pending" else premium, None if status == "pending" else pnl)


def book(t: date, positions=(), pending_ids=()) -> BookState:
    pending = tuple(PendingOrderState(100 + i, pid, "close", t) for i, pid in enumerate(pending_ids))
    return BookState(t, 100_000_000, 0, tuple(positions), pending)
