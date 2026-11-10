"""Paired-loss inference (volbt.analytics.inference): hand cases, QLIKE's robustness to a noisy proxy (E3, Patton
2011) and the falsifiers of the one-shot forecast test (E4, marked slow; they still run by default).

All data is made up: literals, or seeded simulations (a log-AR(1) variance path, AR(1) paired differences).

E4 runs the pre-registered test, ewc_bootstrap(d, q=4, block=21), one-sided at the nominal 0.05 (999 draws per run
here; the scorer uses 9,999), on 400 seeded series of T = 2,495 per case. The pre-registration decides at p < 0.025,
chosen on the nulls nearest the 2002-2009 d-series (fix pass 2); its .json carries the battery's falsifier (c) power at
that threshold, 0.8265 over 2,000 runs, below the 0.9 asked here at 0.05:
  (a) d identically 0: the EWC t is undefined (ValueError), and the scorer's null control gives p = 1
      (tests/test_prereg.py);
  (b) the null, mean 0: a Gaussian AR(1) at rho 0.8865 (the 2002-2009 d-series' lag-1 ACF) rejects in [0.02, 0.09]
      on +d and on -d; so does a skewed one, exp(1.5 u) - E exp(1.5 u) (the skew the block sign flip failed);
  (c) power: a mean shift giving a long-run t of 4 (LRV = sigma_e^2 / (1 - rho)^2) rejects in >= 0.9 of the runs.
The band is wider than the battery's [0.025, 0.075] because 400 runs carry a Monte Carlo SE of 0.011; the battery's
2,000 runs per null are in tools/forecast_size.py and the pre-registration.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from volbt.analytics import inference as inf

# E4: the AR(1) coefficient of d, as task 8 measured it on the 2002-2009 d-series (lag-1 ACF 0.8865), and the
# pre-registered test.
RHO = 0.8865
Q, BLOCK = 4, 21

T = 2495                # sessions in the forecast test's window (plan section 6)
RUNS = 400
DRAWS = 999
ALPHA = 0.05
BAND = (0.02, 0.09)


# --- hand cases ---------------------------------------------------------------------------------------------

def test_qlike_is_zero_at_the_truth_and_the_hand_value_elsewhere():
    """y/yhat - ln(y/yhat) - 1: 0 where yhat == y; y = 2, yhat = 1 gives 1 - ln 2; y = 1, yhat = 2 gives ln 2 - 1/2."""
    assert np.array_equal(inf.qlike([1e-4, 0.04, 3.0], [1e-4, 0.04, 3.0]), [0.0, 0.0, 0.0])
    loss = inf.qlike([2.0, 1.0], [1.0, 2.0])
    assert loss == pytest.approx([1 - math.log(2), math.log(2) - 0.5], abs=1e-15)
    assert loss[0] > loss[1]        # forecasting half the variance costs more than forecasting twice it


def test_acf_of_a_literal():
    """[1, 2, 3, 4]: deviations [-1.5, -0.5, 0.5, 1.5], sum of squares 5; lag sums 1.25, -1.5, -2.25."""
    assert inf.acf([1.0, 2.0, 3.0, 4.0], 3) == pytest.approx([1.0, 0.25, -0.3, -0.45], abs=1e-15)
    assert inf.acf([1.0, 2.0, 3.0, 4.0], 0) == pytest.approx([1.0])
    assert np.isnan(inf.acf([2.0, 2.0, 2.0], 2)).all()


def test_mb_se_by_hand():
    """d = [1, 2, 3, 4], block 2: B = [1.5, 2.5, 3.5], var 2/3, k = 2, se = sqrt(1/3).
    Block 1: B = d, var 1.25, k = 4, se = sqrt(0.3125) (the iid bootstrap SE).
    d = [1, 2, 3, 4, 5], block 2: B = [1.5, 2.5, 3.5, 4.5], var 1.25, k = 5 // 2 = 2, se = sqrt(0.625)."""
    assert inf.mb_se([1.0, 2.0, 3.0, 4.0], 2) == pytest.approx(math.sqrt(1 / 3), abs=1e-15)
    assert inf.mb_se([1.0, 2.0, 3.0, 4.0], 1) == pytest.approx(math.sqrt(0.3125), abs=1e-15)
    assert inf.mb_se([1.0, 2.0, 3.0, 4.0, 5.0], 2) == pytest.approx(math.sqrt(0.625), abs=1e-15)


def test_holm_by_hand():
    """[0.01, 0.04, 0.03, 0.005]: sorted 0.005, 0.01, 0.03, 0.04 times 4, 3, 2, 1 = 0.02, 0.03, 0.06, 0.04; the running
    max makes the last 0.06; back in the input order, [0.03, 0.06, 0.06, 0.02]."""
    assert inf.holm([0.01, 0.04, 0.03, 0.005]) == pytest.approx([0.03, 0.06, 0.06, 0.02], abs=1e-15)
    assert inf.holm([0.6, 0.9]) == pytest.approx([1.0, 1.0])          # 1.2 is capped at 1, then the running max
    assert inf.holm([0.2, 0.04]) == pytest.approx([0.2, 0.08])
    assert inf.holm([0.03]) == pytest.approx([0.03])


def test_nw_t_with_no_lags_is_the_plain_t_with_the_ddof_0_std():
    """d = [1, 2, 3, 4]: lags 0 gives mean / (std(d, ddof=0) / sqrt(n)) = 2.5 / (sqrt(1.25) / 2) = sqrt(20).
    Lags 1: gamma_1 = 1.25 / 4, LRV = 1.25 + 2 x 0.5 x 0.3125 = 1.5625, t = 2.5 / sqrt(1.5625 / 4) = 4."""
    d = [1.0, 2.0, 3.0, 4.0]
    assert inf.nw_t(d, 0) == pytest.approx(math.sqrt(20), abs=1e-14)
    assert inf.nw_t(d, 0) == pytest.approx(np.mean(d) / (np.std(d, ddof=0) / 2), abs=1e-14)
    assert inf.nw_t(d, 1) == pytest.approx(4.0, abs=1e-14)
    assert inf.nw_t([-x for x in d], 1) == pytest.approx(-4.0, abs=1e-14)


def test_nw_t_of_a_constant_series_is_0_at_a_zero_mean_and_infinite_otherwise():
    """LRV = 0: 0.0 when the mean is 0, else +-inf with the mean's sign (the module's stated convention)."""
    assert inf.nw_t([0.0] * 6, 2) == 0.0
    assert inf.nw_t([2.0] * 6, 2) == math.inf
    assert inf.nw_t([-0.5] * 6, 0) == -math.inf


@pytest.mark.parametrize(("path", "block", "converged"), [
    ({21: 1.0, 42: 1.3, 84: 1.35, 168: 1.36}, 42, True),     # 1.35 / 1.3 = 1.038
    ({21: 1.0, 42: 1.0, 84: 1.2, 168: 1.25}, 84, True),      # 21 passes but is under the minimum; 42 moves 20%
    ({21: 1.0, 42: 1.5, 84: 2.0, 168: 2.6}, 168, False),     # never within 10%: the largest block of the list
    ({21: 1.0, 42: 0.0, 84: 0.0, 168: 0.0}, 168, False),     # se(b) = 0: the ratio is NaN and never qualifies
])
def test_block_sweep_picks_the_rules_block_on_constructed_se_paths(monkeypatch, path, block, converged):
    monkeypatch.setattr(inf, "mb_se", lambda d, b: path[b])
    out = inf.block_sweep(np.zeros(400))
    assert out["block"] == block and out["converged"] is converged
    assert out["se"] == path
    assert set(out["ratios"]) == {21, 42, 84}
    if path[84]:
        assert out["ratios"][84] == pytest.approx(path[168] / path[84])
    else:
        assert math.isnan(out["ratios"][84])


def test_block_sweep_needs_a_ratio_strictly_inside_the_tolerance(monkeypatch):
    """|3/2 - 1| = 0.5 exactly: not < 0.5, so 42 fails and 84 (4.5 / 3 = 1.5) fails too: the largest block."""
    monkeypatch.setattr(inf, "mb_se", lambda d, b: {21: 1.0, 42: 2.0, 84: 3.0, 168: 4.5}[b])
    out = inf.block_sweep(np.zeros(400), tol=0.5)
    assert (out["block"], out["converged"]) == (168, False)
    assert inf.block_sweep(np.zeros(400), tol=0.5000001)["block"] == 42


def test_block_sweep_reports_mb_se_at_each_block_in_plain_python_types():
    d = np.random.default_rng(3).standard_normal(1000)
    out = inf.block_sweep(d)
    assert out["se"] == {b: inf.mb_se(d, b) for b in (21, 42, 84, 168)}
    assert all(type(k) is int and type(v) is float for k, v in out["se"].items())
    assert all(type(k) is int and type(v) is float for k, v in out["ratios"].items())
    assert type(out["block"]) is int and type(out["converged"]) is bool and isinstance(out["rule"], str)
    assert out["block"] in (42, 84)


# --- the EWC t and its bootstrap -------------------------------------------------------------------------------

def test_ewc_t_by_hand():
    """d = [1, 2, 3, 4], q = 1: Y_1 = sqrt(1/2) (-3 cos(pi/8) - cos(3pi/8)) = -sqrt(1/2) (2.771639 + 0.382683)
    = -2.230442, t = 2 x 2.5 / 2.230442 = 2.2417076. d = [1, 2, 3], q = 1: Y_1 = sqrt(2/3) (cos(pi/6) - 3 cos(pi/6))
    = -sqrt(2), t = sqrt(3) x 2 / sqrt(2) = sqrt(6). The cosines ignore the mean: adding 10 to d changes only the
    numerator."""
    y1 = math.sqrt(0.5) * (-3 * math.cos(math.pi / 8) - math.cos(3 * math.pi / 8))
    assert inf.ewc_t([1.0, 2.0, 3.0, 4.0], 1) == pytest.approx(5.0 / abs(y1), abs=1e-12)
    assert inf.ewc_t([1.0, 2.0, 3.0, 4.0], 1) == pytest.approx(2.2417076, abs=1e-7)
    assert inf.ewc_t([1.0, 2.0, 3.0], 1) == pytest.approx(math.sqrt(6), abs=1e-12)
    assert inf.ewc_t([11.0, 12.0, 13.0], 1) == pytest.approx(math.sqrt(3) * 12 / math.sqrt(2), abs=1e-12)
    assert inf.ewc_t([-1.0, -2.0, -3.0], 1) == pytest.approx(-math.sqrt(6), abs=1e-12)
    w = inf.cosines(50, 4)
    assert np.allclose(w @ w.T, np.eye(4), atol=1e-12) and np.allclose(w.sum(axis=1), 0.0, atol=1e-12)
    with pytest.raises(ValueError, match="q must be"):
        inf.ewc_t([1.0, 2.0, 3.0], 3)


def test_ewc_bootstrap_p_by_enumeration():
    """d = [1, 2, 3], q = 1, block 2: k = 2 blocks from starts {0, 1}, cut to 3 values; centre = mean of the block
    means = 2. The four equally likely resamples, centred: [-1, 0, -1] (t* = -inf), [-1, 0, 0] (-0.8165),
    [0, 1, -1] (0), [0, 1, 0] (+inf). Only +inf reaches t = sqrt(6): p -> 1/4.
    d = [1, 5, 4, 4], q = 1, block 2, where the mean of the block means (3, 4.5, 4: 23/6) is not mean(d) (3.5): the
    nine resamples pair the blocks (1, 5), (5, 4), (4, 4); centred at 23/6 their t* are -1.0888, -0.0850, -0.3947,
    -0.2053, 3.4842, 1.2756, -4.2058, 3.0796 and +inf, and only +inf reaches t = 4.143860: p -> 1/9 (centred at
    mean(d), three of them would: 3/9)."""
    draws = 200_000
    out = inf.ewc_bootstrap([1.0, 2.0, 3.0], 1, 2, draws, seed=1)
    assert out["t"] == pytest.approx(math.sqrt(6), abs=1e-12)
    assert out["p"] == pytest.approx(0.25, abs=5 * math.sqrt(0.25 * 0.75 / draws))
    assert (out["q"], out["block"], out["draws"]) == (1, 2, draws)
    out = inf.ewc_bootstrap([1.0, 5.0, 4.0, 4.0], 1, 2, draws, seed=2)
    assert out["t"] == pytest.approx(4.143860, abs=1e-6)
    assert out["p"] == pytest.approx(1 / 9, abs=5 * math.sqrt(1 / 9 * 8 / 9 / draws))


def test_ewc_bootstrap_is_seeded_chunk_independent_and_its_ci_brackets_the_mean(monkeypatch):
    d = np.random.default_rng(8).standard_normal(600) + 0.05
    out = inf.ewc_bootstrap(d, 4, 10, 2000, seed=11)
    assert out["t"] == pytest.approx(inf.ewc_t(d, 4), rel=1e-12)
    assert out["se"] == pytest.approx(d.mean() / out["t"], rel=1e-12)
    assert 1 / 2001 <= out["p"] <= 1 and out["ci"][0] < d.mean() < out["ci"][1]
    assert inf.ewc_bootstrap(d, 4, 10, 2000, seed=11) == out
    assert inf.ewc_bootstrap(d, 4, 10, 2000, seed=12)["p"] != out["p"]
    monkeypatch.setattr(inf, "CHUNK_CELLS", 77)          # one resample per chunk: the same draws, other BLAS blocks
    other = inf.ewc_bootstrap(d, 4, 10, 2000, seed=11)
    assert other["p"] == out["p"] and other["ci"] == pytest.approx(out["ci"], rel=1e-12)
    with pytest.raises(ValueError, match="low-frequency"):
        inf.ewc_bootstrap(np.zeros(50), 4, 5, 10, seed=1)
    with pytest.raises(ValueError, match="shorter"):
        inf.ewc_bootstrap(d, 4, 600, 10, seed=1)


# --- the sign flip and the CI -------------------------------------------------------------------------------

def test_signflip_p_counts_the_observed_draw_and_ties_as_at_or_above():
    """p = (1 + #{mean* >= mean_obs}) / (1 + draws), by exact enumeration of the sign patterns:
    three equal positive blocks: only + + + reaches the mean, p -> 1/8;
    [1, 1 | 1, 1 | -10] (the last block holds the remainder): sums [2, 2, -10], 5 of 8 patterns >= -6, p -> 5/8;
    [0.1, 0.2, -0.3, 0.4], block 1: 5 of 16 patterns tie or beat the mean in exact arithmetic, one of them only within
    rounding (-0.1 - 0.2 + 0.3 + 0.4 against 0.1 + 0.2 - 0.3 + 0.4)."""
    draws = 20_000
    se = math.sqrt(0.25 / draws)
    assert inf.block_signflip([1.0, 1.0, 1.0], 1, draws, seed=1) == pytest.approx(1 / 8, abs=5 * se)
    assert inf.block_signflip([1.0, 1.0, 1.0, 1.0, -10.0], 2, draws, seed=2) == pytest.approx(5 / 8, abs=5 * se)
    assert inf.block_signflip([0.1, 0.2, -0.3, 0.4], 1, draws, seed=3) == pytest.approx(5 / 16, abs=5 * se)
    assert inf.block_signflip([1.0, 2.0, 3.0], 3, draws, seed=4) == pytest.approx(1 / 2, abs=5 * se)   # one block
    assert inf.block_signflip(np.zeros(50), 5, 10, seed=5) == 1.0


def test_the_random_functions_are_seeded_and_independent_of_the_chunk_size(monkeypatch):
    d = np.random.default_rng(8).standard_normal(500) + 0.05
    p = inf.block_signflip(d, 10, 3000, seed=11)
    ci = inf.block_bootstrap_ci(d, 10, 3000, seed=11)
    assert inf.block_signflip(d, 10, 3000, seed=11) == p and inf.block_bootstrap_ci(d, 10, 3000, seed=11) == ci
    assert inf.block_signflip(d, 10, 3000, seed=12) != p and inf.block_bootstrap_ci(d, 10, 3000, seed=12) != ci
    monkeypatch.setattr(inf, "CHUNK_CELLS", 77)          # one row of 50 blocks per chunk
    assert inf.block_signflip(d, 10, 3000, seed=11) == p and inf.block_bootstrap_ci(d, 10, 3000, seed=11) == ci


def test_signflip_less_is_greater_on_minus_d_and_two_sided_is_symmetric():
    d = np.random.default_rng(9).standard_normal(300) + 0.1
    greater = inf.block_signflip(d, 6, 4000, seed=21)
    assert inf.block_signflip(-d, 6, 4000, seed=21, alternative="less") == greater
    two = inf.block_signflip(d, 6, 4000, seed=21, alternative="two-sided")
    assert two == inf.block_signflip(-d, 6, 4000, seed=21, alternative="two-sided")
    assert greater < two < 1


def test_inference_refuses_bad_input():
    with pytest.raises(ValueError, match="finite"):
        inf.block_signflip([0.1, float("nan"), 0.2], 1, seed=1)
    with pytest.raises(ValueError, match="finite"):
        inf.nw_t([0.1, float("inf")], 0)
    with pytest.raises(ValueError, match="block"):
        inf.mb_se([1.0, 2.0], 3)
    with pytest.raises(ValueError, match="block"):
        inf.block_bootstrap_ci([1.0, 2.0], 0, seed=1)
    with pytest.raises(ValueError, match="alternative"):
        inf.block_signflip([1.0, 2.0], 1, seed=1, alternative="two_sided")
    with pytest.raises(ValueError, match="1-D"):
        inf.mb_se(np.ones((2, 2)), 1)
    with pytest.raises(TypeError):
        inf.block_signflip([1.0, 2.0], 1, 100, 7)          # the seed is keyword-only and has no default


def test_ci_of_a_constant_series_is_the_constant_when_the_last_block_is_cut():
    """n = 5, block 2: k = 3 blocks of 2 make 6 values, cut to 5; every resample of ones has mean exactly 1."""
    assert inf.block_bootstrap_ci(np.ones(5), 2, 500, seed=1) == (1.0, 1.0)
    assert inf.block_bootstrap_ci(np.full(7, 0.25), 3, 500, seed=2) == (0.25, 0.25)


def test_ci_width_is_the_normal_width_of_mb_se_when_the_blocks_tile_d():
    """n = 2,520 = 60 x 42: a resample is 60 whole blocks, so its mean has sd mb_se exactly; the 95% percentile CI of
    a sum of 60 iid block means is about +-1.96 sd wide, and contains mean(d)."""
    rng = np.random.default_rng(13)
    e = rng.standard_normal(2520 + 200)
    d = np.empty_like(e)
    d[0] = e[0]
    for t in range(1, d.size):
        d[t] = 0.5 * d[t - 1] + e[t]
    d = d[200:]
    lo, hi = inf.block_bootstrap_ci(d, 42, 10_000, seed=14)
    assert (hi - lo) / (2 * 1.959964 * inf.mb_se(d, 42)) == pytest.approx(1.0, abs=0.05)
    assert lo < d.mean() < hi
    lo50, hi50 = inf.block_bootstrap_ci(d, 42, 10_000, seed=14, level=0.5)
    assert (hi50 - lo50) / (2 * 0.674490 * inf.mb_se(d, 42)) == pytest.approx(1.0, abs=0.06)


# --- E3: QLIKE under a noisy proxy (Patton 2011) ------------------------------------------------------------

def variance_path(n: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """(h, y): a log-AR(1) daily variance path around 1e-4, and the proxy y = h z^2, z ~ N(0, 1), so E[y | h] = h."""
    rng = np.random.default_rng(seed)
    x = np.empty(n)
    x[0] = 0.0
    shocks = 0.2 * rng.standard_normal(n)
    for t in range(1, n):
        x[t] = 0.98 * x[t - 1] + shocks[t]
    h = 1e-4 * np.exp(x)
    return h, h * rng.standard_normal(n) ** 2


def test_qlike_ranks_forecasts_under_a_noisy_proxy_as_under_the_true_variance():
    """A forecast near h beats one scattered further from it, and one biased low to 0.3 h, under the proxy as under h.
    The proxy is noisy enough to matter: the squared log error, a non-robust loss, prefers 0.3 h under y."""
    h, y = variance_path(20_000, seed=31)
    rng = np.random.default_rng(32)
    near = h * np.exp(0.1 * rng.standard_normal(h.size))
    far = h * np.exp(0.4 * rng.standard_normal(h.size))
    low = 0.3 * h
    for truth in (h, y):
        assert inf.qlike(truth, near).mean() < inf.qlike(truth, far).mean() < inf.qlike(truth, low).mean()
    assert np.mean(np.log(y / low) ** 2) < np.mean(np.log(y / near) ** 2)     # the contrast: log-MSE is fooled
    assert np.mean(np.log(h / low) ** 2) > np.mean(np.log(h / near) ** 2)


def test_qlike_expected_value_is_smallest_at_the_true_variance():
    """Mean QLIKE of c h over c in 0.5..2.0 (steps of 0.1) is smallest at c = 1, under h and under the proxy y."""
    h, y = variance_path(20_000, seed=33)
    scales = np.round(np.arange(0.5, 2.0001, 0.1), 1)
    for truth in (h, y):
        losses = [inf.qlike(truth, c * h).mean() for c in scales]
        assert scales[int(np.argmin(losses))] == 1.0


# --- E4: falsifiers of the one-shot test (slow) -------------------------------------------------------------

def ar1(rho: float, mean: float, seed: int, runs: int = RUNS) -> np.ndarray:
    """`runs` rows of d_t = mean + u_t, u_t = rho u_{t-1} + e_t, e_t ~ N(0, 1), started from the stationary law."""
    e = np.random.default_rng(seed).standard_normal((runs, T))
    u = np.empty_like(e)
    u[:, 0] = e[:, 0] / math.sqrt(1 - rho ** 2)
    for t in range(1, T):
        u[:, t] = rho * u[:, t - 1] + e[:, t]
    return mean + u


def rejection_rate(d: np.ndarray, seed: int) -> float:
    """The share of rows whose one-sided ewc_bootstrap p is below ALPHA, each row with its own seed."""
    return float(np.mean([inf.ewc_bootstrap(row, Q, BLOCK, DRAWS, seed=[seed, i])["p"] < ALPHA
                          for i, row in enumerate(d)]))


@pytest.mark.slow
def test_e4a_a_zero_difference_has_no_ewc_t():
    with pytest.raises(ValueError, match="low-frequency"):
        inf.ewc_bootstrap(np.zeros(T), Q, BLOCK, seed=1)


@pytest.mark.slow
def test_e4b_the_ar1_null_rejects_at_the_nominal_rate_on_both_sides():
    d = ar1(RHO, 0.0, seed=51)
    for side in (d, -d):
        rate = rejection_rate(side, seed=61)
        assert BAND[0] <= rate <= BAND[1], rate


@pytest.mark.slow
def test_e4b_a_skewed_ar1_null_rejects_at_the_nominal_rate_on_both_sides():
    """exp(1.5 u) - exp(1.5^2 / 2), u a unit-variance AR(1) at RHO: mean 0, skewed right on +d and left on -d (the
    orchestrator's null: the block sign flip at block 168 rejected 0.014 and 0.13 of it in the fix pass's 500-run
    screen, the plain EWC t against t_4 0.0195 and 0.1005 in tools/forecast_size.py's 2,000 runs)."""
    u = ar1(RHO, 0.0, seed=52) * math.sqrt(1 - RHO ** 2)
    d = np.exp(1.5 * u) - math.exp(1.5 ** 2 / 2)
    for side in (d, -d):
        rate = rejection_rate(side, seed=62)
        assert BAND[0] <= rate <= BAND[1], rate


@pytest.mark.slow
def test_e4c_a_long_run_t_of_4_is_rejected_in_at_least_90_percent_of_runs():
    """mean / sqrt(LRV / T) = 4 with LRV = 1 / (1 - RHO)^2 (sigma_e = 1): mean = 4 / ((1 - RHO) sqrt(T))."""
    shift = 4.0 / ((1 - RHO) * math.sqrt(T))
    assert rejection_rate(ar1(RHO, shift, seed=54), seed=64) >= 0.9
