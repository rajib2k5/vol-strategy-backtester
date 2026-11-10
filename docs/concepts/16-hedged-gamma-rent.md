# The delta hedge and gamma rent

## First principles

A short straddle is not a bet on direction. It is a bet that the stock will move less than the options' prices say. Delta hedging removes the direction: at each close the book trades SPY shares until its net delta is about zero. What is left is a bet on *how much* the stock moves.

Terms:
- **Delta**: shares of exposure per option ([concept 08](08-greeks-and-their-usd-units.md)). **Net delta** = Σ qty × 100 × delta over the open lots, plus the SPY shares held.
- **Gamma** Γ: how fast delta changes with the stock. **Theta** Θ: the option's value lost per day to time.
- **Gamma rent**: the long-gamma holder pays theta every day and earns back ½ΓS² times the squared return. The short holder collects the theta and pays the squared moves.
- **Break-even move**: the daily move at which the two cancel, σ_implied × √(1/365). At σ = 20% it is 1.047%.

## The maths

For one option marked at implied vol σᵢ and hedged at its delta, the P&L over a short step δt is (ADR-0005, Context):

δΠ ≈ ½ Γ S² [ (δS/S)² − σᵢ² δt ] + 𝒱 δσᵢ

The bracket is realised variance minus implied variance. A long-gamma book earns when the stock moves more than the break-even, a short-gamma book when it moves less. The last term is the vega P&L of a change in σᵢ, which a delta hedge does not remove.

**Worked example**, ADR-0005 test 1 (`tests/test_engine_hedge.py:178`; `uv run pytest -q tests/test_engine_hedge.py`). One long ATM straddle: S = F = K = 400, σ = 20%, 30 days, r = 0. Per straddle (×100): Γ = 3.4774 shares per $, delta +2.287 shares, theta −$30.49 a day. For a 1% move ½Γ(0.01 S)² = $27.82. Hedged, the one-day P&L at S → 404 is about 27.82 − 30.49 = −$2.67, and exactly −$2.82 (the gap is third-order terms). A short straddle is the mirror image: +$2.82.

**The engine's version, in whole shares.** A fractional hedge of 228.7 shares is not tradable. The test uses 100 straddles: net delta 228.7 shares, so the hedge **sells 229** (−229 shares). One day later the book is repriced at S = 404 with 29 days left, and the hedged change in NAV is the Black-76 repricing of the 100 straddles less 229 × $4: **−$282.88**, to the cent. A hedge with the wrong sign would lose 2 × 229 × $4 = $1,832 more.

**Rounding.** The trade is the nearest whole share, halves away from zero: 1,234.5 sells **1,235**, where Python's `round()` gives 1,234. The cost is $0.005 a share commission (minimum $1.00 an order) plus $0.005 slippage, each in `Decimal` and rounded half up: 1,235 shares cost 618 + 618 cents.

**What it leaves.** After the hedge |net delta| ≤ 0.5 shares, because the trade is whole shares. In the development run the largest value was 0.4998 shares over 2,516 sessions (`tools/report_m3.py`, 2026-10-30).

**Worked example on real data**, the 2015 trace (block "trace"): the short straddle's net delta at the 2015-03-16 close was −242.97 shares, so the hedge bought 243, leaving 0.03, for $2.44. The next day the delta was +50.83: sold 51, left −0.17, for $1.26. Commission was the $1.00 minimum and slippage 51 × $0.005 = $0.255, rounded to 26 cents.

## Assumptions

- **Same-close hedging.** The hedge trades at the close that produced its delta. This is the one place the *t+1* rule is relaxed (ADR-0005 §3). A real book would use a delta estimated before the close. The `next_open` variant is implemented but no test runs it.
- **Sticky-strike delta.** Delta is Black-76 at the lot's mark IV with the IV held fixed when spot moves. It ignores the correlation of spot and vol.
- **Shares are cheap.** About $0.01 a share a side in total, so cost is not the reason to hedge less often. Short shares pay a 0.25% a year borrow fee on their prior-close value, an unverified assumption (decision D9).
- **Dividends on the hedge.** Short shares pay the dividend on the ex-date: 100 short shares before a $1.50 ex-date cost $150 at step 2 (ADR-0005 test 5).

## Where it breaks

- **Gaps.** Delta and gamma are a local expansion. A −8% gap day cannot be hedged at the old delta, and with end-of-day data nothing happens in between.
- **Vega is not hedged.** A rise in implied vol hurts a short straddle however well it is hedged.
- **M3 records the hedge, not the attribution.** The `daily_pnl` columns for the delta, gamma, vega, theta and residual parts exist and are null until M6 (decision D23). Theta with F held fixed is $2.96 a day smaller in size than with S held fixed on a 30-day ATM call at 5% ([concept 08](08-greeks-and-their-usd-units.md)), and M6 must attribute that carry, not leave it as residual.
- **Hedge frequency is a sweep, not a result.** Weekly hedging is about √5 times noisier than daily in theory (ADR-0005). The sweep is M5.

## In this project

- `src/volbt/engine/hedge.py:14` `round_half_away`, `:19` `hedge_shares`, `:24` `hedge_due` (time, band and never).
- `src/volbt/engine/loop.py:508` `net_delta`, `:512` `step_06_hedge`, `:493` `execute_hedge` (the three cash flows: trade, commission, slippage).
- `src/volbt/engine/fills.py:114` `stock_cost_cents`; `src/volbt/engine/cash.py:27` `cents`.
- `tests/test_engine_hedge.py:32` banker's rounding, `:40` the sign, `:49` the band, `:63` every 5 sessions is sessions 1, 6, 11, `:87` 1,235 shares for 618 + 618 cents, `:137` the dividend on short shares, `:178` ADR-0005 test 1, `:257` a hedged book trades 0 shares on the expiry day.
