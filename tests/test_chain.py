"""One priced snapshot (volbt.pricing.chain): the IV flags of ADR-0009 §3, one fixture row per flag.

tests/pricing_fixtures/pricing_chain.csv is made up (its README says how); its
expected_iv_flags column is the hand-worked answer.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from volbt.data import flags as data_flags
from volbt.pricing import black76, chain, iv, smile

FIXTURE = Path(__file__).resolve().parent / "pricing_fixtures" / "pricing_chain.csv"
SPOT, RATE = 440.0, 0.05


@pytest.fixture(scope="module")
def priced():
    rows = pd.read_csv(FIXTURE)
    days = sorted(rows["expiry_days"].unique())
    tau = np.array(days) / 365
    out = chain.price_chain(SPOT, RATE, tau, np.zeros((len(days), 0)), np.zeros((len(days), 0)),
                            rows["expiry_days"].map({d: i for i, d in enumerate(days)}).to_numpy(),
                            rows["strike"].to_numpy(float), (rows["call_put"] == "C").to_numpy(),
                            rows["mid"].to_numpy(float), rows["valid"].astype(bool).to_numpy())
    return rows, out


def test_the_iv_flag_bits_are_the_ones_m1_reserved():
    assert chain.IV_FLAG_NAMES == data_flags.IV_FLAG_NAMES
    assert (chain.IV_FAIL, chain.PARITY_OUTLIER, chain.FORWARD_FALLBACK) == (
        data_flags.IV_FAIL, data_flags.PARITY_OUTLIER, data_flags.FORWARD_FALLBACK)


def test_every_row_gets_exactly_its_hand_worked_flags(priced):
    rows, out = priced
    got = out["quotes"]["iv_flags"].tolist()
    assert got == rows["expected_iv_flags"].tolist(), list(zip(rows["why"], got))


def test_each_flag_has_at_least_one_fixture_row(priced):
    rows, _ = priced
    for bit in (chain.IV_FAIL, chain.PARITY_OUTLIER, chain.FORWARD_FALLBACK):
        assert (rows["expected_iv_flags"] & bit).any()


def test_iv_fail_rows_have_no_iv_and_say_why(priced):
    rows, out = priced
    q = out["quotes"]
    failed = (q["iv_flags"] & chain.IV_FAIL) != 0
    assert np.all(np.isnan(q["iv"][failed]))
    reasons = {(int(k), str(cp)): iv.FAIL_NAMES[f] for k, cp, f in zip(rows["strike"], rows["call_put"], q["fail"])}
    # Both fail the American IV solve first: no sigma up to 5 gives the lattice their mids.
    assert reasons[(400, "P")] == "american_above_cap" and reasons[(470, "C")] == "american_above_cap"
    assert np.all(np.isnan(q["eep"][failed]))


def test_the_parity_expiry_and_the_fallback_expiry(priced):
    _, out = priced
    e = out["expiries"]
    assert [chain.METHOD_NAMES[m] for m in e["method"]] == ["parity_median5_deam", "dividend_fallback"]
    # The median of the 5 strikes ignores the damaged 450: F stays near the carry forward 441.75.
    assert abs(e["forward"][0] / 441.7514 - 1) < 2e-4
    assert e["k_star"][0] == 440 and e["n_pairs_valid"][0] == 5 and e["n_pairs_used"][0] == 5
    assert e["forward"][1] == pytest.approx(443.8745, abs=5e-5) and e["n_pairs_valid"][1] == 2
    assert np.isnan(e["forward_raw"][1]) and e["flags"][1] == chain.FORWARD_FALLBACK


def test_only_otm_quotes_are_solved_and_clean_ones_recover_sigma(priced):
    rows, out = priced
    q = out["quotes"]
    itm = ~q["is_otm"]
    assert np.all(np.isnan(q["iv"][itm]))
    clean = (q["iv_flags"] == 0) & q["is_otm"]
    # Cent-rounded European mids at sigma 0.15, minus a small lattice premium: within 0.4 vol points.
    assert np.all(np.abs(q["iv"][clean] - 0.15) < 0.004)
    assert np.all(q["eep"][clean] >= 0)


def test_the_smiles(priced):
    _, out = priced
    first, second = out["smiles"]
    # Expiry 1: OTM valid nodes at 430, 435, 440 (puts) and 445, 450 (calls) = 5: usable.
    assert first["n_points"] == 5 and first["fit_flags"] == 0
    assert first["atm_iv"] == pytest.approx(0.15, abs=0.004)
    # Expiry 2: the fallback forward, and too few nodes.
    assert second["fit_flags"] & smile.SMILE_FORWARD_FALLBACK and second["fit_flags"] & smile.SMILE_THIN


def test_a_deep_itm_put_s_own_premium_does_not_make_its_strike_an_outlier():
    # 90 days at 5.25%, American quotes on a skew, no dividend. On RAW mids F_K falls with the strike,
    # through the ITM puts' premium, to -1.48% at K = 520: 0.5% is crossed from K = 480. On
    # European-equivalent mids (§3a) no strike is an outlier, which is the point of the flag.
    from volbt.pricing import lattice

    spot, rate, tau = 440.0, 0.0525, 90 / 365
    strikes = np.arange(360.0, 521.0, 10)
    both = np.concatenate([strikes, strikes])
    calls = np.r_[np.ones(strikes.size, bool), np.zeros(strikes.size, bool)]
    forward = spot * np.exp(rate * tau)
    sigma = 0.18 - 0.25 * np.log(both / forward)
    mids = np.round(lattice.crr(spot, both, tau, rate, sigma, calls, steps=1000)["price"], 2)
    raw_fk = strikes + (mids[:strikes.size] - mids[strikes.size:]) / np.exp(-rate * tau)
    assert (np.abs(raw_fk / forward - 1) > 0.005).sum() == 5
    out = chain.price_chain(spot, rate, [tau], np.zeros((1, 0)), np.zeros((1, 0)), np.zeros(both.size, int), both,
                            calls, mids, np.ones(both.size, bool))
    assert out["quotes"]["iv_flags"].tolist() == [0] * both.size
    assert abs(out["expiries"]["forward"][0] / forward - 1) < 1e-4


def test_a_smile_needs_five_nodes():
    # ADR-0004 step 2: fewer than 5 valid OTM quotes is a thin smile, not used by the surface.
    strikes = np.array([430.0, 435.0, 445.0, 450.0, 455.0])
    tau = 30 / 365
    forward = 440.0 * np.exp(0.05 * tau)
    from volbt.pricing import black76

    for count, thin in ((4, True), (5, False)):
        k = strikes[:count]
        is_call = k >= forward
        mids = black76.price(forward, k, tau, 0.05, 0.2, is_call)
        out = chain.price_chain(440.0, 0.05, [tau], np.zeros((1, 0)), np.zeros((1, 0)), np.zeros(count, int), k,
                                is_call, mids, np.ones(count, bool))
        assert out["smiles"][0]["n_points"] == count
        assert bool(out["smiles"][0]["fit_flags"] & smile.SMILE_THIN) is thin


def test_an_invalid_quote_and_a_quote_not_smile_ok_are_each_left_out_of_the_smile_on_their_own():
    # Round 3 (F2): in_smile needs BOTH masks. The build passes smile_ok = not WIDE and not invalid, so
    # through the build "valid" alone looks redundant (the round-2 mutants W23 and R11, which drop it,
    # survived the round-3 suite); a direct caller of price_chain keeps smile_ok at its default.
    from volbt.pricing import black76

    strikes = np.array([425.0, 430.0, 435.0, 445.0, 450.0, 455.0])
    tau = 30 / 365
    forward = 440.0 * np.exp(0.05 * tau)
    is_call = strikes >= forward
    mids = black76.price(forward, strikes, tau, 0.05, 0.2, is_call)
    for valid, smile_ok in ((np.r_[True, False, True, True, True, True], None),
                            (np.ones(6, bool), np.r_[True, False, True, True, True, True])):
        out = chain.price_chain(440.0, 0.05, [tau], np.zeros((1, 0)), np.zeros((1, 0)), np.zeros(6, int), strikes,
                                is_call, mids, valid, smile_ok=smile_ok)
        q = out["quotes"]
        assert np.isfinite(q["iv"][1]) and not q["in_smile"][1] and q["in_smile"][[0, 2, 3, 4, 5]].all()
        assert out["smiles"][0]["n_points"] == 5


def test_the_call_at_a_strike_equal_to_the_forward_is_the_otm_quote():
    # ADR-0008 §7: calls for K >= F. r = 0 and no dividend give a fallback forward of exactly S
    # (code mutant M10 made a K == F call ITM, so neither side of that strike had an IV).
    tau = 30 / 365
    strikes = np.array([440.0, 440.0])
    mids = black76.price(440.0, strikes, tau, 0.0, 0.2, [True, False])
    out = chain.price_chain(440.0, 0.0, [tau], np.zeros((1, 0)), np.zeros((1, 0)), [0, 0], strikes, [True, False],
                            mids, [True, True])
    assert out["expiries"]["forward"][0] == 440.0
    assert out["quotes"]["is_otm"].tolist() == [True, False]
    assert np.isfinite(out["quotes"]["iv"][0]) and np.isnan(out["quotes"]["iv"][1])


def test_iv_fail_when_the_american_iv_exists_but_the_european_mid_has_no_black_76_iv():
    # Parity puts F 10% below the lattice's own forward (as if the market knew a dividend the
    # schedule does not), and one call, OTM on F, is quoted near the lattice's upper bound: it has
    # an American IV on the lattice, but its European-equivalent mid is above DF F, so no Black-76
    # IV. IV_FAIL must come from that second solve too (code mutant M11 took it from the first only).
    spot, rate, tau = 400.0, 0.05, 2.0
    low = 0.9 * spot * np.exp(rate * tau)
    strikes = np.arange(370.0, 431.0, 10)
    both = np.concatenate([strikes, strikes])
    calls = np.r_[np.ones(strikes.size, bool), np.zeros(strikes.size, bool)]
    mids = black76.price(low, both, tau, rate, 0.2, calls)
    odd_strike = 1.05 * low
    odd_mid = 380.0          # below the lattice's A(5) (~399) and above DF F (~366)
    strike = np.r_[both, odd_strike]
    out = chain.price_chain(spot, rate, [tau], np.zeros((1, 0)), np.zeros((1, 0)), np.zeros(strike.size, int), strike,
                            np.r_[calls, True], np.r_[mids, odd_mid], np.r_[np.ones(both.size, bool), False])
    q = out["quotes"]
    lattice_forward = spot * np.exp(rate * tau)
    assert out["expiries"]["forward"][0] < 0.95 * lattice_forward and odd_mid > np.exp(-rate * tau) * out["expiries"]["forward"][0]
    assert q["is_otm"][-1] and np.isfinite(q["iv_american"][-1])
    assert iv.FAIL_NAMES[q["fail"][-1]] == "above_upper_bound"
    assert q["iv_flags"][-1] & chain.IV_FAIL and np.isnan(q["iv"][-1])


def test_two_premiums_two_columns():
    # D6: eep is a quote's own premium at its own American IV (OTM quotes and the near-K* quotes);
    # eep_partner is an ITM quote's premium at its partner's OTM IV, used by PARITY_OUTLIER only
    # (code mutant M12 stopped storing it).
    from volbt.pricing import lattice

    spot, rate, tau = 440.0, 0.0525, 90 / 365
    strikes = np.arange(380.0, 501.0, 10)
    both = np.concatenate([strikes, strikes])
    calls = np.r_[np.ones(strikes.size, bool), np.zeros(strikes.size, bool)]
    mids = lattice.crr(spot, both, tau, rate, 0.18, calls, steps=1000)["price"]
    out = chain.price_chain(spot, rate, [tau], np.zeros((1, 0)), np.zeros((1, 0)), np.zeros(both.size, int), both,
                            calls, mids, np.ones(both.size, bool))
    q = out["quotes"]
    otm, itm = q["is_otm"], ~q["is_otm"]
    assert np.all(np.isfinite(q["eep"][otm])) and np.all(np.isfinite(q["iv_american"][otm]))
    assert np.all(np.isnan(q["eep_partner"][otm])) and np.all(np.isfinite(q["eep_partner"][itm]))
    # eep_partner is the lattice premium at the partner's OTM IV, exactly.
    partner = {(k, c): i for i, (k, c) in enumerate(zip(both, calls))}
    for i in np.flatnonzero(itm):
        j = partner[(both[i], not calls[i])]
        expected = lattice.early_exercise_premium(spot, both[i], tau, rate, q["iv"][j], calls[i])
        assert q["eep_partner"][i] == pytest.approx(float(expected[0]), abs=1e-12)
    # The own premium of an OTM put is the lattice's A - E at its own American IV.
    puts = np.flatnonzero(otm & ~calls)
    american = lattice.crr(spot, both[puts], tau, rate, q["iv_american"][puts], False)["price"]
    european = lattice.crr_european(spot, both[puts], tau, rate, q["iv_american"][puts], False)
    assert np.allclose(q["eep"][puts], american - european, atol=1e-6)
    assert np.allclose(american, mids[puts], atol=1e-6)
    # ITM quotes have eep only where they set the forward: one per strike of the 10 nearest K*.
    assert np.isfinite(q["eep"][itm]).sum() == 10 == out["expiries"]["n_deamericanised"][0] // 2


def test_a_smile_whose_nodes_miss_k_0_says_so():
    # All valid OTM nodes above the forward: the ATM IV is an extrapolation (code mutant M16
    # never set SMILE_ATM_OUTSIDE; 63 real smiles have it).
    tau = 30 / 365
    forward = 440.0 * np.exp(0.05 * tau)
    k = np.array([445.0, 450.0, 455.0, 460.0, 465.0])
    mids = black76.price(forward, k, tau, 0.05, 0.2, True)
    out = chain.price_chain(440.0, 0.05, [tau], np.zeros((1, 0)), np.zeros((1, 0)), np.zeros(k.size, int), k,
                            np.ones(k.size, bool), mids, np.ones(k.size, bool))
    assert out["smiles"][0]["fit_flags"] & smile.SMILE_ATM_OUTSIDE
    assert out["smiles"][0]["n_points"] == 5


def test_a_forward_that_cannot_be_de_americanised_says_so():
    # D2: the near-K* calls are quoted below what the lattice gives them at its lowest sigma (spot
    # 440, but quotes on a forward of 430), so none has an American IV. The forward is then raw
    # parity, and `method` and the smile say it; no NaN premium reaches F, and the failures carry
    # their cause, not "below_lower_bound".
    spot, rate, tau = 440.0, 0.05, 7 / 365
    strikes = np.arange(420.0, 441.0, 5)
    both = np.concatenate([strikes, strikes])
    calls = np.r_[np.ones(strikes.size, bool), np.zeros(strikes.size, bool)]
    mids = black76.price(430.0, both, tau, rate, 0.10, calls)
    out = chain.price_chain(spot, rate, [tau], np.zeros((1, 0)), np.zeros((1, 0)), np.zeros(both.size, int), both, calls,
                            mids, np.ones(both.size, bool))
    e, q = out["expiries"], out["quotes"]
    assert chain.METHOD_NAMES[e["method"][0]] == "parity_median5_raw"
    assert np.isfinite(e["forward"][0]) and e["forward"][0] == e["forward_raw"][0]
    assert out["smiles"][0]["fit_flags"] & smile.SMILE_FORWARD_RAW
    reasons = {iv.FAIL_NAMES[f] for f in q["fail"][calls & ~q["is_otm"]] if f}
    assert "below_lower_bound" not in reasons
    assert np.all(np.isnan(q["eep"][calls & (both < 435)]))
