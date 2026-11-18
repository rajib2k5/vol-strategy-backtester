# Trial logs

`m4.jsonl` is milestone 4's trial log: one line for each run of a development-grid configuration on real data.
`tools/run_m4_grid.py` appends the line after the run's ledger folder is in place. Nothing else writes to the file.

## What a line holds

Each line has exactly these keys, in this order (`run_m4_grid.LINE_KEYS`):

| Key | What it is |
|---|---|
| `date` | the UTC date of the run |
| `purpose` | why the run was made: the run of record, or the measurement run before it |
| `label` | the grid entry (`volbt.strategies.grid.m4_grid`), `<structure>/<entry>/<exits>` |
| `trial_group`, `split`, `sample_start`, `sample_end` | from the run's `runs` table |
| `config_hash`, `trial_hash` | `volbt.engine.run_config`: the configuration with and without where it ran (window, split, execution mode, data source) |
| `code_fingerprint` | `volbt.engine.loop.code_fingerprint`: every `.py` file under `src/volbt`, the library versions and Python |
| `data_fingerprint`, `source_commit` | from the run's `runs` table |
| `run_id` | the run's ledger folder, `run_id=<id>`, under `work_dir()/runs` (git-ignored) |
| `params` | the strategy's parameters, its signal's included |

A line holds no metric: no P&L, NAV, return, Sharpe, run status or exit count. `run_m4_grid.read_trials` refuses a
line with any other key.

## The counting rule

- **A trial is a distinct (`config_hash`, `code_fingerprint`, `data_fingerprint`) triple** among the lines of trial
  group `m4_vol` on the development split (`run_m4_grid.trials`).
- `config_hash` holds the window, the execution mode and the data source, so a run in another window or another
  execution mode is another trial. `trial_hash` drops those fields.
- `code_fingerprint` puts the code back: `config_hash` and `trial_hash` leave it out (`run_config.py`). It is
  `volbt.engine.loop.code_fingerprint`: every `.py` file under `src/volbt`, the library versions and Python.
- `data_fingerprint` is the store the run read. A rebuilt store is another trial.
- A run again with all three equal is the same trial: the same configuration on the same code and data gives the same
  ledger, byte for byte (ADR-0001 test 3).
- A run again after any change to `src/volbt`, a library or Python, or on another store, window or execution mode, is a
  new trial.
- The first version of this rule counted distinct (`trial_hash`, `code_fingerprint`) pairs. That undercounted: a run
  for a new window, a new execution mode or a rebuilt store has the same `trial_hash` and the same code. The B2a
  review found it (claim 3); the key was changed on 2026-11-17 (fix pass 1). On the log of record the two keys agree
  (36 trials each, measured), because every line has the same window, mode, code and store.
- `N_raw` = the trials + the entries of ADR-0010's design-choice log: 10 after milestone 4 (rows 1-6 of the
  appendix and the plan's rows 7-10) (`run_m4_grid.n_raw`).
- After the grid of record (2026-11-17, `tools/run_m4_grid.py --workers 4`): 37 lines, the 36 grid runs and one
  measurement run of the same configuration, code and data as the grid's run of its label; 36 trials; N_raw 46.
- A label that ran more than once is read from its last line (`run_m4_grid.latest_by_label`): `tools/report_m4.py`
  and `tools/export_app_data.py` read those runs.

## Runs that are not trials: the nine diagnostic runs of record

`docs/validation/prereg/runs_of_record.jsonl` holds 9 lines. They are not in this log and do not count as trials.

- 8 are smoke runs on the validation split (2020-01-02 to 2023-12-29), trial group `m4_smoke`. 1 is the budget run,
  on 2010-01-04 to 2023-12-29. All nine have `run_purpose` diagnostic.
- Each printed only M3's health lines (run id, status, sessions, timings, counters, the cash and NAV identity errors,
  mark-source shares and mark flags) and the share of sessions where the signal `s` is defined (`tools/smoke_m4.py`).
  No P&L, return or Sharpe was printed. Each run deleted its folder.
- The smoke runs' sessions are all after 2019-12-31. They tested the code and measured the share of `s`.
- The budget run is the short strangle with `always` entry and the DTE exit at 14, the HAR signal, OptionsDX quote
  mode. Its configuration equals the grid entry `short_strangle/always/dte`, except the purpose, the diagnostic kind,
  the window end (2023-12-29, not 2019-12-31), the split and the trial group (measured with `config_json`). So it
  covered the development dates. It printed only its run id, status, sessions, timings and the load average
  (`tools/smoke_m4.py:137-150`), kept no result and deleted its folder.
- It is not counted because it chose nothing: no number of it was used to pick, drop or tune a configuration, and the
  configuration it ran is counted once in this log, with the grid's run of its label. A second count would have
  inflated `N_raw`. The owner can override this (LEARNING_LOG row 172).
- The nine lines have the old `trial_hash` formula: none of the 8 distinct `trial_hash` values among them is a
  `trial_hash` in `m4.jsonl` (measured).

## The rules this log follows

- Every line names a run whose folder exists under `work_dir()/runs`.
- Every development run of trial group `m4_vol` in that folder has a line.
- `tests/test_real_m4.py` checks both (marked `real_data`).
- No P&L, NAV, return or Sharpe of any of these runs is in a committed file, for any date, before milestone 6
  (decision D19, extended to every date: default taken 2026-11-17, owner can override).
