"""The forecast test's series (tools/forecast_test.py; milestone 4, plan section 6, tasks 7 and 8).

Made-up stores (tests/engine_store.py, tests/signal_store.py) and made-up literals; the real-data tests check only the
windows' dates. No test here computes a loss on real data.
"""

from __future__ import annotations

import math
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

import engine_store as es  # noqa: E402
import forecast_test as ft  # noqa: E402
import signal_store as ss  # noqa: E402
from test_engine_lookahead import perturbed_store  # noqa: E402
from volbt.signals.base import RV_MISSING  # noqa: E402

T0 = date(2023, 3, 1)


def weekdays(n, start=date(2015, 1, 5)):
    days, day = [], start
    while len(days) < n:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def test_the_window_keeps_the_sessions_whose_21_session_target_ends_by_the_last_date():
    calendar = weekdays(30)
    assert ft.window(calendar, calendar[2], calendar[25]) == calendar[2:5]
    assert ft.window(calendar, calendar[0], calendar[20]) == []


def test_d_is_the_naive_loss_minus_the_har_loss():
    days = weekdays(3)
    rows = [{"t": t, "har": 2e-4, "har_flags": 0, "fit_date": None, "naive": n} for t, n in zip(days, (1e-4, 2e-4,
                                                                                                         4e-4))]
    out = ft.paired(rows, dict(zip(days, (2e-4, 2e-4, 2e-4))))
    assert out["loss_har"].tolist() == [0.0, 0.0, 0.0]
    assert out["d"].tolist() == pytest.approx([1 - math.log(2), 0.0, math.log(2) - 0.5], abs=1e-15)


def test_the_target_is_the_mean_squared_total_return_of_the_21_sessions_after_t(engine_store):
    """By hand from the fixture's closes and its 2023-03-17 dividend (1.616), which falls inside the target."""
    spots, sessions = es.spot_path(), es.sessions()
    i = sessions.index(T0)
    dividend = dict(es.DIVIDENDS)
    squares = [math.log((spots[sessions[j]] + dividend.get(sessions[j], 0.0)) / spots[sessions[j - 1]]) ** 2
               for j in range(i + 1, i + 22)]
    assert ft.realised(engine_store, [T0], "validation")[T0] == pytest.approx(sum(squares) / 21, rel=1e-12)


@pytest.fixture(scope="module")
def two_stores(tmp_path_factory):
    store_a = ss.signal_store(tmp_path_factory.mktemp("forecast_store_a"))
    return store_a, perturbed_store(store_a, tmp_path_factory.mktemp("forecast_store_b"), T0)


def test_a_forecast_up_to_t0_does_not_move_when_every_input_after_t0_changes(two_stores):
    store_a, store_b = two_stores
    days = [d for d in ss.sessions() if es.FIRST_SNAPSHOT <= d <= es.LAST_SNAPSHOT]
    rows_a, rows_b = ft.forecasts(store_a, days, "validation"), ft.forecasts(store_b, days, "validation")
    before = sum(d <= T0 for d in days)
    assert rows_a[:before] == rows_b[:before]
    assert not any(r["har_flags"] & RV_MISSING for r in rows_a)
    assert {r["fit_date"] for r in rows_a[:before]} == {date(2023, 1, 3), date(2023, 2, 1), date(2023, 3, 1)}
    assert rows_a[before:] != rows_b[before:]          # the premise: the changed future reaches later forecasts


@pytest.mark.real_data
def test_the_scored_window_has_2495_sessions_and_the_block_window_starts_with_har():
    from volbt import config
    from volbt.data.store import Store, session_calendar

    store = Store(config.store_dir())
    calendar = session_calendar(store)
    days = ft.window(calendar, date(2010, 1, 4), date(2019, 12, 31))
    assert (len(days), days[0], days[-1]) == (2495, date(2010, 1, 4), calendar[calendar.index(date(2019, 12, 31)) - 21])
    block = ft.block_window(store, date(2002, 1, 2), date(2009, 12, 31))
    assert (block[0], len(block)) == (date(2002, 4, 1), 1934)
    assert np.isnan(ft.forecasts(store, [date(2002, 3, 28)])[0]["har"])
