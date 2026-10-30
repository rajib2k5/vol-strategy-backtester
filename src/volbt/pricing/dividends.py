"""The dividend schedule the pricing uses: projected ex-dates, each at a PROJECTED amount.

Pricing never needs a dividend yield q: the parity forward carries the dividend (ADR-0008 §4). The
schedule is needed in three places only: the lattice that measures the early-exercise premium,
the early-exercise decision (ADR-0003) and the forward fallback when an expiry has too few
call/put pairs. In all three, using a dividend that was not yet known would be look-ahead, so:

- the AMOUNT is projected from the dividends paid on or before the quote date only. SPY's
  dividends are seasonal (March is the smallest of the year, December the largest), so "the last
  one paid" overstates every March: by 10.9% to 47.3% since 2009. The rule is the one with the
  lowest mean absolute error in a no-look-ahead backtest over SPY's 71 ex-dates since 2009 (the
  M2 review amendment, default taken 2026-10-29; the four rules and their errors are in the
  milestone-2 walkthrough): THE SAME QUARTER A YEAR EARLIER, TIMES THE TRAILING YEAR'S GROWTH,

      D(next q) = D(q, a year earlier) x [sum of the last 4 paid] / [sum of the 4 before them]

  and for a quarter more than a year ahead, the latest paid amount of that quarter times the
  growth once per year ahead. With fewer than 8 dividends paid there is no growth to measure,
  and the amount is the last one paid. Its limits (M2 round 2, design claim 5; kept, since
  choosing again after seeing the results would be snooping): it ranks first of the four in both
  halves of the sample, but its edge over the trailing four-quarter mean is within noise (paired
  difference -1.19 points, bootstrap 95% CI [-2.88, +0.51]); and 6 to 8 quarters ahead it is worse
  than last paid (14.19, 15.58 and 16.95% against 13.92, 14.91 and 15.17%), which matters only
  beyond 180 days, where ADR-0008's proposed carry-consistent rate would absorb it;
- the DATES are projected from SPY's rule: the third Friday of March, June, September and
  December, or the session before it when that Friday is a holiday (ADR-0003, Context). A test
  marked real_data checks the rule against every ex-date SPY has paid since 2009. Past the last
  SPY session known, the holidays are NYSE's own rules for the only two that can fall on a third
  Friday: Good Friday, and Juneteenth (June 19, observed on Friday 18 when it is a Saturday;
  an NYSE holiday from 2022). So 2027-06-18 projects to Thursday 2027-06-17.

A dividend counts for an option when its ex-date is after the quote date and on or before the
expiry: on the quote date itself the close is already ex-dividend.

WHEN the stock drops, in the lattice's clock. SPY opens ex-dividend on the ex-date, so the last
moment to exercise a call for the dividend is the close of the session before it, and the stock
never trades cum-dividend after that close. The drop is therefore timed just after the close of the
day before the ex-date: ((ex_date - quote_date).days - 1) / 365 + DROP_AFTER_CLOSE. Timed at the
ex-date itself, a lattice would let a cum-dividend stock diffuse for a whole extra day, with an
exercise decision at every step of it: on 2023-03-16, the day before an ex-date that was also the
expiry, that priced a premium of $0.33 into an out-of-the-money call whose mid was $0.335.
"""

from __future__ import annotations

import bisect
from datetime import date, timedelta

QUARTER_MONTHS = (3, 6, 9, 12)
FRIDAY = 4                      # date.weekday(): Monday = 0
DAYS_PER_YEAR = 365
# A holiday Friday's ex-date is the session before it, looked for within this many days.
HOLIDAY_WINDOW_DAYS = 7
# Years after the previous close at which the drop happens: after today's close even when the
# ex-date is tomorrow, and before the lattice's first step.
DROP_AFTER_CLOSE = 1e-9
GROWTH_QUARTERS = 4             # the trailing year, against the year before it
JUNETEENTH_FIRST_YEAR = 2022    # the first year NYSE closed for Juneteenth


def third_friday(year: int, month: int) -> date:
    """The third Friday of a month: the first Friday is day 1-7, so the third is day 15-21."""
    first = date(year, month, 1)
    return first + timedelta(days=(FRIDAY - first.weekday()) % 7 + 14)


def good_friday(year: int) -> date:
    """Easter Sunday less two days (the anonymous Gregorian computus, Meeus's form)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month, day = divmod(h + m - 7 * n + 114, 31)
    return date(year, month, day + 1) - timedelta(days=2)


def nyse_closed_friday(day: date) -> bool:
    """True for the two NYSE holidays that can fall on a third Friday: Good Friday and Juneteenth."""
    if day == good_friday(day.year):
        return True
    if day.year >= JUNETEENTH_FIRST_YEAR:
        observed = date(day.year, 6, 19)
        observed -= timedelta(days=1) if observed.weekday() == 5 else timedelta(days=0)
        return day == observed
    return False


def projected_ex_dates(as_of: date, until: date, sessions: list[date]) -> list[date]:
    """SPY's rule-based ex-dates in (as_of, until], ascending.

    `sessions` is the sorted list of SPY sessions (exchange holidays are published in advance, so
    knowing which future weekdays trade is not look-ahead). A third Friday that is not a session
    moves to the last session in the week before it. Past the last session listed, a Friday on
    which NYSE is closed (nyse_closed_friday) moves to the Thursday before it.
    """
    found = []
    last_session = sessions[-1] if sessions else None
    for year in range(as_of.year, until.year + 1):
        for month in QUARTER_MONTHS:
            day = third_friday(year, month)
            if last_session is None or day > last_session:
                if nyse_closed_friday(day):
                    day -= timedelta(days=1)
            else:
                # The last session on or before the Friday (the Friday itself when it trades).
                index = bisect.bisect_right(sessions, day) - 1
                if index >= 0 and (day - sessions[index]).days < HOLIDAY_WINDOW_DAYS:
                    day = sessions[index]
            if as_of < day <= until:
                found.append(day)
    return found


def last_paid(ex_dates: list[date], amounts: list[float], as_of: date) -> float | None:
    """The amount of the latest dividend with ex-date on or before as_of, or None if there is none."""
    paid = [(day, amount) for day, amount in zip(ex_dates, amounts) if day <= as_of]
    return max(paid)[1] if paid else None


def projected_amount(ex_dates: list[date], amounts: list[float], as_of: date, ex_date: date) -> float | None:
    """The amount projected on as_of for a future ex-date: the same quarter a year earlier, times growth.

    Only dividends with ex-date on or before as_of are read (no look-ahead). None when none is paid.
    """
    paid = sorted((day, amount) for day, amount in zip(ex_dates, amounts) if day <= as_of)
    if not paid:
        return None
    values = [amount for _, amount in paid]
    if len(values) < 2 * GROWTH_QUARTERS:
        return values[-1]
    last_day = paid[-1][0]
    months = (ex_date.year - last_day.year) * 12 + ex_date.month - last_day.month
    ahead = max(1, round(months / 3))                 # quarters after the last paid dividend
    previous = sum(values[-2 * GROWTH_QUARTERS:-GROWTH_QUARTERS])
    growth = sum(values[-GROWTH_QUARTERS:]) / previous if previous > 0 else 1.0
    base = values[-GROWTH_QUARTERS + (ahead - 1) % GROWTH_QUARTERS]
    return base * growth ** (1 + (ahead - 1) // GROWTH_QUARTERS)


def drop_time(as_of: date, ex_date: date) -> float:
    """Years from the as_of close to the dividend drop: just after the close of the day before the ex-date."""
    return ((ex_date - as_of).days - 1) / DAYS_PER_YEAR + DROP_AFTER_CLOSE


def schedule(ex_dates: list[date], amounts: list[float], as_of: date, until: date,
             sessions: list[date]) -> tuple[list[float], list[float]]:
    """(drop times in years from as_of, amounts) of the dividends to project for an option expiring `until`."""
    if last_paid(ex_dates, amounts, as_of) is None:
        return [], []
    days = projected_ex_dates(as_of, until, sessions)
    return ([drop_time(as_of, day) for day in days],
            [projected_amount(ex_dates, amounts, as_of, day) for day in days])
