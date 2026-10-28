# ADR-0010: Evaluation protocol: sample splits, trial counting, regimes, stress windows and the stress grid

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
   - VIX 17.31 → 37.32 (2018-02-05) is a shock. VIX 30.0 → 33.0 is not: +10% and +3 points.
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
