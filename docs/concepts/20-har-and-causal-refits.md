# HAR and causal refits

## First principles

A forecast of the next month's variance is a number a trader could have had at the close of day t, or it is not a forecast. A model fitted on the whole sample and then "run" through the past uses parameters that knew the future ([concept 18](18-look-ahead-through-reads-and-state.md)). The fix is to refit on a schedule, and to fit each time only on what had already ended.

**HAR-RV** (heterogeneous autoregressive realised variance, Corsi 2009) is a linear regression of future variance on three past averages of variance: the last day, the last week and the last month. Traders look at different horizons, and the three averages are a cheap way to let each horizon matter.

Terms:
- **v_i = r_i²** ([concept 19](19-realised-variance-from-daily-bars.md)).
- **Day, week, month**: v_i, the mean of v over 5 sessions, and the mean over 22 sessions, each ending at i.
- **Target**: y_i, the mean of v over the next 21 sessions (Andersen, Bollerslev and Diebold 2007 call this the direct multi-horizon form). Corsi's own equation fits the one-day target.
- **Pair**: one regressor row x_i with its target y_i. A pair is usable at date F only if its target has ended by F.
- **Fit date**: the date a fit is stamped with. Its last target ends on or before that date.

## The maths

x_i = [1, v_i, mean v_{i−4..i}, mean v_{i−21..i}] and y_i = mean v_{i+1..i+21}.

The fit is ordinary least squares, `numpy.linalg.lstsq(rcond=None)`, on the pairs whose target ends on or before the fit date F. With fewer than 504 pairs (two years) there is no fit. The forecast at t is the dot product of x_t and the fitted coefficients.

**The refit schedule.** A fit is made on the first session of each calendar month and kept for that month. The fit date of the forecast at t is the first session of t's month, found from the bars the view serves. So a run that starts in the middle of a month fits as of that month's first session, exactly as a run that started years earlier did. A signal value depends on its date, never on the run's start.

**The causal property, in one line.** A fit dated F, given data cut at F, equals the fit given all the data. Notebook 04 shows it on a made-up path: the fit dated ten sessions before t₀ and the forecast at t₀ are equal when every value after t₀ is multiplied by 3 and permuted, and a full-sample fit is not.

**Fallback.** HAR is a regression in levels. After a spike the forecast can be zero or below. Variance cannot be, so a forecast of 0 or less is replaced by the naive RV22 and flagged `RV_FALLBACK` (flag value 1). No session of the traced development run carries it: the run's signal flags are 0 on 2,484 sessions and 4 (`IV30_MISSING`) on 32, with no 1 (the run's `signals` table, `run_id=10d433dd…`).

**Worked example on real data.** The forecast at the close of 2010-04-26 uses the fit dated 2010-04-01, which has 2,534 pairs. Its coefficients are, in order, the constant 6.122e-5, the day 0.01593, the week 0.2741 and the month 0.3920. The regressors on 04-26 are 1, 1.4315e-5, 2.9580e-5 and 3.6869e-5. The four terms are 6.122e-5, 2.28e-7, 8.109e-6 and 1.4452e-5, and they sum to ŷ = 8.401e-5, a daily volatility of 0.917%. The naive RV22 on that day is 3.687e-5, so HAR forecasts 2.28 times the naive value. The constant is the largest term: HAR pulls toward the mean of the fitted years, which include the high-variance 2000-2009 period, and away from the last weeks. Over the development years the run has 120 distinct fit dates, one per month (`signals.model_fit_date`).

On the same day the naive forecast would give RV^ = 0.0993 against HAR's 0.1500, and a signal of 0.851 against 0.0277. This is a comparison of two forecasts on one day. It is not a finding about either: the choice between them was made on the pre-registered forecast test ([concept 24](24-pre-registration-and-block-inference.md)).

## Assumptions

- **A linear fit in levels is good enough.** It is the form of the cited papers. No log form is built, and neither are GARCH or GJR (GARCH and GJR would need `scipy.optimize`, an ADR change, and each adds trials).
- **The 504-pair floor.** Two years of pairs make the signal exist from 2002 on the store's bars, which start 2000-01-03.
- **Monthly is often enough.** ADR-0010 §1 fixes the schedule: monthly, on data up to the refit date.

## Where it breaks

- **Around spikes.** The fit is in levels, so one huge v moves the week and month terms for 5 and 22 sessions, and moves the next refit. The fallback count is reported.
- **The horizon beyond what the papers tested.** ADR-0010 notes that Corsi validated HAR only up to about two weeks ahead. The 21-session direct form needed its own out-of-sample test, which was run once ([concept 24](24-pre-registration-and-block-inference.md)).
- **Regime change.** A fit that spans 2008 sees a world with far more variance than the 2010s, and its constant reflects that.

## In this project

- `src/volbt/signals/har.py:61` `regressors`, `:69` `targets`, `:78` `fit` (it cuts `v` at the fit date before building any pair), `:94` `naive_rv22`, `:100` `har_forecast` (the fallback), `:113` `month_start`, `:120` `HarForecaster` (`:128` `forecast`).
- `src/volbt/signals/vrp.py:68` `update` calls the forecaster each session; `reset` (`:60`) clears its state before a run.
- `tests/test_signals_har.py:87` a fit uses only the pairs whose target ends by the fit date; `:106` lstsq equals the normal equations; `:127` a simulated HAR process is recovered; `:179` a forecast at or below zero falls back; `:188` the forecaster refits on the first session of each month and a mid-month start changes nothing.
- `tests/test_signals_causal.py:117` ADR-0001 test 6: no signal value up to t₀ moves when every input after t₀ changes, at four t₀ (2023-02-28, 03-01, 03-16 and 04-03), with the full-sample fit as the mutant that must fail.
- `notebooks/04_strategies_and_signal.ipynb`, the cells "HAR-RV, fitted only on what had ended".
