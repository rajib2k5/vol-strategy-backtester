"""A made-up store for the signal tests (not a test file: pytest does not collect it).

tests/engine_store.py's store (quotes and snapshots from 2023-01-03 to 2023-04-28), with longer reference tables so
that HAR has its 504 training pairs before the snapshots start:

    spy_bars   from 2017-01-03 (weekdays; engine_store's holidays from 2022-12), a seeded GARCH(1,1)-like path with
               clustered vol up to 2022-11-30 that ends where engine_store's path starts, then engine_store's path
               (the -8% gap of 2023-04-03 included): about 1,690 sessions
    dividends  made-up quarterly amounts on the third Friday of Mar/Jun/Sep/Dec from 2017-03-17 to 2021-12-17, then
               engine_store's (2022-03-18 to 2023-03-17)
    vix        a seeded path around 18 from 2017-01-03 with made-up shocks, one inside the snapshot window
               (2023-03-13: +40%)

Made-up values only.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd

import engine_store as es
from volbt import build
from volbt.data.store import Store

FIRST_BAR = date(2017, 1, 3)
SHOCKS = {date(2018, 2, 5): 1.9, date(2020, 3, 9): 1.5, date(2023, 3, 13): 1.4}


def sessions() -> list[date]:
    days, day = [], FIRST_BAR
    while day <= es.LAST_BAR:
        if day.weekday() < 5 and day not in es.HOLIDAYS:
            days.append(day)
        day += timedelta(days=1)
    return days


def spot_path() -> dict[date, float]:
    """Clustered-vol closes before engine_store's first bar, engine_store's closes from it (whole cents)."""
    later = es.spot_path()
    early = [d for d in sessions() if d < es.FIRST_BAR]
    rng = np.random.default_rng(17)
    variance, returns = 1e-4, []
    for _ in early:
        shock = rng.standard_normal()
        returns.append(math.sqrt(variance) * shock)
        variance = 2e-6 + 0.10 * variance * shock ** 2 + 0.88 * variance      # persistent, clustered
    # Walk back from engine_store's first close, so the path joins it.
    level, out = later[es.FIRST_BAR], {}
    for day, r in zip(reversed(early), reversed(returns)):
        level *= math.exp(-r)               # r is the return from `day` to the session after it
        out[day] = round(level, 2)
    return {**dict(sorted(out.items())), **later}


def dividend_rows() -> list[tuple[date, float]]:
    rows = []
    for year in range(2017, 2022):
        for month in (3, 6, 9, 12):
            first = date(year, month, 1)
            friday = first + timedelta(days=(4 - first.weekday()) % 7 + 14)
            rows.append((friday, round(1.0 + 0.03 * (year - 2017) + 0.01 * month / 3, 3)))
    return rows + list(es.DIVIDENDS)


def vix_path() -> list[float]:
    rng = np.random.default_rng(23)
    level, out = 18.0, []
    for day in sessions():
        level = max(9.0, level + 0.15 * (18.0 - level) + rng.normal(0.0, 0.8))
        if day in SHOCKS:
            level *= SHOCKS[day]
        out.append(round(level, 2))
    return out


def signal_store(root) -> Store:
    """engine_store's store with the longer reference tables, priced by the M2 build."""
    store = es.make_engine_store(root)
    days, spots = sessions(), spot_path()
    closes = [spots[d] for d in days]
    store.write_table("spy_bars", pd.DataFrame({"date": days, "open": closes, "high": closes, "low": closes,
                                                "close": closes, "adj_close": closes, "volume": [1] * len(days)}),
                      sort_by=("date",))
    rows = dividend_rows()
    store.write_table("dividends", pd.DataFrame({"ex_date": [d for d, _ in rows], "amount": [a for _, a in rows]}),
                      sort_by=("ex_date",))
    vix = vix_path()
    store.write_table("vix", pd.DataFrame({"date": days, "open": vix, "high": vix, "low": vix, "close": vix}),
                      sort_by=("date",))
    build.build_pricing(store)
    return store
