# Validation ledger 00: milestone-0 design and research

> **Data notice.** The DoltHub figures in this document (counts, dates, quantiles and summaries, in its text and in its tables) are derived from the DoltHub database `post-no-preference/options` (<https://www.dolthub.com/repositories/post-no-preference/options>), licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), and are shared under the same licence. Changes: we aggregated it into counts, shares and quantiles, compared it with OptionsDX and ran our pricing build on it; no quote row is reproduced. The rest of this repository is MIT. See [DATA.md](../../DATA.md).

**What was attacked:** `docs/adr/0001–0010`, `docs/concepts/00-background.md`, `docs/prfaq.md`, `docs/architecture/README.md`, `docs/architecture/specs/data-model.erd.yaml` (skimmed) and `docs/architecture/engine-daily-loop.sequence.mmd` (now `docs/architecture/out/engine_daily_loop_sequence.mmd`).
**Date:** 2026-10-28. **Reviewer:** adversarial reviewer (Opus), following the `evidence-gated-validation` skill.
**Default verdict:** REFUTED. A claim was conceded only on evidence produced in this review.

## Protocol and its limits (read first)

- **Tiers.** Tier 2 (both channels) was used for every numeric, statistical, financial-maths, data-measurement and version-sensitive claim. Tier 1 (probe or derivation only) was used for the rest.
- **Channel A (primary sources).** A clean-room researcher subagent received only the claim statements, numbered A1–A20. Its report is in the scratch file `m0design-egv/channel-a.md`. Every source was retrieved 2026-10-28.
- **Channel B (probes).** I ran these myself. All scripts are in `<reviewer scratchpad>/m0design-egv/probes/` (kept outside the repo), which is ephemeral; the key commands and outputs are quoted below.
- **Mode: single-context sequential fallback.** The harness delivered Channel A's summary *before* my probes ran. The probe designs had been frozen beforehand, but my verdict-mapping is not blind to Channel A. Results are therefore "dual-confirmed (fallback mode)", never "independently confirmed".
- **Scratch collision.** A concurrent reviewer working on a different scope overwrote my first pre-registered ledger in the shared `scratchpad/egv/`. I restored it under `scratchpad/m0design-egv/`. The probe designs did not change.
- **Environment pin:**
  - Python 3.12.13, duckdb 2.0.0, numpy 2.5.4, scipy 1.18.1, pandas 3.1.0, pyarrow 26.0.0;
  - dolt 2.6.1, Linux 7.0.0 aarch64.
- **Raw data was left untouched.**
  - Kaggle parquet: the (name, size, mtime) listing was identical before and after (`diff` empty).
  - DoltHub clone: `dolt status` reported `nothing to commit, working tree clean` before and after.
  - Only SELECT statements were run, and Cboe CSVs were downloaded to scratch only.
- **Falsifiers.** Each load-bearing probe was shown to fail on a mutant:
  - The binomial pricer reproduces Black–Scholes for a European call and for an American call with no dividend, and gives American put > European put (4.6554 vs 4.4197).
  - Volume-cap probe: when the prior-day cap is replaced by the fill-day cap, the disagreement goes 0.2589 → 0.0.
  - Surface-gap probe: when the contract's own expiry and full grid are used, the front-expiry error goes 1.021 → 0.000 vol pts.
  - Look-ahead probe: perturbing only the future changes the full-sample HAR forecast at t₀.

## Verdict summary

| # | Claim | Verdict | Severity |
|---|---|---|---|
| 1 | ADR-0002 timing has no look-ahead | **PARTIALLY REFUTED**: the fill price and spread are fine, but the volume cap uses information from the fill day | High |
| 2 | The volume-era rule is justified by the data | **SURVIVES**. One number is wrong (11,123 should be 9,775). | Low |
| 3 | The data facts are right | **PARTIALLY REFUTED**: "12 rows", the DoltHub weekday and rows-per-date figures, "2 of 8 sessions" and the gap wording | Medium |
| 4 | ADR-0003 early-exercise inequalities | **Call SURVIVES; put REFUTED.** The put rule fires far too early, and that is a gift to the writer, not conservative. | **High** |
| 5 | SPY market-structure facts | **SURVIVES** on primary sources (single channel). The Section 31 itemisation is wrong, and one citation is weak. | Low |
| 6 | ADR-0007 is the real Cboe/FINRA rule | **PARTIALLY REFUTED.** 15%/10% is right, but the comparison against NAV double-counts option value, and the citation paragraph is wrong. | Medium |
| 7 | ADR-0006 units and budgets are coherent | **PARTIALLY REFUTED.** Units are correct, but for OTM wings the greek budgets are slack and margin sets the leverage, contradicting ADR-0007. | Medium |
| 8 | ADR-0008 parity forward is unbiased enough | **PARTIALLY REFUTED.** At 5% rates it carries a 4–7 bp bias and IV errors of 0.2–0.4 vol pts. The ADR names the wrong mechanism. | Medium |
| 9 | ADR-0009 surface-mode gap bounds the DoltHub distortion | **REFUTED.** The dense chain misses the dominant error sources. | **High** |
| 10 | Background [measured] figures and derivations | **SURVIVES**, with two minor discrepancies | Low |
| 11 | Literature read correctly | **PARTIALLY REFUTED**: ADR-0002's Muravyev–Pearson paraphrase, and the Santa-Clara–Saretto "strangle" attribution | Low |
| 12 | ADR-0010 protocol prevents overfitting and leakage | **PARTIALLY REFUTED.** The PSR/DSR maths and the vol-shock definition survive, but the volume-cap regime changes inside validation, signals leak, and the holdout is not blind. | Medium-High |
| 13 | PR/FAQ is consistent with ADRs and data | **PARTIALLY REFUTED** (6 items) | Medium |
| 14 | ADR-0001 import rules and the `MarketView` guard | **REFUTED.** The AST test permits `strategies → data`, the signals bypass the guard, and three modules lack an import they need. | **High** |

---

## Claim 1: ADR-0002 timing has no look-ahead (PARTIALLY REFUTED)

### C1a: the fill price comes from t+1 quotes (SURVIVES, Tier 1)
- The t+1 16:00 quote exists at the instant of execution. Every one of the 9,468,584 rows is stamped 16:00 New York (see C3c).
- A buy filled at that quote's ask uses no later information.

### C1c: using the fill day's own spread (SURVIVES, Tier 1)
- The half-spread and the opening filters (bid ≥ $0.05, relative spread ≤ 25%) are read from the quote being traded against.
- That is implementable, much like a conditional limit order. No information from after the fill is used.

### C1b: the volume cap uses 10% of the fill day's volume (REFUTED, Tier 2)

**Why it is look-ahead.**
- The daily volume of day t+1 is not known when the order is committed at t.
- It is not fully known even at the 16:00 fill, because SPY options trade until 4:15 pm (C5c).
- It is also correlated with the fill day's own move.

**Measurements** (`p03_volcap.py`, OptionsDX 2021–2023, contract-days with both V_t and V_t+1 non-null):

| Subset | n | 10-lot clipped (fill-day V) | 10-lot clipped (prior-day V) | Clip decision flips | cap(V_t+1) ≠ cap(V_t) | median V_t+1/V_t |
|---|---|---|---|---|---|---|
| near-ATM, 20–40 DTE | 67,519 | 49.7% | 57.8% | **25.9%** | 81.0% | 1.44 |
| 5–10% OTM wings, 20–40 DTE | 123,800 | 71.6% | 72.1% | 22.0% | 70.7% | 1.00 |
| near-ATM, 5–10 DTE (exits) | 80,443 | 19.9% | 28.3% | 18.4% | 72.1% | 1.71 |

- Contract-level `corr(ln(V_t+1/V_t), |ret_t+1|)` = **0.183** (n = 62,098; `p03c_corr.py`).
- Mutant check (`p03_mutant.py`, prior-day volume replaced by fill-day volume): the clip-flip share falls to 0.0.

**Consequences.**
- Using the fill day's volume lets more quantity through than prior-day information would (49.7% vs 57.8% clipped), so it is optimistic.
- The clip decision depends on the fill day on a quarter of near-ATM rows.

**ADR-0002:81 ("the hard cap … should rarely bind") misleads.** It is the *volume* cap that binds in 2021–23, and how often depends on the expiry type:

| 2021–23, near-ATM, 20–40 DTE | Median daily volume | 10-lot clipped |
|---|---|---|
| Monthly (third Friday) | 1,525 contracts (IQR 712–2,967) | 3.8% |
| Weekly | 68 contracts (IQR 17–209) | 56.3% |

**Fix.**
- ADR-0002:72–78: base the cap on volume known at the order date, `V_t` or a trailing median of `V_{t−4..t}`, and stamp the information date on the fill.
- ADR-0002:81: state that the volume cap clips about half of the weekly near-ATM lines in 2021–23, and decide in the ADR whether strategies use monthly expiries.

### C1d: the same-close hedge exception (SURVIVES with a caveat, Tier 2)
- **Channel A (A18).** NYSE Arca Rule 7.35-E(d)(2) starts the closing-auction imbalance freeze at 15:59, and offsetting MOC orders are still accepted after that (FR 2025-17337; nyse.com NYSE Arca trading info). A market-on-close hedge on a delta estimated before 15:59 is therefore feasible.
- **Channel B.** The engine computes delta from the 16:00 option snapshot and S_close itself. That information arrives about one minute after the cut-off.
- ADR-0005:52 already calls the exception "mildly optimistic" and bounds it with the `next_open` variant. Accepted as stated.

### Unspecified collision (Tier 1)
- At step 10, an early assignment can be decided at t for a contract that a strategy also ordered closed at t.
- At t+1 the assignment is booked first (step 2) and the close order fills afterwards (step 3), against a contract no longer held.
- **Fix.** ADR-0001:30–31: cancel orders on contracts removed by start-of-day events, with a reason code.

---

## Claim 2: the volume-era rule is justified by the data (SURVIVES)

`p02_volume.py` (DuckDB, all 14 files; daily total = Σ C_VOLUME + Σ P_VOLUME, nulls as 0):
- **Monthly medians of the daily total:**
  - 2020-10: 330,119 · 2020-11: 385,766 · **2020-12: 366,024** ✓
  - **2021-01: 2,981,034** ✓ · 2021-02: 3,083,662.
  - The ratio is 8.14×, matching the "~8×" in ADR-0002:113.
- **The break is a single step at the yearly-file boundary:** 2020-12-31 = 371,587, then 2021-01-04 = 3,417,626.
- **Yearly medians, 2010 → 2020:** 73,790 → 405,507, against 2.5–3.0 M from 2021 on.
  - The under-count runs through the whole pre-2021 era, so the rule is justified.
  - No primary-source SPY average daily volume was retrieved, so "under-counted" is inferred from the discontinuity (Channel A not run for this sub-claim).
- **Null shares.**
  - `[C_VOLUME]` is null on **37.61%** of rows ✓; `[P_VOLUME]` on 33.38%.
  - Near-ATM 20–40 DTE call nulls: 2010 **84.5%**, 2011 **96.6%**, 2012 **91.0%** ✓ (84–96%).
  - After the break, nulls are still about 19–21% of all call rows, but at most 4% near the money (2021: 0.8%, 2022: 3.9%, 2023: 0.1%).
- **The 2021-01-15 370 put:** volume is null on every row from 2020-12-15 to 12-31 ✓.
  - Then: 01-04 11,123; **01-05 9,775**; 01-06 32,828; 01-07 45,526; 01-08 58,087.
  - The range "11,123–58,087" in ADR-0002:19 is **wrong at the low end**: it should be 9,775–58,087.

**Fix:** ADR-0002:19, change "11,123–58,087" to "9,775–58,087". Optionally add to ADR-0002:16–20 that the break coincides with the 2020/2021 file boundary.

---

## Claim 3: the data facts are right (PARTIALLY REFUTED)

| Sub-claim | Measured (probe) | Verdict |
|---|---|---|
| 14 files, about 569 MiB | `stat`: 14 files, 568.63 MiB | SURVIVES |
| 9,468,584 rows, 3,508 dates, 2010-01-04 → 2023-12-29 | `p01_basic.py`: `(9468584, 3508, '2010-01-04', '2023-12-29')` | SURVIVES |
| Rows per date ≈ 1,052 (2010) → 5,070 (2021) | 1,051.9 → 5,070.2 | SURVIVES |
| Every row stamped 16:00 New York | `[QUOTE_TIME_HOURS]` = 16.0 on 9,468,584 rows; `[QUOTE_UNIXTIME]` and `[EXPIRE_UNIX]` → 16:00 America/New_York on all; 0 date mismatches; one `[UNDERLYING_LAST]` per date; key unique (0 duplicates) | SURVIVES |
| **"12 rows on market closures"** (prfaq.md:171) | `p04_calendar.py`: **12 snapshot *dates*, holding 44,926 rows** (e.g. 2012-10-29: 1,416 rows; 2022-06-20: 4,871) | **REFUTED** (dates, not rows). ADR-0009:53 labels them "Rows … (12)" while listing dates. |
| 26 trading days without a snapshot | 26, against a hand-coded NYSE calendar (3,522 sessions): 2010-05-19 … 2022-12-16, matching ADR-0009's examples | SURVIVES |
| Sandy rows are "stale copies" (ADR-0009:53) | 2012-10-29 and 10-30 both have the same S, but only 6.6% of quotes are identical between them, and 0% vs 10-26 or 10-31 | PARTIALLY REFUTED: the underlying is stale, the quotes are not copies |
| 2023-06-15, 443 strike, 29 DTE: call IV about 0.12, put IV about 0.11, gap about 0.6 vol pts | `p05_20230615.py`: the same, gap about 0.6 vol pts | SURVIVES |
| F_K at 438–448 spans 0.364 (0.082% of F) | 441.9952 to 442.3580: span 0.3628, 0.082% | SURVIVES |
| Quote-quality table, ADR-0004:13–21 | `p14_quality.py`: 745,993 (7.89%) / 632,224; 9,435 / 24,046; 11,721; 96,009; 588,461 / 472,386; 2019 22.08% / 0.56% | SURVIVES |
| Expiries per date 14.6 → 35.7; strikes per date 133 → 327 | 14.6 / 35.68; 132.9 / 326.9 | SURVIVES |
| 0-DTE expiries on 38 (2010), 166 (2022) and 250 of 250 (2023) dates | 38, 166, 250 of 250 | SURVIVES |
| ATM spreads $0.02–0.08 (0.4–2.5% of mid); Mar-2020 $0.245 → $0.61 | $0.02–0.08, 0.40–2.54%; $0.245 / $0.61 | SURVIVES |
| Fractional `[DTE]` on 3,267,818 rows | 3,267,818 | SURVIVES |
| DoltHub `option_chain` has 13 columns as listed | `describe option_chain`: identical names, types and PK | SURVIVES (dual: A schema / B describe) |
| DoltHub has no SPY dates 2024-07-29 → 08-12 | Dates present: …07-26, **07-29**, **08-12**, 08-14… Missing are 07-31, 08-02, 08-05, 08-07 and 08-09 | SURVIVES as "between" (ADR-0009:81). "**from** 2024-07-29 **to** 2024-08-12" (prfaq.md:73,176; ADR-0010:17) is wrong at both ends |
| Mon/Wed/Fri only "until Aug-2024; every weekday from 2024-09" (ADR-0009:80) | Weekday counts: 2024-08: M3 W3 F3; **2024-09: M5 Tu2 W4 Th3 F4**; 2024-10: M3 Tu5 W5 Th5 F4 | PARTIALLY REFUTED: every weekday only from **Oct-2024**. The PR/FAQ's "~Oct 2024" is right. |
| DoltHub rows per date 88–212 (ADR-0009:76) | 2024: **76–266**; 2025: 86–210; 2026: 162–216 | REFUTED (the ADR's own "samples I queried" caveat applies) |
| DoltHub front expiry 11–18 DTE; 3 expiries (2024–25), 4 (2026) | Front DTE 11–17 (2024), 11–18 (2025), 10–18 (2026), median 13–14; 3 expiries in 2024, 3–4 in 2025, 4 in 2026; back expiry median 56 DTE | SURVIVES (front 10 DTE seen in 2026) |
| 2025-04-30 520 put quoted on "2 of the 8 sessions" 2025-03-31 → 04-17 (ADR-0009:83, ADR-0004:33) | DoltHub has **14** sessions in that window; the put is quoted on 04-02 and 04-14 only | REFUTED in the count (2 of 14). The conclusion gets stronger. |
| DoltHub date range 2019-02-09 → 2026-10-26 | First 2019-02-09, last 2026-10-26 | SURVIVES (newly measured). 46 of 48 SPY dates in 2019 are **Saturdays**. |
| "Nine full-scan DuckDB queries in 1.3 s" | Script not in the repo, so not reproducible as written. My 11 aggregate full scans ran in 0.65 s; 0.79 s wall including `uv run` start-up (`/usr/bin/time`) | SURVIVES as an order of magnitude (Tier 1) |

**Fixes.**
- prfaq.md:171: change to "12 snapshot dates (44,926 rows) dated on market closures".
- ADR-0009:53: change to "Snapshot dates on market closures (12; 44,926 rows)".
- ADR-0009:76: rows per date 76–266.
- ADR-0009:80: "Mon/Wed/Fri until Aug-2024; partial Tue/Thu in Sep-2024; every weekday from Oct-2024".
- ADR-0004:49: "Tue/Thu before Oct-2024".
- ADR-0009:83 and ADR-0004:33: "2 of the 14 sessions".
- prfaq.md:73,176 and ADR-0010:17: "no SPY dates between 2024-07-29 and 2024-08-12 (07-31 to 08-09 missing)".
- ADR-0009:53: "both show the same S (stale underlying; quotes differ)".

---

## Claim 4: ADR-0003 early-exercise inequalities (call SURVIVES; put REFUTED)

### Derivation (Channel A: first principles)

**Call, immediately before the ex-date.**
- Exercising pays S − K, and the holder receives D.
- Holding, after the last ex-date before expiry, leaves an American call on a non-dividend stock. That equals the European call, C_ex = P_E + (S − D) − K·e^{−rτ}.
- Exercise is optimal iff S − K > C_ex, i.e. iff **D > P_E + K(1 − e^{−rτ})**. This is exact, both necessary and sufficient, when only one dividend remains.
- ADR-0003 uses the *American* market put, P_mid ≥ P_E. The rule is therefore sufficient but not strictly necessary, and the gap is P_A − P_E for a deep-OTM put, which is tiny.
- With a second dividend before expiry, the continuation value exceeds the European value, and the rule is no longer exact. That is rare for 30–60 DTE.

**Put.**
- Exercising now pays K − S. Holding a *European* is worth P_E = C_E + K·e^{−rτ} − S + PV(D).
- The ADR condition K(1 − e^{−rτ}) > C + PV(D) is "exercise beats holding a European".
- The true American comparison is K − S ≥ P_A,cont ≥ P_E. The ADR condition is therefore **necessary (in practice) but not sufficient**: it ignores the right to exercise later.
- When a dividend is due before expiry, the alternative that dominates is "wait until just after the ex-date, then exercise". The ADR rule ignores it entirely.

### Channel B: binomial American pricer

- Pricer: CRR with an escrowed discrete dividend (`amer.py`).
- Self-test (`p06_amer_selftest.py`):
  - European call: tree 6.88802 vs Black–Scholes 6.88873.
  - American call with no dividend equals the European call.
  - American put 4.6554 vs European 4.4197, converging (N = 500 → 4000: 4.6544 → 4.6555).
  - European call with a dividend: tree 5.76236 vs Black–Scholes-escrowed 5.76237.

**Call rule** (`p07d_call_tol.py`, `p07e_call_eps.py`; D = 1.70 just before the ex-date; K = 450):
- Lowest S at which the ADR rule fires, against the exact optimal boundary:
  - r = 5%, σ = 0.20, τ = 7 d: ADR 462.62, exact 462.59.
  - r = 0.25%, σ = 0.30, τ = 60 d: ADR 545.82, exact 545.79.
  - Every case with τ = 1, 7, 30 or 60 d agrees within $0.05.
- Assigning every qualifying short call makes the writer pay D − time value. That is conservative, as ADR-0003:103 says.
- **Verdict: SURVIVES.**

**Put rule** (`p07b_earlyex_fast.py`, K = 450; S_adr = highest S at which the ADR rule fires; S_ex = highest S at which exercise is optimal):

| r | σ | T | Dividend | S_adr (% ITM) | S_ex (% ITM) | Writer gain if assigned at S_adr, P_A − (K − S), per share |
|---|---|---|---|---|---|---|
| 5% | 0.12 | 30 d | none | 436.07 (3.2%) | 428.25 (5.1%) | 0.62 |
| 5% | 0.20 | 30 d | none | 421.70 (6.7%) | 408.86 (10.1%) | 0.70 |
| 5% | 0.20 | 60 d | none | 415.82 (8.2%) | 398.30 (13.0%) | 1.30 |
| 5% | 0.20 | 30 d | 1.70 at 10 d | 398.58 (12.9%) | **never optimal** | 1.12 |
| 5% | 0.30 | 60 d | 1.70 at 10 d | 379.85 (18.5%) | **never optimal** | 1.86 |
| 2% | 0.20 | 30 d | none | 412.46 (9.1%) | 399.61 (12.6%) | 0.33 |
| 0.25% | 0.20 | 30 d | none | 394.67 (14.0%) | 382.29 (17.7%) | 0.05 |

**The ADR's justification is wrong on both counts.**
- ADR-0003:89 says the rule "may fire a little early. That means more assignments, which is conservative for a short."
- **It fires early by 3–5 points of moneyness**, and with an ex-date before expiry it fires when no rational holder would exercise at all.
- **Early, sub-optimal assignment hands the writer P_A − (K − S) > 0.**
  - The writer's liability, marked at about P_A, is extinguished at intrinsic.
  - That is $33–186 per contract per false assignment at 2–5% rates.
  - So the rule is **optimistic for short puts** and pessimistic for long puts.
  - The bias is concentrated in 2023 and the 2024–26 holdout, the high-rate years, and in sell-offs, exactly when short-put books are hurting.
- The bias of "assume every qualifying contract is assigned" therefore depends on the side:
  - conservative for short calls;
  - **optimistic** for short puts under this put rule.

**Fix.**
- ADR-0003:73: replace the put condition with the market's own American signal. Assign iff the put's time value is gone: `P_mid(K) − max(K − S, 0) ≤ ε`, with ε about half the spread, *and* no ex-date before expiry with D > K(1 − e^{−r·τ_ex}). Alternatively, use the binomial boundary.
- ADR-0003:89 and :103: rewrite the bias statement accordingly.
- ADR-0003 test 7: add a case that is ITM by 6% at r = 5%, σ = 0.2, 30 d. The current rule assigns it; the corrected rule must not.

**Minor (ADR-0003 test 5, line 122).** "Expiring at t+1 (τ = 1/365)" contradicts line 27, "τ runs from the ex-date to expiry": with t+1 as both the ex-date and the expiry, τ = 0. The verdict is unchanged.

---

## Claim 5: SPY market-structure facts (SURVIVES, single channel: primary sources)

No runtime probe can test exchange rules, so Channel B is N/A. The data are consistent with the 16:00 stamp only.

- **Ex-by-ex at $0.01, all account types.**
  - OCC Rule 805(d)(2): "$0.01 or more" (A1, via a 2024 OCC SEC filing). The 2008 approval order is Rel. 34-57163.
  - June 2008 is documented only as the *scheduled* implementation.
  - Closing price = last regular-hours sale.
- **American, physically settled, "p.m.-settled".**
  - FR 2023-16885 (Rel. 34-98044): SPY options are "physically settled, p.m.-settled and American-style" (A2).
  - For a physically settled option, "p.m.-settled" can only mean exercise status is set by the closing price.
- **Trading hours.**
  - Non-expiring SPY options trade until 4:15 pm.
  - Expiring ones also trade until 4:15 pm: SEC Rel. 34-105153 p. 10, "trading on the expiration day of equity options will continue until 4:15 p.m."; Cboe ETH FAQ Q5.
  - Rel. **34-105569** (cited at ADR-0002:26) is the SEC's 28 May 2026 approval of SR-CBOE-2025-079 and **never names SPY**. Weak citation.
- **Ex-dividend timing.**
  - Prospectus (26 Jan 2026): the ex-date is the third Friday (or the business day before), and the record date equals the ex-date.
  - SSGA file: 1.638367 (2023-06-16), 1.759024 (2024-06-21), 1.965548 (2024-12-20) ✓. Ex-date = record date from 2024-06-21.
- **Penny ticks.** Cboe Rule 5.4(a), in Rel. 34-105131: "QQQs, IWM, and SPY … $0.01 All prices". Rel. 34-89075 is the 2020 Penny Interval Program filing.
- **Fees (ADR-0002:58–62): PARTIALLY REFUTED in the itemisation.**
  - OCC $0.025 applies only from 2025-01-01; it was $0.02 before.
  - FINRA TAF on options: $0.00279 (2024–25), $0.00329 (2026), $0 for Q4-2026.
  - Cboe ORF $0.01248 per side from 2026-07.
  - **Section 31 on a $500 option sale:** $0.0040 (FY2023), **$0.0139 (FY2024)**, $0 (FY2025), **$0.0103 (FY2026)**. "Under $0.01" is false at two of the four rates.
  - The pass-through total (~$0.04–0.06) and $0.70 all-in still hold as an approximation.

**Fix.**
- ADR-0002:26: cite 34-105153 or the Cboe ETH FAQ.
- ADR-0002:61: "about $0.004–0.014 per $500 sold (FY2023–26 rates)".
- ADR-0002:59: "$0.025 since 2025 ($0.02 before)".
- ADR-0003:14: the open "not verified" note can now cite 34-105153.

---

## Claim 6: ADR-0007's margin model is the real Cboe/FINRA rule (PARTIALLY REFUTED)

**15%/10%, not 20%/10%: SURVIVES** (Channel A, A8).
- Cboe Margin Manual (cover date 30 Nov 2021), p. 7, row "ETF – tracking a broad based index": 100% of option value + 15% of underlying − OTM amount. Minimum: option value + 10% of underlying (calls) or 10% of the put's exercise price (puts).
- FINRA Interpretation 4210(f)(2)(E)/02 "Listed non-leveraged ETP options on broad-based index": 15%.
- Channel B: the ADR-0007 tests 2–5 reproduce under 15%/10% (4,800; 4,600; 8,000; 16,605 per contract; `p12_adr_tests.py`, `p09_greeks.py` margin function).

**The citation is wrong.**
- ADR-0007:14 cites "FINRA 4210(f)(2)(E)(i)". That paragraph's 15% row is "broad index stock group" and never mentions ETFs; the ETF row is in **Interpretation 4210(f)(2)(E)/02**.
- Notice 09-53 cites the predecessor rules NASD 2520 and NYSE 431.

**Straddle rule: SURVIVES.** Margin Manual p. 8: the greater requirement plus the other side's market value; worked example on p. 45.

**Hedge shares at 30%: PARTIALLY REFUTED as "conservative"** (A10).
- FINRA 4210(c) maintenance is 25% long and max(30%, $5/share) short.
- So 30% is conservative only for long shares, equal to the rule for short SPY, and **below** Reg T initial margin (50% long; 150% of market value on short sales, 12 CFR 220.12).

**The comparison against NAV double-counts option value: REFUTED as "the real rule".**
- FINRA 4210(a)(5) equity already deducts the market value of short securities.
- The Cboe Manual says "Sale proceeds may be applied". Its worked example (p. 30): short Oct 410 put at 0.10, requirement $4,110, "SMA Debit or Margin Call: $4,110.00 − $10.00 = $4,100.00".
- ADR-0007:44 compares `margin_req` (which includes 100% of option value) against `NAV_mid` (which already subtracts it). That counts the option value twice.
- Probe (`p17_margin_trigger.py`), 24 short 30-DTE ATM straddles, S = 450, vol rising with the fall:

  | Spot drop | ADR rule | Proceeds-applied comparison |
  |---|---|---|
  | −50% | triggers a margin call (req $645,771 > NAV $506,637) | no call (req − option value $108,000) |
  | −60% | triggers | still no call |

- The error is conservative, but the ADR presents it as the rule. It also tightens the 50% pre-trade cap (ADR-0007:41).

**DGS3MO conversion: SURVIVES** (A12 + probe).
- FRED and Treasury define it as a bond-equivalent (investment) yield on a 365/366-day basis.
- `r_cc = (365/91)·ln(1 + y·91/365)` gives 0.0521594 at y = 5.25 and 0.000500 at y = 0.05.
- $428.80 and $46.99 reproduce.
- The 366-day leap-year and 91- vs 92-day differences are below 0.3 bp.

**Fix.**
- ADR-0007:14: cite Interpretation 4210(f)(2)(E)/02 and Margin Manual p. 7.
- ADR-0007:44 and :41: compare `margin_req − Σ short-option market value` against `NAV_mid`, or keep the stricter rule but label it a conservative house rule.
- ADR-0007:39: "30% (= short maintenance; long is 25%; Reg T initial 50% is not modelled)".

---

## Claim 7: ADR-0006 greek units and budgets are coherent (PARTIALLY REFUTED)

**Units: SURVIVES** (derivation plus `p09_greeks.py`).
- `gamma_1pct_usd = Σ q·100·Γ·S²·0.01` is d(delta_usd) for a 1% move (ignoring the re-scaling of S in delta_usd).
- ½·0.01·gamma_1pct is the P&L of a 1% move, and 50·gamma_1pct·m² the P&L of a move m.
- Vega is per vol point, theta per calendar day (/365).
- Test values reproduce: 9.148603; delta_usd 20,457.43; gamma_1pct 2,781.94; vega 45.73; theta −15.24.
- The gamma/vega ratio is 1/(στ) = 67.6 at σ = 0.18, 30 DTE (computed 6,930/102.5 = 67.6).

**Short 30-DTE ATM straddle, S = 450, σ = 0.18, r = 0.04 (q = 0 or 1.3%), NAV $1M.**
- Per straddle: vega $102.5, gamma_1pct $6,930, theta −$30.9/day, margin $8,603.
- Per-position caps (40%): n_vega = **9**, n_gamma = 11, n_theta = 12–13. **Vega binds first: 9 straddles**, consistent with "7–12" at ADR-0002:81.
- Portfolio caps: vega 24, gamma 28, theta 32. At 24 straddles the margin is **20.6% of NAV**, and it takes 58 straddles to reach the 50% cap.
- Theta overtakes vega at 30 DTE only above σ ≈ 0.24 (σ > 2.92τ).
- The ADR's "theta binds before gamma above about 19%" is a correct *pairwise* statement.

**Sweep** (`p09_greeks.py`; tenors 7–180 d; σ 0.12–0.50):

| Structure | Binding constraint | Margin at the greek limit |
|---|---|---|
| ATM straddle | greeks, every case | at most **23% of NAV**, so the 50% margin cap is **never** binding |
| 10% OTM strangle, σ = 0.18, 30 d | vega allows 155 | 71% of NAV |
| 15% OTM strangle, σ = 0.18, 30 d | vega allows 1,338 | 603% of NAV |

- For OTM wings, the margin cap and the 100-contract hard cap set the size; the greek budgets do not.
- That contradicts ADR-0007:29 ("Leverage is set by the greek budgets … never by 'use all available margin'").

**Stress** (`p09b_stress.py`, full revaluation):
- At the full vega budget (24 straddles), (−10%, +20 vol pts) loses **8.2% of NAV**. The ADR's Taylor estimate is 13.2% for this book, or 15% at full budgets, so for straddles it is conservative.
- A 10%-OTM strangle book at the 50% margin cap (109 strangles) passes every greek budget (vega 1,758 < 2,500; gamma 118,801 < 200,000), yet loses **18.8% of NAV at (−10%, +20)** and **58.3% at (−20%, +40)**.
- So the greek budgets do not bound tail loss for wing books, and ADR-0006:46's 15% figure is not a bound.

**Fix.**
- ADR-0006:46–48: state that the 15% is a second-order estimate for ATM structures only.
- ADR-0006: add a full-revaluation stress limit (for example, cell (−10%, +20) ≥ −X% of NAV) as a pre-trade check, reusing the ADR-0010 grid.
- ADR-0007:29: "set by greek budgets for near-ATM structures; by the margin cap and hard cap for OTM wings".

---

## Claim 8: ADR-0008's parity forward is unbiased enough (PARTIALLY REFUTED)

**Pairs used** (ADR-0008:45–47): every strike with both sides quoted, K* = argmin |C − P|, and F = median of F_K over the 5 strikes nearest K*. These are near-ATM pairs, where the *put's* early-exercise premium at positive rates is not negligible.

**Channel B: binomial American prices with σ flat, then the ADR procedure** (`p08_parity.py`):

| Case | F_true | F_hat | Bias | F_K slope | Max IV error using F_hat | Max IV error using F_true |
|---|---|---|---|---|---|---|
| S = 442.61, r = 5.22%, σ = 0.12, 29 d, D 1.638 at 1 d | 442.8031 | 442.6127 | **−4.3 bp** | −0.029 per strike | **+0.19 vol pts** (calls near ATM) | **+0.34** (OTM puts near ATM) |
| Same, no dividend | | | −4.0 bp | −0.027 | 0.18 | 0.36 |
| r = 5%, σ = 0.20, 60 d, D at 30 d | | | **−7.4 bp** | | 0.24 | 0.44 |
| r = 0.25%, σ = 0.20, 30 d | | | −0.1 bp | | 0.007 | 0.010 |

**Real-data corroboration** (`p05_20230615.py`):
- On 2023-06-15, F_K falls monotonically from 442.376 (K = 436) to 441.871 (K = 450), a slope of about −0.036 per strike. That sign and size match the binomial American signature.
- The parity forward (median, about 442.27) is about 12 bp below the carry forward implied by DGS3MO 5.22% and D = 1.638 (about 442.80). The binomial explains about 4 bp; the rest (rate or underlying-timing mismatch) is unexplained.

**What is refuted.**
1. ADR-0008:74, "the early-exercise premium is close to zero" for OTM quotes, is false at 5% rates: near-ATM OTM puts carry 0.3–0.44 vol pts of early-exercise premium.
2. ADR-0008:95 attributes the F_K dispersion to "early-exercise value of ITM calls near ex-dates". The dispersion appears **with no dividend at all**: it is the *put* early-exercise premium at positive rates.
3. The bias depends on the rate regime: about 0 in 2010–21 and 0.2–0.4 vol pts in 2023–26. That correlates with the validation/holdout split.
4. ADR-0008:30 says the parity forward "removes the gap". It shrinks the vendor's 0.57-point call/put gap, but leaves an American-premium bias of about 0.2–0.3 points.

**Fix.**
- ADR-0008:44–50 and :73–75: de-Americanise the roughly 10 near-ATM quotes per (date, expiry) with a CRR tree before computing F_K and IVs. This is only 10 trees per expiry, not 100× the whole chain.
- At minimum, store the F_K slope per expiry in `expiry_forwards` and report IV error by rate regime.
- ADR-0008:95: correct the stated mechanism.

---

## Claim 9: ADR-0009's surface-mode gap bounds the DoltHub distortion (REFUTED)

**DoltHub's grid, measured** (C3 table and `dolt sql`):
- 3 expiries in 2024, 3–4 in 2025, 4 in 2026.
- Front expiry 10–18 DTE (median 13–14); back expiry median 56 DTE.
- About 19 strikes per expiry, about 2–2.5% apart. For example, 2025-04-02, front expiry: 452, 466, 480, … 675, around S ≈ 564.
- Mon/Wed/Fri only before Oct-2024, and a 5-session hole from 2024-07-31 to 08-09.

**Fair-test probe** (`p15_surface_gap.py`): 30 OptionsDX dates in 2022–23, subsampled to 19 strikes about 2.3% apart, re-centred, with the ADR-0004 interpolation (linear total variance, flat beyond the ends).

| Error source | Median \|error\| | p90 \|error\| | n |
|---|---|---|---|
| Inside the 19-strike range, off-grid strikes | 0.033 vol pts ($1.06 per contract) | 0.111 vol pts ($3.96 per contract) | 5,842 IVs / 3,827 prices |
| Beyond the range (flat extrapolation) | **7.0 vol pts** (mean −13.2) | 34.6 vol pts | 1,865 |
| **7-DTE ATM contract marked from the ~14-DTE front smile**, because DoltHub quotes nothing under 10 DTE and ADR-0004 rule 3's cross-expiry fallback then has no bracketing expiry | **1.02 vol pts** | 2.63 vol pts | 1,229 |

- Falsifier: using the contract's own expiry and full grid gives an error of 0.000.

**Why the in-sample gap understates the distortion.**
- OptionsDX in-sample has 7-DTE quotes, all expiries and 150–330 strikes every session.
- A surface-mode run on that dense chain therefore measures only the small in-grid error in the first row of the table.
- It misses all of these:
  1. every `exit_dte = 7` exit, which in the holdout is marked and filled about 1 vol pt (median) off;
  2. wing extrapolation after re-centring;
  3. `STALE_SURFACE` marks on Tue/Thu before Oct-2024 (about 40% of sessions);
  4. the August 2024 hole.
- "Bounds that distortion" (ADR-0009:145) is false, and it contradicts the PR/FAQ, which calls this an open item (prfaq.md:196).

**Fix.**
- ADR-0009:129: run in-sample configurations in surface mode on **OptionsDX subsampled to DoltHub's grid**:
  - only the 3–4 expiries DoltHub would list (front 10–18 DTE, back about 56 DTE);
  - 19 strikes at about 2% spacing, re-centred daily;
  - Mon/Wed/Fri sessions for the pre-Oct-2024 analogue.
  - Report quote-mode vs that.
- ADR-0009:145: drop "bounds".
- ADR-0004:55: specify the extrapolation below the front expiry, because there is no bracketing expiry.

---

## Claim 10: background [measured] figures and derivations (SURVIVES)

`p10_vix.py` on Cboe CSVs downloaded 2026-10-28.
- The `cdn.cboe.com` URL returns **307** to `cdn-api.cboe.com/...`, then 200 (also A19).
- RV = 252/21·Σ of the next 21 squared SPX log returns, with zero mean and overlapping windows.

| Figure | Doc | Measured |
|---|---|---|
| Mean VIX vs mean √RV, windows 1990-01-02 → 2026-09-28 (n = 9,248) | 19.43 / 15.33 | **19.43 / 15.33** ✓ |
| Share of days VIX > RV; mean ln(RV/VIX²); corr(dlog SPX, dVIX) | 85.9%; −0.60; −0.79 | 85.9%; −0.602; −0.786 ✓ |
| Carr–Wu window, Jan 1996 – Feb 2003 | 23.73 / 18.97 | **23.71** / 18.97. The 0.02 gap is window-boundary sensitive (minor). |
| VIX close 2024-08-02, 08-05, 08-06 | about 23, 39, 28 | the same, to the cent ✓ |
| Realised vol over the 21 days after 08-05 | 16.2% | 16.2% ✓ |
| 2022 PUT; SPX; SPX max drawdown | −7.66%; −19.44%; −25.43% | −7.66%; −19.44%; −25.43% ✓ |
| Feb-2018 | about 17 → about 37, +115.6% (largest since 1990), SPX −4.10% | ✓ |
| Mar-2020 | 82.69 | ✓ |
| 2020-02-21 | VIX about 17 → 88.0% realised | ✓ |
| Apr-2025 | 45.31, 52.33 | ✓ |
| Mean VIX² − RV by year (2018 / 2020 / 2022 / 2024 / 2025) | −6 / −198 / +89 / +89 / +45 | ✓ |
| 2020: share of days VIX > RV | 76.7% | ✓ |
| 2022 VIX mean; high | 25.6; 36.45 (03-07) | ✓ |
| VIX/VIX3M ≥ 1 in 2022 | 15 of 252 | 15 ✓, but the VIX file has 256 rows in 2022 (minor) |
| VIX > VIX3M since 2009-09-18 | 7.5% | ✓ |

**Gamma rent: SURVIVES** (derivation).
- Step 4 uses Θ + ½σ²S²Γ + rSΔ − rV = 0, so Θ − r(V − ΔS) = −½σ²S²Γ ✓.
- Var(½ΓS²σ²δt(z² − 1)) = ½(ΓS²σ²δt)² ✓.

**Weekly vs daily hedging error ≈ 2.1×: SURVIVES** (`p11_hedge.py`; 200,000 paths, ATM call, σ_r = σ_i = 0.2):

| Discretisation | Ratio |
|---|---|
| 21 trading-day steps | 2.057 (seeds 2.048–2.058) |
| 30 calendar-day steps | 2.143 |
| Fine grid | 2.161 |

√5 = 2.236.

**ADR-0005 test 1 numbers: SURVIVE.**
- Exact one-day P&L: −2.82 at S = 404, +79.87 at 408, −30.75 at 400.
- Gamma + analytic theta: −2.67 and +80.79.

**Minor inconsistency (background:125).** "σ = 16% → about 1.0% a day" assumes δt = 1/252, but the repo's calendar-day convention (ADR-0005:15, ADR-0006) gives 16%·√(1/365) = 0.84%. **Fix:** "0.84% per calendar day (1.0% per trading day if δt = 1/252)".

---

## Claim 11: the literature is read correctly (PARTIALLY REFUTED)

- **Muravyev & Pearson (2020).** The abstract (Crossref) says "less than 40% of the size of conventional measures", and "one-quarter smaller than conventional estimates".
  - **ADR-0002:9 says "under 40% of the *quoted* spread … a quarter smaller than the quoted spread": REFUTED.**
  - background:199 is faithful.
  - **Fix:** ADR-0002:9, use "conventional effective-spread measures".
- **Santa-Clara & Saretto, 2004 WP** (A14).
  - Confirmed: +2.7%/month, Sharpe 0.474 → −1.0% (p. 19); 4–6.9% (p. 16); 10.28% / 10.69% (p. 15); 1.69 (p. 2).
  - But the margin result is for "the portfolio that involves a short position in the near-maturity 5% strangle", an optimal mix with the market and T-bills, not "the best strangle" (ADR-0007:12) or "the 5% strangle" alone (background:195). **PARTIALLY REFUTED.**
  - The 3.15%/week figure is Coval & Shumway's *zero-beta* straddle, cited by S-C&S. background:165 says "restate", which is acceptable.
  - The published JFM version was not checked.
  - **Fix:** ADR-0007:12, "turned the optimal portfolio containing the short near-maturity 5% strangle from +2.7% to −1.0% a month". Same at background:195.
- **Carr & Wu.** The 2004 WP (the file at the cited NYU URL) gives 24.41, 18.82, −0.594, t = −9.484 and premium = RV − SW ✓. The RFS 2009 tables were not compared, and the doc says so.
- **Corsi (2009).** Table 5 has 1-day, 1-week and 2-week horizons only ✓.
- **DOIs: all 18 resolve.**
  - Channel B: `curl https://doi.org/<doi>` gives HTTP 302 to the expected publisher for each.
  - Channel A: Crossref metadata matches every citation. Only anomaly: Crossref dates Corsi 2008-11-07 (online), while the print issue is 7(2), 2009.
  - **ACCEPTED (dual-confirmed, fallback mode).**

---

## Claim 12: ADR-0010's protocol prevents overfitting and leakage (PARTIALLY REFUTED)

**Survives.**
- PSR = 0.9433, SR* = 0.07873 (Φ⁻¹(0.9) = 1.28155, Φ⁻¹(1 − 1/(10e)) = 1.78924) and DSR = 0.6319 reproduce (`p12_adr_tests.py`).
- The formulas match Bailey & López de Prado (A20). Kurtosis is raw, not excess.
- **Vol-shock definition** (`p10_vix.py`):
  - Shock sessions are 1.7% (development), 2.1% (validation) and 1.5% (holdout).
  - Post-shock sessions are 24.4% / 27.2% / 20.3%.
  - 50 of 123 shocks fire only through the +5-point arm (high-VIX days) and 29 only through the +25% arm.
  - Coherent and not degenerate.

**Refuted.**
1. **The volume-cap regime changes inside the validation split** (2021-01-04) and never applies in development (2010–19) or the holdout (DoltHub, hard cap only).
   - Measured: a 10-lot on weekly near-ATM 20–40 DTE lines is clipped on 56% of contract-days in 2021–23, and never under the hard cap.
   - Configurations tuned without any volume cap meet one only in 2021–23.
2. **Trial counting.**
   - DSR's N is the number of *independent* trials (A20). Distinct `config_hash` values are correlated, and the ADR does not say how N or V[SR] will be estimated.
   - Choices made outside `runs` (the volume-reliable date, `exit_dte`, thresholds, notebook exploration, all chosen with the full 2010–2023 data in view) are not counted.
3. **The holdout is not blind.** background §6 already analyses Aug-2024 and Apr-2025 outcomes ("A book stopped out on 4–8 Apr missed the reversal"). Designing stop and regime rules after reading that leaks holdout knowledge.
4. **Validation re-runs.** "A re-run after a change is logged … counts as a new trial" (ADR-0010:28) lets validation be used for tuning.
5. **Signal look-ahead** (see C14). Signals fitted over the full history let validation and holdout data shape development-period features, and the split guard (ADR-0010:103) only checks the dates a run *requests*.

**Fix.**
- ADR-0010:27–29: split results by the volume-cap era *inside* validation, or apply the same cap rule in every split (for example, a hard cap scaled to a known pre-2021 proxy).
- ADR-0010:36–42: define N_eff (for example, by clustering trial return correlations) and log design choices made outside `runs` as trials.
- ADR-0010:28: cap the number of validation re-runs.
- ADR-0010 Consequences: state that holdout events were studied in the background doc.

---

## Claim 13: the PR/FAQ is consistent with the ADRs and data (PARTIALLY REFUTED)

1. **prfaq.md:171, "12 rows dated on market closures":** these are 12 snapshot dates with 44,926 rows (C3).
2. **prfaq.md:197, "Early assignment is assumed whenever exercising early pays the holder":** the put rule assigns when exercise does *not* pay, by up to 3–5 points of moneyness, or always before a dividend (C4).
3. **prfaq.md:143–144, "Sharpe is scale-free … What changes it is how big the positions are relative to the capital":**
   - Sharpe on excess returns is invariant to constant leverage.
   - What leverage changes is the path: margin calls, ruin and compounding.
   - The same error is at ADR-0007:64 ("Sharpe can be scaled up by leverage") and background:218 ("Leverage scales Sharpe").
4. **prfaq.md:73, 176:** the gap "from 2024-07-29 to 2024-08-12" is wrong at both ends: those two dates exist (C3).
5. **prfaq.md:196 vs ADR-0009:145:** the PR/FAQ calls the surface-mode estimate possibly too small (correct), while the ADR says it "bounds" the distortion. The ADR is wrong (C9).
6. **prfaq.md:53–54 and 134:** "10% of the day's volume … on the fill day" inherits the look-ahead in C1b.
7. **Consistent:** "Mon/Wed/Fri only before ~Oct 2024" (prfaq.md:125, 175) matches the data. ADR-0009:80 is the one that is wrong.

**Fix:** the corresponding lines, plus FAQ 5 rewritten as "Sharpe is unchanged by leverage until the path forces a sale; margin calls and ruin are what leverage changes."

---

## Claim 14: ADR-0001 import rules and the `MarketView` guard (REFUTED)

Probe: `p16_imports_lookahead.py`.

- **The table is acyclic: SURVIVES** (`graphlib` topological sort succeeds).
- **The AST test enforces a weaker rule than the table.**
  - ADR-0001:137 fails only if a module imports one "not on its left in the table".
  - That rule allows **33 edges the "May import" column forbids**, including:
    - **`strategies → data`**: direct store access, the exact bypass of `MarketView`, which ADR-0001:65 says never happens;
    - `risk → strategies`, `analytics → engine`, `pricing → data`.
  - The one mutation check (`pricing → engine`) exercises only an upward edge.
- **Modules that need an import they are not allowed.** `needs … allowed by table = False` for:
  - **`engine → signals`.** The sequence diagram (`out/engine_daily_loop_sequence.mmd:51`, `Eng->>Sig`) has the engine call signals directly, but the engine may import only data, pricing, strategies and risk.
  - **The pricing build.** ADR-0001:47 says derived tables are "written by `volbt.data` and `volbt.pricing`", but ADR-0001:57 says pricing is "pure functions, no I/O" and may import only numpy/scipy. Building `quote_iv`, `expiry_forwards` and `smile_fits` needs both data and pricing, and no allowed module except `engine` has both.
  - **`signals → data`.** Signals need SPY bars, VIX and quote_iv history but may import only pricing. They must be handed the full history, which is the next problem.
  - Analytics regimes are fine: the ERD's `signals` table carries `vix_bucket` and `vol_regime`.
- **Look-ahead path around `MarketView`.**
  - ADR-0001:43: signals are "column operations over the full history … then shifted".
  - Shifting fixes the index, not the parameters.
  - Probe: a HAR fitted by OLS on the full series, then shifted, gives a forecast at t₀ = 1500 of 2.985e-03. Multiplying **only data after t₀** by 3 changes it to 2.992e-03 (`look-ahead: True`).
  - This contradicts ADR-0010:31 (monthly expanding refits).
  - No test covers signals: ADR-0001 test 2 checks only a strategy requesting a later chain.

**Fix.**
- ADR-0001:137: make the AST test enforce the explicit May-import sets, and add mutants `strategies → data` and `risk → strategies`.
- ADR-0001:58–61: add `signals` to engine's allowed imports, or route signals through strategies and fix the sequence diagram.
- Move the pricing build into a `build` module allowed to import data and pricing, or into `data` with pricing injected.
- ADR-0001:43: replace the sentence with "signals are computed causally (expanding or rolling fits using data ≤ t)".
- Add a metamorphic test: perturb every input dated after t, and assert every signal value at ≤ t is bit-identical.

---

## Findings nobody asked about

1. **The ADR-0002 rounding formula fails in floating point.**
   - Implementing `ceil_to_tick(mid + k·h)` naively gives, for quote 2.00/2.10:
     - a k = 1 sell of **1.99** (should be 2.00);
     - a k = 0 sell of **2.04** (should be 2.05);
     - because `mid − h = 1.9999999999999998`.
   - Over 100,000 random penny quotes, the k = 1 buy differs from the ask on 12,155 (12.2%).
   - Property test 8 ("≤ 2 decimals") cannot detect this.
   - **Fix (ADR-0002:46–49):** use integer cents or Decimal arithmetic, and add test cases at exact-tick boundaries.
2. **OptionsDX closure-day snapshots are not copies.**
   - Identical quotes against the neighbouring days are 0–2.6%, and the underlying differs by cents: 2022-07-04 differs from 07-01's by about 4 cents; 2022-01-17 from 01-14's by about 6 cents.
   - That suggests late re-snapshots of the prior session, and that the vendor's normal-day `[UNDERLYING_LAST]` may not equal the official close.
   - Unverified: no yfinance closes were fetched. M1's 0.10% tolerance ($0.45) would hide a cents-level asynchronicity.
3. **DoltHub's 2019 SPY rows are dated on Saturdays** (46 of 48 dates). The ADR-0009 §5 cross-vendor check has no same-date overlap with OptionsDX in 2019.
4. **The volume cap depends on the expiry type** (median near-ATM volume: weekly 68 vs monthly 1,525). No ADR says which expiries the strategies trade.
5. **On 2023-06-15 the parity forward sits about 12 bp below the DGS3MO carry forward.** Only about 4 bp is explained by the early-exercise premium, so the forward is unstable in level, not only in dispersion.
6. **ADR-0003 test 7c** gives 4.5815 vs the documented 4.5816 (rounding).
7. **The sequence diagram's message count** ("35 messages", architecture README) was not re-rendered. The tool lacks Mermaid here, so it was not verified.

## The single most important fix

**Close the look-ahead hole in ADR-0001.**
- Make the AST test enforce the explicit "May import" sets, so `strategies → data` fails.
- Replace "vectorised over the full history, then shifted" (ADR-0001:43) with causal fitting, and add a perturb-the-future metamorphic test over every signal.
- Today the structure the PR/FAQ cites as its main look-ahead defence would pass a strategy that reads the store directly and a full-sample HAR fit.

## The one item to delete

**Delete ADR-0009 §4's dense-chain surface-mode run as the holdout-distortion estimate** (ADR-0009:129 and :145, "bounds that distortion").
- It produces a reassuringly small number, about 0.03 vol pts in-grid, while the DoltHub-specific errors are about 1 vol pt at every 7-DTE exit and 7+ vol pts in the wings.
- Replace it with the OptionsDX-subsampled-to-DoltHub-grid run described under C9.
