"""Sessions the market closed without notice, and n_window as it could be known at t (milestone 4 fix pass, N2).

The engine's session calendar is the store's: the dates of the SPY bars (decision D3). It already lacks the days the
market closed without notice, before anyone knew they would close. n_window, the number of sessions in
(t, t + 30 calendar days] that the VRP signal divides by, would see such a closure from t on: a look-ahead of up to
30 days (the review found Sandy 2012 shifting s by +0.095 to +0.111 on 20 sessions, and 2018-12-05 by about +0.05 on
21). So a closure counts as a session at every t before its announcement date, and is known from that date on.

    UNSCHEDULED_CLOSURES   (closed date, announcement date, source) for every weekday in the store's range
                           (2000-01-03 to 2026-10-28) that is neither a session nor a scheduled NYSE holiday
    n_window(calendar, t)  sessions of `calendar` in (t, t + 30 days], plus the closures in that window not yet
                           announced at t

A closure is known at every t on or after its announcement date. For 2001 and 2012 no session lies between the last
session before the closure and the announcement, so any date in that gap gives the same n_window. Where the NYSE's and
another market's notices differ, the NYSE's (the later) date is used: SPY lists on NYSE Arca (default taken
2026-11-09, owner can override).

Residual (not fixed here, recorded in the milestone notes): the strategy's own calendar in SessionContext (D3) is the
realised one, so a strategy that counts sessions ahead itself still sees a closure early.

Standard library only.
"""

from __future__ import annotations

from bisect import bisect_right
from datetime import date, timedelta

WINDOW_DAYS = 30

UNSCHEDULED_CLOSURES: tuple[tuple[date, date, str], ...] = (
    (date(2001, 9, 11), date(2001, 9, 11), "September 11 attacks: NYSE closed 2001-09-11 to 09-14, reopened 09-17"),
    (date(2001, 9, 12), date(2001, 9, 11), "September 11 attacks: NYSE closed 2001-09-11 to 09-14, reopened 09-17"),
    (date(2001, 9, 13), date(2001, 9, 11), "September 11 attacks: NYSE closed 2001-09-11 to 09-14, reopened 09-17"),
    (date(2001, 9, 14), date(2001, 9, 11), "September 11 attacks: NYSE closed 2001-09-11 to 09-14, reopened 09-17"),
    (date(2004, 6, 11), date(2004, 6, 7), "NYSE notice of 2004-06-07: national day of mourning, President Reagan"),
    (date(2007, 1, 2), date(2006, 12, 29), "NYSE Group release of 2006-12-29: national day of mourning, "
                                           "President Ford (Nasdaq announced 2006-12-28)"),
    (date(2012, 10, 29), date(2012, 10, 28), "NYSE Euronext statement of 2012-10-28: Hurricane Sandy"),
    (date(2012, 10, 30), date(2012, 10, 29), "NYSE Euronext confirmation of 2012-10-29 (the 10-28 statement said "
                                             "pending confirmation): Hurricane Sandy; csmonitor.com, 2012-10-29, "
                                             "'Hurricane Sandy will keep markets closed Tuesday'"),
    (date(2018, 12, 5), date(2018, 12, 1), "ICE/NYSE press release of 2018-12-01: national day of mourning, "
                                           "President George H. W. Bush"),
    (date(2025, 1, 9), date(2024, 12, 30), "NYSE announcement of 2024-12-30: national day of mourning, "
                                           "President Carter"),
)


def n_window(calendar: list[date], t: date, closures=None, days: int = WINDOW_DAYS) -> int:
    """Sessions of the sorted `calendar` in (t, t + days], plus each closure in that window announced after t
    (`closures` defaults to UNSCHEDULED_CLOSURES)."""
    end = t + timedelta(days=days)
    known = bisect_right(calendar, end) - bisect_right(calendar, t)
    table = UNSCHEDULED_CLOSURES if closures is None else closures
    return known + sum(1 for closed, announced, _ in table if t < closed <= end and announced > t)
