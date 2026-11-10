"""What a signal is to the engine (milestone 4, plan sections 2 and 3).

    SignalValue   one signal's value at one session: frozen, plain values only
    Signal        the interface the engine calls: name, params() and update(view, n_window)

The engine owns the signal objects a strategy declares (`Strategy.signals`). Before a run's first session it calls
`reset()` on each, so no state survives from another run. At step 9 of each session it calls
`update(view, n_window)` once per signal with that session's MarketView, writes the value to the `signals`
table and hands it to the strategy in `ctx.signals`. So a signal's state (its last fit) lives in one object, and
the table holds every session's value (ADR-0001 §1 step 9).

`n_window` is the number of sessions in (t, t + 30 calendar days], which the engine reads from the session calendar
(decision D3): a signal sees the market only through the view, and the view holds no future date.

Every value at t depends only on data dated on or before t, through the view (ADR-0001 §2; test 6 proves it).
May import (volbt): pricing, view.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

# SignalValue.flags bits.
RV_FALLBACK = 1 << 0        # the model's forecast was <= 0, so the naive RV22 stands in for it (plan section 4)
RV_MISSING = 1 << 1         # no forecast: too few training pairs for a fit, or too few returns for the naive one
IV30_MISSING = 1 << 2       # no IV30: no snapshot, no usable smile, or the read needs SURFACE_EXTRAP_TENOR
WINDOW_EMPTY = 1 << 3       # n_window is 0 (no session in (t, t + 30 days]): RV^ and s are not defined (fix pass, N5)
SIGNAL_FLAG_NAMES = ("RV_FALLBACK", "RV_MISSING", "IV30_MISSING", "WINDOW_EMPTY")


@dataclass(frozen=True)
class SignalValue:
    """One signal at one session. NaN (never None) for a number that is not defined; the ledger writes it as null.

    value          the signal: s_t = ln(IV30^2 / RV^2), the log variance ratio (plan section 4)
    iv30           the ATM-forward implied vol at 30 calendar days (volbt.signals.iv30)
    iv30_flags     the SURFACE_* bits of that read
    rv_forecast    RV^ = sqrt(n_window * y^ * 365 / 30): the forecast variance over the window, annualised for display
    rv_model       "har" or "naive"
    model_fit_date the fit the forecast used (the first session of t's month), None for "naive" or when no fit
    n_window       sessions in (t, t + 30 days]
    flags          RV_FALLBACK, RV_MISSING, IV30_MISSING, WINDOW_EMPTY
    vrp_spread     iv30 - rv_forecast
    vix_bucket     the previous session's VIX bucket (ADR-0010 §3), None before the second VIX close
    vol_regime     "shock", "post_shock" or "calm", lagged one session (ADR-0010 §3)
    """

    value: float
    iv30: float
    iv30_flags: int
    rv_forecast: float
    rv_model: str
    model_fit_date: date | None
    n_window: int
    flags: int
    vrp_spread: float
    vix_bucket: str | None
    vol_regime: str | None


class Signal(Protocol):
    """The interface the engine calls. `name` keys the value in ctx.signals and the `signals` table.

    reset() returns the signal to the state it had when built (no fit): the engine calls it once per signal before
    a run's first session, so a strategy object run twice, or on another store, starts from a clean state (review
    finding N3: a monthly fit carried over from another store would otherwise be reused in the same month)."""

    name: str

    def params(self) -> dict[str, Any]: ...

    def reset(self) -> None: ...

    def update(self, view: Any, n_window: int) -> SignalValue: ...
