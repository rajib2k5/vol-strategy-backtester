"""Tests for volbt.illustrative. Expected values are literals worked out by hand
(arithmetic in comments), never recomputed with the code under test."""

import numpy as np
import pytest

from volbt import illustrative as ill


# --- shipped parameters ----------------------------------------------------------------

def test_shipped_parameters():
    # Changing the look of the hero surface should be a deliberate edit to this test too.
    assert ill.RHO == -0.7
    assert ill.ETA == 1.0
    assert ill.SIGMA_ATM_SHORT == 0.16
    assert ill.SIGMA_ATM_LONG == 0.20


# --- total variance --------------------------------------------------------------------

@pytest.mark.parametrize("rho", [-0.7, 0.0, 0.3, -0.99])
@pytest.mark.parametrize("theta", [0.000490958904, 0.0165, 0.04, 0.5])
def test_total_variance_at_the_money_equals_theta(theta, rho):
    # k = 0 makes phi*k = 0, so
    #   w = theta/2 * (1 + rho*0 + sqrt((0 + rho)^2 + 1 - rho^2))
    #     = theta/2 * (1 + sqrt(rho^2 + 1 - rho^2))
    #     = theta/2 * (1 + sqrt(1))
    #     = theta/2 * 2 = theta        for ANY rho.
    # (This is why theta is called the ATM total variance.)
    assert ill.total_variance(0.0, theta, rho=rho, eta=1.0) == pytest.approx(theta, rel=1e-14)


def test_total_variance_off_the_money_matches_hand_value():
    # theta = 0.04 (sigma_atm 20% for one year), rho = -0.7, eta = 1.
    #   phi = eta / sqrt(theta) = 1 / 0.2 = 5
    # Put side, k = -0.1:
    #   phi*k = -0.5;  rho*phi*k = (-0.7)(-0.5) = 0.35
    #   (phi*k + rho)^2 = (-1.2)^2 = 1.44;  + 1 - rho^2 = 1.44 + 1 - 0.49 = 1.95
    #   sqrt(1.95) = 1.3964240043768941
    #   w = 0.04/2 * (1 + 0.35 + 1.3964240043768941) = 0.02 * 2.7464240043768941
    #     = 0.054928480087537882
    assert ill.total_variance(-0.1, 0.04, rho=-0.7, eta=1.0) == pytest.approx(
        0.054928480087537882, rel=1e-12)
    # Call side, k = +0.1:
    #   phi*k = 0.5;  rho*phi*k = -0.35
    #   (0.5 - 0.7)^2 = 0.04;  + 0.51 = 0.55;  sqrt(0.55) = 0.74161984870956629
    #   w = 0.02 * (1 - 0.35 + 0.74161984870956629) = 0.02 * 1.3916198487095663
    #     = 0.027832396974191326
    assert ill.total_variance(0.1, 0.04, rho=-0.7, eta=1.0) == pytest.approx(
        0.027832396974191326, rel=1e-12)


def test_total_variance_broadcasts_expiries_down_rows_and_strikes_across_columns():
    theta = np.array([[0.04], [0.09]])  # shape (2, 1): two expiries
    k = np.array([-0.1, 0.0, 0.1])      # shape (3,):   three strikes
    w = ill.total_variance(k, theta, rho=-0.7, eta=1.0)
    assert w.shape == (2, 3)
    # Row 0 is the hand-worked theta = 0.04 case above.
    assert w[0] == pytest.approx([0.054928480087537882, 0.04, 0.027832396974191326], rel=1e-12)


# --- ATM term structure ----------------------------------------------------------------

def test_sigma_atm_is_a_straight_line_between_the_endpoints():
    assert ill.sigma_atm(7) == pytest.approx(0.16, rel=1e-14)
    assert ill.sigma_atm(365) == pytest.approx(0.20, rel=1e-14)
    # Halfway: (186 - 7) / (365 - 7) = 179 / 358 = 0.5, so 0.16 + 0.04 * 0.5 = 0.18.
    assert ill.sigma_atm(186) == pytest.approx(0.18, rel=1e-14)


def test_atm_total_variance_is_sigma_squared_times_years():
    # dte = 186: sigma = 0.18, T = 186/365 years.
    #   theta = 0.18^2 * 186/365 = 0.0324 * 186 / 365 = 6.0264 / 365 = 0.016510684931506849
    assert ill.atm_total_variance(186) == pytest.approx(0.016510684931506849, rel=1e-12)
    # dte = 365 is exactly one year: theta = 0.2^2 * 1 = 0.04.
    assert ill.atm_total_variance(365) == pytest.approx(0.04, rel=1e-14)


# --- the grid --------------------------------------------------------------------------

def test_grid_axes_and_shape():
    k_grid, dte_grid, iv = ill.iv_grid()
    assert len(k_grid) == 26 and len(dte_grid) == 20
    # iv[i_dte][j_k]: rows are expiries (20), columns are strikes (26). 20 != 26, so a
    # transposed table is caught by the shape alone.
    assert iv.shape == (20, 26)
    assert k_grid[0] == -0.30 and k_grid[-1] == 0.20
    assert dte_grid[0] == 7 and dte_grid[-1] == 365
    assert np.all(np.diff(k_grid) > 0) and np.all(np.diff(dte_grid) > 0)
    # Steps of 0.5 / 25 = 0.02, so -0.30 + 15 * 0.02 = 0 lands exactly on the grid.
    assert k_grid[15] == 0.0
    # Exact decimals, not -0.27999999999999997 (np.linspace's float noise).
    assert k_grid[1] == -0.28 and k_grid[10] == -0.1 and k_grid[20] == 0.1
    assert np.issubdtype(dte_grid.dtype, np.integer)


def test_iv_at_the_money_equals_sigma_atm():
    k_grid, dte_grid, iv = ill.iv_grid()
    # At k = 0, w = theta = sigma_atm^2 * T, so iv = sqrt(w / T) = sigma_atm.
    assert iv[0, 15] == pytest.approx(0.16, rel=1e-12)    # dte = 7
    assert iv[-1, 15] == pytest.approx(0.20, rel=1e-12)   # dte = 365
    assert iv[:, 15] == pytest.approx(ill.sigma_atm(dte_grid), rel=1e-12)


def test_iv_one_year_off_the_money_matches_hand_value():
    k_grid, dte_grid, iv = ill.iv_grid()
    assert dte_grid[-1] == 365 and k_grid[10] == -0.1
    # dte = 365 means T = 1, so iv = sqrt(w). From the total-variance test above,
    # w(k=-0.1, theta=0.04) = 0.054928480087537882
    #   iv = sqrt(0.054928480087537882) = 0.23436825742309448
    assert iv[-1, 10] == pytest.approx(0.23436825742309448, rel=1e-12)
    # k = +0.1 is column 15 + 5 = 20: w = 0.027832396974191326, iv = 0.16683044378707181
    assert iv[-1, 20] == pytest.approx(0.16683044378707181, rel=1e-12)


def test_iv_short_expiry_hand_value_checks_the_time_conversion():
    k_grid, dte_grid, iv = ill.iv_grid()
    assert dte_grid[0] == 7
    # dte = 7: T = 7/365 = 0.019178; sigma_atm = 0.16
    #   theta = 0.16^2 * 7/365 = 0.0256 * 7 / 365 = 0.00049095890
    #   phi = 1 / sqrt(theta) = 1 / 0.0221575925 = 45.131257
    #   k = -0.1: phi*k = -4.5131257;  rho*phi*k = 3.1591880
    #   (phi*k + rho)^2 + 1 - rho^2 = (-5.2131257)^2 + 0.51 = 27.176679 + 0.51 = 27.686680
    #   sqrt(27.686680) = 5.2618
    #   w = theta/2 * (1 + 3.1591880 + 5.2618) = 0.00024547945 * 9.4210 = 0.0023126622
    #   iv = sqrt(w / T) = sqrt(0.0023126622 * 365/7) = sqrt(0.120588) = 0.34725901
    assert iv[0, 10] == pytest.approx(0.34725900552708568, rel=1e-9)


def test_equity_skew_low_strikes_have_higher_vol_than_high_strikes():
    k_grid, _, iv = ill.iv_grid()
    j_put, j_call = 10, 20   # k = -0.10 and k = +0.10
    assert k_grid[j_put] == -0.1 and k_grid[j_call] == 0.1
    # rho < 0 puts more variance on the low-strike side at every expiry.
    assert np.all(iv[:, j_put] > iv[:, j_call])


def test_positive_rho_flips_the_skew():
    _, _, iv = ill.iv_grid(rho=0.7)
    # With rho = +0.7 the smile mirrors: w(k; +rho) = w(-k; -rho), so the call side is higher.
    assert np.all(iv[:, 10] < iv[:, 20])


def test_iv_is_finite_and_positive_everywhere():
    _, _, iv = ill.iv_grid()
    assert np.all(np.isfinite(iv)) and np.all(iv > 0)


# --- no-arbitrage checks ---------------------------------------------------------------

def test_shipped_parameters_pass_every_check():
    _, dte_grid, _ = ill.iv_grid()
    # With phi = eta/sqrt(theta):  theta*phi = eta*sqrt(theta)  and  theta*phi^2 = eta^2.
    #   butterfly_1: worst case is the longest expiry, theta = 0.04:
    #       1.0 * 0.2 * (1 + 0.7) = 0.34 < 4
    #   butterfly_2: 1.0^2 * 1.7 = 1.7 <= 4
    #   calendar: sigma_atm and T both grow, so theta = sigma^2 * T only grows, and with
    #       phi = eta/sqrt(theta) the whole w(k, T) table grows with it (see the tests below).
    assert ill.no_arbitrage_checks(dte_grid) == {
        "butterfly_1": True, "butterfly_2": True, "calendar": True}


def test_eta_2_breaks_butterfly_2_only():
    _, dte_grid, _ = ill.iv_grid()
    # eta = 2: theta*phi^2*(1+|rho|) = 2^2 * 1.7 = 6.8 > 4  -> butterfly_2 fails.
    # butterfly_1 still holds: theta*phi*(1+|rho|) = 2 * 0.2 * 1.7 = 0.68 < 4 at theta = 0.04.
    assert ill.no_arbitrage_checks(dte_grid, eta=2.0) == {
        "butterfly_1": True, "butterfly_2": False, "calendar": True}


def test_butterfly_2_threshold_depends_on_abs_rho():
    # theta*phi^2 = eta^2 for every expiry, so butterfly_2 reads: eta^2 * (1 + |rho|) <= 4.
    # rho = +0.5 and rho = -0.5 both give (1 + |rho|) = 1.5:
    #   eta = 1.6: 2.56 * 1.5 = 3.84 <= 4  -> passes
    #   eta = 1.7: 2.89 * 1.5 = 4.335 > 4  -> fails
    for rho in (0.5, -0.5):
        assert ill.no_arbitrage_checks([365], rho=rho, eta=1.6)["butterfly_2"] is True
        assert ill.no_arbitrage_checks([365], rho=rho, eta=1.7)["butterfly_2"] is False


def test_large_eta_breaks_butterfly_1():
    # dte = 365: theta = 0.04, sqrt(theta) = 0.2, phi = eta / 0.2 = 5 * eta,
    # so theta*phi*(1+|rho|) = 0.04 * 5 * eta * 1.7 = 0.34 * eta.
    #   eta = 12: 0.34 * 12 = 4.08 >= 4  -> fails (strict "< 4")
    #   eta = 11: 0.34 * 11 = 3.74 <  4  -> passes
    assert ill.no_arbitrage_checks([365], eta=12.0)["butterfly_1"] is False
    assert ill.no_arbitrage_checks([365], eta=11.0)["butterfly_1"] is True


def test_calendar_fails_when_total_variance_decreases_with_expiry():
    # Expiries listed longest first: theta(365) = 0.04 then theta(7) = 0.00049 is a decrease.
    assert ill.no_arbitrage_checks([365, 7])["calendar"] is False
    assert ill.no_arbitrage_checks([7, 365])["calendar"] is True


def test_calendar_allows_equal_total_variance():
    # Non-decreasing: the same expiry twice gives equal theta, which is allowed.
    assert ill.no_arbitrage_checks([30, 30])["calendar"] is True


# --- butterfly boundaries, with exactly representable numbers ----------------------------
# rho = 0 makes 1 + |rho| exactly 1, and theta = 1, 16 have exact square roots, so every
# number below is exact in binary floating point and the comparison sits ON the boundary.

def test_butterfly_2_passes_exactly_at_4():
    # theta = 1: phi = eta / sqrt(1) = eta, so theta*phi^2*(1+|rho|) = eta^2 = 2^2 = 4.
    # The condition is "<= 4", so exactly 4 passes.
    assert ill.butterfly_conditions([1.0], rho=0.0, eta=2.0) == {
        "butterfly_1": True, "butterfly_2": True}


def test_butterfly_2_fails_just_above_4_and_passes_just_below():
    above = np.nextafter(2.0, 3.0)   # 2.0000000000000004: eta^2 = 4.000000000000002 > 4
    below = np.nextafter(2.0, 0.0)   # 1.9999999999999998: eta^2 = 3.999999999999999 < 4
    assert ill.butterfly_conditions([1.0], rho=0.0, eta=above)["butterfly_2"] is False
    assert ill.butterfly_conditions([1.0], rho=0.0, eta=below)["butterfly_2"] is True


def test_butterfly_1_fails_exactly_at_4_because_it_is_strict():
    # eta = 1, theta = 16: phi = 1/sqrt(16) = 0.25 and theta*phi*(1+|rho|) = 16 * 0.25 * 1 = 4.
    # The condition is "< 4", so exactly 4 fails. (butterfly_2 here is 16 * 0.0625 = 1 <= 4.)
    assert ill.butterfly_conditions([16.0], rho=0.0, eta=1.0) == {
        "butterfly_1": False, "butterfly_2": True}


def test_butterfly_1_passes_below_4_and_fails_above():
    # theta*phi = eta*sqrt(theta) = sqrt(theta) for eta = 1: sqrt(15.99) = 3.9987 < 4, sqrt(16.01) = 4.0013 > 4.
    assert ill.butterfly_conditions([15.99], rho=0.0, eta=1.0)["butterfly_1"] is True
    assert ill.butterfly_conditions([16.01], rho=0.0, eta=1.0)["butterfly_1"] is False


def test_butterfly_conditions_hold_only_if_every_expiry_passes():
    # One bad expiry (theta = 16, exactly 4) fails the whole set, wherever it sits in the array.
    assert ill.butterfly_conditions([1.0, 16.0], rho=0.0, eta=1.0)["butterfly_1"] is False
    assert ill.butterfly_conditions([16.0, 1.0], rho=0.0, eta=1.0)["butterfly_1"] is False
    assert ill.butterfly_conditions([1.0, 4.0], rho=0.0, eta=1.0)["butterfly_1"] is True


def test_butterfly_conditions_use_abs_rho_in_the_boundary():
    # rho = -1: 1 + |rho| = 2. eta = 1, theta = 4: theta*phi*(1+|rho|) = 4 * 0.5 * 2 = 4 -> fails (strict);
    # butterfly_2: 4 * 0.25 * 2 = 2 <= 4 passes. Same for rho = +1.
    for rho in (-1.0, 1.0):
        assert ill.butterfly_conditions([4.0], rho=rho, eta=1.0) == {
            "butterfly_1": False, "butterfly_2": True}


# --- calendar: a check that can actually fail --------------------------------------------

def test_inverted_term_structure_fails_calendar_only():
    _, dte_grid, _ = ill.iv_grid()
    # 7-day vol 100%, one-year vol 5%: theta(7) = 1.0^2 * 7/365 = 0.01918 but
    # theta(365) = 0.05^2 * 1 = 0.0025, so theta FALLS with expiry. Butterfly numbers stay tiny
    # (eta = 1, rho = -0.7: eta^2 * 1.7 = 1.7 <= 4), so only the calendar check can object.
    assert ill.no_arbitrage_checks(dte_grid, sigma_short=1.0, sigma_long=0.05) == {
        "butterfly_1": True, "butterfly_2": True, "calendar": False}


def test_flat_term_structure_is_still_calendar_free():
    _, dte_grid, _ = ill.iv_grid()
    # Constant 20% vol: theta = 0.04 * T grows with T, so w grows at every k.
    assert ill.no_arbitrage_checks(dte_grid, sigma_short=0.2, sigma_long=0.2)["calendar"] is True


def test_term_structure_parameters_reach_the_grid():
    _, dte_grid, iv = ill.iv_grid(sigma_short=0.30, sigma_long=0.25)
    # k = 0 is column 15; there iv = sigma_atm, which is the straight line 0.30 -> 0.25.
    assert iv[0, 15] == pytest.approx(0.30, rel=1e-12)
    assert iv[-1, 15] == pytest.approx(0.25, rel=1e-12)


def test_calendar_condition_compares_w_at_every_strike_not_just_theta():
    # Two expiries, two strikes. theta (the k = 0 column here) rises 1 -> 2, but at the second
    # strike w FALLS 3 -> 2.5: a longer-dated option cheaper than a shorter one at that strike.
    theta = [1.0, 2.0]
    assert ill.calendar_condition(theta, [[1.0, 3.0], [2.0, 2.5]]) is False
    # Same table with the second strike no longer falling (equal is allowed).
    assert ill.calendar_condition(theta, [[1.0, 3.0], [2.0, 3.0]]) is True


def test_calendar_condition_fails_when_theta_falls_even_if_w_rows_look_fine():
    # w rises in both columns, but theta (a separate input) falls: still a violation.
    assert ill.calendar_condition([2.0, 1.0], [[1.0, 3.0], [2.0, 4.0]]) is False


def test_calendar_condition_checks_every_adjacent_pair_of_expiries():
    # The dip is only between the 2nd and 3rd expiry.
    w = [[1.0], [2.0], [1.5], [3.0]]
    assert ill.calendar_condition([1.0, 2.0, 2.0, 3.0], w) is False


def test_no_arbitrage_checks_hands_the_real_w_table_to_the_calendar_check(monkeypatch):
    # For SSVI with phi = eta/sqrt(theta), theta rising already implies w rises (Theorem 4.1, see
    # the docstring), so no input can make the w comparison disagree with the theta one. This
    # spy pins the wiring instead: the table handed over is the true w(k, T), row per expiry.
    seen = {}

    def spy(theta, w):
        seen["theta"], seen["w"] = np.asarray(theta), np.asarray(w)
        return True

    monkeypatch.setattr(ill, "calendar_condition", spy)
    ill.no_arbitrage_checks([365, 365], k=[-0.1, 0.0, 0.1])
    assert seen["theta"] == pytest.approx([0.04, 0.04], rel=1e-14)
    assert seen["w"].shape == (2, 3)
    # The hand values from test_total_variance_off_the_money_matches_hand_value (theta = 0.04).
    assert seen["w"][0] == pytest.approx([0.054928480087537882, 0.04, 0.027832396974191326], rel=1e-12)


def test_shipped_surface_has_total_variance_rising_with_expiry_at_every_drawn_strike():
    k_grid, dte_grid, iv = ill.iv_grid()
    # Rebuild w from the drawn IVs themselves: w = iv^2 * T, T = dte / 365 (column vector).
    w = iv**2 * (dte_grid / 365)[:, None]
    assert np.all(np.diff(w, axis=0) > 0)


@pytest.mark.parametrize("rho", [-0.99, -0.7, -0.1, 0.3, 0.7, 0.99])
def test_phi_condition_of_gatheral_jacquier_theorem_4_1_holds_for_phi_eta_over_sqrt_theta(rho):
    # Theorem 4.1's second condition: 0 <= d(theta*phi)/d(theta) <= (1 + sqrt(1 - rho^2)) / rho^2 * phi.
    # By hand for phi = eta/sqrt(theta): theta*phi = eta*sqrt(theta), derivative = eta/(2 sqrt(theta)) = phi/2.
    # So the ratio derivative/phi is 1/2, and the upper bound ratio is (1 + sqrt(1 - rho^2)) / rho^2,
    # which is >= 1 for every |rho| < 1 (shipped rho = -0.7: (1 + sqrt(0.51)) / 0.49 = 3.4981).
    thetas = np.geomspace(1e-4, 1.0, 40)           # spans theta(7d) = 0.00049 to theta(365d) = 0.04 and beyond
    h = thetas * 1e-6                               # central difference step, relative to theta
    theta_phi = lambda t: t * ill.phi(t, eta=1.0)   # noqa: E731 - the quantity whose derivative is bounded
    derivative = (theta_phi(thetas + h) - theta_phi(thetas - h)) / (2 * h)
    ratio = derivative / ill.phi(thetas, eta=1.0)
    assert ratio == pytest.approx(0.5, rel=1e-6)
    upper_ratio = (1 + np.sqrt(1 - rho**2)) / rho**2
    assert np.all(ratio >= 0) and np.all(ratio <= upper_ratio)


def test_shipped_rho_upper_bound_ratio_matches_hand_value():
    # rho = -0.7: rho^2 = 0.49, sqrt(1 - 0.49) = sqrt(0.51) = 0.714143, so (1 + 0.714143) / 0.49 = 3.49825.
    assert (1 + np.sqrt(1 - ill.RHO**2)) / ill.RHO**2 == pytest.approx(3.49825, rel=1e-5)
