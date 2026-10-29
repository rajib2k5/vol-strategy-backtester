"""The 13-bit quality_flags mask (ADR-0009 §3): one integer per quote, one bit per problem.

Why a bitmask. A quote can have several problems at once (a zero bid AND an invalid vendor IV).
One bit per problem keeps them all in one small integer column, and each consumer picks the
bits it cares about with `&`: marks (ADR-0004), fills (ADR-0002) and the smile (ADR-0008) each
apply their own rule. We flag rows; we do not delete them (ADR-0009 §2).

    flags = ZERO_BID | VENDOR_IV_INVALID   # 4 | 2048 = 2052
    flags & ZERO_BID != 0                  # True: this quote has a zero bid

All price tests run on whole cents. Every vendor price is a whole number of cents (measured on
all 9,468,584 OptionsDX rows, and DoltHub stores decimal(7,2)), so cents lose nothing and make
the boundaries exact: in binary floats, 400.40/400 - 1 is not exactly 0.001.

Two bits of the 13 are never set on a stored quote. NON_SESSION_DATE (7) marks a vendor date in
the calendar's own table, calendar_actions; since every such date is dropped, no stored quote
carries it. RELABELLED (8) is RESERVED AND UNUSED: the calendar's relabel rule was removed in
round 2 of the M1 review (calendar.py says why), and the bit keeps its number so that no other
bit moves.

The three IV flags of ADR-0009 (IV_FAIL, PARITY_OUTLIER, FORWARD_FALLBACK) are not part of this
mask. They belong to quote_iv.iv_flags, which the M2 pricing build writes. Their bits are
reserved below and nothing in M1 sets them.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

# Bit 0 is the lowest bit. The name list is in bit order: FLAG_NAMES[b] has value 1 << b.
BID_NULL = 1 << 0             # bid is null
ASK_NULL = 1 << 1             # ask is null
ZERO_BID = 1 << 2             # bid = 0
CROSSED = 1 << 3              # bid > ask
LOCKED = 1 << 4               # bid = ask > 0
WIDE = 1 << 5                 # ask - bid > mid, i.e. relative spread > 100% (only when bid > 0)
STALE = 1 << 6                # bid and ask unchanged from the contract's previous snapshot while |dS/S| >= 0.5%
NON_SESSION_DATE = 1 << 7     # the vendor dated the row on a day that is not a SPY session (and it is dropped)
RELABELLED = 1 << 8           # RESERVED, never set: the relabel rule it marked was removed in M1 (round 2)
VOLUME_UNRELIABLE = 1 << 9    # volume null, or OptionsDX before 2021-01-04, or DoltHub
UNDERLYING_MISMATCH = 1 << 10  # |UNDERLYING_LAST / SPY close - 1| > 0.10%
VENDOR_IV_INVALID = 1 << 11   # the vendor's IV is null or <= 0 (renamed from VENDOR_IV_NULL in M1)
EXPIRY_DAY = 1 << 12          # tau = 0: the quote is on the expiry date

FLAG_NAMES = (
    "BID_NULL", "ASK_NULL", "ZERO_BID", "CROSSED", "LOCKED", "WIDE", "STALE", "NON_SESSION_DATE",
    "RELABELLED", "VOLUME_UNRELIABLE", "UNDERLYING_MISMATCH", "VENDOR_IV_INVALID", "EXPIRY_DAY",
)
FLAG_BITS = {name: bit for bit, name in enumerate(FLAG_NAMES)}

# Reserved for M2: quote_iv.iv_flags, a separate column in a separate table. Never set in M1.
IV_FAIL = 1 << 0
PARITY_OUTLIER = 1 << 1
FORWARD_FALLBACK = 1 << 2
IV_FLAG_NAMES = ("IV_FAIL", "PARITY_OUTLIER", "FORWARD_FALLBACK")

# The thresholds, written as exact fractions so the cent arithmetic below stays in integers.
STALE_MOVE_DENOMINATOR = 200        # |dS/S| >= 1/200 = 0.5%
MISMATCH_DENOMINATOR = 1000         # |u/S - 1| > 1/1000 = 0.10%
VOLUME_RELIABLE_FROM = date(2021, 1, 4)


def flag_names(mask: int) -> list[str]:
    """The names of the bits set in `mask`, lowest bit first."""
    return [name for bit, name in enumerate(FLAG_NAMES) if mask & (1 << bit)]


def cents(prices) -> np.ndarray:
    """Dollars to whole cents, as float64 so a null stays NaN (every comparison with NaN is False)."""
    return np.rint(np.asarray(pd.array(prices, dtype="Float64").to_numpy(dtype=float, na_value=np.nan)) * 100)


def set_where(condition, bit: int) -> np.ndarray:
    return np.where(condition, bit, 0).astype(np.int32)


def mid_flags(bid: np.ndarray, ask: np.ndarray) -> np.ndarray:
    """Bits 0-5, which need only the quote itself: bid and ask in cents (NaN for null)."""
    out = set_where(np.isnan(bid), BID_NULL)
    out |= set_where(np.isnan(ask), ASK_NULL)
    out |= set_where(bid == 0, ZERO_BID)
    out |= set_where(bid > ask, CROSSED)
    out |= set_where((bid == ask) & (bid > 0), LOCKED)
    # WIDE: ask - bid > mid = (ask + bid)/2, i.e. 2(ask - bid) > ask + bid. Only for a bid above
    # zero: a zero bid has its own flag, and 0.00/0.05 would otherwise be "200% wide" as well.
    out |= set_where((bid > 0) & (2 * (ask - bid) > ask + bid), WIDE)
    return out


def quote_flags(frame: pd.DataFrame) -> np.ndarray:
    """The 13-bit mask for every row of a session-dated quote table.

    Needs the columns: bid, ask, prev_bid, prev_ask (the same contract's previous snapshot,
    null if none), spy_close, prev_spy_close, underlying_last, volume, vendor_iv, source,
    quote_date, expiry, and date_flags (the calendar's bits for the row's date; 0 on every
    session, and the calendar keeps no other date).
    """
    bid, ask = cents(frame["bid"]), cents(frame["ask"])
    out = np.asarray(frame["date_flags"], dtype=np.int32) | mid_flags(bid, ask)

    # STALE: the quote did not move although SPY moved at least 0.5% since the contract's last
    # snapshot. |S - S_prev| / S_prev >= 1/200  <=>  200 |S - S_prev| >= S_prev, in cents.
    spot, prev_spot = cents(frame["spy_close"]), cents(frame["prev_spy_close"])
    unchanged = (bid == cents(frame["prev_bid"])) & (ask == cents(frame["prev_ask"]))
    moved = STALE_MOVE_DENOMINATOR * np.abs(spot - prev_spot) >= prev_spot
    out |= set_where(unchanged & moved, STALE)

    # VOLUME_UNRELIABLE: null volume means "unknown", not zero (ADR-0002 §5).
    source = np.asarray(frame["source"])
    quote_day = pd.to_datetime(frame["quote_date"]).to_numpy()
    early = (source == "optionsdx") & (quote_day < np.datetime64(VOLUME_RELIABLE_FROM))
    volume_null = pd.isna(frame["volume"]).to_numpy()
    out |= set_where(volume_null | early | (source == "dolthub"), VOLUME_UNRELIABLE)

    # UNDERLYING_MISMATCH: |u - S| / S > 1/1000  <=>  1000 |u - S| > S. A null u (DoltHub) never trips it.
    underlying = cents(frame["underlying_last"])
    out |= set_where(MISMATCH_DENOMINATOR * np.abs(underlying - spot) > spot, UNDERLYING_MISMATCH)

    # VENDOR_IV_INVALID: null, or not above zero. OptionsDX has IVs from -0.0005 to -0.00001 and
    # exact zeros; DoltHub has zero vols on bid = ask = 0 quotes. A very high IV (above 5) is a
    # real, if extreme, number and is not flagged here; tools/report_m1.py counts it.
    iv = np.asarray(pd.array(frame["vendor_iv"], dtype="Float64").to_numpy(dtype=float, na_value=np.nan))
    out |= set_where(np.isnan(iv) | (iv <= 0), VENDOR_IV_INVALID)
    out |= set_where(pd.to_datetime(frame["expiry"]).to_numpy() == quote_day, EXPIRY_DAY)
    return out
