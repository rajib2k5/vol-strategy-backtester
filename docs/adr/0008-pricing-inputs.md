# ADR-0008: Pricing inputs — rate, forward, dividends, day count, European approximation, IV solver

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
5. **Changed:** quotes are de-Americanised with a CRR lattice before the forward and the IVs are computed (Decision 3a), and model marks add the premium back (Decision 8). On the same synthetic chains the forward error falls to 0.04–0.06 bp and the maximum IV error to 0.007 vol points at 29 DTE (0.0075–0.010 at 60 DTE, round 2). The test is test 8.

Round 2 (`docs/validation/00-round2-ledger.md`, claim 8): the forward error is at most 0.07 bp in every case the reviewer ran, but three caveats apply. The maximum IV error at 60 DTE is 0.0075–0.010 vol points, not "at most 0.007". Test 8 must pin the truth lattice at N ≥ 2,000: with an N = 200 truth it fails its own 0.01 bound at 0.029. And the fixed |k| ≤ 0.15 band edge fails the 0.02 vol-point gate at 60 DTE and beyond (0.023 at 60 DTE and σ = 15%, up to 0.127 at 90 DTE and σ = 30%); M2 decides whether to widen it or to define the band in k/(σ√τ) (§7).

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
2. **Rate.** One rate for all expiries: r_cc from FRED DGS3MO, converted as in ADR-0007. Discount factor `DF = e^{−r_cc·τ}`.
3. **Forward: implied from put-call parity, per (date, expiry).**
   - For each strike with valid two-sided call and put quotes (ADR-0009 flags clear), compute `F_K = K + (C_mid − P_mid)/DF`.
   - Find `K*`, the strike with the smallest `|C_mid − P_mid|`.
   - `F` is the **median of `F_K` over the 5 strikes nearest `K*`**.
   - Record the dispersion (median absolute deviation / F).
   - Fallback if fewer than 3 pairs: `F = S·e^{r_cc·τ} − Σ D_i·e^{r_cc(τ−τ_i)}`, using the **last paid** dividend for each expected ex-date. Flag the row `FORWARD_FALLBACK`.
   - Every strike whose `|F_K − F|/F > 0.5%` gets the flag `PARITY_OUTLIER`.

   **3a. De-Americanisation** (new after the M0 review). The steps above run on European-equivalent mids, not on raw mids.
   1. Take the raw parity forward `F⁽⁰⁾` from the raw mids, as above. It is stored as `forward_raw`.
   2. For the 10 strikes nearest `K*`, both the call and the put: let `σ₀` be the Black-76 IV of the raw mid on the current F.
   3. Compute `EEP = CRR_American(σ₀) − CRR_European(σ₀)`: the same lattice and `S_t`, `r_cc`, τ, with escrowed discrete dividends at the projected ex-dates and the last paid amounts (§4). `deam_tree_steps = 200`.
   4. The European-equivalent mid is `mid − EEP`. Recompute F_K and F from these mids, and repeat steps 2–4 once more. Two passes brought F within 0.06 bp of the true forward in every synthetic case (test 8).
   5. Store the slope of F_K against K for the expiry (`fk_slope_per_strike`) and the count of corrected quotes.

   One premium evaluation per quote is enough, with no American-IV solve: an error in σ₀ moves the premium only to second order.
4. **Dividends.**
   - **Pricing never needs q.** The forward carries the dividend.
   - Dividends are used only in four places:
     - cash on ex-dates for share positions (ADR-0005);
     - the early-exercise test (ADR-0003, using the last paid amount);
     - the forward fallback;
     - the lattice that computes the early-exercise premium (§3a, §7, §8). The premium is second-order in the dividend amount, so the last paid amount is enough.
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
   - **De-Americanise first.** For every OTM quote with |k| ≤ `deam_band = 0.15`, subtract the EEP as in §3a, at that quote's own σ₀ and the final F, and store it in `quote_iv.eep`. Beyond the band the premium was at most 0.014 vol points (r = 5%, σ = 0.15, 30 DTE). The M2 pricing gate re-checks the band edge on the highest-rate date of each year, for every tenor in use, and widens the band if the edge exceeds 0.02 vol points. A fixed |k| ≤ 0.15 already fails that gate at 60 DTE and beyond (0.023 vol points at 60 DTE and σ = 15%; up to 0.127 at 90 DTE and σ = 30%), so M2 considers a band in k/(σ√τ) instead of in k, and decides it there.
   - **Bounds check first.** A call needs `DF·max(F−K, 0) < C < DF·F`, and a put needs `DF·max(K−F, 0) < P < DF·K`. A price outside these bounds is flagged `IV_FAIL`, and no IV is produced.
   - **Newton–Raphson on σ.**
     - Start from the Brenner–Subrahmanyam guess `σ₀ = √(2π/τ)·C/(DF·F)`, clipped to [0.01, 3].
     - Stop when `|price error| < 1e-8` or after 50 iterations.
   - **Bisection fallback** on [1e-4, 5.0]. It runs when Newton leaves the bracket, when vega < 1e-8, or when Newton fails to converge.
8. **American SPY options on a European model.**
   - **The surface is European-equivalent.** Its IVs come from de-Americanised OTM mids (§7), so Black-76 at a surface IV gives the *European* price.
   - **Model marks add the premium back.** A model mark (ADR-0004 rules 3 and 4) of a contract with |k| ≤ 0.15 is the CRR American price at the surface IV, `exercise_tree_steps = 500`. Beyond the band it is Black-76.
   - Without that step, a short put marked off the surface in the high-rate holdout would carry too small a liability: by $14.29 per contract for an ATM 30-DTE put at r = 5%, σ = 0.15.
   - **Greeks stay Black-76** at the mark IV (ADR-0006 units). They are an approximation for near-ATM puts at high rates.
   - Early exercise itself is decided by the rules in ADR-0003, on the same lattice.

## Alternatives considered

- **Vendor IV and greeks.** Rejected. They are internally inconsistent (the 0.57-vol-point call/put gap above), and vendor theta does not reconcile (ADR-0004).
- **S·e^{(r−q)τ} with a continuous dividend yield q.** Rejected. SPY's dividend is discrete and quarterly, and it falls on expiry Fridays, so a continuous yield misprices the forward by about one dividend across an ex-date. It would also need a forecast of q, which brings look-ahead risk if realised dividends are used.
- **Discrete dividends with an explicit dividend schedule.** Rejected as the primary method and kept only as the fallback. It needs future dividend amounts, whereas the parity forward reads the market's own expectation.
- **An American pricer for every quote, with American IVs throughout.** Rejected. We use the lattice only for the premium, inside a band (§3a, §7, §8), and keep Black-76 everywhere else.
  - The full version would solve an American IV for every quote, an iterative solve with several lattice evaluations each.
  - It would make the greeks lattice greeks too, which complicates the attribution (ADR-0005).
  - The premium-only version removes the measured bias, to 0.007 vol points at 29 DTE (0.0075–0.010 at 60 DTE).
  - It would win for deep-ITM or long-dated books.
- **No correction, documented as a known bias** (the M0 design). Rejected after the M0 review. The bias is 4–7 bp in the forward and 0.2–0.7 vol points in the IVs at 5% rates, and about zero at 0.25%. A bias that switches on with the rate regime would contaminate the validation-versus-holdout comparison.
- **Fitting F as a free parameter of the smile** instead of from parity. Rejected: it trades a known, removable bias for an identification problem between the forward and the skew.
- **A term structure of rates** (DGS1MO, DGS6MO, DGS1). Rejected for simplicity. r enters only through DF, because the forward comes from parity. A 1% rate error on a 30-day option changes DF by about 8 bp. This would win for LEAPS.
- **Trading-day time (τ in /252).** Rejected for pricing. Vendor gamma and vega reconcile with calendar time to within 1% (ADR-0004), and the VIX uses calendar time.
  - The weekend effect (less variance over a weekend than over three weekdays) is a signal-design issue for comparing IV with RV in M4. It is not a pricing input.

## Consequences and biases

- **The parity forward needs both sides quoted near the money.** DoltHub lists about 17–27 strikes per expiry, roughly half on each side of the money, which is enough for the 10 near-K\* pairs of §3a. If a day has no valid pair, it falls back to the dividend schedule, with a flag.
- **What moves `F_K` across strikes.** Mainly the American *put* premium at positive rates. It grows with the strike, so raw `F_K` falls with K, with no dividend needed.
  - Near ex-dates, the early-exercise value of ITM calls adds to that for low strikes.
  - De-Americanisation (§3a) removes the first effect, and with the dividend schedule most of the second.
  - On 2023-06-15 the raw `F_K` values across strikes 438–448 spanned 0.364, which is 0.082% of F, falling by 0.036 per strike.
  - Any borrow cost or snapshot-timing mismatch is still absorbed into F, and is not removed. See the unexplained 8 bp in Context.
- **The correction needs the dividend schedule** (last paid amounts on projected ex-dates). An error in the amount moves the premium only to second order.
- **Build cost.** One lattice pair at N = 200 takes a few ms in numpy, and a 2022 date has about 2,300 OTM quotes within |k| ≤ 0.15. Unvectorised, that would be several hours for 2010–2023. This is an estimate, not measured end to end. M2 vectorises across strikes, and the pricing gate checks the premium against N = 2,000 to within 0.01 vol points (N = 200 differs from N = 2,000 by 0.004 in price, about 0.007 vol points, at the ATM test point). Any synthetic "truth" chain used to test this must itself be built at N ≥ 2,000 (test 8).
- **One rate for every expiry.** This gives a small level error in DF and none in F.

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
