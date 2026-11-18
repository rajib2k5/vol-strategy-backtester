# ADR-0010: Evaluation protocol: sample splits, trial counting, regimes, stress windows and the stress grid

> **Data notice.** The DoltHub figures in this document (counts, dates, quantiles and summaries, in its text and in its tables) are derived from the DoltHub database `post-no-preference/options` (<https://www.dolthub.com/repositories/post-no-preference/options>), licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), and are shared under the same licence. Changes: we aggregated it into counts, shares and quantiles, compared it with OptionsDX and ran our pricing build on it; no quote row is reproduced. The rest of this repository is MIT. See [DATA.md](../../DATA.md).

**Status:** Accepted at milestone 0. Implemented in M6; the M4 signal work must respect the splits from its first run.

## Revised after M0 review (2026-10-28)

The adversarial review (`docs/validation/00-design-research-ledger.md`, claim 12) found five leaks. The PSR/DSR arithmetic and the vol-shock definition survived.

1. **The volume-cap regime changed inside validation.** The volume cap switched on at 2021-01-04: never in development, only part-way through validation, and never in the holdout. A 10-lot on weekly near-ATM 20–40 DTE lines is clipped on 57.2% of 2021–23 contract-days by the fill-day rule, and 58.4% by the order-day rule (re-measured in round 2 with contracts selected on the order date; round 1 said 56% and 65%, a fill-day selection artefact, ADR-0002). **Changed:** the hard cap is the rule of record in every split, and the volume cap is a reported validation diagnostic (§1).
2. **N was a raw count of `config_hash` values.** The DSR needs the number of *independent* trials. Correlated variants of one idea are not independent, and choices made outside `runs` were not counted at all. **Changed:** N_eff by clustering trial returns, a conservative N_raw that includes logged design choices, and a headline DSR that takes the worse of the two (§2, and the appendix).
3. **The holdout is not blind.** The background doc §6, written before any strategy run, already discusses Aug-2024 and Apr-2025 outcomes, for example "A book stopped out on 4–8 Apr missed the reversal". **Changed:** this is now stated as a consequence, with rules that limit the damage (§1, Consequences).
4. **Validation re-runs were unlimited.** "A re-run after a change … counts as a new trial" let validation be used for tuning. **Changed:** at most two re-runs per frozen configuration, for logged defects only, each charged as a trial (§1).
5. **Signals could leak through full-sample fits.** The split guard checked only the dates a run requested. **Changed** in ADR-0001: signals are causal, and the split guard sits inside the `MarketView` (test 4).

Also corrected: the Aug-2024 hole is 2024-07-30 → 2024-08-09, and 07-29 and 08-12 both have data.

Round 2 (`docs/validation/00-round2-ledger.md`, claims 7 and 12): PSR 0.9433 and DSR 0.6319 reproduce. The weekly clip shares above are corrected. `n_trials` is now N_raw, with N_eff reported as `n_trials_eff`, because in a null simulation with correlated variants `dsr_eff` alone had a false-positive rate of up to 35.7% (§2). PSR is stated on the per-period Sharpe ratio (§2).

## M3 amendments (default taken 2026-10-30, owner can override)

The M3 build (`docs/milestones/03-daily-engine.md`; `LEARNING_LOG.md`, default 56) applied this ADR's splits to its own runs. The original text stays in place.

1. **§1, what a run after 2019 may report** (decision D19). The reference strategy of M3 is a diagnostic that exercises the engine; it is not a strategy under test. To keep the validation and holdout data from steering M4, M3 follows these rules:
   - **Health metrics only after 2019.** A run whose sample ends after 2019-12-31 reports mechanics: cash reconciliation, one mark per lot per session, the hedge residual, fills against quotes, mark-source shares, `DEGRADED` counts and timings. No P&L, NAV level, return or Sharpe ratio appears anywhere for it: not in the docs, the notebook, the committed logs or the app. `tools/run_backtest.py` prints timings only, and `tools/report_m3.py` prints no P&L for a run that ends after 2019.
   - **No holdout run in M3.** A 2020-26 short-straddle result would steer the design of M4's short-vol strategies.
   - **The 60-second run spans 2010-2023** (development and validation, split `validation`), `run_purpose = diagnostic`, `trial_group = m3_engine_reference`, with its P&L redacted. It measures ADR-0001's 60 s trigger and the engine's health, not a strategy.
   - **The committed engine datasets** (`blotter.json`, `positions_timeline.json`) come from the development run (2010-2019) only, are labelled as a diagnostic run that "is not a strategy result", and hold no P&L, NAV, return or Sharpe. The development run's P&L is not headlined either (risk 11 of the M3 plan). `tools/export_app_data.py` refuses a run whose split is not `development` unless `--allow-split` is given, which is meant only for runs on made-up stores.

## M4 amendments (default taken 2026-11-17, owner can override)

The M4 build (`docs/milestones/04-strategies-and-signal.md`; [ADR-0011](0011-vrp-signal-and-strategy-rules.md); `docs/validation/04-ledger.md`; `docs/validation/trials/README.md`; `LEARNING_LOG.md`, defaults 103, 104, 109-112, 121-125 and 171-177) used this ADR's splits for its first signal, strategies and trials. The original text and the M3 amendments stay in place.

1. **§1, who freezes and who scores** (plan section 6, default taken 2026-11-09).
   - **M4** reports development diagnostics only, labelled "in-sample, 36 trials of N_raw 46, selection-biased, no claim". It builds the pre-registration machinery (item 2) and uses it once, on the forecast test (item 6).
   - **The strategy pre-registration freezes at the end of M5.** M5's risk rules change the configurations, so a freeze at M4 would test configurations that never trade. **M6** commits a dated amendment with its PSR/DSR code hash, then scores validation once and the holdout once. Rejected: freezing inside M6, because attribution work would then sit between selection and freeze.
   - **After 2019-12-31, M4 runs only P&L-independent health runs:** `tools/smoke_m4.py` runs each structure with the DTE exit only, so the path does not depend on P&L, on validation (OptionsDX in quote mode and DoltHub in surface mode) as `diagnostic_kind` `smoke`, plus the 60-second `budget` run. They print M3's health whitelist and delete their ledgers. **No holdout run is made.**
   - For M6 (planned, not built): "X earns a premium" tests d = r − r_f, and "the VRP signal beats always-short" tests d = r_gated − r_always. The decision metric is the daily excess return on NAV_mid, with Sharpe, PSR and DSR beside it. The block comes from the development series, between 21 sessions and T/8 (88 for the holdout). The holdout is labelled `semi-blind` and `proxy: surface mode`.
2. **§1, the pre-registration machinery** (built in M4, `tools/prereg.py`, `tools/score_prereg.py`, `tools/forecast_test.py`).
   - **Files** in `docs/validation/prereg/`: `<id>.json` (the claim, candidates, benchmark, k, metric and its proxy flag, windows with the SHA-256 of their date lists, the block rule, draws and seed, α, the correction, the scoring command and the scorer's SHA-256), `<id>.md` (the rationale, written from the .json), and `<id>.sha256` (the `sha256sum` of both). An amendment is a new dated file that names the old hash.
   - **Freezing.** All three files are committed before any scoring. `score_prereg.py` refuses on a hash mismatch, an uncommitted or modified file, a changed scorer closure (14 files) or a spent window.
   - **One shot.** `spent.jsonl` (append-only, committed) holds one line per scoring: the window, the pre-registration's id and hash, the candidates, the result hash and the date. The scorer writes it, and a side ledger, before it computes anything. Any line spends that window for every candidate. `runs_of_record.jsonl` logs every run past 2019.
   - **The run gate.** `make_run_gate` is passed to `run_backtest` by the tools. It refuses an unlisted configuration, a holdout run with no validation record, a run past the limits below, and a spent window. `RunConfig.prereg_id` is required of a trial past 2019, and a diagnostic past 2019 names its `diagnostic_kind`.
   - **Trust boundary.** These checks catch mistakes and the routes `tools/prereg.py`'s docstring names. They are not a barrier against a person who edits the repository, runs the code elsewhere, or deliberately changes a field to get a new trial hash.
3. **§1, defect re-runs only before scoring.** A re-run of a frozen configuration on validation is allowed to fix a logged defect only while its pre-registration has not scored that window. After the scoring, a failing result is final: the window is spent for every candidate, and a fix is a new configuration that goes back to development.
4. **§1 and "How we will test it", tests 4 and 8: the names and the implementation.** Test 4's second bullet (a holdout run whose configuration has no frozen-validation record raises) is called **test 4b** from M4 on. The run gate enforces 4b and test 8 (a third validation re-run raises: the run of record and two re-runs, a fourth refused, started or completed), both by `trial_hash`, the configuration without where it ran, so a holdout run finds its validation record. `tests/test_prereg.py:560` (4b) and `:579` (8) run them on real `RunConfig`s.
5. **§2 and Consequences, the window-matched horizon replaces the note "annualised with 252 sessions".** The note in the Consequences section said realised vol is close-to-close and annualised with 252 sessions. With 252, a 30-day window of 17 sessions biases the log ratio of implied to realised variance by ln(21/17) = 0.2113, about half the 0.4 entry band. The signal compares the implied total variance IV30² × 30/365 with the forecast n × ŷ, where n is the number of sessions in (t, t + 30 days] from the session calendar. HAR's horizon needing its own out-of-sample test stands, and was run once (item 6). See [ADR-0011](0011-vrp-signal-and-strategy-rules.md) §4.
6. **The forecast test, the first use.** Claim: the 21-session HAR beats the naive RV22 on QLIKE, a proxy loss (k = 1). Scored once on 2026-11-17 on the development window 2010-01-04 to 2019-11-29: EWC bootstrap-t (q 4, block 21, 9,999 draws), one-sided p = 0.0139 against the registered 0.025, so HAR (concept note 24; `docs/validation/04-ledger.md`). It is roughly 5%-level evidence, QLIKE is a proxy, and the window is development data, fresh for this loss but not unseen. No stake rides on it: it only sets the signal's RV model.
7. **Appendix, design choices 7 to 10.** The design-choice log grows from 6 to 10 entries, each added to N_raw (the table is in [ADR-0011](0011-vrp-signal-and-strategy-rules.md), appendix): 7, `exit_dte = 14`; 8, the entry windows; 9, the RV model; 10, θ in {0, 0.4} and the 0.4 band.
8. **§2, the counting rule for M4's trials.** `docs/validation/trials/m4.jsonl` is the trial log of M4's development grid, one line per run of a grid configuration on real data, written by `tools/run_m4_grid.py` after the run's ledger is in place. A line holds the date, purpose, label, trial group, split, sample dates, `config_hash`, `trial_hash`, `code_fingerprint`, `data_fingerprint`, `source_commit`, `run_id` and the parameters. It holds no metric and no run status.
   - **What a trial is.** For trial group `m4_vol`, a trial is a distinct (`config_hash`, `code_fingerprint`, `data_fingerprint`) triple among the log's development lines. This replaces §2's "distinct `config_hash` values with `run_purpose = trial`" for this group, in two ways. `config_hash` and `trial_hash` leave the code out (`run_config.py`), so a re-run after a code change would count as no new trial: the run's `code_fingerprint` (every `.py` file under `src/volbt`, the libraries and Python) puts the code back, and the `data_fingerprint` puts the data back. A re-run on the same code and data is the same trial: it gives the same ledger byte for byte (ADR-0001 test 3).
   - **The first key was refuted by review.** B2a first counted the distinct (`trial_hash`, `code_fingerprint`) pair. The B2a review showed that this undercounts: `trial_hash` drops the split, the sample dates, `execution_mode` and `data_source`, so two runs of one configuration on different data would count as one trial. A fix pass changed the key to the triple above. On the log written on 2026-11-17 (local time; its lines carry the UTC date 2026-11-18) both keys give 36 trials and N_raw 46.
   - **N_raw** = the trials + the design-choice log (10 after M4). After the grid of record (`tools/run_m4_grid.py --workers 4`, 2026-11-17 local): 37 lines (the 36 grid runs and one measurement run of the same configuration, code and data), 36 trials, **N_raw 46**.
   - **The log is complete.** Every line names a run folder whose `runs` row it copies, and every development run of `m4_vol` under the work folder has a line (`tests/test_real_m4.py`, marked `real_data`).
9. **§1, decision D19 extended to every date before M6.** D19 held back P&L, NAV, return and Sharpe for runs after 2019. Before M6, no P&L, NAV, return or Sharpe of any M4 run, for any date, is in a committed file or printed by the grid and report tools (`tools/run_m4_grid.py`, `tools/report_m4.py`). The M4 app files and documents show signals, contract picks, exit reasons and dates, and the forecast test, and no result. An exit reason of `profit_target` or `stop` says that the position's hedged P&L crossed its threshold on that date. (Default taken 2026-11-17, owner can override.)

## Context

- **Many trials.** We will try many strikes, tenors, thresholds and vol models. The best Sharpe among N trials is biased upwards (Bailey & López de Prado 2014; `docs/concepts/00-background.md` §7).
- **A drawdown is not a vol shock.** In 2022 the S&P fell 19.4%, yet the realised variance premium stayed positive and short vol did comparatively well (background §6). Regimes must therefore be split by **vol shock**, not by drawdown.
- **Coverage by episode.**

  | Episode | Data source |
  |---|---|
  | Feb-2018 | OptionsDX |
  | Mar-2020 | OptionsDX |
  | 2022 | OptionsDX |
  | Apr-2025 | DoltHub |
  | Aug-2024 | none for the shock: DoltHub has no SPY dates from 2024-07-30 to 2024-08-09. 07-29 and 08-12 exist (ADR-0009) |

## Decision

### 1. Sample splits

These are fixed now, before any strategy has been run.

| Split | Dates | Source / mode | Rule |
|---|---|---|---|
| Development | 2010-01-04 → 2019-12-31 | OptionsDX, `quote` | Tuning allowed. Every distinct `config_hash` counts as a trial. |
| Validation | 2020-01-02 → 2023-12-29 | OptionsDX, `quote` (of record), plus the diagnostics below | Frozen configurations only. One run of record per configuration, plus at most two re-runs for logged defects. |
| Holdout (out-of-sample) | 2024-01-02 → 2026-10-26 | DoltHub, `surface` | Run once per frozen configuration. Never used for tuning. |

**One rule of record in every split.** A frozen configuration is judged by the rules it will face out of sample. So every run of record, in every split, uses:
- `cap_mode = hard_only`, the only cap the holdout can apply, because DoltHub has no volume;
- `fill_timing = next_close`;
- the same `exit_dte`;
- the same expiry universe (ADR-0002 §5).

**Validation diagnostics.** These select nothing and are not trials: `run_purpose = diagnostic`.
- `cap_mode = volume`, run from 2021-01-04 to 2023-12-29. The difference from the run of record is reported as the **capacity haircut**, next to the validation Sharpe.
- The surface-mode runs S, M and M′ of ADR-0009 §4, which estimate the holdout's surface-mode distortion.
- **Added in M4 fix pass 3 (2026-11-10):** a diagnostic run past 2019 names which one it is in `RunConfig.diagnostic_kind`: `volume_cap`, `surface_s`, `masked_m` or `masked_m_prime` (the two above), or `smoke` or `budget` (the M4 plan section 6 smoke and 60-second budget runs). The run gate (`tools/prereg.py make_run_gate`) refuses a diagnostic past 2019 without one, records it, and limits its re-runs as for a validation trial: a run with the same trial_hash, kind, data source and execution mode as an earlier one needs a reason, and the third re-run is refused. The nine records written before this rule read as eight `smoke` runs and one `budget` run (`prereg.LEGACY_KIND_RULE`). Fix pass 4 changed the count (next bullet).
- **Revised in M4 fix pass 4 (2026-11-10):**
  - The gate counted the diagnostics of one trial_hash together, whatever their kind, data source and execution mode: the run and two re-runs in total, started or completed. A fourth was refused. *Revised after the fifth review (fix pass 5): the two classes are counted apart (next bullet).*
  - A `smoke` or `budget` diagnostic of a trial_hash that a pre-registration in `docs/validation/prereg/` lists as a candidate or benchmark is refused. It would run a listed configuration on validation data outside its run of record.
  - `trial_group` is a label: it is left out of the trial_hash, so a new label does not reset the count. A trial or a named diagnostic past 2019 must have `seed` 0: no code draws from the seed.
  - The nine records written before fix pass 2 count toward no current limit. Their trial_hash has the old formula, which no current configuration gives, and they have no data source or execution mode. They were the M4 smoke and budget runs: their output was engine health only, and the smoke tool deleted their ledgers. They stay on the record as they are.
  - Trust boundary: the limits count per trial_hash. A change to any field that defines a configuration gives a new trial_hash. So the limits bind an honest workflow, and every run past 2019 stays on the record. They are not a barrier against a deliberate change made to get a new trial_hash: such a run is recorded as the new configuration it is.
- **Revised in M4 fix pass 5 (2026-11-10):** the gate counts the two classes of diagnostic apart. With one count, a structure's full smoke (both data sources) and its budget run used its three diagnostics, so its ADR-0009 §4 run S was refused.
  - ADR diagnostics (`volume_cap`, `surface_s`, `masked_m`, `masked_m_prime`): per trial_hash and kind, the run and two re-runs, started or completed. A fourth is refused. A re-run needs a reason.
  - Health runs (`smoke`, `budget`): per trial_hash, kind, data source and execution mode, the run and two re-runs. A fourth is refused. A re-run needs a reason. A health run of a trial_hash that a pre-registration lists is refused, as before. *Revised after the sixth review (fix pass 6): only on the pairs the tools run (next bullet).*
  - Neither class counts toward the other. A smoke run that crashes part way is run again whole with `--rerun-reason`.
  - Trust boundary, added: a field can enter the trial_hash without acting on the run, for example `hedge_band_pct_nav` under time hedging or `participation_rate` under `cap_mode = hard_only`. A change to such a field gives a new trial_hash and the same run.
- **Added in M4 fix pass 6 (2026-11-10):**
  - A health run is accepted only on a (data source, execution mode) pair that `tools/smoke_m4.py` runs (`prereg.HEALTH_PAIRS`): `smoke` on (OptionsDX, `quote`) and (DoltHub, `surface`), `budget` on (OptionsDX, `quote`). Any other pair is refused. Before, the gate accepted all four pairs.
  - The most runs of one trial_hash on validation dates are **15**: 3 validation trials, 3 runs S, 6 smoke runs and 3 budget runs. This was measured on a made-up repository (`tests/test_prereg.py::test_one_configuration_runs_at_most_15_times_on_validation_dates`). The health runs pass only before a pre-registration lists the configuration. The volume cap adds 3 under its own trial_hash (`cap_mode` enters it). Runs M and M′ add 3 each once built: `RunConfig` refuses them today, and `chain_mask` enters the trial_hash, so each counts under its own. *Revised after the seventh review (fix pass 7): a holdout trial on validation dates made 16; it is now refused, and the maximum is 15 again (next bullet).*
  - The gate compares only a run's dates after 2019-12-31 with the spent windows. Development dates are free, so the scored forecast window (2010-01-04 to 2019-11-29) does not refuse the budget run (2010-01-04 to 2023-12-29) or its two re-runs. A run that shares a date after 2019-12-31 with a spent window is still refused. The scorer's own spent check still compares whole windows.
- **Added in M4 fix pass 7 (2026-11-10):** the gate refuses a trial past 2019 whose dates lie outside its split (`volbt.view.SPLITS`). A validation trial runs on validation dates and a holdout trial on holdout dates. Before, a pre-registration could name a "holdout" window of validation dates, and a holdout trial on it was accepted: a 16th run of one trial_hash on validation dates (review H). With that attack added to `tests/test_prereg.py::test_one_configuration_runs_at_most_15_times_on_validation_dates`, the most runs of one trial_hash on validation dates are **15**.
- **Added in M4 fix pass 8 (2026-11-10):** the forecast scorer's checks of `tools/` (`tools/score_prereg.py` `tools_entries`) read every folder in `tools/` and every file there whose name ends with an import suffix (`.py`, `.pyc` or an extension module's suffix). A file's module name is its name less the longest import suffix; a folder's is its name. The checks leave out an entry whose module name holds a dot, such as `tools/prereg.old.py`: no import loads it under any name. They also leave out `tools/__pycache__`, Python's bytecode cache: Python writes it, git ignores it and the standard library has a folder of that name, so reading it would refuse every run. No check reads what it holds. A name with a hyphen is read: `sysconfig` imports its data module by such a name, and the name check now runs before it does (review I). The pre-registration's `.md` states this rule.
- **Added in M4 fix pass 9 (2026-11-10):** the forecast scorer's commit check of `tools/` (`tools/score_prereg.py` `uncommitted_entries`) refuses an entry of `tools/` (a file with an import suffix, or a folder) when HEAD does not hold it as committed. A file must be in HEAD with the same bytes. For a folder, HEAD must hold it as a folder, and every file with an import suffix directly in it must be committed as it is. Files deeper down, and files without an import suffix, are not checked. The pre-registration's `.md` said that a folder must be committed as it is (review J); it now says this. The scorer also refuses `_PYTHON_SYSCONFIGDATA_NAME`, as it refuses `PYTHONPATH`, `PYTHONHOME` and `PYTHONUSERBASE`: it names the module `sysconfig` imports, so a `tools/` file of that name would run before the commit check.

**Validation re-runs.**
- A frozen configuration may be re-run on validation at most **two** times after its run of record.
- A re-run is allowed only to fix a defect that a gate or a review found. It must log the commit and the reason (`runs.rerun_of`, `runs.rerun_reason`).
- Each re-run is charged as a trial (§2).
- Any parameter change is not a re-run: it is a new `config_hash`, and it goes back to development.
- A configuration that would need a third re-run is retired.

**Warm-up.** Realised-vol models are fitted on an expanding window of SPY daily bars starting 2000-01-03. They are refitted monthly using data up to *t* only, through the `MarketView` (ADR-0001), so the split guard covers signals too. Option-free history therefore removes the need for an options warm-up.

### 2. Trial accounting

- **The runs table is the trial log.** Every run is a row in `runs`, carrying a `trial_group` and a `run_purpose` (`trial` or `diagnostic`).
  - The trials of a group are its distinct `config_hash` values with `run_purpose = trial`, plus its validation re-runs. A frozen configuration's validation run of record repeats a configuration already counted in development, so it adds no trial.
- **PSR.** We report it with benchmark SR\* = 0, on daily excess returns, using their sample skew γ₃ and kurtosis γ₄:
  `PSR = Φ((SR − SR*)·√(n−1) / √(1 − γ₃·SR + (γ₄−1)/4·SR²))`.
  - **SR here is the per-period Sharpe ratio: daily, not annualised.** The formula is stated for the per-period SR, with n counting those periods. An annualised SR (√252 × daily, ADR-0007) put into it gives a wrong, inflated PSR. The annualised ratio is reported separately.
- **DSR.** It is the PSR evaluated at
  `SR* = √V[SR]·((1−γ)·Φ⁻¹(1−1/N) + γ·Φ⁻¹(1−1/(N·e)))`, where γ = 0.5772 (the Euler–Mascheroni constant). If N = 1, SR\* = 0.
- **N must count independent trials** (Bailey & López de Prado 2014). It is computed two ways, and both are reported.
  - **N_raw, the conservative count.** The number of trials in the group, plus one for each entry in the design-choice log (appendix). V[SR] is the variance of the trials' Sharpe ratios. This gives `dsr_raw`.
  - **N_eff, the effective count.**
    1. Align the daily excess-return series of the group's trials on their common sessions.
    2. Compute the correlation matrix ρ and the distance `d_ij = √(½(1 − ρ_ij))`.
    3. Cluster hierarchically with average linkage, and cut the tree at `d* = √(½(1 − ρ*))` with **ρ\* = 0.5**, fixed now, before any run. Trials whose returns are more than about 50% correlated therefore count as one.
    4. N_eff is the number of clusters.
    5. Each cluster is represented by the equal-weighted average of its members' excess returns, and V[SR] is the variance of those cluster Sharpe ratios.

    This gives `dsr_eff`. Sensitivity at ρ\* = 0.3 and 0.7 is reported but is never the headline. This is the trial-clustering idea of López de Prado & Lewis (2019, "Detection of false investment strategies using unsupervised learning methods"; the citation was not re-checked in this revision), with a fixed cut in place of their silhouette-based choice of the number of clusters, so that it is deterministic and cannot be tuned after the fact.
  - **The headline is `dsr = min(dsr_raw, dsr_eff)`,** reported with `n_trials` = N_raw and `n_trials_eff` = N_eff.
    - **Why the minimum, and why `n_trials` is N_raw.** `dsr_eff` alone is not a safe headline: in a null simulation with correlated variants it had a false-positive rate of up to 35.7%. The minimum is protected by `dsr_raw`, which does not rely on the clustering, so `n_trials` is the N behind that guard.
    - The SR and V[SR] in the DSR are per-period (daily) too.
- **What N still misses.** Choices made outside the runs table are counted only if they are in the design-choice log. Exploration in notebooks, and choices made while reading the literature, are not counted. So the DSR is an *upper* bound on significance, optimistic by an amount we cannot measure.

### 3. Regimes (descriptive splits; a strategy may use them only lagged)

- **VIX level**, on the *previous* session's close. Buckets: < 15, 15–20, 20–30, ≥ 30.
- **Term structure.** VIX/VIX3M ≥ 1 (backwardation) vs < 1. VIX3M availability is checked in M1.
- **Vol shock.** A session is a shock if VIX rises at least +25% or at least +5 points close to close. The 21 sessions after a shock form the "post-shock" regime. Results are reported for shock, post-shock and calm sessions separately.

### 4. Named stress windows

Each window runs peak to trough, close to close, using the dates in background §6. Every window is reported with a 21-session recovery tail.

| Window | Dates |
|---|---|
| Feb-2018 | 2018-01-26 → 2018-02-08 |
| Mar-2020 | 2020-02-19 → 2020-03-23 |
| 2022 | 2022-01-03 → 2022-12-30 |
| Aug-2024 | 2024-07-16 → 2024-08-05 |
| Apr-2025 | 2025-02-19 → 2025-04-08 |

- **2022 is reported as a drawdown-without-shock contrast,** not as a vol shock.
- **Aug-2024 is marked `NO_DATA`.** DoltHub has the window's start, 07-17 to 07-29 on Mon/Wed/Fri, but not the shock: nothing from 07-30 to 08-09, so the trough of 08-05 is missing. It is represented only by the stress-grid cells (−10%, +20) and (−5%, +10). For reference, VIX closed at 23.39 on 2 Aug and 38.57 on 5 Aug, and SPX fell 8.49% from its peak.

### 5. Spot × vol stress grid

The grid uses full revaluation, not greeks.

- **Shocks.**
  - Spot shocks *s*: {−20, −15, −10, −5, −2, 0, +2, +5, +10}%.
  - Parallel vol shocks *v*: {−10, −5, 0, +5, +10, +20, +40} vol points.
- **Revaluation.** For each cell, every lot is repriced with Black-76:
  - `F' = F·(1+s)`;
  - `σ' = max(σ_mark + v/100, 0.01)` at the lot's own strike (sticky strike);
  - τ is unchanged (an instantaneous shock);
  - shares are revalued at `S·(1+s)`.
- **Outputs.** P&L is reported in USD and as % of NAV.
- **When it is computed.** At the last session of each run, and at the start of each stress window.

## Alternatives considered

- **A random or rolling k-fold split.** Rejected. Vol regimes are autocorrelated, so a shuffled split leaks the regime into training. Purged walk-forward is a possible M6 extension, but not the protocol of record.
- **Defining regimes by drawdown.** Rejected, because of 2022: a grinding bear market with a positive realised VRP would be filed as "stress".
- **Contemporaneous VIX for regime labels in strategy logic.** Rejected: it uses the same close the strategy trades on (ADR-0002). For descriptive splits the lag barely matters, and it costs nothing.
- **A sticky-moneyness grid** (IV follows log-moneyness when spot moves). Not used for the base grid, because a spot drop would then make puts *cheaper* in vol terms, the opposite of the skew's reaction in a sell-off. Sticky strike is the simpler, more conservative choice for short puts. A sticky-moneyness variant will be added later.
- **A greek-based (Taylor) grid.** Rejected: it is wrong exactly in the large-shock cells we care about. Greeks are still reported next to the grid for comparison.

## Consequences and biases

- **Development years have fewer severe vol shocks than validation years.** The development period contains one severe shock, Feb-2018, plus Aug-2011, Aug-2015 and Q4-2018. Validation contains Mar-2020 and 2022. Strategies tuned in calm years may look worse in validation, which is the honest outcome.
- **The holdout runs in surface mode only,** so its numbers carry the surface-mode distortion (ADR-0009). They are reported next to the masked-run estimate of it, which is an estimate and not a bound.
- **The holdout is out of sample in data, but not in knowledge.**
  - Before any strategy was run, the background doc (§6) already described how Aug-2024 and Apr-2025 played out: the VIX path, the 9 Apr reversal, and that a book stopped out on 4–8 Apr missed it.
  - Whoever designs the stop and regime rules has read that.
  - Mitigations:
    - stop and regime rules are frozen with a written rationale before any holdout run;
    - no rule may refer to a 2024–26 event or date;
    - every holdout result is labelled "semi-blind".
  - A truly blind test needs data from after 2026-10-26.
- **The hard cap of record is optimistic about capacity** in every split. The validation capacity haircut shows by how much for 2021–23. For the holdout it cannot be measured.
- **Engine rules chosen on validation-period data.** The ADR-0004 surface rules were chosen by their mark error against quotes on 2022–23 OptionsDX, which is validation data. They were not chosen on returns, and they are in the design-choice log.
- **The parallel, sticky-strike grid ignores how the skew moves.** It probably understates losses for short-put books in large down moves.
- **A note for M4 (no ADR change).** The signal's realised vol is close-to-close, including the overnight return, annualised with 252 sessions so it is comparable with IV30. HAR is validated by Corsi only up to about 2 weeks ahead, so the 21-day horizon needs its own out-of-sample test on the development split.

## How we will test it

1. **PSR.** Daily SR = 0.10, n = 253, skew 0, kurtosis 3 → PSR = **0.9433**.
2. **DSR.** Inputs: N = 10 trials and a standard deviation of trial SRs of 0.05.
   - Φ⁻¹(0.9) = 1.28155 and Φ⁻¹(1 − 1/(10e)) = 1.78924, so SR\* = **0.07873**.
   - The same SR = 0.10 then gives DSR = **0.6319**.
3. **Regime boundaries.**
   - A previous VIX close of 19.99 → bucket 15–20; 20.00 → bucket 20–30.
   - VIX from about 17 to about 37 (2018-02-05) is a shock. VIX 30.0 → 33.0 is not: +10% and +3 points.
4. **Split guard.**
   - A run tagged `development` that creates a `MarketView` with any `as_of` after 2019-12-31 raises `SplitError`. The guard sits in the view, so signals are covered.
   - A `holdout` run whose `config_hash` has no frozen-validation record also raises.
5. **Grid cells.** One long call: S = F = K = 400, σ = 0.20, τ = 30/365, r = 0, base value $914.86. The test checks three cells:

   | Cell (spot, vol) | P&L |
   |---|---|
   | (0, +5) | +$228.63 |
   | (−10%, 0) | −$886.62 |
   | (−10%, +20) | −$493.07 |

6. **Aug-2024 coverage.** The stress-window report for a DoltHub run lists Aug-2024 with status `NO_DATA` and no metrics. It must not silently omit the row.
7. **N_eff.**
   - Ten synthetic trials over 1,000 sessions: five near-copies of series A (pairwise ρ ≈ 0.99) and five of series B, with corr(A, B) ≈ 0. Then N_eff = **2**, and N_raw = 10 plus the number of design-choice log entries.
   - Ten independent series give N_eff = 10.
   - In both cases `dsr` equals the smaller of `dsr_raw` and `dsr_eff`, `n_trials` equals N_raw and `n_trials_eff` equals N_eff.
8. **Re-run cap.** A third validation re-run of the same `config_hash` raises. Each allowed re-run increases N_raw by one.
9. **One cap rule of record.** A development, holdout or run-of-record validation run with `cap_mode = volume` raises. A diagnostic validation run with `cap_mode = volume` and a start before 2021-01-04 also raises.

## Appendix: design-choice log (counted in N_raw)

These choices were made at M0 with data from the samples in view. Each adds one to N_raw. Later milestones append to this list, in the ADR that makes the choice.

| # | Choice | Data in view when it was made | ADR |
|---|---|---|---|
| 1 | `volume_reliable_from = 2021-01-04` | OptionsDX volume, 2010–2023 | 0002 |
| 2 | Standard monthly expiries by default | OptionsDX volume by expiry type, 2021–23 | 0002 |
| 3 | Opening filters: bid ≥ $0.05, relative spread ≤ 25% | OptionsDX spreads, 2010–2023 | 0002 |
| 4 | Vol-shock definition (+25% or +5 points) and VIX buckets | Cboe VIX 1990–2026, which includes the holdout years | 0010 |
| 5 | Named stress windows and their dates | Cboe VIX/SPX 2018–2025, which includes the holdout | 0010 |
| 6 | ADR-0004 surface rules: Lee-clipped strike extrapolation, k/√τ tenor extrapolation | OptionsDX 2022–23 (validation) masked by DoltHub | 0004 |

Choices made without looking at these samples are not counted, for example the `exit_dte = 7` default, which came from the literature.
