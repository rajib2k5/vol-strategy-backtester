"""Which expiry a strategy trades, and when the reference strategy closes (ADR-0002 test 9, ADR-0003 test 9).

Pure date arithmetic over hand-made lists of expiries and a hand-made BookState / SessionContext: no store is
read, except in the one run test that shows the loop hands the strategy the right next session.
"""

from __future__ import annotations

from datetime import date, timedelta

import engine_helpers as eh
from volbt.strategies import expiry
from volbt.strategies.base import BookState, LotState, PendingOrderState, PositionState, SessionContext
from volbt.strategies.expiry import MAX_EXPIRY_DAYS, nearest_monthly, standard_monthly, third_friday
from volbt.strategies.reference import RollingShortStraddle

# SPY's expiries listed around 2022-04-01: weeklies on Mon/Wed/Fri, the monthly on Thursday 2022-04-14 because
# Good Friday, 2022-04-15 (the third Friday), was a market holiday.
APRIL_2022 = [date(2022, 4, 1), date(2022, 4, 4), date(2022, 4, 6), date(2022, 4, 8), date(2022, 4, 11),
              date(2022, 4, 13), date(2022, 4, 14), date(2022, 4, 18), date(2022, 4, 20), date(2022, 4, 22),
              date(2022, 4, 25), date(2022, 4, 27), date(2022, 4, 29),
              date(2022, 5, 20), date(2022, 6, 17), date(2022, 7, 15)]


def weekdays(first: date, last: date, holidays=()) -> frozenset:
    """A hand-made exchange calendar: the weekdays from first to last, without `holidays`."""
    days = (first + timedelta(days=i) for i in range((last - first).days + 1))
    return frozenset(day for day in days if day.weekday() < 5 and day not in set(holidays))


# Good Fridays, third Fridays that were not sessions: 2014-04-18, 2019-04-19, 2022-04-15.
GOOD_FRIDAYS = (date(2014, 4, 18), date(2019, 4, 19), date(2022, 4, 15))
SESSIONS = weekdays(date(2014, 1, 2), date(2024, 12, 31), GOOD_FRIDAYS)


def test_a_14_dte_target_on_2022_04_01_selects_the_thursday_monthly_not_a_weekly():
    """ADR-0002 test 9: 2022-04-14, the Thursday before Good Friday, and never 04-11, 04-13 or 04-18."""
    chosen = nearest_monthly(APRIL_2022, date(2022, 4, 1), SESSIONS, target_dte=14)
    assert chosen == date(2022, 4, 14)
    assert chosen not in (date(2022, 4, 11), date(2022, 4, 13), date(2022, 4, 18))
    # a target of 12 days sits exactly on the 04-13 weekly (DTE 12): the monthly is still chosen
    assert nearest_monthly(APRIL_2022, date(2022, 4, 1), SESSIONS, target_dte=12) == date(2022, 4, 14)
    # a target of 17 sits on the 04-18 weekly, and the monthly 04-14 is the nearest standard one
    assert nearest_monthly(APRIL_2022, date(2022, 4, 1), SESSIONS, target_dte=17, min_dte=0) == date(2022, 4, 14)


def test_standard_monthly_is_the_third_friday_when_it_is_listed():
    assert third_friday(2022, 4) == date(2022, 4, 15)
    assert third_friday(2023, 3) == date(2023, 3, 17)
    assert third_friday(2024, 3) == date(2024, 3, 15)
    # the third Friday is listed: it wins over the weeklies around it, one monthly per month
    march_2023 = [date(2023, 3, 10), date(2023, 3, 15), date(2023, 3, 16), date(2023, 3, 17), date(2023, 3, 24),
                  date(2023, 3, 31)]
    assert standard_monthly(march_2023, SESSIONS) == [date(2023, 3, 17)]
    # several months, in order
    assert standard_monthly(march_2023 + APRIL_2022, SESSIONS) == [date(2022, 4, 14), date(2022, 5, 20), date(2022, 6, 17),
                                                        date(2022, 7, 15), date(2023, 3, 17)]


def test_a_holiday_third_friday_falls_back_to_the_last_session_before_it_and_to_nothing_else():
    """Rule c: only the last session before a non-session third Friday stands in for it (M3 round-3 review: the
    three-day lookback took the Wednesday weekly 2022-04-13 when Thursday 04-14 was not listed on DoltHub)."""
    friday = date(2022, 4, 15)                   # Good Friday; the last session before it is Thursday 04-14
    assert standard_monthly([date(2022, 4, 13), date(2022, 4, 14)], SESSIONS) == [date(2022, 4, 14)]
    # the Thursday not listed: the Wednesday and Tuesday weeklies before it are not the monthly
    assert standard_monthly([date(2022, 4, 12), date(2022, 4, 13)], SESSIONS) == []
    assert nearest_monthly([date(2022, 4, 13), date(2022, 5, 20)], date(2022, 3, 16), SESSIONS, 30, 21, 180) == date(2022, 5, 20)
    # a day AFTER the third Friday never stands in for it (Monday 04-18 is not the Saturday rule)
    assert standard_monthly([friday + timedelta(days=3)], SESSIONS) == []
    # and when the Friday itself is listed, the Thursday before it is not a second monthly
    assert standard_monthly([date(2023, 3, 16), date(2023, 3, 17)], SESSIONS) == [date(2023, 3, 17)]


def test_juneteenth_2026_takes_thursday_06_18_or_no_monthly():
    """Juneteenth, Friday 2026-06-19, is the third Friday of June 2026 and not a session: the monthly is Thursday
    06-18 when listed, never the Tuesday weekly 06-16 (the round-3 review's DoltHub decision day 2026-06-03)."""
    june = weekdays(date(2026, 1, 2), date(2026, 12, 31), (date(2026, 6, 19),))
    assert third_friday(2026, 6) == date(2026, 6, 19)
    assert standard_monthly([date(2026, 6, 16), date(2026, 6, 18)], june) == [date(2026, 6, 18)]
    assert standard_monthly([date(2026, 6, 16)], june) == []


def test_a_saturday_dated_monthly_is_the_month_s_standard_monthly_unless_the_friday_is_listed():
    """Rule b: OptionsDX dates the December 2015 monthly Saturday 2015-12-19 (settled at the Friday 12-18 close
    through D16's map); the picker returned no December 2015 monthly at all before round 3 (finding N1)."""
    assert date(2015, 12, 18) in SESSIONS and third_friday(2015, 12) == date(2015, 12, 18)
    assert standard_monthly([date(2015, 12, 19), date(2015, 12, 31)], SESSIONS) == [date(2015, 12, 19)]
    assert nearest_monthly([date(2015, 12, 19), date(2015, 12, 31), date(2016, 1, 15)], date(2015, 11, 16), SESSIONS,
                           30, 21, 180) == date(2015, 12, 19)
    # the Friday listed as well: the Friday is the monthly, the Saturday is not a second one
    assert standard_monthly([date(2015, 12, 18), date(2015, 12, 19)], SESSIONS) == [date(2015, 12, 18)]
    # a Saturday that does not follow the third Friday is not a monthly
    assert standard_monthly([date(2015, 12, 12), date(2015, 12, 26)], SESSIONS) == []


def test_the_good_friday_months_take_the_thursday_before():
    """The three Good Fridays that were third Fridays: the monthly is the Thursday before, with weeklies around it."""
    for friday in GOOD_FRIDAYS:
        thursday, wednesday, monday = (friday - timedelta(days=n) for n in (1, 2, 4))
        listed = [monday, wednesday, thursday, friday + timedelta(days=3), friday + timedelta(days=7)]
        assert friday not in SESSIONS
        assert standard_monthly(listed, SESSIONS) == [thursday], friday


def test_an_unlisted_third_friday_that_is_a_session_leaves_the_month_without_a_monthly():
    """M3 round-2 review: 2020-03-20 was a session, so the Wednesday weekly 2020-03-18 is not March's monthly
    (the DoltHub run c5b03bcc held 10 such Wednesday weeklies out of 35 positions)."""
    listed = [date(2020, 3, 18), date(2020, 4, 17)]
    assert date(2020, 3, 20) in SESSIONS
    assert standard_monthly(listed, SESSIONS) == [date(2020, 4, 17)]
    assert nearest_monthly(listed, date(2020, 3, 2), SESSIONS, target_dte=16) == date(2020, 4, 17)
    # nor is the session before it, Thursday 2020-03-19: rule c applies only to a third Friday that is not a session
    assert standard_monthly([date(2020, 3, 19), date(2020, 4, 17)], SESSIONS) == [date(2020, 4, 17)]
    # a third Friday past the calendar's last date is not known to be a holiday, so it is treated as a session
    end = weekdays(date(2024, 1, 2), date(2024, 12, 31))
    assert standard_monthly([date(2025, 1, 15)], end) == []


def test_no_expiry_beyond_180_days_whatever_max_dte_is_asked():
    """The 180-day constraint: nearest_monthly caps max_dte at MAX_EXPIRY_DAYS."""
    assert MAX_EXPIRY_DAYS == 180
    today = date(2022, 12, 18)
    far = third_friday(2023, 6)                  # 180 days after 2022-12-18
    assert (far - today).days == 180
    beyond = third_friday(2023, 7)               # 209 days
    assert (beyond - today).days > 180
    listed = [third_friday(2023, 1), far, beyond, third_friday(2023, 9)]
    # asked for a 300-day target and a 400-day ceiling, the answer is still inside 180 days
    chosen = nearest_monthly(listed, today, SESSIONS, target_dte=300, max_dte=400)
    assert chosen == far and (chosen - today).days == 180
    # with only longer expiries listed there is no answer at all
    assert nearest_monthly([beyond, third_friday(2023, 9)], today, SESSIONS, target_dte=300, max_dte=400) is None
    # 181 days is out: move today back one day so that `far` is 181 days away
    assert nearest_monthly([far], today - timedelta(days=1), SESSIONS, target_dte=181, max_dte=400) is None
    # the cap applies to every parameter combination, not only the defaults
    for target in (30, 90, 200, 400):
        for ceiling in (60, 180, 400, 10_000):
            got = nearest_monthly(listed + APRIL_2022, today, SESSIONS, target_dte=target, max_dte=ceiling)
            assert got is None or 0 <= (got - today).days <= 180


def test_min_dte_and_ties_in_nearest_monthly():
    today = date(2023, 1, 3)
    listed = [date(2023, 2, 17), date(2023, 3, 17)]          # 45 and 73 days
    assert nearest_monthly(listed, today, SESSIONS, target_dte=30, min_dte=21) == date(2023, 2, 17)
    assert nearest_monthly(listed, today, SESSIONS, target_dte=30, min_dte=50) == date(2023, 3, 17)
    assert nearest_monthly(listed, today, SESSIONS, target_dte=59, min_dte=0) == date(2023, 2, 17)    # 14 vs 14: the earlier
    assert nearest_monthly(listed, today, SESSIONS, target_dte=30, min_dte=100) is None


# --- ADR-0003 test 9: the reference strategy's close order ---------------------------------------------------

EXPIRY = date(2024, 3, 15)          # a Friday
CALL, PUT = "SPY   240315C00500000", "SPY   240315P00500000"


def book_with_short_straddle(contracts: int = 10, pending: bool = False) -> tuple[BookState, PositionState]:
    lots = (LotState(1, 1, CALL, EXPIRY, 500.0, "C", -contracts), LotState(2, 1, PUT, EXPIRY, 500.0, "P", -contracts))
    position = PositionState(1, "short_straddle", "open", date(2024, 2, 9), lots)
    pending_orders = (PendingOrderState(9, 1, "close", date(2024, 3, 6)),) if pending else ()
    return BookState(date(2024, 3, 7), 99_000_000, 0, (position,), pending_orders), position


def ctx(session: date, next_session: date | None) -> SessionContext:
    return SessionContext(session, next_session, True, "optionsdx", "quote", SESSIONS)


def test_the_close_intent_is_created_when_dte_at_the_next_session_reaches_exit_dte():
    """ADR-0003 test 9: expiry Fri 2024-03-15, exit_dte 7: created on 2024-03-07 (DTE at 03-08 is 7) for the 03-08
    fill, and not on 2024-03-06 (DTE at 03-07 is 8)."""
    strategy = RollingShortStraddle(exit_dte=7)
    book, position = book_with_short_straddle()
    on_the_7th = strategy.exit_order(position, book, ctx(date(2024, 3, 7), date(2024, 3, 8)))
    assert on_the_7th is not None
    assert (on_the_7th.position_id, on_the_7th.intent, on_the_7th.exit_reason) == (1, "close", "dte")
    assert on_the_7th.packages == 10
    assert {(leg.osi_symbol, leg.ratio) for leg in on_the_7th.legs} == {(CALL, 1), (PUT, 1)}      # buy back both shorts
    assert strategy.exit_order(position, book, ctx(date(2024, 3, 6), date(2024, 3, 7))) is None
    # earlier days, and the whole of decide(): exactly one close intent over the weeks before expiry
    days = [date(2024, 3, 1) + timedelta(days=i) for i in range(0, 14) if (date(2024, 3, 1) + timedelta(days=i)).weekday() < 5]
    created = [d for d, nxt in zip(days, days[1:])
               if strategy.exit_order(position, book, ctx(d, nxt)) is not None]
    # from the first day the rule holds on (the engine then lets one pending order stand per position)
    assert created == [date(2024, 3, 7), date(2024, 3, 8), date(2024, 3, 11), date(2024, 3, 12), date(2024, 3, 13)]


def test_exit_dte_boundary_is_inclusive_at_every_exit_dte():
    book, position = book_with_short_straddle()
    for exit_dte in (1, 3, 7, 14):
        strategy = RollingShortStraddle(exit_dte=exit_dte)
        at_boundary = EXPIRY - timedelta(days=exit_dte)          # the next session, exit_dte days before expiry
        before_boundary = at_boundary - timedelta(days=1)
        assert strategy.exit_order(position, book, ctx(at_boundary - timedelta(days=1), at_boundary)) is not None
        assert strategy.exit_order(position, book, ctx(before_boundary - timedelta(days=1), before_boundary)) is None


def test_exit_dte_zero_holds_to_expiry():
    """ADR-0003's sweep value 0: no close intent, not even on the session before expiry (DTE at the next is 0)."""
    strategy = RollingShortStraddle(exit_dte=0)
    book, position = book_with_short_straddle()
    for today, nxt in ((date(2024, 3, 6), date(2024, 3, 7)), (date(2024, 3, 13), date(2024, 3, 14)),
                       (date(2024, 3, 14), EXPIRY), (EXPIRY, date(2024, 3, 18))):
        assert strategy.exit_order(position, book, ctx(today, nxt)) is None, today


def test_no_close_intent_without_lots_without_a_next_session_or_with_one_pending():
    strategy = RollingShortStraddle(exit_dte=7)
    book, position = book_with_short_straddle()
    assert strategy.exit_order(position, book, ctx(date(2024, 3, 7), None)) is None
    pending_book, _ = book_with_short_straddle(pending=True)
    assert strategy.exit_order(position, pending_book, ctx(date(2024, 3, 7), date(2024, 3, 8))) is None
    flat = PositionState(1, "short_straddle", "open", date(2024, 2, 9),
                         tuple(LotState(i, 1, s, EXPIRY, 500.0, r, 0) for i, (s, r) in enumerate(((CALL, "C"), (PUT, "P")))))
    assert strategy.exit_order(flat, book, ctx(date(2024, 3, 7), date(2024, 3, 8))) is None


def test_the_loop_hands_the_strategy_the_session_after_the_order_day(engine_store, tmp_path):
    """ADR-0003 test 9 through a run: the first position expires 2023-02-17; with exit_dte 7 the close order is
    created on Thursday 02-09 (the next session, Friday 02-10, has DTE 7) and fills on 02-10; not on 02-08."""
    result = eh.run(engine_store, tmp_path, RollingShortStraddle(exit_dte=7), stop_after=date(2023, 2, 14))
    orders, fills_table = eh.table(result, "orders"), eh.table(result, "fills")
    closes = orders[orders["intent"] == "close"]
    assert len(closes) == 1
    close = closes.iloc[0]
    assert (close["created_date"], close["resolved_date"], close["exit_reason"]) == (date(2023, 2, 9), date(2023, 2, 10), "dte")
    assert close["created_date"] != date(2023, 2, 8)
    closing_fills = fills_table[fills_table["order_id"] == close["order_id"]]
    assert len(closing_fills) == 2 and set(closing_fills["fill_date"]) == {date(2023, 2, 10)}
    assert expiry.third_friday(2023, 2) == date(2023, 2, 17)
