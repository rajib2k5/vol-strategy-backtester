# Integer-cent fills, and why an order fills at t+1

## First principles

A fill has three parts: when it happens, at what price, and how many contracts. ADR-0002 fixes all three. This note covers the first two, and the cap that limits the third.

**When.** A decision at *t* is made after snapshot *t*. It cannot trade at prices that were already on the screen. So it fills at the *t+1* close, against *t+1*'s quotes. The order records the *t* it was created on, and the volume it used is the volume of snapshot *t*, never the fill day's.

**At what price.** A quote has a bid *b* and an ask *a*. The half-spread is *h* = (a − b)/2. The fill pays **mid ± k·h**: a buy pays more, a sell receives less. With k = 1 a buy pays the ask and a sell receives the bid. With k = 0 both fill at the mid. The result is rounded **outward** to the tick: up for a buy, down for a sell.

**Why integers.** The bids and asks in this data are whole cents (`fills.to_cents` converts each one), and a fill is a whole cent too. In floating point the rounding fails on the cent boundaries. For a 2.00 / 2.10 quote at k = 1 the sell should be 2.00, and `(2.00 + 2.10)/2 − (2.10 − 2.00)/2` is 1.9999999999999998, which floors to 1.99. Over 100,000 random penny quotes the float k = 1 buy missed the ask on 11.8% of them (ADR-0002, Revised, point 3). So every price here is an integer number of cents, with no float anywhere.

Terms:
- **k**: the fraction of the half-spread given up, one of 0, ¼, ½, ¾, 1. The default is 1.
- **Quote state**: *valid* (0 < b ≤ a, not stale), *zero bid* (b = 0 < a), or *no quote* (crossed, one-sided, stale or missing).
- **Reduce-only**: an order that only reduces |qty| of a lot (a close). Everything else is an opening order.
- **Package**: the legs of a structure filled together (a straddle is one call and one put).

## The maths

With *b* and *a* in cents and k = n/4, the buy is the ceiling and the sell the floor of (b + a ± k(a − b))/2. In integers:

- buy = −(−(4(b + a) + n(a − b)) // 8)
- sell = (4(b + a) − n(a − b)) // 8

`//` is floor division. The ceiling is the floor of the negated value, negated again.

**Worked example**, ADR-0002 test 1 (`tests/test_engine_fills.py:161`; `uv run pytest -q tests/test_engine_fills.py`): bid 200, ask 210.

| k | buy | sell |
|---|---|---|
| 1 | 2.10 | 2.00 |
| ¾ | 2.09 | 2.01 |
| ½ | 2.08 | 2.02 |
| ¼ | 2.07 | 2.03 |
| 0 | 2.05 | 2.05 |

At k = ¼: 4 × 410 + 1 × 10 = 1,650, and 1,650/8 = 206.25 rounds up to 207. The sell is (1,640 − 10)/8 = 203.75, which rounds down to 203. A property test checks 100,000 random quotes at each k: both prices are integers, b ≤ sell ≤ buy ≤ a, and at k = 1 the buy is the ask and the sell is the bid.

**The opening filter in integers.** An opening order needs a bid of at least 5 cents and a spread of at most 25% of the mid. In integers the second test is 8(a − b) ≤ a + b. A quote 70 / 90 is exactly 25% and passes; 70 / 91 fails. In floats `(0.90 − 0.70)/((0.90 + 0.70)/2)` is above 0.25 and would reject the first one (`tests/test_engine_fills.py:240`).

**The cap and the package rule.** An opening package fills min over legs of ⌊cap / |ratio|⌋ whole packages. With V_t = 850 the cap is ⌊0.10 × 850⌋ = 85. A straddle with caps 85 and 60 fills **60** packages, and the other 60 requested are cancelled with `CAP` and never carried. 120 contracts pay 120 × $0.70 = **$84.00** (ADR-0002 test 5, `:271`). A null V_t is *unknown*, never 0: the cap falls back to 100. Reduce-only orders get the hard cap of 100 only, so a proxy can never trap a position.

**Money in cents.** Commission and slippage on SPY shares are `Decimal`, rounded half up. 1,235 shares cost 1,235 × $0.005 = $6.175 each, which is 618 cents. Python's `round(1235 * 0.005, 2)` gives 6.17 (`:281`).

## Assumptions

- **k = 1 by default.** Every fill crosses the full spread. This is pessimistic for a patient trader and honest for a backtest that cannot see the book. The sweep over k is M6.
- **The fill day's quote is the one that fills.** A contract absent from snapshot *t+1* cannot fill: an opening order is cancelled (`NO_QUOTE`), and a reduce-only order is filled off the surface at model mid ± m·h_model, rounded outward.
- **Volume is reliable only for OptionsDX from 2021-01-04.** Before that, or in `hard_only` mode, the cap is the hard cap of 100.

## Where it breaks

- **The spread is the end-of-day quote's.** A real order in a fast market pays more. The model cannot say how much.
- **A missing snapshot.** An option order created at *t* waits until the next snapshot and keeps its place. A remainder that the cap cut off is a different case: it is cancelled, never carried.
- **Zero bid.** An opening sell into a zero bid is rejected (`ZERO_BID`). A reduce-only buy fills at the ask whatever k is, because the mid of 0 / ask is meaningless. A reduce-only sell does not fill, and the long is held.

## In this project

- `src/volbt/engine/fills.py:52` `price_cents`, `:70` `quote_state`, `:81` `opening_liquid`, `:92` `leg_cap`, `:101` `package_count`, `:109` `option_fee_cents`, `:114` `stock_cost_cents`, `:183` `leg_price`.
- `src/volbt/engine/loop.py:331` `fill_option_order`: the quote states, the cap and the package rule on one order. `:443` `step_03_fill` runs it for every order created before *t*.
- `src/volbt/engine/loop.py:574` `new_order` stamps V_t and its date on each leg when the order is created.
- Measured on the development run (`tools/report_m3.py`, run `4eede29cb2ae...`, 2026-11-09): 469 quote fills and 8 surface fills, and the share of quote fills at the far side with k = 1 is 1.0000. In the 2015 trace the short call sold at the bid 5.21 (quote 5.21 / 5.24) and was bought back at the ask 5.20.
