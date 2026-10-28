# ADR-0006: Greek units, budgets and limit enforcement

**Status:** Accepted, milestone 0.
- Implemented in M5.
- The budget levels will be recalibrated in M5 against the full-revaluation stress grid from M6.

## Revised after M0 review (2026-10-28)

The adversarial review (`docs/validation/00-design-research-ledger.md`, claim 7) refuted "the budgets bound the stress loss". The units survived. I re-measured with my own Black-76 full revaluation: S = 450, σ = 0.18, r = 4%, q = 1.3%, 30 DTE, NAV $1M.

1. **The greek budgets do not bound tail loss for wing books.** A book of 10%-OTM short strangles stops at the margin cap long before any greek budget binds.
   - The reviewer's book: 109 strangles at the 50% gross-margin cap, vega 1,758 < 2,500, gamma 118,801 < 200,000. On full revaluation it loses **18.8% of NAV at (−10%, +20 vol)** and **58.3% at (−20%, +40)**. Reproduced exactly.
   - At the net-margin cap of ADR-0007, 111 strangles, delta-hedged: 20.2% and 61.3%.
2. **The 15% in "Why these levels" was presented as a bound.** It is a second-order estimate, and only for near-ATM books, where it is conservative: a full-vega-budget book of 24 ATM straddles loses 8.8% on full revaluation.
3. **Changed:** a full-revaluation **stress-loss budget** is now a binding constraint, both pre-trade and at the end of the day. It has two limits: 15% of NAV at (−10%, +20) and 35% at the worst of the 63 cells of the ADR-0010 grid.

## Context

"Vega $2,500" means nothing until the unit is pinned down. Vendors disagree on units: OptionsDX vega is per 1 vol point, and its theta convention did not reconcile (ADR-0004).

Greeks are what the strategy is actually exposed to, so risk is capped on greeks rather than on contracts or premium.
- Contract counts scale exposure with S.
- Premium-based sizing sells *more* contracts when vol is low. That means more vega and gamma just before vol jumps from a low base, which is what happened in Feb-2018.

## Decision

### Units

All greeks are portfolio-level USD amounts. They include the ×100 multiplier and the signed quantity `q` (contracts, positive = long), and they come from our Black-76 at the mark IV (ADR-0004).

| Name | Definition | Meaning |
|---|---|---|
| `delta_shares` | Σ q·100·Δ + shares | Share-equivalent exposure |
| `delta_usd` | `delta_shares · S` | P&L for a +100% move, to first order |
| `gamma_1pct_usd` | Σ q·100·Γ · S² · 0.01 | Change in `delta_usd` for a +1% move in S |
| `vega_1vol_usd` | Σ q·100·∂V/∂σ · 0.01 | P&L when every IV rises by 1 vol point (0.20 → 0.21), all expiries in parallel |
| `theta_1d_usd` | Σ q·100·∂V/∂t / 365 | P&L from one **calendar** day passing, all else fixed |

How the gamma unit maps to P&L:
- A move of ±1% earns or loses ½·0.01·`gamma_1pct_usd`.
- A move of *m* earns or loses `50·gamma_1pct_usd·m²`.

A term-weighted vega, Σ vegaᵢ·√(30/max(DTEᵢ, 7)), is **reported** for calendars. It is not budgeted, and will be revisited in M5.

### Budgets

Budgets are fractions of NAV_mid at *t*. They are checked on absolute values.

| Greek | Portfolio budget | Per position (40% of the portfolio budget) | At NAV $1M |
|---|---|---|---|
| vega | 0.25% NAV per vol point | 0.10% | $2,500 / $1,000 |
| gamma | 20% NAV per 1% | 8% | $200,000 / $80,000 |
| theta | 0.10% NAV per day | 0.04% | $1,000 / $400 |

**Why these levels.**
- **Stress loss, as a design target.** At full budget, a second-order estimate of an instantaneous −10% spot and +20 vol-point shock costs about 15% of NAV: gamma 50·200,000·0.01 = $100k, plus vega 20·2,500 = $50k. Feb-2018 was −4.1% and +20 VIX points in one day.
  - **This is not a bound.** For near-ATM books it overstates the full-revaluation loss: 24 ATM straddles lose 8.8%. For OTM wings the greek budgets are slack, and margin rather than greeks sets the size. A margin-capped book of 10%-OTM strangles loses 20.2%.
  - The stress-loss budget below is what bounds the loss at the grid cells.
- **Gamma vs vega.** For an ATM option, `gamma_1pct / vega_1vol = 1/(σ·τ)`. With the per-position limits, the two bind at the same size when 1/(στ) = 80. That is 30 days at σ = 15%, or 23 days at σ = 20%. Shorter tenors are therefore gamma-limited and longer ones vega-limited.
- **Theta.** The theta cap binds before gamma once IV is above about 19%. Its role is to cap the total "rent" collected (theta ≈ 50·`gamma_1pct`·σ²/365), so it shrinks short-gamma size in high-vol regimes.

**Delta** is handled by the hedge (ADR-0005), not budgeted here. In runs with hedging off, delta is reported but not limited, because measuring it is the point of those runs.

### Stress-loss budget (binding)

The book is revalued in full on the ADR-0010 §5 grid, using the shared revaluation in `volbt.pricing`:
- 9 spot shocks × 7 parallel vol shocks;
- sticky strike, with `σ' = max(σ_mark + v, 0.01)`;
- instantaneous, so τ is unchanged;
- hedge shares revalued at `S·(1+s)`.

| Limit | Cells | Budget, fraction of NAV_mid at *t* | At NAV $1M |
|---|---|---|---|
| `stress_core_budget` | (−10%, +20 vol) | loss ≤ 15% | $150,000 |
| `stress_worst_budget` | the worst of all 63 cells | loss ≤ 35% | $350,000 |

**Why these levels.**
- 15% at (−10%, +20) turns the M0 design target above into a limit. It is a Feb-2018-class day applied instantaneously.
- 35% at the worst cell, which for short-vol books is (−20%, +40), keeps a Mar-2020-sized instantaneous shock to about a third of NAV. That stays inside the margin cushion of ADR-0007.

**Effect at the defaults** (S = 450, σ = 0.18, r = 4%, q = 1.3%, 30 DTE, NAV $1M, empty book, unhedged):

| Structure | Portfolio size allowed by the other limits | Allowed by the stress budget | Binding |
|---|---|---|---|
| ATM straddle | 24 (portfolio vega) | 44 (core cell) | greeks, as before |
| 10%-OTM strangle | 111 (net margin) | 65 (worst cell) | **stress** |
| 15%-OTM strangle | 111 (net margin) | 94 (worst cell) | **stress** |

The levels are recalibrated in M5 together with the greek budgets.

**What it does not bound.**
- Moves outside the grid: spot below −20% or vol above +40 points.
- Skew moves, because the grid is parallel and sticky-strike.
- Gaps between hedges, and multi-day paths.

The margin rules (ADR-0007) and the named stress windows (ADR-0010) cover those, partly.

### Vega-notional sizing

Each entry is sized by the vega of one package:

```
n = floor(position_vega_target / |vega_1vol per package|),   position_vega_target = 0.10% NAV
```

The vega of one package is:
- **Straddles, strangles and vol-arb:** the total vega.
- **Calendars:** the vega of the long back-month leg, so that a near-zero net vega cannot inflate the count.

### Pre-trade check (step 9: scale, else reject)

Greeks are linear in quantity at fixed marks, so the largest feasible quantity has a closed form.
- Take the portfolio greek G, budget B and per-package greek g.
- If g **adds** to |G|: `n_G = floor((B − |G|)/|g|)`.
- If g **reduces** |G|: `n_G = floor((B + |G|)/|g|)`. This lets the trade cross zero but never pass B on the other side.
- Each greek's per-position cap also applies: `floor(0.4·B/|g|)`.

**The stress loss is linear in quantity too,** since every cell is a revaluation at fixed marks.
- Let `L_c` be the book's loss in cell c, `l_c` one package's loss there, and `B_c` the budget that applies to c.
- For each constrained cell where the package adds loss (`l_c > 0`): `n_c = floor((B_c − L_c)/l_c)`, and `n_stress = min_c n_c`.
- If hedging is on, the projection assumes the package's delta is hedged at the fill-day close; with hedging off, it is not.

The final quantity is `n = min(n_requested, all n_G, n_stress)`. If n < 1 the order is rejected; if n < n_requested it is scaled. Either way a row is written to `risk_events`, naming the limit that bound.

Orders that reduce the absolute value of every greek they touch, and the loss in every constrained cell, are never blocked. The margin pre-check (ADR-0007) runs after this one.

### End-of-day breach (step 8)

There is hysteresis to avoid churn from greek drift: a breach triggers when |G| > **1.10·B**, and the reduction target is |G| ≤ **1.00·B**.

Greeks are handled in the order **gamma, then vega, then theta, then the stress budget**. Gamma comes first because it moves fastest and is the gap risk, and cutting gamma usually cuts vega too. The stress budget uses the same hysteresis: a breach at a loss above 1.10·B, reduced to 1.00·B, cutting the largest contributors to the breached cell's loss first.

For each breached greek:
1. Sort the positions that contribute with the same sign as the portfolio by |contribution|, largest first. Ties go by `position_id`, oldest first.
2. Reduce the largest by `min(open packages, ceil(excess/|g_package|))`.
3. Repeat until the excess is ≤ 0.

The reductions are reduce-only orders that fill at *t+1* (ADR-0002).

## Alternatives considered

- **Limits in contracts or premium.** Rejected, because exposure varies with S and σ (see Context). This would win only for a single fixed structure at a fixed tenor.
- **Pro-rata scaling of all contributors on a breach.** Rejected. It crosses the spread on every position instead of one or two. It would win if strategy mix mattered more than costs.
- **Reject-only pre-trade checks (no scaling).** Rejected. It makes exposure discontinuous: one dollar over the budget loses the whole trade.
- **A VaR or expected-shortfall budget instead of greek budgets.** Deferred to M5/M6. Greeks are explainable, they map one-to-one onto the gamma-rent formula, and they are linear in quantity, which makes the pre-trade check exact. The stress-loss budget is a deterministic scenario limit, not a VaR: it needs no distribution or look-back window.
- **Greek budgets alone, deferring any stress budget to M5** (the M0 design). Rejected after the M0 review. Margin-capped wing books pass every greek budget and lose 58–61% of NAV at (−20%, +40). That would leave the backtest free to run books that the M0 text said it would not.
- **A tighter vega budget for wings,** instead of a stress budget. Rejected. Vega per strangle at 10% OTM is $16, against $103 for an ATM straddle, so a vega budget tight enough to stop wings would cripple ATM books. A loss limit in dollars treats both alike.
- **A per-expiry vega bucket, or budgeting the term-weighted vega.** Deferred. The √(30/DTE) weighting is a desk heuristic we have not verified. It would win if M6 shows calendars losing on front-month vol spikes despite small parallel vega.

## Consequences and biases

- **Greeks are computed at day-*t* marks, but fills happen at *t+1*.** The real exposure after the fill can therefore differ, by about a day of greek drift. The 10% hysteresis absorbs most of it, and the end-of-day check catches the rest a day late. That is mildly optimistic in fast markets.
- **Parallel vega understates calendar risk** when front-month vol rises more than back-month vol. This is visible in the attribution.
- **Budgets scale with NAV.** After a loss the book shrinks, a pro-cyclical de-risking that a real desk might not do. After gains it grows.
- **The stress budget makes wing size depend on the grid.** A different worst cell, such as −25%, would change the size. The grid is fixed in ADR-0010 before any run, so this cannot be tuned.

## How we will test it

1. **Units.** One long call with S = F = K = 400, σ = 0.20, τ = 30/365, r = 0 gives:
   - `delta_usd` = $20,457.44
   - `gamma_1pct_usd` = $2,781.94
   - `vega_1vol_usd` = $45.73
   - `theta_1d_usd` = −$15.24

   A long straddle has twice the gamma, vega and theta: $5,563.88, $91.46 and −$30.49.
2. **Sizing.** At NAV $1M, one short straddle package has |vega| $91.46, so floor(1,000/91.46) = **10**.
   - Per-position gamma is 55,639 ≤ 80,000 and per-position theta is 304.9 ≤ 400, so the size stays 10.
3. **Scale.** The book holds vega −1,800, gamma −120,000 and theta +700. Adding 10 short straddles is limited as follows:

   | Greek | Headroom | Packages allowed |
   |---|---|---|
   | vega | 700 | floor(700/91.46) = 7 |
   | gamma | 80,000 | 14 |
   | theta | 300 | 9 |

   The order is scaled to **7** (`risk_action = scaled`).
4. **Reject, and the risk-reducing exception.** With book vega at −2,450, the headroom is 50 < 91.46, so the order is rejected. With the same book, a *long* straddle is allowed.
5. **Breach and hysteresis.**
   - Vega −2,800 is above 2,750. The excess over the budget is 300. The largest contributor holds 15 packages at −$100 each, so it is cut by 3 packages, as a reduce-only order for *t+1*.
   - Vega −2,700 is within the hysteresis band, so no action is taken.
6. **Order of greeks.** When gamma and vega are both breached, the gamma reduction is generated first, and vega is re-evaluated on the post-gamma projection.
7. **The stress budget binds for wings.** S = 450, σ = 0.18, r = 4%, q = 1.3%, τ = 30/365, NAV $1M, hedging off.
   - Per short 10%-OTM strangle (495 call, 405 put): vega $16.12, gamma $1,089.92, theta $4.90, net margin $4,500. Losses are $1,727.58 at (−10%, +20) and $5,344.32 at the worst cell, (−20%, +40).
   - The book holds 60 of them, and an order for 50 more arrives. The limits allow:

     | Limit | Packages allowed |
     |---|---|
     | per-position vega | 62 |
     | portfolio vega | 95 |
     | portfolio gamma | 123 |
     | portfolio theta | 144 |
     | net margin (ADR-0007) | 51 |
     | stress core cell | 26 |
     | **stress worst cell** | **5** |

   - The order is scaled to **5** (`risk_action = scaled`, `risk_events.greek = stress_worst`).
8. **The stress budget does not bind ATM.** With the same market, 24 short ATM straddles lose 8.8% at (−10%, +20) and 19.5% at (−20%, +40) delta-hedged. An order sized by the vega budget passes the stress check unchanged.
