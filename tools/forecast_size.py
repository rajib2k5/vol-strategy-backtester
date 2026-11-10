"""The forecast test's size battery, its candidate screen, its matched-null threshold and the threshold's sensitivity
(milestone 4 fix passes 1 to 5): simulated data only.

Run:  uv run python tools/forecast_size.py battery RUNS OUT.json [--procs N]     (2,000 runs: the pre-registration's)
      uv run python tools/forecast_size.py match DEPENDENCE.json BATTERY.json OUT.json [--runs N] [--procs N]
      uv run python tools/forecast_size.py variants DEPENDENCE.json BATTERY.json MATCH.json OUT.json [--runs N]
                                                                                [--procs N]
      uv run python tools/forecast_size.py conditional DEPENDENCE.json OUT.json [--paths N] [--seed N] [--procs N]
      uv run python tools/forecast_size.py combinations DEPENDENCE.json BATTERY.json MATCH.json VARIANTS.json OUT.json
                                                                                [--procs N]
      uv run python tools/forecast_size.py sv-means                             (re-derive the S1-S3 centring constants)

battery. Each run draws one simulated, mean-0 daily d-series of length T = 2,495 (the scored window's n) from a null,
and runs the pre-registered test on it, volbt.analytics.inference.ewc_bootstrap(d, q=4, block=21, draws=999),
one-sided, on +d and on -d (a test of mean(d) <= 0 must hold its level whichever way the skew points), counting
p < a at each a of THRESHOLDS. On the same runs it screens the candidates the fix passes rejected (SCREEN, below),
so every figure the pre-registration states about them comes from this script's output. tools/prereg.py copies
OUT.json into the pre-registration's "size" and "screen" sections.

match (fix pass 2, item 9). DEPENDENCE.json is `tools/prereg.py dependence`'s output: twelve centred summaries of the
real 2002-2009 d-series (inference.dependence_summaries; nothing of its mean or its sign). The script simulates
PATHS paths of every null at that window's n, takes the same summaries on +d and -d, and weights each null-side by
its share of the ACCEPT nearest paths (ABC model choice: kurtosis on a log scale, each summary scaled by its pooled
robust SD, Euclidean distance). On the null-sides with weight it measures the test's size at each threshold on the
battery's seeds (from BATTERY.json) and on a second seed, and its power at a mean shift of SHIFT_SD standard
deviations of the run mean; falsifier (c) comes from the battery's power cell. The rule: the largest threshold
whose ABC-weighted size is at most SIZE_CAP on both seeds and whose ABC-weighted power is at least POWER_FLOOR
(default taken 2026-11-09, owner can override). tools/prereg.py copies OUT.json into the "matched" section.

variants (fix pass 3, item D1; review D's c1/run_variants.py, abc_variants.py and sizes.py, ported). The same rule
on other reasonable choices: the cap (0.05, 0.06), the acceptance share (0.25%, 0.5%, 2%, 5%), the summaries (without
spec4_20, without the kurtosis, without both), the scaling (pooled SD, pooled MAD), the kurtosis not logged, a prior
uniform over the three families rather than the 60 null-sides, a third size seed (THIRD_SEED) in place of or beside
the second, and VARIANT_SUMMARY_SEEDS (20 other summary seeds). For that it measures the size on all 60 null-sides
at the second and third seeds and the power at the power seed (2,000 runs each), checks that its weights and its
matched null-sides' second-seed sizes and power equal MATCH.json's, and reports, per variant, the matched null-sides,
the threshold the rule picks and the ABC-weighted size and power at each threshold, with the binomial Monte Carlo
SE of the registered weighted size. tools/prereg.py copies OUT.json into the "variants" section.

conditional (fix pass 3, item D2; review D's c2/cond.py and cond_analyse.py, ported). Each simulated path of every
null, on +d and -d, has a calibration segment of the real window's n (1,934), a gap of COND_GAP sessions, then a
scored segment of T: the twelve summaries come from the first, the test (999 draws) runs on the last. It compares,
at each acceptance share of COND_ACCEPTS, the rejection rate on the accepted paths (those whose calibration summaries
are nearest the real d's) with the ABC-weighted null-side average the match reports; and, within each null-side of
weight >= COND_HEAVY at 1%, the rate on its own nearest 10% of paths with its rate on all. --seed (fix pass 4, item
F3) names the draw's seed, COND_SEED by default. tools/prereg.py copies OUT.json into the "conditional" section.

combinations (fix pass 4, item F1; review E's c2/combos.py, ported). No test runs: the registered rule on every
combination of the variant table's own choices (CHOICES: the cap, the acceptance share, the summaries dropped, the
scaling, the kurtosis logged or not, the prior and the size seeds; 2,160 combinations), from the saved per-null-side
tables (BATTERY.json's rates on the battery's seeds, VARIANTS.json's on the second, third and power seeds) and the
match's summaries drawn again (SUMMARY_SEED, the same paths). It counts the threshold each picks: one choice changed
at a time (the variant table's rows, checked against VARIANTS.json), two at a time, and the full grid, and adds two
power-requirement rows on the registered weights (POWER_ROWS: an ABC-weighted power floor of 0.95, and the first
revision's falsifier (c) power of at least 0.9 in place of the ABC-weighted power). "band" is the lowest and the
highest threshold any combination picks; a pick is always one of THRESHOLDS, so the band's edges are edges of that
menu as much as of the choices. Fix pass 5 (item G2, review F claim 1): abc_weights logs the kurtosis only when it is
kept, so a combination that drops the kurtosis is the same rule with the kurtosis logged or not. rule_key names the
rule; the full grid also counts its distinct rules ("distinct_rules"), the two-at-a-time part the rules that are not
one choice at a time and not counted before ("distinct"), and two combinations of one rule must pick the same
threshold. "none_at_lowest" gives, for each combination that picks none, its size on each table, its cap, its power
and the floor at the lowest threshold, and which of size and power fails there (review F N1).
tools/prereg.py copies OUT.json into the "combinations" section.

Nothing here reads the store.

The nulls (30), each copied from the script that defined it, unchanged but for the interface (rng, runs, n):
  S1, S2, S3   the review's stochastic-volatility QLIKE differences (t5 returns; S/egv/m4a/adversarial/c10/
               size_sim.py), centred at their population means (SV_MEANS, below)
  S4           the review's MA(20) of Gaussian, right- or left-skewed lognormal innovations plus a share f of long
               memory (a sum of three AR(1)s): f in {0, 0.1, 0.15} at rhos .99/.997/.999 (c10/size_s4.py), and
               f in {0.1, 0.2, 0.3} at rhos .97/.985/.993 and .98/.99/.995 (Gaussian and left-skewed)
  orch         the orchestrator's: exp(s u) - E exp(s u) for u a unit-variance Gaussian AR(1) at rho 0.8865 ("ar1",
               the 2002-2009 d-series' lag-1 ACF) or the mean of three AR(1)s at 0.8865, 0.99, 0.998 ("long"),
               s in {0, 1, 1.5} (S/m4v/size/my_size.py)
The power cells (falsifier (c) of tests/test_inference.py): a unit-variance Gaussian AR(1) at rho 0.8865 shifted
so its long-run t is delta = 0, 2.5, 3 or 4: mean = delta sqrt((1 + rho) / (1 - rho) / T).

Seeds. battery: the data of cell k, chunk c (250 runs each) from np.random.default_rng([20261109, k, c]); the
bootstrap of run i on side s (0 for +d, 1 for -d) seeded [20261109, k, c, i, s]; a screened bootstrap or sign flip
appends its own tag to that list. match: the summaries' paths from default_rng([SUMMARY_SEED, k]); the second
seed's data from default_rng([SECOND_SEED, k, c]) and bootstraps [SECOND_SEED, k, c, i, s]; the run-mean SD from
default_rng([SD_SEED, k]); the power runs from default_rng([POWER_SEED, k, c]), bootstraps [POWER_SEED, k, c, i, s].
variants: the summaries of seed u from default_rng([u, k]); a size or power seed u's data from default_rng([u, k, c])
and bootstraps [u, k, c, i, s] (so its matched null-sides repeat the match's runs exactly). conditional: the data
from default_rng([seed, k, c]) and bootstraps [seed, k, c, i, s], seed COND_SEED unless --seed names another.
combinations: the summaries from default_rng([SUMMARY_SEED, k]), as the match's.
scipy is used for the filters and the t quantiles only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from scipy import stats
from scipy.signal import lfilter

T = 2495
Q, BLOCK, DRAWS = 4, 21, 999
NOMINAL = 0.05
THRESHOLDS = (0.05, 0.04, 0.03, 0.025, 0.02)
CHUNK = 250
SEED = 20261109
BAND = (0.025, 0.075)
STEP = 21                   # the monthly origins of the screen: every 21st session (non-overlapping targets)

# match (fix pass 2, item 9)
SUMMARY_SEED, SECOND_SEED, SD_SEED, POWER_SEED = 20261111, 20261110, 20261112, 20261113
PATHS = 1000                # simulated paths per null at the calibration window's n, each giving +d and -d
ACCEPT = 0.01               # the nearest share of all paths whose null-sides get the weight
SIZE_CAP = 0.055            # "at most about 0.05": the level plus 10%
POWER_FLOOR = 0.9           # ABC-weighted power at SHIFT_SD run-mean SDs
SHIFT_SD = 4.0
SD_RUNS = 4000
JOINT_ACF21_MAX = 0.10      # review A's joint check: ACF at lag 21 at most this
JOINT_KEYS = ("r42", "r84", "skew", "kurt", "acf21")
RHO = 0.8865                # the 2002-2009 d-series' lag-1 ACF: the orchestrator's AR(1) and the power cells

# variants (fix pass 3, item D1)
THIRD_SEED = 41001
VARIANT_SUMMARY_SEEDS = tuple(range(31001, 31021))

# conditional (fix pass 3, item D2)
COND_SEED, COND_PATHS, COND_GAP = 20261114, 3000, 21
COND_ACCEPTS = (0.0025, 0.005, 0.01, 0.02, 0.05)
COND_HEAVY = 0.03

# combinations (fix pass 4, item F1): each modelling choice of the variant table and the values it takes
CHOICES = {"cap": (0.05, 0.055, 0.06), "accept": (0.0025, 0.005, 0.01, 0.02, 0.05),
           "drop": ((), ("spec4_20",), ("kurt",), ("spec4_20", "kurt")), "scale": ("iqr", "sd", "mad"),
           "logkurt": (True, False), "prior": ("sides", "family"), "seeds": ("second", "third", "all3")}
REGISTERED_CHOICE = {"cap": SIZE_CAP, "accept": ACCEPT, "drop": (), "scale": "iqr", "logkurt": True,
                     "prior": "sides", "seeds": "second"}
# the variant table's rows (run_variants' specs) as one changed choice each
VARIANT_CHOICE = {"cap 0.05": ("cap", 0.05), "cap 0.06": ("cap", 0.06), "accept 0.50%": ("accept", 0.005),
                  "accept 0.25%": ("accept", 0.0025), "accept 2.00%": ("accept", 0.02),
                  "accept 5.00%": ("accept", 0.05), "drop spec4_20": ("drop", ("spec4_20",)),
                  "drop kurt": ("drop", ("kurt",)), "drop spec4_20 and kurt": ("drop", ("spec4_20", "kurt")),
                  "scale: pooled SD": ("scale", "sd"), "scale: pooled MAD": ("scale", "mad"),
                  "kurtosis not logged": ("logkurt", False), "prior uniform over the 3 families": ("prior", "family"),
                  "third size seed replaces the second": ("seeds", "third"),
                  "three size seeds, all must pass": ("seeds", "all3")}
POWER_FLOOR_HIGH = 0.95     # a power-requirement row: the ABC-weighted power floor at 0.95
FALSIFIER_FLOOR = 0.9       # the first revision's requirement: falsifier (c) power of at least 0.9

# The population means of the S1-S3 d (`sv-means`: 12 x 25 batches of 200 runs, 149.7 million simulated days each;
# their batch-to-batch SE is at most 0.00015, the run mean's SD 0.018 to 0.032).
SV_MEANS = {"S1": 0.13660591000563765, "S2": 0.0621875963609275, "S3": 0.09889911197384527}

# --- S1, S2, S3 ---------------------------------------------------------------------------------------------------
H = 21
RHOS_SV = (0.6, 0.96, 0.997)
SDS = (0.25, 0.30, 0.35)
NU = 5


def _simulate(rng, runs, n):
    x = np.zeros((runs, n))
    for rho, sd in zip(RHOS_SV, SDS):
        s_eps = sd * math.sqrt(1 - rho * rho)
        eps = rng.standard_normal((runs, n)) * s_eps
        x0 = rng.standard_normal(runs) * sd
        comp, _ = lfilter([1.0], [1.0, -rho], eps, axis=1, zi=(rho * x0)[:, None])
        x += comp
    h = 1e-4 * np.exp(x - 0.5 * sum(s * s for s in SDS))
    z = rng.standard_t(NU, (runs, n)) / math.sqrt(NU / (NU - 2))
    return h, np.sqrt(h) * z


def _qlike(y, yhat):
    ratio = y / yhat
    return ratio - np.log(ratio) - 1.0


def sv_series(rng, runs, n_t, scenario):
    """(runs, n_t) uncentred d of scenario S1, S2 or S3."""
    burn = 300
    n = burn + 22 + n_t + H
    _, r = _simulate(rng, runs, n)
    v = r * r
    c = np.cumsum(np.concatenate([np.zeros((runs, 1)), v], axis=1), axis=1)
    idx = burn + 22 + np.arange(n_t)
    g = (c[:, idx + 1] - c[:, idx - 21]) / 22
    y = (c[:, idx + 1 + H] - c[:, idx + 1]) / H
    if scenario == "S1":
        c1 = 0.8
        f1 = 1 / c1 + math.log(c1)
        lo, hi = 1.0001, 3.0
        for _ in range(200):
            mid = (lo + hi) / 2
            if 1 / mid + math.log(mid) < f1:
                lo = mid
            else:
                hi = mid
        c2 = (lo + hi) / 2
        return _qlike(y, c1 * g) - _qlike(y, c2 * g)
    if scenario == "S3":
        g252 = (c[:, idx + 1] - c[:, idx - 251]) / 252
        g2 = 0.55 * g + 0.45 * g252
        return _qlike(y, g) - _qlike(y, g2)
    lam = 0.94
    e = lfilter([1 - lam], [1.0, -lam], v, axis=1, zi=(lam * v[:, :50].mean(axis=1))[:, None])[0]
    g2 = e[:, idx]
    return _qlike(y, g) - _qlike(y, g2)


# --- S4 ------------------------------------------------------------------------------------------------------------

def s4(rng, runs, f, kind, rhos=(0.99, 0.997, 0.999), sigma=1.2, iid=0.08, n_t=T):
    n = n_t + 20
    if kind == "gauss":
        e = rng.standard_normal((runs, n))
    else:
        e = rng.lognormal(0.0, sigma, (runs, n))
        e = (e - math.exp(sigma * sigma / 2)) / math.sqrt((math.exp(sigma * sigma) - 1) * math.exp(sigma * sigma))
        if kind == "left":
            e = -e
    ma = lfilter(np.ones(21) / math.sqrt(21), [1.0], e, axis=1)[:, 20:]
    noise = math.sqrt(1 - iid) * ma + math.sqrt(iid) * rng.standard_normal((runs, n_t))
    lm = np.zeros((runs, n_t))
    for rho in rhos:
        x0 = rng.standard_normal(runs)
        eps = rng.standard_normal((runs, n_t)) * math.sqrt(1 - rho * rho)
        lm += lfilter([1.0], [1.0, -rho], eps, axis=1, zi=(rho * x0)[:, None])[0] / math.sqrt(len(rhos))
    return math.sqrt(1 - f) * noise + math.sqrt(f) * lm


# --- the orchestrator's ----------------------------------------------------------------------------------------------

def _ar(rng, rho, runs, n_t=T):
    e = rng.standard_normal((runs, n_t + 500)) * math.sqrt(1 - rho * rho)
    return lfilter([1.0], [1.0, -rho], e, axis=1)[:, 500:]


def orch(rng, runs, name, s, n_t=T):
    rhos = (RHO,) if name == "ar1" else (RHO, 0.99, 0.998)
    u = sum(_ar(rng, r, runs, n_t) for r in rhos) / math.sqrt(len(rhos))
    return np.exp(s * u) - math.exp(s * s / 2) if s else u


# --- the battery -----------------------------------------------------------------------------------------------------

def battery() -> list[dict]:
    """The 30 nulls: {name, family, args}."""
    out = [{"name": s, "family": "sv", "args": {"scenario": s}} for s in ("S1", "S2", "S3")]
    for f in (0.0, 0.1, 0.15):
        for kind in ("gauss", "right", "left"):
            out.append({"name": f"S4 f={f} {kind} rhos=.99/.997/.999", "family": "s4",
                        "args": {"f": f, "kind": kind, "rhos": (0.99, 0.997, 0.999)}})
    for rhos in ((0.97, 0.985, 0.993), (0.98, 0.99, 0.995)):
        for f in (0.1, 0.2, 0.3):
            for kind in ("gauss", "left"):
                out.append({"name": f"S4 f={f} {kind} rhos={'/'.join(str(r)[1:] for r in rhos)}", "family": "s4",
                            "args": {"f": f, "kind": kind, "rhos": rhos}})
    for name in ("ar1", "long"):
        for s in (0.0, 1.0, 1.5):
            out.append({"name": f"orch {name} s={s}", "family": "orch", "args": {"name": name, "s": s}})
    return out


def cells() -> list[dict]:
    out = [dict(n, kind="size") for n in battery()]
    out += [{"name": f"power delta={d}", "family": "power", "args": {"delta": d}, "kind": "power"}
            for d in (0.0, 2.5, 3.0, 4.0)]
    return out


def generate(null: dict, rng, runs: int, n_t: int = T) -> np.ndarray:
    """(runs, n_t) mean-0 d of a null (or a power cell, shifted by its delta)."""
    family, a = null["family"], null["args"]
    if family == "power":
        return orch(rng, runs, "ar1", 0.0, n_t) + a["delta"] * math.sqrt((1 + RHO) / (1 - RHO) / n_t)
    if family == "sv":
        return sv_series(rng, runs, n_t, a["scenario"]) - SV_MEANS[a["scenario"]]
    if family == "s4":
        return s4(rng, runs, a["f"], a["kind"], a["rhos"], n_t=n_t)
    return orch(rng, runs, a["name"], a["s"], n_t)


def side_name(side: int) -> str:
    return "+d" if side == 0 else "-d"


# --- the candidate screen (fix pass 2, item 13) ------------------------------------------------------------------------

def autocov_all(x: np.ndarray) -> np.ndarray:
    """(runs, n) biased autocovariances gamma_0..gamma_{n-1} (divided by n), by FFT."""
    n = x.shape[1]
    xc = x - x.mean(axis=1, keepdims=True)
    m = 1 << (2 * n - 1).bit_length()
    f = np.fft.rfft(xc, m, axis=1)
    return np.fft.irfft(f * np.conj(f), m, axis=1)[:, :n] / n


def fixed_b_t(x: np.ndarray, b: float) -> np.ndarray:
    """The Newey-West (Bartlett) t of each row's mean with bandwidth M = round(b n) (Kiefer and Vogelsang 2005)."""
    n = x.shape[1]
    big_m = max(1, int(round(b * n)))
    gam = autocov_all(x)
    lrv = gam[:, 0] + 2.0 * gam[:, 1:big_m] @ (1.0 - np.arange(1, big_m) / big_m)
    return x.mean(axis=1) / np.sqrt(np.maximum(lrv, 1e-300) / n)


def fixed_b_cv(n: int, b: float, reps: int = 40_000) -> float:
    """The 95% quantile of fixed_b_t under iid N(0, 1) of length n, simulated (seed [99, n, 1000 b])."""
    rng = np.random.default_rng([99, n, int(b * 1000)])
    values = np.concatenate([fixed_b_t(rng.standard_normal((2000, n)), b) for _ in range(reps // 2000)])
    return float(np.quantile(values, 1 - NOMINAL))


def ewc_rows(x: np.ndarray, q: int) -> np.ndarray:
    from volbt.analytics import inference as inf

    return inf._ewc_rows(x, inf.cosines(x.shape[1], q))


# name -> description; each is one-sided at a nominal 0.05
SCREEN = {
    "ewc_t_q2": "the plain EWC t, q = 2, against t_2",
    "ewc_t_q3": "the plain EWC t, q = 3, against t_3",
    "ewc_t_q4": "the plain EWC t, q = 4, against t_4",
    "fixed_b_0.5": "the fixed-b Newey-West t, b = 0.5, against its simulated iid-normal 95% quantile",
    "fixed_b_1": "the fixed-b Newey-West t, b = 1, against its simulated iid-normal 95% quantile",
    "signflip_168": "the block sign flip at block 168 (inference.block_signflip, 999 draws)",
    "ewc_boot_q3": "the EWC bootstrap-t at q = 3, block 21 (inference.ewc_bootstrap, 999 draws)",
    "monthly_ewc_t_q4": "the EWC t, q = 4, on the 119 monthly origins (every 21st session), against t_4",
    "monthly_fixed_b_1": "the fixed-b t, b = 1, on the monthly origins, against its simulated 95% quantile",
    "monthly_ewc_boot_q4_b1": "the EWC bootstrap-t, q = 4, block 1, on the monthly origins (999 draws)",
    "monthly_ewc_boot_q4_b3": "the EWC bootstrap-t, q = 4, block 3, on the monthly origins (999 draws)",
}


def screen_rejects(x: np.ndarray, k: int, chunk: int, cvs: dict) -> dict[str, list[int]]:
    """{candidate: [rejections on +d, on -d]} over the rows of x (the battery's runs of one chunk)."""
    from volbt.analytics import inference as inf

    out = {}
    monthly = x[:, ::STEP]
    closed = {"ewc_t_q2": ewc_rows(x, 2), "ewc_t_q3": ewc_rows(x, 3), "ewc_t_q4": ewc_rows(x, 4),
              "fixed_b_0.5": fixed_b_t(x, 0.5), "fixed_b_1": fixed_b_t(x, 1.0),
              "monthly_ewc_t_q4": ewc_rows(monthly, 4), "monthly_fixed_b_1": fixed_b_t(monthly, 1.0)}
    for name, t in closed.items():
        cv = cvs[name]
        out[name] = [int(np.count_nonzero(t > cv)), int(np.count_nonzero(-t > cv))]
    seeded = {"signflip_168": 1, "ewc_boot_q3": 3, "monthly_ewc_boot_q4_b1": 4, "monthly_ewc_boot_q4_b3": 5}
    for name in seeded:
        out[name] = [0, 0]
    for i, row in enumerate(x):
        for side, d in enumerate((row, -row)):
            base = [SEED, k, chunk, i, side]
            m = d[::STEP]
            p = {"signflip_168": inf.block_signflip(d, 168, DRAWS, seed=base + [1]),
                 "ewc_boot_q3": inf.ewc_bootstrap(d, 3, BLOCK, DRAWS, seed=base + [3])["p"],
                 "monthly_ewc_boot_q4_b1": inf.ewc_bootstrap(m, 4, 1, DRAWS, seed=base + [4])["p"],
                 "monthly_ewc_boot_q4_b3": inf.ewc_bootstrap(m, 4, 3, DRAWS, seed=base + [5])["p"]}
            for name, value in p.items():
                out[name][side] += int(value < NOMINAL)
    return out


def screen_cvs() -> dict[str, float]:
    n_month = len(range(0, T, STEP))
    return {"ewc_t_q2": float(stats.t.ppf(0.95, 2)), "ewc_t_q3": float(stats.t.ppf(0.95, 3)),
            "ewc_t_q4": float(stats.t.ppf(0.95, 4)), "fixed_b_0.5": fixed_b_cv(T, 0.5), "fixed_b_1": fixed_b_cv(T, 1.0),
            "monthly_ewc_t_q4": float(stats.t.ppf(0.95, 4)), "monthly_fixed_b_1": fixed_b_cv(n_month, 1.0)}


def battery_task(args):
    from volbt.analytics import inference as inf

    k, chunk, runs, cvs = args
    x = generate(cells()[k], np.random.default_rng([SEED, k, chunk]), runs)
    test = {a: [0, 0] for a in THRESHOLDS}
    for i, row in enumerate(x):
        for side, d in enumerate((row, -row)):
            p = inf.ewc_bootstrap(d, Q, BLOCK, DRAWS, seed=[SEED, k, chunk, i, side])["p"]
            for a in THRESHOLDS:
                test[a][side] += int(p < a)
    return k, chunk, test, screen_rejects(x, k, chunk, cvs), ewc_rows(x, 4)


def summarise(rates: dict[str, list[float]], kinds: dict[str, str]) -> dict:
    """worst high and low, in-band count over the size cells' 60 null-sides; power by delta."""
    size = [(v, name, side_name(s)) for name, pair in rates.items() if kinds[name] == "size"
            for s, v in enumerate(pair)]
    high, low = max(size), min(size)
    return {"worst": {"high": {"rate": high[0], "null": high[1], "side": high[2]},
                      "low": {"rate": low[0], "null": low[1], "side": low[2]}},
            "in_band": f"{sum(BAND[0] <= v <= BAND[1] for v, _, _ in size)}/{len(size)}",
            "power": {name.split("=")[1]: pair[0] for name, pair in rates.items() if kinds[name] == "power"}}


def minmax_cv(t4: dict[str, np.ndarray], kinds: dict[str, str]) -> dict:
    """The EWC t (q = 4) at the critical value that brings the worst null-side nearest the band: a grid of 161 values
    from 0.9 to 2.5 times t_4's 95% quantile, the first with the smallest worst distance outside the band."""
    cv0 = float(stats.t.ppf(0.95, 4))
    best = None
    for cv in np.linspace(cv0 * 0.9, cv0 * 2.5, 161):
        rates = {name: [float(np.mean(t > cv)), float(np.mean(-t > cv))] for name, t in t4.items()}
        dist = max(max(0.0, v - BAND[1], BAND[0] - v) for name, pair in rates.items() if kinds[name] == "size"
                   for v in pair)
        if best is None or dist < best[0]:
            best = (dist, float(cv), rates)
    return {"description": "the plain EWC t, q = 4, against the min-max critical value on these nulls",
            "cv": round(best[1], 4), "rates": best[2], **summarise(best[2], kinds)}


def run_battery(runs: int, procs: int) -> dict:
    from volbt.analytics import inference as inf

    cs = cells()
    kinds = {c["name"]: c["kind"] for c in cs}
    cvs = screen_cvs()
    jobs = [(k, c, min(CHUNK, runs - c * CHUNK), cvs) for k in range(len(cs)) for c in range(-(-runs // CHUNK))]
    test = {k: {a: [0, 0] for a in THRESHOLDS} for k in range(len(cs))}
    screen = {k: {name: [0, 0] for name in SCREEN} for k in range(len(cs))}
    t4 = {k: {} for k in range(len(cs))}
    started = time.time()
    with Pool(procs) as pool:
        for k, chunk, counts, rejects, t in pool.imap_unordered(battery_task, jobs):
            for a in THRESHOLDS:
                for side in (0, 1):
                    test[k][a][side] += counts[a][side]
            for name in SCREEN:
                for side in (0, 1):
                    screen[k][name][side] += rejects[name][side]
            t4[k][chunk] = t
    by_threshold = {}
    for a in THRESHOLDS:
        rates = {cs[k]["name"]: [test[k][a][0] / runs, test[k][a][1] / runs] for k in range(len(cs))}
        by_threshold[str(a)] = {"rates": rates, **summarise(rates, kinds)}
    candidates = {}
    for name, description in SCREEN.items():
        rates = {cs[k]["name"]: [screen[k][name][0] / runs, screen[k][name][1] / runs] for k in range(len(cs))}
        candidates[name] = {"description": description, "cv": round(cvs[name], 4) if name in cvs else None,
                            "rates": rates, **summarise(rates, kinds)}
    candidates["ewc_t_q4_minmax"] = minmax_cv(
        {cs[k]["name"]: np.concatenate([t4[k][c] for c in sorted(t4[k])]) for k in range(len(cs))}, kinds)
    return {"test": f"volbt.analytics.inference.ewc_bootstrap(d, q={Q}, block={BLOCK}, draws={DRAWS}), one-sided",
            "q": Q, "block": BLOCK, "draws": DRAWS, "power_rho": RHO, "thresholds": list(THRESHOLDS),
            "inference_sha256": hashlib.sha256(Path(inf.__file__).read_bytes()).hexdigest(),
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "runs": runs, "T": T, "band": list(BAND), "mc_se_at_0.05": round(math.sqrt(0.05 * 0.95 / runs), 4),
            "data_seed": f"np.random.default_rng([{SEED}, cell, chunk]), chunks of {CHUNK} runs",
            "bootstrap_seed": f"[{SEED}, cell, chunk, run, side]",
            "screen_seeds": "the battery's data; bootstrap or sign-flip seeds [20261109, cell, chunk, run, side, tag], "
                            "tag 1 sign flip, 3 EWC bootstrap q 3, 4 and 5 the monthly bootstraps at block 1 and 3",
            "seconds": round(time.time() - started, 1), "by_threshold": by_threshold, "screen": candidates}


# --- match (fix pass 2, item 9) ------------------------------------------------------------------------------------------

def summary_task(args):
    from volbt.analytics import inference as inf

    k, paths, n, seed = args if len(args) == 4 else (*args, SUMMARY_SEED)
    x = generate(battery()[k], np.random.default_rng([seed, k]), paths, n)
    out = []
    for side in (0, 1):
        rows = [inf.dependence_summaries(row if side == 0 else -row) for row in x]
        out.append(np.array([[r[key] for key in inf.SUMMARY_KEYS] for r in rows]))
    return k, out


def transform(matrix: np.ndarray) -> np.ndarray:
    """The summaries as matched: excess kurtosis on a log scale, log(kurt + 3), the rest as they are."""
    from volbt.analytics.inference import SUMMARY_KEYS

    out = np.array(matrix, dtype=float, copy=True)
    j = SUMMARY_KEYS.index("kurt")
    out[..., j] = np.log(out[..., j] + 3.0)
    return out


def abc(real: dict, summaries: dict[tuple[int, int], np.ndarray]) -> dict:
    """ABC weights over the null-sides, and per null-side medians, RMS robust z and the joint share."""
    from volbt.analytics.inference import SUMMARY_KEYS

    keys = list(SUMMARY_KEYS)
    rv = transform(np.array([real[key] for key in keys]))
    order = sorted(summaries)
    pooled = np.vstack([transform(summaries[ks]) for ks in order])
    labels = [ks for ks in order for _ in range(len(summaries[ks]))]
    q75, q25 = np.percentile(pooled, [75, 25], axis=0)
    scale = (q75 - q25) / 1.349
    dist = np.sqrt((((pooled - rv) / scale) ** 2).sum(axis=1))
    accepted = int(round(ACCEPT * len(dist)))
    nearest = np.argsort(dist, kind="stable")[:accepted]
    counts = {ks: 0 for ks in order}
    for i in nearest:
        counts[labels[i]] += 1
    sides = {}
    for ks in order:
        raw = summaries[ks]
        x = transform(raw)
        med = np.median(x, axis=0)
        iqr = (np.percentile(x, 75, axis=0) - np.percentile(x, 25, axis=0)) / 1.349
        z = (rv - med) / iqr
        col = {key: raw[:, j] for j, key in enumerate(keys)}
        joint = ((col["r42"] >= real["r42"]) & (col["r84"] >= real["r84"]) & (col["skew"] >= real["skew"])
                 & (col["kurt"] >= real["kurt"]) & (col["acf21"] <= JOINT_ACF21_MAX))
        sides[ks] = {"weight": counts[ks] / accepted, "count": counts[ks], "rms_z": float(np.sqrt(np.mean(z ** 2))),
                     "median": {key: float(np.median(raw[:, j])) for j, key in enumerate(keys)},
                     "joint_share": float(np.mean(joint))}
    return {"scale": {key: float(v) for key, v in zip(keys, scale)}, "accepted": accepted, "paths": len(dist),
            "sides": sides}


def sd_task(args):
    k, = args
    rng = np.random.default_rng([SD_SEED, k])
    means = np.concatenate([generate(battery()[k], rng, 500).mean(axis=1) for _ in range(SD_RUNS // 500)])
    return k, float(means.std(ddof=1))


def test_task(args):
    """Rejections at each threshold of one matched null-side's chunk: (key, chunk, {a: count})."""
    from volbt.analytics import inference as inf

    seed, k, side, chunk, runs, shift = args
    x = generate(battery()[k], np.random.default_rng([seed, k, chunk]), runs)
    counts = {a: 0 for a in THRESHOLDS}
    for i, row in enumerate(x):
        d = (row if side == 0 else -row) + shift
        p = inf.ewc_bootstrap(d, Q, BLOCK, DRAWS, seed=[seed, k, chunk, i, side])["p"]
        for a in THRESHOLDS:
            counts[a] += int(p < a)
    return (seed, k, side), counts


def run_match(dependence: dict, battery_json: dict, battery_sha256: str, runs: int, procs: int) -> dict:
    from volbt.analytics import inference as inf

    real = dependence["summaries"]
    n = int(dependence["window"]["n"])
    nulls = battery()
    started = time.time()
    with Pool(procs) as pool:
        summaries = {}
        for k, (plus, minus) in pool.imap_unordered(summary_task, [(k, PATHS, n) for k in range(len(nulls))]):
            summaries[(k, 0)], summaries[(k, 1)] = plus, minus
        weights = abc(real, summaries)
        matched = [ks for ks, v in weights["sides"].items() if v["count"] > 0]
        sd = dict(pool.imap_unordered(sd_task, sorted({(k,) for k, _ in matched})))
        jobs = []
        for k, side in matched:
            for chunk in range(-(-runs // CHUNK)):
                size = min(CHUNK, runs - chunk * CHUNK)
                jobs.append((SECOND_SEED, k, side, chunk, size, 0.0))
                jobs.append((POWER_SEED, k, side, chunk, size, SHIFT_SD * sd[k]))
        totals = {}
        for key, counts in pool.imap_unordered(test_task, jobs):
            acc = totals.setdefault(key, {a: 0 for a in THRESHOLDS})
            for a in THRESHOLDS:
                acc[a] += counts[a]

    def label(ks):
        return f"{nulls[ks[0]]['name']} {side_name(ks[1])}"

    battery_rates = battery_json["by_threshold"]
    table, per_side = [], []
    w = {ks: weights["sides"][ks]["weight"] for ks in matched}
    total_w = sum(w.values())
    for ks in matched:
        name = nulls[ks[0]]["name"]
        per_side.append({"null_side": label(ks), "weight": w[ks], "sd_run_mean": sd[ks[0]],
                         "size_battery_seed": {str(a): battery_rates[str(a)]["rates"][name][ks[1]] for a in THRESHOLDS},
                         "size_second_seed": {str(a): totals[(SECOND_SEED, *ks)][a] / runs for a in THRESHOLDS},
                         "power": {str(a): totals[(POWER_SEED, *ks)][a] / runs for a in THRESHOLDS}})
    falsifier = {str(a): battery_rates[str(a)]["rates"]["power delta=4.0"][0] for a in THRESHOLDS}
    chosen = None
    for a in THRESHOLDS:
        row = {"threshold": a}
        for seed_key in ("size_battery_seed", "size_second_seed"):
            row[f"abc_{seed_key}"] = sum(s["weight"] * s[seed_key][str(a)] for s in per_side) / total_w
            worst = max(per_side, key=lambda s: s[seed_key][str(a)])
            row[f"worst_matched_{seed_key}"] = {"rate": worst[seed_key][str(a)], "null_side": worst["null_side"]}
        row["abc_power"] = sum(s["weight"] * s["power"][str(a)] for s in per_side) / total_w
        row["falsifier_c_power"] = falsifier[str(a)]
        row["passes"] = bool(max(row["abc_size_battery_seed"], row["abc_size_second_seed"]) <= SIZE_CAP
                             and row["abc_power"] >= POWER_FLOOR)
        table.append(row)
        if chosen is None and row["passes"]:
            chosen = a
    if chosen is None:
        raise SystemExit("no threshold passes the rule: none can be registered")
    sides = []
    for ks, v in sorted(weights["sides"].items(), key=lambda item: item[1]["rms_z"]):
        name = nulls[ks[0]]["name"]
        sides.append({"null_side": label(ks), "weight": v["weight"], "rms_z": v["rms_z"],
                      "joint_share": v["joint_share"], "median": v["median"],
                      "size": {str(a): battery_rates[str(a)]["rates"][name][ks[1]] for a in (NOMINAL, chosen)}})
    same_sign = [s for s in sides if math.copysign(1.0, s["median"]["skew"]) == math.copysign(1.0, real["skew"])]

    def worst_of(group, a):
        s = max(group, key=lambda s: s["size"][str(a)])
        return {"rate": s["size"][str(a)], "null_side": s["null_side"], "median_skew": s["median"]["skew"]}

    return {"script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "inference_sha256": hashlib.sha256(Path(inf.__file__).read_bytes()).hexdigest(),
            "battery_sha256": battery_sha256, "real": real, "real_window": dependence["window"],
            "method": {"summaries": list(inf.SUMMARY_KEYS),
                       "transform": "excess kurtosis as log(kurt + 3); the other eleven as they are",
                       "paths_per_null": PATHS, "n": n, "sides": "each path on +d and on -d",
                       "scale": "each summary over its pooled robust SD, IQR / 1.349 over every path",
                       "distance": "Euclidean", "accept": ACCEPT, "accepted": weights["accepted"],
                       "paths": weights["paths"],
                       "weight": "a null-side's share of the accepted paths (ABC model choice, uniform prior)"},
            "seeds": {"summaries": f"default_rng([{SUMMARY_SEED}, cell])",
                      "battery_seed": "the battery's (BATTERY.json)",
                      "second_seed": f"data default_rng([{SECOND_SEED}, cell, chunk]), bootstrap "
                                     f"[{SECOND_SEED}, cell, chunk, run, side]",
                      "sd_run_mean": f"default_rng([{SD_SEED}, cell]), {SD_RUNS} runs at T = {T}",
                      "power": f"data default_rng([{POWER_SEED}, cell, chunk]), bootstrap "
                               f"[{POWER_SEED}, cell, chunk, run, side]"},
            "runs": runs, "scale": weights["scale"],
            "rule": f"the largest threshold of {list(THRESHOLDS)} whose ABC-weighted size is at most {SIZE_CAP} on "
                    f"both seeds and whose ABC-weighted power at {SHIFT_SD:g} SD(run mean) is at least {POWER_FLOOR}",
            "size_cap": SIZE_CAP, "power_floor": POWER_FLOOR, "shift_sd": SHIFT_SD, "threshold": chosen,
            "table": table, "matched": per_side, "null_sides": sides,
            "joint": {"rule": f"r42 >= real, r84 >= real, skew >= real, kurt >= real and acf21 <= {JOINT_ACF21_MAX}",
                      "summaries": list(JOINT_KEYS), "max_share": max(s["joint_share"] for s in sides),
                      "max_null_side": max(sides, key=lambda s: s["joint_share"])["null_side"]},
            "worst": {"overall": {str(a): worst_of(sides, a) for a in (NOMINAL, chosen)},
                      "same_skew_sign": {str(a): worst_of(same_sign, a) for a in (NOMINAL, chosen)}},
            "seconds": round(time.time() - started, 1)}


# --- variants (fix pass 3, item D1) ---------------------------------------------------------------------------------

def abc_weights(real: dict, summaries: dict[tuple[int, int], np.ndarray], keys=None, accept: float = ACCEPT,
                scale: str = "iqr", logkurt: bool = True) -> dict[tuple[int, int], float]:
    """{null-side: weight} of the ABC choice under a variant: `keys` (a subset of SUMMARY_KEYS, all by default), the
    acceptance share, the scale ("iqr": IQR / 1.349, "sd": the pooled SD, "mad": 1.4826 x the pooled median absolute
    deviation) and the kurtosis on a log scale or not. The defaults are abc()'s, and give its weights."""
    from volbt.analytics.inference import SUMMARY_KEYS

    keys = list(keys or SUMMARY_KEYS)
    idx = [list(SUMMARY_KEYS).index(key) for key in keys]

    def tr(matrix):
        out = np.array(matrix, dtype=float)[..., idx].copy()
        if logkurt and "kurt" in keys:
            j = keys.index("kurt")
            out[..., j] = np.log(out[..., j] + 3.0)
        return out

    rv = tr(np.array([real[key] for key in SUMMARY_KEYS]))
    order = sorted(summaries)
    pooled = np.vstack([tr(summaries[ks]) for ks in order])
    labels = np.array([i for i, ks in enumerate(order) for _ in range(len(summaries[ks]))])
    if scale == "iqr":
        q75, q25 = np.percentile(pooled, [75, 25], axis=0)
        sc = (q75 - q25) / 1.349
    elif scale == "sd":
        sc = pooled.std(axis=0)
    elif scale == "mad":
        sc = 1.4826 * np.median(np.abs(pooled - np.median(pooled, axis=0)), axis=0)
    else:
        raise ValueError(f"scale {scale!r}")
    dist = np.sqrt((((pooled - rv) / sc) ** 2).sum(axis=1))
    m = int(round(accept * len(dist)))
    counts = np.bincount(labels[np.argsort(dist, kind="stable")[:m]], minlength=len(order))
    return {order[i]: counts[i] / m for i in range(len(order)) if counts[i] > 0}


def family_prior(weights: dict[tuple[int, int], float]) -> dict[tuple[int, int], float]:
    """The weights under a prior uniform over the three families (sv, s4, orch) instead of the 60 null-sides: each
    divided by its family's number of nulls, then renormalised."""
    family = [n["family"] for n in battery()]
    size = {f: family.count(f) for f in set(family)}
    out = {ks: v / size[family[ks[0]]] for ks, v in weights.items()}
    total = sum(out.values())
    return {ks: v / total for ks, v in out.items()}


def choose(weights: dict, size_tables: list[dict], power_table: dict, cap: float = SIZE_CAP,
           floor: float = POWER_FLOOR) -> dict:
    """The registered rule on `weights`: the largest threshold whose weighted size is at most `cap` on every table and
    whose weighted power is at least `floor`. {threshold (None if none passes), size [per table], power, passes}."""
    size = [{str(a): sum(v * tab[ks][str(a)] for ks, v in weights.items()) for a in THRESHOLDS} for tab in size_tables]
    power = {str(a): sum(v * power_table[ks][str(a)] for ks, v in weights.items()) for a in THRESHOLDS}
    passes = {str(a): bool(max(tab[str(a)] for tab in size) <= cap and power[str(a)] >= floor) for a in THRESHOLDS}
    chosen = next((a for a in THRESHOLDS if passes[str(a)]), None)
    return {"threshold": chosen, "size": size, "power": power, "passes": passes}


def sides_task(args):
    """Rejections at each threshold of one null's chunk, on +d and on -d, with a mean shift: (seed, k, counts)."""
    from volbt.analytics import inference as inf

    seed, k, chunk, runs, shift = args
    x = generate(battery()[k], np.random.default_rng([seed, k, chunk]), runs)
    counts = {side: {a: 0 for a in THRESHOLDS} for side in (0, 1)}
    for i, row in enumerate(x):
        for side in (0, 1):
            d = (row if side == 0 else -row) + shift
            p = inf.ewc_bootstrap(d, Q, BLOCK, DRAWS, seed=[seed, k, chunk, i, side])["p"]
            for a in THRESHOLDS:
                counts[side][a] += int(p < a)
    return seed, k, counts


def run_variants(dependence: dict, battery_json: dict, battery_sha256: str, match_json: dict, match_sha256: str,
                 runs: int, procs: int) -> dict:
    from volbt.analytics import inference as inf

    real, n = dependence["summaries"], int(dependence["window"]["n"])
    nulls = battery()
    started = time.time()

    def label(ks):
        return f"{nulls[ks[0]]['name']} {side_name(ks[1])}"

    with Pool(procs) as pool:
        summ = {}
        jobs = [(k, PATHS, n, seed) for seed in (SUMMARY_SEED, *VARIANT_SUMMARY_SEEDS) for k in range(len(nulls))]
        for (k, (plus, minus)), (_, _, _, seed) in zip(pool.imap(summary_task, jobs), jobs):
            summ.setdefault(seed, {})[(k, 0)], summ[seed][(k, 1)] = plus, minus
        sd = dict(pool.imap_unordered(sd_task, [(k,) for k in range(len(nulls))]))
        jobs = []
        for seed, shift_sd in ((SECOND_SEED, 0.0), (THIRD_SEED, 0.0), (POWER_SEED, SHIFT_SD)):
            for k in range(len(nulls)):
                for chunk in range(-(-runs // CHUNK)):
                    jobs.append((seed, k, chunk, min(CHUNK, runs - chunk * CHUNK), shift_sd * sd[k]))
        totals = {}
        for seed, k, counts in pool.imap_unordered(sides_task, jobs):
            for side in (0, 1):
                acc = totals.setdefault((seed, k, side), {a: 0 for a in THRESHOLDS})
                for a in THRESHOLDS:
                    acc[a] += counts[side][a]
    keys = [(k, s) for k in range(len(nulls)) for s in (0, 1)]
    by = battery_json["by_threshold"]
    tables = {"battery": {ks: {str(a): by[str(a)]["rates"][nulls[ks[0]]["name"]][ks[1]] for a in THRESHOLDS}
                          for ks in keys}}
    for name, seed in (("second", SECOND_SEED), ("third", THIRD_SEED), ("power", POWER_SEED)):
        tables[name] = {ks: {str(a): totals[(seed, *ks)][a] / runs for a in THRESHOLDS} for ks in keys}
    # the registered weights, and the matched null-sides' second-seed sizes and power, are the match's
    registered = abc_weights(real, summ[SUMMARY_SEED])
    ref = {s["null_side"]: s for s in match_json["matched"]}
    reproduction = {
        "weights": max(abs(registered.get(ks, 0.0) - ref[label(ks)]["weight"] if label(ks) in ref
                           else registered.get(ks, 0.0)) for ks in keys),
        "second_seed_size": max(abs(tables["second"][ks][str(a)] - ref[label(ks)]["size_second_seed"][str(a)])
                                for ks in registered for a in THRESHOLDS),
        "power": max(abs(tables["power"][ks][str(a)] - ref[label(ks)]["power"][str(a)])
                     for ks in registered for a in THRESHOLDS)}
    if set(map(label, registered)) != set(ref) or any(v != 0 for v in reproduction.values()):
        raise SystemExit(f"the variants do not reproduce the match: {reproduction}")
    base = [tables["battery"], tables["second"]]

    def no(*drop):
        return [key for key in inf.SUMMARY_KEYS if key not in drop]

    specs = [
        ("registered", "the registered rule: cap 0.055, nearest 1%, twelve summaries, IQR scaling, log kurtosis",
         registered, base, SIZE_CAP),
        ("cap 0.05", "the cap at the level, 0.05", registered, base, 0.05),
        ("cap 0.06", "the cap at 0.06", registered, base, 0.06),
        *[(f"accept {acc:.2%}", f"the nearest {acc:.2%} accepted", abc_weights(real, summ[SUMMARY_SEED], accept=acc),
           base, SIZE_CAP) for acc in (0.005, 0.0025, 0.02, 0.05)],
        ("drop spec4_20", "eleven summaries, without spec4_20",
         abc_weights(real, summ[SUMMARY_SEED], keys=no("spec4_20")), base, SIZE_CAP),
        ("drop kurt", "eleven summaries, without the kurtosis",
         abc_weights(real, summ[SUMMARY_SEED], keys=no("kurt")), base, SIZE_CAP),
        ("drop spec4_20 and kurt", "ten summaries, without spec4_20 and the kurtosis",
         abc_weights(real, summ[SUMMARY_SEED], keys=no("spec4_20", "kurt")), base, SIZE_CAP),
        ("scale: pooled SD", "each summary over its pooled SD", abc_weights(real, summ[SUMMARY_SEED], scale="sd"),
         base, SIZE_CAP),
        ("scale: pooled MAD", "each summary over 1.4826 x its pooled median absolute deviation",
         abc_weights(real, summ[SUMMARY_SEED], scale="mad"), base, SIZE_CAP),
        ("kurtosis not logged", "the excess kurtosis as it is, not log(kurt + 3)",
         abc_weights(real, summ[SUMMARY_SEED], logkurt=False), base, SIZE_CAP),
        ("prior uniform over the 3 families", "a prior uniform over the families sv, s4 and orch, not the 60 "
         "null-sides", family_prior(registered), base, SIZE_CAP),
        ("third size seed replaces the second", f"the size at seed {THIRD_SEED} in place of the second seed's",
         registered, [tables["battery"], tables["third"]], SIZE_CAP),
        ("three size seeds, all must pass", f"the battery's, the second and the third ({THIRD_SEED}) seed",
         registered, [tables["battery"], tables["second"], tables["third"]], SIZE_CAP),
    ]
    variants = []
    for name, description, weights, size_tables, cap in specs:
        picked = choose(weights, size_tables, tables["power"], cap)
        table_names = ["battery", "second", "third"] if len(size_tables) == 3 else (
            ["battery", "third"] if size_tables[1] is tables["third"] else ["battery", "second"])
        variants.append({"name": name, "description": description, "sides": len(weights), "cap": cap,
                         "threshold": picked["threshold"], "size": dict(zip(table_names, picked["size"])),
                         "power": picked["power"], "passes": picked["passes"]})
    seeds = []
    for seed in VARIANT_SUMMARY_SEEDS:
        weights = abc_weights(real, summ[seed])
        picked = choose(weights, base, tables["power"])
        seeds.append({"seed": seed, "sides": len(weights), "threshold": picked["threshold"],
                      "size": dict(zip(["battery", "second"], picked["size"]))})
    mc_se = {name: {str(a): math.sqrt(sum(v * v * tables[name][ks][str(a)] * (1 - tables[name][ks][str(a)]) / runs
                                          for ks, v in registered.items())) for a in THRESHOLDS}
             for name in ("battery", "second")}
    return {"script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "inference_sha256": hashlib.sha256(Path(inf.__file__).read_bytes()).hexdigest(),
            "battery_sha256": battery_sha256, "match_sha256": match_sha256, "real": real, "runs": runs,
            "seeds": {"summaries": f"default_rng([seed, cell]) for seed {SUMMARY_SEED} (the match's) and "
                                   f"{VARIANT_SUMMARY_SEEDS[0]}-{VARIANT_SUMMARY_SEEDS[-1]}",
                      "second": SECOND_SEED, "third": THIRD_SEED, "power": POWER_SEED,
                      "runs": "data default_rng([seed, cell, chunk]), bootstrap [seed, cell, chunk, run, side]"},
            "reproduction": {**reproduction, "note": "max |difference| from the match's weights, and its matched "
                                                     "null-sides' second-seed sizes and power (0: the same runs)"},
            "variants": variants,
            "summary_seeds": {"seeds": list(VARIANT_SUMMARY_SEEDS), "rows": seeds,
                              "picks": {**{str(a): sum(r["threshold"] == a for r in seeds) for a in THRESHOLDS},
                                        "none": sum(r["threshold"] is None for r in seeds)}},
            "mc_se": {"registered_weights": mc_se,
                      "note": "binomial SE of the registered ABC-weighted size: sqrt(sum w^2 r (1 - r) / runs)"},
            "sides_rates": {name: {label(ks): tables[name][ks] for ks in keys}
                            for name in ("second", "third", "power")},
            "seconds": round(time.time() - started, 1)}


# --- conditional (fix pass 3, item D2) ------------------------------------------------------------------------------

def cond_task(args):
    from volbt.analytics import inference as inf

    k, chunk, runs, nc, seed = args
    x = generate(battery()[k], np.random.default_rng([seed, k, chunk]), runs, nc + COND_GAP + T)
    summ, p = np.zeros((2, runs, len(inf.SUMMARY_KEYS))), np.zeros((2, runs))
    for side in (0, 1):
        for i, row in enumerate(x):
            d = row if side == 0 else -row
            s = inf.dependence_summaries(d[:nc])
            summ[side, i] = [s[key] for key in inf.SUMMARY_KEYS]
            p[side, i] = inf.ewc_bootstrap(d[nc + COND_GAP:], Q, BLOCK, DRAWS,
                                           seed=[seed, k, chunk, i, side])["p"]
    return k, chunk, summ, p


def run_conditional(dependence: dict, paths: int, procs: int, seed: int = COND_SEED) -> dict:
    from volbt.analytics import inference as inf

    real, nc = dependence["summaries"], int(dependence["window"]["n"])
    nulls = battery()
    started = time.time()
    keys = list(inf.SUMMARY_KEYS)
    summ = np.zeros((len(nulls), 2, paths, len(keys)))
    pv = np.zeros((len(nulls), 2, paths))
    jobs = [(k, c, min(CHUNK, paths - c * CHUNK), nc, seed) for k in range(len(nulls))
            for c in range(-(-paths // CHUNK))]
    with Pool(procs) as pool:
        for k, c, s, p in pool.imap_unordered(cond_task, jobs):
            summ[k, :, c * CHUNK:c * CHUNK + s.shape[1]] = s
            pv[k, :, c * CHUNK:c * CHUNK + p.shape[1]] = p
    x = transform(summ).reshape(-1, len(keys))
    p = pv.reshape(-1)
    side_id = np.repeat(np.arange(2 * len(nulls)), paths)
    rv = transform(np.array([real[key] for key in keys]))
    q75, q25 = np.percentile(x, [75, 25], axis=0)
    dist = np.sqrt((((x - rv) / ((q75 - q25) / 1.349)) ** 2).sum(axis=1))
    order = np.argsort(dist, kind="stable")
    side_size = {a: np.array([np.mean(p[side_id == s] < a) for s in range(2 * len(nulls))]) for a in THRESHOLDS}
    names = [f"{n['name']} {side_name(s)}" for n in nulls for s in (0, 1)]
    rows = []
    for acc in COND_ACCEPTS:
        m = int(round(acc * len(dist)))
        near = order[:m]
        w = np.bincount(side_id[near], minlength=2 * len(nulls)) / m
        by = {}
        for a in THRESHOLDS:
            cond = float(np.mean(p[near] < a))
            by[str(a)] = {"side_average": float(w @ side_size[a]), "accepted_paths": cond,
                          "se": math.sqrt(cond * (1 - cond) / m)}
        rows.append({"accept": acc, "accepted": m, "sides": int(np.count_nonzero(w)), "by_threshold": by})
    m = int(round(0.01 * len(dist)))
    w = np.bincount(side_id[order[:m]], minlength=2 * len(nulls)) / m
    within = []
    for s in np.argsort(-w, kind="stable"):
        if w[s] < COND_HEAVY:
            break
        idx = np.where(side_id == s)[0]
        k10 = len(idx) // 10
        nearest = idx[np.argsort(dist[idx], kind="stable")[:k10]]
        within.append({"null_side": names[s], "weight": float(w[s]), "n": int(k10),
                       "all": {str(a): float(np.mean(p[idx] < a)) for a in THRESHOLDS},
                       "nearest_10pct": {str(a): float(np.mean(p[nearest] < a)) for a in THRESHOLDS}})
    return {"script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "inference_sha256": hashlib.sha256(Path(inf.__file__).read_bytes()).hexdigest(),
            "real": real, "seed": f"data default_rng([{seed}, cell, chunk]), bootstrap "
                                  f"[{seed}, cell, chunk, run, side]", "seed_value": seed,
            "paths_per_null": paths, "n_calibration": nc, "gap": COND_GAP, "T": T, "draws": DRAWS,
            "method": "the match's scaling (IQR / 1.349 over every path, log(kurt + 3)) and Euclidean distance on the "
                      "calibration segment's twelve summaries; the test on the scored segment",
            "by_accept": rows, "heavy": COND_HEAVY, "within_side": within,
            "seconds": round(time.time() - started, 1)}


# --- combinations (fix pass 4, item F1) ------------------------------------------------------------------------------

def choice_label(dim: str, value) -> str:
    """One changed choice as the .json and the .md name it ("cap 0.05", "drop spec4_20 and kurt", ...)."""
    if dim == "accept":
        return f"accept {value:.2%}"
    if dim == "drop":
        return "drop " + " and ".join(value) if value else "drop none"
    if dim == "logkurt":
        return "kurtosis logged" if value else "kurtosis not logged"
    return f"{dim} {value:g}" if isinstance(value, float) else f"{dim} {value}"


def pick_counts(picks: list) -> dict[str, int]:
    """{threshold: how many picked it} for every threshold, and "none"."""
    return {**{str(a): sum(x == a for x in picks) for a in THRESHOLDS}, "none": sum(x is None for x in picks)}


def rule_key(c: dict) -> tuple:
    """A combination of CHOICES as the rule it is: the kurtosis logged or not is no choice when the kurtosis is dropped
    (abc_weights logs it only when "kurt" is kept), so it is None there (fix pass 5, item G2)."""
    return tuple((dim, None if dim == "logkurt" and "kurt" in c["drop"] else c[dim]) for dim in CHOICES)


def run_combinations(dependence: dict, battery_json: dict, battery_sha256: str, match_json: dict, match_sha256: str,
                     variants_json: dict, variants_sha256: str, procs: int) -> dict:
    import itertools

    from volbt.analytics import inference as inf

    real, n = dependence["summaries"], int(dependence["window"]["n"])
    nulls = battery()
    started = time.time()

    def label(ks):
        return f"{nulls[ks[0]]['name']} {side_name(ks[1])}"

    with Pool(procs) as pool:
        summ = {}
        for k, (plus, minus) in pool.imap(summary_task, [(k, PATHS, n) for k in range(len(nulls))]):
            summ[(k, 0)], summ[(k, 1)] = plus, minus
    keys = [(k, s) for k in range(len(nulls)) for s in (0, 1)]
    by = battery_json["by_threshold"]
    tables = {"battery": {ks: {str(a): by[str(a)]["rates"][nulls[ks[0]]["name"]][ks[1]] for a in THRESHOLDS}
                          for ks in keys}}
    for name in ("second", "third", "power"):
        tables[name] = {ks: variants_json["sides_rates"][name][label(ks)] for ks in keys}
    size_tables = {"second": [tables["battery"], tables["second"]], "third": [tables["battery"], tables["third"]],
                   "all3": [tables["battery"], tables["second"], tables["third"]]}
    cache = {}

    def weights(c):
        wk = (c["accept"], c["drop"], c["scale"], c["logkurt"])
        if wk not in cache:
            cache[wk] = abc_weights(real, summ, keys=[key for key in inf.SUMMARY_KEYS if key not in c["drop"]],
                                    accept=c["accept"], scale=c["scale"], logkurt=c["logkurt"])
        return cache[wk] if c["prior"] == "sides" else family_prior(cache[wk])

    def chosen(c):
        w = weights(c)
        return choose(w, size_tables[c["seeds"]], tables["power"], c["cap"]), len(w)

    def pick(c):
        picked, sides = chosen(c)
        return picked["threshold"], sides

    registered = weights(REGISTERED_CHOICE)
    ref = {s["null_side"]: s["weight"] for s in match_json["matched"]}
    weight_gap = max(abs(registered.get(ks, 0.0) - ref.get(label(ks), 0.0)) for ks in keys)
    if set(map(label, registered)) != set(ref) or weight_gap != 0:
        raise SystemExit(f"the combinations do not reproduce the match's weights (max gap {weight_gap})")
    dims = list(CHOICES)
    # one choice changed at a time: the variant table's rows, which must give the variants' picks and sides
    rows = {row["name"]: row for row in variants_json["variants"]}
    one, mismatch = [], []
    for name, (dim, value) in VARIANT_CHOICE.items():
        threshold, sides = pick({**REGISTERED_CHOICE, dim: value})
        one.append({"changes": [choice_label(dim, value)], "variant": name, "threshold": threshold, "sides": sides})
        if (threshold, sides) != (rows[name]["threshold"], rows[name]["sides"]):
            mismatch.append(name)
    if set(VARIANT_CHOICE) != set(rows) - {"registered"} or mismatch:
        raise SystemExit(f"the one-at-a-time picks do not reproduce the variants: {mismatch}")
    two = []
    # fix pass 5, item G2: the two-at-a-time rules that are neither a one-at-a-time rule nor counted before
    seen = {rule_key(REGISTERED_CHOICE)} | {rule_key({**REGISTERED_CHOICE, dim: value})
                                            for dim, value in VARIANT_CHOICE.values()}
    two_distinct = []
    for d1, d2 in itertools.combinations(dims, 2):
        for x1 in CHOICES[d1]:
            for x2 in CHOICES[d2]:
                if x1 == REGISTERED_CHOICE[d1] or x2 == REGISTERED_CHOICE[d2]:
                    continue
                c = {**REGISTERED_CHOICE, d1: x1, d2: x2}
                threshold, sides = pick(c)
                two.append({"changes": [choice_label(d1, x1), choice_label(d2, x2)], "threshold": threshold,
                            "sides": sides})
                if rule_key(c) not in seen:
                    seen.add(rule_key(c))
                    two_distinct.append(threshold)
    grid, none, none_at_lowest, rules = [], [], [], {}
    lowest = str(min(THRESHOLDS))
    for values in itertools.product(*CHOICES.values()):
        c = dict(zip(dims, values))
        outcome, _ = chosen(c)
        threshold = outcome["threshold"]
        grid.append(threshold)
        rules.setdefault(rule_key(c), set()).add(threshold)
        if threshold is None:
            changes = [choice_label(dim, c[dim]) for dim in dims if c[dim] != REGISTERED_CHOICE[dim]]
            none.append(changes)
            size, power = [float(tab[lowest]) for tab in outcome["size"]], float(outcome["power"][lowest])
            none_at_lowest.append({"changes": changes, "threshold": float(lowest), "size": size, "cap": c["cap"],
                                   "power": power, "floor": POWER_FLOOR,
                                   "fails": [what for what, failed in (("size", max(size) > c["cap"]),
                                                                       ("power", power < POWER_FLOOR)) if failed]})
    if any(len(found) != 1 for found in rules.values()):
        raise SystemExit("two combinations of one rule (rule_key) pick different thresholds")
    falsifier = {str(a): by[str(a)]["rates"]["power delta=4.0"][0] for a in THRESHOLDS}
    high = choose(registered, size_tables["second"], tables["power"], SIZE_CAP, POWER_FLOOR_HIGH)
    low = choose(registered, size_tables["second"], tables["power"], SIZE_CAP, 0.0)
    passes = {str(a): bool(max(t[str(a)] for t in low["size"]) <= SIZE_CAP and falsifier[str(a)] >= FALSIFIER_FLOOR)
              for a in THRESHOLDS}
    power_rows = [
        {"name": f"ABC power floor {POWER_FLOOR_HIGH:g}",
         "description": f"the registered rule with the ABC-weighted power floor at {POWER_FLOOR_HIGH:g}, not "
                        f"{POWER_FLOOR:g}", "sides": len(registered), "cap": SIZE_CAP,
         "threshold": high["threshold"], "size": dict(zip(["battery", "second"], high["size"])),
         "power": high["power"], "requirement": "abc_power", "floor": POWER_FLOOR_HIGH, "passes": high["passes"]},
        {"name": f"falsifier (c) power floor {FALSIFIER_FLOOR:g}",
         "description": f"the first revision's power requirement: falsifier (c) power of at least "
                        f"{FALSIFIER_FLOOR:g}, in place of the ABC-weighted power", "sides": len(registered),
         "cap": SIZE_CAP, "threshold": next((a for a in THRESHOLDS if passes[str(a)]), None),
         "size": dict(zip(["battery", "second"], low["size"])), "power": low["power"],
         "falsifier_c_power": falsifier, "requirement": "falsifier_c_power", "floor": FALSIFIER_FLOOR,
         "passes": passes}]
    picked = [x for x in grid if x is not None]
    return {"script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "inference_sha256": hashlib.sha256(Path(inf.__file__).read_bytes()).hexdigest(),
            "battery_sha256": battery_sha256, "match_sha256": match_sha256, "variants_sha256": variants_sha256,
            "real": real, "summaries_seed": f"default_rng([{SUMMARY_SEED}, cell]) (the match's)",
            "choices": {dim: [list(v) if isinstance(v, tuple) else v for v in values]
                        for dim, values in CHOICES.items()},
            "registered": {dim: list(v) if isinstance(v, tuple) else v for dim, v in REGISTERED_CHOICE.items()},
            "rule": "the registered rule (tools/forecast_size.py choose): the largest threshold whose weighted size "
                    "is at most the cap on every size table and whose ABC-weighted power is at least the floor",
            "reproduction": {"weights": weight_gap, "one_at_a_time_mismatch": mismatch,
                             "note": "max |difference| from the match's weights; the one-at-a-time rows whose pick or "
                                     "matched null-sides differ from VARIANTS.json's (none: the same rule)"},
            "one_at_a_time": {"n": len(one), "picks": pick_counts([r["threshold"] for r in one]), "rows": one},
            "two_at_a_time": {"n": len(two), "picks": pick_counts([r["threshold"] for r in two]), "rows": two,
                              "distinct": {"n": len(two_distinct), "picks": pick_counts(two_distinct),
                                           "note": "the two-at-a-time combinations that are a rule of their own: not a "
                                                   "one-at-a-time rule, not counted before (rule_key: with the "
                                                   "kurtosis dropped, logging it is no choice)"}},
            "full_grid": {"n": len(grid), "picks": pick_counts(grid), "none": none,
                          "distinct_rules": {"n": len(rules), "picks": pick_counts([next(iter(found))
                                                                                   for found in rules.values()]),
                                             "note": "each distinct rule once (rule_key: with the kurtosis dropped, "
                                                     f"logging it is no choice, so {len(grid) - len(rules)} "
                                                     "combinations repeat a rule)"},
                          "none_at_lowest": none_at_lowest},
            "thresholds": list(THRESHOLDS),
            "power_rows": power_rows,
            "band": [min(picked), max(picked)],
            "seconds": round(time.time() - started, 1)}


def sv_means() -> dict:
    """The S1-S3 centring constants: 12 x 25 batches of 200 runs per scenario, seeds [7|8|9, batch group]."""
    out = {}
    for scenario, base in (("S1", 7), ("S2", 8), ("S3", 9)):
        means = []
        for group in range(12):
            rng = np.random.default_rng([base, group])
            means += [sv_series(rng, 200, T, scenario).mean() for _ in range(25)]
        means = np.array(means)
        out[scenario] = {"mean": float(means.mean()), "se": float(means.std(ddof=1) / math.sqrt(means.size))}
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="mode", required=True)
    b = sub.add_parser("battery")
    b.add_argument("runs", type=int)
    b.add_argument("out", type=Path)
    b.add_argument("--procs", type=int, default=os.cpu_count())
    m = sub.add_parser("match")
    m.add_argument("dependence", type=Path)
    m.add_argument("battery", type=Path)
    m.add_argument("out", type=Path)
    m.add_argument("--runs", type=int, default=2000)
    m.add_argument("--procs", type=int, default=os.cpu_count())
    v = sub.add_parser("variants")
    v.add_argument("dependence", type=Path)
    v.add_argument("battery", type=Path)
    v.add_argument("match", type=Path)
    v.add_argument("out", type=Path)
    v.add_argument("--runs", type=int, default=2000)
    v.add_argument("--procs", type=int, default=os.cpu_count())
    c = sub.add_parser("conditional")
    c.add_argument("dependence", type=Path)
    c.add_argument("out", type=Path)
    c.add_argument("--paths", type=int, default=COND_PATHS)
    c.add_argument("--seed", type=int, default=COND_SEED)
    c.add_argument("--procs", type=int, default=os.cpu_count())
    cb = sub.add_parser("combinations")
    cb.add_argument("dependence", type=Path)
    cb.add_argument("battery", type=Path)
    cb.add_argument("match", type=Path)
    cb.add_argument("variants", type=Path)
    cb.add_argument("out", type=Path)
    cb.add_argument("--procs", type=int, default=os.cpu_count())
    sub.add_parser("sv-means")
    args = parser.parse_args(argv)
    if args.mode == "sv-means":
        print(json.dumps(sv_means(), indent=1))
        return 0
    if args.mode == "variants":
        raw_b, raw_m = args.battery.read_bytes(), args.match.read_bytes()
        result = run_variants(json.loads(args.dependence.read_text(encoding="utf-8")), json.loads(raw_b),
                              hashlib.sha256(raw_b).hexdigest(), json.loads(raw_m), hashlib.sha256(raw_m).hexdigest(),
                              args.runs, args.procs)
        args.out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
        for row in result["variants"]:
            print(f"{row['name']:40s} sides {row['sides']:2d} -> {row['threshold']}  "
                  + "  ".join(f"@{a}: " + " / ".join(f"{t[a]:.4f}" for t in row["size"].values())
                              for a in ("0.03", "0.025", "0.02")) + f"  power@0.025 {row['power']['0.025']:.4f}")
        print(f"summary seeds: picks {result['summary_seeds']['picks']}; {result['seconds']} s")
        return 0
    if args.mode == "conditional":
        result = run_conditional(json.loads(args.dependence.read_text(encoding="utf-8")), args.paths, args.procs,
                                 args.seed)
        args.out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
        for row in result["by_accept"]:
            print(f"accept {row['accept']:.2%} ({row['accepted']}): " + "  ".join(
                f"@{a}: side-avg {v['side_average']:.4f} | accepted paths {v['accepted_paths']:.4f} (se {v['se']:.4f})"
                for a, v in row["by_threshold"].items()))
        print(f"{result['seconds']} s")
        return 0
    if args.mode == "combinations":
        raw_b, raw_m, raw_v = args.battery.read_bytes(), args.match.read_bytes(), args.variants.read_bytes()
        result = run_combinations(json.loads(args.dependence.read_text(encoding="utf-8")), json.loads(raw_b),
                                  hashlib.sha256(raw_b).hexdigest(), json.loads(raw_m),
                                  hashlib.sha256(raw_m).hexdigest(), json.loads(raw_v),
                                  hashlib.sha256(raw_v).hexdigest(), args.procs)
        args.out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
        for part in ("one_at_a_time", "two_at_a_time", "full_grid"):
            print(f"{part}: {result[part]['n']} combinations, picks {result[part]['picks']}")
        print(f"two_at_a_time distinct: {result['two_at_a_time']['distinct']['n']} rules, picks "
              f"{result['two_at_a_time']['distinct']['picks']}")
        print(f"full_grid distinct: {result['full_grid']['distinct_rules']['n']} rules, picks "
              f"{result['full_grid']['distinct_rules']['picks']}")
        for row in result["full_grid"]["none_at_lowest"]:
            print(f"none: {row['changes']} at {row['threshold']}: size {row['size']} cap {row['cap']}, power "
                  f"{row['power']:.4f} floor {row['floor']}, fails {row['fails']}")
        for row in result["power_rows"]:
            print(f"{row['name']}: picks {row['threshold']}")
        print(f"band {result['band']}; {result['seconds']} s")
        return 0
    if args.mode == "battery":
        result = run_battery(args.runs, args.procs)
        args.out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
        for a, row in result["by_threshold"].items():
            print(f"p < {a}: worst {row['worst']}, in band {row['in_band']}, power {row['power']}")
        print(f"{result['runs']} runs, {result['seconds']} s")
        return 0
    raw = args.battery.read_bytes()
    result = run_match(json.loads(args.dependence.read_text(encoding="utf-8")), json.loads(raw),
                       hashlib.sha256(raw).hexdigest(), args.runs, args.procs)
    args.out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    for row in result["table"]:
        print(row)
    print(f"threshold {result['threshold']}; {result['seconds']} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
