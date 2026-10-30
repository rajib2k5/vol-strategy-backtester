# ADR-0004: Mark-to-market

> **Data notice.** The DoltHub figures in this document (counts, dates, quantiles and summaries, in its text and in its tables) are derived from the DoltHub database `post-no-preference/options` (<https://www.dolthub.com/repositories/post-no-preference/options>), licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), and are shared under the same licence. Changes: we aggregated it into counts, shares and quantiles, compared it with OptionsDX and ran our pricing build on it; no quote row is reproduced. The rest of this repository is MIT. See [DATA.md](../../DATA.md).

**Status:** Accepted at milestone 0. Implemented in M3, using the surface built in M2. To be revisited in M6 once the share of model-marked NAV has been measured on both datasets.

## Revised after M0 review (2026-10-28)

The adversarial review (`docs/validation/00-design-research-ledger.md`, claims 3 and 9) found that rule 3 left two cases undefined or badly defined, and that two DoltHub facts were wrong. All four were re-measured, on OptionsDX masked by DoltHub's own 2022–23 sampling (ADR-0009 §4).

1. **Flat extrapolation beyond the last strike was biased low.** On a DoltHub-like 19-strike grid, holding the IV flat beyond the end missed the far-strike IVs by a median 7.0 vol points (p90 34.6, mean −13.2). It under-marks far wings, which flatters short wings. **Changed:** total variance is extended linearly, with its end slope clipped to Lee's moment bound, and the mark is flagged. On the same test the median error falls to 1.2 vol points (0.46 within |k| ≤ 0.40).
2. **There was no rule below the front expiry.** DoltHub lists no expiry under 10 DTE, so a 7-DTE exit has no bracketing expiry. **Changed:** IV is held constant along k/√τ from the nearest listed expiry, and the mark is flagged. Measured median error 1.2 vol points, mean +0.4. Reading the front smile at the same k, as the reviewer's probe did, measured 1.9, mean −2.2, on the same sample; the reviewer's 1.02 was for |k| ≤ 0.05 only.
3. **The cross-expiry fallback is the usual case out of sample, not a rare one.** A DoltHub expiry is listed on only about half the sessions between its first and last listing. On masked 2022–23 data, 56% of 30-DTE and 75% of 45-DTE marks come from it, with a median error of 0.24 vol points. That is six times the in-grid error. The sample pools two regimes (listing share 0.286 in 2022, 0.50–0.54 from 2023; ADR-0009), so the table below is re-reported for 2022 and 2023 separately, and 2023 is the closer analogue of the holdout. **Changed:** it is now triggered when the contract's own expiry is absent, not only when it is thin, and it is flagged.
4. **Facts.** The 520 put was quoted on 2 of **14** sessions, not 8. DoltHub has Tue/Thu sessions only from **Oct**-2024.
5. **Knock-on from ADR-0008.** The surface is now built from de-Americanised quotes. Rules 3 and 4 therefore price near-the-money contracts with the American lattice, so that a model mark matches the quote marks it replaces.

Round 2 (`docs/validation/00-round2-ledger.md`, claim 11): the error figures above reproduce, but the masked 2022–23 sample pools two expiry-persistence regimes (ADR-0009, Round 2), so they describe the holdout only as far as 2023 resembles it. They are re-reported by year.

## M2 review amendments (default taken 2026-10-29, owner can override)

The M2 adversarial review (`docs/validation/02-ledger.md`, round 1) found two gaps between this ADR and the surface M2 built.

1. **Which IV a quote's greeks use.** Line "Greeks come from our own Black-76 at the mark's IV, using the IV solved from the mid for rules 1 and 2" is ambiguous now that the build solves an IV only for out-of-the-money quotes, and also gives a descriptive IV to quotes that rule 1 does not mark from their mid (a `STALE` quote, rule 3) or that are not clean (a zero bid, rule 2). `quote_iv` now says which IVs are the surface's own: `in_smile` is true for a quote that was valid (bid above 0, not `STALE`, not crossed), OTM and solved, which are exactly the smile's nodes. **Changed:** M3's model marks (rules 3 and 4) and the greeks of every ITM quote and of every quote not `in_smile` come from `surface_iv` at the quote's own log-moneyness, never from that quote's own `iv`. ~~An `in_smile` quote's greeks may use its own `iv`, which is the surface's value there (the smile is exact at its nodes).~~ *Round 2 (design claim 6, decision E8, default taken 2026-10-29): an `in_smile` quote's greeks use its own `iv`. That is not always the surface's value at its strike: the calendar constraint (amendment 2) moves 1.56% of OptionsDX nodes on 250 random dates (1.27% since round 3 took WIDE quotes out of the smile, amendment 3) (`uv run python tools/report_m2.py`, block "the calendar constraint at the smiles' own nodes"), so "the surface's value there" was wrong, and "may" left two possible greeks.* The marks of rules 1 and 2 are still the mid.
2. **The calendar constraint.** Step 4's linear-in-τ interpolation and step 5's extrapolation carried the market's crossing smiles into the surface: the first `surface_frames.json` had 17, 18, 2 and 10 grid cells where total variance fell from one tenor to the next at a fixed k (code claim 7; round-1 measurement). **Changed:** total variance never falls with τ at a fixed k, and step 5's w along k/√τ is replaced by its running maximum from the back expiry (never below the back expiry's constrained value) or its running minimum up to the front expiry (never above the front's). `surface_iv` at τ ≤ 0 returns NaN instead of raising (an expiring contract is marked by rule 0). ~~The surface reads the running maximum of the listed expiries' w(k) in τ order. A cell where this changes the value carries the new bit `SURFACE_CALENDAR_FLOOR` (8).~~ *Round 2 (design claim 1, code claim 3; decision E1, default taken 2026-10-29): that running maximum included every expiry's EXTRAPOLATED wings, so a short expiry's wing beyond its last quote raised longer expiries' quoted nodes (2020-02-28: a 322-day node at k = −1.43 from IV 0.515 to 1.242 off the 215-day wing); on 250 random OptionsDX dates it moved 33,871 nodes (5.82%), 26,494 of them (78.2%) off an extrapolated wing, and 7,742 (4.42%) of the 0-60-day, |k| ≤ 0.15 nodes (the round-2 reviewer's measurement). Now quoted values beat extrapolated ones: a value is anchored where k is inside its own expiry's nodes; anchored values take the running maximum of the anchored values before them (a genuine quote-against-quote crossing is still resolved by raising the longer one); each extrapolated value is clamped between the anchored floors before and after it (so it can be lowered); a final running maximum orders the rest without moving an anchor. A NaN node is a missing value that never spreads past the next expiry; unsorted expiries are sorted. Measured on the same 250 dates: 9,088 OptionsDX nodes moved (1.56%), 0 by anything but a shorter expiry's quote, 3,270 (1.87%) of the 0-60-day, |k| ≤ 0.15 nodes; the largest move, +41.98 vol points (2014-09-15, 15 days, k = −0.147), is a quoted crossing ([report], block "the calendar constraint at the smiles' own nodes"; round 3 found it driven by WIDE stub quotes of the 11-day expiry, and with them out of the smile, amendment 3, the same 250 dates give 7,278 of 571,130 nodes moved, 1.27%, 3,184 of the 174,816 0-60-day, |k| ≤ 0.15 nodes, 1.82%, and a largest move of +7.51 vol points). The bit is renamed **`SURFACE_CALENDAR_ADJUSTED` (8)**: the constraint moved the value, up or down, beyond 1e-12 of it.*

### M2 round-3 amendments (defaults taken 2026-10-29, owner can override)

3. **Step 1, the inputs: a `WIDE` quote is not a smile node** (round 3, code finding N-1; decision F2). "Use the valid OTM quotes" admitted `WIDE` quotes (ADR-0009 bit 5, ask − bid > mid). On 2014-09-15 the 11-day expiry's stub puts at 171-175.5 (bid 0.03-0.05, ask 4.83-4.84) read IVs of 0.80-0.87 between tight neighbours at 0.33-0.38, and as anchors of the calendar constraint (amendment 2) they lifted 13 later expiries up to 197 days, the 15-day node at k = −0.147 by +41.98 vol points; 160 nodes on the 250 random dates moved by more than 5 vol points. **Changed:** the smile's nodes are the valid OTM quotes that are not `WIDE` and have an IV (`quote_iv.in_smile`); a `WIDE` quote keeps its quote_iv row, its IV and its premium, and may still enter the forward's near-K\* pairs (ADR-0008 amendment 10). Rejected: `WIDE` quotes as nodes that do not anchor the constraint, because the wide node still distorts its own smile (0.87 against 0.35 at the tight neighbours). Measured on the rebuilt store ([report], blocks "IV solve" and "the calendar constraint at the smiles' own nodes"; scratch `fix4/f2/`): 137,754 of OptionsDX's 7,870,569 valid OTM quotes (1.75%) and 74 of DoltHub's 80,606 are `WIDE`; leaving them out removed 137,750 nodes from 37,431 OptionsDX smiles and 74 from 48 DoltHub ones, and one smile fell below 5 nodes (OptionsDX 2019-02-08, 38 days, 7 to 4); on the 250 dates 7,278 of 571,130 nodes move (1.27%, 0 down, 0 by a wing), 4 by more than 5 vol points, the largest +7.51 (2020-07-23, a 20-day node raised by an 18-day quote at the same strike); the exported frames' calendar-moved cells are 67, 80, 28 and 24 of 286 (66, 80, 28, 24 before). Test: `tests/test_pricing_build.py::test_a_wide_quote_keeps_its_iv_and_its_pair_but_is_not_a_smile_node`.
4. **The calendar constraint's missing values and equal tenors** (round 3, code finding N-5; decision F7). An infinite w was clipped to the next floor or, past the last anchor, spread to every later row, and two smiles at one τ were resolved by their order in the list. **Changed:** `calendar_variance` treats ±inf as missing, like NaN (not an anchor, never spread, NaN where it is), and `surface_iv` raises ValueError on two usable expiries whose τ differ by 10⁻¹² years or less. Neither occurs in the build (one smile per listed expiry, every node finite); tests `tests/test_smile.py::test_an_infinite_w_is_missing_like_nan`, `::test_two_expiries_at_the_same_tau_are_refused`.

### M2 round 4: an open question, for owner review (default taken 2026-10-30, owner can override)

5. **Stub quotes that are not `WIDE` still drive the calendar constraint** (round 4, finding N-A; decision G4). **Default: no further node rule in M2** (no spread or outlier rule for smile nodes); the measurement is recorded for the owner. On the 250 random OptionsDX dates of amendment 2 (seed 1), of the 174,816 nodes at 0-60 days and |k| ≤ 0.15, the constraint moves 3,184 (0 down): 130 by more than 1 vol point, 7 by more than 2, 1 by more than 5. That one is +5.09 vol points (2020-03-20, a 20-day node at k = −0.009), raised by the 19-day smile, whose node at the 228 put (bid 13.07, ask 15.60, a spread of 17.6% of the mid: not `WIDE`) reads 6.16 vol points above its neighbours' interpolation. The drivers of the 130 moves above 1 vol point are the two nodes of the shorter smile that bracket k, 260 in all: 20 `LOCKED`, 58 with a one-tick spread, 108 with a bid of 0.05 or less, 16 more than 2 vol points from their neighbours. In the committed `surface_frames.json` the largest move on a quoted cell (bit 8, neither bit 1 nor bit 4) is 0.97 vol points (2020-03-16, 270 days, k = −0.26). M3's surface marks inherit these moves: rules 3 and 4 read `surface_iv`. Measured by the round-4 reviewer's `f2_stub_drivers.py` on the real store (read-only), re-run by the fixer with identical output, and a fixer's probe over the committed frames (session scratchpad `fix5/g4/`). The question for the owner: whether a node needs a spread or leave-one-out outlier rule beyond `WIDE`, and which.

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
| 3 | Crossed, one-sided (bid or ask null), stale, or missing, and the day has a surface | Black-76 at the day's surface IV for this contract (method below). For \|k\| ≤ 0.15 it is the CRR American price at that IV, because the surface is European-equivalent (ADR-0008 §8). *(Round 2, decision E8: from milestone 3 the American price applies at every \|k\|, decided for milestone 3, matching M2's de-Americanisation of every OTM quote with no band.)* | `SURFACE_MODEL` |
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
6. **The calendar constraint** (flag `SURFACE_CALENDAR_ADJUSTED`, M2 review amendment 2 as revised in round 2). Total variance never falls with τ at a fixed k: at and between expiries quoted values take the running maximum of the quoted values before them and extrapolated ones are held between the quoted values around them; step 5 takes its monotone envelope.

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
- **Greeks.** Greeks come from our own Black-76 at the mark's IV, using the IV solved from the mid for rules 1 and 2 and the surface IV for rules 3 and 4. We never use vendor greeks. *(M2 review amendment 1, as fixed in round 2: an `in_smile` quote's greeks use its own `iv`; an ITM quote, a `STALE` one and any quote not `in_smile` take `surface_iv` at its log-moneyness.)*
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
