# Realised variance from daily bars

## First principles

**Realised variance** is how much a price actually moved, squared and averaged. An option's implied variance is a price for that movement. The signal in this project compares the two ([concept 21](21-iv30-log-variance-ratio-and-calendar-time.md)), so it needs a number for the movement that was not seen yet, and a number for the movement that was.

With daily bars there is one cheap estimate of a day's variance: the squared return of that day.

Terms:
- **Return** r: the log change of the price over one session, close to close. **Total return**: the return of someone who also receives the dividend.
- **Ex-date**: the first session on which a buyer no longer gets the dividend. The stock price drops by about the dividend on that day.
- **v_i = r_i²**: the daily squared return, a proxy for the day's variance.
- **Proxy**: a noisy stand-in for a quantity we cannot see. The true variance of one day is never observed.

## The maths

For bar i, with the unadjusted close C_i and the dividend D_i whose ex-date is bar i:

r_i = ln((C_i + D_i) / C_{i−1})

The rest follows from that line.

- **Why add D_i back.** On an ex-date the close falls by about D_i for a reason that is not risk. Without the add-back the drop counts as variance. In a made-up example (notebook 04) a close that falls from 100.50 to 100.00 on a 0.50 dividend gives r = −0.00499 without the add-back and 0.0 with it.
- **Why the unadjusted close.** The view serves no `adj_close`. An adjusted close on day t is scaled by every dividend paid after t, so it carries future information. The unadjusted close and the dividend table are both dated, and the view cuts both at *t* ([concept 18](18-look-ahead-through-reads-and-state.md)).
- **A weekend is one return.** The close on Monday over the close on Friday is one value of r. A holiday is the same. The variance of the next 30 calendar days is therefore a number of *sessions* times a per-session variance, and the number of sessions changes from window to window ([concept 21](21-iv30-log-variance-ratio-and-calendar-time.md)).
- **Windows.** `window_mean(v, n)` at index i is the mean of v over the n values ending at i. The 5-session and 22-session means are the HAR regressors ([concept 20](20-har-and-causal-refits.md)); the 22-session mean of r² is the naive forecast, RV22.

**A proxy is noisy but not biased.** If a day's return is normal with variance h, then r² has mean h and variance 2h², so its standard deviation is √2 = 1.41 times its mean. One day tells little. Averaging many days, or regressing on them, tells more. The loss used for the forecast test, QLIKE, ranks forecasts the same way with this proxy as with the true variance (Patton 2011), which is why the proxy is acceptable there ([concept 24](24-pre-registration-and-block-inference.md)). It is still a proxy, and the result is labelled so.

**Worked example on real data.** The store holds 6,746 SPY bars from 2000-01-03 to 2026-10-28, 2,515 of them before 2010-01-04, and 108 dividends, 41 of them before 2010 (`tools/measure_listing.py`, 2026-11-17). The 2,515 bars before the development split are the warm-up: the first HAR fit needs 504 training pairs, and they exist from 2002. Read through a view as of 2010-04-26 (the session of the [walkthrough](../milestones/04-strategies-and-signal.md)'s traced position), `total_log_returns` gives 2,592 returns, the first one dated 2000-01-04. The last five, in percent, are 0.889, −0.182, 0.298, 0.651 and −0.378. Their squares are the v values that fill the day and week regressors of that session.

## Assumptions

- **Close to close, overnight included.** The estimate has no intraday data. Two days with the same close-to-close return can have had very different paths. This is the main source of the noise.
- **Dividends are a known table.** An ex-date that is not a bar date joins the first bar after it. None exists in the store: every SPY ex-date is a session. A dividend dated before the first bar has no return to join and is dropped.
- **No splits.** The yfinance file has 0 split rows (`tools/measure_listing.py`), so an unadjusted close needs no split correction.
- **Returns are not normal.** The 1.41 above is the normal case. Fat tails make the proxy noisier, and the forecast test's block bootstrap does not assume normality.

## Where it breaks

- **Jumps and gaps.** A −8% gap day puts one huge v into every window that holds it, for 22 sessions. The naive forecast then jumps and falls back 22 sessions later.
- **Noisy at one day.** Nobody should read v_i as the variance of day i.
- **Bar errors.** A wrong close in the SPY file would be a false return. This note does not check the bars.

## In this project

- `src/volbt/signals/realised.py:29` `total_log_returns`, `:49` `window_variance`, `:54` `window_mean` (a direct sum per window with `np.convolve`, so one element does not depend on what comes after it, unlike a cumulative sum).
- `src/volbt/signals/vrp.py:68` `update` calls `total_log_returns(view.spy_bars(), view.dividends())` each session, through the session's view.
- `notebooks/04_strategies_and_signal.ipynb`, the cell "Realised variance from daily bars".
- `tests/test_signals_har.py` (the dividend add-back and the edges).
