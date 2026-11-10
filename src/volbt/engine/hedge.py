"""The delta hedge (ADR-0005): when it is due, and how many SPY shares it trades.

Net delta, in shares, is sum over open lots of qty x 100 x spot delta (Black-76 at the lot's mark IV,
sticky strike) plus the shares held, delivered shares included (ADR-0003 §3: they replace the expiring
options' terminal delta, so a hedged book trades 0 on an expiry day). The hedge trades
-round_half_away(net delta): 1,234.5 -> sell 1,235 (Python's round() gives 1,234, banker's rounding).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def round_half_away(value: float) -> int:
    """Nearest integer, halves away from zero: 1234.5 -> 1235, -1234.5 -> -1235, 2.4999 -> 2."""
    return int(Decimal(repr(float(value))).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def hedge_shares(net_delta_shares: float) -> int:
    """The shares to trade to bring the book back to zero delta."""
    return -round_half_away(net_delta_shares)


def hedge_due(cfg, session_index: int, net_delta_shares: float, spot: float, nav_mid: float) -> tuple[bool, str]:
    """(due, trigger). session_index counts the run's sessions from 0.

    time:  every n-th session from the first: n = 5 hedges on sessions 1, 6, 11 (indices 0, 5, 10).
    band:  checked daily, due when |net delta x S| > band x NAV_mid (ADR-0005 §4).
    never: not due (an unhedged book; ADR-0003 §3 liquidates delivered shares instead).
    """
    if cfg.hedge_mode == "never":
        return False, "none"
    if cfg.hedge_mode == "time":
        return session_index % cfg.hedge_every_n == 0, "schedule"
    exposure = Decimal(repr(abs(net_delta_shares * spot)))
    return exposure > Decimal(repr(nav_mid)) * Decimal(cfg.hedge_band_pct_nav.numerator) / cfg.hedge_band_pct_nav.denominator, "band"
