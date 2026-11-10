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

DAYS TO EXPIRY IN MILESTONE 4 (part B). Every DTE of the M4 rules (the entry windows, exit_dte, the calendar's front)
counts calendar days from a session to the contract's SETTLEMENT date, not to its listed expiry: settle_date applies
decision D16's map, so the Saturday-dated December 2015 monthly (2015-12-19) counts to its Friday close, 2015-12-18.
Strategies may not import the engine (ADR-0001 §4), so SETTLE_MAP is a copy of volbt.engine.settlement's
NON_SESSION_EXPIRIES, and tests/test_strategy_picks.py keeps the two equal. The M3 reference strategy still counts to
the listed expiry (its regression gate). Default taken 2026-11-09, owner can override.
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


# Decision D16's map (volbt.engine.settlement.NON_SESSION_EXPIRIES): the session whose close settles a listed expiry
# that is not a session. A copy, because strategies may not import the engine; a test keeps it equal to the engine's.
SETTLE_MAP = {date(2015, 12, 19): date(2015, 12, 18), date(2018, 12, 5): date(2018, 12, 4)}


def settle_date(expiry: date, sessions, last_session: date | None = None) -> date | None:
    """The session whose close settles a contract listed with `expiry` (volbt.engine.settlement.settle_date's rule).

    The expiry itself when it is a session or falls after the calendar's last date (`last_session`, default the latest
    of `sessions`); else SETTLE_MAP's date; else None: an unmapped non-session expiry, which the engine refuses to
    open (UnmappedExpiry), so no M4 rule picks it.
    """
    last_session = last_session if last_session is not None else (max(sessions) if sessions else None)
    if expiry in sessions or (last_session is not None and expiry > last_session):
        return expiry
    return SETTLE_MAP.get(expiry)


def dte(expiry: date, as_of: date, sessions, last_session: date | None = None) -> int | None:
    """Calendar days from `as_of` to the settlement date of `expiry` (None for an unmapped non-session expiry)."""
    settle = settle_date(expiry, sessions, last_session)
    return None if settle is None else (settle - as_of).days


def monthly_in_window(expiries, as_of: date, lo: int, hi: int, sessions,
                      last_session: date | None = None) -> list[date]:
    """The standard monthlies among the listed `expiries` with lo <= DTE <= hi at `as_of`, ascending.

    DTE counts to the settlement date (module docstring); the listed expiry is also at most MAX_EXPIRY_DAYS after
    as_of, the cap the engine's check_intent applies to every opening leg. `sessions` is the exchange calendar
    (standard_monthly); `last_session` its last date (default: computed from `sessions`).
    """
    days = sessions if isinstance(sessions, (set, frozenset)) else frozenset(sessions)
    last = last_session if last_session is not None else (max(days) if days else None)
    found = []
    for expiry in standard_monthly(expiries, days):
        to_settle = dte(expiry, as_of, days, last)
        if to_settle is not None and lo <= to_settle <= hi and (expiry - as_of).days <= MAX_EXPIRY_DAYS:
            found.append(expiry)
    return found


def next_monthly(expiries, front: date, sessions) -> date | None:
    """The standard monthly of the calendar month after `front`'s, if it is among the listed `expiries`; else None.

    The straddle calendar's back leg is the next monthly or nothing: an unlisted next monthly is never replaced by a
    later one (default taken 2026-11-09, owner can override).
    """
    year, month = (front.year + 1, 1) if front.month == 12 else (front.year, front.month + 1)
    for expiry in standard_monthly(expiries, sessions):
        if (expiry.year, expiry.month) == (year, month):
            return expiry
    return None
