"""The fill model (ADR-0002): integer-cent prices, quote states, the liquidity cap, packages, costs.

Every price here is an INTEGER number of cents. With b and a the bid and ask in cents and k = n/4:

    buy  = ceil ((b + a + k (a - b)) / 2) = -(-(4 (b + a) + n (a - b)) // 8)
    sell = floor((b + a - k (a - b)) / 2) =    (4 (b + a) - n (a - b)) // 8

which is mid +- k half-spreads rounded outward to the tick, done with no float at all: in float dollars
(2.00 + 2.10)/2 - (2.10 - 2.00)/2 is 1.9999999999999998, and a floor of it gives 1.99 (ADR-0002 test 8).

Quote states on the fill day (ADR-0002 §7, ADR-0009 flags):

    valid      0 < bid <= ask, not STALE (a locked quote, bid = ask, is valid with h = 0)
    zero_bid   bid = 0 < ask
    no_quote   crossed, one-sided (a side null, ask <= 0), STALE, or the contract not in the snapshot

    opening order     valid: fill if bid >= 5 cents and 8 (a - b) <= a + b (relative spread <= 25%),
                      else ILLIQUID; zero_bid: ZERO_BID; no_quote: NO_QUOTE
    reduce-only       valid: fill; zero_bid: a buy fills at the ask whatever k is, a sell does not fill
                      (ZERO_BID: the long is held); no_quote: a SURFACE fill at model_mid +- m h_model,
                      rounded outward
    surface mode      every fill is a surface fill (the DoltHub contract chosen at t is usually not listed
                      at t + 1, ADR-0009)

The cap (§5) uses only the volume known when the order was created, V_t, stamped on the order leg:
min(100, floor(0.10 V_t)) when cap_mode = volume, the source is OptionsDX, t >= 2021-01-04 and V_t is not
null; otherwise the hard cap of 100. A null volume is "unknown", never 0. Reduce-only orders get the hard
cap only, so a proxy can never trap a position.

Packages (§6): an opening package fills min over legs of floor(cap / |ratio|) whole packages, never legs; the
remainder is cancelled (CAP), never carried. A REDUCE-ONLY package fills leg by leg (decision D6, an
ADR-0002 amendment: §5's "a proxy can never trap a position" beats §6's "packages fill whole" for an order
that only reduces risk: a long straddle whose put has a zero bid would otherwise keep its ITM call).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from fractions import Fraction

import numpy as np

from volbt.data import flags as quality
from volbt.engine.cash import cents

VALID, ZERO_BID, NO_QUOTE = "valid", "zero_bid", "no_quote"
NOT_VALID = quality.BID_NULL | quality.ASK_NULL | quality.CROSSED | quality.STALE | quality.ZERO_BID


def price_cents(bid_c: int, ask_c: int, k: Fraction, side: int) -> int:
    """ADR-0002 §2 in integer cents: side +1 buys, -1 sells. k must be a multiple of 1/4."""
    n = k * 4
    if n.denominator != 1:
        raise ValueError(f"k = {k} is not a multiple of 1/4")
    n = int(n)
    if side > 0:
        return -(-(4 * (bid_c + ask_c) + n * (ask_c - bid_c)) // 8)
    return (4 * (bid_c + ask_c) - n * (ask_c - bid_c)) // 8


def to_cents(price) -> int | None:
    """A vendor price in dollars (every one is a whole number of cents) as int cents; None for null/NaN."""
    if price is None or not np.isfinite(price):
        return None
    return int(round(float(price) * 100))


def quote_state(bid_c: int | None, ask_c: int | None, quality_flags: int | None) -> str:
    """valid, zero_bid or no_quote (module docstring). A missing contract has no cents and no flags."""
    if bid_c is None or ask_c is None or quality_flags is None:
        return NO_QUOTE
    if ask_c <= 0 or bid_c > ask_c or (quality_flags & (quality.CROSSED | quality.STALE)):
        return NO_QUOTE
    if bid_c == 0:
        return ZERO_BID
    return VALID


def opening_liquid(bid_c: int, ask_c: int, cfg) -> bool:
    """ADR-0002 §7: bid >= open_min_bid and (a - b) / mid <= 25%, in integers: (a - b) <= rel (a + b) / 2."""
    rel = cfg.open_max_rel_spread
    return bid_c >= cfg.open_min_bid_cents and 2 * (ask_c - bid_c) * rel.denominator <= rel.numerator * (ask_c + bid_c)


def volume_reliable(cfg, created, volume) -> bool:
    return (cfg.data_source == "optionsdx" and created >= cfg.volume_reliable_from and volume is not None
            and np.isfinite(volume))


def leg_cap(cfg, reduce_only: bool, cap_volume, created) -> tuple[int, str, bool]:
    """(contracts the leg may fill, cap_type, volume_reliable) for one order leg (§5)."""
    reliable = volume_reliable(cfg, created, cap_volume)
    if reduce_only or cfg.cap_mode != "volume" or not reliable:
        return cfg.max_contracts_per_line, "hard", reliable
    p = cfg.participation_rate
    return min(cfg.max_contracts_per_line, (int(cap_volume) * p.numerator) // p.denominator), "volume", reliable


def package_count(requested: int, caps, ratios) -> int:
    """Whole packages an opening order fills: min(requested, min over legs floor(cap / |ratio|)).

    ADR-0002 test 5: a straddle with caps 85 and 60 fills 60 packages.
    """
    return min([requested] + [cap // abs(ratio) for cap, ratio in zip(caps, ratios)])


def option_fee_cents(contracts: int, cfg) -> int:
    """ADR-0002 §3: 70 cents per contract per side; 120 contracts pay $84.00."""
    return abs(contracts) * cfg.fee_per_contract_cents


def stock_cost_cents(shares: int, cfg) -> tuple[int, int]:
    """(commission, slippage) in cents for one SPY share order (ADR-0002 §4).

    Commission $0.005 a share with a $1.00 minimum per order, slippage $0.005 a share, each exact in
    Decimal and rounded ROUND_HALF_UP: 1,235 shares cost 618 + 618 cents (round() on floats gives 6.17).
    No order, no cost.
    """
    if shares == 0:
        return 0, 0
    size = Decimal(abs(shares))
    commission = max(size * cfg.stock_commission_per_share, cfg.stock_commission_min)
    return cents(commission), cents(size * cfg.stock_half_spread)


def outward_cents(price: float, side: int) -> int:
    """A model price rounded outward to the tick: up for a buy, down for a sell."""
    value = Decimal(repr(float(price))) * 100
    return int(value.to_integral_value(rounding=ROUND_CEILING if side > 0 else ROUND_FLOOR))


H_MODEL_OTHER_EXPIRY = 1 << 4   # fills.fill_flags: h_model came from another expiry (ADR-0002 §7), above SURFACE_* 1-8


def h_model(day_quotes: dict | None, expiry, k: float, band: float) -> tuple[float | None, bool]:
    """ADR-0002 §7: the median half-spread of valid quotes in the same expiry within +-band log-moneyness.

    `day_quotes` maps expiry -> (log_moneyness array, half_spread array) of the day's valid quotes. If the
    contract's own expiry has none in the band, the nearest listed expiry (by days) that has some is used.
    Returns (h, True when it came from another expiry); (None, False) when no expiry has any.
    """
    if not day_quotes:
        return None, False

    def band_median(key):
        if key not in day_quotes:
            return None
        km, half = day_quotes[key]
        inside = np.abs(km - k) <= band
        return float(np.median(half[inside])) if inside.any() else None

    own = band_median(expiry)
    if own is not None:
        return own, False
    for key in sorted(day_quotes, key=lambda e: (abs((e - expiry).days), e)):
        found = band_median(key)
        if found is not None:
            return found, key != expiry
    return None, False


@dataclass
class LegFill:
    """What one leg of one order did on one fill pass."""

    leg_no: int
    qty: int                     # signed contracts filled (0: nothing)
    price_cents: int | None
    bid: float | None
    ask: float | None
    mid: float | None
    half_spread: float | None
    k_half_spread: float | None
    fill_source: str | None      # "quote" or "surface"
    cap_contracts: int
    cap_type: str
    volume_reliable: bool
    reason: str | None           # why the leg did not fill (fully), or None


def leg_price(state: str, reduce_only: bool, side: int, bid_c, ask_c, model_mid, h, cfg, surface_mode: bool):
    """(price_cents, fill_source, reason) for one leg's quote state, or (None, None, reason)."""
    if surface_mode or (reduce_only and state == NO_QUOTE):
        if model_mid is None or h is None or not np.isfinite(model_mid):
            return None, None, "NO_QUOTE"
        spread = float(cfg.surface_half_spread_mult) * h
        price = outward_cents(model_mid + side * spread, side)
        if price < 1:
            return None, None, "NO_QUOTE"
        return price, "surface", None
    if state == NO_QUOTE:
        return None, None, "NO_QUOTE"
    if state == ZERO_BID:
        if reduce_only and side > 0:
            return ask_c, "quote", None          # the mid of 0/ask is meaningless: pay the ask, whatever k is
        return None, None, "ZERO_BID"
    if not reduce_only and not opening_liquid(bid_c, ask_c, cfg):
        return None, None, "ILLIQUID"
    return price_cents(bid_c, ask_c, cfg.k, side), "quote", None
