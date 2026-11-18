# Milestone 4: four strategies, the VRP signal and the forecast test

> **Data notice.** The DoltHub figures in this document (counts, dates, quantiles and summaries, in its text and in its tables) are derived from the DoltHub database `post-no-preference/options` (<https://www.dolthub.com/repositories/post-no-preference/options>), licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), and are shared under the same licence. Changes: we aggregated it into counts, shares and quantiles, compared it with OptionsDX and ran our pricing build on it; no quote row is reproduced. The rest of this repository is MIT. See [DATA.md](../../DATA.md).

Status: built. **What was reviewed.** Parts A and B1 (the interfaces, the position P&L, the signals, the inference code, the pre-registration tools and the strategies) went through nine review rounds; [`docs/validation/04-ledger.md`](../validation/04-ledger.md) lists each claim, verdict, fix and test. Part B2 is the grid of record, the export and the app pages, and this document with its notes, notebook, ADRs and diagrams. Its builder ran its own checks. An adversarial review of the grid and the export found one major and three minor defects, and a fix pass fixed them ([04-ledger](../validation/04-ledger.md), part B2). A verifier re-measured the figures in these documents. **Nothing here is a result.** No P&L, NAV level, return or Sharpe ratio of any M4 run, for any date, appears in this document, in the notebook, in the committed logs or in the app (decision D19, extended to every date before M6: LEARNING_LOG row 173). The app shows each position's exit reason: a `profit_target` or `stop` reason says that the position's hedged P&L crossed its threshold on that date, and plan section 8 allows that for development data. The grid's 36 runs are development trials, "in-sample, 36 trials of N_raw 46, selection-biased, no claim".

Every number below names the command or the file it came from, and the day. Five sources give most of them:

- **[trace]** The ledger tables of development run `10d433dd0b1c28c5d1a116200e682c1f48928eab9eec2ff801d60810427bf0e8` (the gated short straddle, entry threshold 0, every exit on), read with pyarrow, and the store read through a view (2026-11-17). The code to read them back is under "Data flow".
- **[grid]** `uv run python tools/run_m4_grid.py --workers 4` (2026-11-17 local): 36 runs, all `status ok`, 2,516 sessions each. Its trial log is `docs/validation/trials/m4.jsonl`.
- **[report]** `uv run python tools/report_m4.py` (re-run 2026-11-17: 731 lines, 36 blocks, equal to the builder's output except the timings). It prints M3's health whitelist, position counts and the signal's coverage, and no P&L.
- **[listing]** `uv run python tools/measure_listing.py` (2026-11-17): the listing and session counts of the plan's section 1, re-measured.
- **[forecast]** `docs/validation/prereg/2026-11-09-forecast-har-vs-naive.result.json` and the last section of [the ledger](../validation/04-ledger.md).

> ### Guess first (ungraded)
>
> Write your guesses down *before* you read on. They are not graded. The point is to find out where your picture of a volatility signal is wrong.
>
> 1. A 30-calendar-day window holds a number of sessions. **What are the smallest and the largest number in ten years of development data?** If you annualised realised variance with 252 sessions instead, **by how much would the signal be biased on the shortest window?**
> 2. The pre-registered forecast test compared the HAR forecast with the naive 22-day mean on QLIKE. **Which won, and with what p-value?** Is "significant at 2.5%" an honest way to say it?
> 3. On **how many of the 2,516 development sessions** has the signal no value, and why?
> 4. The traced position was opened on 2010-04-27, after a signal on 04-26. **Why not a week earlier?** And **what ended it**, and when?
> 5. **How many trials** do the 36 grid configurations make, and what is N_raw?
> 6. A close order is created when the next session is at most 14 days from expiry. **At how many days before expiry do the closes of the traced run fill?**
> 7. The HAR forecast for 2010-04-26 is **how many times** the naive forecast?
>
> Answers are in "Measured results".

---

## What we built and why

M4 puts the first real strategies on the M3 engine. It builds a **signal**: the log ratio of the implied variance of the next 30 calendar days (IV30) to a forecast of the realised variance over the same days. It builds **four structures** (a short and a long ATM straddle, a short 0.25-delta strangle, a straddle calendar), their **contract picks**, their **entry and exit rules**, and a **grid** of 36 development configurations. The engine changes so that signals are computed causally at step 9 and written to a `signals` table, and so that every position has a **hedged P&L** that the stop and the profit target can read.

It also builds the machinery for **using the evaluation protocol once**: a hash-frozen pre-registration, a one-shot scorer, a spent ledger and a run gate. It used them on one claim, the forecast test: does the 21-session HAR forecast beat the naive RV22? The answer, scored once on development data, was yes, at roughly 5%-level evidence, with QLIKE as a proxy loss. It chose the signal's RV model. Everything about strategy performance waits for M6.

What a user can now do: run `tools/run_m4_grid.py` and `tools/report_m4.py`, read `signals` and `position_daily` in a run's ledger, and open the app's Signal and Strategies tabs.

## Why this design

| Choice | Alternatives | Why this one | What it costs |
|---|---|---|---|
| Returns from the **unadjusted close plus the ex-date dividend** | The adjusted close | The view serves no adjusted close: an adjusted close on day t is scaled by every dividend paid after t | One more table read per session |
| **HAR-RV in levels, direct 21 sessions, refitted on the first session of each month** | Logs; GARCH or GJR; a daily refit; one fit on the whole sample | Cited form; GARCH needs `scipy.optimize`, an ADR change, and adds trials; a whole-sample fit leaks the future (ADR-0001 test 6) | A level fit can forecast 0 or less after a spike: a fallback to the naive forecast, counted (0 on the traced run) |
| A fit uses only the pairs whose **target ended by the fit date**, at least 504 | Every pair up to t | A pair whose target runs past the fit date holds the future | The signal starts in 2002 on the store's bars, not at once |
| The window is **counted from the calendar** | 252 sessions a year | A window holds 17 to 22 sessions; 252 biases the ratio by ln(21/17) = 0.2113 on a 17-session window | The engine reads the future calendar (decision D3), which leaks an unscheduled closure a day early |
| **IV30 from the surface at k = 0**, the same call as `atm_iv_30d` | A model-free variance from all strikes | The engine already has the call, and the marks use it | One strike, not the whole smile |
| The position P&L is **hedged and computed by the engine** | Option-only P&L; strategies pricing their own marks; hedge shares shared pro rata by delta | The hedge is book-level; a second pricer would be a second ADR-0004; pro rata is unbounded when deltas nearly cancel | The P&L exists only under a daily close hedge with next-close fills (null elsewhere) |
| Entries on **the standard monthly at 50-60 DTE**, one position per expiry, at most two open | The monthly nearest 45 DTE, one position at a time | DoltHub lists that monthly on every measured session (162 of 162 and 54 of 54), so every split trades the same contracts | Two open positions double the exposure until M5 |
| **`exit_dte = 14`** in every split | 21 (always cross-expiry); 7 (always extrapolated in tenor) | At 14 DTE the monthly's own expiry is listed on 31 of 31 and 11 of 11 sessions | A holiday or weekend can make it "at most 14" (position 2 below) |
| Exits in the order **stop, profit target, signal, DTE**, one close order per position | Several orders per position | A fixed order makes the reason reproducible; D22 allows one pending order per position | A stop acts on the close and fills at the next one |
| **`FixedPackages(10)`** until M5 | A tuned size; vega sizing now | A tuned size is another trial; vega sizing is M5 | No budget acts in M4 |
| **Pre-register, score once, spend first**, strategy freeze at the end of M5 | Freeze at M4; freeze inside M6 | M5's risk rules change the configurations; M6 attribution would sit between selection and freeze | The machinery is heavy for one claim |
| A trial is a **(config hash, code fingerprint, data fingerprint) triple** | A distinct config hash; the (trial hash, code fingerprint) pair, which review refuted | The hashes leave the code out, so a re-run after a code change would count as no new trial; the trial hash also drops the split, dates, mode and source | A code change that does not touch the grid's behaviour still counts as a new trial |

## Code walkthrough

Read in this order. Each step names one file and line (as of the working tree on 2026-11-17).

1. `src/volbt/signals/base.py:34` `SignalValue` (frozen: the signal, IV30, its flags, the forecast, the model, the fit date, `n_window`, the flags, the spread and the lagged regime) and `:63` `Signal` (`reset()` and `update(view, n_window)`). The flag bits are at `:26`.
2. `src/volbt/signals/realised.py:29` `total_log_returns` and `:54` `window_mean`. [Concept 19](../concepts/19-realised-variance-from-daily-bars.md).
3. `src/volbt/signals/har.py:61` `regressors`, `:69` `targets`, `:78` `fit` (it cuts `v` at the fit date before it builds a pair), `:100` `har_forecast` (the fallback), `:113` `month_start`, `:120` `HarForecaster` and `:128` its `forecast`. [Concept 20](../concepts/20-har-and-causal-refits.md).
4. `src/volbt/signals/iv30.py:42` `iv30` and `src/volbt/signals/regime.py:61` `lagged_regime` (the VIX bucket and regime of the previous VIX session).
5. `src/volbt/signals/vrp.py:43` `rv_hat`, `:50` `VrpSignal` and `:68` `update`: returns, forecast, IV30, the log ratio. [Concept 21](../concepts/21-iv30-log-variance-ratio-and-calendar-time.md).
6. `src/volbt/engine/loop.py:196` `n_window` (from the calendar), `:704` `update_signals` (once per signal, through the session's view, one `signals` row each) and `:722` `step_09_decide` (the strategy sees the values in `ctx.signals`). `:662` `check_intent` refuses an opening leg more than 180 days out. `:604` `position_rows` writes `position_daily`.
7. `src/volbt/engine/positions.py:46` `computed` (when a position P&L exists) and `:74` `position_pnl`. [Concept 23](../concepts/23-exits-on-a-hedged-book.md).
8. `src/volbt/strategies/expiry.py:46` `standard_monthly`, `:112` `monthly_in_window` and `:130` `next_monthly`. `src/volbt/strategies/structures.py:72` `atm_straddle`, `:82` `delta_strangle`, `:100` `straddle_calendar` and `:110` `Chain` (the session's listed options, read through the view). [Concept 22](../concepts/22-structures-and-contract-selection.md).
9. `src/volbt/strategies/rules.py:56` `allows` (an entry), `:96` `exit_reason` (the precedence). `src/volbt/strategies/sizing.py:27` `FixedPackages`.
10. `src/volbt/strategies/vol.py:90` `decide`, `:116` `exit_order` and `:130` `entry_order`. `src/volbt/strategies/grid.py:59` `m4_grid` (the 36 configurations).
11. `src/volbt/engine/ledger.py:89` `signals` and `:93` `position_daily`, the two new tables.
12. `src/volbt/analytics/inference.py:221` `ewc_bootstrap` (the registered test), `:91` `qlike`. `tools/forecast_test.py:77` `paired`, `tools/score_prereg.py:264` `score`, `tools/prereg.py:598` `make_run_gate`. [Concept 24](../concepts/24-pre-registration-and-block-inference.md).
13. `tools/run_m4_grid.py:105` `decided_rv_model` (reads the decision from the committed result), `:267` `run_grid`, `:337` `n_raw`. `tools/report_m4.py:59` `report`. `tools/smoke_m4.py:112` `smoke`.
14. `tools/export_app_data.py:599` `signals_timeline_body`, `:660` `strategy_positions_body` and `:727` `m4_bodies`. `app/src/lib/contract.ts:2526` `parseSignalsTimeline` and `:2699` `parseStrategyPositions`; `app/src/views/SignalPage.tsx` and `app/src/views/StrategiesPage.tsx`.
15. `tests/signal_store.py`: a made-up store with bars from 2017-01-03 and clustered volatility, for ADR-0001 test 6 (`tests/test_signals_causal.py`, `tests/test_strategy_causal.py`).

The notebook `notebooks/04_strategies_and_signal.ipynb` (built from `realised.py`, `har.py`, `vrp.py`, `regime.py` and `inference.py` by `tools/build_notebooks.py`) and the redrawn diagrams in `docs/architecture/out/` (`data_model_ledger_erd`, `engine_daily_loop_sequence`) are made by other steps and are not described here.

## Data flow

One position, followed from its signal to its exit: **position 4 of development run `10d433dd…`**, a short straddle on the 2010-06-18 expiry. The run is the gated short straddle (entry when s ≥ 0, exits on the signal at s ≤ −0.4, the stop and the profit target, and DTE). To read the values back:

```python
import pyarrow.parquet as pq
R = "data/runs/run_id=10d433dd0b1c28c5d1a116200e682c1f48928eab9eec2ff801d60810427bf0e8"
table = lambda name: pq.read_table(f"{R}/{name}/part-0.parquet").to_pandas()
table("positions"), table("signals"), table("orders"), table("order_legs"), table("lots")
```

1. **The signal at the close of Monday 2010-04-26** (step 9). `VrpSignal.update` read the bars and dividends through that day's view: 2,592 total returns. The HAR forecast used the fit dated 2010-04-01 (the first session of April), 2,534 pairs; its forecast mean daily variance was 8.401e-5, a daily volatility of 0.917%. `n_window` was 22 sessions in (04-26, 05-26]. RV^ = √(22 × 8.401e-5 × 365/30) = **0.14995**. IV30, read from the surface at k = 0 and 30/365, was **0.152047**. So **s = 2 ln(0.152047/0.14995) = 0.0277**. The lagged VIX label was bucket 15-20, regime `calm`. The flags were 0.
2. **Why not a week earlier.** The 06-18 expiry is inside the 50-60 DTE window from 04-19 (60 days) to 04-29 (50 days). On 04-19 and 04-20 s did not exist: IV30 was NaN with `SURFACE_EXTRAP_TENOR`, because 30 days was not bracketed by two expiries (flags 4). On 04-21, 04-22 and 04-23 s was −0.339, −0.266 and −0.030, all below the entry threshold 0. On 04-26 it was +0.0277, the first value at or above 0. The book held one position (position 3, expiring 05-21), under the limit of two, and 06-18 had not been held. So the entry was allowed.
3. **The contract pick** (`entry_order`). The listed standard monthlies that day were 2010-05-21 (25 DTE), **2010-06-18 (53 DTE)** and 2010-07-16 (81 DTE). Only 06-18 is in 50-60. Its parity forward was 120.84. The strikes near it, 119 to 123, are 1.84, 0.84, 0.16, 1.16 and 2.16 away, so the ATM strike is **121**. The legs are `SPY   100618C00121000` and `SPY   100618P00121000`, ratio −1 each, 10 packages (`FixedPackages(10)`). The order carried `entry_signal` 0.027711, which the `positions` row holds.
4. **The order and the fill** (created 04-26, step 9; filled Tuesday 2010-04-27, step 3). `check_intent` passed: both legs expire 53 days out, under 180. The order (id 6) has two legs and filled 10 packages at the quote of 04-27: a sale fills at the bid at k = 1 (concept 13). The position opened on 04-27. The ledger holds 2 orders (6 and 8), 4 order legs, 4 fills and 2 lots for it.
5. **The nights** (ten sessions, 04-27 to 05-10, with 10 `position_daily` rows). Each close marked both lots, hedged, and wrote the position's hedged P&L, which this document does not quote. The signals table shows what the strategy saw: s was +0.0744 (04-27), −0.0617 (04-28), −0.3435 (04-29), −0.0576 (04-30), −0.3582 (05-03), −0.0795, +0.0780, +0.1334 and +0.7021 (05-07). On 05-03, the first session of May, the HAR forecast was refitted: `model_fit_date` moved from 2010-04-01 to 2010-05-03. The lagged VIX label was `shock` on 04-28 and `>=30` and `shock` on 05-07, the session after 2010-05-06 (the day of the "flash crash"). No close order exists for the position before 05-10, so no exit held on any of those sessions.
6. **The exit decision** (Monday 2010-05-10, step 9). s was **−0.547**, at or below the signal exit of θ − 0.4 = −0.4. `exit_reason` checks the stop and the target first. Neither held, because the reason came out as `signal`. The DTE exit did not hold either: the next session, 05-11, was 38 days from 06-18, and the rule needs at most 14. `exit_order` made one close order for the position: 10 packages, ratio +1 on each leg (order 8).
7. **The close fills** (Tuesday 2010-05-11, step 3). A buy to close fills at the ask at k = 1. Both lots went to quantity 0, and the position closed on **2010-05-11** with exit reason `signal`. The `position_daily` rows run from 04-27 to 05-11: 11 rows.
8. **The files.** `strategy_positions.json` lists the position with `opened` 2010-04-27, `closed` 2010-05-11, the two legs with ratio −1, `entry_signal` 0.027711 and exit reason `signal`. The page draws it as a bar coloured by the exit reason, under the banner "36 development trials; no performance shown before M6".

**A second position, for the DTE exit.** Position 1 (expiry 2010-03-19) was closed by `dte`: the order was created on 2010-03-04, when the next session (03-05) was 14 days from the expiry, and filled on 03-05. Position 2 (expiry 2010-04-16) shows why the rule says "at most 14": 14 days before is Good Friday, 2010-04-02, so the order created on Thursday 04-01 filled on Monday 04-05, 11 days before. Across the run, 15 of the 16 positions closed on `dte` filled exactly 14 days before settlement, and position 2 filled 11 days before [trace].

## Pitfalls met and how each is guarded

| Pitfall | How it shows up | Guard |
|---|---|---|
| **A fit that knows the future** | A HAR fitted once on the whole sample moved a forecast at t₀ from 2.985e-03 to 2.992e-03 when only later data changed (the M0 review's probe) | Refit monthly from pairs that ended by the fit date; ADR-0001 test 6 at four t₀; the full-sample HAR and a view at `sample_end` as the mutants that must fail (`tests/test_signals_causal.py`) |
| **A signal that depends on where the run started** | A run that starts mid-month would fit on its first day, not on the month's first session | The fit date is the first session of t's month, found from the bars, so a mid-month start gives the same values (`tests/test_signals_har.py:188`) |
| **State from another run** | A strategy object run twice reused last run's monthly fit in the same month | `reset()` before every run (LEARNING_LOG 107); a signal without it is refused |
| **A 17-session window read as 21** | Bias of 0.2113 in s | `n_window` from the calendar; `WINDOW_EMPTY` flags n = 0 |
| **HAR forecasts 0 or less** | A negative variance has no square root | The naive fallback with `RV_FALLBACK`; the count is reported |
| **An option-only stop** | A hedged short straddle stopped on a move its hedge paid for | The hedged position P&L, computed by the engine; null (and a refused stop) where the hedge is not the daily close hedge |
| **A close that cannot fill at 14** | A holiday or a weekend | "At most 14", and the order waits for the next snapshot |
| **A leg past 180 days** | One DGS3MO rate leaves a carry gap | `check_intent` refuses it, whatever strategy wrote it (a scripted 363-DTE straddle once filled) |
| **A trial that is not counted** | `config_hash` leaves the code out | The trial is a (config hash, code fingerprint, data fingerprint) triple; the trial log is checked for completeness (`tests/test_real_m4.py`) |
| **A second look at the forecast window** | The scorer could be run again until the answer is right | It writes the spend to `spent.jsonl` first, refuses a spent window, and checks hashes and the scorer's closure |
| **A result that leaks through a count** | An exit count depends on the stop, which depends on P&L | After 2019 only P&L-independent health runs; before M6 no P&L of any M4 run in a committed file or tool output |
| **Reading "p = 0.0139" as 1.4% evidence** | The test's size at its threshold is above its nominal one | The result carries the effective sizes beside p; the wording is "roughly 5%-level evidence" |

## Measured results

### The guesses, answered

1. **Window sizes.** In the development run's `signals.n_window`: 17 sessions on 3 sessions of the run, 18 on 36, 19 on 334, 20 on 576, 21 on 1,018 and 22 on 549 [trace]. So the smallest is 17 and the largest 22. With 252 the bias on a 17-session window would be ln(21/17) = **0.2113**, about half the 0.4 band.
2. **The forecast test.** HAR won: **p = 0.0139** against the registered threshold 0.025, mean(d) = 0.2477, 95% interval [0.0401, 0.5991], EWC t 2.691, n = 2,495 sessions from 2010-01-04 to 2019-11-29, n/block = 118.8 [forecast]. "Significant at 2.5%" overstates it: at that line the test rejects mean-0 nulls at 0.0508 and 0.0502 (two seeds), at 0.011 to 0.083 across the matched nulls and at 0.189 on the worst, so it is about 5%-level evidence. QLIKE is a proxy loss, the window is development data, and no stake rides on it (concept 24).
3. **Sessions with no signal.** **32 of 2,516**: 5 where 30 days is not bracketed by two expiries (2010-01-15, 01-19, 04-16, 04-19 and 04-20; flag `SURFACE_EXTRAP_TENOR`) and 27 with no usable smile. s is defined on 2,484 sessions (0.9873) in every one of the 36 runs [report; trace]. The HAR fallback count is 0.
4. **The traced position.** Opened 2010-04-27 after the signal of 04-26 (not earlier because s was NaN on 04-19 and 04-20 and negative on 04-21 to 04-23), ended by the **signal exit decided on 2010-05-10** (s = −0.547) and filled on 2010-05-11 [trace].
5. **Trials.** 36 configurations, 36 trials (36 distinct config hash, code fingerprint and data fingerprint triples among 37 log lines: the 36 grid runs and one measurement run of the same configuration). N_raw = 36 + 10 = **46** [grid; `run_m4_grid.n_raw`].
6. **DTE fills.** 15 of the 16 `dte` closes in the traced run filled exactly 14 days before settlement; one filled 11 days before (Good Friday) [trace].
7. **HAR against naive on 2010-04-26.** HAR's forecast variance 8.401e-5 against the naive 3.687e-5: **2.28 times**. The constant term of the fit is the largest of the four terms (concept 20). On that day the naive forecast would give s = 0.851 against HAR's 0.0277, which is one day's comparison and no finding.

### The grid of record

`tools/run_m4_grid.py --workers 4` ran the 36 configurations in 278.6 s wall, with a peak of 2,400.2 MiB per worker; one measured run took 29.04 s alone (LEARNING_LOG row 174). Each run covers 2,516 sessions, 2010-01-04 to 2019-12-31. Every run's `status` is `ok`, and `report_m4` prints its M3 health block [report]. The grid's RV model is `har`, read from the committed forecast result by `decided_rv_model`, not typed in (row 171).

### Health of the traced run

From the report's block for `short_straddle/above_0.0/dte+signal+pt_sl`: cash equals the initial cash plus the sum of its flows on every session, and the NAV identity's maximum error is 0.00e+00 USD; there are 2,497 snapshot sessions of 2,516; the in-NAV marks are 97.29% `QUOTE_MID`, 1.53% `SURFACE_MODEL` and 1.18% `STALE_SURFACE`; **20 of 2,516 sessions are DEGRADED** (11 in 2010, 7 in 2011, 1 in 2012, 1 in 2019); the run has 196 option fills, all at the quote, every one at the far side of the quote (k = 1); the hedge wrote a row on all 2,516 sessions (99,328 shares traded in all) and left at most 0.4984 shares of delta; and there are two early assignments of short calls, decided 2010-03-18 and 2013-09-19 (both by the closed form) [report].

### The listing counts behind 50-60 and 14

On DoltHub (2020-22 and 2023) a standard monthly at 50-60 DTE is listed on 162 of 162 and 54 of 54 session-expiry pairs, at 36-49 DTE on 32.2% and 30.3%, at 29-35 on 1.0% and 33.3%, at 15-21 never, at 14 on 31 of 31 and 11 of 11, and at 7 never. On OptionsDX, 1,010 of the 2,497 development snapshots have a standard monthly at 50-60 DTE [listing]. (The plan's "54.1%" at 10-14 DTE is 33 of 62 = 53.2%; the tool's figure replaces it.)

### Tests, app, data and gates

The test files of this milestone are `tests/test_signals_*.py`, `tests/test_strategy_*.py`, `tests/test_engine_positions.py`, `tests/test_inference.py`, `tests/test_forecast_test.py`, `tests/test_prereg*.py`, `tests/test_m4_*.py`, `tests/test_run_m4_grid.py`, `tests/test_report_m4.py`, `tests/test_smoke_m4.py`, `tests/test_export_m4*.py`, `tests/test_real_m4.py` and the notebook tests in `tests/test_notebooks.py`. This document does not quote a total: the orchestrator records the full gate run at commit. The gates of this part that were run for this document: `tools/build_notebooks.py --check`, `tests/test_notebooks.py`, `tests/test_diagrams.py`, the diagram check and the Mermaid render gate, `tools/licensing/scan_real_rows.py` (the same 30 lines it flagged before), `tools/licensing/check_tracked_data.py`, and a link checker over the new and changed documents.

## Mutation runs

Every new or changed test of this part has one hand mutant that must make it fail, run in a scratch copy: the notebook tests (a wrong stub constant, a full-sample fit in the causal demo, a negative-mean `d`, a stale notebook, a wrong horizon line, a dropped notebook in the build, a dividend not added back, and a `.gitattributes` that no longer pins notebooks: 8 mutants, 8 killed). The mutants of parts A, B1 and B2a are in [the ledger](../validation/04-ledger.md) and in the builders' reports.

## Decisions taken in M4 that the ADRs did not fix

Each is a default, taken on its date, that the owner can override (LEARNING_LOG, the rows named):

- **The RV model comes from the committed forecast result**, with checks (row 171).
- **A trial is a (config hash, code fingerprint, data fingerprint) triple** (ADR-0010 amendment 8; the first key, trial hash and code fingerprint, was refuted by the B2a review and replaced in its fix pass; LEARNING_LOG row 172).
- **D19 applies to every date before M6** (row 173).
- **The measurement run is a run of record; 4 workers** (row 174).
- **The app shows the gated configuration of each structure at θ = 0** (row 175).
- **The exporter always writes the M4 files, except with `--without-m4`** (row 176).
- **Real export from a clean clone** (row 177).
- **This document's traced position** (row 178): position 4 of the gated short straddle, because it shows a signal entry, a signal exit, a monthly refit and a volatility spike in one position.
- **Placement and status of ADR-0011 and the amendments** (rows 179 and 180).
- **The notebook's scope** (row 181) and **what the documents quote** (row 182).

Not changed (scope): the Strategies page heads all four cards "VolStrategy" and the Signal and Strategies pages show no "Data sources and terms" notice (the M3 pages do). They are follow-ups for the owner.

## Not done in M4

- **No strategy result.** No P&L, NAV, return, Sharpe, PSR or DSR of any M4 run. That is M6.
- **No risk rules.** Greek budgets, the stress-loss budget, margin and vega sizing are M5; positions are 10 packages, and two may be open at once.
- **No GARCH or GJR**, and no log-HAR. They need `scipy.optimize` (an ADR change) and add trials.
- **No strategy pre-registration, no validation or holdout run.** The pre-registration freezes at the end of M5. The M4 health runs after 2019 print mechanics only.
- **The forecast test has one weakness left open:** `spent_by` compares window dates only; a later window that starts on 2019-12-02 would not be refused (04-ledger, "Open, not fixed here").
- **The calendar's holdout is sparse**: a 22-35 DTE monthly is rarely listed on DoltHub (1.0% and 33.3% at 29-35 DTE).
- **The documents' figures were re-measured, the prose was not reviewed.** A verifier re-measured about 150 figures in this part's documents with its own code (the router's row 10), and none disagreed. No independent reader reviewed the prose.

## Concepts used

- [Realised variance from daily bars](../concepts/19-realised-variance-from-daily-bars.md)
- [HAR and causal refits](../concepts/20-har-and-causal-refits.md)
- [IV30, the log variance ratio and calendar time](../concepts/21-iv30-log-variance-ratio-and-calendar-time.md)
- [Structures and contract selection](../concepts/22-structures-and-contract-selection.md)
- [Exits on a hedged book](../concepts/23-exits-on-a-hedged-book.md)
- [Pre-registration and block inference](../concepts/24-pre-registration-and-block-inference.md)
- From milestone 3: [the daily loop](../concepts/12-daily-loop.md), [the delta hedge and gamma rent](../concepts/16-hedged-gamma-rent.md), [look-ahead through reads and state](../concepts/18-look-ahead-through-reads-and-state.md)
- From milestone 2: [the smile in total variance](../concepts/11-smile-in-total-variance.md)

## Explain it back

Answer aloud first, then check against the code and the ADRs. They get harder as they go.

1. **The signal.** Write s_t from IV30 and the forecast. Why does the window hold n sessions and not 21, what is ln(21/17), and what does the engine do when n is 0? Why is the forecast's unit variance per session, and IV30's per calendar year?
2. **Realised variance.** Why add the dividend back to the unadjusted close? Why not use the adjusted close? What is the variance of r² for a normal r, and why does that not break QLIKE?
3. **HAR and causality.** Name the three regressors and the target. A fit is dated F: which pairs may it use, and why? Why does a run that starts mid-month give the same values? Explain ADR-0001 test 6 (four t₀, the perturbation, the premise, the mutants that must fail), and the fallback.
4. **Contract picks.** On 2010-04-26, which expiry and strike, and why? Why 50-60 DTE (the DoltHub figures) and not 45? What does a strangle's strike pick use for delta, and why the engine's own inputs? What does the calendar need that the others do not?
5. **Exits on a hedged book.** Write the position P&L. Why must it be hedged? When is it null, and what does a stop do then? Give the exit order and say what happens when two exits hold. Why is the DTE exit "at most 14"? Which exit ended position 4, and why not the stop?
6. **Why 14.** Give the three DTE choices and the listing figure that rules out each other one. What is the cost of a close at 14 (a stale or extrapolated mark)?
7. **The test and the spend.** State the claim, the metric, the block, the threshold and the decision rule. Why is p = 0.0139 "roughly 5%-level evidence", and what else is in the result's label? What does `spent.jsonl` do, and what does the run gate refuse? Why does the strategy pre-registration freeze at the end of M5?
8. **Trials.** Why is a trial a (config hash, code fingerprint, data fingerprint) triple, and why did the first key undercount? What is N_raw after M4 and what does it feed? Why does the document show no P&L for any date, and which document tells M6 what to test?
