# Milestone 2: adversarial review, rounds 1 to 4 — evidence-gated validation ledger

> **Data notice.** The DoltHub figures in this document (counts, dates, quantiles and summaries, in its text and in its tables) are derived from the DoltHub database `post-no-preference/options` (<https://www.dolthub.com/repositories/post-no-preference/options>), licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), and are shared under the same licence. Changes: we aggregated it into counts, shares and quantiles, compared it with OptionsDX and ran our pricing build on it; no quote row is reproduced. The rest of this repository is MIT. See [DATA.md](../../DATA.md).

**Reviewers (2026-10-29):**
- **Code reviewer:** `adversarial-reviewer` (Opus), `evidence-gated-validation`. Channel A read the H.15, Treasury, Lee (2004), Gatheral–Jacquier and SPY-prospectus sources; Channel B ran probes against a read-only copy of the store and 23 of its own mutants in a scratch copy.
- **Design reviewer:** `adversarial-reviewer` (Opus). Synthetic clean chains, the real store (read-only) and a copy of the app's validator.
- **Verifier:** `verifier` (Sonnet). Re-measured the walkthrough's numbers and re-ran 10 of its 40 mutants.

**Recorded by the orchestrator** (the reviewers' rules forbid writing report files). The probes are in the session scratchpad (`egv/m2/{code/probes,design,verify}/`). **Scope:** the uncommitted milestone-2 tree on top of 35cb682.

## The orchestrator's own verification, before acting

- **Design 3 (the 700-day clean chain).** Re-ran the reviewer's `p5_mechanism.py` in the real repo and saw the same output: F −102.99 bp (2 passes, N = 200) and −100.98 bp (20 passes, N = 1,000), 120 of 130 quotes `PARITY_OUTLIER`, the largest OTM IV error 1.01 vol points. **Confirmed.**
- **Design 2/4 (dividend seasonality).** Re-ran `p4_season.py`. Corrections within 60 days above 3 vol points: 250 span a March ex-date, 132 September, 106 December, 47 June; the largest 7.06, in March. **Confirmed** that March dominates. The % overstatement itself was not re-run.
- **Code 7 (calendar arbitrage in the committed file).** Its own script over `app/public/data/surface_frames.json`, w = iv² · dte/365 down each k column: 17, 18, 2 and 10 falling adjacent cells; the worst −0.00243, −0.00459, −0.00453, −0.00100. **Confirmed.**
- **Code 10 (the fingerprint).** Read `build.py:243-256` (the lines then; after round 1 `:260-287`, after round 2 `:264-291`, after round 3 `:268-295`): `code_fingerprint` hashed `volbt/pricing/*.py` and `build.py` only, not `store.py`, `flags.py`, `config.py` or any library version. **Confirmed.** The dividends table was in `REFERENCE_TABLES`, so M19 is a missing test, not a bug.
- **Code 2 (the IV tolerance).** Ran `implied_vol` on K = 500, F = 442, σ 0.12: at 7 and 10 days the prices (5.9e-14 and 3.8e-10) came back as 0.01 after 0 iterations with no fail code; at 14 days (1.5e-7) as 0.11973. **Confirmed.**
- **Design 10 (the validator).** Read `p10_outcomes.txt`: 11 contradictory files accepted (its 12th ACCEPTED line is the committed baseline; corrected in round 2, verifier V4). Not re-run.
- **Verify 5 and 7.** Read: the "297 files" was off by the walkthrough itself (298), and the 480.3 s slowest-partition row could not be reproduced (`pricing_timings.json` was overwritten by build 4; build 2's 483.76 s is only in `data/logs/pricing_build_2.log`).

## Code reviewer, per claim

| # | Claim | Verdict | Key evidence |
|---|---|---|---|
| 1 | Black-76 and its greeks | SURVIVES | Against mpmath: prices 2.7e-16, greeks 2.5e-13 relative; delta_usd 20,457.4301. |
| 2 | The IV solver converges to the root | **PARTLY REFUTED** | An absolute 1e-8 USD tolerance accepts the clipped start guess: any price below 1e-8 returns 0.01 after 0 iterations (358 random cases: median error 0.074, max 1.05); an ITM call one ulp above its bound returns 0.0319 against the root 0.0233. No build effect. |
| 3 | The lattice | **PARTLY REFUTED** | p > 1 when σ < r√(τ/N): σ = 1e-4, a 430 call, 30 days, 5% gives 10.000 against 11.7635, a European sum of −4e186 (the round-1 code reviewer's measurement; not reproduced in round 2, verifier V7: in-process it is now NaN, and the naive sum is +5.65e185), a NaN premium. Latent (the lowest raw IV built was 0.0387). |
| 4 | The ex-date rule | SURVIVES | 71 of 71 ex-dates; cutting the dividends at the quote date changes 0 of 12,693. Minor: past the last bar 2027-06-18 (Juneteenth observed) is kept where the rule gives 06-17. |
| 5 | Parity forward | SURVIVES | 0 mismatches on 20,000 random chains. |
| 6 | The IV-flag fixture | **PARTLY REFUTED** | The 18 rows re-derive exactly. Latent: a NaN premium near K\* makes pass 1's F NaN, pass 2 fails, and F silently becomes forward_raw, still labelled `parity_median5_deam`; a NaN premium is reported as "below_lower_bound". |
| 7 | The surface has no calendar arbitrage | **REFUTED** | Beyond the last node (w 0.0138 → 0.0122 → 0.0106 at k = 0.2, 30 → 60 days) and past the back expiry; the committed file has 17/18/2/10 falling cells; `surface_iv(tau=0)` raises ZeroDivisionError. |
| 8 | The early-exercise example | SURVIVES (wording) | 0.5201 at N = 500. Exercise is OPTIMAL below 409.02; 409.75 is where the toleranced rule fires; the old inequality fired at 421.70. |
| 9 | Quote validity and the rate | **PARTLY REFUTED** | (a) STALE quotes with a bid get an IV and sit in the 99.977% denominator, though ADR-0004 rule 1 marks them off the surface. (b) DGS3MO dated t is not public at the 16:00 ET snapshot of t. |
| 10 | The incremental build is safe | **REFUTED** | A changed `COMPRESSION_LEVEL` re-prices nothing yet a forced build writes other bytes; library versions are not fingerprinted; deleting `option_quotes/source=dolthub` leaves its 3 pricing partitions and the summary counts them. |
| 11 | The summary's denominators | SURVIVES | Recomputed. 13.1% = 835,088 / 6,363,238 (all quotes beyond 180 days); over the quotes the test can flag it is 13.8%. |
| 12 | The tests kill the mutants | **PARTLY REFUTED** | 11 of 23 own mutants survive (M5, M10, M11, M12, M15, M16, M18, M19, M20, M21, M22). One de-Americanisation pass is NOT equivalent on real snapshots: up to 3.41 bp in a 0–60-day F and 0.40 vol points (2019-03-14), 16 flag flips (2023-06-15). |
| 13 | Test 8's loosened 60-day bound | SURVIVES | Still kills the raw mutant; at N = 2,000 the error is 0.0043, so 0.0111 is the N = 200 premium's own. *Superseded by round 2, R7 (below): the 0.0043 is the old σ₀ method's error, not the new method's. The new method gives 0.0109/0.0047/0.0032/0.0029 at N = 200/500/1,000/2,000.* |
| — | Outside the claims | — | Theta holds F fixed: ATM 30 days at 5%, −$15.04 per contract per day against −$18.12 with S fixed; the gap lands in ADR-0005's attribution residual. |

## Design reviewer, per claim

| # | Claim | Verdict | Key evidence |
|---|---|---|---|
| 1 | No \|k\| band | SURVIVES (caveats) | 1,061,465 add up, but 74% are beyond 180 days where the correction itself is wrong (3). The k/(σ√τ) prototype script is not in the repo. |
| 2 | The 7.06-point correction | **PARTLY REFUTED** | The 2013-03-12 calls are worth exercising, but the 7.06 is inflated by the dividend projection (March 2013 projected at December 2012's 1.022; SPY paid 0.694). On an ex-date eve the de-Americanised parity forward equals the carry forward at the projected amount. |
| 3 | Why PARITY_OUTLIER beyond 180 days | **REFUTED** | The 1.87% depends on the lattice's own rate; a clean synthetic chain at the pricer's own r and D gives 120/130 flagged at 700 days and F −103 bp, with 20 passes or N = 1,000: §3a's σ₀ rule settles on a biased answer. Options-implied box rates sit above Treasuries at the same tenor (van Binsbergen, Diamond and Grotteria 2022); DGS3MO is the wrong comparator for 1–2 years. 0–60 days survives. |
| 4 | Last paid is close enough | **PARTLY REFUTED** | Last paid overstates every March since 2009 by 10.9–47.3% (mean +21.4%), understates December (−13.7%) and June (−8.2%). The trailing four-quarter mean cuts the worst error from 47% to 30%. |
| 5 | PARITY_OUTLIER on European-equivalent mids | **PARTLY REFUTED** | Right as a rule (DoltHub 2023: 1,806 of 19,468 raw, 0 after), but beyond ~540 days at high rates the test measures the method's own error. |
| 6 | `quote_iv.eep` | **PARTLY REFUTED** | Two definitions in one column: ITM rows at the partner's IV, OTM rows at their own σ₀. "The strike's OTM IV" includes 1,114,724 zero-bid and 408,677 STALE IVs, all `iv_flags` 0. ADR-0004 line 100 (line 108 at round 2) still says "IV solved from the mid". |
| 7 | DoltHub's LOO error | SURVIVES | The gap is the strike grid. Reading DoltHub's smile at OptionsDX-only strikes gives 0.098/0.391, so concept 11's "in-grid error" overstates by about 1.5x. |
| 8 | The data-flow example | SURVIVES | Reads back exactly. |
| 9 | The surface frames | **PARTLY REFUTED** | The numbers hold, but `data_fingerprint` is the hash of a JSON dump of the input fingerprints, not ADR-0001 §7's, and it folds in the code hash. |
| 10 | The app validator | **REFUTED** | 11 contradictory files accepted (`p10_outcomes.txt`; 12 ACCEPTED lines, one of them the committed baseline); the badge hard-codes "(OptionsDX)"; no licence notice or DATA.md link in the app; LICENSE-DATA.md calls the SPY and VIX closes "our own measurements" and gives surface_frames.json no licence. |
| 11 | ADR-0004's model-mark band | SURVIVES | |
| 12 | The docs | **PARTLY REFUTED** | 58 file:line references right; wrong: the 480.3 s row, an unrendered "{R}", "2023 has the fewest outliers", "1-4 days" (2-4), the data_fingerprint wording, concept 07's F N(d1) reading, "the error in σ₀ is second order". |
| — | Outside the claims | — | DGS3MO timing (code 9b); the Data Quality page shows DoltHub-derived numbers without the CC BY-SA attribution; projected ex-dates past the session list keep holiday Fridays. |

## Verifier

9 of 11 rows AGREE. DISAGREE: `check_tracked_data` printed 298 files, the walkthrough 297 (the walkthrough itself); the build-time row (above). Notes: the top six corrections are 2–4 days before expiry, not 1–4; guess 7's band also holds 2017 (+0.93) and 2019 (+0.65), and 2022 is 0.63 points below DGS3MO. Its mutant reruns: 5 killed as stated; the two "equivalent" ones survive the eight files.

## Fixes, one per refutation

Each fix is a decision of the orchestrator's brief (D1-D13, defaults taken 2026-10-29, the owner can override), recorded in the walkthrough's decisions, LEARNING_LOG.md's "Defaults taken" and the ADR it amends.

| Refutation | Fix | The test that fails without it |
|---|---|---|
| Design 3, code 6, code 12 (one pass) | **D1.** The premium at each quote's own American IV on the lattice, in one pass (`src/volbt/pricing/deam.py`, `chain.py`); ADR-0008 amendment 1. | `tests/test_forward.py::test_a_clean_long_dated_american_chain_is_not_a_parity_outlier` (9 chains), `test_de_americanisation_removes_the_forward_bias_at_5_22_percent`, `tests/test_real_pricing.py` (real snapshots) |
| Code 3, code 6 | **D2.** σ_eff = max(σ, 2\|r\|√dt, 1e-4) in every lattice; `parity_median5_raw` and `SMILE_FORWARD_RAW` when the forward cannot be de-Americanised; American fail codes. | `tests/test_lattice.py::test_the_up_probability_stays_inside_0_1_at_any_sigma`, `::test_a_sigma_below_the_floor_gives_a_finite_price_not_nonsense`, `tests/test_chain.py::test_a_forward_that_cannot_be_de_americanised_says_so` |
| Code 9b | **D3.** The DGS3MO value dated strictly before the quote date (`build.rate_on`); ADR-0008 amendment 3. | `tests/test_pricing_build.py::test_the_rate_is_the_last_one_dated_strictly_before_the_quote_date` |
| Design 2, 4; code 4 minor | **D4.** The same quarter a year earlier times trailing growth (`dividends.projected_amount`); NYSE Good Friday and Juneteenth past the last bar; ADR-0008 amendment 4, ADR-0003. | `tests/test_forward.py::test_the_amount_is_the_same_quarter_a_year_earlier_times_the_trailing_growth`, `::test_past_the_last_session_nyse_holidays_still_move_the_ex_date`, `tests/test_real_pricing.py::test_the_dividend_rule_is_the_best_of_the_four_in_a_no_look_ahead_backtest` |
| Code 7 | **D5.** The calendar floor in `surface_iv` (revised in round 2, E1, and its bit renamed) (running maximum of w(k), the monotone envelope of step 5), bit `SURFACE_CALENDAR_FLOOR`; τ ≤ 0 returns NaN; ADR-0004 amendment 2. | `tests/test_smile.py::test_w_never_falls_with_tenor_at_any_k_on_random_surfaces`, `::test_the_floor_holds_w_at_a_crossing_and_says_so`, `tests/test_export_surface.py::test_the_committed_file_never_has_total_variance_falling_with_tenor` |
| Design 6, code 9a | **D6.** `eep` = own premium at own American IV; `eep_partner` for PARITY_OUTLIER; `in_smile`; ADR-0004 amendment 1. | `tests/test_chain.py::test_two_premiums_two_columns`, `tests/test_pricing_build.py::test_a_zero_bid_or_stale_quote_gets_an_iv_but_enters_neither_the_forward_nor_the_smile` |
| Code 2 | **D7.** Relative price and σ tolerances, the OTM side, "unresolved"; ADR-0008 amendment 5. | `tests/test_iv.py::test_a_tiny_otm_price_gets_its_true_sigma_not_the_clipped_guess`, `::test_an_itm_price_one_float_step_above_its_lower_bound_is_unresolved`, `::test_a_price_on_a_flat_stretch_is_unresolved_not_converged_far_from_its_root` |
| Code 10 | **D8.** The fingerprint covers every volbt module the build imports, numpy/scipy/pandas/pyarrow/duckdb and Python, and the store's write settings; orphan partitions are deleted. | `tests/test_pricing_build.py::test_the_fingerprint_covers_every_volbt_module_the_build_imports`, `::test_a_new_library_version_reprices_every_partition`, `::test_a_new_store_write_setting_reprices_every_partition`, `::test_a_pricing_partition_whose_quotes_are_gone_is_deleted` |
| Code 12 | **D9.** A test for each surviving mutant (table in the walkthrough, "Mutation runs"). | listed there |
| Design 10 | **D10.** `parseSurfaceFrames` refuses all 11 real contradictions; the badge reads `run.data_source`; data notices on the Surface and Data Quality pages. | `app/src/lib/surfaceFrames.test.ts` (60 of 60 mutants of the new checks killed) |
| Design 9, 10 | **D11.** `data_fingerprint` in ADR-0001 §7's form over the frames' input files, apart from `config_hash`; LICENSE-DATA.md and DATA.md name Yahoo and Cboe values and their terms and the terms of surface_frames.json. | `tests/test_export_surface.py::test_the_data_fingerprint_is_adr_0001_s_list_of_input_files` |
| Design 12, verifier | **D12.** Every number of the walkthrough re-measured on the rebuilt store; concept notes 07-11 corrected. | the walkthrough's commands |

## Mutants after the fixes

A scratch copy of the repository (`rsync -a --exclude /data --exclude node_modules --exclude .venv`, with its own `uv sync --offline --frozen` environment), each mutant written into the copy, its test files run with `pytest -q -x`, and the file restored and checked against the real repository's SHA-256. The runner and its output are in the session scratchpad (`fix2/mut/run_mutants.py`, `mutants.out`).

| Set | What | Killed |
|---|---|---|
| C | The code reviewer's 23 mutants (`mutants_12.py`), each at the same place in the new code, against its 9 test files | **22 of 23** |
| W | The walkthrough's original 40, against its 8 test files. "No de-Am passes" and "one de-Am pass" now mutate the one-pass solve: no de-Americanisation, and the premium at the starting σ instead of the American IV. "The rate from the day before" is now "the rate dated on the day itself" | **40 of 40** |
| N | 22 mutants of the round-1 fixes: no American solve; the forward from every pair; no lattice guard; no `parity_median5_raw` label; last paid amount; no NYSE holidays; no calendar floor; plain step 5 past the back expiry and before the front one; τ ≤ 0 raises; no rounding bump; no time-value resolution check; Newton on the price alone; no pinned check; an ITM price solved on its own side; the fingerprint without library versions, without store settings, without `data/store.py`; orphan partitions kept; the data fingerprint over every partition; `data_last_date` dropped; `eep` kept on every attempted quote | **22 of 22** |

The ten survivors the brief named are all killed now, each by its own test: M5 (`test_a_dividend_exactly_at_a_node_time_has_gone_ex_at_that_node`), M10 (`test_the_call_at_a_strike_equal_to_the_forward_is_the_otm_quote`), M11 (`test_iv_fail_when_the_american_iv_exists_but_the_european_mid_has_no_black_76_iv`), M12 (`test_two_premiums_two_columns`), M15 (`test_the_cross_expiry_flag_marks_a_k_beyond_either_smile`), M16 (`test_a_smile_whose_nodes_miss_k_0_says_so`), M18 (`test_the_summary_tenor_buckets_have_their_edges_in_the_right_bucket`), M19 (`test_a_change_in_a_reference_table_reprices_every_partition[dividends]`, parametrized by a literal list after the run showed that parametrizing over `REFERENCE_TABLES` itself let the mutant remove its own case; checked on its own in the scratch copy: `1 failed, 2 passed`), M20 (`test_a_quote_with_a_zero_ask_has_no_mid_and_no_iv_fail`), M21 (`test_the_summary_counts`, and the tenor test).

**The one survivor, C-M22 (the Newton start guess without DF), is a near-equivalent mutant.** The guess only sets where Newton starts, and is clipped to [0.01, 3]; on the 5,000-case property set the mutant changes no fail code, moves no IV by more than 1.9e-10, flips 10 solver labels between Newton and bisection, and raises the mean iteration count from 11.50 to 11.58 (`fix2/proto/m3_m22.py` in the session scratchpad). No test should pin an iteration count.

**The first run of the same mutants** (before four test additions) killed 80 of 86. Its survivors and what happened to each:
- C-M3 (the price tolerance loosened): the σ-step criterion still pinned σ, but answers repriced only to 1.85e-10; killed by `test_property_a_newton_answer_reprices_to_1e_10_of_its_price`, which uses a literal 1e-10, not the constant under test.
- W04 (vega without √τ): killed in the first M2 review only through an IV test's own use of `black76.vega`; killed now by `test_the_vega_function_is_the_greeks_vega_and_the_slope_of_the_price`.
- N-D5e (no rounding bump): the committed file was already bumped; killed by `test_a_frame_never_lets_rounding_make_total_variance_fall` (123 cells would fall without it).
- N-D6 (`eep` kept on every attempted quote): killed by the clean 700-day chain, where F moves several strikes from forward_raw.
- N-D7d (no reprice check after bisection): equivalent. The pinned check adds 8 times the smallest normal float to its rounding, so an answer at a price where Black-76 underflows fails it first; the reprice check was removed from `iv.py`, and the 400,000-case sweep gives the same fail counts with and without it (381,005 / 388 unresolved OTM).

**The walkthrough's earlier claim that one de-Americanisation pass is equivalent to two is withdrawn**: the review measured 3.41 bp and 16 flag flips on real snapshots, and the procedure now has no passes to count.

**App (D10):** 60 mutants of the new `parseSurfaceFrames` checks and the data notices, 60 killed, every file byte-identical afterwards (`fix2/app/mutation-output.txt`).

## Gates after the fixes (2026-10-29)

| Gate | Command | Output |
|---|---|---|
| Forced build 1 | `/usr/bin/time -f "WALL %e s, MAXRSS %M KB" uv run python tools/build_pricing.py --workers 10 --force` | `WALL 473.52 s, MAXRSS 4864148 KB`, `EXIT 0` (`data/logs/pricing_build_final_1.log`) |
| Forced build 2 | the same | `WALL 488.90 s, MAXRSS 4852956 KB`, `EXIT 0`; SHA-256 of all 68 pricing parquet and JSON files identical to build 1 (`pricing_build_final_{1,2}.sha256`) |
| Incremental run | `uv run python tools/build_pricing.py --workers 10` | `WALL 3.12 s`, 0 partitions priced, all 68 files unchanged |
| Export | `uv run python tools/export_app_data.py --store data/store` | wrote the four files of `app/public/data/` |
| Tests | `uv run pytest -q` | `849 passed, 37 deselected` |
| Real data | `uv run pytest -q -m real_data` | `35 passed, 851 deselected` |
| Notebooks | `uv run python tools/build_notebooks.py --check` | `notebooks are up to date` |
| App | `cd app && npm run verify && npm audit` | lint clean; `Test Files 26 passed (26)`, `Tests 802 passed (802)`; lines 99.61%, branches 97.23%; `✓ built`; `found 0 vulnerabilities` |
| Tracked data | `uv run python tools/licensing/check_tracked_data.py` | `clean: 0 raw vendor files in 302 files git would commit (0 size warning(s))` |
| Diagrams | `tools/diagrams/build.py docs/architecture/specs --out docs/architecture/out --check`, then `--verify-mermaid` | `ok: 7 spec(s) up to date in docs/architecture/out`; the Mermaid check passes on all 7 |
| Report | `uv run python tools/report_m2.py > data/logs/report_m2.txt` | every [report] number of the walkthrough is read from it |

## Round 2 (2026-10-29)

**Reviewers:** a code reviewer (`adversarial-reviewer`, Opus: probes on a read-only store copy, 34 new mutants), a design reviewer (`adversarial-reviewer`, Opus: synthetic chains, the real store read-only, a copy of the app's validator) and a verifier (`verifier`, Sonnet: every gate, about 90 `file:line` references, the concepts' numbers). **Scope:** the uncommitted tree on top of 35cb682 after the round-1 fixes D1-D13. Probes in the session scratchpad (`egv/m2/r2/{code/probes,design,verify}/`); the fixes' own probes in `fix3/`.

### The orchestrator's own verification, before acting

- **Design 1 (the calendar floor).** Read `smile.py`: `floor = np.maximum.accumulate(w_own, axis=0)` takes the running maximum over every expiry's own w, extrapolated wings included. `q2_worst.out` and `q2_nodes_core.out`: 2020-02-28, a 322-day node at k = −1.428 from 0.515 to 1.242 off the 215-day wing; in the 0-60-day, \|k\| ≤ 0.15 region 4.42% of nodes raised, 5,104 of 7,742 off an extrapolated wing. **Confirmed.**
- **Design 2 (the validator).** `q5_validator.out`: 15 contradictory files accepted; the DoltHub page showed the OptionsDX notice without CC BY-SA. **Confirmed.**
- **Code 1 (orphan deletion).** Read `build.py:309-314`: the deletion loop ran over every pricing partition before the `sources`/`years` filter, with keys from the live option_quotes only, so an empty option_quotes deleted everything. **Confirmed.**
- **Code 2 (American IV).** Read `deam.py:112`: `done = abs(gap) <= tol` converges on the price alone. `c1_mech.out`: P470-P476 σ_A 0.0836-0.0930 against a truth of 0.08 at the same N, premium 15.72 against 16.54, A flat in σ. **Confirmed.**

### Code reviewer, per claim

| # | Claim attacked | Verdict | Evidence |
|---|---|---|---|
| C1 | Orphan deletion is safe | **REFUTED** (medium) | It ignored the filters (mutant R31 survived the suite); with no option_quotes it deleted all 21 files, then crashed; a symlinked quotes partition made live pricing "orphan" and deleted it; a `.tmp` leftover did the same; a symlinked pricing table had files deleted outside the store; a stray folder crashed the build half-way through its deletions (`c7_orphans*.out`). |
| C2 | The American IV solve converges to the quote's σ | **REFUTED** (medium, latent) | On a flat stretch of A(σ) (immediate exercise) it "converged" at any σ with `FAIL_NONE`: σ 0.08 at 700 days F −74 bp, 198 of 244 flagged; r 10% −53 bp. No real case found in the store. Mislabels: `deamericanise=False` said `parity_median5_deam`; a NaN, zero or negative mid and τ ≤ 0 said `american_below_floor`; a NaN spot, strike or rate said `american_no_convergence` after 40 walks; a NaN dividend was dropped silently (`c1_*.out`). |
| C3 | D5: "the floor never lowers" | **REFUTED** | False before the front expiry (832,782 cells lowered on random surfaces, all flagged); a NaN node spread to every later tenor; unsorted expiries made w fall (`c5_surface.out`). |
| C4 | D7: every answer to 1e-10 | **PARTLY REFUTED** | OTM within 9.99e-11; ITM 4,666 of 101,038 worse than 1e-10 (worst 2e-7), and 4,418 of 11,769 ITM "unresolved" were resolvable (the fixed `TIME_VALUE_RESOLUTION` cut). No build effect (`c6_iv.out`). |
| C5 | The tests kill the fixes' mutants | **PARTLY REFUTED** | 34 new mutants, 10 survived: R2, R3 (near-equivalent), R4, R6, R20, R23, R24, R27, R28, R31 (`mutants_r2.out`). Weak tests: the up-probability test asserted on a copy of p; the code-change test monkeypatched `code_fingerprint`; the clean-chain tests were self-consistent (truth and procedure on one lattice) and none was below σ 0.12. |
| C6 | The summary is deterministic | **PARTLY REFUTED** | Float aggregates differed by 1.8e-15 between runs at 20 threads (`avg`); only the 6-digit rounding hid it (`c9_threads2.out`). |
| — | Lattice equality old against new; speed; the lattice guard; no look-ahead; fingerprint coverage; 68-file determinism; peak memory | SURVIVES | 8.5e-14, 2.0-2.9×; worker 1.68 GB, the summary's join 4.84 GB. |

### Design reviewer, per claim

| # | Claim attacked | Verdict | Evidence |
|---|---|---|---|
| R1 | The calendar floor only removes arbitrage | **REFUTED** (high) | Driven by shorter expiries' extrapolated wings: 33,871 nodes moved (5.82%), 26,494 of them (78.2%) off a wing, up to 72.76 vol points (`q2_*.out`). |
| R2 | The validator refuses contradictions | **REFUTED** | 15 accepted (A, A2 with the bit-8 excuse, B, C, D, D2, E, F, G, H, I, J, K, L, M); the DoltHub notice missing (`q5_validator.out`). |
| R3 | `config_hash` names the code of the data | **REFUTED** | A `--year` build after a code change left stale partitions while the summary named the new code; the export only checked that the inputs file existed. |
| R4 | Long-dated PARITY_OUTLIER is a rate problem the docs explain | **PARTLY REFUTED** | The mechanism: the deep-ITM side's premium at its partner's IV pins F_K to the lattice's carry forward; a per-expiry carry-consistent rate cleared 3,600 → 356 of 16,768 over 8 dates; "a rate fix alone would not clear them" wrong; guess 7's "−0.55 points in 2022" contaminated; the flag does nothing downstream; F moves up to +42.5 bp (949 days), ATM IVs a median 0.10-0.22 points; 82,751 of 568,856 deep-ITM call mids below S − K (`q3_*.out`). |
| R5 | D4's dividend rule is the best | **PARTLY REFUTED** | Its edge over the trailing mean is noise (CI [−2.88, +0.51]); a fifth rule scored 6.20%; 6-8 quarters ahead worse than last paid (`q1_dividends.out`). |
| R6 | ADR-0004 amendment 1 | **REFUTED** | An `in_smile` quote's own IV is not "the surface's value there" (5.82% of nodes differ); "may" leaves two greeks; the \|k\| ≤ 0.15 American band undecided. |
| R7 | The 60-day bound | **REFUTED** (docs) | The test comment and walkthrough cite 0.0043 (the old method); the new method gives 0.0109/0.0047/0.0032/0.0029 at N = 200/500/1,000/2,000; ADR-0008 still promised 0.0075-0.010 and a 0.01 gate. |
| R8 | The licence text | **REFUTED** | Cboe's terms forbid publishing without written consent, yet the app said "used under Cboe's terms"; Yahoo's "personal use only" omitted; OptionsDX's terms page 404; concept 09 quoted DoltHub counts without the notice. |
| R9 | The docs' statements | **REFUTED** | "A rate error leaves F alone" (concept 07, ADR-0008); "linear in w adds no butterfly arbitrage" (`q7_butterfly.py`); "the nodes are clean"; the walkthrough's "Not done" omits the floor problem. |
| R10 | ADR-0008 amendment 3 | minor | No carve-out for M1's on-or-before cross-vendor rule. |

### Verifier

Every gate **AGREE**; about 90 `file:line` references hold; 11 concept numbers AGREE. DISAGREE (wording): V1 "SUM(n_points − 2) by tenor agrees" needs `WHERE n_points >= 5`; V2 the ledger's `build.py:243-256` is historical; V3 "(a to k of the ledger)" refers to a list the ledger does not have; V4 "12 contradictory files" is 11 (one ACCEPTED line is the baseline), and ADR-0004 line 100 is now 108. Not reproducible: V5 1,778 against 1,806 of 19,468; V6 "$0.33 of premium in a $0.335 call" (today's lattice gives $0.255-0.256); V7 "a European sum of −4e186"; V8 the round-1 numbers (835,088; 17/18/2/10; 16 flips; −103/−101 bp) are only confirmed from recorded output. V9 "83 to 275 bp" against −275.5: rounding, fine.

### Fixes (decisions E1-E14, defaults taken 2026-10-29)

Each fix names the test that fails without it: the mutant that kills it, from the run below.

| Finding | Fix | Killed by |
|---|---|---|
| R1, C3 | **E1.** `smile.calendar_variance`: anchored (quoted) values take the running maximum of anchored values; extrapolated values clamped between the anchored floors before and after; a final running maximum; NaN is missing (`np.fmax`); `surface_iv` sorts its expiries; bit 8 renamed `SURFACE_CALENDAR_ADJUSTED` (moved up or down) in Python, the contract, the app and the docs. Real store, 250 dates: 9,088 OptionsDX nodes moved (1.56%), 0 by an extrapolated wing; 0-60 days \|k\| ≤ 0.15: 3,270 (1.87%); largest +41.98 vol points, a quoted crossing. The exporter now refuses a frame rounding cannot mend. | E1a, E1b, E1d-E1k, N-D5a-c, R16, R17, R20, R21 (E1c is equivalent, below) |
| C1 | **E2.** Deletion only on an unfiltered build; no option_quotes partition raises before anything is read or deleted; `Store.checked_partitions` refuses a symlink anywhere in the four tables, a path resolving outside the store root, a stray file or folder and a partition without `part-0.parquet`; the whole plan is checked before the first deletion; `delete_partition` refuses a symlinked or escaping target. | E2a-E2i, R34, N-D8d |
| C2 | **E3.** Identified = the price clears the tolerance AND dA ≥ dE/2 (the second condition beyond the brief's default: with the first alone a truth on N = 2,000 left the σ 0.08 chain 42 bp low); the partner's identified American IV prices an unidentified quote's premium, else `american_unidentified` and out of the forward; `american_no_mid`, `american_expired`, `american_bad_input` (at once, no walk); `parity_median5_raw` for `deamericanise=False`. 20 clean chains, truth N = 2,000: 0 flagged, \|F\| ≤ 7.73 bp (exact with the truth on N = 200). | E3a-E3k, R2, R3, R4, R6 |
| R2 | **E4.** The app refuses 12 of the 15 (A, A2, B, C, D, D2, E, F, H, I, J, M), plus three rules derived from the contract (whole-row `SURFACE_CROSS_EXPIRY` with the expiry count, strike-extrapolation runs from the row's edges, two bit-8 rules); G (a DoltHub file), K (bit 8 on a row that sits on a listed expiry) and L (labels are hand-written) accepted, each with a test giving the reason. The Surface page's notice follows `run.data_source`. | the app's 41 mutants (41 killed: 37 of the E4 agent's, and 4 of the extrapolated-cell IV ceiling added after this round's own review of E4; the gate line "killed 41 / 41") |
| R3 | **E5.** `pricing_inputs.json` records `{code, inputs}` per partition; `pricing_problems`/`require_current` refuse a summary or an export while any partition is unpriced, orphaned or priced by older code ("partitions priced by older code: run a full build"); a refused build removes the stale summary. | E5a-E5g |
| R4 | **E6.** ADR-0008 amendment 8 (Proposed: draft for owner review): a per-expiry carry-consistent rate; M2 keeps DGS3MO; strategies at most 180 days until the owner decides. Walkthrough, concept 10 and guess 7 rewritten; the parity-implied-rate claims withdrawn. | docs |
| R5 | **E7.** Kept; the limits stated in `dividends.py`, ADR-0008 amendment 4 and the walkthrough. | docs |
| R6 | **E8.** ADR-0004 amendment 1: an `in_smile` quote's greeks use its own IV; American marks at every \|k\| from M3 (ADR-0004 rule 3, ADR-0008 §8). | docs |
| R7 | **E9.** 0.0109/0.0047/0.0032/0.0029 re-measured ([report] "the 60-day case by the procedure's step count"); ADR-0008 and the test comment restated; 0.0043 removed. | docs |
| R8 | **E10.** DATA.md: Cboe's terms (prior written consent to publish), the files that carry VIX values listed "for owner review", yfinance's "intended for personal use only", OptionsDX's known facts; the app no longer says "used under Cboe's terms"; concept 09's notice; the DoltHub-derived document list. | docs |
| R9, R10 | **E11.** Concept 07 and ADR-0008 on the rate (0.53 bp, +42.5 bp); concept 11 on butterflies and "clean" nodes; the walkthrough's "Not done"; ADR-0008 amendment 3's carve-out. | docs |
| V1-V9 | **E12.** Each corrected in the walkthrough, concepts and this ledger (V8: the round-1 numbers are labelled "round-1 measurement"). | docs |
| C4, C5, C6 | **E13.** The ITM path's pinned check counts the rounding the time value inherits, from the ITM price's own Black-76 terms (no fixed cut; 200,000 random ITM prices all within 1e-6, max 4.6e-8); the docs say where 1e-10 holds; tests for R4, R6, R20, R23, R24, R27, R28, R31; `lattice.up_probability` deleted, `crr` returns the p it walked with; the code-change test edits a fingerprinted file in a copy; the summary's mean is exact (rational), so no float aggregate depends on thread order. | E13a-E13e, R22-R25, R27, R28, C-M3, C-M4, N-D7a-c, N-D7e |

### Round 2, mutants after the fixes

Run by `scratchpad/fix3/mut/run_mutants_r2fix.py` in four scratch copies, each file restored and checksummed; the iv.py set and five re-tested mutants again by `run_followup.py` and `run_followup2.py` after the last code and test changes; every verdict in `mutants_final.out`.

| Set | Mutants | Killed | Survivors, and why each is acceptable |
|---|---|---|---|
| Round 1 code reviewer (C) | 23 | 22 | C-M22, the Newton guess without DF: near-equivalent (no IV moves by more than 1.9e-10, round 1) |
| Round 1 walkthrough (W) | 40 | 39 | W39, the partition fingerprint without the code: equivalent now, because `pricing_inputs.json` records the code fingerprint and the skip compares it directly (E5g, which breaks that comparison, is killed) |
| Round 1 fixes (N) | 22 | 22 | — (N-D5a-c, N-D7a and N-D8d at the sites the round-2 fixes rewrote) |
| Round 2 code reviewer (R) | 34 | 33 | R31, deletion honouring the filters: equivalent now, because a filtered build never reaches the deletion; its live form, a filtered build that deletes (E2a), is killed. R2, R3, R4, R6, R20, R23, R24, R27, R28, which survived round 2, are killed |
| Round 2 fixes (E) | 45 | 42 | E1c, extrapolated values never floored: equivalent, the final running maximum already lifts each to the anchored floor before it. E2j and E2k, the plan's re-check and the comparison of the two listings of option_quotes: defence in depth that `Store.checked_partitions` makes unreachable (it refuses every state they would catch, first) |
| **All** | **164** | **158** | |

The first run killed 151 of 163. E2c, E2d, E2g, E5c and E13d survived it because their tests matched a word the pytest folder name also contains ("symlink", "outside") or did not exist (a stray file between partition folders, an unpriced quotes partition, the p `crr` reports): the tests now match the exact message and were added, and all five are killed. E13a and E13e (the ITM time value's rounding ignored, or counted from the OTM side's terms) survived the follow-up until `tests/test_iv.py` pinned four ITM prices that the weaker estimate "solved" up to 1.5e-6 off; both are killed.

### Round 2, gates after the fixes (2026-10-29)

| Gate | Command | Output |
|---|---|---|
| Forced build 1 | `/usr/bin/time -f "WALL %e s, MAXRSS %M KB" uv run python tools/build_pricing.py --workers 10 --force` | `WALL 790.05 s, MAXRSS 5250560 KB`, `exit 0` at load average 10.91 (`data/logs/pricing_build_r2_4.{log,load}`) |
| Forced build 2 | the same | `WALL 618.13 s, MAXRSS 5254616 KB`, `exit 0` at load average 37.37; SHA-256 of all 68 pricing parquet and JSON files identical to build 1 (`pricing_build_r2_{4,5}.sha256`) |
| Incremental run | `uv run python tools/build_pricing.py --workers 10` | `WALL 3.77 s`, 0 partitions priced, all 68 files unchanged (`pricing_build_r2_6.sha256`) |
| Export | `uv run python tools/export_app_data.py --store data/store` | wrote the four files of `app/public/data/`; `surface_frames.json` 42,697 bytes, `config_hash` d0c8a0357555… |
| Tests | `uv run pytest -q` | `923 passed, 37 deselected` |
| Real data | `uv run pytest -q -m real_data` | `35 passed, 925 deselected` |
| Notebooks | `uv run python tools/build_notebooks.py --check` | `notebooks are up to date` |
| App | `cd app && npm run verify && npm audit` | lint clean; `Test Files 27 passed (27)`, `Tests 887 passed (887)`; lines 99.64%, branches 97.48%; `✓ built`; `found 0 vulnerabilities` |
| Tracked data | `uv run python tools/licensing/check_tracked_data.py` | `clean: 0 raw vendor files in 304 files git would commit (0 size warning(s))` |
| Diagrams | `tools/diagrams/build.py docs/architecture/specs --out docs/architecture/out --check`, then `--verify-mermaid` (with `DIAGRAM_KIT_CHROMIUM` and `DIAGRAM_KIT_MERMAID_JS` set) | `ok: 7 spec(s) up to date in docs/architecture/out`; `mermaid 12.2.0: 7 spec(s) checked` |
| Report | `uv run python tools/report_m2.py > data/logs/report_m2.txt` | `exit 0`; every [report] number of the walkthrough is read from it |
| App mutants | `scratchpad/fix3/app_mutants_run_e4fix.py` | `killed 41 / 41`, three files restored byte for byte (37 of the E4 agent's, and 4 of the extrapolated-IV ceiling added after this round's own review of E4) |

**Reviewed after the fixes.** An `adversarial-reviewer` (Opus) attacked E4 and E10 after they were delegated. It confirmed the 12 refusals and 3 acceptances, the derived flag rules on 4,901 exported frames, and the licence text; it refuted the validator's IV ceiling of 5 for every cell (the exporter's Lee-clipped wing can read 5.07 at 7 days and k = −0.30: 24 of 4,500 random exported surfaces would have been refused), a comment claiming the 1e-12 calendar slack absorbs nothing a 1e-6 IV step makes (6.7e-14 falls pass), and the Surface page intro naming OptionsDX on a DoltHub file. Fixed: a quoted cell is still bounded by 5, an extrapolated one by `MAX_EXTRAPOLATED_IV` = 10 (above the 8.8 a wing can reach on this grid, below a percent mistake); the comment corrected; the intro names no vendor. The one gap it found in DATA.md's VIX list (a rounded "65" in `docs/concepts/00-background.md`, repeated in `docs/architecture/graph/graph.json`) is added to the list.

## Round 3 (2026-10-29)

**Reviewers:** a code reviewer (`adversarial-reviewer`, Opus: probes on a read-only store copy, its own mutants N1-N14 in a scratch copy) and a docs, licence and app-validator reviewer (`adversarial-reviewer`, Opus, with two forks for claim 1 and claims 9-10). **Scope:** the uncommitted tree on top of 35cb682 after the round-2 fixes E1-E14. The code reviewer attacked E1-E3, E5 and E13; the docs reviewer E4, E6-E12 and E14. Probes in the session scratchpad (`egv/m2/r3/{code/probes,docs}/`); the fixes' own probes in `fix4/`.

### The orchestrator's own verification, before acting

- **Code claim 6 (provenance).** Read `build.py:354`: `pricing_problems` compared only `recorded[k]["code"]`. Read `e5_quotes_rewritten.out`: quotes ×1.30 with the code unchanged, the summary and the export ACCEPTED, the frame kept the old IV. **Confirmed.**
- **Code claims 4 and 5 (the partner).** Read `chain.py` `solve()`: the partner's IV was used only if already attempted (`np.isfinite(am_iv[partner])`), with no solve on demand. Read `e3_chains_outside_grid.out`. **Confirmed.**
- **N-1 (WIDE nodes).** Read `e1_worst2.out`: 2014-09-15, the 2014-09-26 puts at 171-175.5, bid 0.03-0.05, ask 4.83-4.84, quality_flags 544 (WIDE | VOLUME_UNRELIABLE), `in_smile` True, IV 0.80-0.87 against 0.33-0.38 at the tight neighbours. WIDE = ask − bid > mid (`flags.py:39`). `e1_wide_driver.out`: 10,625 of 581,755 nodes WIDE (1.8%). **Confirmed.**
- **N-3 (empty filters).** `e2_attacks.out`: `sources=[]` and `years=[]` each deleted 3 orphan files; `build.py:395` read `if not sources and not years`. **Confirmed.**
- **Docs claim 1 (validator).** T1: `contract.ts:1305-1308` allowed an IV above `MAX_IV` with any extrapolated bit. N4: `export_app_data.py:100` hard-coded "(OptionsDX)". **Confirmed** by reading.
- **Docs claim 6 (licence).** README:79-81 said "not redistributed, except the four ... closes" for Yahoo and Cboe; `grep -c "CC BY-SA"` gave 0 in ADR-0004, ADR-0002 and concept 05 while ADR-0004:9-12 quoted DoltHub measurements. **Confirmed.**
- **Docs claim 5.** ADR-0008:138 said "r enters only through DF, because the forward comes from parity". **Confirmed.**

### Code reviewer, per claim

| # | Claim attacked | Verdict | Evidence |
|---|---|---|---|
| 1 | E1: quoted values beat extrapolated ones | SURVIVES (but see N-1) | 9,088 nodes moved (1.56%), 0 by a wing, 0 down, reproduced; 1,260 fuzzed surfaces, 0 violations |
| 2 | The surface never lets w fall with tenor | SURVIVES | 0 falling w over the fuzz; the 4 committed frames 0 falling, each equal to a recomputation from the store |
| 3 | E2: orphan deletion is safe | SURVIVES, 2 Low | N-3 (an empty filter list is unfiltered), N-4 (no store lock) |
| 4 | E3: the American IV and the partner's premium | **REFUTED** | r 8%, 700 days, σ 0.12, one dividend: F −5.94 bp, 4 PARITY_OUTLIER, 2 IV_FAIL (OTM puts unidentified, partner never attempted); the region-wide bound sentence false |
| 5 | E3's tests | **REFUTED** | mutant N1 (the partner from any expiry) survived the whole suite; F bounds of 0.05 bp on measured 0.028, 0.014 and 0.003 |
| 6 | E5: provenance | **REFUTED** | quotes ×1.30 with the code unchanged: `pricing_problems` [], summary and export accepted, the frame shipped the old IV 0.180069 (a rebuild gives 0.233795); an interrupted build left a stale summary |
| 7 | E13: the solver's ITM path, the summary's determinism | SURVIVES | OTM 9.991e-11, ITM 4.588e-8 and 5.73e-8; the summary at 1 and 20 threads: 0 of 4,416 values differ |
| 8 | The round-2 mutant table | SURVIVES | 158 of 164 confirmed, the 6 equivalences hold; its own 14: 13 killed, N1 survived |
| 9 | The gates | SURVIVES | 923 passed / 37 deselected; real_data 34 (+1 dolt test not run); r2_4 == r2_5 |
| 10 | The build time's explanation | not proven | the walk ratio predicts about 623/633 s; the 790 s run was at the lower load; asked for CPU time |
| N-1 | (new, Medium) | — | WIDE stub quotes are smile nodes and anchor the calendar constraint: 160 nodes moved by more than 5 vol points (4 without WIDE); the +41.98 is an 11-day WIDE put lifting 13 expiries to 197 days (32 days 0.2647 → 0.5103) |
| N-3, N-4 | (new, Low) | — | an empty filter is unfiltered; no store lock |
| N-5 | (new, Low, unreachable) | — | +inf spreads in `calendar_variance`; two expiries at one τ resolved by list order |

### Docs, licence and validator reviewer, per claim

| # | Claim attacked | Verdict | Evidence |
|---|---|---|---|
| 1 | E4: the app's validator | **REFUTED** | T1 (IV 9.99 accepted on a bit-4-only cell), P1 (bit 8 on row `firstInside` unchecked), P6 (strike flag on rows before the front), X2 (`atm_iv_30d` capped at 5 though its cell may reach 10), N4 (the exporter's label always "(OptionsDX)": a DoltHub export is refused), N1 (`--frame` dates unsorted), X1 (a synthetic smile above 10, Low); the 41/41 app mutants ran on 5 test files, and one survives the full suite |
| 2 | E6: ADR-0008 amendments 7 and 8 | **REFUTED** (narrowly) | prfaq:85 still called every flag quote quality; the walkthrough's "0.10-0.22" lost its qualifier |
| 3 | E7: the dividend rule's limits | SURVIVES | the numbers reproduce (`q1_dividends.out` identical) |
| 4 | E8: ADR-0004 amendment 1 | SURVIVES (caveats) | |
| 5 | E9: the 60-day bound | **REFUTED** (narrowly) | ledger:38 still quoted 0.0043; ADR-0008:138 "r enters only through DF" |
| 6 | E10: the licence and terms text | **REFUTED** | Cboe's clause incomplete (also no copying, retrieval-system storage or derivative works); README:79-81 contradicted DATA.md (13 files with VIX values); the yfinance quote misattributed (its README says the API is for personal use); OptionsDX "terms" circular; about 28 files carried DoltHub-derived figures without the notice; the SPX/PUT-derived figures (00-background:253-259, ADR-0010:107) absent from DATA.md |
| 7 | E11: concept and walkthrough corrections | **REFUTED** (narrowly) | "Not done" lacked 4 of the fixer's own items |
| 8 | E12, E14: the verifier's V1-V9 and the round-2 ledger | **REFUTED** (narrowly) | V3 and V7 unfixed; the E4 row said 37 against the gate's 41; ledger:221 and walkthrough:3 overstated what was reviewed |
| 9 | The documents' numbers | **REFUTED** (narrowly) | walkthrough:7, :37, :84, :117 wrong; three numbers with no log (:207 −0.54 bp, :170 3.19/3.39, 2014-09-15 at ADR-0004:22 and :209) |
| 10 | The defaults | **REFUTED** (narrowly) | LEARNING_LOG rows 18-26 lacked "default taken 2026-10-29, owner can override"; line 46 said every row was a prfaq question |
| new | | — | the dividend limits mislead (the sum-of-dividends metric favours the rule at h = 6 and 8); the deep-ITM shortfall needs its size; stale \|k\|-band text at ADR-0003:117 and ADR-0008:131; "M3 plan D5" points outside the repo; prfaq:118-119; `tools/report_m2.py:324-350` still printed the withdrawn −0.55 block |

Measured by the docs reviewer and used below: Cboe's terms (www.cboe.com/terms, updated 2022-11-16); yfinance's README; optionsdx.com/terms-of-service/ HTTP 404; the deep-ITM shortfall (82,751 of 568,856 below S − K; median $0.06; 8,563 by more than 0.10% of S); the sum-of-dividends error table.

### Fixes (decisions F1-F14, defaults taken 2026-10-29)

Each fix names the test that fails without it: the mutant that kills it, from the run below. The decisions are recorded in the walkthrough's decision 17, `LEARNING_LOG.md` defaults 27-34 and the ADR each amends.

| Finding | Fix | Fails without it |
|---|---|---|
| Code 6 | **F1.** `pricing_problems` requires every option_quotes partition's record to equal `{"code": the current code fingerprint, "inputs": partition_fingerprint(...)}`; `build_pricing` removes `pricing_summary.json` after the empty-store check and before any deletion or write, so an interrupted build leaves none and the export refuses. Provenance is what `pricing_inputs.json` records, not signed (ADR-0001 amendment 2, ADR-0008 amendment 11). The export's wall time: 0.85, 0.89, 0.93 s before, 2.58, 3.50, 3.76 s after (one SHA-256 pass over 0.5 GB of option_quotes; load average 8.8 at the start of the second set). | `tests/test_pricing_build.py::test_quotes_rewritten_with_the_code_unchanged_are_refused_by_the_summary_and_the_export`, `::test_a_changed_reference_table_is_refused_until_every_partition_is_repriced`, `::test_a_build_interrupted_after_deleting_orphans_leaves_no_summary_and_the_export_refuses`, `::test_the_summary_is_removed_before_the_build_deletes_or_writes_anything` (mutants F1a-F1c, E5f) |
| N-1 | **F2.** A WIDE quote keeps its IV and may enter the forward, but is not a smile node (`build.NOT_SMILE`, `price_chain(smile_ok=...)`; ADR-0004 amendment 3, ADR-0008 amendment 10, ADR-0009 bit 5). Rebuilt store: 137,754 of 7,870,569 valid OTM OptionsDX quotes WIDE; 137,750 nodes left 37,431 smiles; 1 smile fell below 5 nodes; on the 250 dates 7,278 of 571,130 nodes moved (1.27%), 0 down, 0 by a wing, 4 by more than 5 vol points, the largest +7.51 (2020-07-23, a quoted crossing of the 18- and 20-day 160 puts), exactly the reviewer's prediction (571,130, 7,278, 4); frames' moved cells 67, 80, 28, 24. WIDE pairs in the forward: among the 5 median strikes of 16 of 93,857 parity expiries; leaving them out would move those forwards by at most 2.38 bp (`fix4/f2/`) | `::test_a_wide_quote_keeps_its_iv_and_its_pair_but_is_not_a_smile_node`; `tests/test_real_pricing.py::test_the_solve_rate_over_valid_otm_quotes` (mutants F2a-F2d) |
| Code 4 | **F3.** `chain.solve` solves an unidentified quote's partner when no earlier step had (ADR-0008 amendment 9). The 160-chain grid: 29 chains failed above half a tick before, 1 after (pinned with its cause); the region-wide bound sentence struck in ADR-0008 amendment 7 and concept 10. The real store: forwards byte-identical, quote_iv identical but for `in_smile` | `tests/test_deam.py::test_an_otm_quote_s_partner_is_solved_when_no_earlier_step_attempted_it`, the 28 clean chains (mutants F3a, F3b) |
| Code 5 | **F4.** `test_a_flat_quote_s_partner_comes_from_its_own_expiry` (two expiries, the same strikes); `CLEAN_CHAINS` from 20 to 28, each F bound the measured value × 1.25 rounded up at two significant digits with the value in its comment; test 8, the 0.25% case, the 60-day case and the exact chains likewise (`fix4/f3/measure_listed.out`, `other_bounds.out`) | the reviewer's mutant N1 (killed), F4a, F4b |
| N-3 | **F5.** Unfiltered means `sources is None and years is None`; an empty list raises ValueError before anything is read or deleted (ADR-0001 amendment 3) | `::test_an_empty_filter_list_raises_before_anything_is_read_or_deleted` (F5a) |
| N-4 | **F6.** One writer at a time, documented: ADR-0001 amendment 4, the walkthrough's "Not done" | docs |
| N-5 | **F7.** `calendar_variance` treats ±inf as missing; `surface_iv` raises on two expiries within 1e-12 years (ADR-0004 amendment 4) | `tests/test_smile.py::test_an_infinite_w_is_missing_like_nan`, `::test_two_expiries_at_the_same_tau_are_refused` (F7a-F7c) |
| Code 10 | **F8.** CPU time with wall time on the forced builds, and the load average sampled every 30 s (`fix4/run_build.sh`); the walkthrough states the cause only as far as that measures it | gates below |
| Docs 1 | **F9** (delegated to an Opus agent, reviewed by the fixer against its evidence). One IV-ceiling rule in `contract.ts` and the exporter (above 5 only with SURFACE_EXTRAP_STRIKE, or a calendar-adjusted cell past the back expiry; 3,248 such cells above 5 on 60,000 random surfaces through the exporter, none with bit 4 alone); `atm_iv_30d` at its cell's ceiling; bit 8 and strike flags on a proven front row and along tenor; the label from the data source; `--frame` sorted, a repeated date refused; the exporter refuses a frame above its ceiling (ADR-0001 amendment 5). P1 and P6 as stated were false of the exporter (on seed 7: 670 frames with bit 8 on a first inside row that is not the front, 711 cells with a front-row strike bit the earlier rows lack), so the rules check what it does write | the app's mutants (below) and 20 Python mutants of the exporter (20 killed) |
| Docs 6 | **F10, F11** (delegated to a Sonnet agent, checked by the fixer). Cboe's terms clause and the computed Cboe statistics for owner review; the yfinance and OptionsDX text; README points to DATA.md's list; DATA.md's short-form CC BY-SA notice under the title of 23 documents (every file of the reviewer's list), the graph files listed in DATA.md | docs |
| Docs 2, 5, 7-10 | **F12.** prfaq:85 and :117-119; walkthrough:205 with the qualifier and the 8 per-date medians; ledger:38 superseded; ADR-0008 "r enters only through DF" struck; "Not done" with the four missing items and this round's; V3 (the eleven files listed), V7 (labelled, not reproduced); the E4 row 41; what was reviewed (ledger, walkthrough:5); walkthrough :7, :37, :84, :117; the three numbers with no log (the −0.54 bp now [report] "the sigma 0.08 chain by the procedure's step count", −0.538 bp; 3.19/3.39 removed; 2014-09-15 replaced by the rebuilt store's largest move); LEARNING_LOG rows 18-26 and its intro; default 26's determinism in ADR-0001 amendment 1 | docs |
| New | **F13.** Both dividend metrics (the sum of the next 6 and 8 dividends: 9.11 and 10.62% against last paid's 10.47 and 11.07%) in ADR-0008 amendment 4 and the walkthrough; the deep-ITM shortfall (median $0.060, p90 $0.265; 8,563, 1.51%, by more than 0.10% of S) in [report] and the walkthrough; the stale \|k\|-band text at ADR-0003 and ADR-0008 struck; "M3 plan D5" → "decided for milestone 3"; `tools/report_m2.py`'s withdrawn parity-implied-rate block deleted | docs |
| — | **F14.** This section | — |

### Round 3, mutants after the fixes

Run by `scratchpad/fix4/mut/run_mutants_r3fix.py` in four scratch copies (`rsync` without `/data`, `node_modules`, `.venv`, `.git`; each with its own `uv sync --offline --frozen`), every earlier set through the round-2 runner, re-targeted where round 3 rewrote the site (E1e, E2a, E5f, R31, W23, R11); each file restored and checksummed equal to the real file; a mutant that survives its targeted files is run on the whole default suite before it is called a survivor. Every verdict is in `fix4/mut/mutants_r3_all.out` and `followup_r3.out`.

| Set | Mutants | Killed | Survivors, and why each is acceptable |
|---|---|---|---|
| Round 1 code reviewer (C) | 23 | 22 | C-M22, the Newton guess without DF: near-equivalent (round 1) |
| Round 1 walkthrough (W) | 40 | 39 | W39, the partition fingerprint without the code: equivalent (the record compares the code itself) |
| Round 1 fixes (N) | 22 | 22 | — |
| Round 2 code reviewer (R) | 34 | 33 | R31: equivalent (a filtered build never reaches the deletion; its live form E2a is killed) |
| Round 2 fixes (E) | 45 | 42 | E1c (implied by the final running maximum), E2j and E2k (defence in depth that `Store.checked_partitions` makes unreachable) |
| Round 3 code reviewer (V, N1-N14) | 14 | 14 | — (N1, which survived round 2's suite, is killed by `test_a_flat_quote_s_partner_comes_from_its_own_expiry`) |
| Round 3 fixes (F) | 16 | 15 | F5b, the deletion branch on truthiness: equivalent behind F5's guard, which raises on an empty list first |
| **All** | **194** | **187** | |

What the run found about the tests themselves:
- **W23 and R11** (`in_smile` without `valid`) survived the whole suite at first: the build passes `smile_ok = not WIDE and not invalid`, so through the build `valid` is redundant. A direct caller of `price_chain` keeps `smile_ok` at its default, so `tests/test_chain.py::test_an_invalid_quote_and_a_quote_not_smile_ok_are_each_left_out_of_the_smile_on_their_own` was added; both are killed by it.
- **C-M22 and E1c** were "killed" in the first run only by `tests/test_notebooks.py::test_committed_pricing_core_notebook_equals_a_fresh_build`, which compares the notebook with the source text it copies: it pins text, not behaviour. Re-run without the notebook-sync tests, both survive, and are counted as survivors above.
- **F1b** as first written disabled the input check outright (a duplicate of F1a); it was replaced by "the old summary removed only by an unfiltered build", killed by `test_a_filtered_build_deletes_nothing_and_its_summary_refuses_until_a_full_build`.

**App (F9).** Run by the F9 agent against the FULL vitest suite (baseline `Tests 935 passed (935)`; `scratchpad/fix4/f9/mut/app_mutants_final.out`), 19 mutants re-targeted where the code was rewritten, each file restored by SHA-256: round 1's 60, **59** killed (k5, total variance in another float order, equivalent within the 1e-12 calendar slack); round 2's 41, **41**; the round-3 reviewer's 17, **17** (`quoted_cap_strike_only`, which survived the full suite before, is killed); the agent's own 30, **30**. The exporter's Python mutants: **20 of 20** (`py_mutants_final.out`).

### Round 3, gates after the fixes (2026-10-29)

| Gate | Command | Output |
|---|---|---|
| Forced build 1 | `/usr/bin/time -f "WALL %e s, USER %U s, SYS %S s, MAXRSS %M KB" uv run python tools/build_pricing.py --workers 10 --force` (`scratchpad/fix4/run_build.sh`) | `WALL 594.35 s, USER 4905.03 s, SYS 20.10 s, MAXRSS 5252364 KB`, `exit 0`, load average 14.94 at the start, median 18.97 while running (`data/logs/pricing_build_r3_1.{log,load,loadtrace}`) |
| Forced build 2 | the same | `WALL 653.79 s, USER 5134.42 s, SYS 22.75 s, MAXRSS 5274892 KB`, `exit 0`, load 8.27 at the start, median 21.72; SHA-256 of all 68 pricing parquet and JSON files identical to build 1 (`pricing_build_r3_{1,2}.sha256`) |
| Incremental run | `uv run python tools/build_pricing.py --workers 10` | `WALL 7.05 s, USER 23.58 s, SYS 3.40 s`, 0 partitions priced, all 68 files unchanged (`pricing_build_r3_3_incremental.sha256`) |
| Export | `uv run python tools/export_app_data.py --store data/store` | wrote the four files of `app/public/data/`; `surface_frames.json` 42,700 bytes, `config_hash` f9142dd407d6…; wall 2.58-3.76 s (0.85-0.93 s before F1) |
| Report | `uv run python tools/report_m2.py > data/logs/report_m2.txt` | `exit 0`, `WALL 166.81 s` |
| Tests | `uv run pytest -q` | `964 passed, 37 deselected` |
| Real data | `uv run pytest -q -m real_data` | `35 passed, 966 deselected` |
| Notebooks | `uv run python tools/build_notebooks.py --check` | `notebooks are up to date` |
| App | `cd app && npm run verify && npm audit` | lint clean; `Test Files 28 passed (28)`, `Tests 935 passed (935)`; All files 99.15 / 97.66 / 99.12 / 99.66 (statements, branches, functions, lines); `✓ built in 2.80s`; `found 0 vulnerabilities` |
| Tracked data | `uv run python tools/licensing/check_tracked_data.py` | `clean: 0 raw vendor files in 306 files git would commit (0 size warning(s))` |
| Diagrams | `tools/diagrams/build.py docs/architecture/specs --out docs/architecture/out --check`, then with `--verify-mermaid` (`uv run --offline --with playwright==1.64.1`, `DIAGRAM_KIT_CHROMIUM` and `DIAGRAM_KIT_MERMAID_JS` set) | `ok: 7 spec(s) up to date in docs/architecture/out`; `mermaid 12.2.0: 7 spec(s) checked` |

**Not reviewed.** Round 3's fixes F1-F14 have not been attacked by an independent reviewer. F9 and F10-F12 were delegated (an Opus agent and a Sonnet agent) and checked by the fixer against their evidence, which is not a review.

## Round 4 (2026-10-30)

**Reviewer:** `adversarial-reviewer` (Opus): probes on a read-only copy of the store, the gates and its own 10 mutants in a scratch copy with `.git`. **Scope:** the uncommitted tree on top of 35cb682 after the round-3 fixes. It attacked F1-F14 (claims 1-8 of its brief: F1, F2, F3, F5 and F7, F9, the gates, the mutants, the documents). Probes in the session scratchpad (`egv/m2/r4/work/probes/`); the fixes' own probes and runs in `fix5/`.

### The orchestrator's own verification, before acting

- **Claim 1, 1a (a second file in a reference table).** Read `build.py:298-303`: `partition_fingerprint` hashed `table_dir(t)/"part-0.parquet"` only; `store.py:269-271`: the views read `table_dir/**/*.parquet`. Read `f1_extra_reference_file.out`: as stated. **Confirmed.**

### Reviewer, per claim

| # | Claim attacked | Verdict | Evidence |
|---|---|---|---|
| 1 | F1: provenance | **REFUTED** (narrowly) | 1a (Medium): a second parquet in a reference table (`rates/part-1.parquet`) is read by `Store.connect` (`**/*.parquet`), but `partition_fingerprint` and `frame_input_files` hash only `part-0.parquet`: rate 0.0522 → 0.0722, problems [], the summary and the export accepted, an incremental build re-priced nothing, the frame shipped IV 0.180069 (0.179531 after `--force`). 1b (Low): the export checks, then reads (a race), and ships old IVs under the new `data_fingerprint`. An added partition, an interrupted build and a mid-rewrite: refused |
| 2 | F2: WIDE quotes out of the smile | SURVIVES | `expiry_forwards` 22 of 22 identical; `quote_iv` differs only in `in_smile` (137,824 true → false); 571,130 / 7,278 / 4 / +7.51 reproduced |
| 3 | F3: the partner solved on demand | SURVIVES | 1 of 160 chains above half a cent; one level only; 0 on-demand solves on 40 real dates |
| 4 | F5, F7 | SURVIVES | docstring nit: at τ ≤ 0 equal taus return NaN |
| 5 | F9: the IV ceiling, `quoted_share` | code SURVIVES; the fixer's `quoted_share` premise **REFUTED** | `quoted_share` already counts 4\|8 cells as extrapolated (`EXTRAPOLATED_BITS` = 1\|4); the walkthrough's clause that it counts them as quoted is false |
| 6 | The gates | SURVIVES | 964 / 37; 35; npm 935 in 28; tracked clean in 306; its own forced build equals r3_2 on 68 files |
| 7 | The mutants | SURVIVES (187 of 194) | its own 10: 7 killed; R4-F1b, R4-F2a and R4-F3a survive the default suite (`-m real_data` kills them only through the fingerprint guards) |
| 8 | Documents | **REFUTED** (narrowly) | D1 walkthrough "Not done" (`quoted_share` clause); D2 ADR-0004 amendment 2's 3,270 (1.87%) stale, the rebuilt store gives 3,184 of 174,816 (1.82%); D3 README:79, DATA.md:8 and ADR-0010:45 disagree on the out-of-sample span |
| N-A | (new, Medium, owner decision) | — | stub quotes that are not WIDE still drive the calendar constraint at 0-60 days, \|k\| ≤ 0.15: 3,184 moved, 130 by more than 1 vol point, 7 by more than 2, 1 by more than 5 (+5.09, 2020-03-20, a put with a 17.6% spread 6.16 points above its neighbours); drivers LOCKED, one tick wide, bid ≤ 0.05; in the committed frames the worst moved quoted cell 0.97 points |
| N-B | (new, Low) | — | R4-F1b, R4-F2a and R4-F3a survive the default suite |

### Fixes (decisions G1-G5, defaults taken 2026-10-30)

Each fix names the test that fails without it: the mutant that kills it, from the run below. The decisions are recorded in the walkthrough's decision 18, `LEARNING_LOG.md` defaults 35-37 and the ADR each amends. The reviewer's two F1 probes, re-run on the fixed code (`fix5/probes_after/`): `f1_extra_reference_file.py` reproduces the rate move (0.0722) and then stops at `pricing_problems` with `InconsistentStore: …/rates: an unpartitioned table's folder must hold exactly the file part-0.parquet, it holds ['part-0.parquet', 'part-1.parquet']`; `f1_export_toctou.py` stops at the export with `PricingNotCurrent: partitions whose quotes or reference tables changed since they were priced …['source=optionsdx/year=2023']`.

| Finding | Fix | Fails without it |
|---|---|---|
| 1a | **G1.** `Store.checked_table_file(name)` (`store.py`) returns `<name>/part-0.parquet` and raises `InconsistentStore`, reading only, when the folder holds another parquet, any other file, a folder, a symlink (the folder or anything in it) or no `part-0.parquet`. `build.partition_fingerprint` and `export_app_data.frame_input_files` use it (rates, dividends, spy_bars; vix for the export); `build_pricing` checks the three pricing inputs after the empty-store check and before it removes the summary or deletes anything. Refused, not hashed (the E2 stray-file rule). M1's writer leaves exactly that file: `Store.write_table` without partition columns removes the folder and writes `part-0.parquet` through a `.tmp` and a rename (`pipeline.py:182`); no other writer touches these tables. No other `part-0.parquet` assumption outside the tests (grep). ADR-0001 amendment 6 | `tests/test_pricing_build.py::test_a_reference_table_that_is_not_its_one_file_is_refused_by_the_build_the_summary_and_the_export` (a second parquet, a symlinked part-0, a stray file: summary, export and build, forced or not, refuse; the pricing files, the summary, `pricing_inputs.json`, the dolthub orphans and the stray file all survive), `::test_a_second_vix_file_is_refused_by_the_export`, `::test_checked_table_file_accepts_exactly_the_one_file_write_table_leaves` (9 cases) (mutants G1a-G1h) |
| 1b | **G2.** The export takes the frames' `data_fingerprint` before it reads them; after reading (and the `data_last_date` query) it calls `require_current` again and takes the fingerprint again, and raises `PricingNotCurrent` if either changed. ADR-0001 amendment 4 says the export is a reader that checks before and after | `::test_an_input_rewritten_while_the_export_reads_the_frames_is_refused`: the reviewer's interleaving (`build.surface_frames_body` monkeypatched to rewrite after reading) with the frame's quotes ×1.30, another year's quotes (only the second `require_current` sees them) and vix (only the fingerprint does) (mutants G2a-G2c) |
| D1-D3, nit | **G3.** The walkthrough's "Not done" clause deleted (and "and `quoted_share`" in its next sentence, false for the same reason; the committed frames have 0 cells with bits 4 and 8 but not 1, `fix5/g4/frames_quoted_moves.out`); ADR-0004 amendment 2 gives the rebuilt store's 3,184 of 174,816 (1.82%) beside the round-2 figure, from `data/logs/report_m2.txt` (block "the calendar constraint at the smiles' own nodes", which prints it); README:79 and DATA.md:8 now say DoltHub covers 2019-2026 (2019-05-10 to 2026-10-26 in the store) and that the out-of-sample holdout is 2024-01-02 to 2026-10-26, as ADR-0010:45 gives; `smile.surface_iv`'s docstring says the NaN at τ ≤ 0 comes before the equal-tau check; the walkthrough's "What was reviewed" and this ledger | docs |
| N-A | **G4** (owner decision, default: no further node rule in M2). The measurement in ADR-0004 amendment 5 (an open question, for owner review) and the walkthrough's "Not done". The reviewer's `f2_stub_drivers.py` re-run on the real store (read-only): output identical to the reviewer's (`fix5/g4/f2_stub_drivers.out`: 174,816 nodes, 3,184 moved, 0 down, 130 / 7 / 1 above 1, 2 and 5 vol points, +5.09 at 2020-03-20; 260 driver nodes, 20 LOCKED, 58 one tick wide, 108 with a bid ≤ 0.05); the committed frames' worst moved quoted cell (bit 8, neither 1 nor 4) 0.97 vol points, 2020-03-16, 270 days, k = −0.26 (`fix5/g4/frames_quoted_moves.out`) | docs |
| N-B | **G5.** (a) `::test_with_no_option_quotes_the_build_raises_and_deletes_nothing` also requires `pricing_summary.json` byte-identical; (b) `::test_the_summary_counts_a_wide_quote_as_valid_but_not_smile_ok` (one OTM put of optionsdx 2023-06-15 made WIDE: `otm_valid` 116, `otm_valid_wide` 1, `otm_smile_ok` = `in_smile` = 115); (c) **not written: R4-F3a is equivalent.** A quote that step 5 solves first is OTM on the final F and not on the step-3 forward, so its partner (the other type, same strike and expiry) is OTM on the step-3 forward and was attempted in step 3 whenever it has a mid; a partner with no mid has no American IV (`american_no_mid`), so solving it changes nothing. Measured (`fix5/g5/r4_f3a_equivalence.out`, both copies exec'd from `chain.py`'s text): on 3,000 random American chains (r 0-10%, 30-1,000 days, up to 3 dividends, up to 15% of mids missing) step 5 first solved 7,541 quotes, 5,056 of them flat, and had to solve 570 partners on demand, 0 of them with a finite mid; the outputs of R4-F3a equal the code's on all 3,000. The comparison's own check: with no on-demand solve at all, 8 of 200 chains differ (`r4_f3a_control.out`) | (a) R4-F1b; (b) R4-F2a; (c) — |

### Round 4, mutants after the fixes

Run by `scratchpad/fix5/mut/run_r4_fix_mutants.py` in three scratch copies WITH `.git` (`rsync -a --exclude /data --exclude node_modules --exclude .venv`, each with its own `uv sync --offline --frozen`), each mutant against the WHOLE default suite (no `-x`), each file restored and checked by SHA-256. The unmutated suite in the copy first: `981 passed, 37 deselected` (`fix5/mut/baseline_default.out`). Every verdict and every failed test is in `fix5/mut/mutants_{a,b,c}.out`.

| Mutant | What | Verdict | Fails without it |
|---|---|---|---|
| R4-F1b | the summary removed before the empty-store check (the reviewer's) | killed: 4 failed, 977 passed | the empty-store test; the three G1 build cases |
| R4-F2a | the summary's `smile_ok` on NOT_VALID (the reviewer's) | killed: 1 failed, 980 passed | the WIDE summary test |
| R4-F3a | the partner solved on demand only in step 3 (the reviewer's) | **survived**: 981 passed | equivalent (G5 c) |
| G1a | `partition_fingerprint` takes `part-0.parquet` unchecked | killed: 3 failed | the three G1 cases (the summary) |
| G1b | no check before the summary and orphan deletions | killed: 3 failed | the three G1 cases (nothing deleted) |
| G1c | `frame_input_files` takes `part-0.parquet` unchecked | killed: 1 failed | the vix test |
| G1d | no symlink check inside the folder | killed: 2 failed | symlinked part-0 (both tests) |
| G1e | only parquet names counted | killed: 3 failed | stray file; the `.tmp`; a folder |
| G1f | a folder named `part-0.parquet` accepted | killed: 1 failed | `[part-0 a folder]` |
| G1g | a symlinked table folder followed | killed: 1 failed | `[symlinked folder]` |
| G1h | no missing-folder check | killed: 1 failed | `[no table]` |
| G2a | no `require_current` after reading | killed: 2 failed | another year's quotes; the frame's quotes |
| G2b | no fingerprint comparison | killed: 1 failed | vix |
| G2c | the first fingerprint taken after reading | killed: 1 failed | vix |
| **All** | **14** | **13 killed** | R4-F3a equivalent |

Not re-run in round 4: round 3's 194 (187 killed) and the reviewer's seven other mutants (killed in its own run, `egv/m2/r4/work/probes/r4_mutants.out`).

### Round 4, gates after the fixes (2026-10-30)

| Gate | Command | Output |
|---|---|---|
| Forced build | `/usr/bin/time -f "WALL %e s, USER %U s, SYS %S s, MAXRSS %M KB" uv run python tools/build_pricing.py --workers 10 --force` (`scratchpad/fix5/run_build.sh r4_1 --force`) | `WALL 679.55 s, USER 5718.61 s, SYS 27.77 s, MAXRSS 5279084 KB`, `exit 0`; load average 13.30 at the start, 11.32 at the end, median 19.55 (range 12.14-27.05) over 22 samples while it ran, with the fixer's test suite and fuzz running beside it (`data/logs/pricing_build_r4_1.{log,load,loadtrace,sha256}`) |
| Against round 3 | `diff data/logs/pricing_build_r3_2.sha256 data/logs/pricing_build_r4_1.sha256`; `scratchpad/fix5/compare_r3_2.py` | **66 of 66 parquet files identical.** `pricing_summary.json` and `pricing_inputs.json` differ, as they must: they name the code fingerprint (f9142dd407d6… → a4b22664c957…), which G1 and G3 changed. With the old code put back (the summary's `code_fingerprint`; each partition's `code`, and its `inputs` recomputed with the old code over today's files) both equal r3_2's bytes; all 22 recorded `inputs` fingerprints recompute (`fix5/compare_r4_1.out`) |
| Incremental run | `uv run python tools/build_pricing.py --workers 10` (`run_build.sh r4_2_incremental`) | `WALL 4.62 s, USER 29.75 s, SYS 6.41 s`, `exit 0`, 0 partitions priced, all 68 files unchanged (`pricing_build_r4_2_incremental.sha256`) |
| Export | `uv run python tools/export_app_data.py --store data/store` | wrote the four files of `app/public/data/`, wall 1.63 s; `surface_frames.json` 42,700 bytes, `config_hash` a4b22664c957…, `data_fingerprint` 7bf384806719… (unchanged); against round 3's files only `generated_at`, and in `surface_frames.json` `run.config_hash` and `run.run_id`, differ |
| Report | `uv run python tools/report_m2.py > data/logs/report_m2.txt` | `exit 0`, `WALL 64.37 s`, nothing on stderr; against round 3's report only the code fingerprint and the timing lines differ |
| Tests | `uv run pytest -q` | `981 passed, 37 deselected` (964 + 17 new) |
| Real data | `uv run pytest -q -m real_data` | `35 passed, 983 deselected` |
| Notebooks | `uv run python tools/build_notebooks.py --check` | `notebooks are up to date` (rebuilt once: `02_pricing_core.ipynb` copies `smile.py`, whose docstring G3 changed) |
| App | `cd app && npm run verify && npm audit` | lint clean; `Test Files 28 passed (28)`, `Tests 935 passed (935)`; All files 99.15 / 97.66 / 99.12 / 99.66; `✓ built in 2.54s`; `found 0 vulnerabilities` |
| Tracked data | `uv run python tools/licensing/check_tracked_data.py` | `clean: 0 raw vendor files in 306 files git would commit (0 size warning(s))` |
| Diagrams | `uv run --group diagrams python tools/diagrams/build.py docs/architecture/specs --out docs/architecture/out --check`, then `--verify-mermaid` (`--with playwright==1.64.1`, `DIAGRAM_KIT_CHROMIUM` and `DIAGRAM_KIT_MERMAID_JS` set) | `ok: 7 spec(s) up to date in docs/architecture/out`; `mermaid 12.2.0: 7 spec(s) checked` |

**Not reviewed.** G1-G5 were checked by the orchestrator's mutants (the 14 above, run by the fixer as the orchestrator's brief set them); no independent reviewer has attacked them.

## Resolution

See the milestone-2 commit message, which lists each refuted claim and its fix. **What was reviewed.** Round 1 reviewed M2 (code, design, verifier). Round 2 reviewed the D-fixes made after round 1 (D1-D13). Round 3 reviewed the E-fixes made after round 2: the code reviewer E1-E3, E5 and E13; the docs, licence and app-validator reviewer E4, E6-E12 and E14. Round 4 reviewed F1-F14. G1-G5 were checked by the orchestrator's mutants.
