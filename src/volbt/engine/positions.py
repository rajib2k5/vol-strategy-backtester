"""The hedged P&L of one position (milestone 4, plan section 3), which the engine writes to `position_daily`.

    pnl_t = fills_t + open_t + settled_t + H_t

    fills_t     the position's option fills up to t: sum of -qty 100 price - fees (integer cents)
    open_t      its open lots at t's close: sum of qty 100 mark_t (the in-NAV marks of step 5, or of pass 9b)
    settled_t   what its settled lots delivered, valued at the session the delivery was booked: shares (S_u + D_u)
                plus the cash at K. An expiry is booked at step 4, after the dividends of step 2, so D_u is 0 there;
                an early exercise or assignment is booked at the start of step 2, before them, so its shares carry
                the dividend with ex-date u. Either way it is qty 100 times the intrinsic value at S_u (plus D_u)
    H_t         sum over u <= t of -Delta_{u-1} (S_u + D_u - S_{u-1}): the position's share of the book's daily
                delta hedge, Delta in shares at the previous close's marks, D_u the dividend with ex-date u

Why hedged: the hedge is book-level (ADR-0005), so an option-only P&L would stop out a hedged short straddle on a
move its hedge already paid for. Why the engine computes it: a strategy that priced its own marks would be a second
ADR-0004 (rejected in the plan).

What it leaves out: interest, the borrow fee and the hedge's commission and slippage are the book's, not a
position's. So for a book that holds one position from flat, with the daily hedge at the close (hedge_mode "time",
every session, timing "same_close"),

    pnl_t = NAV_mid,t - NAV_mid,0 - interest - borrow fee - hedge costs + residual

where the residual is sum over u of (N_{u-1} + Delta_{u-1}) (S_u + D_u - S_{u-1}), N the book's shares: the hedge
trades whole shares, so |N + Delta| <= 0.5 share after each hedge, plus the cents the dividend flows round off.
With hedge_mode "never" the book holds no hedge and H is 0 (default taken 2026-11-09, owner can override).

Only where the book's hedge is the positions' (fix pass after the M4 part A review). H assumes the book holds
-Delta_{u-1} shares at every close: true, to half a share, under the daily hedge at the close (hedge_mode "time",
hedge_every_n 1, hedge_timing "same_close"), and trivially with "never" (no hedge, H = 0). Under any other hedge (every
n > 1 sessions, a band, the next open) the book's shares lag the positions' delta: the review measured |N + Delta| up
to 809 shares with hedge_every_n = 5 and 753 with next_open, so H would credit the positions with a hedge the book did
not hold. The same holds for fill_timing "same_close": its pass 9b fills lots after the close's hedge, so they are
hedged from the next session (second review: |N + Delta| up to 525 shares on a made-up store); a position P&L needs
fill_timing "next_close" (fix pass 2, review B claim 5). There the engine does not compute a position P&L: hedge_usd
and pnl_usd are NaN (null in position_daily, NaN in the book a strategy reads), the conservative choice. Rejected: allocating the book's shares to positions pro
rata by delta, because two positions whose deltas nearly cancel make the shares per unit of delta unbounded (default
taken 2026-11-09, owner can override).
"""

from __future__ import annotations

SHARES_PER_CONTRACT = 100


def computed(cfg) -> bool:
    """True when the engine computes a position P&L under cfg's hedge (module docstring): fills at the next close,
    and the daily hedge at the close or no hedge."""
    if cfg.fill_timing != "next_close":
        return False
    return cfg.hedge_mode == "never" or (cfg.hedge_mode == "time" and cfg.hedge_every_n == 1
                                         and cfg.hedge_timing == "same_close")


def hedge_increment(delta_prev: float, spot_prev: float, spot: float, dividend: float) -> float:
    """-Delta_{u-1} (S_u + D_u - S_{u-1}): one session's term of H, in USD."""
    return -delta_prev * (spot + dividend - spot_prev)


def delivery_value(shares: int, cash_cents: int, spot: float, dividend: float = 0.0) -> float:
    """USD value of a settled lot's delivery at the session it was booked: shares (S + D) plus the cash at K."""
    return shares * (spot + dividend) + cash_cents / 100


def open_value(rows) -> tuple[float, float]:
    """(sum of value_mid_usd, sum of delta_shares) over a position's in-NAV mark rows, in lot_id order."""
    value = delta = 0.0
    for row in rows:
        value += row["value_mid_usd"]
        delta += row["delta_shares"]
    return value, delta


def position_pnl(fills_cents: int, open_usd: float, settled_usd: float, hedge_usd: float) -> float:
    """pnl_t = fills + open lots + settled lots + H (module docstring), in USD."""
    return fills_cents / 100 + open_usd + settled_usd + hedge_usd
