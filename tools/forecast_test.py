"""The forecast test's paired series: HAR against the naive RV22 at 21 sessions, pseudo out of sample (plan section 6).

    window(calendar, start, last_target_end)   the sessions t >= start whose target (the 21 sessions after t) ends by
                                               last_target_end: the forecast test's dates
    forecasts(store, days, split)              per t: HAR's and the naive forecast, each from the view of t only
    realised(store, days, split)               per t: y_t = mean r^2 over the 21 sessions after t (ex post)
    paired(rows)                               d_t = QLIKE(naive)_t - QLIKE(HAR)_t: d > 0 favours HAR
    block_window(store, first, last_target_end)   the 2002-2009 window the block is measured on: from the first
                                               session >= `first` with a HAR forecast

The forecasts read only through each session's view (StoreView over a YearCache of the reference tables), so a
forecast at t depends only on data dated on or before t; HAR refits on each month's first session (volbt.signals.har).
HAR is the candidate WITH its fallback: on a session where its forecast is <= 0 it forecasts the naive value, and
d_t is 0 there. The target uses the bars after t by definition (it is the outcome), read from a view at the window's
last target date.

This module computes series; it prints and writes nothing. tools/prereg.py measures the block with it on 2002-2009,
and tools/score_prereg.py scores the pre-registered window with it, once.
"""

from __future__ import annotations

from datetime import date

import numpy as np

from volbt.analytics.inference import qlike
from volbt.data.store import YearCache, session_calendar, view
from volbt.signals import har
from volbt.signals.base import RV_MISSING
from volbt.signals.realised import total_log_returns

HORIZON = har.HORIZON


def window(calendar: list[date], start: date, last_target_end: date) -> list[date]:
    """The sessions t >= start whose HORIZON sessions after t all fall on or before last_target_end."""
    days = sorted(calendar)
    out = []
    for i, day in enumerate(days):
        if day >= start and i + HORIZON < len(days) and days[i + HORIZON] <= last_target_end:
            out.append(day)
    return out


def forecasts(store, days: list[date], split: str = "development") -> list[dict]:
    """Per t in `days`: {t, har, har_flags, fit_date, naive}, each forecast from view(t) only."""
    cache = YearCache(store, "optionsdx")
    forecaster = har.HarForecaster()
    rows = []
    for t in days:
        v_view = view(t, split, store, cache)
        dates, r = total_log_returns(v_view.spy_bars(), v_view.dividends())
        v = r ** 2
        value, fit_date, flags = forecaster.forecast(v, dates)
        rows.append({"t": t, "har": value, "har_flags": flags, "fit_date": fit_date, "naive": har.naive_rv22(v)})
    return rows


def realised(store, days: list[date], split: str = "development") -> dict[date, float]:
    """y_t = mean r^2 over the HORIZON sessions after t, for each t in `days`, from one view at the last target."""
    calendar = sorted(session_calendar(store))
    last = calendar[calendar.index(max(days)) + HORIZON]
    final = view(last, split, store, YearCache(store, "optionsdx"))
    dates, r = total_log_returns(final.spy_bars(), final.dividends())
    position = {d: i for i, d in enumerate(dates.astype(object))}
    v = r ** 2
    out = {}
    for t in days:
        i = position[t]
        if i + HORIZON >= v.size:
            raise ValueError(f"the target of {t} runs past {last}")
        out[t] = float(v[i + 1:i + 1 + HORIZON].mean())
    return out


def paired(rows: list[dict], targets: dict[date, float]) -> dict[str, np.ndarray]:
    """The aligned series: y, the two forecasts, their QLIKE losses and d = QLIKE(naive) - QLIKE(HAR)."""
    y = np.array([targets[row["t"]] for row in rows])
    yhat_har = np.array([row["har"] for row in rows])
    yhat_naive = np.array([row["naive"] for row in rows])
    loss_har, loss_naive = qlike(y, yhat_har), qlike(y, yhat_naive)
    return {"y": y, "har": yhat_har, "naive": yhat_naive, "loss_har": loss_har, "loss_naive": loss_naive,
            "d": loss_naive - loss_har}


def block_window(store, first: date, last_target_end: date, split: str = "development") -> list[date]:
    """The block's window: from the first session >= `first` with a HAR forecast, to the last t whose target ends by
    last_target_end. Scanning the first months needs their forecasts, which are computed and thrown away here."""
    days = window(session_calendar(store), first, last_target_end)
    rows = forecasts(store, days[:300], split)
    usable = [row["t"] for row in rows if not row["har_flags"] & RV_MISSING]
    if not usable:
        raise ValueError(f"no HAR forecast in the 300 sessions from {first}")
    return [d for d in days if d >= usable[0]]
