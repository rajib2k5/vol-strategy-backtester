"""Milestone 4, part B (plan sections 5 and 10, task 9): which expiries and contracts the four structures pick.

Expiries: DTE counts to the settlement date (strategies.expiry, decision D16's map); the 50-60 and 22-35 windows are
inclusive; weeklies are never picked; the holiday Fridays (Good Friday 2014-04-18 and 2019-04-19) move the monthly
to the Thursday and DTE counts to it; the calendar's back is the next month's monthly or nothing; nothing over 180
days. Contracts: the ATM strike nearest the parity forward with a call and a put listed (tie: the lower); the
strangle by ADR-0005's spot delta at the engine's mark IV; the calendar's one strike on both expiries. Made-up values.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from strategy_fakes import FakeView, symbol, weekdays
from volbt.engine import settlement
from volbt.strategies import expiry as ex
from volbt.strategies import structures as st
from volbt.strategies.base import LegIntent

D = date
SESSIONS_2015 = weekdays(D(2015, 9, 1), D(2016, 3, 31), {D(2015, 11, 26), D(2015, 12, 25), D(2016, 1, 1)})


# --- settlement-date DTE -------------------------------------------------------------------------------------------

def test_the_settle_map_is_the_engines_and_gives_the_engines_dates():
    assert ex.SETTLE_MAP == settlement.NON_SESSION_EXPIRIES
    last = max(SESSIONS_2015)
    sessions_2018 = weekdays(D(2018, 11, 1), D(2019, 1, 31), {D(2018, 12, 5), D(2018, 12, 25)})
    for expiry, sessions in ((D(2015, 12, 18), SESSIONS_2015), (D(2015, 12, 19), SESSIONS_2015),
                             (D(2016, 6, 17), SESSIONS_2015), (D(2018, 12, 5), sessions_2018),
                             (D(2018, 12, 4), sessions_2018)):
        assert ex.settle_date(expiry, sessions, max(sessions)) == settlement.settle_date(expiry, sessions, max(sessions))
    assert ex.settle_date(D(2018, 12, 5), sessions_2018) == D(2018, 12, 4)
    assert ex.settle_date(D(2015, 12, 19), SESSIONS_2015, last) == D(2015, 12, 18)
    assert ex.settle_date(D(2016, 6, 17), SESSIONS_2015, last) == D(2016, 6, 17)       # after the calendar: own date
    # An unmapped non-session expiry: the engine refuses it; the strategy never picks it.
    assert ex.settle_date(D(2015, 12, 20), SESSIONS_2015, last) is None
    with pytest.raises(settlement.UnmappedExpiry):
        settlement.settle_date(D(2015, 12, 20), SESSIONS_2015, last)
    assert ex.monthly_in_window([D(2015, 12, 20)], D(2015, 10, 26), 0, 180, SESSIONS_2015) == []


def test_dte_counts_to_the_friday_close_of_the_saturday_dated_december_2015_monthly():
    listed = [D(2015, 11, 20), D(2015, 12, 11), D(2015, 12, 19), D(2016, 1, 15)]
    assert ex.dte(D(2015, 12, 19), D(2015, 10, 19), SESSIONS_2015) == 60          # 61 to the listed Saturday
    assert ex.monthly_in_window(listed, D(2015, 10, 19), 50, 60, SESSIONS_2015) == [D(2015, 12, 19)]
    assert ex.monthly_in_window(listed, D(2015, 10, 29), 50, 60, SESSIONS_2015) == [D(2015, 12, 19)]
    # Listed DTE 50, settlement DTE 49: out of the window.
    assert ex.monthly_in_window(listed, D(2015, 10, 30), 50, 60, SESSIONS_2015) == []


def test_the_window_is_inclusive_skips_weeklies_and_keeps_the_180_day_cap():
    sessions = weekdays(D(2023, 1, 1), D(2024, 12, 31))
    monthly, weekly = D(2023, 6, 16), D(2023, 6, 9)
    listed = [weekly, monthly, D(2023, 7, 21), D(2024, 1, 19)]
    for days, inside in ((49, False), (50, True), (60, True), (61, False)):
        found = ex.monthly_in_window(listed, monthly - timedelta(days=days), 50, 60, sessions)
        assert (monthly in found) is inside, days
    assert weekly not in ex.monthly_in_window(listed, weekly - timedelta(days=55), 50, 60, sessions)
    # 2024-01-19 is 218 days after 2023-06-15: never, whatever the window asks.
    assert ex.monthly_in_window(listed, D(2023, 6, 15), 0, 400, sessions) == [D(2023, 6, 16), D(2023, 7, 21)]


@pytest.mark.parametrize("good_friday, thursday", [(D(2014, 4, 18), D(2014, 4, 17)), (D(2019, 4, 19), D(2019, 4, 18))])
def test_a_good_friday_monthly_is_the_thursday_and_dte_counts_to_it(good_friday, thursday):
    sessions = weekdays(D(good_friday.year, 1, 1), D(good_friday.year, 12, 31), {good_friday})
    listed = [thursday, thursday + timedelta(days=28)]
    assert ex.standard_monthly(listed, sessions)[0] == thursday
    assert ex.monthly_in_window(listed, thursday - timedelta(days=50), 50, 60, sessions) == [thursday]
    # 49 days to the Thursday (50 to the Friday): out.
    assert ex.monthly_in_window(listed, thursday - timedelta(days=49), 50, 60, sessions) == []


def test_the_calendars_back_is_the_next_months_monthly_or_nothing():
    sessions = weekdays(D(2015, 1, 1), D(2016, 12, 31), {D(2015, 12, 25), D(2016, 1, 1)})
    listed = [D(2015, 12, 18), D(2016, 1, 8), D(2016, 1, 15), D(2016, 3, 18)]
    assert ex.next_monthly(listed, D(2015, 12, 18), sessions) == D(2016, 1, 15)       # December -> January, no weekly
    # February's monthly is not listed: no back leg, not March's.
    assert ex.next_monthly(listed, D(2016, 1, 15), sessions) is None


# --- contracts -----------------------------------------------------------------------------------------------------

def chain_symbols(expiry, strikes, missing=()):
    return {float(k): {r: symbol(expiry, r, k) for r in ("C", "P") if (k, r) not in missing} for k in strikes}


def test_atm_is_the_strike_nearest_the_forward_listed_with_both_rights():
    e = D(2023, 6, 16)
    symbols = chain_symbols(e, (395, 400, 405))
    assert st.atm_straddle(symbols, 401.0, -1) == (LegIntent(symbol(e, "C", 400), -1), LegIntent(symbol(e, "P", 400), -1))
    assert st.atm_straddle(symbols, 402.5, 1) == (LegIntent(symbol(e, "C", 400), 1), LegIntent(symbol(e, "P", 400), 1))
    no_put = chain_symbols(e, (395, 400, 405), missing={(400, "P")})
    assert st.atm_straddle(no_put, 401.0, -1)[0].osi_symbol == symbol(e, "C", 405)
    assert st.atm_straddle({}, 401.0, -1) is None
    with pytest.raises(ValueError):
        st.atm_straddle(symbols, 401.0, 2)


def test_the_strangle_takes_the_deltas_nearest_a_quarter_and_needs_the_call_above_the_put():
    calls = [(395.0, "C", "c395", 0.62), (410.0, "C", "c410", 0.375), (415.0, "C", "c415", 0.125),
             (420.0, "C", "c420", 0.1)]
    puts = [(380.0, "P", "p380", -0.20), (385.0, "P", "p385", -0.26), (390.0, "P", "p390", -0.33)]
    # |0.375 - 0.25| = |0.125 - 0.25| exactly: the tie goes to the lower strike.
    assert st.delta_strangle(calls + puts) == (LegIntent("c410", -1), LegIntent("p385", -1))
    assert st.delta_strangle(calls + puts, 0.1) == (LegIntent("c420", -1), LegIntent("p380", -1))
    assert st.delta_strangle(calls) is None
    crossed = [(380.0, "C", "c380", 0.25), (390.0, "P", "p390", -0.25)]
    assert st.delta_strangle(crossed) is None


def adr_0005_delta(spot, forward, strike, tau, rate, sigma, is_call):
    """ADR-0005: DF (F/S) N(d1) for a call, -DF (F/S) N(-d1) for a put, written out here."""
    d1 = (math.log(forward / strike) + sigma * sigma * tau / 2) / (sigma * math.sqrt(tau))
    n = 0.5 * (1 + math.erf((d1 if is_call else -d1) / math.sqrt(2)))
    return (1 if is_call else -1) * math.exp(-rate * tau) * forward / spot * n


def test_the_strangle_deltas_are_adr_0005s_at_the_engines_mark_iv():
    t, e, later = D(2023, 4, 20), D(2023, 6, 16), D(2023, 9, 15)
    in_smile = {symbol(e, "C", 420): (True, 0.30), symbol(e, "P", 380): (True, 0.35),
                symbol(e, "C", 410): (False, 0.50)}                 # an IV, but not in the smile: the surface's
    view = FakeView(t, {e: 402.0, later: 404.0}, range(370, 431, 5), spot=401.0, rate=0.04, ivs=in_smile)
    chain = st.Chain(view, t, "optionsdx")
    deltas = {(k, r): d for k, r, _, d in chain.deltas(e)}
    tau = (e - t).days / 365
    for (strike, right), sigma in (((420.0, "C"), 0.30), ((380.0, "P"), 0.35), ((410.0, "C"), 0.20),
                                   ((390.0, "P"), 0.20)):
        # r is the last rate dated before the session (0.04), never the session's own row (0.09).
        assert deltas[(strike, right)] == pytest.approx(adr_0005_delta(401.0, 402.0, strike, tau, 0.04, sigma,
                                                                       right == "C"), rel=1e-12)
    surface = {(k, r): d for k, r, _, d in st.Chain(view, t, "optionsdx", surface_mode=True).deltas(e)}
    assert surface[(420.0, "C")] == pytest.approx(adr_0005_delta(401.0, 402.0, 420.0, tau, 0.04, 0.20, True),
                                                  rel=1e-12)


def test_the_calendar_takes_one_strike_listed_on_both_expiries_nearest_the_front_forward():
    front, back = D(2023, 5, 19), D(2023, 6, 16)
    front_symbols = chain_symbols(front, (395, 400, 405))
    back_symbols = chain_symbols(back, (395, 400, 405), missing={(395, "P")})
    legs = st.straddle_calendar(front_symbols, back_symbols, 396.0)
    assert legs == (LegIntent(symbol(front, "C", 400), -1), LegIntent(symbol(front, "P", 400), -1),
                    LegIntent(symbol(back, "C", 400), 1), LegIntent(symbol(back, "P", 400), 1))
    assert st.straddle_calendar(front_symbols, {}, 396.0) is None
