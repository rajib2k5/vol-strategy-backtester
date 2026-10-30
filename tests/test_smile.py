"""The smile and the surface in total variance (ADR-0004 tests 5, 9, 10 and 11, and the wing clip)."""

import numpy as np
import pytest

from volbt.pricing import smile


def nodes(ivs_by_k, tau):
    k = np.array(sorted(ivs_by_k))
    return k, np.array([ivs_by_k[x] for x in k]) ** 2 * tau


def test_interpolation_is_linear_in_total_variance():
    # ADR-0004 test 5: 0.22 at k = -0.05 and 0.18 at 0, tau = 0.1. At k = -0.025,
    # w = 0.5 (0.22^2 + 0.18^2) 0.1 = 0.004040, so sigma = 0.2010 (linear in vol would give 0.2000).
    k, w = nodes({-0.05: 0.22, 0.0: 0.18}, 0.1)
    var, beyond = smile.smile_variance(-0.025, k, w)
    assert float(var) == pytest.approx(0.004040, abs=5e-9) and not bool(beyond)
    assert float(smile.smile_iv(-0.025, 0.1, k, w)[0]) == pytest.approx(0.2010, abs=5e-5)


def test_strike_extrapolation_is_not_flat():
    # ADR-0004 test 9: 0.22 at -0.10 and 0.20 at -0.05, tau = 0.1. At -0.15 the slope in |k| is
    # 0.0168, inside [0, 2], so w = 0.00568 and sigma = 0.2383; a flat rule would give 0.22.
    k, w = nodes({-0.10: 0.22, -0.05: 0.20}, 0.1)
    assert smile.wing_slope(w[1], w[0], k[1], k[0]) == pytest.approx(0.0168)
    sigma, beyond = smile.smile_iv(-0.15, 0.1, k, w)
    assert float(smile.smile_variance(-0.15, k, w)[0]) == pytest.approx(0.00568, abs=5e-9)
    assert float(sigma) == pytest.approx(0.2383, abs=5e-5) and bool(beyond)
    flags = smile.surface_iv(np.array([-0.15]), 0.1, [(0.1, k, w)])[1]
    assert int(flags[0]) == smile.SURFACE_EXTRAP_STRIKE


def test_a_falling_wing_is_clipped_to_flat_and_a_steep_one_to_lees_bound():
    # Falling away from the money: slope 0, so the far IV holds at the last node's total variance.
    k, w = np.array([-0.10, -0.05, 0.0]), np.array([0.004, 0.005, 0.006])
    assert float(smile.smile_variance(-0.30, k, w)[0]) == pytest.approx(0.004)
    # Steeper than 2 per unit of |k|: clipped to 2.
    k, w = np.array([0.0, 0.05, 0.10]), np.array([0.004, 0.005, 0.5])
    assert float(smile.smile_variance(0.20, k, w)[0]) == pytest.approx(0.5 + 2.0 * 0.10)


def test_tenor_extrapolation_holds_iv_along_k_over_sqrt_tau():
    # ADR-0004 test 10: one expiry at 14/365 with 0.22 at k = -0.05 and 0.18 at 0. A 7-day contract
    # at k = -0.025 reads the smile at k' = -0.025 sqrt(2) = -0.03536: sigma = 0.2091, and 0.2010 at the same k.
    tau_near = 14 / 365
    k, w = nodes({-0.05: 0.22, 0.0: 0.18}, tau_near)
    sigma, flags = smile.surface_iv(np.array([-0.025]), 7 / 365, [(tau_near, k, w)])
    assert float(sigma[0]) == pytest.approx(0.2091, abs=5e-5)
    assert int(flags[0]) == smile.SURFACE_EXTRAP_TENOR
    assert float(smile.smile_iv(-0.025, tau_near, k, w)[0]) == pytest.approx(0.2010, abs=5e-5)


def test_cross_expiry_interpolation_when_the_own_expiry_is_absent():
    # ADR-0004 test 11: a 30-day contract between listed expiries at 14 and 51 days: linear w in tau
    # at fixed k, flagged SURFACE_CROSS_EXPIRY, no exception.
    t1, t2, tau = 14 / 365, 51 / 365, 30 / 365
    k1, w1 = nodes({-0.1: 0.25, -0.05: 0.21, 0.0: 0.18, 0.05: 0.16, 0.1: 0.17}, t1)
    k2, w2 = nodes({-0.1: 0.23, -0.05: 0.205, 0.0: 0.185, 0.05: 0.17, 0.1: 0.168}, t2)
    sigma, flags = smile.surface_iv(np.array([0.0]), tau, [(t1, k1, w1), (t2, k2, w2)])
    w = 0.18**2 * t1 + (0.185**2 * t2 - 0.18**2 * t1) * (tau - t1) / (t2 - t1)
    assert float(sigma[0]) == pytest.approx(np.sqrt(w / tau), abs=1e-12)
    assert int(flags[0]) == smile.SURFACE_CROSS_EXPIRY


def test_the_own_expiry_is_read_directly():
    t1 = 30 / 365
    k1, w1 = nodes({-0.1: 0.25, -0.05: 0.21, 0.0: 0.18, 0.05: 0.16, 0.1: 0.17}, t1)
    sigma, flags = smile.surface_iv(np.array([0.0, 0.2]), t1, [(t1, k1, w1)])
    assert float(sigma[0]) == pytest.approx(0.18) and list(flags) == [0, smile.SURFACE_EXTRAP_STRIKE]


def test_a_longer_tenor_than_the_back_expiry_extrapolates_too():
    t1 = 30 / 365
    k1, w1 = nodes({-0.1: 0.25, 0.0: 0.18, 0.1: 0.17}, t1)
    sigma, flags = smile.surface_iv(np.array([0.0]), 60 / 365, [(t1, k1, w1)])
    assert float(sigma[0]) == pytest.approx(0.18) and int(flags[0]) == smile.SURFACE_EXTRAP_TENOR


def test_no_usable_expiry_is_an_error_not_a_guess():
    with pytest.raises(ValueError, match="no usable expiry"):
        smile.surface_iv(np.array([0.0]), 0.1, [])


def test_nodes_are_sorted_and_nan_free():
    k, w = smile.smile_nodes([0.05, -0.1, np.nan, 0.0], [0.17, 0.25, 0.2, np.nan], 0.5)
    assert k.tolist() == [-0.1, 0.05] and w.tolist() == pytest.approx([0.25**2 * 0.5, 0.17**2 * 0.5])


# --- the calendar constraint (M2 review, code claim 7; amendment D5; round 2, decision E1) -------------

def test_the_cross_expiry_flag_marks_a_k_beyond_either_smile():
    # Inside the first smile's nodes, beyond the second's: still a strike extrapolation (code
    # mutant M15 flagged only k beyond both).
    t1, t2 = 14 / 365, 51 / 365
    k1, w1 = nodes({-0.2: 0.30, -0.1: 0.25, 0.0: 0.18, 0.1: 0.17, 0.2: 0.18}, t1)
    k2, w2 = nodes({-0.1: 0.23, -0.05: 0.205, 0.0: 0.185, 0.05: 0.17, 0.1: 0.168}, t2)
    _, flags = smile.surface_iv(np.array([-0.15, 0.0]), 30 / 365, [(t1, k1, w1), (t2, k2, w2)])
    assert int(flags[0]) & smile.SURFACE_EXTRAP_STRIKE and not int(flags[1]) & smile.SURFACE_EXTRAP_STRIKE


def crossing_expiries():
    """Two smiles that cross: at k = 0.2 the 60-day w (0.0106) is below the 30-day one (0.0138).

    The review's own example (code claim 7): w 0.0138 -> 0.0122 -> 0.0106 at k = 0.2 from 30 to 60 days.
    """
    t1, t2 = 30 / 365, 60 / 365
    k = np.array([-0.2, -0.1, 0.0, 0.1, 0.2])
    w1 = np.array([0.0110, 0.0060, 0.0030, 0.0050, 0.0138])
    w2 = np.array([0.0180, 0.0100, 0.0055, 0.0070, 0.0106])
    return [(t1, k, w1), (t2, k, w2)]


def total_variance(k, tau, expiries):
    sigma, flags = smile.surface_iv(np.asarray(k, dtype=float), tau, expiries)
    return sigma**2 * tau, flags


def test_the_floor_holds_w_at_a_crossing_and_says_so():
    expiries = crossing_expiries()
    for days in (30, 45, 60, 90):
        w, flags = total_variance([0.2], days / 365, expiries)
        assert float(w[0]) >= 0.0138 - 1e-12
        # Floored at 45 and 60 days; at 90, step 5 off the 60-day smile is already 0.0139.
        assert bool(int(flags[0]) & smile.SURFACE_CALENDAR_ADJUSTED) is (days in (45, 60))
    # At 45 days, between the expiries: linear between the floored values, i.e. flat at 0.0138
    # (the plain rule gave 0.0122).
    assert float(total_variance([0.2], 45 / 365, expiries)[0][0]) == pytest.approx(0.0138)
    # Where the smiles do not cross, nothing changes and nothing is flagged.
    w, flags = total_variance([0.0], 45 / 365, expiries)
    assert float(w[0]) == pytest.approx(0.0030 + 0.0025 * 0.5) and not int(flags[0]) & smile.SURFACE_CALENDAR_ADJUSTED


def test_w_never_falls_with_tenor_at_any_k_on_random_surfaces():
    # Random smiles at random tenors, read at every k on a fine grid of tenors from 1 day to 3
    # years, before, between and past the expiries: w(k, tau) never falls as tau grows.
    rng = np.random.default_rng(7)
    grid_k = np.linspace(-0.6, 0.4, 41)
    grid_tau = np.linspace(1, 1095, 220) / 365
    for _ in range(40):
        taus = np.sort(rng.uniform(3, 700, rng.integers(1, 6))) / 365
        expiries = []
        for tau in taus:
            k = np.sort(rng.uniform(-0.4, 0.3, rng.integers(5, 12)))
            sigma = np.clip(0.18 - 0.4 * k + rng.normal(0, 0.05, k.size), 0.03, 1.5)
            expiries.append((float(tau), k, sigma**2 * tau))
        w = np.vstack([total_variance(grid_k, tau, expiries)[0] for tau in grid_tau])
        assert np.all(np.diff(w, axis=0) >= -1e-12), np.min(np.diff(w, axis=0))


def test_tenor_extrapolation_takes_the_monotone_envelope_of_step_5():
    # A front smile so steep just above the money that holding IV along k/sqrt(tau) makes w FALL
    # as tau grows toward the front expiry: at k = 0.03 step 5 gives 0.00172 at 6 days but the
    # 10-day expiry itself has 0.001575. The envelope takes the minimum over the tenors up to the
    # front expiry, so w(6 days) <= w(10 days), flagged.
    t1 = 10 / 365
    k, w = np.array([-0.05, 0.0, 0.02, 0.06, 0.1]), np.array([0.0012, 0.0001, 0.0001, 0.0060, 0.0062])
    plain6 = float(smile.smile_variance(0.03 * np.sqrt(10 / 6), k, w)[0]) * 6 / 10
    front = float(smile.smile_variance(0.03, k, w)[0])
    assert plain6 > front
    w6, f6 = total_variance([0.03], 6 / 365, [(t1, k, w)])
    w3, _ = total_variance([0.03], 3 / 365, [(t1, k, w)])
    assert float(w3[0]) <= float(w6[0]) <= front + 1e-15
    assert float(w6[0]) == pytest.approx(front) and int(f6[0]) & smile.SURFACE_CALENDAR_ADJUSTED


def wing_and_quote():
    """A 30-day smile quoted on [-0.10, 0.10] whose left wing extrapolates steeply, and a 300-day
    smile quoted down to k = -0.5. At k = -0.4 the 30-day wing (extrapolated) gives w = 0.0550,
    above the 300-day QUOTE there (0.0300): the review's 2020-02-28 case in miniature."""
    t1, t2 = 30 / 365, 300 / 365
    k1 = np.array([-0.10, -0.05, 0.0, 0.05, 0.10])
    w1 = np.array([0.0100, 0.0025, 0.0016, 0.0013, 0.0014])          # left wing slope 0.15 per unit of |k|
    k2 = np.array([-0.5, -0.4, -0.2, 0.0, 0.2])
    w2 = np.array([0.0340, 0.0300, 0.0200, 0.0150, 0.0160])
    return [(t1, k1, w1), (t2, k2, w2)]


def test_an_extrapolated_wing_never_moves_a_quoted_node():
    # Round 2, design claim 1: the first floor took the running maximum over every expiry's w, its
    # extrapolated wings included, and raised the 300-day quote at k = -0.4 to the 30-day wing.
    expiries = wing_and_quote()
    wing = float(smile.smile_variance(-0.4, expiries[0][1], expiries[0][2])[0])
    assert wing == pytest.approx(0.0100 + 0.15 * 0.30) and wing > 0.0300
    w, flags = total_variance([-0.4, -0.2, 0.0], 300 / 365, expiries)
    assert w.tolist() == pytest.approx([0.0300, 0.0200, 0.0150], rel=1e-12)       # the quotes, exactly
    assert not (np.asarray(flags) & smile.SURFACE_CALENDAR_ADJUSTED).any()


def test_an_extrapolated_wing_above_a_later_quote_is_lowered_to_it_and_says_so():
    # The 30-day wing at k = -0.4 (0.0550) stands above the next quoted value (the 300-day 0.0300):
    # it is held at 0.0300, the bit says the constraint moved it (down), and w rises from there.
    expiries = wing_and_quote()
    w, flags = total_variance([-0.4], 30 / 365, expiries)
    assert float(w[0]) == pytest.approx(0.0300) and int(flags[0]) & smile.SURFACE_CALENDAR_ADJUSTED
    assert int(flags[0]) & smile.SURFACE_EXTRAP_STRIKE
    path = np.array([float(total_variance([-0.4], days / 365, expiries)[0][0]) for days in range(5, 400, 5)])
    assert np.all(np.diff(path) >= -1e-15)              # flat at 0.0300 to float noise, then rising
    # Before the front, step 5 off the 30-day smile is capped at that adjusted value: never above it.
    before = float(total_variance([-0.4], 10 / 365, expiries)[0][0])
    assert before <= 0.0300 + 1e-15


def test_calendar_variance_raises_quotes_clamps_extrapolations_and_skips_nan():
    nan, inf = np.nan, np.inf
    w = np.array([[0.020, 0.010, 0.050, nan],     # rows: expiries in tau order; columns: four values of k
                  [0.015, 0.030, 0.020, 0.040],
                  [0.025, 0.012, 0.060, 0.030]])
    anchored = np.array([[True, True, False, True],
                         [True, False, True, True],
                         [True, True, True, True]])
    out = smile.calendar_variance(w, anchored)
    # k0: all quoted: the running maximum (0.020 holds through the 0.015 crossing).
    assert out[:, 0].tolist() == [0.020, 0.020, 0.025]
    # k1: the middle value is extrapolated (0.030): held between the quoted floors before and after
    # it, [0.010, max(0.010, 0.012)], so 0.012.
    assert out[:, 1].tolist() == [0.010, 0.012, 0.012]
    # k2: an extrapolated FRONT value (0.050) above the next quote (0.020): lowered to it.
    assert out[:, 2].tolist() == [0.020, 0.020, 0.060]
    # k3: a NaN front value is missing, not a floor: the row stays NaN and the rest are read as quoted.
    assert np.isnan(out[0, 3]) and out[1:, 3].tolist() == [0.040, 0.040]
    assert np.all(out[np.isfinite(out)] < inf)


@pytest.mark.parametrize("bad", [np.inf, -np.inf], ids=["plus-inf", "minus-inf"])
def test_an_infinite_w_is_missing_like_nan(bad):
    # Round 3 (code finding N-5; decision F7): +inf was clipped to the next floor or, past the last
    # anchor, spread to every later row; -inf was clamped up to the floor before it. Both are missing
    # values now: NaN where they are, and no effect on any other row.
    w = np.array([[0.020, 0.010], [0.015, 0.030], [0.025, 0.012]])
    anchored = np.array([[True, True], [False, False], [True, True]])
    plain = smile.calendar_variance(np.where([[False, False], [True, False], [False, False]], np.nan, w), anchored)
    out = smile.calendar_variance(np.where([[False, False], [True, False], [False, False]], bad, w), anchored)
    assert np.isnan(out[1, 0]) and np.array_equal(out, plain, equal_nan=True)
    tail = smile.calendar_variance(np.array([[0.02], [bad], [0.01]]), np.array([[True], [False], [False]]))
    assert np.isnan(tail[1, 0]) and tail[2, 0] == 0.02 and np.isfinite(tail[[0, 2], 0]).all()


def test_two_expiries_at_the_same_tau_are_refused():
    # Round 3 (N-5; F7): with two smiles at one tau the constraint raised whichever came second in the
    # list, so the surface depended on the list's order.
    k = np.array([-0.2, -0.1, 0.0, 0.1, 0.2])
    low, high = (30 / 365, k, np.full(5, 0.04**2 * 30)), (30 / 365, k, np.full(5, 0.30**2 * 30 / 365))
    with pytest.raises(ValueError, match="two usable expiries have the same tau"):
        smile.surface_iv(k, 45 / 365, [low, high])
    with pytest.raises(ValueError, match="two usable expiries have the same tau"):
        smile.surface_iv(k, 45 / 365, [(30 / 365 + 1e-13, k, low[2]), high])
    assert np.isfinite(smile.surface_iv(k, 45 / 365, [(30 / 365 + 1e-9, k, low[2]), high])[0]).all()


def test_a_nan_node_does_not_spread_past_the_next_expiry():
    # Round 2, code claim 3: one NaN node in the front smile made 5 cells NaN at every later tenor.
    # A NaN is a missing value: the cells it touches at its own expiry, and between it and the next
    # expiry, stay NaN (no number is invented for them); from the next expiry on, none does.
    expiries = wing_and_quote()
    k1, w1 = expiries[0][1], expiries[0][2].copy()
    w1[2] = np.nan
    broken = [(expiries[0][0], k1, w1), expiries[1]]
    grid = np.linspace(-0.3, 0.2, 51)
    own = np.isnan(smile.surface_iv(grid, 30 / 365, broken)[0])
    assert 0 < own.sum() < grid.size
    for days in (60, 120):
        assert np.array_equal(np.isnan(smile.surface_iv(grid, days / 365, broken)[0]), own), days
    for days in (300, 400, 900):
        assert np.isfinite(smile.surface_iv(grid, days / 365, broken)[0]).all(), days


def test_unsorted_expiries_give_the_sorted_answer():
    expiries = crossing_expiries() + [wing_and_quote()[1]]
    grid = np.linspace(-0.3, 0.2, 26)
    for days in (7, 30, 45, 60, 200, 300, 500):
        a = smile.surface_iv(grid, days / 365, expiries)
        b = smile.surface_iv(grid, days / 365, expiries[::-1])
        assert np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1])


def random_surface(rng):
    taus = np.sort(rng.choice(np.arange(2, 800), rng.integers(1, 7), replace=False)) / 365
    expiries = []
    for tau in taus:
        k = np.unique(np.sort(rng.uniform(-0.6, 0.4, rng.integers(5, 20))))
        sigma = np.maximum(rng.uniform(0.05, 0.9) + rng.uniform(-1.5, 0.5) * k + rng.uniform(-1, 8) * k**2
                           + rng.normal(0, 0.02, k.size), 0.01)
        if rng.random() < 0.3:
            sigma = sigma * (1 + 30 * k**4)                 # steep convex wings: w grows faster than k^2
        expiries.append((float(tau), k, sigma**2 * tau))
    return expiries


def test_the_adjusted_bit_is_set_exactly_where_the_constraint_moved_the_value():
    # On random surfaces, before, at, between and past the expiries: the bit is set exactly where w
    # differs, beyond 1e-12 of it, from steps 2-5 alone (calendar=False), up or down, and NEVER at a
    # quoted node by anything but a shorter expiry's quote (round 2: the bit past the back expiry was
    # tested only above a 1% move, mutant R20).
    rng = np.random.default_rng(11)
    grid_k = np.r_[np.linspace(-1.0, 0.8, 91), 0.0]
    small_moves = 0
    for _ in range(150):
        expiries = random_surface(rng)
        taus = np.array([e[0] for e in expiries])
        grid_tau = np.unique(np.r_[np.linspace(0.5 / 365, taus[-1] * 1.8 + 30 / 365, 60), taus, taus * (1 + 1e-9)])
        for tau in grid_tau:
            sigma, flags = smile.surface_iv(grid_k, tau, expiries)
            plain, plain_flags = smile.surface_iv(grid_k, tau, expiries, calendar=False)
            w, p = sigma**2 * tau, plain**2 * tau
            moved = np.abs(w - p) > 1e-9 * p
            has = (flags & smile.SURFACE_CALENDAR_ADJUSTED) != 0
            assert not (moved & ~has).any() and not (plain_flags & smile.SURFACE_CALENDAR_ADJUSTED).any()
            assert not (has & (np.abs(w - p) <= 1e-13 * p)).any()
            small_moves += int((has & (np.abs(w - p) < 1e-2 * p) & (taus[-1] < tau)).sum())
        # At each expiry's own nodes: the value is the running maximum of the QUOTED values there.
        for i, (tau, kn, wn) in enumerate(expiries):
            sigma, _ = smile.surface_iv(kn, tau, expiries)
            quoted = [smile.smile_variance(kn, e[1], e[2]) for e in expiries[: i + 1]]
            expected = np.max([np.where(beyond, -np.inf, v) for v, beyond in quoted], axis=0)
            assert sigma**2 * tau == pytest.approx(expected, rel=1e-12)
    assert small_moves > 0                    # the past-the-back moves below 1% were tested


def test_tau_at_or_below_zero_is_nan_not_an_exception():
    expiries = crossing_expiries()
    for tau in (0.0, -1 / 365):
        sigma, flags = smile.surface_iv(np.array([0.0, 0.1]), tau, expiries)
        assert np.all(np.isnan(sigma)) and np.all(flags == 0)


def test_the_flag_names_match_the_bits():
    bits = (smile.SURFACE_EXTRAP_STRIKE, smile.SURFACE_CROSS_EXPIRY, smile.SURFACE_EXTRAP_TENOR, smile.SURFACE_CALENDAR_ADJUSTED)
    assert bits == (1, 2, 4, 8) and len(smile.SURFACE_FLAG_NAMES) == 4
    assert smile.SMILE_FLAG_NAMES[3] == "SMILE_FORWARD_RAW" and smile.SMILE_FORWARD_RAW == 8
