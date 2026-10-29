# ADR-0004: Mark-to-market

**Status:** Accepted at milestone 0. Implemented in M3, using the surface built in M2. To be revisited in M6 once the share of model-marked NAV has been measured on both datasets.

## Revised after M0 review (2026-10-28)

The adversarial review (`docs/validation/00-design-research-ledger.md`, claims 3 and 9) found that rule 3 left two cases undefined or badly defined, and that two DoltHub facts were wrong. All four were re-measured, on OptionsDX masked by DoltHub's own 2022–23 sampling (ADR-0009 §4).

1. **Flat extrapolation beyond the last strike was biased low.** On a DoltHub-like 19-strike grid, holding the IV flat beyond the end missed the far-strike IVs by a median 7.0 vol points (p90 34.6, mean −13.2). It under-marks far wings, which flatters short wings. **Changed:** total variance is extended linearly, with its end slope clipped to Lee's moment bound, and the mark is flagged. On the same test the median error falls to 1.2 vol points (0.46 within |k| ≤ 0.40).
2. **There was no rule below the front expiry.** DoltHub lists no expiry under 10 DTE, so a 7-DTE exit has no bracketing expiry. **Changed:** IV is held constant along k/√τ from the nearest listed expiry, and the mark is flagged. Measured median error 1.2 vol points, mean +0.4. Reading the front smile at the same k, as the reviewer's probe did, measured 1.9, mean −2.2, on the same sample; the reviewer's 1.02 was for |k| ≤ 0.05 only.
3. **The cross-expiry fallback is the usual case out of sample, not a rare one.** A DoltHub expiry is listed on only about half the sessions between its first and last listing. On masked 2022–23 data, 56% of 30-DTE and 75% of 45-DTE marks come from it, with a median error of 0.24 vol points. That is six times the in-grid error. The sample pools two regimes (listing share 0.286 in 2022, 0.50–0.54 from 2023; ADR-0009), so the table below is re-reported for 2022 and 2023 separately, and 2023 is the closer analogue of the holdout. **Changed:** it is now triggered when the contract's own expiry is absent, not only when it is thin, and it is flagged.
4. **Facts.** The 520 put was quoted on 2 of **14** sessions, not 8. DoltHub has Tue/Thu sessions only from **Oct**-2024.
5. **Knock-on from ADR-0008.** The surface is now built from de-Americanised quotes. Rules 3 and 4 therefore price near-the-money contracts with the American lattice, so that a model mark matches the quote marks it replaces.

Round 2 (`docs/validation/00-round2-ledger.md`, claim 11): the error figures above reproduce, but the masked 2022–23 sample pools two expiry-persistence regimes (ADR-0009, Round 2), so they describe the holdout only as far as 2023 resembles it. They are re-reported by year.

## Context

The daily marks are the only input to NAV, greeks, stops, margin and every risk-adjusted metric. A mark that does not move when it should makes NAV look smoother than it really is. That inflates Sharpe and hides drawdowns, and it does so most in stress, when quotes go bad.

### Quote quality in OptionsDX

Measured over all 9,468,584 rows, 2010–2023.

| Problem | Calls | Puts |
|---|---|---|
| `bid = 0` | 745,993 (7.9%) | 632,224 |
| `bid > ask` (crossed) | 9,435 | 24,046 |
| Null bid/ask | 11,721 | not measured |
| `bid = ask > 0` (locked) | 96,009 | not measured |
| Null vendor IV | 588,461 | 472,386 |

In 2019, puts with `K/S < 0.80` had `bid = 0` on 22.1% of rows. At `K/S ≥ 0.97` the share was 0.6%.

### Vendor IVs and greeks

The vendor's IV and greeks are not reliable enough to mark with. On 2023-06-15, for the 443 strike with 29 DTE:

- **Call and put IVs disagree.** The vendor shows `[C_IV]` about 0.12 and `[P_IV]` about 0.11, a gap of about 0.6 vol points at the same strike.
- **Our recompute.** Taking the forward implied by put-call parity and solving from the mid gives 0.1196.
- **Vendor theta does not reconcile.** The vendor shows −0.0914 per day. Black-Scholes-Merton (BSM) on calendar days gives between −0.104 (r = q = 0) and −0.126 (r = 5.25%, q = 1.5%). Vendor gamma and vega match BSM to within 1%.

### DoltHub

In DoltHub a held contract is usually **not quoted** on later days (measured, ADR-0009).
- **Strikes.** Each listed expiry gets about 17–27 strikes, a median of 20–24 in 2024–25, on a grid about 2.2% of spot apart. The grid is re-centred every day.
- **Example.** The 2025-04-30 520 put appears on only 2 of the 14 sessions between 2025-03-31 and 2025-04-17.
- **Expiries come and go.** DoltHub lists 3–4 expiries a day, at about 13, 29 and 51–56 DTE. An expiry first listed at 25 DTE or more appears on a median 50% of the sessions between its first and last listing.
- **Nothing under 10 DTE is ever listed.**

### Snapshot timing

OptionsDX quotes are stamped 16:00 ET, the same instant as `[UNDERLYING_LAST]`. Neither dataset contains pre-open quotes, which avoids the Aug-2024 pre-open quote-widening problem.

## Decision

Each lot gets exactly one mark per session. The mark is chosen by the first rule below that applies, and its `mark_source` is recorded.

| # | Condition on day *t* (ADR-0009 flags) | Mark | `mark_source` |
|---|---|---|---|
| 0 | Contract expires at *t* | Intrinsic value at `S_set` (ADR-0003) | `INTRINSIC` |
| 1 | `0 < bid ≤ ask`, not `STALE`, not `CROSSED` | `(bid+ask)/2` | `QUOTE_MID` |
| 2 | `bid = 0 < ask` | `ask/2`, which is still the mid | `ZERO_BID_MID` |
| 3 | Crossed, one-sided (bid or ask null), stale, or missing, and the day has a surface | Black-76 at the day's surface IV for this contract (method below). For \|k\| ≤ 0.15 it is the CRR American price at that IV, because the surface is European-equivalent (ADR-0008 §8) | `SURFACE_MODEL` |
| 4 | No snapshot on day *t* (missing session; DoltHub Tue/Thu before Oct-2024) | As rule 3, at the **previous** surface's IV at the same log-moneyness, re-priced at today's spot and forward ("sticky moneyness") | `STALE_SURFACE` |

**How the surface IV is found.** Each step that is not a plain interpolation sets a bit in `position_marks.mark_flags`.

1. **Inputs.** Use the valid OTM quotes: puts with K < F, calls with K ≥ F. Take their implied vols, recomputed from de-Americanised mids (ADR-0008).
2. **Own expiry, inside the quoted strikes.** If the contract's expiry has at least 5 valid OTM quotes, interpolate total variance `w = σ²τ` linearly in log-moneyness `k = ln(K/F)` between neighbouring valid quotes.
3. **Own expiry, beyond the last quoted strike** (flag `SURFACE_EXTRAP_STRIKE`).
   - Extend `w` linearly in k, using the slope of the two outermost nodes on that side.
   - Clip the slope so that `w` neither falls as |k| grows nor rises faster than 2|k|. That is Roger Lee's (2004) moment bound for the wings.
   - Never hold the IV flat.
4. **Own expiry absent or thin, with bracketing expiries** (flag `SURFACE_CROSS_EXPIRY`).
   - Interpolate across expiries: linear in `w` at fixed k, between the nearest listed expiry on each side. Each of them is evaluated by steps 2–3.
   - k uses the contract expiry's fallback forward (ADR-0008).
5. **No bracketing expiry** (flag `SURFACE_EXTRAP_TENOR`).
   - This happens when the contract is shorter than the shortest listed expiry, for example every DoltHub contract under 10 DTE, or longer than the longest.
   - Hold the IV constant along standardised moneyness k/√τ, from the nearest listed expiry: `σ(τ, k) = σ_near(k·√(τ_near/τ))`.
   - The smile steepens as 1/√τ, so evaluating the near smile at the same k instead would understate short-dated wing IVs.

**Measured errors of these steps.** OptionsDX 2022–23, masked to the (expiry, strike) pairs DoltHub listed on 73 of its sessions; |k| ≤ 0.15; "truth" is the IV from the contract's own full-chain quotes.

| Step | Share of held-contract marks | Median \|error\| | p90 \|error\| | Mean error |
|---|---|---|---|---|
| 2, own expiry, in-grid | 97% at 14 DTE; 44% at 30 DTE; 25% at 45 DTE | 0.04 vol pts | 0.16 | +0.04 |
| 3, beyond the grid | 0–2% | 0.19 (flat: 0.67) | 0.75 (flat: 1.68) | −0.26 |
| 4, cross-expiry | 100% at 21 DTE; 56% at 30 DTE; 75% at 45 DTE | 0.24 | 0.68 | 0.00 |
| 5, below the front expiry | 100% at 7 DTE | 1.21 (same-k: 1.88) | 3.11 (same-k: 6.41) | +0.44 (same-k: −2.17) |

The 7-DTE error is mostly the term-structure level between 7 and about 14 DTE, which DoltHub does not quote, so no extrapolation rule can remove it. It is the main reason ADR-0003 has M4 choose `exit_dte` with the masked surface gap in view.

### Feeding NAV and greeks

- **Two NAV series.**
  - `NAV_mid = cash + shares·S_t + Σ qty·100·mark`. This one drives returns, Sharpe and margin.
  - `NAV_liq` values longs at the bid and shorts at the ask, using rule 3's model price ± `h_model` when there is no valid side.
  - `NAV_mid − NAV_liq` is the spread haircut. Drawdowns are reported on both series.
- **Greeks.** Greeks come from our own Black-76 at the mark's IV, using the IV solved from the mid for rules 1 and 2 and the surface IV for rules 3 and 4. We never use vendor greeks.
  - When the mid is below the no-arbitrage bound and the IV cannot be solved, the mark stays the mid, but the greeks use the surface IV, and the row is flagged `IV_FAIL`.

### Surfacing bad marks

- **Per lot.** `position_marks` stores, for each lot and day, the `mark_source` and the quote's `quality_flags`.
- **Per day.** `daily_pnl.share_nav_model_marked` is the share of gross option value marked by rules 3 or 4. If it exceeds **20%**, the day gets `mark_quality = DEGRADED`. The app shades those days.
- **Attribution residual check.** Each day's P&L is split into delta, gamma, vega and theta (ADR-0005). If the residual, `|pnl_residual| > max($50, 10% of |pnl_total|)`, the lot is flagged `ATTRIBUTION_BREAK`. A large unexplained residual means either a bad mark or a bug.
- **Mark jumps.** A mark that moves more than 50% in a day while |ΔS/S| < 1% and |Δσ_ATM| < 2 vol points is flagged `MARK_JUMP`. It is still used.

## Alternatives considered

- **Carry forward the last valid mid, with a stale flag.** Rejected as a fallback.
  - The mark ignores both delta and vega. On a −5% day, an ATM put carried at yesterday's price misstates the P&L by about |Δ|·ΔS ≈ 0.5 × 5% × S per share.
  - It smooths NAV in exactly the sessions where quotes fail, which are stress sessions.
  - Carrying the **IV** forward at the same moneyness (rule 4) keeps the delta and vega response. That is the version we adopted.
- **Mark at the last trade (`[C_LAST]`).** Rejected. The last trade can be hours old, it is absent in DoltHub, and it is not synchronous with the 16:00 underlying.
- **Mark at the conservative side** (bid for longs, ask for shorts) **as the main NAV.** Rejected as the main NAV, because it charges the spread every day rather than once. We still report it, as `NAV_liq`.
- **Mark from vendor IV.** Rejected. It does not reprice the mid under any one forward: the call and put IVs differ by 0.57 vol points at the same strike.
- **An SVI or SSVI smile fit for rule 3.** Not rejected for good, only deferred. It is smoother and arbitrage-aware, but it can fail to converge on thin smiles (DoltHub has about 17–27 strikes per expiry), and a failed fit would itself need a fallback. Piecewise-linear total variance is exact at the quoted strikes. SVI wins if the M6 attribution residual on model-marked lots turns out materially worse than on quote-marked lots.

## Consequences and biases

- **Zero-bid mids sit above the true expected value.** Marking a zero-bid long at `ask/2` overstates it slightly, and the same mark understates a short's liability. The amounts are small, since asks are typically $0.01–0.05, and `NAV_liq` bounds them.
- **Model marks inherit the surface's error.** On DoltHub most marks will be `SURFACE_MODEL`, so out-of-sample NAV is partly a model output.
  - Most of those marks also carry `SURFACE_CROSS_EXPIRY`, and every 7-DTE exit carries `SURFACE_EXTRAP_TENOR`. The errors are in the table above.
  - ADR-0009 §4 measures the effect on strategy results, on OptionsDX masked by DoltHub's own sampling, separately for 2020–22 and 2023.
- **Rule 4 freezes the smile on missing days.** It misses vol moves on those days, so vega P&L arrives a day late. That is optimistic for short vega when vol rises on a missing day. The flag makes it visible.

## How we will test it

1. **Quote mid.** bid 1.00 / ask 1.20 → mark 1.10, `QUOTE_MID`.
2. **Zero bid.** bid 0 / ask 0.04 → mark 0.02, `ZERO_BID_MID`. For one long contract, `NAV_liq` uses 0. For one short contract it uses 0.04.
3. **Surface mark.** A crossed quote, 1.10 / 1.00, with surface IV 0.20 at the strike, F = S = 400, K = 400, τ = 30/365, r = 0 → mark **9.1486**, `SURFACE_MODEL`.
4. **Carry-forward rejected.** The same put is missing on a day when S falls from 400 to 380, with σ unchanged. The mark must increase toward the Black-76 put value at S = 380. A test fails if the mark equals the previous day's.
5. **Interpolation.** Valid OTM IVs are 0.22 at k = −0.05 and 0.18 at k = 0.00, with τ = 0.1. At k = −0.025 the interpolated `w` is 0.5 × (0.22² + 0.18²) × 0.1 = 0.004040, so σ = 0.2010.
6. **Degraded day.** Gross option value is $100k, and $25k of it is marked by rule 3, a share of 25% > 20% → `DEGRADED`.
7. **Stale surface.** No snapshot on Tue 2024-03-12 (DoltHub) → every lot is marked `STALE_SURFACE` from the 2024-03-11 smile, re-priced at the 03-12 SPY close.
8. **Greeks come from our model.** A fixture row has vendor delta 0.40, and its Black-76 call delta at the recomputed IV is 0.5114 (S = F = 400, K = 400, σ = 0.20, τ = 30/365, r = 0). The row stores 0.5114 in `position_marks.delta`.
9. **Strike extrapolation is not flat.** Nodes: IV 0.22 at k = −0.10 and 0.20 at k = −0.05, with τ = 0.1. At k = −0.15 the slope in |k| is 0.0168, inside [0, 2], so `w` = 0.00568 and σ = **0.2383**. A flat rule would give 0.22. The mark carries `SURFACE_EXTRAP_STRIKE`.
10. **Tenor extrapolation along k/√τ.** The nearest listed expiry has τ₁ = 14/365, with nodes IV 0.22 at k = −0.05 and 0.18 at k = 0. For a contract with τ = 7/365 and k = −0.025, the smile is read at k′ = −0.025·√2 = −0.03536, giving σ = **0.2091**. Reading it at the same k would give 0.2010. The mark carries `SURFACE_EXTRAP_TENOR`.
11. **Cross-expiry when the own expiry is absent.** A held 30-DTE contract whose expiry DoltHub does not list that day, with listed expiries at 14 and 51 DTE, is marked by linear `w` between them at fixed k, and carries `SURFACE_CROSS_EXPIRY`. It must not raise and must not use a stale mark.
