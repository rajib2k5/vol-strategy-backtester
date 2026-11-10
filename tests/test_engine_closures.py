"""n_window and the market's closures without notice (milestone 4 fix pass, review finding N2).

The session calendar is the realised one, so it lacks a closure before anyone knew of it. n_window counts such a
closure as a session at every t before its announcement date (volbt.engine.closures). Calendars here are made up:
the weekdays of a period minus the dates the test removes.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

from volbt.engine import closures
from volbt.engine.loop import Run

D = date


def weekdays(first: date, last: date, removed=()) -> list[date]:
    out, day = [], first
    while day <= last:
        if day.weekday() < 5 and day not in removed:
            out.append(day)
        day += timedelta(days=1)
    return out


def test_the_table_lists_weekdays_announced_on_or_before_they_closed():
    assert len(closures.UNSCHEDULED_CLOSURES) == 10
    for closed, announced, source in closures.UNSCHEDULED_CLOSURES:
        assert closed.weekday() < 5 and announced <= closed and source


def test_sandy_counts_as_two_sessions_until_it_was_announced():
    """2012-10-29 and 10-30 closed without notice (announced 10-28 and 10-29). At 10-26 the window (10-26, 11-25]
    holds the realised sessions plus those two; at 10-31 they are past."""
    calendar = weekdays(D(2012, 9, 1), D(2012, 12, 31), removed={D(2012, 10, 29), D(2012, 10, 30), D(2012, 11, 22)})
    realised = sum(1 for d in calendar if D(2012, 10, 26) < d <= D(2012, 11, 25))
    assert closures.n_window(calendar, D(2012, 10, 26)) == realised + 2
    assert closures.n_window(calendar, D(2012, 9, 28)) == sum(1 for d in calendar if D(2012, 9, 28) < d
                                                              <= D(2012, 10, 28)) + 0       # 10-29 is 31 days out
    assert closures.n_window(calendar, D(2012, 10, 1)) == sum(1 for d in calendar if D(2012, 10, 1) < d
                                                              <= D(2012, 10, 31)) + 2


def test_sandy_tuesday_is_dated_by_its_confirmation():
    """Fix pass 2, item 7 (review B claim 7): 10-29 was announced on Sunday 10-28, the second day (10-30) only on
    10-29 (the 10-28 statement said "pending confirmation"). No session lies between, so n_window is the same."""
    table = {closed: announced for closed, announced, _ in closures.UNSCHEDULED_CLOSURES}
    assert table[D(2012, 10, 29)] == D(2012, 10, 28) and table[D(2012, 10, 30)] == D(2012, 10, 29)
    calendar = weekdays(D(2012, 9, 1), D(2012, 12, 31), removed={D(2012, 10, 29), D(2012, 10, 30), D(2012, 11, 22)})
    for t in (D(2012, 10, 26), D(2012, 10, 28)):
        realised = sum(1 for d in calendar if t < d <= t + timedelta(days=30))
        assert closures.n_window(calendar, t) == realised + (2 if t == D(2012, 10, 26) else 1)
    assert closures.n_window(calendar, D(2012, 10, 29)) == sum(1 for d in calendar if D(2012, 10, 29) < d
                                                               <= D(2012, 11, 28))


def test_a_closure_is_known_from_its_announcement_date():
    """2018-12-05 was announced on Saturday 12-01: unknown at Friday 11-30, known at Monday 12-03."""
    calendar = weekdays(D(2018, 10, 1), D(2019, 2, 28), removed={D(2018, 12, 5), D(2018, 11, 22), D(2018, 12, 25),
                                                                 D(2019, 1, 1), D(2019, 1, 21), D(2019, 2, 18)})

    def realised(t):
        return sum(1 for d in calendar if t < d <= t + timedelta(days=30))

    assert closures.n_window(calendar, D(2018, 11, 30)) == realised(D(2018, 11, 30)) + 1
    assert closures.n_window(calendar, D(2018, 12, 3)) == realised(D(2018, 12, 3))
    assert closures.n_window(calendar, D(2018, 12, 4)) == realised(D(2018, 12, 4))
    # A made-up table: a closure announced on the session itself is known at that session.
    made_up = ((D(2018, 12, 5), D(2018, 11, 30), "made up"),)
    assert closures.n_window(calendar, D(2018, 11, 30), made_up) == realised(D(2018, 11, 30))
    assert closures.n_window(calendar, D(2018, 11, 29), made_up) == realised(D(2018, 11, 29)) + 1


def test_the_engine_counts_its_window_with_the_closures():
    calendar = weekdays(D(2012, 9, 1), D(2012, 12, 31), removed={D(2012, 10, 29), D(2012, 10, 30), D(2012, 11, 22)})
    run = SimpleNamespace(calendar=calendar)
    for t in (D(2012, 10, 1), D(2012, 10, 26), D(2012, 10, 31)):
        assert Run.n_window(run, t) == closures.n_window(calendar, t)
    assert Run.n_window(run, D(2012, 10, 26)) == sum(1 for d in calendar if D(2012, 10, 26) < d
                                                     <= D(2012, 11, 25)) + 2
