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

## M3 amendments (default taken 2026-10-30, owner can override)

The M3 build (`docs/milestones/03-daily-engine.md`; `LEARNING_LOG.md`, defaults 53, 69 and 70) found two gaps between this ADR and real contracts, and its adversarial review (`docs/validation/03-ledger.md`, claims 3 and 6, finding R4, and the finding nobody asked about, R5) changed the first amendment; the round-2 review (2026-11-09, finding DS-1) changed its 2018-12-05 entry back. The original text stays in place.

1. **§2, expiries that are not sessions: an explicit map of what a primary source confirms** (decisions D16 and B8). §2 takes the expiry date to be a session. A few listed SPY expiry dates are not. **Changed:** a contract settles on its expiry date when that is a session, or when it falls after the last session of the calendar (see the last bullet). Two dates are mapped, each to the session whose close settles it. Any other non-session expiry stops the run with `UnmappedExpiry`, because guessing a settlement would invent a price (`src/volbt/engine/settlement.py`).
   - **2015-12-19 (a Saturday) settles at the 2015-12-18 close.** The December 2015 SPY standard series were grandfathered with a Saturday expiration, but exercise processing had moved to the Friday: SEC Rel. 34-69772, approving SR-OCC-2013-04 (<https://www.govinfo.gov/content/pkg/FR-2013-06-21/pdf/2013-14793.pdf>); Cboe RG13-118 / C2 RG13-041 (<https://cdn.cboe.com/resources/regulation/circulars/regulatory/RG-C2-2013-041.pdf>), which lists "December 2015 SPY"; SEC Rel. 34-70900 (<https://www.sec.gov/files/rules/sro/ise/2013/34-70900.pdf>), which sets the exercise cut-off at the business day before a Saturday expiration.
   - **2018-12-05 (a Wednesday) settles at the 2018-12-04 close** (amended 2026-11-09, round-2 finding DS-1). Markets were closed for the national day of mourning for President George H.W. Bush. OCC Information Memo #44125 (2018-12-02, "Processing December 5, 2018 – President George H.W. Bush") says that Wednesday, December 5, 2018 is an expiration date, and its table lists SPY options at "Tuesday closing prices". It was read through the Wayback Machine (<https://web.archive.org/web/20190822143120id_/https://www.theocc.com/webapps/infomemos?number=44125&date=201812&lastModifiedDate=12%2F02%2F2018+00%3A00%3A00>), because theocc.com answers HTTP 403 to direct fetches. FINRA's Information Notice of 2018-12-04 sets a 10:00 a.m. ET exercise cut-off on 12-05 for options expiring that day. Cboe Exchange Notice C2018120300 (<https://cdn.cboe.com/resources/schedule_update/2018/Cboe-to-Observe-National-Day-of-Mourning-on-Wednesday-December-5-2018.pdf>) moves ETP Wednesday weeklies to "Tuesday EOD" and does not name SPY. **History:** the first version mapped the date on the Cboe notice alone. The first review removed the entry (claim 3, finding R4), because that notice does not name SPY and the memo was unread, and the map holds only what a primary source confirms. The round-2 design reviewer read the memo through the Wayback Machine, and the orchestrator checked its text (2026-11-09). The entry is back.
   - **2018-12-23 and 2018-12-25 stay unmapped.** OptionsDX lists them (86 and 66 rows, 5 and 3 strikes, 2018-11-30 to 12-17); no primary source shows SPY series with those dates. Neither is a third Friday, so the standard-monthly picker never selects one; a run that opened one would stop with `UnmappedExpiry`.
   - **An expiry after the last session of the calendar settles on its own date** (finding R5; the reviewer found it unasked). The first version treated any expiry after the last SPY bar in the store as an unmapped non-session. The real store's last bar is 2026-10-28 (`session_calendar`, 2026-10-30), so a holdout or DoltHub run that reached late 2026 would have stopped on every contract expiring after it. A date after the calendar is not known to be a non-session, and no run reaches it. `settle_date` takes the calendar's last date and returns the expiry itself past it.
   - The SEC, Cboe and govinfo sources were retrieved on 2026-10-30, OCC #44125 on 2026-11-09. The Cboe notice is undated; its id points to 2018-12-03. Tests: `tests/test_engine_settlement.py::test_the_d16_map_of_non_session_expiries` (2015-12-19 settles on 12-18 and 2018-12-05 on 12-04; 2018-12-23 and 2018-12-25 raise), `tests/test_contract.py::test_the_apps_settlement_map_is_the_engines` (the app's copy of the map is the same), `::test_a_run_refuses_to_open_a_contract_with_an_unmapped_non_session_expiry` and `tests/test_engine_review.py::test_an_expiry_after_the_calendar_settles_on_its_own_date`.
2. **§5, "Hedges or liquidation follow the rules in point 3": early delivery is liquidated too** (decision B9). Point 3 creates the liquidation order for shares delivered at expiry. The engine first created none for shares delivered by an early assignment, so an unhedged book held them to the end of the run. A strict xfail test found it. **Changed:** at step 10 of day *t*, when an early event is decided for an unhedged book (`hedge.mode = never`), a `share_liquidation` order is created. The shares are booked at the start of *t+1* (step 2) and sold at the *t+1* close (step 3), as for an expiry-day delivery. Test: `tests/test_engine_early.py::test_an_unhedged_book_liquidates_early_assigned_shares`.
3. **§5, an open point, not changed.** For a call with two ex-dates before expiry, the engine's lattice branch runs from *t* (τ = expiry − *t*), while the closed form measures τ from the ex-date. On test 6's inputs the boundaries are 462.60 (closed form), 464.21 (the lattice from *t*) and 462.61 (the lattice at the closed form's τ). It applies only to calls beyond about 90 days; the reference strategy never holds one.

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
