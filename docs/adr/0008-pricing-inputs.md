# ADR-0008: Pricing inputs — rate, forward, dividends, day count, European approximation, IV solver

> **Data notice.** The DoltHub figures in this document (counts, dates, quantiles and summaries, in its text and in its tables) are derived from the DoltHub database `post-no-preference/options` (<https://www.dolthub.com/repositories/post-no-preference/options>), licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), and are shared under the same licence. Changes: we aggregated it into counts, shares and quantiles, compared it with OptionsDX and ran our pricing build on it; no quote row is reproduced. The rest of this repository is MIT. See [DATA.md](../../DATA.md).

**Status:** Accepted, milestone 0.
- Implemented in M2.
- Revisited in M2 if the parity forward proves unstable near ex-dates.

## Revised after M0 review (2026-10-28)

The adversarial review (`docs/validation/00-design-research-ledger.md`, claim 8) refuted the European approximation at high rates. I re-measured it with my own CRR lattice on synthetic American chains: flat σ, a known true forward, then this ADR's procedure.

1. **The parity forward is biased low at high rates.** The early-exercise premium (EEP) of American puts lowers `F_K = K + (C − P)/DF`.
   - At S = 442.61, r = 5.22%, σ = 0.12, 29 DTE: −4.3 bp with a $1.638 dividend the next day, and −4.0 bp with no dividend.
   - At r = 5%, σ = 0.20, 60 DTE, with a dividend at 30 days: −7.4 bp. At r = 0.25%: −0.1 bp.
   - IV errors on OTM quotes reach 0.19 vol points in the first case and 0.69 in the third.
2. **"OTM early-exercise premium ≈ 0" was false at 5%.** At r = 5%, σ = 0.15, 30 DTE, the OTM put's premium in vol points is 0.33 at k = 0, 0.16 at k = −0.02, 0.06 at −0.05 and 0.01 at −0.10.
3. **The Consequences named the wrong mechanism.** The F_K dispersion appears with no dividend at all. It comes from the *put* premium at positive rates, which grows with the strike, not from ITM calls near ex-dates. The real 2023-06-15 chain shows exactly that signature: F_K falls from 442.376 (K = 436) to 441.871 (K = 450), almost monotonically (two small upticks, at K = 439 and 441), a slope of about −0.036 per strike.
4. **The bias depends on the rate regime:** about zero in 2010–21, and 0.2–0.4 vol points in 2023–26. So it lines up with the validation/holdout split.
5. **Changed:** quotes are de-Americanised with a CRR lattice before the forward and the IVs are computed (Decision 3a), and model marks add the premium back (Decision 8). On the same synthetic chains the forward error falls to 0.04–0.06 bp and the maximum IV error to 0.007 vol points at 29 DTE (0.0075–0.010 at 60 DTE, round 2, for the σ₀ method then in force). The test is test 8. *(M2 round 2, design claim 7: under the American-IV method of amendment 1 the 60-DTE case's maximum IV error is 0.0109, 0.0047, 0.0032 and 0.0029 vol points with the procedure on N = 200, 500, 1,000 and 2,000 steps, truth N = 2,000 ([report], block "the 60-day case by the procedure's step count"): the N = 200 lattice's own error. The gate is the one `tests/test_forward.py` enforces: 0.01 vol points at 29 DTE, 0.015 at 60 DTE.)*

Round 2 (`docs/validation/00-round2-ledger.md`, claim 8): the forward error is at most 0.07 bp in every case the reviewer ran, but three caveats apply. The maximum IV error at 60 DTE is 0.0075–0.010 vol points, not "at most 0.007" (the σ₀ method; under amendment 1 it is 0.0109 at N = 200, see point 5). Test 8 must pin the truth lattice at N ≥ 2,000: with an N = 200 truth it fails its own 0.01 bound at 0.029. And the fixed |k| ≤ 0.15 band edge fails the 0.02 vol-point gate at 60 DTE and beyond (0.023 at 60 DTE and σ = 15%, up to 0.127 at 90 DTE and σ = 30%); M2 decides whether to widen it or to define the band in k/(σ√τ) (§7).

## M2 review amendments (default taken 2026-10-29, owner can override)

The M2 adversarial review (`docs/validation/02-ledger.md`, round 1) refuted four parts of this ADR as written. Each change below is an amendment of the section it names; the original text stays in place, marked.

1. **§3a, de-Americanisation: the premium at the quote's own American IV, not at σ₀.** The rule "σ₀ = the Black-76 IV of the raw mid, premium at σ₀, two passes" settles on a biased answer: the raw mid of an American put contains the premium, so σ₀ is too high and so is the premium priced at it, and more passes or more steps do not remove it. On a clean synthetic 700-day chain at r = 5.22%, σ = 0.12 (the pricer's own r and dividend), it gave F −101 bp and 120 of 130 quotes `PARITY_OUTLIER`, with 20 passes or N = 1,000 (design claim 3). **Now:** each quote that needs a premium (the 10 strikes nearest K\*, both sides, and every OTM quote with a mid) gets its American IV on the lattice, σ_A with `CRR_American(σ_A) = mid` (a bracketed secant solve in [σ_floor, 5], vectorised over the date's quotes, `volbt/pricing/deam.py`), and `EEP = CRR_American(σ_A) − CRR_European(σ_A)` on the same lattice. The European-equivalent mid is `mid − EEP`, F is parity on the European-equivalent mids of the strikes nearest K\*, and the OTM IV is still the Black-76 IV of the European-equivalent mid on F. The premium does not depend on F, so this is one pass, not two. A mid outside [A(σ_floor), A(5)] has no American IV: `IV_FAIL` with the cause (`american_below_floor`, `american_above_cap`), never a NaN that reaches F. Measured (`uv run python tools/report_m2.py`, blocks "ADR-0008 test 8 and its 60-day case" and "clean long-dated American chains"): test 8 F +0.031 bp, maximum OTM IV error 0.0060 vol points; its 60-day case +0.042 bp and 0.0109. ~~The nine clean chains of 365, 540 and 700 days at σ 0.12, 0.15 and 0.20 (N = 1,000 truth) at most 0.36 bp from the true forward, with 0 `PARITY_OUTLIER`.~~ Superseded by amendment 7 (round 2): those chains were self-consistent and none was below σ 0.12.
2. **§3a, the lattice: a guard on the up-probability.** CRR's p = (e^{r dt} − d)/(u − d) leaves (0, 1) when σ < |r|√dt, and the walk then prices nonsense (σ = 10⁻⁴, 30 days, 5%: an ITM call at 10.000 against 11.7635, a NaN premium; code claim 3; `tests/test_lattice.py` pins 11.7635 now). Every lattice now prices at σ_eff = max(σ, 2|r|√dt, 10⁻⁴), where p is about 0.75; the American IV solve starts its bracket there. An expiry whose forward cannot be de-Americanised (fewer than 3 near-K\* pairs with both quotes solved) keeps the raw parity forward and says so: `method = 'parity_median5_raw'` and the smile's `SMILE_FORWARD_RAW` bit.
3. **§2, the rate's date: the last DGS3MO value dated strictly before the quote date.** DGS3MO for day t is the Treasury's ~15:30 ET bid side, posted by the Treasury around 18:00 ET and on H.15/FRED at 16:15 ET on the next business day (code claim 9b, the H.15 and Treasury methodology pages): it is not public at the 16:00 ET snapshot of t. Using it would be a small look-ahead ([report], "the rate's date": the size on 2023-03-20, a day the rate moved). *Carve-out (M2 round 2, design claim 10):* M1's cross-vendor check (`volbt.data.crossvendor`, LEARNING_LOG.md default 11) keeps its "on or before" rule: it compares two vendors' implied spots of the same snapshot, a data-quality measurement taken after the fact, not a price a strategy could act on at 16:00, so the look-ahead argument does not apply to it.
4. **§3 fallback and §4: the projected dividend amount.** "The last paid amount" overstates every March since 2009 by 10.9–47.3%, because SPY's dividends are seasonal, and "second order in the amount" fails on an ex-date eve, where the parity forward equals the carry forward at the projected amount (design claims 2 and 4). The amount is now the rule with the lowest mean absolute error in a no-look-ahead backtest over SPY's 71 ex-dates since 2009: **the same quarter a year earlier, times the trailing four quarters' sum over the four before them** (6.52%, against 11.89% for last paid, 9.17% for the same quarter a year earlier, 7.71% for the trailing four-quarter mean; [report], "dividend projection rules"). With fewer than 8 dividends paid it falls back to the last one. Projected ex-dates past the last SPY session apply NYSE's Good Friday and Juneteenth closures (2027-06-18 → 2027-06-17). *Its limits (M2 round 2, design claim 5, decision E7: kept; choosing a fifth rule after seeing the results would be snooping):* it ranks first of the four in both halves of the sample, but its edge over the trailing four-quarter mean is within noise (paired difference −1.19 points, bootstrap 95% CI [−2.88, +0.51]), and 6, 7 and 8 quarters ahead it is worse than last paid (14.19, 15.58 and 16.95% against 13.92, 14.91 and 15.17%). That is the error of the h-th dividend alone. A long expiry's lattice carries the SUM of the dividends to expiry, and on that metric the rule beats last paid at every horizon measured: a mean absolute error of 6.52, 6.34, 7.08, 9.11 and 10.62% against 11.89, 10.38, 8.53, 10.47 and 11.07% for the sum of the next 1, 2, 4, 6 and 8 dividends (the same backtest; round-3 docs reviewer, decision F13). Either way it matters only beyond 180 days, where the proposed carry-consistent rate (amendment 8) would absorb it (the round-2 reviewer's no-look-ahead backtest, re-run on 2026-10-29 with identical output).
5. **§7, the IV solver: tolerances on σ, not an absolute 10⁻⁸ on the price.** An absolute 10⁻⁸ USD tolerance accepted the clipped starting guess: any price below 10⁻⁸ came back as 0.01 after 0 iterations (code claim 2). Newton now stops when the price matches to 10⁻¹⁰ of itself and its next step is below 10⁻¹⁰ of σ; bisection halves until the bracket is under 10⁻¹⁰ of σ; an ITM price is solved on its OTM side (its time value, by parity); and an answer whose price float64 cannot resolve (~~the time value within 10⁻⁹ of the price,~~ an underflowed price, a price on a flat stretch near the upper bound, an ITM time value that the rounding of the ITM price and its bound can hide) is `IV_FAIL` "unresolved", never a number. *Round 2 (code claim 4, decision E13):* the fixed cut at 10⁻⁹ of the price is gone: it called ITM prices unresolved whose σ float64 pins (4,418 of the reviewer's 11,769). The pinned check now counts the time value's inherited rounding. σ is within 10⁻¹⁰ of the float price's root where float64 pins it that well (every solved OTM case with σ 0.01–4 and τ up to 3 years); near the upper bound and for ITM prices it is within the price's rounding over vega, at most 10⁻⁶ of σ (`tools/report_m2.py`, block "IV solver accuracy").
6. **"An error in σ₀ moves the premium only to second order" (§3a) and "the premium is second-order in the dividend amount" (§4, Consequences) are withdrawn.** Items 1 and 4 measured both errors as first-order where they matter: long tenors at high rates, and ex-date eves.

### M2 round-2 amendments (defaults taken 2026-10-29, owner can override)

The round-2 review (`docs/validation/02-ledger.md`, "Round 2") refuted parts of amendment 1 and of the story told about long expiries.

7. **§3a: an American IV counts only where the price identifies it** (code claim 2, decision E3). Deep in the money A(σ) is flat, or nearly: exercising at once is optimal at the root for a range of σ, so any σ there "matches" the mid and the premium A − E at it is not the quote's. On a clean 700-day chain at σ 0.08 amendment 1 settled 74 bp low with 198 of 244 quotes flagged (truth N = 1,000). **Now** a matched σ_A must also be identified: with dA = A(σ_A(1 + 10⁻⁶)) − A(σ_A) and dE the same for the European price, dA must exceed the solve's price tolerance (iv.py's pinned standard) and be at least half of dE (so an error in the lattice's American price moves the premium by no more than itself). An unidentified quote (`american_unidentified`) is priced at its partner's (same expiry and strike, other type) identified American IV, with `iv_american` null and `eep` the premium there; with no such partner it has no premium and stays out of the forward. The second condition was added after the measurement: with the first alone, a truth on N = 2,000 still left the σ 0.08 chain 42 bp low (σ_A 0.082–0.095 on near-flat puts whose A'/E' was 0.15–0.17). Bad inputs fail at once with their own codes (`american_no_mid`, `american_expired`, `american_bad_input`; a NaN dividend is never dropped), and `deamericanise=False` labels its forward `parity_median5_raw`. Measured on 20 clean chains, truth N = 2,000 and the procedure at N = 200 (`tests/test_forward.py`; [report], block "clean long-dated American chains"): 0 `PARITY_OUTLIER` in all 20; ~~|F error| at most 0.82 bp at r ≤ 8% and σ ≥ 0.12, 3.76 bp at σ 0.08, 7.73 bp at r 10% and 700 days~~ (it was −53 bp with 174 flagged at r 10% and 700 days), the N = 200 lattice's own error (with the truth on N = 200 every one is exact to 10⁻³ bp). *Round 3 (code claim 4, decision F3): the struck bounds were stated for a region of (r, τ, σ), and the region held a counterexample: r 8%, 700 days, σ 0.12, one dividend gave −5.94 bp with 2 `IV_FAIL` and 4 `PARITY_OUTLIER`. A bound is stated only on the chains listed (amendment 9).* On the real build the change is small: see the walkthrough, "IV solve".
8. **Proposed: draft for owner review. §2, a per-expiry carry-consistent rate beyond 180 days** (design claim 4, decision E6). Not adopted in M2: M2 keeps one DGS3MO rate. *The mechanism.* A deep-ITM quote's premium is priced at its partner's OTM IV on the lattice, whose carry forward is (S − PV(D)) e^{r τ} at DGS3MO and the projected dividends; so its European-equivalent F_K is pinned near that carry forward, and beyond 180 days `PARITY_OUTLIER` measures the gap between the lattice's carry forward and the market's parity forward, not quote quality. Flagged quotes stay in the smile (every flagged OTM quote is `in_smile`) and the flag does nothing downstream. *The proposal:* per expiry beyond 180 days, the rate r_e at which the lattice's carry forward equals the parity forward (about 3 re-pricings per long expiry). *The reviewer's measurements* (round-2 design reviewer, scratch probe `q3_carryrate.py`, 8 dates): flagged quotes fall from 3,600 to 356 of 16,768; F moves by up to +42.5 bp (at 949 days); ATM IVs move by a median 0.10–0.22 vol points on the dates with a rate gap. 82,751 of 568,856 deep-ITM call mids beyond 180 days are below S − K, which no American model prices ([report], block "deep in-the-money call mids below S − K"). *Until the owner decides,* strategies trade expiries of at most 180 days: a constraint for M4.

### M2 round-3 amendments (defaults taken 2026-10-29, owner can override)

The round-3 review (`docs/validation/02-ledger.md`, "Round 3") refuted parts of amendment 7 and of the build's provenance.

9. **§3a: the partner's American IV is solved when it is needed** (code claim 4, decision F3). Amendment 7 priced an unidentified quote's premium at its partner's American IV only if an earlier step had already solved the partner. An OTM put between S and F at a high rate is flat in σ, and its partner call, ITM on the forward and not among the 10 strikes nearest K\*, was never attempted, so the put had no IV: on a clean chain at r 8%, 700 days, σ 0.12, one dividend, 2 `IV_FAIL` and 4 `PARITY_OUTLIER` with the truth on the procedure's own lattice. **Now** `chain.solve` solves the partner then. On a 160-chain grid (r 0.25%, 5.22%, 8% and 10%; 365, 450, 540 and 700 days; σ 0.08-0.20; one or quarterly dividends; truth N = 2,000) the round-2 code failed 29 chains above half a tick (an `IV_FAIL` or a `PARITY_OUTLIER` on a mid of $0.005 or more), this one fails 1 (session scratchpad `fix4/f3/classify_pre_f3.out`, `classify.out`). Bounds hold **on the chains listed** in `tests/test_forward.py` (28, [report] block "clean long-dated American chains"), never on a region of (r, τ, σ). Two limits stay, each pinned by a test: (a) below half a tick (deep-OTM synthetic mids of $2e-5 to $5e-4, which no market quote has) a 10⁻⁶ bump of σ moves the price by less than the 10⁻⁸ USD tolerance, so such a quote is `american_unidentified`; (b) the one failing chain, r 10%, 700 days, σ 0.08, one dividend: the 456 put is flat, and its partner call (A = E) fails the identification's first test on precision alone (the bump moves its $66.10 price by 6.42e-6, under the tolerance 1e-7 × mid = 6.61e-6), so the pair is `IV_FAIL` and `PARITY_OUTLIER` (`test_the_one_chain_of_the_round_3_grid_that_still_fails_is_pinned_with_its_cause`). Fixing (b) means changing the identification test of amendment 7; not done (the walkthrough's "Not done").
10. **§7 and the smile: a WIDE quote keeps its IV but is not a smile node** (code finding N-1, decision F2). A quote is a node of its expiry's smile (`quote_iv.in_smile`) when it is valid (a mid with a bid above 0, not `STALE`, not crossed: ADR-0004 rule 1), **not `WIDE`** (ask − bid ≤ mid, ADR-0009 bit 5), OTM on F, and has an IV. A `WIDE` quote still gets its quote_iv row, its American IV, its premium and its IV, and its strike may still enter the forward's near-K\* pairs. Why: stub quotes such as bid 0.03, ask 4.84 gave IVs of 0.80-0.87 between tight neighbours at 0.33-0.38 (2014-09-15, the 11-day expiry 2014-09-26) and, through the calendar constraint (ADR-0004 amendment 2), lifted 13 later expiries. Rejected: WIDE quotes as nodes that do not anchor the constraint (the wide node still distorts its own smile). Measured: the walkthrough, "The calendar constraint at the nodes" and "WIDE quotes in the forward".
11. **Provenance is what `pricing_inputs.json` records** (code claim 6, decision F1; ADR-0001 amendment 2). A summary or an export now requires every option_quotes partition's record to equal the current code's fingerprint AND the current SHA-256 of its quotes and of the rates, dividends and spy_bars tables. The record is not signed: a hand edit of `pricing_inputs.json` is not defended against.

## Context

Every IV, greek and model mark depends on five inputs. They are listed in the order they are fixed:

- the rate;
- the forward (which carries the dividend);
- time to expiry;
- the pricing model;
- the IV solver.

### Vendor IV is inconsistent with its own quotes (measured)

On 2023-06-15, at the 29-DTE expiry:

| Strike | Mid | Vendor `[C_IV]` | Vendor `[P_IV]` |
|---|---|---|---|
| 443 call | 5.560 | 0.12062 | |
| 443 put | 6.315 | | 0.11490 |

- One strike carries two vendor IVs, 0.57 vol points apart.
- **No standard inputs reprice the call at the vendor's IV.** The call mid is 5.560:
  - r = q = 0 gives 5.813.
  - r = 5.25%, q = 1.5% gives 6.465.
- **Using a forward from put-call parity shrinks the gap, but does not remove it.** The parity forward from the 438–448 strikes is 442.00–442.36, against S = 442.61. The next day was an ex-dividend date (2023-06-16, $1.638367, State Street). The IV solved from the call mid on that forward is 0.1196.
  - The American put premium still biases that forward low. On this date F_K falls by 0.036 per strike across 436–450.
  - The median parity forward, about 442.24, is about 12 bp below the carry forward implied by DGS3MO and the dividend, 442.80. The early-exercise premium explains about 4 bp of that; the rest is **unexplained**, possibly a rate or underlying-timing mismatch. M2 measures the gap on every date.

### Vendor DTE has a daylight-saving artefact (measured)

Vendor `[DTE]` is fractional (x.04 or x.96 days) on 3,267,818 rows. Both `[QUOTE_UNIXTIME]` and `[EXPIRE_UNIX]` are 16:00 ET on every row, so the fraction is a one-hour clock shift, not real time to expiry.

## Decision

1. **Model.** Price with European Black-76 on the forward:
   - `C = DF·[F·N(d₁) − K·N(d₂)]`
   - `P = DF·[K·N(−d₂) − F·N(−d₁)]`
   - where `d₁ = (ln(F/K) + ½σ²τ)/(σ√τ)` and `d₂ = d₁ − σ√τ`.
   - Spot delta is `DF·(F/S)·N(d₁)`. Gamma, vega and theta are the analytic Black-76 greeks, with units as in ADR-0006.
2. **Rate.** One rate for all expiries: r_cc from FRED DGS3MO, converted as in ADR-0007. Discount factor `DF = e^{−r_cc·τ}`. *(M2 review amendment 3: the value dated strictly before the quote date.)*
3. **Forward: implied from put-call parity, per (date, expiry).**
   - For each strike with valid two-sided call and put quotes (ADR-0009 flags clear), compute `F_K = K + (C_mid − P_mid)/DF`.
   - Find `K*`, the strike with the smallest `|C_mid − P_mid|`.
   - `F` is the **median of `F_K` over the 5 strikes nearest `K*`**.
   - Record the dispersion (median absolute deviation / F).
   - Fallback if fewer than 3 pairs: `F = S·e^{r_cc·τ} − Σ D_i·e^{r_cc(τ−τ_i)}`, using the **last paid** dividend for each expected ex-date *(M2 review amendment 4: the projected amount)*. Flag the row `FORWARD_FALLBACK`.
   - Every strike whose `|F_K − F|/F > 0.5%` gets the flag `PARITY_OUTLIER`.

   **3a. De-Americanisation** (new after the M0 review; **steps 2–4 replaced by M2 review amendment 1**, the premium at the quote's own American IV in one pass). The steps above run on European-equivalent mids, not on raw mids.
   1. Take the raw parity forward `F⁽⁰⁾` from the raw mids, as above. It is stored as `forward_raw`.
   2. For the 10 strikes nearest `K*`, both the call and the put: let `σ₀` be the Black-76 IV of the raw mid on the current F.
   3. Compute `EEP = CRR_American(σ₀) − CRR_European(σ₀)`: the same lattice and `S_t`, `r_cc`, τ, with escrowed discrete dividends at the projected ex-dates and the last paid amounts (§4). `deam_tree_steps = 200`.
   4. The European-equivalent mid is `mid − EEP`. Recompute F_K and F from these mids, and repeat steps 2–4 once more. Two passes brought F within 0.06 bp of the true forward in every synthetic case (test 8).
   5. Store the slope of F_K against K for the expiry (`fk_slope_per_strike`) and the count of corrected quotes.

   ~~One premium evaluation per quote is enough, with no American-IV solve: an error in σ₀ moves the premium only to second order.~~ Withdrawn (M2 review amendments 1 and 6).
4. **Dividends.**
   - **Pricing never needs q.** The forward carries the dividend.
   - Dividends are used only in four places:
     - cash on ex-dates for share positions (ADR-0005);
     - the early-exercise test (ADR-0003, using the last paid amount);
     - the forward fallback;
     - the lattice that computes the early-exercise premium (§3a, §7, §8). ~~The premium is second-order in the dividend amount, so the last paid amount is enough.~~ Withdrawn: the amount is projected (M2 review amendment 4).
   - The source is yfinance SPY dividends, cross-checked against the State Street distribution file.
5. **Time to expiry.**
   - `τ = (expiry_date − quote_date).days / 365`, counted in ET calendar dates. Both stamps are 16:00 ET, so this is exact.
   - On expiration day τ = 0, and the contract is valued at intrinsic only (ADR-0003).
   - We do not use vendor `[DTE]`.
6. **Underlying.**
   - `S_t` is the SPY **unadjusted** official close. With yfinance, use `auto_adjust=False` and the `Close` column. The library's default adjustment behaviour must be verified in M1.
   - It must agree with OptionsDX `[UNDERLYING_LAST]` to within 0.10%. Otherwise the session is flagged (ADR-0009).
   - S is used for settlement, hedging and spot delta. Pricing uses F.
7. **IV solver.**
   - **Input.** Solve from the mid, using the OTM side only: puts for K < F, calls for K ≥ F. The smile uses the same convention (ADR-0004).
   - **De-Americanise first.** For every OTM quote with |k| ≤ `deam_band = 0.15`, subtract the EEP as in §3a, at that quote's own σ₀ and the final F, and store it in `quote_iv.eep`. Beyond the band the premium was at most 0.014 vol points (r = 5%, σ = 0.15, 30 DTE). The M2 pricing gate re-checks the band edge on the highest-rate date of each year, for every tenor in use, and widens the band if the edge exceeds 0.02 vol points. A fixed |k| ≤ 0.15 already fails that gate at 60 DTE and beyond (0.023 vol points at 60 DTE and σ = 15%; up to 0.127 at 90 DTE and σ = 30%), so M2 considers a band in k/(σ√τ) instead of in k, and decides it there. *(M2 decided: no band, every OTM quote is corrected (milestone-2 walkthrough, decision 1), at its own American IV (M2 review amendment 1).)*
   - **Bounds check first.** A call needs `DF·max(F−K, 0) < C < DF·F`, and a put needs `DF·max(K−F, 0) < P < DF·K`. A price outside these bounds is flagged `IV_FAIL`, and no IV is produced.
   - **Newton–Raphson on σ.**
     - Start from the Brenner–Subrahmanyam guess `σ₀ = √(2π/τ)·C/(DF·F)`, clipped to [0.01, 3].
     - Stop when `|price error| < 1e-8` or after 50 iterations. *(M2 review amendment 5: relative tolerances on the price and on σ, and "unresolved" where float64 cannot pin σ.)*
   - **Bisection fallback** on [1e-4, 5.0]. It runs when Newton leaves the bracket, when vega < 1e-8, or when Newton fails to converge.
8. **American SPY options on a European model.**
   - **The surface is European-equivalent.** Its IVs come from de-Americanised OTM mids (§7), so Black-76 at a surface IV gives the *European* price.
   - **Model marks add the premium back.** A model mark (ADR-0004 rules 3 and 4) of a contract with |k| ≤ 0.15 is the CRR American price at the surface IV, `exercise_tree_steps = 500`. Beyond the band it is Black-76. *(Round 2, decision E8: from milestone 3 a model mark is the CRR American price at every |k| (decided for milestone 3), as M2 de-Americanises every OTM quote with no band.)*
   - Without that step, a short put marked off the surface in the high-rate holdout would carry too small a liability: by $14.29 per contract for an ATM 30-DTE put at r = 5%, σ = 0.15.
   - **Greeks stay Black-76** at the mark IV (ADR-0006 units). They are an approximation for near-ATM puts at high rates.
   - Early exercise itself is decided by the rules in ADR-0003, on the same lattice.

## Alternatives considered

- **Vendor IV and greeks.** Rejected. They are internally inconsistent (the 0.57-vol-point call/put gap above), and vendor theta does not reconcile (ADR-0004).
- **S·e^{(r−q)τ} with a continuous dividend yield q.** Rejected. SPY's dividend is discrete and quarterly, and it falls on expiry Fridays, so a continuous yield misprices the forward by about one dividend across an ex-date. It would also need a forecast of q, which brings look-ahead risk if realised dividends are used.
- **Discrete dividends with an explicit dividend schedule.** Rejected as the primary method and kept only as the fallback. It needs future dividend amounts, whereas the parity forward reads the market's own expectation.
- **An American pricer for every quote, with American IVs throughout.** Rejected. We use the lattice only for the premium ~~, inside a band (§3a, §7, §8)~~ (of every OTM quote with a mid and of the near-K\* quotes, with no |k| band since M2: amendment 1 and the walkthrough's decision 1; model marks at every |k| from milestone 3, §8), and keep Black-76 everywhere else.
  - The full version would solve an American IV for every quote, an iterative solve with several lattice evaluations each.
  - It would make the greeks lattice greeks too, which complicates the attribution (ADR-0005).
  - The premium-only version removes the measured bias, to 0.007 vol points at 29 DTE (0.0075–0.010 at 60 DTE under the σ₀ method; 0.0109 under amendment 1 at N = 200, see Revised point 5).
  - It would win for deep-ITM or long-dated books.
- **No correction, documented as a known bias** (the M0 design). Rejected after the M0 review. The bias is 4–7 bp in the forward and 0.2–0.7 vol points in the IVs at 5% rates, and about zero at 0.25%. A bias that switches on with the rate regime would contaminate the validation-versus-holdout comparison.
- **Fitting F as a free parameter of the smile** instead of from parity. Rejected: it trades a known, removable bias for an identification problem between the forward and the skew.
- **A term structure of rates** (DGS1MO, DGS6MO, DGS1). Rejected for simplicity. ~~r enters only through DF, because the forward comes from parity.~~ *Wrong (M2 round 3, docs claim 2):* the lattice's carry runs at r, so r moves the premium and the European-equivalent F_K beyond 180 days (amendment 8), and the rate's date moved forwards within 60 days by up to 0.53 bp (walkthrough, "The rate's date"). A 1% rate error on a 30-day option changes DF by about 8 bp. This would win for LEAPS.
- **Trading-day time (τ in /252).** Rejected for pricing. Vendor gamma and vega reconcile with calendar time to within 1% (ADR-0004), and the VIX uses calendar time.
  - The weekend effect (less variance over a weekend than over three weekdays) is a signal-design issue for comparing IV with RV in M4. It is not a pricing input.

## Consequences and biases

- **The parity forward needs both sides quoted near the money.** DoltHub lists about 17–27 strikes per expiry, roughly half on each side of the money, which is enough for the 10 near-K\* pairs of §3a. If a day has no valid pair, it falls back to the dividend schedule, with a flag.
- **What moves `F_K` across strikes.** Mainly the American *put* premium at positive rates. It grows with the strike, so raw `F_K` falls with K, with no dividend needed.
  - Near ex-dates, the early-exercise value of ITM calls adds to that for low strikes.
  - De-Americanisation (§3a) removes the first effect, and with the dividend schedule most of the second.
  - On 2023-06-15 the raw `F_K` values across strikes 438–448 spanned 0.364, which is 0.082% of F, falling by 0.036 per strike.
  - Any borrow cost or snapshot-timing mismatch is still absorbed into F, and is not removed. See the unexplained 8 bp in Context.
- **The correction needs the dividend schedule** (projected amounts on projected ex-dates, M2 review amendment 4). ~~An error in the amount moves the premium only to second order.~~ Withdrawn (amendment 6): on an ex-date eve the amount sets the forward.
- **Build cost.** One lattice pair at N = 200 takes a few ms in numpy, and a 2022 date has about 2,300 OTM quotes within |k| ≤ 0.15. Unvectorised, that would be several hours for 2010–2023. This is an estimate, not measured end to end. M2 vectorises across strikes. ~~The pricing gate checks the premium against N = 2,000 to within 0.01 vol points.~~ *(Round 2, design claim 7: the gate is what `tests/test_forward.py` enforces, a truth on N = 2,000 and the procedure on N = 200: 0.01 vol points at 29 DTE, 0.015 at 60 DTE, and the clean long-dated chains' per-case bounds of amendment 7. M2 measured the build: [report], block "build time".)* Any synthetic "truth" chain used to test this must itself be built at N ≥ 2,000 (test 8).
- **One rate for every expiry.** ~~This gives a small level error in DF and none in F.~~ *Wrong (M2 round 2, design claim 9):* F comes from parity on European-equivalent mids, and the premiums taken off them are priced on a lattice whose carry runs at the one rate, so the rate moves F too: a one-day change of DGS3MO (2023-03-20) moves forwards within 60 days by up to 0.53 bp ([report], "the rate's date"), and the proposed carry-consistent rate (amendment 8) moves long-dated forwards by up to +42.5 bp.

## How we will test it

1. **Rate.** DGS3MO = 5.25 → r_cc = 0.0521594. DGS3MO = 0.05 → r_cc = 0.000500.
2. **Parity forward.**
   - Inputs: K = 443, C_mid = 5.560, P_mid = 6.315, τ = 29/365, r_cc = 0.0521594.
   - Then DF = 0.995864, and F = 443 − 0.755/0.995864 = **442.2419**.
3. **Round trip.**
   - Inputs: F = S = K = 400, σ = 0.20, τ = 30/365, r = 0.
   - The call price is **9.148603**. Solving that price back gives σ = 0.200000 (tolerance 1e-8).
   - A 5,000-case property test runs the same round trip over σ ∈ [0.05, 2], k ∈ [−0.5, 0.3] and τ ∈ [1/365, 1]. It must converge every time, using bisection when Newton fails.
4. **Bounds.** A call priced at DF·F + 0.01 gives `IV_FAIL`, not an exception and not an IV of 5.0.
5. **Day count across DST.**
   - Quote 2024-03-08, expiry 2024-03-15 → τ = 7/365.
   - The vendor-style UNIX difference is 6.9583 days, because DST started on 03-10. The test asserts we use 7.
6. **Expiry day.** τ = 0 → the price equals intrinsic, and the IV solver is not called.
7. **Fallback forward.**
   - Inputs: S = 450, r_cc = 5%, τ = 30/365, one ex-date at τ₁ = 10/365, last dividend 1.80.
   - F = 450·e^{0.05·30/365} − 1.80·e^{0.05·20/365} = 451.853 − 1.805 = **450.048**.
8. **De-Americanisation removes the forward bias (synthetic American chain).**
   - Inputs: CRR American prices at flat σ = 0.12 for strikes S ± 25, with S = 442.61, r = 5.22%, τ = 29/365 and D = 1.638367 at 1 day. The true forward is 442.8031. **The truth lattice is pinned at N ≥ 2,000 steps** (the procedure under test keeps `deam_tree_steps = 200`). An N = 200 truth lattice makes the test fail its own 0.01 bound, at a maximum IV error of 0.029.
   - **With §3a:** F is within 0.1 bp of 442.8031 (measured 442.8004, −0.06 bp), and every OTM IV is within 0.01 vol points of 0.12 (measured maximum 0.006).
   - **Mutant check:** with §3a disabled, the same test must fail. Measured: F = 442.6122 (−4.3 bp), maximum IV error 0.19 vol points.
   - Repeat at r = 0.25%: both versions pass, and the correction changes F by less than 0.1 bp.
9. **Model marks are American.** Put, S = K = 450, r = 5%, σ = 0.15 (surface IV), τ = 30/365, no dividend. Its rule-3 mark is the N = 500 CRR price, **6.9574**, not the Black-76 price 6.8162.
