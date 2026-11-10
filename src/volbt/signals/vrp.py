"""The VRP signal: the log ratio of implied to forecast variance over the next 30 calendar days (plan section 4).

    VrpSignal(rv_model)   rv_model "har" (volbt.signals.har) or "naive" (RV22); update(view, n_window) at step 9

At session t, with n = n_window (sessions in (t, t + 30 days], from the engine's calendar):

    y^      the forecast mean daily variance of the next sessions (HAR, or the naive mean of the last 22 r^2)
    RV^     sqrt(n y^ 365 / 30): the forecast variance over the window, annualised for display
    IV30    volbt.signals.iv30
    s_t     ln(IV30^2 / RV^2) = ln(IV30^2 30/365 / (n y^)): implied total variance over the forecast one,
            both over the same 30 calendar days; vrp_spread = IV30 - RV^

Matching the window replaces ADR-0010's "annualised with 252" note: with 252, a 17-session window would bias the
ratio by ln(21/17) = 0.21. s and the spread are NaN when either side is (no snapshot, no fit, no session in the
window); the flags say why (WINDOW_EMPTY for n = 0). IV30 is NaN with IV30_MISSING on a session with no usable
smile, though iv30's own flags (iv30_flags) are 0 there: the 27 such development sessions carry IV30_MISSING.
The VIX regime labels ride along, lagged (volbt.signals.regime).

Every read is through the view of session t, so a value at t depends only on data dated on or before t (ADR-0001
test 6: tests/test_signals_causal.py). The only state is the HAR forecaster's current monthly fit, which reset()
clears; the engine calls it before each run.

`source` is the vendor whose smiles give IV30 (default "optionsdx"); it must be the run's source (the engine's
view serves one source). Default taken 2026-11-09, owner can override.

May import (volbt): pricing, view. numpy only.
"""

from __future__ import annotations

import math
from typing import Any

from volbt.signals.base import IV30_MISSING, RV_MISSING, WINDOW_EMPTY, SignalValue
from volbt.signals.har import HORIZON, MIN_PAIRS, HarForecaster, naive_rv22
from volbt.signals.iv30 import DAYS, DAYS_PER_YEAR, iv30
from volbt.signals.realised import total_log_returns
from volbt.signals.regime import lagged_regime

RV_MODELS = ("har", "naive")


def rv_hat(n_window: int, forecast: float) -> float:
    """sqrt(n y^ 365 / 30); NaN unless the forecast is finite and positive and the window holds a session."""
    if not (math.isfinite(forecast) and forecast > 0 and n_window > 0):
        return float("nan")
    return math.sqrt(n_window * forecast * DAYS_PER_YEAR / DAYS)


class VrpSignal:
    """See the module docstring. `name` defaults to "vrp_<rv_model>"."""

    def __init__(self, rv_model: str = "har", source: str = "optionsdx", name: str | None = None) -> None:
        if rv_model not in RV_MODELS:
            raise ValueError(f"rv_model must be one of {RV_MODELS}, not {rv_model!r}")
        self.rv_model, self.source = rv_model, source
        self.name = name if name is not None else f"vrp_{rv_model}"
        self.reset()

    def reset(self) -> None:
        """No fit: the state of a new signal (the engine calls it before each run's first session)."""
        self.forecaster = HarForecaster(HORIZON, MIN_PAIRS) if self.rv_model == "har" else None

    def params(self) -> dict[str, Any]:
        return {"rv_model": self.rv_model, "source": self.source, "horizon": HORIZON, "min_pairs": MIN_PAIRS,
                "window_days": DAYS}

    def update(self, view, n_window: int) -> SignalValue:
        t = view.as_of
        dates, r = total_log_returns(view.spy_bars(), view.dividends())
        v = r ** 2
        if self.forecaster is not None:
            forecast, fit_date, flags = self.forecaster.forecast(v, dates) if v.size else (float("nan"), None,
                                                                                           RV_MISSING)
        else:
            forecast, fit_date = naive_rv22(v), None
            flags = 0 if math.isfinite(forecast) else RV_MISSING
        rv = rv_hat(n_window, forecast)
        if n_window <= 0:
            flags |= WINDOW_EMPTY       # the review's N5: a NaN s with flags 0 would read as "no reason given"
        sigma, iv_flags = iv30(view, t, self.source)
        if not math.isfinite(sigma):
            flags |= IV30_MISSING
        value = 2 * math.log(sigma / rv) if math.isfinite(sigma) and sigma > 0 and math.isfinite(rv) else float("nan")
        bucket, regime = lagged_regime(view.vix(), t)
        return SignalValue(value=value, iv30=sigma, iv30_flags=iv_flags, rv_forecast=rv, rv_model=self.rv_model,
                           model_fit_date=fit_date, n_window=n_window, flags=flags, vrp_spread=sigma - rv,
                           vix_bucket=bucket, vol_regime=regime)

