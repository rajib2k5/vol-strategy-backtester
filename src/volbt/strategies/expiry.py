"""Which expiry a strategy trades: the standard monthly (ADR-0002 §5), never beyond 180 days.

The standard monthly expiry is the third Friday of the month, or the session before it when that Friday
is not a session (Thursday 2022-04-14, the day before Good Friday). We find it from the LISTED expiries and
the session calendar (decision D3: the engine hands it to the strategy in SessionContext.sessions; only
unscheduled closures leak, a day early). Per month, in this order:

  a. the third Friday, if it is listed;
  b. else the Saturday after it, if it is listed: the legacy Saturday-dated monthlies (OptionsDX dates the
     December 2015 monthly 2015-12-19; it settles at the Friday close through decision D16's map);
  c. else, ONLY when the third Friday is not a session, the last session before it, if it is listed;
  d. else no monthly that month.

So a weekly listed on another day of that week is never chosen. (M3 round-2 review: without the calendar, an
unlisted third Friday let a Wednesday weekly stand in for it, 10 of the 35 positions of DoltHub run c5b03bcc.
Round-3 review: the three-day lookback that replaced it still took the Wednesday weekly 2022-04-13 when the
Thursday 04-14 was not listed, and 2026-06-16 for Juneteenth 2026; and it never took the Saturday 2015-12-19.)
A third Friday after the calendar's last date is not known to be a holiday: it is treated as a session.

THE 180-DAY CONSTRAINT (ADR-0008 amendment 8, proposed, and the milestone-2 walkthrough's "Not done").
Beyond 180 days the pricing build's one DGS3MO rate leaves a carry gap that PARITY_OUTLIER measures on
15.4% of OptionsDX's quotes. Until the owner decides on a per-expiry rate, strategies trade expiries of
at most MAX_EXPIRY_DAYS: nearest_monthly never returns a longer one, whatever it is asked for.
"""

from __future__ import annotations

from datetime import date, timedelta

FRIDAY = 4                  # date.weekday()
MAX_EXPIRY_DAYS = 180       # the constraint above


def third_friday(year: int, month: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(FRIDAY - first.weekday()) % 7 + 14)


def standard_monthly(expiries, sessions) -> list[date]:
    """The standard monthly expiries among the listed `expiries` (dates), ascending, at most one per month.

    `sessions` is the exchange calendar (a set of dates, future ones included). Per month: the third Friday, else
    the Saturday after it, else (only when the third Friday is not a session) the last session before it; each
    only if it is listed (Good Friday 2022-04-15 -> Thursday 04-14; December 2015 -> Saturday 12-19).
    """
    listed = set(expiries)
    sessions = sessions if isinstance(sessions, (set, frozenset)) else frozenset(sessions)
    first, last = (min(sessions), max(sessions)) if sessions else (None, None)
    found = set()
    for year, month in sorted({(day.year, day.month) for day in listed}):
        friday = third_friday(year, month)
        saturday = friday + timedelta(days=1)
        if friday in listed:
            found.add(friday)
        elif saturday in listed:
            found.add(saturday)
        elif last is not None and first < friday <= last and friday not in sessions:
            before = friday - timedelta(days=1)
            while before > first and before not in sessions:
                before -= timedelta(days=1)
            if before in sessions and before in listed:
                found.add(before)
    return sorted(found)


def nearest_monthly(expiries, as_of: date, sessions, target_dte: int = 30, min_dte: int = 0,
                    max_dte: int = MAX_EXPIRY_DAYS) -> date | None:
    """The standard monthly expiry whose DTE is nearest target_dte, with min_dte <= DTE <= max_dte.

    `sessions` is the exchange calendar (standard_monthly). max_dte is capped at MAX_EXPIRY_DAYS. A tie goes to the
    earlier expiry. None when nothing qualifies. ADR-0002 test 9: on 2022-04-01 a 14-DTE target selects 2022-04-14,
    never a weekly.
    """
    ceiling = min(max_dte, MAX_EXPIRY_DAYS)
    candidates = [day for day in standard_monthly(expiries, sessions) if min_dte <= (day - as_of).days <= ceiling]
    if not candidates:
        return None
    return min(candidates, key=lambda day: (abs((day - as_of).days - target_dte), day))
