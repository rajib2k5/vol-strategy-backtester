"""The American IV solve (deam.py): repricing, identifiability, the fail codes, the partner's premium.

M2 round 2 (code claim 2, decision E3): an American price that is flat in sigma (deep in the money,
where exercising at once is optimal) "converged" at any sigma, and the premium at it was not the
quote's; bad inputs all came back as american_below_floor or after 40 walks as no_convergence; and
four mutants of the solve (R2, R3, R4, R6) survived the suite. Each test below names what it kills.
"""

import numpy as np
import pytest

from volbt.pricing import chain, deam, iv, lattice

SPOT, RATE, DIV = 442.61, 0.0521594, 1.638367


def random_quotes(n=3000, seed=5, rate=0.045):
    """Random American quotes priced on the procedure's own lattice (N = 200): the truth is known exactly."""
    rng = np.random.default_rng(seed)
    strike = SPOT * np.exp(rng.uniform(-0.6, 0.4, n))
    tau = rng.uniform(2, 900, n) / 365
    sigma = rng.uniform(0.06, 1.2, n)
    call = rng.random(n) < 0.5
    times = np.where(rng.random(n) < 0.7, rng.uniform(0.001, 0.5, n), 0.0)[:, None]
    amounts = np.where(times > 0, 1.6, 0.0)
    mid = lattice.crr(SPOT, strike, tau, rate, sigma, call, times, amounts)["price"]
    keep = mid > 0.005
    return {"mid": mid[keep], "strike": strike[keep], "tau": tau[keep], "sigma": sigma[keep], "call": call[keep],
            "times": times[keep], "amounts": amounts[keep], "rate": rate}


def solve(q):
    return deam.american_iv(q["mid"], SPOT, q["strike"], q["tau"], q["rate"], q["call"], q["times"], q["amounts"])


def test_every_solved_quote_reprices_to_its_tolerance_and_its_sigma():
    # Mutant R6 ("pinned" at a 1e-3 bracket) stopped 7 of these off the root and survived the suite.
    q = random_quotes()
    got = solve(q)
    solved = np.isfinite(got["iv"])
    assert solved.sum() > 0.85 * solved.size
    a = lattice.crr(SPOT, q["strike"][solved], q["tau"][solved], q["rate"], got["iv"][solved], q["call"][solved],
                    q["times"][solved], q["amounts"][solved])["price"]
    tol = np.maximum(1e-8, 1e-7 * q["mid"][solved])
    assert np.all(np.abs(a - q["mid"][solved]) <= tol)
    assert np.max(np.abs(got["iv"][solved] / q["sigma"][solved] - 1)) < 1e-4
    # The ones not solved are deep in the money with A flat (or nearly) in sigma: unidentified, never a number.
    assert set(np.unique(got["fail"][~solved]).tolist()) <= {iv.FAIL_AMERICAN_UNIDENTIFIED}


def test_a_premium_is_never_negative_even_where_it_is_zero():
    # Puts at r = 0 with no dividend are never exercised early: A = E, and the two sums differ in
    # their last bits. Mutant R2 (no clamp at 0) returned 1,849 premiums below 0, down to -3e-11.
    rng = np.random.default_rng(7)
    n = 2000
    strike, tau, sigma = SPOT * np.exp(rng.uniform(-0.5, 0.3, n)), rng.uniform(2, 700, n) / 365, rng.uniform(0.08, 0.8, n)
    mid = lattice.crr(SPOT, strike, tau, 0.0, sigma, False)["price"]
    got = deam.american_iv(mid, SPOT, strike, tau, 0.0, False, np.zeros((n, 0)), np.zeros((n, 0)))
    premium = got["premium"][np.isfinite(got["premium"])]
    assert premium.size > 0.9 * n and premium.min() == 0.0 and premium.max() < 1e-9


def test_a_call_with_no_dividend_is_walked_at_a_negative_rate():
    # Only at r >= 0 is a call with no dividend never exercised early. At r = -1% a deep ITM call is
    # (holding cash costs): its premium is positive and its sigma is found on the American lattice.
    # Mutant R3 solved every no-dividend call on the European sum and survived.
    strike, tau, rate, sigma = np.array([360.0, 380.0, 400.0]), np.full(3, 2.0), -0.01, 0.20
    mid = lattice.crr(SPOT, strike, tau, rate, sigma, True)["price"]
    truth = lattice.early_exercise_premium(SPOT, strike, tau, rate, sigma, True)
    assert truth.min() > 0.5
    got = deam.american_iv(mid, SPOT, strike, tau, rate, True, np.zeros((3, 0)), np.zeros((3, 0)))
    assert np.all(got["fail"] == iv.FAIL_NONE) and got["iv"] == pytest.approx(sigma, rel=1e-6)
    assert got["premium"] == pytest.approx(truth, rel=1e-5) and np.all(got["walks"] > 0)


def test_a_mid_below_the_lattice_floor_fails_at_once_as_below_floor():
    # A put mid below what the lattice gives at its lowest sigma (here below intrinsic): no American
    # IV, found in a few walks. Mutant R4 (a strict < at the floor) ran it to no_convergence.
    got = deam.american_iv([30.0], SPOT, [480.0], [30 / 365], RATE, [False], [[1 / 365]], [[DIV]])
    assert int(got["fail"][0]) == iv.FAIL_AMERICAN_BELOW_FLOOR and np.isnan(got["iv"][0]) and np.isnan(got["premium"][0])
    assert int(got["walks"][0]) <= 3


@pytest.mark.parametrize("mid, strike, tau, spot, rate, times, amounts, code", [
    (np.nan, 440.0, 30 / 365, SPOT, RATE, 1 / 365, DIV, iv.FAIL_AMERICAN_NO_MID),
    (0.0, 440.0, 30 / 365, SPOT, RATE, 1 / 365, DIV, iv.FAIL_AMERICAN_NO_MID),
    (-1.0, 440.0, 30 / 365, SPOT, RATE, 1 / 365, DIV, iv.FAIL_AMERICAN_NO_MID),
    (5.0, 440.0, 0.0, SPOT, RATE, 1 / 365, DIV, iv.FAIL_AMERICAN_EXPIRED),
    (5.0, 440.0, -0.01, SPOT, RATE, 1 / 365, DIV, iv.FAIL_AMERICAN_EXPIRED),
    (5.0, np.nan, 30 / 365, SPOT, RATE, 1 / 365, DIV, iv.FAIL_AMERICAN_BAD_INPUT),
    (5.0, 440.0, np.nan, SPOT, RATE, 1 / 365, DIV, iv.FAIL_AMERICAN_BAD_INPUT),
    (5.0, 440.0, 30 / 365, np.nan, RATE, 1 / 365, DIV, iv.FAIL_AMERICAN_BAD_INPUT),
    (5.0, 440.0, 30 / 365, SPOT, np.nan, 1 / 365, DIV, iv.FAIL_AMERICAN_BAD_INPUT),
    (5.0, 440.0, 30 / 365, SPOT, RATE, 1 / 365, np.nan, iv.FAIL_AMERICAN_BAD_INPUT),     # never dropped silently
    (5.0, 440.0, 30 / 365, SPOT, RATE, np.inf, DIV, iv.FAIL_AMERICAN_BAD_INPUT),
], ids=["nan-mid", "zero-mid", "negative-mid", "tau-0", "tau-negative", "nan-strike", "nan-tau", "nan-spot", "nan-rate",
        "nan-dividend", "inf-dividend-time"])
def test_each_input_that_cannot_be_priced_has_its_own_code_and_costs_no_walk(mid, strike, tau, spot, rate, times,
                                                                           amounts, code):
    # The review: NaN, 0 or negative mids and tau <= 0 all said american_below_floor; NaN spot,
    # strike or rate said no_convergence after 40 walks; a NaN dividend was dropped and "solved".
    good = deam.american_iv([5.0], SPOT, [440.0], [30 / 365], RATE, [False], [[1 / 365]], [[DIV]])
    with np.errstate(all="raise"):
        got = deam.american_iv([mid, 5.0], spot, [strike, 440.0], [tau, 30 / 365], rate, [False, False],
                               [[times], [1 / 365]], [[amounts], [DIV]])
    assert int(got["fail"][0]) == code and np.isnan(got["iv"][0]) and np.isnan(got["premium"][0])
    assert int(got["walks"][0]) == 0
    if np.isfinite(spot) and np.isfinite(rate):          # the good row beside it is solved as if alone
        assert got["iv"][1] == good["iv"][0] and got["premium"][1] == good["premium"][0]


def test_a_flat_american_price_is_unidentified_not_converged():
    # The review's mechanism (code claim 2): at sigma 0.08, 700 days, r 5.22%, the 484 put is
    # exercised at once at every sigma from 0 to 0.10, so A(sigma) = 42.786117 for all of them.
    # The old solve "converged" at 0.1048 with a premium of 18.85 (the truth at 0.08: 24.91).
    tau = 700 / 365
    flat = [lattice.crr(SPOT, 484.0, tau, RATE, s, False, [[1 / 365]], [[DIV]])["price"][0] for s in (0.0, 0.05, 0.10)]
    assert max(flat) - min(flat) < 1e-10
    got = deam.american_iv([flat[0]], SPOT, [484.0], [tau], RATE, [False], [[1 / 365]], [[DIV]])
    assert int(got["fail"][0]) == iv.FAIL_AMERICAN_UNIDENTIFIED and np.isnan(got["iv"][0]) and np.isnan(got["premium"][0])


def flat_chain(drop_call_at=None):
    """The review's clean 700-day chain at sigma 0.08 on the procedure's own lattice, every $2 from 332 to 574."""
    tau = 700 / 365
    strikes = np.arange(332.0, 575.0, 2.0)
    both = np.concatenate([strikes, strikes])
    calls = np.r_[np.ones(strikes.size, bool), np.zeros(strikes.size, bool)]
    mid = lattice.crr(SPOT, both, tau, RATE, 0.08, calls, [[1 / 365]], [[DIV]])["price"]
    if drop_call_at is not None:
        mid[calls & (both == drop_call_at)] = 500.0          # above A(5): the call has no American IV
    out = chain.price_chain(SPOT, RATE, [tau], [[1 / 365]], [[DIV]], np.zeros(both.size, int), both, calls, mid,
                            np.ones(both.size, bool))
    return both, calls, out, (SPOT - DIV * np.exp(-RATE / 365)) * np.exp(RATE * tau)


def test_an_unidentified_quote_takes_its_premium_at_its_partner_s_american_iv():
    # With the truth on the procedure's own lattice, the procedure is exact once the flat puts are
    # priced at their partner calls' American IV: F 0.000 bp, 0 flagged (it was -52 bp, 144 flagged).
    both, calls, out, truth = flat_chain()
    q, e = out["quotes"], out["expiries"]
    assert abs(e["forward"][0] / truth - 1) * 1e4 < 1e-3 and ((q["iv_flags"] & chain.PARITY_OUTLIER) != 0).sum() == 0
    rescued = np.flatnonzero(q["premium_from_partner"])
    assert rescued.size >= 5 and not calls[rescued].any()
    tau = 700 / 365
    for i in rescued:
        partner = np.flatnonzero(calls & (both == both[i]))[0]
        mid = lattice.crr(SPOT, both[partner], tau, RATE, 0.08, True, [[1 / 365]], [[DIV]])["price"]
        sigma = deam.american_iv(mid, SPOT, [both[partner]], [tau], RATE, [True], [[1 / 365]], [[DIV]])["iv"]
        expected = lattice.early_exercise_premium(SPOT, both[i], tau, RATE, sigma, False, [[1 / 365]], [[DIV]])[0]
        assert np.isnan(q["iv_american"][i]) and q["eep"][i] == pytest.approx(expected, rel=1e-12)
        assert np.isfinite(sigma[0]) and sigma[0] == pytest.approx(0.08, rel=1e-6)


def test_an_unidentified_quote_with_no_identified_partner_stays_out_of_the_forward():
    # The call at the strike of a flat put has no American IV (its mid is above A(5)): the put keeps
    # no premium, so its pair does not enter the de-Americanised forward.
    both, calls, plain, _ = flat_chain()
    k = both[np.flatnonzero(plain["quotes"]["premium_from_partner"])[0]]
    both, calls, out, _ = flat_chain(drop_call_at=k)
    q = out["quotes"]
    put = np.flatnonzero(~calls & (both == k))[0]
    assert np.isnan(q["eep"][put]) and np.isnan(q["iv_american"][put]) and not q["premium_from_partner"][put]
    assert out["expiries"]["n_deamericanised"][0] == plain["expiries"]["n_deamericanised"][0] - 2


def test_an_otm_quote_s_partner_is_solved_when_no_earlier_step_attempted_it():
    # Round 3 (code claim 4; decision F3): r 8%, 700 days, sigma 0.12, one dividend, on the
    # procedure's own lattice. The puts at 470 and 472 lie between S (442.61) and F (514.09): OTM on
    # F, flat in sigma. Their partner calls are ITM on F and not among the 10 strikes nearest K*
    # (492), so no step attempted them, and the puts had no IV: 2 IV_FAIL and 4 PARITY_OUTLIER
    # (measured 2026-10-29 with the round-2 code, fix4/f3/f3_case.py). Now the partner is solved then.
    tau, rate, sigma = 700 / 365, 0.08, 0.12
    strikes = np.arange(332.0, 575.0, 2.0)
    both = np.concatenate([strikes, strikes])
    calls = np.r_[np.ones(strikes.size, bool), np.zeros(strikes.size, bool)]
    mid = lattice.crr(SPOT, both, tau, rate, sigma, calls, [[1 / 365]], [[DIV]])["price"]
    out = chain.price_chain(SPOT, rate, [tau], [[1 / 365]], [[DIV]], np.zeros(both.size, int), both, calls, mid,
                            np.ones(both.size, bool))
    q, e = out["quotes"], out["expiries"]
    truth = (SPOT - DIV * np.exp(-rate / 365)) * np.exp(rate * tau)
    assert abs(e["forward"][0] / truth - 1) * 1e4 < 1e-3 and e["k_star"][0] == 492.0
    assert ((q["iv_flags"] & chain.IV_FAIL) != 0).sum() == 0 and ((q["iv_flags"] & chain.PARITY_OUTLIER) != 0).sum() == 0
    for k in (470.0, 472.0):
        put = np.flatnonzero(~calls & (both == k))[0]
        call = np.flatnonzero(calls & (both == k))[0]
        assert q["is_otm"][put] and not q["is_otm"][call] and q["premium_from_partner"][put]
        call_sigma = deam.american_iv(mid[[call]], SPOT, [k], [tau], rate, [True], [[1 / 365]], [[DIV]])["iv"]
        expected = lattice.early_exercise_premium(SPOT, k, tau, rate, call_sigma, False, [[1 / 365]], [[DIV]])[0]
        assert q["eep"][put] == pytest.approx(expected, rel=1e-12) and q["iv"][put] == pytest.approx(sigma, abs=5e-4)


def test_a_flat_quote_s_partner_comes_from_its_own_expiry():
    # Round 3 (code claim 5; decision F4): the round-3 reviewer's mutant N1 looked the partner up by
    # strike and type alone, in ANY expiry, and survived the suite. Two expiries list the same
    # strikes: the 700-day one (sigma 0.08, its deep-ITM puts flat) first, a 365-day one (sigma
    # 0.20) after it, so a lookup without the expiry finds the 365-day call.
    tau_a, tau_b = 700 / 365, 365 / 365
    strikes = np.arange(332.0, 575.0, 2.0)
    one = np.concatenate([strikes, strikes])
    calls_one = np.r_[np.ones(strikes.size, bool), np.zeros(strikes.size, bool)]
    mid_a = lattice.crr(SPOT, one, tau_a, RATE, 0.08, calls_one, [[1 / 365]], [[DIV]])["price"]
    mid_b = lattice.crr(SPOT, one, tau_b, RATE, 0.20, calls_one, [[1 / 365]], [[DIV]])["price"]
    both, calls = np.concatenate([one, one]), np.concatenate([calls_one, calls_one])
    expiry = np.r_[np.zeros(one.size, int), np.ones(one.size, int)]
    out = chain.price_chain(SPOT, RATE, [tau_a, tau_b], [[1 / 365], [1 / 365]], [[DIV], [DIV]], expiry, both, calls,
                            np.concatenate([mid_a, mid_b]), np.ones(both.size, bool))
    q, e = out["quotes"], out["expiries"]
    truth_a = (SPOT - DIV * np.exp(-RATE / 365)) * np.exp(RATE * tau_a)
    assert abs(e["forward"][0] / truth_a - 1) * 1e4 < 1e-3
    rescued = np.flatnonzero(q["premium_from_partner"] & (expiry == 0))
    assert rescued.size >= 5
    for i in rescued:
        partner = np.flatnonzero((expiry == 0) & (calls != calls[i]) & (both == both[i]))[0]
        sigma = deam.american_iv(mid_a[[partner]], SPOT, [both[i]], [tau_a], RATE, [calls[partner]], [[1 / 365]],
                                 [[DIV]])["iv"]
        expected = lattice.early_exercise_premium(SPOT, both[i], tau_a, RATE, sigma, calls[i], [[1 / 365]], [[DIV]])[0]
        assert q["eep"][i] == pytest.approx(expected, rel=1e-12)


def test_without_de_americanisation_the_forward_says_raw_parity():
    # The review: deamericanise=False labelled the raw forward parity_median5_deam.
    both, calls, _, _ = flat_chain()
    mid = lattice.crr(SPOT, both, 60 / 365, RATE, 0.15, calls, [[1 / 365]], [[DIV]])["price"]
    out = chain.price_chain(SPOT, RATE, [60 / 365], [[1 / 365]], [[DIV]], np.zeros(both.size, int), both, calls, mid,
                            np.ones(both.size, bool), deamericanise=False)
    assert chain.METHOD_NAMES[out["expiries"]["method"][0]] == "parity_median5_raw"
    assert out["expiries"]["forward"][0] == out["expiries"]["forward_raw"][0]
    assert all(s["fit_flags"] & chain.SMILE_FORWARD_RAW for s in out["smiles"])
