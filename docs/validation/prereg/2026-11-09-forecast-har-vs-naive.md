# Forecast test: HAR-RV against the naive RV22 (2026-11-09-forecast-har-vs-naive)

Pre-registered 2026-11-09 (milestone 4, plan section 6). Status: **written, not committed, not scored.** The plan
requires these three files to be committed before any scoring; no commit can be made until the history rewrite of the
repositories ends, so scoring waits for it.

## Revisions before commit
- First, after the milestone 4 part A review: the block sign flip (block 168) was replaced by an EWC bootstrap-t,
  chosen by the rule of the first revision: the smallest worst-case size among the candidates with power of at least
  0.9 at falsifier (c) (the battery's Gaussian AR(1), a long-run t of 4).
- Second, after the second review: review A named p < 0.025 first (below), and the rule, coded after it, picks it on
  the simulated null-sides nearest the 2002-2009 d-series. Every figure below became the saved output of
  `tools/forecast_size.py` that the .json carries ("size", "screen", "matched"). The power requirement moved from the
  falsifier (c) power to the ABC-weighted power on the matched null-sides, shifted by 4 SD of the run mean. At p <
  0.025 the falsifier (c) power is 0.8265, below the first revision's 0.9; the ABC-weighted power is 0.9446.
- How p < 0.025 was reached: review A, the second review, named p < 0.025 before the rule was coded. Its ABC-weighted
  sizes at p < 0.025 were 0.0529 (seed 6001, 1,000 runs per matched null-side of its own match) and 0.0512 (seed 7001,
  1,000 runs per matched null-side of its own match). The second fix pass's item list opened with "Decision threshold
  p < 0.025". The rule's size cap, 0.055, was set with those sizes in view. With the cap at 0.05, the rule picks p <
  0.02 (the table under "How fragile the threshold is").
- Third, after the third review: the threshold's history above, the variant table, the conditional check and the
  spread of size across the matched null-sides were added. The threshold was not chosen again.
- Fourth, after the fourth review: the threshold's fragility is stated from every combination of the variant table's
  choices and from two power-requirement rows; a larger conditional draw, declared before it ran, is the main
  conditional figure, and the two earlier draws are kept; wording that implied the threshold was chosen blind was
  removed. The threshold and the decision rule were not chosen again.
- Fifth, after the fifth review: the combinations are counted by combination and by distinct rule; the menu of
  thresholds, and why the combinations that pick none pick none, are stated; the three conditional draws are compared
  two at a time; six simulations were run again with the final `tools/forecast_size.py` and gave the same values: the
  battery, the match, the variants, the combinations, the main conditional draw and the third fix pass's draw. Review
  D's draw was not run again: its seed was not recorded. The text states what the scorer's hash covers. The threshold
  and the decision rule were not chosen again. (Corrected after the sixth review: this item said that every simulation
  was run again.)
- Sixth, after the sixth review: the scorer's checks of tools/ were widened, and the text states when they run and
  what they do not stop (under "The data looked at"); the fifth item now names the six simulations that were run
  again. No simulation was run, and the threshold and the decision rule were not chosen again.
- Seventh, after the seventh review: run as a script, the scorer refuses an entry of tools/ that takes the name of one
  of its modules, or that shares a module name with another entry, before it imports tools/prereg.py. Its checks of
  tools/ left out entries whose module name was not an identifier (the eighth revision replaced this rule). The text
  under "The data looked at" now says the checks catch mistakes and the routes they name, not code written to defeat
  them, and names a module that removes itself. The scoring steps say to commit tools/ in full. No simulation was run,
  and the threshold and the decision rule were not chosen again.
- Eighth, after the eighth review: the checks of tools/ now read an entry whose module name has a hyphen, and leave
  out an entry whose module name holds a dot. A file's module name is its name less the longest import suffix. The
  scorer's name check now runs before sysconfig imports its data module. The text under "The data looked at" and the
  scoring steps state which entries the checks read, and that tools/__pycache__ is left out. No simulation was run,
  and the threshold and the decision rule were not chosen again.
- Ninth, after the ninth review: the text said that a folder in tools/ must be committed as it is, but the commit
  check reads less. The scoring steps and the text under "The data looked at" now say what it reads. For a folder,
  HEAD must hold it as a folder, and every file with an import suffix directly in it must be committed as it is. The
  commit check does not read files deeper down, or files without an import suffix. The scorer now also refuses
  _PYTHON_SYSCONFIGDATA_NAME, which names the module sysconfig imports, and the text lists the variables it refuses.
  No simulation was run, and the threshold and the decision rule were not chosen again.

## Why this test
ADR-0010 asks for an out-of-sample test of the 21-day HAR before the signal uses it. The signal's RV model (design
choice 9 of the log) is the one thing this test decides: HAR if the test rejects, else naive.

## What is fixed here
- One candidate (k = 1), one benchmark, one window: 2010-01-04 to 2019-11-29, n = 2,495, every target ending by
  2019-12-31. The window is development data; it has been looked at for other reasons (M3's engine runs), never for
  this loss.
- QLIKE, labelled proxy: realised variance from daily closes is a noisy stand-in for the true variance. QLIKE ranks
  forecasts the same under such a proxy (Patton 2011), which is why it, not MSE, is the metric. It is asymmetric: it
  punishes an under-forecast more than an over-forecast of the same size.
- d_t = QLIKE(naive)_t - QLIKE(HAR)_t, one-sided: H0 mean(d) <= 0 against mean(d) > 0.
- The test: `volbt.analytics.inference.ewc_bootstrap(d, q=4, block=21, draws=9999, seed=20261109)`. The EWC t
  estimates the long-run variance of d from its 4 lowest cosine frequencies; its p-value is a moving-block bootstrap-t
  (blocks of 21 sessions, the targets' overlap), which carries the skew of d into the reference law. The CI of mean(d)
  comes from the same draws. **Decision: HAR if p < 0.025, else naive.** d identically 0 gives p = 1. The scorer's
  result carries the threshold and the effective size below next to the p-value. It also carries the fragile band of
  "How fragile the threshold is" and a flag that says whether p lies in it.

## How the threshold was checked
- The battery (`tools/forecast_size.py battery`, 2,000 runs per null-side, 999 bootstrap draws per run where the
  scorer takes 9,999, seeds in the .json): 30 mean-0 nulls on +d and on -d, 60 null-sides (the review's
  stochastic-volatility nulls S1-S3 and long-memory family S4, the orchestrator's skewed AR(1) at the 2002-2009 lag-1
  ACF of 0.8865 and its long-memory variant). At nominal 0.05 the rejection rate lies in [0.025, 0.075] on 41/60
  null-sides: worst 0.253 (orch long s=1.5, -d), lowest 0.0315 (S1, +d). At p < 0.025: 44/60 in that band, worst 0.189
  (orch long s=1.5, -d), lowest 0.011 (orch long s=1.5, +d). Outside the band at 0.05 (+d / -d): S1 0.0315 / 0.085; S2
  0.0375 / 0.0895; S3 0.043 / 0.085; S4 f=0.1 gauss rhos=.99/.997/.999 0.1075 / 0.1075; S4 f=0.1 right
  rhos=.99/.997/.999 0.1255 / 0.089; S4 f=0.1 left rhos=.99/.997/.999 0.1025 / 0.1205; S4 f=0.15 gauss
  rhos=.99/.997/.999 0.1055 / 0.112; S4 f=0.15 right rhos=.99/.997/.999 0.132 / 0.1025; S4 f=0.15 left
  rhos=.99/.997/.999 0.102 / 0.1235; orch long s=0.0 0.121 / 0.109; orch long s=1.0 0.0545 / 0.1915; orch long s=1.5
  0.0355 / 0.253.
- The 2002-2009 d-series (n = 1,934) has the centred summaries: ACF at lags 1, 5, 21, 63, 126 and 252 of 0.88655,
  0.628334, 0.0426707, 0.086634, 0.0507162, -0.0186719; moving-block SE ratios r21, r42, r84 of 1.13437, 1.10185,
  1.16037; sample skewness 2.3172; excess kurtosis 20.5334; spec4_20 3.84935. Of 1,000 simulated paths per null-side
  (n = 1,934), at most 0.018 of one null-side's (orch ar1 s=1.5 +d) meet a joint rule on 5 of the 12 summaries: "r42
  >= real, r84 >= real, skew >= real, kurt >= real and acf21 <= 0.1".
- The matched null-sides: each path's twelve summaries are scaled by their pooled robust SD (IQR / 1.349; the kurtosis
  as log(kurt + 3)); the nearest 1% of the 60,000 paths by Euclidean distance to the real d's (600 paths) are
  accepted, and a null-side's weight is its share of them (ABC model choice, uniform prior over the 60 null-sides). 16
  null-sides carry weight: S4 f=0.1 right rhos=.99/.997/.999 +d 0.1367, S4 f=0.15 right rhos=.99/.997/.999 +d 0.1150,
  S4 f=0.15 left rhos=.99/.997/.999 -d 0.1133, S4 f=0.1 left rhos=.99/.997/.999 -d 0.1100, S4 f=0.1 left
  rhos=.98/.99/.995 -d 0.1067, S4 f=0.1 left rhos=.97/.985/.993 -d 0.0733, S4 f=0.0 left rhos=.99/.997/.999 -d 0.0617,
  orch long s=1.0 +d 0.0583, S4 f=0.2 left rhos=.97/.985/.993 -d 0.0533, S4 f=0.0 right rhos=.99/.997/.999 +d 0.0517,
  orch long s=1.5 +d 0.0433, S4 f=0.2 left rhos=.98/.99/.995 -d 0.0383, S4 f=0.3 left rhos=.98/.99/.995 -d 0.0167, S4
  f=0.3 left rhos=.97/.985/.993 -d 0.0150, S3 +d 0.0033, orch ar1 s=1.0 +d 0.0033.
- The rule (default taken 2026-11-09, owner can override): the largest threshold of [0.05, 0.04, 0.03, 0.025, 0.02]
  whose ABC-weighted size is at most 0.055 on both seeds and whose ABC-weighted power at 4 SD(run mean) is at least
  0.9. The sizes on the battery's seeds are the battery's own runs. Each matched null-side was run again on a second
  seed (2,000 runs) and, shifted by 4 SD of its run mean, on the power seed (2,000 runs). The rule picks p < 0.025,
  the threshold named before it was coded. Per threshold (the size rule is the cap 0.055 on both seeds and an
  ABC-weighted power of at least 0.9):

| p < | ABC size, battery / second seed | Worst matched, battery / second seed | ABC power | Falsifier (c) power | Size rule |
|---|---|---|---|---|---|
| 0.05 | 0.0900 / 0.0869 | 0.132 / 0.134 | 0.9835 | 0.942 | fails |
| 0.04 | 0.0756 / 0.0731 | 0.113 / 0.1125 | 0.9751 | 0.9175 | fails |
| 0.03 | 0.0604 / 0.0579 | 0.0945 / 0.0925 | 0.9591 | 0.864 (below the first revision's 0.9) | fails |
| 0.025 | 0.0508 / 0.0502 | 0.0815 / 0.083 | 0.9446 | 0.8265 (below the first revision's 0.9) | passes |
| 0.02 | 0.0424 / 0.0419 | 0.069 / 0.0695 | 0.9235 | 0.764 (below the first revision's 0.9) | passes |

- Worst sizes, labelled. On the whole battery: 0.253 at 0.05 and 0.189 at 0.025 (orch long s=1.5 -d, path-median
  sample skewness -4.99, the sign opposite to the real d's). On a null-side whose skewness has the real d's sign (+):
  0.132 at 0.05 and 0.0815 at 0.025 (S4 f=0.15 right rhos=.99/.997/.999 +d, median skewness +1.00). Sample skewness at
  n = 1,934 (path medians): the orchestrator's AR(1) nulls 3.97 (s = 1.0) and 7.73 (s = 1.5), its long-memory nulls
  2.84 (s = 1.0) and 4.99 (s = 1.5); the real d 2.3172.
- So a rejection at p < 0.025 is evidence at an ABC-weighted size of 0.0508 (battery seed) or 0.0502 (second seed) on
  the null-sides nearest the real d, whose own sizes run from 0.011 to 0.0815 (battery seed) and from 0.013 to 0.083
  (second seed); and at 0.189 (orch long s=1.5, -d) if d is as persistent and as skewed as the battery's worst
  null-side.
- Power on the battery's Gaussian AR(1) at rho 0.8865 shifted to a long-run t of delta (delta 0 is its size, delta 4
  falsifier (c)): at 0.05 0.048 at delta 0.0, 0.645 at delta 2.5, 0.7735 at delta 3.0, 0.942 at delta 4.0; at 0.025
  0.021 at delta 0.0, 0.471 at delta 2.5, 0.5895 at delta 3.0, 0.8265 at delta 4.0.

## How fragile the threshold is
- The same rule with one modelling choice changed at a time (`tools/forecast_size.py variants`; the row without
  spec4_20 and the kurtosis changes two summaries at once): the battery's runs, and 2,000 runs per null-side on the
  second seed (20261110) and on a third seed (41001) for all 60 null-sides, so a variant's matched null-sides need no
  new run; the ABC-weighted power on the power seed (20261113). Each size is ABC-weighted on the variant's matched
  null-sides, on the battery seed / the second seed unless the variant names other seeds. The last 2 rows change the
  power requirement, on the registered weights (`tools/forecast_size.py combinations`):

| Variant | Matched null-sides | Picks p < | Size at p < 0.03 | Size at p < 0.025 | Size at p < 0.02 | ABC power at p < 0.025 |
|---|---|---|---|---|---|---|
| the registered rule: cap 0.055, nearest 1%, twelve summaries, IQR scaling, log kurtosis | 16 | 0.025 | 0.0604 / 0.0579 | 0.0508 / 0.0502 | 0.0424 / 0.0419 | 0.9446 |
| the cap at the level, 0.05 | 16 | 0.02 | 0.0604 / 0.0579 | 0.0508 / 0.0502 | 0.0424 / 0.0419 | 0.9446 |
| the cap at 0.06 | 16 | 0.025 | 0.0604 / 0.0579 | 0.0508 / 0.0502 | 0.0424 / 0.0419 | 0.9446 |
| the nearest 0.50% accepted | 16 | 0.025 | 0.0596 / 0.0567 | 0.0501 / 0.0491 | 0.0419 / 0.0410 | 0.9443 |
| the nearest 0.25% accepted | 13 | 0.025 | 0.0614 / 0.0585 | 0.0518 / 0.0507 | 0.0432 / 0.0423 | 0.9504 |
| the nearest 2.00% accepted | 20 | 0.025 | 0.0595 / 0.0571 | 0.0499 / 0.0493 | 0.0417 / 0.0412 | 0.9403 |
| the nearest 5.00% accepted | 37 | 0.025 | 0.0573 / 0.0551 | 0.0480 / 0.0474 | 0.0400 / 0.0395 | 0.9347 |
| eleven summaries, without spec4_20 | 16 | 0.025 | 0.0581 / 0.0555 | 0.0488 / 0.0478 | 0.0406 / 0.0398 | 0.9408 |
| eleven summaries, without the kurtosis | 32 | 0.025 | 0.0618 / 0.0593 | 0.0521 / 0.0514 | 0.0436 / 0.0431 | 0.9359 |
| ten summaries, without spec4_20 and the kurtosis | 15 | 0.025 | 0.0602 / 0.0576 | 0.0506 / 0.0498 | 0.0421 / 0.0417 | 0.9375 |
| each summary over its pooled SD | 25 | 0.025 | 0.0594 / 0.0569 | 0.0498 / 0.0493 | 0.0416 / 0.0412 | 0.9402 |
| each summary over 1.4826 x its pooled median absolute deviation | 16 | 0.03 | 0.0518 / 0.0493 | 0.0430 / 0.0423 | 0.0358 / 0.0348 | 0.9517 |
| the excess kurtosis as it is, not log(kurt + 3) | 17 | 0.03 | 0.0508 / 0.0484 | 0.0421 / 0.0415 | 0.0351 / 0.0340 | 0.9535 |
| a prior uniform over the families sv, s4 and orch, not the 60 null-sides | 16 | 0.03 | 0.0530 / 0.0503 | 0.0443 / 0.0431 | 0.0370 / 0.0355 | 0.9556 |
| the size at seed 41001 in place of the second seed's | 16 | 0.025 | 0.0604 / 0.0567 | 0.0508 / 0.0483 | 0.0424 / 0.0403 | 0.9446 |
| the battery's, the second and the third (41001) seed | 16 | 0.025 | 0.0604 / 0.0579 / 0.0567 | 0.0508 / 0.0502 / 0.0483 | 0.0424 / 0.0419 / 0.0403 | 0.9446 |
| the registered rule with the ABC-weighted power floor at 0.95, not 0.9 | 16 | none | 0.0604 / 0.0579 | 0.0508 / 0.0502 | 0.0424 / 0.0419 | 0.9446 |
| the first revision's power requirement: falsifier (c) power of at least 0.9, in place of the ABC-weighted power | 16 | none | 0.0604 / 0.0579 | 0.0508 / 0.0502 | 0.0424 / 0.0419 | 0.9446 |

- The power-requirement rows. The registered rule with the ABC-weighted power floor at 0.95, not 0.9: the ABC-weighted
  power is 0.9835, 0.9751, 0.9591, 0.9446, 0.9235 at p < 0.05, 0.04, 0.03, 0.025, 0.02; it reaches 0.95 at p < 0.05,
  0.04 and 0.03, and the size is at most the cap 0.055 at p < 0.025 and 0.02: no threshold meets both, so it picks
  none. The first revision's power requirement: falsifier (c) power of at least 0.9, in place of the ABC-weighted
  power: the falsifier (c) power is 0.942, 0.9175, 0.864, 0.8265, 0.764 at p < 0.05, 0.04, 0.03, 0.025, 0.02; it
  reaches 0.9 at p < 0.05 and 0.04, and the size is at most the cap 0.055 at p < 0.025 and 0.02: no threshold meets
  both, so it picks none.
- The 20 other seeds of the twelve summaries (31001 to 31020, in place of the match's default_rng([20261111, cell])):
  the rule picks p < 0.025 on 20 of 20. The size at p < 0.025 runs from 0.0486 to 0.0517 (battery seed) and from
  0.0481 to 0.0513 (second seed); the size at p < 0.03 is never below 0.0559.
- Monte Carlo error: the binomial SE of the registered ABC-weighted size at p < 0.025 is 0.0016 (battery seed) and
  0.0016 (second seed). The cap 0.055 is 2.7 and 3.1 SE above the sizes 0.0508 and 0.0502.
- Every combination of the table's choices (`tools/forecast_size.py combinations`: the saved per-null-side tables and
  the match's summaries drawn again; no new test run): the share accepted (0.25%, 0.50%, 1.00%, 2.00%, 5.00%); the cap
  (0.05, 0.055, 0.06); the summaries dropped (none, spec4_20, kurt, spec4_20 and kurt); the kurtosis logged (yes, no);
  the prior (sides, family); the scaling (iqr, sd, mad); the size seeds (second, third, all3). One choice at a time
  gives the table's 15 rows above the power rows; two at a time, 93 combinations; all of them, 2,160 combinations.
- **Stated before scoring:** one modelling choice at a time (the 15 variant rows and the 20 other summary seeds) picks
  p < 0.02 to p < 0.03, and each picks a threshold. Two at a time pick p < 0.02 to p < 0.04 (p < 0.02 on 7, p < 0.025
  on 53, p < 0.03 on 30, p < 0.04 on 3), and each picks a threshold. Every combination of the table's choices picks p
  < 0.02 to p < 0.05 (p < 0.02 on 161, p < 0.025 on 886, p < 0.03 on 813, p < 0.04 on 216, p < 0.05 on 75), and 9 pick
  no threshold. Both power-requirement rows pick no threshold. With the kurtosis dropped, logging it is no choice, so
  the 2,160 combinations are 1,620 distinct rules (540 combinations repeat a rule). Counted by distinct rule: p < 0.02
  on 95, p < 0.025 on 595, p < 0.03 on 633, p < 0.04 on 216, p < 0.05 on 75, and 6 pick no threshold. The most common
  pick is p < 0.025 by combination and p < 0.03 by distinct rule. Of the 93 combinations two at a time, 91 are rules
  of their own (not a one-at-a-time rule and not counted before): p < 0.02 on 7, p < 0.025 on 51, p < 0.03 on 30, p <
  0.04 on 3, and each picks a threshold.
- The picks come from the table's menu: p < 0.05, 0.04, 0.03, 0.025 and 0.02. 75 combinations (75 distinct rules) pick
  its top, p < 0.05, so the saved tables cannot say what a threshold above 0.05 would do.
- The 9 combinations that pick none, and both power-requirement rows, fail at p < 0.02 on power, not on size. The 9
  combinations: ABC-weighted power 0.8989 on 3 and 0.8940 on 6 against the floor 0.9; size at most 0.0429 against the
  cap 0.05. The power rows at p < 0.02: "ABC power floor 0.95": ABC-weighted power 0.9235 against 0.95, size at most
  0.0424 against the cap 0.055; "falsifier (c) power floor 0.9": falsifier (c) power 0.764 against 0.9, size at most
  0.0424 against the cap 0.055. So a p below 0.02 is a rejection at a size within the cap under every combination and
  both power rows.
- A p in [0.02, 0.05) is decided by these modelling choices, not by the data. A p below 0.02 rejects under every
  combination that picks a threshold; a p of 0.05 or more rejects under none, which is true of this menu only. The
  decision stays HAR if p < 0.025: the registered threshold is not chosen again. The scorer's result carries this band
  as "fragile_band" ([0.02, 0.05]) and "fragile": true when 0.02 <= p < 0.05.

## What the matched null-sides show
- Nearest in the twelve summaries is not alike in what drives size. The 12 S4 null-sides carry 0.8917 of the weight.
  Their path medians: sample skewness 0.67 to 1.18 (the real d 2.3172), excess kurtosis 0.87 to 2.13 (the real d
  20.5334), spec4_20 0.89 to 2.04 (the real d 3.84935). At most 0.003 of one S4 null-side's paths meet the joint rule.
  Only the sign of the skewness matches at the median; the paths accepted from these null-sides are the few whose
  summaries lie near the real d's.
- The other matched null-sides (weight; path-median sample skewness, excess kurtosis and spec4_20; size at p < 0.025,
  battery seed / second seed): orch long s=1.0 +d (0.0583; 2.84, 12.16, 3.06; 0.0295 / 0.02); orch long s=1.5 +d
  (0.0433; 4.99, 35.90, 2.66; 0.011 / 0.0165); S3 +d (0.0033; 4.90, 34.73, 0.87; 0.018 / 0.013); orch ar1 s=1.0 +d
  (0.0033; 3.97, 24.89, 0.88; 0.0225 / 0.024).
- Across the 16 matched null-sides the size at p < 0.025 runs from 0.011 (orch long s=1.5 +d) to 0.0815 (S4 f=0.15
  right rhos=.99/.997/.999 +d) on the battery seed, and from 0.013 (S3 +d) to 0.083 (S4 f=0.1 left rhos=.99/.997/.999
  -d) on the second seed. The ABC-weighted size is a weighted mean of these, so it depends on how the battery was
  composed. A prior uniform over the three families (S1-S3, S4 and the orchestrator's nulls) in place of the 60
  null-sides gives 0.0443 / 0.0431 at p < 0.025 and picks p < 0.03.
- The conditional check (`tools/forecast_size.py conditional`): each path has a 1,934-session calibration segment, a
  21-session gap and a 2,495-session test segment. The paths whose calibration summaries are nearest the real d's (the
  match's scaling and distance over all of a draw's paths) are accepted, and the test (999 draws) runs on their test
  segment. The main draw, declared before it ran: 10,000 paths per null (600,000 in all), seed 20261115. At p < 0.025,
  per share accepted, the accepted paths' size (its binomial SE) against the same null-sides' weighted average over
  all their paths: 0.25% (1,500 paths, 17 null-sides) 0.0560 (0.0059) against 0.0496; 0.50% (3,000 paths, 18
  null-sides) 0.0493 (0.0040) against 0.0493; 1.00% (6,000 paths, 22 null-sides) 0.0498 (0.0028) against 0.0492; 2.00%
  (12,000 paths, 36 null-sides) 0.0498 (0.0020) against 0.0490; 5.00% (30,000 paths, 46 null-sides) 0.0481 (0.0012)
  against 0.0476. So the accepted paths' size runs from 0.0481 to 0.0560, from +0.0000 to +0.0064 above the side
  average, at most 1.1 SE from it.
- Two earlier draws of the same check, 3,000 paths per null each. The third fix pass's (seed 20261114) gave 0.0411 to
  0.0600 against side averages of 0.0465 to 0.0493: -0.0072 to +0.0108 above them, at most 1.6 SE. Review D's draw was
  re-analysed from its saved simulation with identical output; its seed was not recorded, and it is not reproducible
  from this repository. It gave 0.0481 to 0.0556 against 0.0459 to 0.0481: +0.0004 to +0.0075 above them, at most 1.7
  SE (from its 4-decimal figures).
- The three draws two at a time: the difference of the accepted paths' size at p < 0.025, over both draws' SEs
  combined, at the shares 0.25%, 0.50%, 1.00%, 2.00%, 5.00%, in that order. The main draw minus the third fix pass's:
  -0.32, -0.21, +1.60, +1.26, +2.08 SE. The main draw minus review D's: +0.41, -0.21, -0.95, +0.40, -0.60 SE. The
  third fix pass's minus review D's: +0.58, +0.00, -2.03, -0.68, -2.13 SE. 3 of these 15 differences are larger than 2
  SE. The binomial SE is conditional on the accepted set: it counts the test's rejections on the paths a draw
  accepted, not which paths it accepts, so it understates the spread between draws.
- Above the cap: the main draw's 0.0560 at 0.25%, the third fix pass's 0.0600 at 0.25%, review D's 0.0556 at 1.00%.
  Each is above the rule's size cap 0.055 and above the registered ABC-weighted size 0.0508 (battery seed) and 0.0502
  (second seed).
- Within each null-side whose share of the main draw's nearest 1% is at least 0.03 (its acceptance share in this draw,
  not its registered weight), the tenth of its paths nearest the real d rejects at p < 0.025 at: S4 f=0.1 left
  rhos=.99/.997/.999 -d (share 0.1160) 0.0750 on its nearest 1,000 against 0.0685 on all its paths; S4 f=0.1 right
  rhos=.99/.997/.999 +d (share 0.1152) 0.0800 on its nearest 1,000 against 0.0722 on all its paths; S4 f=0.15 left
  rhos=.99/.997/.999 -d (share 0.1123) 0.0890 on its nearest 1,000 against 0.0782 on all its paths; S4 f=0.15 right
  rhos=.99/.997/.999 +d (share 0.1075) 0.0860 on its nearest 1,000 against 0.0814 on all its paths; S4 f=0.1 left
  rhos=.98/.99/.995 -d (share 0.0960) 0.0200 on its nearest 1,000 against 0.0303 on all its paths; S4 f=0.1 left
  rhos=.97/.985/.993 -d (share 0.0907) 0.0220 on its nearest 1,000 against 0.0294 on all its paths; S4 f=0.0 right
  rhos=.99/.997/.999 +d (share 0.0617) 0.0270 on its nearest 1,000 against 0.0222 on all its paths; S4 f=0.0 left
  rhos=.99/.997/.999 -d (share 0.0617) 0.0180 on its nearest 1,000 against 0.0239 on all its paths; orch long s=1.0 +d
  (share 0.0538) 0.0260 on its nearest 1,000 against 0.0281 on all its paths; S4 f=0.2 left rhos=.98/.99/.995 -d
  (share 0.0508) 0.0390 on its nearest 1,000 against 0.0363 on all its paths; S4 f=0.2 left rhos=.97/.985/.993 -d
  (share 0.0468) 0.0360 on its nearest 1,000 against 0.0308 on all its paths; orch long s=1.5 +d (share 0.0372) 0.0160
  on its nearest 1,000 against 0.0147 on all its paths.

## Tests evaluated and rejected (the screen: the battery's 2,000 runs per null-side, nominal 0.05)
- the plain EWC t, q = 2, against t_2 (critical value 2.92): worst 0.2485 (orch long s=1.5, -d), 39/60 in the band,
  power 0.7975 at falsifier (c)
- the plain EWC t, q = 3, against t_3 (critical value 2.3534): worst 0.28 (orch long s=1.5, -d), 35/60 in the band,
  power 0.907 at falsifier (c)
- the plain EWC t, q = 4, against t_4 (critical value 2.1318): worst 0.298 (orch long s=1.5, -d), 34/60 in the band,
  power 0.944 at falsifier (c)
- the fixed-b Newey-West t, b = 0.5, against its simulated iid-normal 95% quantile (critical value 2.7857): worst
  0.2985 (orch long s=1.5, -d), 32/60 in the band, power 0.942 at falsifier (c)
- the fixed-b Newey-West t, b = 1, against its simulated iid-normal 95% quantile (critical value 3.7526): worst 0.3
  (orch long s=1.5, -d), 32/60 in the band, power 0.929 at falsifier (c)
- the block sign flip at block 168 (inference.block_signflip, 999 draws): worst 0.372 (orch long s=1.5, -d), 14/60 in
  the band, power 0.9815 at falsifier (c)
- the EWC bootstrap-t at q = 3, block 21 (inference.ewc_bootstrap, 999 draws): worst 0.236 (orch long s=1.5, -d),
  41/60 in the band, power 0.898 at falsifier (c)
- the EWC t, q = 4, on the 119 monthly origins (every 21st session), against t_4 (critical value 2.1318): worst 0.296
  (orch long s=1.5, -d), 34/60 in the band, power 0.858 at falsifier (c)
- the fixed-b t, b = 1, on the monthly origins, against its simulated 95% quantile (critical value 3.7416): worst
  0.303 (orch long s=1.5, -d), 30/60 in the band, power 0.8465 at falsifier (c)
- the EWC bootstrap-t, q = 4, block 1, on the monthly origins (999 draws): worst 0.23 (orch long s=1.5, -d), 39/60 in
  the band, power 0.849 at falsifier (c)
- the EWC bootstrap-t, q = 4, block 3, on the monthly origins (999 draws): worst 0.2215 (orch long s=1.5, -d), 40/60
  in the band, power 0.844 at falsifier (c)
- the plain EWC t, q = 4, against the min-max critical value on these nulls (critical value 5.3296): worst 0.121 (orch
  long s=1.5, -d), 1/60 in the band, power 0.3225 at falsifier (c)
- The rule of the first revision: the smallest worst-case size among the candidates with power of at least 0.9 at
  falsifier (c). It picks the EWC bootstrap-t at q = 4 (worst 0.253 (orch long s=1.5, -d), power 0.942); the
  candidates with that power: the plain EWC t, q = 3, against t_3: worst 0.28, power 0.907; the plain EWC t, q = 4,
  against t_4: worst 0.298, power 0.944; the fixed-b Newey-West t, b = 0.5, against its simulated iid-normal 95%
  quantile: worst 0.2985, power 0.942; the fixed-b Newey-West t, b = 1, against its simulated iid-normal 95% quantile:
  worst 0.3, power 0.929; the block sign flip at block 168 (inference.block_signflip, 999 draws): worst 0.372, power
  0.9815.

## The data looked at
- The 2002-2009 d-series (2002-04-01 to 2009-12-01, n = 1,934, labelled "pre-development") was used only for summaries
  that do not reveal its mean or sign: the ACF (lag 1 0.8865), the moving-block SE sweep (it did not settle:
  se(168)/se(84) = 1.1604), its centred moments (skewness 2.317 and excess kurtosis 20.533, moments of (d - mean) / sd
  with ddof 0: the same sample estimators as the twelve summaries, to 3 decimals) and the twelve summaries above. The
  lag-1 ACF 0.8865 set the battery's AR(1) nulls and falsifier (c), on whose power the first revision chose q = 4 and
  the EWC bootstrap-t. The twelve summaries set the matched null-sides that check the threshold.
- Disclosed: milestone 4 part A's IV30 probe (a scratch script outside the repository) printed VrpSignal("har") and
  VrpSignal("naive") values on 5 sessions of 2015. Each embeds that session's HAR or naive RV forecast. No target,
  loss or d was computed from them.
- The scorer's SHA-256 covers the 14 files of its closure: the repository files it imports, found from the source.
  Other code outside the closure is not hashed. The scorer's checks catch mistakes and the routes they name. They do
  not stop code written to defeat them. Any code that runs in the scorer's process before or between the checks can
  defeat them: a file put on the import path, a .pth file, an edited library or standard library, a forged .pyc, or a
  module that removes itself. The routes named here are examples, not a complete list.
- The checks of tools/ read every folder in tools/ and every file there whose name ends with an import suffix (.py,
  .pyc or an extension module's suffix). A file's module name is its name less the longest import suffix; a folder's
  module name is its name. The checks leave out an entry whose module name holds a dot, such as tools/prereg.old.py:
  no import loads it under any name. They also leave out tools/__pycache__, Python's bytecode cache. Python writes it
  when the scorer imports its modules, git ignores it, and the standard library also has a folder of that name, so the
  commit check and the name check would refuse every run. `import __pycache__` can load it, and no check reads what it
  holds. The checks read a name with a hyphen: the standard library's sysconfig imports its data module by such a name
  (here _sysconfigdata__linux_aarch64-linux-gnu).
- Run as a script, before it imports tools/prereg.py, the scorer refuses to run when an entry of tools/ that the
  checks read takes the name of one of the scorer's modules there and is not that module's .py file (a tools/prereg/
  package would run in place of tools/prereg.py), or when two entries of tools/ that the checks read share a module
  name. Before it imports any third-party module, it refuses when PYTHONPATH, PYTHONHOME, PYTHONUSERBASE or
  _PYTHON_SYSCONFIGDATA_NAME is set, when an entry of tools/ that the checks read has the name of a standard-library
  module or of a module found on another entry of sys.path, when HEAD does not hold such an entry as committed, or
  when sys.modules holds a module loaded from tools/ that is not a closure file. Under the ledgers' lock, just before
  it writes the first spent line, the scorer refuses again when sys.modules holds such a module. The first three
  variables can put other code before the scorer's. _PYTHON_SYSCONFIGDATA_NAME names the module sysconfig imports, and
  the scorer refuses it before that import. The name check also runs before that import, so a tools/ file named after
  sysconfig's data module is refused before it runs. The commit check reads the same entries as the name check: a file
  with an import suffix, or a folder. A file must be in HEAD with the same bytes. For a folder, HEAD must hold it as a
  folder, and every file with an import suffix directly in it must be committed as it is. The commit check does not
  read files deeper down, or files without an import suffix.
- Some routes run before the check that refuses them, or are not refused. A tools/ file named after a standard-library
  module that the scorer imports first (tools/gettext.py) runs before the check that refuses it. A committed tools/
  file that a library imports when it exists (tools/numexpr.py, which pandas imports) runs before the check under the
  lock. If its import raises ImportError, Python removes it from sys.modules and pandas carries on: no check refuses
  it, and the scorer scores. A committed tools/ file that is first imported after the spend is not refused.
- The pre-registration names the versions of duckdb 2.0.0, numpy 2.5.4, pandas 3.1.0, pyarrow 26.0.0, python 3.12.13.
  A closure file edited by mistake, or another version of a library or of Python, makes the scorer refuse; the remedy
  is an amendment, a new dated file that names this one's hash.
- The store's spy_bars and dividends files are named by SHA-256: scoring on other data refuses.

## What happens next
1. Commit the whole tree first, tools/ in full, with the three files and an empty spent.jsonl (after the history
   rewrite). The scorer's checks read each file with an import suffix and each folder in tools/, other than
   tools/__pycache__ and an entry whose module name holds a dot. The scorer refuses to run while HEAD does not hold
   such an entry as committed. A file must be in HEAD with the same bytes. For a folder, HEAD must hold it as a
   folder, and every file with an import suffix directly in it must be committed as it is. The commit check does not
   read files deeper down, or files without an import suffix (tools/score_prereg.py uncommitted_entries says which).
2. `uv run python tools/score_prereg.py 2026-11-09-forecast-har-vs-naive`, once. It spends the window (spent.jsonl and
   its side ledger in the git common directory) before it computes the result.
3. Commit the result and spent.jsonl and push at once: the pushed history is then the record. Until then, a clone
   whose refs do not reach that commit does not see the spend (tools/prereg.py names other ways to defeat the
   tripwire). Then set the signal's rv_model by the decision rule.
