"""Cash in integer cents (decision D7): every flow rounded once, ROUND_HALF_UP, with Decimal.

Why integers. Float cash cannot reconcile exactly: a sum of a few thousand float flows differs from the
balance in its last bits, and "cash = initial + sum of flows" would hold only to a tolerance. In cents
every flow is an exact integer, so the identity holds exactly on every session (tests/test_engine_cash.py),
and a flow is rounded once, where it is created, never again.

Rounding is Decimal ROUND_HALF_UP, never Python's round() (banker's rounding on a binary float:
round(1235 * 0.005, 2) gives 6.17, ADR-0002 §4).

    interest_cents      ADR-0007 §2: balance (e^(r d / 365) - 1) on the PRIOR-CLOSE balance (decision D8),
                        at the previous session's rate, for the calendar days d since it (Friday to Monday
                        is 3); a negative balance pays r + 0.50%
    dividend_cents      ADR-0005 §6: shares x D on the ex-date (short shares pay it)
    borrow_fee_cents    ADR-0005 §1 (decision D9): 0.25%/yr on the short shares' prior-close market value
"""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
DAYS_PER_YEAR = 365


def cents(amount: Decimal) -> int:
    """USD as a Decimal -> whole cents, ROUND_HALF_UP (6.175 -> 618, -6.175 -> -618)."""
    return int((Decimal(amount) / CENT).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def growth(rate: float, days: int) -> Decimal:
    """e^(rate days / 365) - 1, exactly the float expm1 gives, as a Decimal (no second rounding)."""
    return Decimal(math.expm1(rate * days / DAYS_PER_YEAR))


def interest_cents(balance_cents: int, rate: float, days: int, negative_spread: Decimal) -> int:
    """ADR-0007 test 1: $1,000,000 at r_cc 5.2159% over 3 days earns $428.80; -$100,000 pays $46.99."""
    if days <= 0 or balance_cents == 0:
        return 0
    rate_used = rate + (float(negative_spread) if balance_cents < 0 else 0.0)
    return cents(Decimal(balance_cents) / 100 * growth(rate_used, days))


def dividend_cents(shares: int, amount: float) -> int:
    """Signed: + for long shares, - for short. `amount` as stored (3 decimals), read exactly via its repr."""
    return cents(Decimal(shares) * Decimal(repr(amount)))


def borrow_fee_cents(shares: int, price_cents: int, days: int, fee: Decimal) -> int:
    """The fee (a NEGATIVE flow) on short shares; 0 when the prior close was flat or long."""
    if shares >= 0 or days <= 0:
        return 0
    value = Decimal(-shares) * Decimal(price_cents) / 100
    return -cents(value * growth(float(fee), days))
