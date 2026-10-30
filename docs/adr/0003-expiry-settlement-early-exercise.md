# ADR-0003: Expiry, settlement, pin risk and early exercise

> **Data notice.** The DoltHub figures in this document (counts, dates, quantiles and summaries, in its text and in its tables) are derived from the DoltHub database `post-no-preference/options` (<https://www.dolthub.com/repositories/post-no-preference/options>), licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), and are shared under the same licence. Changes: we aggregated it into counts, shares and quantiles, compared it with OptionsDX and ran our pricing build on it; no quote row is reproduced. The rest of this repository is MIT. See [DATA.md](../../DATA.md).

**Status:** Accepted, milestone 0. Implemented in M3; the default exit DTE is revisited in M4.

## Revised after M0 review (2026-10-28)

The adversarial review (`docs/validation/00-design-research-ledger.md`, claim 4) refuted the put rule. I re-derived it and re-measured it with my own CRR lattice and a Barone-Adesi–Whaley check, written independently of the reviewer's code.

1. **The put rule fired too early.** `K(1−e^{−rτ}) > C + PV(div)` compares exercising now with holding a *European* put. That condition is necessary but not sufficient, because it ignores the right to exercise later and the option to wait for an ex-date.
   - At r = 5%, σ = 0.20, 30 DTE, K = 450, it fired below S = 421.70 (6.7% ITM). Exercise is optimal only below S = 408.82 (10.1% ITM; BAW gives 411.12).
   - With a $1.70 dividend 10 days out, it fired at 12.9% ITM, where exercise is never optimal before the ex-date.
2. **"More assignments is conservative for a short" was false.** Premature assignment extinguishes the writer's liability at intrinsic value while it is worth more. That hands the writer the time value: $61.70–129.47 per contract per false assignment at r = 5%, $32.91 at 2% and $5.12 at 0.25%. So the rule was **optimistic for short puts**, most of all in the high-rate years: 2023 and the 2024–26 holdout.
3. **Changed.** Puts are now decided on a CRR lattice: exercise when the continuation value is no more than intrinsic. The old inequality survives only as a cheap pre-filter, because it is a necessary condition. The rule is the same in quote and surface mode (Decision 5).
4. **The call rule survives.** Re-checked against my own lattice with a dividend just before the ex-date, the closed form agrees with the optimal boundary to within $0.01 of spot. Examples: 462.60 vs 462.61 at r = 5%, σ = 0.20, τ = 7 d; 545.85 vs 545.85 at r = 0.25%, σ = 0.30, τ = 60 d. It now uses the European put P_E rather than the market mid, which makes it exact and the same in both modes.
5. **Test 5 contradicted line 27.** Its τ of 1/365 conflicted with "τ runs from the ex-date to expiry", which gives τ = 0 when the ex-date and the expiry are the same day. Test 5 now uses τ = 0.

Round 2 (`docs/validation/00-round2-ledger.md`, claim 6): the put-rule boundaries reproduce (old rule 421.70; lattice 409.02, 408.78 and 408.66 by tree size; tolerance boundary 409.75; BAW 411.12) and the call closed form matches the lattice. One premise was wrong: "the only option price in surface mode is the European one" contradicts ADR-0008's lattice marks inside |k| ≤ 0.15. It is reworded in Decision 5 and in the rejected market-time-value alternative; the decision does not change.

## Context

These are the SPY contract facts the decision relies on. Sources are listed at the end.

| Fact | Source |
|---|---|
| SPY options are American-style, physically settled (100 shares) and PM-settled. | [1] |
| Exercise-by-exception (Ex-by-Ex) auto-exercises expiring equity and ETF options that are ≥ $0.01 in the money, in all account types. | OCC Rule 805, $0.01 since the June-2008 expiration [2] |
| OCC decides moneyness from the underlying's 4:00 pm ET close. | [3] |
| Expiring ETF options trade until 4:15 pm ET. | SEC Rel. 34-105153, p. 10: "trading on the expiration day of equity options will continue until 4:15 p.m."; Cboe ETH FAQ, Q5 [3] |
| Exercise instructions are due by 5:30 pm ET. | FINRA Rule 2360(b)(23)(A)(iii) [4] |

**Dividends.**
- SPY's ex-dividend date is the third Friday of March, June, September and December, or the business day before it [5]. That is usually the monthly expiration day.
- Since T+1 settlement, the ex-date has equalled the record date. Examples [5]:
  - 2024-06-21: $1.759024
  - 2024-12-20: $1.965548
- **Who holds the dividend.** Whoever holds the shares before the ex-date gets it. A short call that is assigned the evening before the ex-date therefore delivers shares and leaves us short over the ex-date, so we owe the dividend.

**Early-exercise condition for calls.** A call holder exercises just before the ex-date if the dividend exceeds what the call would still be worth after the ex-date above intrinsic value.
- European put-call parity after the ex-date gives `C_ex = P + (S − D) − K·e^{−rτ}`.
- Exercise beats holding when `S − K > C_ex`, which is equivalent to **`D > P_E(K) + K·(1 − e^{−rτ})`**, with P_E the European put.
- Here τ runs from the ex-date to expiry.
- Cboe [6] and OIC [7] state the simpler "put < dividend" heuristic, which leaves out the interest term.

**Early-exercise condition for deep in-the-money puts.** This is *not* the mirror image of the call condition.
- Exercising now pays `K − S`. Not exercising keeps an **American** put, worth `P_A ≥ P_E`.
- By European put-call parity, `P_E = C_E + K·e^{−rτ} − S + PV(D)`. So "exercise beats a European" is `K·(1 − e^{−rτ}) > C_E(K) + PV(dividends with ex-date before expiry)`.
- That inequality is **necessary** (exercise can be optimal only if it beats the European) but **not sufficient**. It leaves out two things:
  - the right to exercise later, when the put is deeper in the money;
  - waiting until just after an ex-date. If `D > K·(e^{r·τ_ex} − 1)`, waiting dominates exercising now, because the put gains D when the stock goes ex.
- The exact decision is `K − S ≥ continuation value of the American put`, and that needs a lattice. A call is different: after its last ex-date before expiry, the continuation is a European call, so the closed form is exact.
- Measured gap (K = 450, σ = 0.20, 30 DTE): at r = 5% the European test fires at 6.7% ITM and the optimum is 10.1%; at r = 0.25% they are 14.0% and 17.7%. The cost of the gap scales with r, so it was small in 2010–2015 and 2020–21 and large at the roughly 5% rates of 2023–26.

**Data.** OptionsDX quotes the expiring contracts on expiration day at 16:00. In 2023, all 250 dates contain a 0-DTE expiry (measured).

## Decision

**The engine models settlement and early exercise.** Strategies, by default, avoid both by closing positions at a DTE threshold.

1. **Default exit by DTE.**
   - With `exit_dte = 7` calendar days, a close order is created at *t* when DTE at *t+1* ≤ 7, and it fills at *t+1* (ADR-0002).
   - The values swept are {0 (hold to expiry), 3, 7, 14, 21}.
   - **Out of sample, a 7-DTE exit has no quoted expiry.** DoltHub lists no expiry under 10 DTE, so in surface mode the exit is marked and filled by tenor extrapolation (ADR-0004), with a median error of about 1.2–1.3 vol points (measured, ADR-0009 §4). M4 chooses `exit_dte` with the DoltHub-masked surface gap in view, and applies the same value in every split.
2. **Settlement on expiration day *t*** (step 4 of the daily loop):
   - Moneyness is computed from `S_set = SPY official close at t`. This is the unadjusted close, checked against `[UNDERLYING_LAST]` (ADR-0009).
   - A call is exercised if `S_set − K ≥ 0.01`; a put if `K − S_set ≥ 0.01`. Otherwise the contract expires worthless.
   - We model no contrary instructions: we never decline to exercise, and we assume no counterparty declines either.
   - Shares delivered per contract, at price *K*:

     | Position | Shares delivered |
     |---|---|
     | Long call | +100 |
     | Short call | −100 |
     | Long put | −100 |
     | Short put | +100 |

   - Cash moves by ∓100·K accordingly.
   - The exercise or assignment fee is 0 by default (ADR-0002).
   - Delivered shares join the SPY share position.
3. **Delivered shares.**
   - **Delta-hedged strategies.** The day-*t* hedge (step 6) runs *after* settlement. It therefore sees the delivered shares in place of the expiring options' terminal delta of ±1 or 0 per share. The two net out, so no extra trade is needed. That matches a real hedged book, where assigned shares replace hedge shares.
   - **Unhedged strategies.** A reduce-only order to liquidate the delivered shares is created at *t* and fills at the *t+1* SPY close, with the cost of ADR-0002 §4. The book carries the overnight risk, or the weekend risk for a Friday expiry, which is the real cost of physical settlement.
4. **Pin risk.**
   - Any short contract with `|S_set − K| ≤ pin_band = $0.50` at expiry is still settled by the deterministic Ex-by-Ex rule, but is flagged `pin_flag`.
   - The analytics report the count and the notional exposed.
   - We do **not** simulate what happens after 4:00 pm: with EOD data there is no information about it.
5. **Early assignment and early exercise.** Checked at step 10 of day *t*; takes effect at the start of *t+1*.
   - **Common inputs, the same in quote and surface mode.**
     - `S_t`, the SPY close.
     - `r_t`, the DGS3MO continuous rate *(M2 review amendment, default taken 2026-10-29, owner can override: the value dated strictly before t, ADR-0008 amendment 3)*.
     - σ = the day's surface IV at the contract's log-moneyness for its expiry (ADR-0004 rule 3, built from de-Americanised OTM quotes, ADR-0008). For an ITM put (K > F) that node comes from the OTM call at the same strike.
     - Dividends: each projected ex-date before expiry, at the **last paid** amount, so there is no look-ahead. The actual D is what gets booked on the ex-date. *(M2 review amendment, default taken 2026-10-29, owner can override: at the projected amount of ADR-0008 amendment 4, the same quarter a year earlier times the trailing year's growth, still from dividends paid by t only. The last paid amount overstated every March since 2009 by 10.9–47.3%, and the call rule fires on exactly those ex-date eves.)*
     - **Market mids are not used.** In surface mode a put price is a model price. Beyond |k| ≤ 0.15 it is the European Black-76 price, for which "time value ≤ 0" is algebraically the refuted European rule. Inside that band a model mark is the CRR American price at the surface IV (ADR-0008 §8), and a time-value test on it would only repeat the lattice rule below.
   - **Who is affected.** If we are short, we are assigned on **every** contract for which exercise is optimal. If we are long, we exercise it ourselves.
   - **Calls, when *t+1* is an ex-date with dividend D.** Each ITM call is exercised if `D > P_E(K) + K·(1 − e^{−r_t·τ})`.
     - `P_E` is the Black-76 European put at σ, and τ runs from the ex-date to expiry.
     - This is exact when that ex-date is the last one before expiry. That covers every lot with fewer than about 90 DTE, since SPY goes ex quarterly.
     - A lot with a further ex-date before expiry uses the put lattice below, with the call payoff.
   - **Puts, every day, for each ITM put lot.**
     1. **Pre-filter:** skip the lot unless `K·(1 − e^{−r_t·τ}) > C_E(K) + Σ D_i·e^{−r_t·τ_i}`, with C_E the Black-76 call at σ. It is a necessary condition, so a lot that fails it cannot be optimal to exercise, and the lattice is skipped.
     2. **Decision:** a CRR lattice with `exercise_tree_steps = 500` over τ, at σ and r_t, with escrowed discrete dividends at the projected ex-dates. The put is exercised iff `continuation value at t − (K − S_t) ≤ exercise_tol = $0.005` per share.
     - One evaluation takes about 4 ms in numpy (measured).
     - The decision method, σ and the margin `continuation − intrinsic` are stored in `expiry_events` (`decision_method`, `decision_iv`, `threshold_value`).
   - **Bookkeeping.**
     - The shares are booked at *K* at the start of *t+1*.
     - The dividend on the ex-date is booked afterwards (step 2 of the daily loop).
     - Hedges or liquidation follow the rules in point 3.
     - Each event is recorded in `expiry_events`, with `event_type ∈ {expired_worthless, exercised, assigned, early_exercised, early_assigned}`.

## Alternatives considered

- **Treating SPY options as European (never early-exercised).**
  - Rejected because it is *favourable to short calls*: a real holder exercises ITM calls the day before the ex-date and the writer pays the dividend.
  - It would win only for OTM-only books that always close well before ex-dates, and the default DTE exit does not guarantee that.
- **Probability-weighted or random partial assignment.** Rejected: we have no data to calibrate the share of long holders who exercise, and a random draw adds noise without adding information. Assuming 100% assignment of qualifying contracts is an explicit worst case.
- **For puts, the European comparison `K(1−e^{−rτ}) > C + PV(D)`** (the M0 rule). Rejected after the M0 review. It fires 3–5 points of moneyness too early at 2–5% rates, and before an ex-date it fires when exercise is never optimal. Each false assignment gifts a short put its time value. It is kept only as a pre-filter.
- **For puts, the market's own time value, `P_mid − (K − S) ≤ ε` with ε about half the spread.** Rejected as the rule of record.
  - In surface mode (DoltHub, and most held contracts there) the put price is a model price. ~~The European Black-76 price beyond |k| ≤ 0.15, where the test reduces to the refuted rule, and the lattice price at the surface IV inside that band (ADR-0008 §8), where it would only repeat the lattice rule.~~ *(M2 round 3, docs reviewer: the band is gone. From milestone 3 a model mark is the CRR American price at the surface IV at every |k| (ADR-0004 rule 3, ADR-0008 §8, round-2 decision E8), so in surface mode the test would only repeat the lattice rule.)*
  - So quote and surface mode would run different rules, and ADR-0010 needs one rule across splits.
  - Its error is bounded by the deep-ITM put's quoted spread, not by a $0.005 tolerance.
  - It would win if every split had American quotes for every held contract.
- **Barone-Adesi–Whaley instead of a lattice.** Rejected. It is an approximation: at r = 5%, σ = 0.20, 30 DTE it puts the exercise boundary at S = 411.12, against the lattice's 408.82, so it would assign about $2 of spot early. It would win if lattice cost mattered, and at about 4 ms per pre-filtered lot it does not.
- **A lattice for calls too.** Not needed. For a single remaining ex-date the closed form is exact, and it agrees with the lattice to $0.01 of spot. The lattice is used only for the rare call with two ex-dates left.
- **Settling expiring options at the last quote instead of at intrinsic value.** Rejected: the 16:00 quote on expiration day is noisy, and OCC settles against the close, not the option's own quote.
- **Forcing liquidation at the expiry-day close for unhedged books.** Rejected:
  - Under the timing rule of ADR-0002 we would be trading on the same snapshot that determined moneyness.
  - In reality, Friday's assignments are known only after 5:30 pm.

## Consequences and biases

- **The DTE exit gives up the last week of theta** for short-vol strategies. That week has the highest theta per day and also the highest gamma.
  - Expected effect: lower mean return and a lighter left tail.
  - The exit also pays one more spread crossing than letting OTM options expire worthless, which is conservative on costs.
  - The `exit_dte` sweep measures both effects.
- **Assignment exactly at optimal exercise is the writer's worst case, so it is conservative for shorts.** A real holder who deviates from the optimal policy transfers value to the writer.
  - **Exercising early** extinguishes the writer's liability at intrinsic value while it is worth more. The M0 put rule did exactly this.
  - **Exercising late** lets the writer keep earning interest on K. On a deep-ITM put that is about K·r/365 per share per day: $6 per contract per day at K = 450 and r = 5%.
  - Assuming every holder of a qualifying contract exercises therefore overstates how often assignment happens, and that is the conservative direction.
- **The only remaining bias is the boundary's model error.**
  - The tolerance moves the boundary toward the money: at r = 5%, σ = 0.20, 30 DTE the rule fires below S = 409.75 rather than about 408.8. The in-model gift is at most $0.005 per share, or $0.50 per contract.
  - A surface IV that is too low moves the boundary toward the money too (σ = 0.12 instead of 0.20 moves it from 10.1% to 5.1% ITM at r = 5%), which gifts the writer. One that is too high makes assignment late. The analytics report `decision_iv` next to every early assignment.
- **For long options we exercise optimally ourselves.** That is a legitimate decision of ours, not a bias.
- **Pin outcomes are deterministic.** That *understates* pin risk, possibly by a lot. Hence the flag and the reported count, and the default DTE exit avoids most of it.
- **The weekend gap on delivered shares is captured** for unhedged books, and only to the extent that a Friday-to-Monday close-to-close move captures it.

## How we will test it

1. **Ex-by-Ex at the threshold.**
   - At `S_set = 450.00`, a 450 call and a 450 put both expire worthless.
   - A 449.99 call is exercised (ITM by $0.01).
   - A 450.01 put is exercised.
2. **Long-call exercise.** Two long 440 calls at `S_set = 450` deliver +200 shares and cash −$88,000.
   - The shares are marked at $90,000, so the settlement adds +$2,000 net.
   - That equals the calls' intrinsic value (2 × 100 × 10). Settlement conserves NAV relative to an intrinsic valuation.
3. **Hedged netting.** Book: one long 460 put and +100 hedge shares, with `S_set = 450` on expiry day.
   - The put is exercised and delivers −100 shares, leaving a net 0.
   - The day-*t* hedge trades 0 shares, and no liquidation order is created.
4. **Unhedged liquidation.** The same put without a hedge leaves −100 shares.
   - A reduce-only buy-to-cover order for 100 shares is created at *t* and fills at the *t+1* close.
   - The P&L includes `−100 × (S_{t+1} − S_t)` plus the ADR-0002 §4 cost.
5. **Early call assignment.** *t+1* is an ex-date with D = $1.80, and it is also the expiration day, the usual SPY case. Short 440 call, S = 450, r = 5%.
   - τ from the ex-date to expiry is 0, so `K(1 − e^{−rτ}) = 0`, and the European put at τ = 0 is worth its intrinsic value, 0.
   - 0 < 1.80, so the call is assigned.
   - Start of *t+1*: −100 shares, cash +$44,000, then the dividend: cash −$180.
6. **No early call assignment.** Same as test 5, but the expiry is 30 days after the ex-date (τ = 30/365).
   - The interest term is 440 × (1 − e^{−0.05·30/365}) = 1.8045, and the European put is 3.00.
   - 4.80 > 1.80, so the call is not assigned.
   - **Closed form against the lattice.** With K = 450, σ = 0.20, r = 5%, τ = 7/365 and D = 1.70, the closed form fires from S = 462.60 and the lattice optimum from 462.61. The test asserts they agree within $0.05.
7. **Deep-ITM put.** K = 450, τ = 30/365, σ = 0.20, no ex-date unless stated, N = 500, tol = $0.005.

   | Case | Old inequality, LHS vs RHS | Continuation − intrinsic | Assigned? |
   |---|---|---|---|
   | a. r = 5%, S = 420 (7.1% ITM) | 1.8455 > 1.6026, fires | 0.5201 | **No.** The refuted rule assigned it. |
   | b. r = 5%, S = 400 (12.5% ITM) | 1.8455 > 0.2159, fires | −0.0037 | Yes |
   | c. r = 5%, S = 395, last dividend 1.70 at an ex-date 10 days out | 1.8455 > 1.7919, fires | 1.0986 | **No:** waiting for the ex-date dominates |
   | d. r = 0.25%, S = 390 (15.4% ITM) | 0.0925 > 0.0493, fires | 0.0167 | **No** |

   - **Stability.** Each decision is the same at N = 2,000, where the margins are 0.5187, −0.0009, 1.0997 and 0.0169.
   - **Pre-filter.** At r = 5% and S = 430, the old inequality does not fire, and the lattice is not called.
8. **Pin flag.** With `S_set = 450.30`, a short 450 call is assigned (ITM by 0.30) and `pin_flag = true`. With `S_set = 451.00` it is assigned and the flag is false.
9. **DTE exit date.** For an expiry of Fri 2024-03-15 with `exit_dte = 7`, the close order is created on 2024-03-07 (DTE at 03-08 is 7) and fills on 2024-03-08.

## Sources

1. Federal Register, SR-CBOE-2023-036 (8 Aug 2023): https://www.govinfo.gov/content/pkg/FR-2023-08-08/html/2023-16885.htm
2. ISE Regulatory Circular 2008-29 (16 Jun 2008): https://m.nasdaqtrader.com/Content/NewsAlerts/ISERics/RIC-2008-29$OCC_Rule_Change_Automatic_exercise_reduction$20080616.pdf
   - Phlx Memo 1107-08: https://www.nasdaqtrader.com/content/phlxmemos/2008/Jun/1107-08.pdf
   - The current OCC rulebook PDF returned HTTP 403, so the current wording is **unverified**.
3. Cboe Equity Options ETH FAQ (updated 2 Oct 2026), Q5: https://cdn.cboe.com/resources/techspec/technical-specifications-equity-options-extended-trading-hours-faq.pdf
4. FINRA Information Notice, 3 Feb 2021: https://www.finra.org/rules-guidance/notices/information-notice-020321
5. SPY prospectus (485BPOS, 26 Jan 2026): https://www.sec.gov/Archives/edgar/data/884394/000119312526022316/d77353d485bpos.htm
   - State Street historical distributions: https://www.ssga.com/library-content/products/fund-data/etfs/us/spdr-etf-historical-distributions.xlsx
6. Cboe Insights (15 Apr 2024): https://www.cboe.com/insights/posts/dont-get-stuck-paying-the-dividend-on-your-short-trade/
7. OIC Office Hours FAQ: https://www.optionseducation.org/news/september-office-hours-faqs-volatility-crush,-assignment-risk-and-vertical-spreads
