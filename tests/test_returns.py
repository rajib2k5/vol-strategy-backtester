"""Returns and their metrics (volbt.analytics.returns, ADR-0007 §6): ADR-0007 tests 7 and 8, and small hand cases.

Every input is a literal; the dates are in 2017-2019.
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pytest

from volbt.analytics import returns as rt

EXCESS = [0.01, -0.01, 0.02, 0.00]          # ADR-0007 test 8


def test_a_nav_of_1_004_287_after_1_000_000_is_a_return_of_0_4287_percent():
    """ADR-0007 test 7; the first session has no return, so n NAVs give n - 1 returns."""
    assert rt.daily_returns([1_000_000.0, 1_004_287.0]) == pytest.approx([0.004287], abs=1e-12)
    r = rt.daily_returns([100.0, 110.0, 99.0])
    assert r == pytest.approx([0.1, -0.1], abs=1e-15)
    assert rt.daily_returns([100.0]).size == 0


def test_the_riskfree_return_uses_the_previous_rate_over_the_calendar_days():
    """Friday 2019-01-18 to Tuesday 2019-01-22 (Monday was a holiday) is 4 days at Friday's rate; the first session
    has none, and Thursday to Friday is 1 day at Thursday's rate."""
    days = [date(2019, 1, 17), date(2019, 1, 18), date(2019, 1, 22)]
    rf = rt.riskfree_returns([0.02, 0.03, 0.05], days)
    assert rf == pytest.approx([math.expm1(0.02 * 1 / 365), math.expm1(0.03 * 4 / 365)], rel=1e-14)
    assert rt.riskfree_returns([0.03, 0.05], np.array(days[1:], dtype="datetime64[D]")) == pytest.approx(
        [math.expm1(0.03 * 4 / 365)], rel=1e-14)
    with pytest.raises(ValueError, match="aligned"):
        rt.riskfree_returns([0.02, 0.03], days)


def test_sharpe_by_hand_is_6_148_and_unchanged_by_scaling():
    """ADR-0007 test 8: mean 0.005, sample std 0.012910, sqrt(252) x 0.005 / 0.012910 = 6.148; x2 leaves it."""
    assert rt.sharpe(EXCESS) == pytest.approx(6.148, abs=5e-4)
    assert rt.sharpe(EXCESS) == pytest.approx(math.sqrt(252) * 0.005 / math.sqrt(5e-4 / 3), rel=1e-12)
    assert rt.sharpe([2 * x for x in EXCESS]) == pytest.approx(rt.sharpe(EXCESS), rel=1e-12)
    assert math.isnan(rt.sharpe([0.01])) and math.isnan(rt.sharpe([0.01, 0.01]))


def test_sortino_divides_by_the_root_mean_square_of_the_losses_over_all_values():
    """[0.01, -0.01, 0.02, 0.00]: min(x, 0) = [0, -0.01, 0, 0], mean of squares 1e-4 / 4, root 0.005, so the ratio is
    sqrt(252) x 0.005 / 0.005 = sqrt(252) (over the one negative value alone it would be sqrt(252) / 2)."""
    assert rt.sortino(EXCESS) == pytest.approx(math.sqrt(252), rel=1e-12)
    assert math.isnan(rt.sortino([0.01, 0.02, 0.0]))


def test_max_drawdown_is_the_most_negative_fall_from_the_running_peak():
    """[100, 120, 90, 130, 117]: 90 / 120 - 1 = -0.25 beats 117 / 130 - 1 = -0.10."""
    assert rt.max_drawdown([100.0, 120.0, 90.0, 130.0, 117.0]) == pytest.approx(-0.25, abs=1e-15)
    assert rt.max_drawdown([100.0, 101.0, 102.0]) == 0.0


def test_cagr_compounds_over_365_day_years_and_calmar_divides_by_the_drawdown():
    """100 -> 121 from 2017-01-01 to 2019-01-01 (730 days): 1.21^(365/730) - 1 = 10%. With a fall from 110 to 99 on
    the way (-10%), Calmar is 0.10 / 0.10 = 1."""
    days = [date(2017, 1, 1), date(2018, 1, 1), date(2019, 1, 1)]
    assert rt.cagr([100.0, 110.0, 121.0], days) == pytest.approx(0.10, abs=1e-12)
    days4 = [date(2017, 1, 1), date(2017, 6, 1), date(2018, 1, 1), date(2019, 1, 1)]
    assert rt.calmar([100.0, 110.0, 99.0, 121.0], days4) == pytest.approx(1.0, abs=1e-12)
    assert math.isnan(rt.calmar([100.0, 110.0, 121.0], days))           # never falls
    assert rt.cagr([100.0, 0.0], days[:2]) == -1.0                      # everything lost
    assert math.isnan(rt.cagr([100.0, 101.0], [date(2019, 1, 2)] * 2))   # no time elapsed
