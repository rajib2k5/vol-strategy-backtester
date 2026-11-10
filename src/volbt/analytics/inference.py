"""Paired-loss inference for a one-shot pre-registered test (milestone 4, plan sections 6 and 7, E3 and E4).

`d` is a 1-D array of paired differences, oriented by the caller so that d > 0 favours the candidate (for the forecast
test, d_t = QLIKE(naive)_t - QLIKE(HAR)_t). Every function that takes `d` (and acf) refuses one that is empty, not 1-D
or not finite: a NaN compares False with everything, so a count of draws would see no draw at or above it.

    qlike(y, yhat)                  y/yhat - ln(y/yhat) - 1, elementwise (Patton 2011): >= 0, and 0 iff yhat == y
    acf(x, nlags)                   sample autocorrelations at lags 0..nlags, the biased estimator (denominator n var)
    mb_se(d, block)                 the moving-block bootstrap SE of mean(d) over floor(n / block) whole blocks, exact
    block_sweep(d, blocks, ...)     mb_se at each block, and the block the plan's rule picks (a dependence summary)
    dependence_summaries(d)         twelve centred summaries of d's dependence and shape (nothing of its mean or sign)
    ewc_t(d, q)                     the equal-weighted cosine (EWC) t of mean(d), q low-frequency cosines
    ewc_bootstrap(d, q, block, ...) the forecast test: its EWC t, a one-sided moving-block bootstrap-t p-value of
                                    mean(d) <= 0 against mean(d) > 0, and the bootstrap-t CI of mean(d)
    block_signflip(d, block, ...)   one-sided block sign-flip p-value (NOT the forecast test's: see "Size" below)
    nw_t(d, lags)                   mean(d) / sqrt(LRV / n), LRV the Newey-West (Bartlett) long-run variance
    block_bootstrap_ci(d, block, ...)   the moving-block bootstrap percentile CI of mean(d), resamples of n values
    holm(pvalues)                   Holm step-down adjusted p-values, in the input order

The forecast test (fix pass of 2026-11-09, item 1). The EWC t (Mueller 2007; Lazarus, Lewis, Stock and Watson 2018):

    Y_j = sqrt(2/n) sum_{t=1..n} cos(pi j (t - 1/2) / n) d_t,  j = 1..q;   t = sqrt(n) mean(d) / sqrt(mean_j Y_j^2)

estimates the long-run variance from the q lowest frequencies only, so its reference law is t_q (exactly, for iid
normal d) rather than a normal, and it stays closer to its level than a kernel estimate with a fixed block when d is
strongly persistent. The skewness of a QLIKE difference is handled by the bootstrap: resamples of n values made of
ceil(n / block) blocks d[s : s+block] (s uniform on 0..n-block, the last block cut), each centred at c, the mean of all
n - block + 1 block means, give t* = ewc_t(d* - c); p = (1 + #{t* >= t}) / (1 + draws), and the CI is
mean(d) - t*_{(1 +- level)/2} se with se = sqrt(mean_j Y_j^2 / n). c is ~ E* mean*, not exactly: it would be exact
but for the cut last block, whose r = n - (k - 1) block values average the means of r-value prefixes, not of whole
blocks (E* mean* = ((k - 1) block c + r mean of those prefix means) / n). The gap is negligible: at most 9.6e-4 of an
se on 200 simulated series of the battery at n = 2,495, block 21 (k = 119, r = 17; fix pass 2, review A claim 3).
q = 4 and block = 21 (the targets' overlap) were chosen on a battery of simulated nulls, and the decision threshold
on the nulls nearest the 2002-2009 d-series (docs/validation/prereg/2026-11-09-forecast-har-vs-naive.md).

Size. No test of a mean holds its level on every null in that battery (tools/forecast_size.py, 2,000 runs per
null): at a nominal 0.05 the nulls with a near-unit-root component (an AR(1) at rho 0.998 or 0.999 in d over
n = 2,495) reject well above 0.075, the worst of them skewed, and the review's stochastic-volatility nulls a little
above it on -d; the pre-registration's "size" lists every null's rate and the worst. The block sign flip at block
168 (15 blocks) is far outside the band on the same nulls (the pre-registration's "screen" has its rates): a skewed
d breaks its symmetric reference law. It is kept, documented, for no current test.

The moving-block SE and the CI count blocks differently on purpose: mb_se is the exact variance of the mean of
k = floor(n / b) whole blocks (a closed form, no draws), and block_bootstrap_ci resamples exactly n values, ceil(n / b)
blocks with the last one cut. With n = 2,495 and b = 168 the two variances differ by the factor (n / b) / k = 1.06.

The sign flip. d is cut into consecutive blocks of `block` (the last holds the remainder) with sums S_i. Under the null
each block sum is symmetric about 0 and the blocks are nearly independent, so mean* = sum(s_i S_i) / n with independent
signs s_i = +-1 is a draw from the null distribution of mean(d). p = (1 + #{mean* >= mean_obs}) / (1 + draws), so
p >= 1/(1 + draws) and, with d identically 0, p = 1. A draw within 1e-12 x sum|S_i| / n of the observed mean counts as
a tie (at or above it), so the last bit of a sum never decides a tie (default taken 2026-11-09, owner can override).

Randomness. Each random function takes an explicit seed and builds its own np.random.default_rng(seed); nothing reads
or sets global state. The draws are made in chunks of about CHUNK_CELLS values each, from rng.random() (one 64-bit
word per value), so the draws for a seed are the same whatever the chunk size. That rests on numpy's behaviour
(2.5.4: Generator.random fills an array from consecutive draws of the bit generator), not on a documented guarantee;
tests/test_inference.py pins it. ewc_bootstrap's p is then the same too, but its CI only to rounding (about 1e-16):
the matrix product of a chunk is blocked differently by BLAS when the chunk's size changes.

May import (volbt): config, pricing. numpy only.
"""

from __future__ import annotations

import math

import numpy as np

BLOCKS = (21, 42, 84, 168)
CHUNK_CELLS = 1 << 20          # values drawn per chunk: about 8 MB of float64
TIE = 1e-12


def series(d) -> np.ndarray:
    """d as a 1-D float array; ValueError if it is empty, not 1-D or not finite."""
    d = np.asarray(d, dtype=float)
    if d.ndim != 1 or d.size == 0:
        raise ValueError(f"d must be a non-empty 1-D array, got shape {d.shape}")
    if not np.isfinite(d).all():
        raise ValueError("d must be finite (a NaN would decide every comparison of a sign-flip draw)")
    return d


def check_block(block: int, n: int) -> int:
    """block as an int; ValueError unless 1 <= block <= n."""
    if not 1 <= int(block) <= n:
        raise ValueError(f"block must be in 1..{n}, got {block}")
    return int(block)


def qlike(y, yhat) -> np.ndarray:
    """y/yhat - ln(y/yhat) - 1, elementwise (Patton 2011). y and yhat > 0; numpy's NaN or inf otherwise.

    The loss of forecasting the variance yhat when the proxy is y. It is >= 0 and 0 only at yhat == y, and its expected
    value given a proxy with E[y] = h is smallest at yhat = h: so it ranks forecasts with a noisy unbiased proxy as it
    would with the true variance (tests/test_inference.py, E3). It is asymmetric: an under-forecast costs more than
    an over-forecast by the same factor (y = 2, yhat = 1 gives 0.3069; y = 1, yhat = 2 gives 0.1931), so the forecast
    closer to y in absolute terms does not always have the lower loss.
    """
    ratio = np.asarray(y, dtype=float) / np.asarray(yhat, dtype=float)
    return ratio - np.log(ratio) - 1.0


def autocov(x: np.ndarray, nlags: int) -> np.ndarray:
    """gamma_j = sum_t (x_t - mean)(x_{t-j} - mean) / n for j = 0..nlags (0 at j >= n)."""
    if nlags < 0:
        raise ValueError(f"nlags must be >= 0, got {nlags}")
    x = x - x.mean()
    n = x.size
    return np.array([np.dot(x[j:], x[:n - j]) / n if j < n else 0.0 for j in range(nlags + 1)])


def acf(x, nlags: int) -> np.ndarray:
    """Autocorrelations at lags 0..nlags: gamma_j / gamma_0, the mean removed once (lag 0 is 1).

    [1, 2, 3, 4] gives [1, 0.25, -0.3, -0.45]. A constant x (gamma_0 = 0) gives NaN at every lag.
    """
    gamma = autocov(series(x), int(nlags))
    if gamma[0] == 0:
        return np.full(gamma.size, np.nan)
    return gamma / gamma[0]


def mb_se(d, block: int) -> float:
    """The moving-block bootstrap SE of mean(d): sqrt(var(B_j, ddof=0) / (n // block)), B_j the mean of d[j : j+block]
    (whole blocks only, floor(n / block) of them: the module docstring says why the CI's count differs).

    By hand, d = [1, 2, 3, 4], block 2: B = [1.5, 2.5, 3.5], var 2/3, k = 2, so se = sqrt(1/3) = 0.57735. Block 1 gives
    the iid bootstrap SE, std(d, ddof=0) / sqrt(n).
    """
    d = series(d)
    b = check_block(block, d.size)
    means = np.convolve(d, np.ones(b), "valid") / b       # B_j for j = 0..n-b, each its own sum
    return math.sqrt(float(np.var(means)) / (d.size // b))


def block_sweep(d, blocks=BLOCKS, tol: float = 0.10, minimum: int = 42) -> dict:
    """The SE at each block and the block the rule picks (plan section 6).

    Rule: the smallest b in `blocks` with b >= minimum, 2b also in `blocks` and |se(2b)/se(b) - 1| < tol (with the
    default list the candidates are 42 and 84). If none qualifies, the SE still grows at every doubling, so the
    dependence reaches past every block the rule can pick: then the largest block of the list (168), the widest SE
    and the fewest blocks, with converged False (the plan does not say; default taken 2026-11-09, owner can
    override). A ratio whose se(b) is 0 is NaN and never qualifies.

    Returns {"se": {b: se}, "ratios": {b: se(2b)/se(b)} for every b whose 2b is listed, "block": int,
    "converged": bool, "rule": the rule in one line}, in plain Python ints and floats.
    """
    d = series(d)
    blocks = sorted(int(b) for b in blocks)
    paired = [b for b in blocks if 2 * b in blocks]
    if not paired:
        raise ValueError(f"no block in {blocks} has its double in the list")
    se = {b: float(mb_se(d, b)) for b in blocks}
    ratios = {b: se[2 * b] / se[b] if se[b] > 0 else float("nan") for b in paired}
    passing = [b for b in paired if b >= minimum and abs(ratios[b] - 1) < tol]
    chosen = passing[0] if passing else blocks[-1]
    rule = (f"smallest b in {blocks} with b >= {minimum}, 2b listed and |se(2b)/se(b) - 1| < {tol}; "
            f"else the largest b of the list, converged False")
    return {"se": se, "ratios": ratios, "block": int(chosen), "converged": bool(passing), "rule": rule}


SUMMARY_LAGS = (1, 5, 21, 63, 126, 252)
SUMMARY_KEYS = tuple(f"acf{lag}" for lag in SUMMARY_LAGS) + ("r21", "r42", "r84", "skew", "kurt", "spec4_20")


def dependence_summaries(d) -> dict[str, float]:
    """Twelve centred summaries of d (fix pass 2, item 9; review A's summ.py): the ACF at lags 1, 5, 21, 63, 126 and
    252; the SE ratios mb_se(2b) / mb_se(b) at b = 21, 42, 84; the sample skewness and excess kurtosis (moments of
    (d - mean) / std, ddof 0); and spec4_20, the mean squared projection of d on its 4 lowest cosines over that on
    cosines 5..20. Each is invariant to adding a constant to d, and none but the skewness changes sign with d: so none
    reveals mean(d) or its sign (the skewness is the third moment about the mean). n must exceed 336 (2 x 168).

    Returns {key: float} for SUMMARY_KEYS, in that order.
    """
    d = series(d)
    if d.size <= 2 * BLOCKS[-1]:
        raise ValueError(f"dependence_summaries needs more than {2 * BLOCKS[-1]} values, got {d.size}")
    rho = acf(d, SUMMARY_LAGS[-1])
    se = {b: mb_se(d, b) for b in BLOCKS}
    z = (d - d.mean()) / d.std()
    y = cosines(d.size, 20) @ d
    y2 = y * y
    out = {f"acf{lag}": float(rho[lag]) for lag in SUMMARY_LAGS}
    out.update({f"r{b}": se[2 * b] / se[b] for b in (21, 42, 84)})
    out["skew"] = float(np.mean(z ** 3))
    out["kurt"] = float(np.mean(z ** 4) - 3.0)
    out["spec4_20"] = float(y2[:4].mean() / y2[4:20].mean())
    return out


def cosines(n: int, q: int) -> np.ndarray:
    """The (q, n) matrix sqrt(2/n) cos(pi j (t - 1/2) / n), j = 1..q, t = 1..n: orthonormal rows, each orthogonal to a
    constant, so the EWC variance ignores the mean."""
    if not 1 <= int(q) < n:
        raise ValueError(f"q must be in 1..{n - 1}, got {q}")
    t = (np.arange(1, n + 1) - 0.5) / n
    return math.sqrt(2.0 / n) * np.cos(np.pi * np.outer(np.arange(1, int(q) + 1), t))


def _ewc_rows(x: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """The EWC t of each row of x (rows, n) with the cosines `weights` (q, n)."""
    y = x @ weights.T
    lrv = (y * y).mean(axis=1)
    n = x.shape[1]
    with np.errstate(divide="ignore", invalid="ignore"):
        return math.sqrt(n) * x.mean(axis=1) / np.sqrt(lrv)


def ewc_t(d, q: int) -> float:
    """sqrt(n) mean(d) / sqrt(mean_j Y_j^2), Y_j = sqrt(2/n) sum_t cos(pi j (t - 1/2) / n) d_t (module docstring).

    t_q under iid normal d. By hand, d = [1, 2, 3, 4], q = 1: Y_1 = sqrt(1/2) (cos(pi/8) + 2 cos(3pi/8) - 3 cos(3pi/8)
    - 4 cos(pi/8)) = -2.230442, so t = 2 x 2.5 / 2.230442 = 2.2417076. A d whose cosine projections are all 0 (a
    constant) gives +-inf, or NaN at a zero mean.
    """
    d = series(d)
    return float(_ewc_rows(d[None, :], cosines(d.size, q))[0])


def ewc_bootstrap(d, q: int, block: int, draws: int = 9_999, *, seed, level: float = 0.95) -> dict:
    """The forecast test (module docstring): {"t", "se", "p", "ci", "draws", "q", "block"}.

    t is ewc_t(d, q); se = sqrt(mean_j Y_j^2 / n); p the one-sided moving-block bootstrap-t p-value of mean(d) <= 0
    against mean(d) > 0, (1 + #{t* >= t}) / (1 + draws); ci = (mean - t*_hi se, mean - t*_lo se), t*_lo and t*_hi the
    (1 - level)/2 and (1 + level)/2 quantiles of t* (numpy's linear quantile). d identically 0 has no EWC t (0/0):
    ValueError. The draws come in chunks from rng.random(), so for a seed p is chunk-independent and the CI is to
    rounding (module docstring, "Randomness").
    """
    d = series(d)
    n = d.size
    b = check_block(block, n)
    if b == n:
        raise ValueError("block must be shorter than d")
    if draws < 1:
        raise ValueError(f"draws must be >= 1, got {draws}")
    if not 0 < level < 1:
        raise ValueError(f"level must be in (0, 1), got {level}")
    weights = cosines(n, q)
    y = weights @ d
    lrv = float(np.mean(y * y))
    if lrv <= 0:
        raise ValueError("d has no low-frequency variation (a constant): the EWC t is not defined")
    se = math.sqrt(lrv / n)
    t = float(d.mean()) / se
    k = -(-n // b)
    starts_n = n - b + 1
    centre = float(np.convolve(d, np.ones(b), "valid").mean()) / b    # ~ E* mean* (exact but for the cut last block)
    offsets = np.arange(b)
    rng = np.random.default_rng(seed)
    stars = []
    for rows in chunks(draws, k * b):
        starts = (rng.random((rows, k)) * starts_n).astype(np.intp)
        resample = d[(starts[:, :, None] + offsets).reshape(rows, k * b)[:, :n]]
        stars.append(_ewc_rows(resample - centre, weights))
    stars = np.concatenate(stars)
    p = (1 + int(np.count_nonzero(stars >= t))) / (1 + draws)
    lo, hi = np.quantile(stars, [(1 - level) / 2, (1 + level) / 2])
    mean = float(d.mean())
    return {"t": t, "se": se, "p": p, "ci": (mean - float(hi) * se, mean - float(lo) * se), "draws": int(draws),
            "q": int(q), "block": b}


def chunks(draws: int, width: int):
    """Row counts that add up to `draws`, each chunk about CHUNK_CELLS values of `width` columns."""
    rows = max(1, CHUNK_CELLS // max(width, 1))
    for start in range(0, draws, rows):
        yield min(rows, draws - start)


def block_signflip(d, block: int, draws: int = 10_000, *, seed, alternative: str = "greater") -> float:
    """The block sign-flip p-value (module docstring): "greater" tests mean(d) <= 0 against mean(d) > 0.

    "less" counts draws at or below the observed mean (the same as "greater" on -d), "two-sided" draws whose |mean*|
    is at or above |mean_obs|. 10,000 draws on n = 2,495 take about 0.15 s at block 1 and a few ms at block 42.
    """
    d = series(d)
    b = check_block(block, d.size)
    if alternative not in ("greater", "less", "two-sided"):
        raise ValueError(f"alternative must be 'greater', 'less' or 'two-sided', got {alternative!r}")
    if draws < 1:
        raise ValueError(f"draws must be >= 1, got {draws}")
    n = d.size
    sums = np.add.reduceat(d, np.arange(0, n, b))           # block sums; the last block holds the remainder
    observed = float(sums.sum()) / n
    tie = TIE * float(np.abs(sums).sum()) / n
    rng = np.random.default_rng(seed)
    count = 0
    for rows in chunks(draws, sums.size):
        means = np.where(rng.random((rows, sums.size)) < 0.5, -1.0, 1.0) @ sums / n
        if alternative == "greater":
            count += int(np.count_nonzero(means >= observed - tie))
        elif alternative == "less":
            count += int(np.count_nonzero(means <= observed + tie))
        else:
            count += int(np.count_nonzero(np.abs(means) >= abs(observed) - tie))
    return (1 + count) / (1 + draws)


def nw_t(d, lags: int) -> float:
    """mean(d) / sqrt(LRV / n), LRV = gamma_0 + 2 sum_{j=1..lags} (1 - j/(lags+1)) gamma_j (Newey-West, Bartlett).

    gamma_j is the biased autocovariance (divided by n), so lags = 0 gives the plain t with the ddof=0 std,
    mean / (std(d, ddof=0) / sqrt(n)). When LRV <= 0 (a constant d): 0.0 if the mean is 0, else +-inf with the mean's
    sign (default taken 2026-11-09, owner can override). By hand, d = [1, 2, 3, 4], lags 1: gamma = [1.25, 0.3125],
    LRV = 1.25 + 2 x 0.5 x 0.3125 = 1.5625, t = 2.5 / sqrt(1.5625 / 4) = 4.0.
    """
    d = series(d)
    lags = int(lags)
    gamma = autocov(d, lags)
    weights = 1.0 - np.arange(1, lags + 1) / (lags + 1)
    lrv = float(gamma[0] + 2.0 * np.dot(weights, gamma[1:]))
    mean = float(d.mean())
    if lrv <= 0:
        return 0.0 if mean == 0 else math.copysign(math.inf, mean)
    return mean / math.sqrt(lrv / d.size)


def block_bootstrap_ci(d, block: int, draws: int = 10_000, *, seed, level: float = 0.95) -> tuple[float, float]:
    """The moving-block bootstrap percentile CI of mean(d).

    A resample is k = ceil(n / b) blocks d[s : s+b], each start s uniform on 0..n-b (with replacement), joined and cut
    to n values: the last block keeps its first r = n - (k-1) b values. The CI is the (1-level)/2 and (1+level)/2
    quantiles of the resample means, numpy's default ("linear") quantile. d identically 0 gives (0.0, 0.0).
    """
    d = series(d)
    b = check_block(block, d.size)
    if not 0 < level < 1:
        raise ValueError(f"level must be in (0, 1), got {level}")
    if draws < 1:
        raise ValueError(f"draws must be >= 1, got {draws}")
    n = d.size
    k = -(-n // b)
    r = n - (k - 1) * b
    full = np.convolve(d, np.ones(b), "valid")                     # the sum of d[s : s+b], s = 0..n-b
    last = np.convolve(d, np.ones(r), "valid")[:n - b + 1]         # the sum of d[s : s+r], same starts
    rng = np.random.default_rng(seed)
    means = []
    for rows in chunks(draws, k):
        starts = (rng.random((rows, k)) * (n - b + 1)).astype(np.intp)
        means.append((full[starts[:, :-1]].sum(axis=1) + last[starts[:, -1]]) / n)
    means = np.concatenate(means)
    lo, hi = np.quantile(means, [(1 - level) / 2, (1 + level) / 2])
    return float(lo), float(hi)


def holm(pvalues) -> np.ndarray:
    """Holm step-down adjusted p-values, in the input order.

    Sorted ascending, p_(i) becomes max over j <= i of min(1, (m - j + 1) p_(j)): monotone in the sort and capped at 1.
    By hand, [0.01, 0.04, 0.03, 0.005] gives [0.03, 0.06, 0.06, 0.02].
    """
    p = np.asarray(pvalues, dtype=float)
    if p.ndim != 1:
        raise ValueError(f"pvalues must be 1-D, got shape {p.shape}")
    m = p.size
    order = np.argsort(p, kind="stable")
    stepped = np.maximum.accumulate(np.minimum(1.0, (m - np.arange(m)) * p[order]))
    adjusted = np.empty(m)
    adjusted[order] = stepped
    return adjusted
