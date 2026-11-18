# Pre-registration and block inference

## First principles

A test of a claim is only as honest as the number of times the data was allowed to answer. If you try 36 rules and report the best, the best looks good by luck. If you test one claim, write down how you will decide first, and look once, the answer means what it says.

Terms:
- **Pre-registration**: the claim, the candidates, the metric, the window, the test, the threshold and the decision rule, all written and hashed before any scoring.
- **k**: how many tests the registration scores. Here k = 1, so a multiplicity correction changes nothing (the Holm-adjusted p equals p).
- **One-shot**: the window is scored once. The scorer writes the spend to an append-only ledger *before* it computes, and a window that overlaps a spent one is refused for every candidate.
- **Paired difference** d_t: the benchmark's loss minus the candidate's loss on session t, so d > 0 favours the candidate.
- **QLIKE**: the loss y/ŷ − ln(y/ŷ) − 1 of forecasting variance ŷ when the proxy is y. It is 0 only at ŷ = y. It is a proxy loss ([concept 19](19-realised-variance-from-daily-bars.md)).
- **Block**: a run of consecutive sessions kept together when resampling, to keep the dependence between neighbours.
- **Effective size**: the rate at which a test, run on data whose true mean is 0, rejects at the threshold. A test with nominal 0.025 and effective size 0.05 is 5%-level evidence.

## The maths

**The claim, as registered.** The 21-session HAR forecast ([concept 20](20-har-and-causal-refits.md)) has a lower QLIKE than the naive RV22 on development sessions: mean(d) > 0 with d_t = QLIKE(naive)_t − QLIKE(HAR)_t.

**Why a block test.** The 21-session targets of neighbouring sessions share 20 of their 21 days, so d is strongly autocorrelated: its lag-1 autocorrelation on 2002-2009 was 0.8865. A test that treats the 2,495 sessions as independent would overstate the evidence. The test has to carry the dependence.

**The test, as registered (EWC bootstrap-t).**
- The EWC t: Y_j = √(2/n) Σ_t cos(πj(t − ½)/n) d_t for j = 1..q, and t = √n · mean(d) / √(mean_j Y_j²). It estimates the long-run variance from the q lowest frequencies, with q = 4. For independent normal d it follows a t distribution with q degrees of freedom.
- The bootstrap: resample n values as ⌈n/block⌉ blocks of 21 consecutive d, centre them, compute t* for each of 9,999 draws, and set p = (1 + #{t* ≥ t}) / (1 + draws). The bootstrap handles the skew of a QLIKE difference. The confidence interval is mean(d) minus the t* quantiles times the standard error.
- **Block 21** is the targets' overlap, fixed in advance. It was not measured: the 2002-2009 moving-block sweep did not settle. q = 4 and the EWC bootstrap-t were chosen on simulated nulls set from the 2002-2009 lag-1 autocorrelation.
- **Threshold p < 0.025**, one-sided. The decision rule is: use HAR if p < 0.025 and the EWC t is positive; otherwise use naive.

**The files and the spend.** `docs/validation/prereg/<id>.json` holds the claim and every setting, `<id>.md` the rationale and `<id>.sha256` the `sha256sum` of both. All three are committed before scoring. `tools/score_prereg.py` refuses on a hash mismatch, an uncommitted or modified file, a changed scorer, or a spent window. It appends the spend to `spent.jsonl` (and a side ledger) before it computes anything. `tools/prereg.py make_run_gate` is the gate that `run_backtest` takes for any run past 2019-12-31: it refuses an unlisted configuration, a holdout run with no validation record (ADR-0010 test 4b), a fourth run of one trial on validation dates (test 8: the run of record and two re-runs), and a spent window. A defect re-run happens only before scoring; after scoring, a fail is final.

**Result on real data** (scored once, 2026-11-17, development window 2010-01-04 to 2019-11-29, n = 2,495 sessions; `docs/validation/prereg/2026-11-09-forecast-har-vs-naive.result.json` and [the ledger](../validation/04-ledger.md)): the rule gives **HAR**. p = 0.0139 against the threshold 0.025; mean(d) = 0.2477; 95% interval [0.0401, 0.5991]; EWC t = 2.691; standard error 0.0921; n/block = 118.8.

**How to read it.**
- **About 5%-level evidence, not 2.5%.** At the 0.025 line the test rejects mean-0 nulls at 0.0508 and 0.0502 (ABC-weighted over the simulated nulls nearest the data, two seeds), at 0.011 to 0.083 across the individual matched nulls, and at 0.189 on the worst null of the battery. The result carries these sizes beside p.
- **QLIKE is a proxy.** A lower QLIKE ranks forecast loss. It says nothing about the value of the signal or of any strategy. The decision it feeds is only the signal's RV model.
- **Development data, fresh for this loss, not unseen.** The window is on the development split, and the signal's HAR forecasts had been computed on those sessions in the M4 budget run, which printed only run ids, status, sessions and timings. No loss was computed before the scoring.
- **k = 1 is honest.** The scorer computes one test.

**Trial counting.** The strategy grid is a different matter. Its 36 configurations run on development data, and every distinct (config hash, code fingerprint, data fingerprint) triple among its development runs is a trial. N_raw = the trials + the design-choice log: 36 + 10 = 46 (ADR-0010, M4 amendment 8). Any strategy P&L from those runs is in-sample, selection-biased and no claim; none is reported before M6.

## Assumptions

- **The proxy is unbiased.** QLIKE ranks forecasts under a noisy unbiased proxy as it would under the truth (Patton 2011). A biased proxy would not.
- **The simulated nulls resemble the data.** The size figures come from nulls chosen by their dependence summaries. They are an estimate of the test's behaviour, not a proof.
- **The ledger is honest.** The one-shot rule binds a workflow, not an adversary: a person with write access can still run the code elsewhere. The tools list what they do not stop (`tools/prereg.py`'s docstring).

## Where it breaks

- **Size.** No test of a mean held its level on every simulated null. Near-unit-root nulls reject far above the nominal rate. That is why the effective size is reported.
- **A threshold named with the sizes in view.** The 0.025 threshold was named by a reviewer before the matching rule was coded, and the rule's size cap was set with that reviewer's sizes in view. The `.md` says so.
- **A spent window is a window of dates.** The spent window ends on 2019-11-29 but its targets run to 2019-12-31, so a later window starting on 2019-12-02 would not be refused (open item, 04-ledger).
- **Validation and holdout are not scored.** The strategy pre-registration freezes at the end of M5; M6 scores validation once and the holdout once.

## In this project

- `src/volbt/analytics/inference.py:91` `qlike`, `:124` `mb_se`, `:137` `block_sweep`, `:210` `ewc_t`, `:221` `ewc_bootstrap` (the registered test), `:271` `block_signflip`, `:300` `nw_t`, `:319` `block_bootstrap_ci`, `:347` `holm`.
- `tools/forecast_test.py:36` `window`, `:46` `forecasts`, `:77` `paired`; `tools/score_prereg.py:264` `score`, `:208` `unspent`; `tools/prereg.py:598` `make_run_gate`.
- `src/volbt/engine/run_config.py:117` `prereg_id` (a trial past 2019 without one is refused).
- `tests/test_inference.py:130` `ewc_t` by hand, `:147` the bootstrap p by enumeration, `:314-340` the falsifiers; `tests/test_prereg.py:560` test 4b and `:579` test 8 on real configurations; `tests/test_prereg_files.py:46` the registration is intact.
- `notebooks/04_strategies_and_signal.ipynb`, the cells "The forecast test: a paired loss and a block bootstrap".
