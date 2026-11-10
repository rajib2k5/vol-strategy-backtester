"""Settlement on expiration day (ADR-0003 §2-4), as bookings on the book.

    S_set   the SPY official close at t, UNADJUSTED (spy_bars.close; never the option's own quote, never the
            dividend-adjusted close)
    rule    exercise-by-exception: a call is exercised iff S_set - K >= $0.01, a put iff K - S_set >= $0.01,
            in integer cents; otherwise it expires worthless. No contrary instructions.
    shares  long call +100, short call -100, long put -100, short put +100 per contract, at K; cash -/+ 100 K
    pin     a SHORT contract with |S_set - K| <= $0.50 is still settled by the rule, and flagged

Expiries that are not sessions (decision D16). A contract settles on its expiry date when that is a session.
A few listed expiry dates are not: each is mapped to the session whose close settles it, ONLY where a primary
source says so; any other non-session expiry stops the run (UnmappedExpiry), because guessing its settlement
would invent a price.

    2015-12-19 (Saturday)   -> 2015-12-18: the December-2015 SPY standard series were "grandfathered" with a
                               Saturday expiration date, but exercise processing had moved to the Friday for all
                               standard contracts (SEC Rel. 34-69772, approving SR-OCC-2013-04, 78 FR 37645,
                               2013-06-21; Cboe RG13-118 / C2 RG13-041, 2013-08-29, lists "December 2015 SPY";
                               SEC Rel. 34-70900: the exercise cut-off is the business day before a Saturday
                               expiration)
    2018-12-05 (Wednesday)  -> 2018-12-04: the national day of mourning for President George H.W. Bush. OCC
                               Information Memo #44125 (2018-12-02, "Processing December 5, 2018 - President
                               George H.W. Bush"): "Wednesday, December 5, 2018 is an expiration date", and its
                               table lists "SPY Options | Tuesday closing prices | December 7, 2018" (the prices
                               used, then the settlement date). FINRA's Information Notice of 2018-12-04: options
                               expiring 2018-12-05 have a 10:00 a.m. ET exercise cut-off on 12-05. (The first M3
                               review removed this entry while the memo was unread; the round-2 review read it.)
    unmapped                2018-12-23 (Sunday) and 2018-12-25 (Christmas): OptionsDX lists them (86 and 66 rows,
                            5 and 3 strikes, 2018-11-30 to 12-17); no primary source shows SPY series with those
                            dates. Neither is a third Friday, so the standard-monthly picker never selects one; a
                            run that opened one would stop.
    after the calendar      an expiry after the last SPY bar in the store is not known to be a non-session: it
                            settles on its own date, which no run reaches (M3 review: holdout runs into late 2026
                            stopped with UnmappedExpiry on every expiry past 2026-10-28).

Sources: https://www.govinfo.gov/content/pkg/FR-2013-06-21/pdf/2013-14793.pdf ,
https://cdn.cboe.com/resources/regulation/circulars/regulatory/RG-C2-2013-041.pdf ,
https://www.sec.gov/files/rules/sro/ise/2013/34-70900.pdf ,
https://cdn.cboe.com/resources/schedule_update/2018/Cboe-to-Observe-National-Day-of-Mourning-on-Wednesday-December-5-2018.pdf
(Cboe Exchange Notice C2018120300: ETP Wednesday weeklies settle "Tuesday EOD"; it does not name SPY),
https://web.archive.org/web/20190822143120id_/https://www.theocc.com/webapps/infomemos?number=44125&date=201812&lastModifiedDate=12%2F02%2F2018+00%3A00%3A00
(OCC #44125 through the Wayback Machine: theocc.com answers 403 to direct fetches; read 2026-11-09). The first
four were retrieved 2026-10-30 by the milestone-3 research step.
"""

from __future__ import annotations

from datetime import date

NON_SESSION_EXPIRIES = {
    date(2015, 12, 19): date(2015, 12, 18),
    date(2018, 12, 5): date(2018, 12, 4),
}
SHARES_PER_CONTRACT = 100


class UnmappedExpiry(ValueError):
    """A contract expires on a date that is not a session and that no primary source maps (D16)."""


def settle_date(expiry: date, sessions: set, last_session: date | None = None) -> date:
    """The session whose close settles a contract expiring `expiry` (module docstring). `last_session` is the last
    date of the calendar (default: the latest of `sessions`): past it, a date is not known to be a non-session."""
    last_session = last_session if last_session is not None else (max(sessions) if sessions else None)
    if expiry in sessions or (last_session is not None and expiry > last_session):
        return expiry
    if expiry in NON_SESSION_EXPIRIES:
        return NON_SESSION_EXPIRIES[expiry]
    raise UnmappedExpiry(f"the contract expiry {expiry} is not a SPY session and is not in the settlement map "
                         "(volbt.engine.settlement, decision D16): the run stops rather than guess its settlement")


def is_exercised(right: str, settle_cents: int, strike_cents: int) -> bool:
    """Exercise-by-exception at $0.01 (ADR-0003 test 1: at 450.00 the 450 call and put both expire)."""
    return settle_cents - strike_cents >= 1 if right == "C" else strike_cents - settle_cents >= 1


def delivered_shares(right: str, qty: int) -> int:
    """Signed shares per ADR-0003's delivery table for `qty` contracts (+ long, - short)."""
    return SHARES_PER_CONTRACT * qty if right == "C" else -SHARES_PER_CONTRACT * qty


def settle_lot(lot, settle_cents: int, strike_cents: int, pin_band_cents: int) -> dict:
    """The expiry event of one lot settling at S_set: event type, shares, cash, pin flag."""
    exercised = is_exercised(lot.right, settle_cents, strike_cents)
    shares = delivered_shares(lot.right, lot.qty) if exercised else 0
    event = "expired_worthless" if not exercised else ("exercised" if lot.qty > 0 else "assigned")
    return {"event_type": event, "contracts": lot.qty, "shares_delivered": shares,
            "cash_cents": -shares * strike_cents,
            "pin_flag": bool(lot.qty < 0 and abs(settle_cents - strike_cents) <= pin_band_cents)}
