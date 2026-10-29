"""The OSI option symbol: one fixed-width string that names one listed option contract.

OSI (the Options Symbology Initiative, 2010) is the 21-character format brokers and the OCC use:

    SPY   240315C00450000
    ^^^^^^                 root, left-justified and padded with spaces to 6 characters
          ^^^^^^           expiry as yymmdd (2024-03-15)
                ^          C for a call, P for a put
                 ^^^^^^^^  strike x 1000, zero-padded to 8 digits (450.000 -> 00450000)

Why we key quotes on it (ADR-0009 §2): it is unique per contract, it sorts by root, expiry,
side and strike, and it means the same thing in OptionsDX and DoltHub, which name their
columns differently.

The strike is held in thousandths of a dollar as an integer ("milli-dollars"), never as a
float: in binary floating point 1.005 * 1000 is 1004.9999999999999, so int() would give 1004.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

ROOT_WIDTH = 6
STRIKE_SCALE = 1000
STRIKE_DIGITS = 8
MAX_STRIKE_MILLI = 10**STRIKE_DIGITS - 1
OSI_PATTERN = re.compile(r"^(?P<root>[A-Z0-9 ]{6})(?P<yymmdd>\d{6})(?P<side>[CP])(?P<strike>\d{8})$")


def strike_to_milli(strike) -> int:
    """450.5 -> 450500. Raises ValueError if the strike is negative, too big, or not a whole number of thousandths."""
    # Decimal(str(x)) reads the shortest decimal that round-trips the float: 450.5 -> "450.5".
    milli = Decimal(str(strike)) * STRIKE_SCALE
    if milli != milli.to_integral_value():
        raise ValueError(f"strike {strike} is not a whole number of thousandths of a dollar")
    if not 0 <= milli <= MAX_STRIKE_MILLI:
        raise ValueError(f"strike {strike} does not fit in {STRIKE_DIGITS} digits of thousandths")
    return int(milli)


def osi_symbol(root: str, expiry: date, call_put: str, strike) -> str:
    """("SPY", 2024-03-15, "C", 450.00) -> "SPY   240315C00450000"."""
    if not root or len(root) > ROOT_WIDTH or not re.fullmatch(r"[A-Z0-9]+", root):
        raise ValueError(f"root {root!r} must be 1 to {ROOT_WIDTH} upper-case letters or digits")
    if call_put not in ("C", "P"):
        raise ValueError(f"call_put must be 'C' or 'P', not {call_put!r}")
    if not 2000 <= expiry.year <= 2099:
        raise ValueError(f"expiry {expiry} is outside the two-digit years 2000-2099")
    return f"{root:<{ROOT_WIDTH}}{expiry:%y%m%d}{call_put}{strike_to_milli(strike):0{STRIKE_DIGITS}d}"


def parse_osi(symbol: str) -> tuple[str, date, str, Decimal]:
    """The inverse: "SPY   240315C00450000" -> ("SPY", date(2024, 3, 15), "C", Decimal("450.000"))."""
    match = OSI_PATTERN.match(symbol)
    if match is None:
        raise ValueError(f"{symbol!r} is not a 21-character OSI symbol")
    yymmdd = match["yymmdd"]
    # date() raises ValueError for a month 13 or a 30 February.
    expiry = date(2000 + int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:]))
    # scaleb(-3) divides by 1000 exactly and keeps the three decimals.
    return match["root"].rstrip(), expiry, match["side"], Decimal(match["strike"]).scaleb(-3)


def osi_symbols(expiry: pd.Series, call_put: pd.Series, strike: pd.Series, root: str = "SPY") -> pd.Series:
    """The same strings as osi_symbol, for whole columns at once (millions of rows)."""
    milli_float = np.asarray(strike, dtype=float) * STRIKE_SCALE
    milli = np.rint(milli_float).astype(np.int64)
    # A strike off the 1/1000 grid would round silently here; refuse it like the scalar version.
    if np.any(np.abs(milli_float - milli) > 1e-6) or np.any((milli < 0) | (milli > MAX_STRIKE_MILLI)):
        raise ValueError("a strike is negative, too big, or not a whole number of thousandths")
    if not set(pd.unique(call_put)) <= {"C", "P"}:
        raise ValueError("call_put must be 'C' or 'P'")
    days = pd.to_datetime(pd.Series(expiry).reset_index(drop=True))
    yymmdd = (days.dt.year % 100) * 10000 + days.dt.month * 100 + days.dt.day
    prefix = f"{root:<{ROOT_WIDTH}}"
    return (prefix + yymmdd.astype(str).str.zfill(6) + pd.Series(call_put).reset_index(drop=True).astype(str)
            + pd.Series(milli).astype(str).str.zfill(STRIKE_DIGITS))
