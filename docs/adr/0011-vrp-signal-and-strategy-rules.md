# ADR-0011: The VRP signal and the strategy rules

> **Data notice.** The DoltHub figures in this document (counts, dates, quantiles and summaries, in its text and in its tables) are derived from the DoltHub database `post-no-preference/options` (<https://www.dolthub.com/repositories/post-no-preference/options>), licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), and are shared under the same licence. Changes: we aggregated it into counts, shares and quantiles, compared it with OptionsDX and ran our pricing build on it; no quote row is reproduced. The rest of this repository is MIT. See [DATA.md](../../DATA.md).

**Status:** Accepted at milestone 4 (default taken 2026-11-17, owner can override). Implemented in M4: the signal, the four structures, the entry and exit rules and the development grid. Fixed packages are replaced by vega sizing in M5. The strategy pre-registration freezes at the end of M5; M6 scores it.

## Context

ADR-0001 to ADR-0010 fix the engine, the fill model, the marks, the hedge and the evaluation protocol. They leave open what M4 builds on top: which number says "implied variance is rich", how it is forecast and compared, which contracts a strategy trades, and when it leaves. This ADR records those choices and why the alternatives lost. Its sections are the plan's sections 3 to 5, as built.

Three facts shape every choice here.
- **The signal must be causal.** A forecast fitted on the whole sample knows the future. ADR-0001 test 6 changes every input after *t₀* and requires every signal value up to *t₀* to stay bit-identical.
- **A window of 30 calendar days holds 17 to 22 sessions.** A fixed "21" or "252" would bias the ratio of implied to realised variance by up to ln(21/17) = 0.21.
- **The development split is the only split a strategy may look at** (ADR-0010 §1). Every configuration run on it is a trial, and the DSR must count it.

## Decision

### 1. Returns and realised variance

- The return is the **total log return from the unadjusted close**: r_i = ln((C_i + D_i) / C_{i−1}), with D_i the dividend whose ex-date is bar i. A weekend is one return. The view serves no adjusted close, because an adjusted close on day t is scaled by every dividend paid after t.
- v_i = r_i² is the daily proxy for variance. It is noisy and not biased. Concept note 19 gives the maths.
- A dividend whose ex-date is not a bar joins the first bar after it. One dated before the first bar is dropped. No such case exists in the store.

### 2. The forecast: HAR-RV, direct 21 sessions, refitted monthly

- **Model.** y_i = mean v_{i+1..i+21} regressed on x_i = [1, v_i, mean v_{i−4..i}, mean v_{i−21..i}], by `numpy.linalg.lstsq`. The regressors are Corsi's (2009); the direct multi-horizon target is the form of Andersen, Bollerslev and Diebold (2007).
- **Causal refit.** A fit is made on the first session of each calendar month, from the pairs whose target ends on or before that date, at least 504 of them. A run that starts mid-month fits as of that month's first session. A value depends on its date, never on the run's start.
- **Fallback.** A forecast of 0 or less falls back to the naive RV22, the mean of the last 22 values of v, and carries `RV_FALLBACK`.
- **The model of the grid is decided, not typed in.** The forecast test (ADR-0010 amendment of M4) chose HAR over the naive RV22 by its pre-registered rule. `tools/run_m4_grid.py` reads the decision from the committed result.
- **Not built:** GARCH and GJR (ADR-0001 lists them). They need `scipy.optimize`, an ADR change, and each would add trials.

### 3. IV30

IV30 is the ATM-forward implied vol at 30 calendar days, `smile.surface_iv` at k = 0 and τ = 30/365 over the day's usable smiles. It is the same call as `DaySurface.atm_iv_30d()`. It is NaN when the session has no snapshot, no usable smile, or when 30 days is not bracketed by two expiries (`SURFACE_EXTRAP_TENOR`). Smiles are read through the view, so the read is dated by *t*.

### 4. The signal, and the window-matched horizon

- With n = the number of sessions in (t, t + 30 calendar days], read from the session calendar (decision D3, with unscheduled closures counted as sessions until their announcement), compare the implied total variance IV30² × 30/365 with the forecast total variance n × ŷ.
- **s_t = ln(IV30² / RV^²)**, with RV^ = √(n ŷ × 365/30). `vrp_spread` = IV30 − RV^.
- **This replaces the note in ADR-0010** ("annualised with 252 sessions"). With 252, a window of 17 sessions biases s by ln(21/17) = 0.2113, about half of the 0.4 entry band.
- s is NaN when either side is. The flags say why: `RV_FALLBACK`, `RV_MISSING`, `IV30_MISSING`, `WINDOW_EMPTY`.
- The VIX bucket and the vol regime of ADR-0010 §3 are written beside s, **lagged one session**.

### 5. The position P&L is hedged, and the engine computes it

- Per position and session: pnl_t = fills_t + open_t + settled_t + H_t, with H_t = Σ −Δ_{u−1}(S_u + D_u − S_{u−1}) (`engine/positions.py`; concept note 23). It is written to `position_daily`.
- It leaves out interest, the borrow fee and the hedge's costs, which are the book's.
- It exists only under a daily hedge at the close with fills at the next close (or no hedge). Elsewhere it is null, and a rule with a stop or a target refuses it.
- The stop and the target read it. M6's attribution may read it too.

### 6. The four structures and their picks

| Structure | Legs | Entry window |
|---|---|---|
| `short_straddle`, `long_straddle` | ATM: the listed strike nearest the expiry's parity forward, a tie to the lower strike | the standard monthly at 50-60 DTE |
| `short_strangle` | call and put nearest a spot delta of ±0.25 (ADR-0005's delta at the engine's own inputs) | the same |
| `straddle_calendar` | short front ATM straddle, long back straddle at the same strike | front monthly at 22-35 DTE; back = the next calendar month's monthly, at most 180 days out |

- The expiry is the standard monthly found from the listed expiries and the session calendar (ADR-0002 §5), never beyond 180 days, never a weekend or weekly stand-in.
- **One position per expiry, at most two open at once.**
- **Why 50-60 DTE.** DoltHub lists a standard monthly at 50-60 DTE on every measured session (162 of 162 session-expiry pairs in 2020-22, 54 of 54 in 2023), so validation and the holdout trade the same contracts at the same DTE. At 36-49 DTE the monthly is listed on 32.2% and 30.3%, at 29-35 DTE on 1.0% and 33.3% (`tools/measure_listing.py`, 2026-11-17). The calendar cannot do the same, so its holdout trades are sparse.

### 7. Entries and exits

- **Entries.** `always`; short-vol structures when s ≥ θ with θ in {0, 0.4}; the long straddle when s ≤ 0. A gated entry needs a finite s.
- **Exits**, the first that holds in this order, for each open position at each session's decision: **stop** (pnl ≤ −1.0 × |premium|), **profit target** (pnl ≥ +0.5 × |premium|), **signal** (short vol: s ≤ θ − 0.4; long vol: s ≥ +0.4; a NaN s holds nothing), **DTE** (the days from the next session to the settlement date of the earliest open lot are at most `exit_dte`). One close order per position (decision D22), filled at the next session.
- **`exit_dte = 14`**, in every split (ADR-0003 amendment of M4).
- **Fixed, not tuned:** `FixedPackages(10)` (inside ADR-0002's 7 to 12 straddles) until M5; a daily hedge at the close, k = 1, hard cap only, fills at the next close.

### 8. The development grid and the trial count

- Each short-vol structure has 10 configurations: `always` with {dte, dte + pt/sl}, and each of the two θ with {dte, dte + signal, dte + pt/sl, dte + both}. The long straddle has 6. **36 configurations, 36 trials**, trial group `m4_vol`, run once each on the development split.
- N_raw = the trials + the design-choice log, which grows from 6 to 10 with the entries in the appendix: **46 after M4.** ADR-0010's amendment of M4 gives the counting rule and the trial log.
- M4 reports development diagnostics only, labelled "in-sample, 36 trials of N_raw 46, selection-biased, no claim". No P&L, NAV, return or Sharpe of any M4 run is committed or printed before M6, for any date (decision D19, extended).

## Alternatives considered

- **An adjusted close for returns.** Rejected: the view serves none, and a close adjusted on day t depends on dividends paid after t.
- **Realised variance from intraday bars.** Not available: the store has daily SPY bars only.
- **HAR in logs, GARCH or GJR.** Rejected for M4: a log form is another design choice to count, and GARCH and GJR need `scipy.optimize`. HAR in levels is fragile around spikes, so the fallback count is reported (0 on the development run of record).
- **A fixed 252-session annualisation.** Rejected (section 4).
- **An option-only position P&L.** Rejected: the hedge is book-level, so an option-only P&L stops out a hedged short straddle on a move its hedge already paid for.
- **Strategies pricing their own marks.** Rejected: a second implementation of ADR-0004.
- **Allocating the book's hedge shares to positions pro rata by delta.** Rejected: two positions with nearly cancelling deltas make shares per unit of delta unbounded.
- **Entry at the monthly nearest 45 DTE, one position at a time.** Rejected (the owner's alternative, plan section 12): it trades unlisted contracts out of sample (32.2% and 30.3% listed at 36-49 DTE).
- **`exit_dte` 21 or 7.** Rejected. At 15-21 DTE a monthly is never listed on DoltHub and always bracketed by two other expiries (98 of 98 and 31 of 31 pairs; ADR-0004's median error at 21 DTE is 0.24 vol points). At 7 DTE it is always below the front expiry and needs tenor extrapolation (34 of 34 and 12 of 12; median error 1.21). At exactly 14 DTE the monthly's own expiry is listed on 31 of 31 and 11 of 11 sessions (median error 0.04).
- **Freezing the strategy pre-registration at M4.** Rejected: M5's risk rules change the configurations, so a freeze now would test configurations that never trade.
- **Freezing it inside M6.** Rejected: attribution work would then sit between selection and freeze.
- **A signal read from a view at `sample_end`.** Rejected: that is a look-ahead the engine cannot detect (ADR-0001 test 6 is the control).

## Consequences and biases

- **36 trials and a 46 N_raw** enter the DSR at M6. The development grid's results are selection-biased by construction, and this ADR makes none public.
- **The HAR forecast is not forecast-tested on strategy P&L.** The forecast test used QLIKE, a proxy loss, on development data. It is roughly 5%-level evidence (concept note 24).
- **The calendar's holdout is sparse.** A 22-35 DTE monthly is rarely listed on DoltHub.
- **Two positions open double the exposure** until M5's sizing and budgets.
- **`n_window` leaks an unscheduled closure a day early** (decision D3; the engine counts a closure as a session until its announcement).
- **IV30 is missing on 32 of the 2,516 development sessions** (5 need tenor extrapolation, 27 have no usable smile); s is NaN there, and no gated entry fires.
- **The holdout is semi-blind** (ADR-0010): the background document already describes 2024-25.
- **HAR in levels can forecast a non-positive variance after a spike.** The naive fallback handles it and is counted.

## How we will test it

1. **Causal signals** (ADR-0001 test 6): `tests/test_signals_causal.py` at four t₀ (2023-02-28, 03-01, 03-16, 04-03) on a made-up store with bars from 2017-01-03. The full-sample HAR and a signal computed from a `sample_end` view must fail it.
2. **Causal strategies:** `tests/test_strategy_causal.py` runs the same perturbation on each structure's decisions.
3. **HAR:** `tests/test_signals_har.py`: a fit uses only the pairs whose target ended by the fit date, `lstsq` equals the normal equations, a simulated HAR process is recovered, the fallback, and a mid-month start changes nothing.
4. **IV30 and the signal:** `tests/test_signals_vrp.py`: IV30 equals the engine surface's 30-day read and M2's exported `atm_iv_30d` where defined, NaN cases, the signal is the log ratio over the window, and an empty window is flagged.
5. **Picks and rules:** `tests/test_strategy_picks.py`, `tests/test_strategy_expiry.py`, `tests/test_strategy_rules.py`: ATM and 0.25-delta picks, the monthly when unlisted, the Good Friday months (Thursday monthly), the precedence, and at most two open positions.
6. **The position P&L identity:** `tests/test_engine_positions.py`: one position's P&L equals the change in NAV_mid less interest, borrow and hedge costs, within the rounding residual times the move, across an ex-date, an early assignment and a partial close.
7. **The grid:** `tests/test_m4_grid.py`: 36 distinct configurations. `tests/test_run_m4_grid.py` and `tests/test_real_m4.py`: the trial log is complete and its count is 36.
8. **180 days:** `check_intent` refuses an opening leg more than 180 days out and fills one at 180 (`tests/test_engine_round2.py:80`); `nearest_monthly` and `monthly_in_window` never return one (`tests/test_strategy_expiry.py:119`, `tests/test_strategy_picks.py:56`).

## Appendix: design-choice log, entries 7 to 10 (counted in N_raw)

These choices were made in M4 with the data in view that the table names. Each adds one to N_raw (ADR-0010 appendix, entries 1 to 6).

| # | Choice | Data in view when it was made | ADR |
|---|---|---|---|
| 7 | `exit_dte = 14` | DoltHub listings 2020-23 and ADR-0004's masked errors (OptionsDX 2022-23 masked by DoltHub) | 0003, 0011 |
| 8 | The entry windows: 50-60 DTE, and 22-35 for the calendar's front | DoltHub listing coverage 2020-23; OptionsDX development snapshots | 0011 |
| 9 | The RV model: HAR against the naive RV22 | The pre-registered forecast test on development sessions 2010-2019 (block and q from 2002-2009) | 0010, 0011 |
| 10 | θ in {0, 0.4} and the 0.4 signal band | A summary of VIX and realised variance, 1990-2026, which includes the holdout years | 0011 |
