# IV30, the log variance ratio, and calendar time against session time

## First principles

An option price says how much variance the market expects until expiry. A forecast says how much a model expects over the same stretch. If the two cover different stretches, their ratio measures the difference in length as well as the difference in belief. This note is about making them cover the same stretch.

Terms:
- **IV30**: the implied volatility of an at-the-money-forward option 30 calendar days from now, read from the day's smile surface ([concept 11](11-smile-in-total-variance.md)). It is an annualised volatility.
- **Total variance**: σ²τ, the variance over the whole life τ. It adds up over time; an annualised σ does not.
- **Calendar time**: days on the calendar, weekends included. Options are priced in it (τ = days/365).
- **Session time**: trading days. Realised variance accrues in it: a weekend adds no return of its own ([concept 19](19-realised-variance-from-daily-bars.md)).
- **n_window**: the number of sessions in (t, t + 30 calendar days].

## The maths

- **IV30** is `smile.surface_iv` at log-moneyness k = 0 and τ = 30/365, so the forward is the expiry's own parity forward. It is the same call as the engine's `DaySurface.atm_iv_30d()` and M2's exported `atm_iv_30d`. It is NaN when the session has no snapshot, no usable smile (fewer than `MIN_NODES` nodes), or when 30 days is not bracketed by two expiries and the read would need tenor extrapolation (flag `SURFACE_EXTRAP_TENOR`, value 4).
- **Implied total variance** over the window: IV30² × 30/365.
- **Forecast total variance** over the window: n_window × ŷ, where ŷ is the forecast mean daily variance ([concept 20](20-har-and-causal-refits.md)).
- **The signal**: s_t = ln(IV30² × 30/365 / (n_window × ŷ)) = ln(IV30² / RV^²), with RV^ = √(n_window × ŷ × 365/30). RV^ is the forecast written as an annualised volatility, so it can sit next to IV30 on a chart.
- **vrp_spread** = IV30 − RV^, kept for display.

s > 0 means the market charges more for the window than the model expects to realise. The short-vol strategies enter when s ≥ θ.

**Why not 252.** ADR-0010 first said to annualise realised vol with 252 sessions. That treats every 30-day window as 21 sessions. A window holds 17 to 22. On a 17-session window the ratio would be biased by ln(21/17) = 0.2113, about half of the 0.4 entry threshold. The window is therefore counted from the exchange calendar, and the bias is gone by construction ([ADR-0011](../adr/0011-vrp-signal-and-strategy-rules.md), [ADR-0010 amendment](../adr/0010-evaluation-protocol.md)).

**Worked example on real data**, 2010-04-26 (the walkthrough's entry): IV30 = 0.152047; n_window = 22; ŷ = 8.401e-5. Implied total variance 0.152047² × 30/365 = 0.0019001. Forecast total variance 22 × 8.401e-5 = 0.0018482. The ratio is 1.0281 and its log is **s = 0.0277**. RV^ = √(0.0018482 × 365/30) = 0.14995. With the window counted as 21 sessions the same inputs would give s = 0.0742, and as 17 sessions 0.2855. So the count moves s by 0.05 (21 sessions) and 0.26 (17 sessions) on this day, against entry thresholds of 0 and 0.4. Notebook 04 shows the same effect on made-up numbers.

**How many sessions a window holds**, in the development run (the `n_window` column of its `signals` table, 2,516 sessions): 17 on 3, 18 on 36, 19 on 334, 20 on 576, 21 on 1,018 and 22 on 549.

**How often IV30 is missing.** On 32 of the 2,516 development sessions s is NaN. All 32 carry `IV30_MISSING`: 5 are `SURFACE_EXTRAP_TENOR` (2010-01-15, 01-19, 04-16, 04-19 and 04-20, early in some months the front expiry is past 30 days) and 27 have no usable smile. Two of the five matter for the walkthrough: on 04-19 and 04-20 the 06-18 expiry was already inside the entry window and s did not exist, so no entry could happen.

## Assumptions

- **The calendar is allowed.** The engine counts future session dates (dates only). Holidays are published in advance (decision D3). An unscheduled closure leaks a day early; the engine counts one as a session until its announcement date (`volbt.engine.closures`).
- **ATM-forward IV30 is the market's 30-day variance.** The smile surface reads IV at one strike. A model-free variance swap rate would use every strike. The project uses the ATM read, the call the engine already has.
- **One vendor.** IV30 here is OptionsDX's (the signal's `source`); the engine's view serves one source per run.

## Where it breaks

- **ATM is one strike.** With a skewed smile the market's variance over the window is not the ATM variance. s measures the ATM read against the forecast, nothing more.
- **IV30 is NaN in some sessions.** s is NaN, a gated entry never fires, and a signal exit does not hold. The other exits still apply.
- **Event days.** A window that holds a known event (a Fed day) has a different n-per-day variance than the model's average.

## In this project

- `src/volbt/signals/iv30.py:35` `usable_smiles`, `:42` `iv30`.
- `src/volbt/signals/vrp.py:43` `rv_hat` (NaN unless the forecast is positive and the window holds a session), `:68` `update` (`2 * math.log(sigma / rv)`), `:50` `VrpSignal`.
- `src/volbt/engine/loop.py:196` `n_window` (from the calendar through `closures.n_window`), `:704` `update_signals`.
- `src/volbt/signals/base.py:26` the flag bits and `:34` `SignalValue`.
- `tests/test_signals_vrp.py`, `tests/test_signals_causal.py:90` (the made-up store has the NaN cases).
- `notebooks/04_strategies_and_signal.ipynb`, the cells "The log variance ratio, and why the window must match".
