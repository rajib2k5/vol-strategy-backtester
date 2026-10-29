# The sampling mask

## First principles

A backtest result depends on the data it ran on, not only on the strategy. Our out-of-sample data (DoltHub, 2024-26) is much thinner than our in-sample data (OptionsDX, 2010-23):

- DoltHub lists about 3 expiries and 17-27 strikes per expiry, re-centred every day;
- until Oct-2024 it has almost only Mondays, Wednesdays and Fridays: before 2024-10-01 its clean SPY dates are 235 Wednesdays, 231 Fridays and 211 Mondays, with 6 Thursdays and 5 Tuesdays;
- an expiry it lists today is often missing tomorrow.

So a holdout result mixes two things: how the strategy did, and what the thin sampling did to the backtest. We cannot separate them on the holdout itself, because there is nothing denser to compare with.

A **sampling mask** separates them on the in-sample period instead. DoltHub's 2020-23 data exists. So we can replay **DoltHub's own sampling** on OptionsDX for the same dates: keep only the OptionsDX contracts that DoltHub listed that day. The full chain and the masked chain then hold the same quotes where they overlap. Any difference between the two backtests is caused by the sampling alone.

## The maths

Write *P(d)* for the set of (expiry, strike) pairs DoltHub lists on date *d*, and *O(d)* for the OptionsDX chain on *d*. Then (ADR-0009 §4):

- `chain_mask = none`: the masked chain is *O(d)*.
- `chain_mask = dolthub`: it is the rows of *O(d)* whose (expiry, strike) is in *P(d)*. A date DoltHub lacks has *P(d)* empty, so the masked chain is empty: the engine marks with `STALE_SURFACE` and option orders wait.
- `chain_mask = dolthub_daily`: as `dolthub`, but on a Tuesday or Thursday that DoltHub lacks, *P(d)* is taken from DoltHub's last listing before *d*, minus any expiry that has passed. This imitates the holdout from Oct-2024, when DoltHub has almost every weekday.

A pair keeps both the call and the put at that strike. Strikes are matched as integer thousandths of a dollar, never as floats.

Measured on the real data (`data/store`, built 2026-10-29 by `uv run python tools/build_data.py`):

- `dolthub` keeps 40,234 pairs over 576 dates; `dolthub_daily` keeps 67,937 pairs over 981 dates.
- Under `dolthub`, 79,792 of the 9,029,124 OptionsDX rows from 2020-01-06 to 2023-12-29 survive: **0.88%** (79,954 of 9,038,866 before round 2 of the M1 review dropped the 2022-06-20 chain the first build had filed under 06-17).

## Assumptions

- **DoltHub's quotes and OptionsDX's quotes are close enough** that the mask changes only which contracts exist, not their prices. The cross-vendor check measures this: on 2020-23, DoltHub's 30-day ATM vendor IV sits a median 0.19 vol points above OptionsDX's.
- **2020-23 sampling looks like 2024-26 sampling.** It does not fully: ADR-0009 measured that an expiry is listed on a median 0.286 of its sessions in 2020-22 and 0.50-0.54 from 2023. So 2023 is the closest analogue, and results are reported separately for 2020-22 and 2023.
- **DoltHub's dates are clean.** The calendar rule runs first, so DoltHub rows dated on closures (103 dates) are already gone.

## Where it breaks

- **Things the mask cannot replay.** The Aug-2024 hole, DoltHub's unknown snapshot time, and price levels that only exist in 2024-26 are not in 2020-23.
- **A different Tue/Thu rule.** M′ carries the last listing forward. If DoltHub's real Tue/Thu listings differ from the day before (they are re-centred daily), M′ is optimistic about how many contracts persist.
- **It estimates, it does not bound.** The masked run measures the distortion under 2020-23 conditions. It is an estimate of the holdout distortion, not a limit on it (ADR-0009, revised after review).

## In this project

- `src/volbt/data/mask.py:44-49`: `listed_pairs`, DoltHub's (date, expiry, strike) set.
- `src/volbt/data/mask.py:52-77`: `build_mask`, for `dolthub` and `dolthub_daily`.
- `src/volbt/data/mask.py:80-90`: `apply_mask`, the semi-join onto OptionsDX.
- `src/volbt/data/pipeline.py:204-208`: the M1 job writes both masks to the `chain_mask` table; M3's engine reads it.
