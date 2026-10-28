# ADR-0005: Delta-hedge frequency, instrument and cost

**Status:** Accepted, milestone 0. Implemented in M3 (mechanics) and M5 (sweep). Revisit after the M6 hedging-error report.

## Revised after M0 review (2026-10-28)

The decisions are unchanged; the review accepted the same-close hedge exception and the test 1 numbers. One test was underspecified. Test 2's $6.18 depends on the rounding mode, because 1,235 × 0.005 = 6.175 and Python's `round()` gives 6.17. It now cites ADR-0002 §4: `Decimal`, `ROUND_HALF_UP`.

## Context

The vol strategies here bet on implied vs realised variance, not on direction. Delta hedging is what turns an option position into a variance bet. For one option marked at implied vol σᵢ and hedged at BSM delta, the P&L over a step δt is (`docs/concepts/00-background.md` §2):

```
δΠ ≈ ½ Γ S² [ (δS/S)² − σᵢ² δt ] + 𝒱 δσᵢ        ("gamma rent")
```

How to read it:
- A long-gamma book earns ½ΓS² times the realised squared return and pays theta at the implied rate. A short-gamma book is the reverse.
- The break-even daily move is σᵢ·√(1/365). At σᵢ = 20% that is 1.047%.
- **Discrete hedging leaves a residual.** Its standard deviation scales with √δt. In the background doc's simulation, weekly hedging was 2.1× noisier than daily (theory gives √5 ≈ 2.2).
- **SPY shares are cheap to trade.** About $0.01 per share per side in total (ADR-0002 §4), so trading cost is not the main reason to hedge less often.

## Decision

1. **Instrument.** Hedge with SPY shares only.
   - We allow fractional deltas, but round the trade to whole shares, half away from zero.
   - Short shares pay `borrow_fee = 0.25%/yr` on their market value. This is an unverified assumption (SPY is normally easy to borrow), so it is a parameter.
2. **Default schedule: hedge at every session's close, back to zero delta.**
   - Target: `hedge.mode = time`, `every_n_sessions = 1`.
   - Net book delta = Σ lots qty·100·Δᵢ + shares, in shares. Trade −round(net delta).
   - **Delta definition.** Δᵢ is the Black-76 spot delta at the lot's mark IV, `DF·(F/S)·N(d₁)` for calls and `DF·(F/S)·(N(d₁)−1)` for puts. That is "sticky strike": the IV is held fixed when spot moves.
   - The hedge runs at step 6 of the daily loop: after fills, settlement and marks, so delivered shares net against it (ADR-0003). It runs before the risk checks.
3. **Timing exception.** `hedge.timing = same_close` (default) trades at the SPY official close of the same session whose snapshot produced the delta.
   - This is the one place where ADR-0002's *t+1* rule is relaxed, and the reason is deliberate. A hedge does not choose a trade to exploit a price; it neutralises exposure. In practice it would be executed with a market-on-close order on a delta estimated at about 15:45.
   - Variant: `hedge.timing = next_open` hedges at the SPY open of *t+1* (yfinance OHLC).
4. **Sweep** (M5). Bands are checked daily and rebalance to zero when breached.
   - Time-based: `every_n_sessions ∈ {1, 2, 5, never}`.
   - Band-based: |net delta·S| > `band_pct_nav ∈ {0.5%, 1%, 2%, 5%}` of NAV.
5. **Costs.** Hedge costs are $0.005/share commission (minimum $1 per order) plus $0.005/share slippage, as in ADR-0002 §4.
6. **Cash flows on the share leg.**
   - On ex-dates, short shares pay D per share and long shares receive it (step 2 of the daily loop).
   - Share proceeds sit in cash and accrue interest (ADR-0007).
   - Leaving out the dividend would be a classic bug: the option prices already embed it through the parity forward (ADR-0008).
7. **Reporting.** `hedges` records the trigger, the shares traded and the cost. `daily_pnl` splits P&L into delta (unhedged part), gamma, vega, theta, hedge costs and residual. The analytics report the hedging error's standard deviation for each sweep setting.

## Alternatives considered

- **Band-only default** (rebalance only when |delta| crosses a threshold). Rejected as the default. On SPY trading costs are negligible, so the band mainly adds hedging noise without saving much. It is kept in the sweep because it would win if the hedge instrument were expensive (SPX options, wider-spread ETFs).
- **Utility-based bands** (Whalley–Wilmott: band ∝ (cost·Γ²·S²/risk-aversion)^⅓). Rejected for now: they need a risk-aversion parameter we have no basis for. A reasonable M5 extension.
- **Minimum-variance or smile-adjusted delta** (adjusting BSM delta for spot–vol correlation, Hull–White 2017). Rejected as the default. Its regression coefficients must be estimated from history, which creates a look-ahead risk if fitted on the full sample, and it makes the attribution harder to explain. It would win if the M6 attribution shows a persistent delta residual correlated with ∂σ/∂S. Planned as a variant.
- **Hedging with ES futures or SPX options.** Rejected: different data, basis risk between SPY and ES, roll mechanics. Not justified for a learning repo.
- **Hedging at *t+1* like option fills.** Rejected as the default: the book would carry a full day of unhedged delta on every new position, which mixes direction into a vol test. Kept as the `next_open` variant.

## Consequences and biases

- **The same-close hedge is mildly optimistic.** It assumes we trade at the exact print the delta came from, which a real book can only approximate. The effect is not directional on average, but it flatters gap days (a real hedge would use a delta estimated before the close). The `next_open` variant bounds it.
- **Sticky-strike delta ignores spot–vol correlation.** For short-put-skewed books it under-hedges on down moves. That shows up as a negative delta residual on sell-offs, and it is visible in the attribution rather than hidden.
- **Hedging error is irreducible noise.** The sweep shows how much of a strategy's P&L variance comes from hedging rather than from the vol spread.

## How we will test it

1. **Gamma rent, one long ATM straddle.** S = F = K = 400, σ = 20%, τ = 30/365, r = q = 0.
   - Per straddle (×100): Γ = 3.4774 shares/$, delta = +2.287 shares, theta = −$30.49/day, vega = $91.46/vol point.
   - For a 1% move: ½Γ(0.01·S)² = $27.82.
   - Hedged one-day P&L, with τ → 29/365 and σ fixed, matches gamma + theta to within $0.25 at a 1% move and $1.00 at a 2% move. The gap comes from third-order terms:

     | Move | Exact | Gamma + theta | Gap |
     |---|---|---|---|
     | S → 404 (1%) | −$2.82 | −$2.67 | $0.15 |
     | S → 408 (2%) | +$79.87 | +$80.79 | $0.92 |

     A third case: S → 400, exact −$30.75 vs theta −$30.49.
2. **Hedge trade.** Net book delta +1,234.6 shares → sell 1,235 shares at the close. Cost: $6.18 commission + $6.18 slippage, each 6.175 rounded `ROUND_HALF_UP` (ADR-0002 §4).
3. **Band.** With `band_pct_nav = 1%`, NAV $1M and S = 400 (band = 25 shares): a net delta of 20 shares → no trade; 30 shares → sell 30.
4. **Weekly schedule.** `every_n_sessions = 5` → hedge rows on sessions 1, 6, 11, … only. A fixture with a known spot path must produce a hedging-error std about √5× the daily one (tolerance 1.6×–2.8× on a 2,000-path simulation, seeded).
5. **Dividend on short hedge shares.** Holding −100 shares at the close before a $1.50 ex-date → cash −$150 at step 2 of the ex-date.
6. **Netting with delivery.** See ADR-0003 test 3: the hedge must trade 0 shares on the expiry day.
