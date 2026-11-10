"""Tests written after the milestone-3 adversarial review: each one fails on a mutant or a bug the review found.

    the rate dated strictly before t (a `<=` mutant survived the suite)
    NAV_liq of a model-marked lot at its mark -/+ h_model (valuing it at the mid survived)
    the put rule's $0.005 tolerance (tol = 0 survived: the real 2019-08-07 assignment had a margin of 0.000126)
    the stale forward's parity-minus-carry basis, decision D10 (removing it survived)
    h_model's +-0.05 band and its nearest-expiry fallback (widening the band and deleting the fallback survived)
    same_close: NAV after pass 9b (the closed lots' step-5 marks stayed in NAV: nav_mid off by -8,740.00)
    a run stopped early takes its own run id (it took the full run's id and replaced its folder)
    an expiry after the calendar's last session is not an unmapped non-session (holdout runs would stop)
    the run id names the code (a "-dirty" commit names no code)
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import numpy as np
import pytest

import engine_helpers as eh
import engine_store as es
from volbt.data.store import session_calendar, view
from volbt.engine import early, fills, report, settlement
from volbt.engine.book import Lot
from volbt.engine.run_config import make_run_id
from volbt.engine.surface import FORWARD_CARRY, DaySurface
from volbt.pricing.forward import carry_forward
from volbt.strategies.reference import RollingShortStraddle

D = date


@pytest.fixture(scope="module")
def reference_run(engine_store, tmp_path_factory):
    return eh.run(engine_store, tmp_path_factory.mktemp("review_ref"), RollingShortStraddle())


def test_every_session_s_rate_is_the_dgs3mo_dated_strictly_before_it(reference_run):
    daily = eh.table(reference_run, "daily_pnl")
    expected = [es.rate_before(d) for d in daily["session_date"]]
    # The fixture's DGS3MO changes every day, so the rate dated ON the session differs from every one of these.
    same_day = [es.r_cc(es.rate_pct()[d]) for d in daily["session_date"]]
    assert daily["rate"].tolist() == expected
    assert all(a != b for a, b in zip(expected, same_day))


def test_nav_liq_of_a_model_marked_lot_is_its_mark_plus_h_model_for_a_short(tmp_path):
    held = es.symbol(D(2023, 3, 17), "C", 400.0)
    store = es.built_store(tmp_path / "store", edits={(D(2023, 2, 15), held): {"bid": 9.00, "ask": 8.50}})
    strategy = eh.Scripted({D(2023, 2, 10): eh.open_legs([(held, -1)], 1)})
    marks = eh.table(eh.run(store, tmp_path / "runs", strategy, sample_end=D(2023, 2, 17)), "position_marks")
    row = marks[(marks["session_date"] == D(2023, 2, 15)) & marks["in_nav"]].iloc[0]
    assert row["mark_source"] == "SURFACE_MODEL" and row["h_model"] > 0
    assert row["value_liq_usd"] == pytest.approx(-100 * (row["mark_price"] + row["h_model"]), abs=1e-9)
    assert row["value_liq_usd"] < row["value_mid_usd"]


def put_lot(strike: float, expiry: date) -> Lot:
    return Lot(1, 1, es.symbol(expiry, "P", strike), expiry, strike, "P", -1, D(2023, 1, 3), expiry)


def test_a_put_within_the_half_cent_tolerance_is_assigned_and_the_tolerance_decides_it():
    t = D(2023, 3, 1)
    lot = put_lot(450.0, D(2023, 3, 31))                       # 30 days, K 450, r 5%, sigma 0.20, no dividend
    cfg = eh.config()
    decision = early.decide_lot(lot, t, D(2023, 3, 2), 409.7, 0.05, 0.20, ([], []), es.sessions(), cfg)
    assert decision["method"] == "crr" and 0 < decision["threshold"] <= 0.005 and decision["exercise"] is True
    strict = early.decide_lot(lot, t, D(2023, 3, 2), 409.7, 0.05, 0.20, ([], []), es.sessions(),
                              replace(cfg, exercise_tol=0.0))
    assert strict["exercise"] is False


def test_the_stale_forward_keeps_the_previous_session_s_parity_minus_carry_basis(engine_store):
    before, missing = D(2023, 2, 7), es.MISSING_SNAPSHOT
    calendar = session_calendar(engine_store)

    def inputs(day):
        v = view(day, "validation", engine_store)
        rates = v.rates()
        rate = float(rates.loc[rates["date"] < np.datetime64(day), "r_cc"].iloc[-1])
        paid = v.dividends()
        return v, float(v.spy_bars()["close"].iloc[-1]), rate, ([d.date() for d in paid["ex_date"]],
                                                                 [float(a) for a in paid["amount"]])

    v0, s0, r0, paid0 = inputs(before)
    surface = DaySurface.from_view(v0, before, "optionsdx", s0, r0, paid0, calendar)
    _, s1, r1, paid1 = inputs(missing)
    stale = surface.stale_copy(missing, s1, r1, paid1)
    expiry = D(2023, 3, 17)
    forward, flags = stale.forward(expiry)
    times, amounts = stale.schedule(expiry)
    carry_today = carry_forward(s1, r1, (expiry - missing).days / 365, times, amounts)
    parity, carry_then = surface.forwards[expiry]
    assert flags == FORWARD_CARRY and parity != carry_then
    assert forward - carry_today == pytest.approx(parity - carry_then, abs=1e-9)


def quotes(**by_expiry):
    return {expiry: (np.asarray(k, float), np.asarray(h, float)) for expiry, (k, h) in by_expiry.items()}


def test_h_model_is_the_median_inside_the_band_of_the_own_expiry():
    a = D(2023, 3, 17)
    day = {a: (np.array([-0.10, -0.04, 0.0, 0.03, 0.06]), np.array([0.50, 0.02, 0.04, 0.06, 0.90]))}
    assert fills.h_model(day, a, 0.0, 0.05) == (0.04, False)          # the 0.50 and 0.90 lie outside +-0.05


def test_h_model_falls_back_to_the_nearest_listed_expiry_and_says_so():
    own, near, far = D(2023, 3, 17), D(2023, 3, 24), D(2023, 4, 21)
    day = {own: (np.array([0.20]), np.array([0.70])), near: (np.array([0.01]), np.array([0.03])),
           far: (np.array([0.0]), np.array([0.05]))}
    assert fills.h_model(day, own, 0.0, 0.05) == (0.03, True)
    assert fills.h_model({}, own, 0.0, 0.05) == (None, False)


def test_same_close_nav_counts_only_the_lots_open_at_the_close(engine_store, tmp_path):
    result = eh.run(engine_store, tmp_path, RollingShortStraddle(), fill_timing="same_close")
    daily, marks, lots = (eh.table(result, n) for n in ("daily_pnl", "position_marks", "lots"))
    closes = eh.table(result, "orders").query("intent == 'close' and status == 'filled'")
    assert len(closes) and (closes["resolved_date"] == closes["created_date"]).all()
    span = lots.set_index("lot_id")
    for _, day in daily.iterrows():
        rows = marks[(marks["session_date"] == day.session_date) & marks["in_nav"]]
        open_now = [lot for lot, row in span.iterrows() if row.opened_date <= day.session_date
                    and (row.closed_date is None or row.closed_date > day.session_date)]
        assert sorted(rows["lot_id"]) == sorted(open_now), day.session_date
        assert day.nav_mid == pytest.approx(day.cash_cents / 100 + day.shares * day.spot + rows["value_mid_usd"].sum(),
                                            abs=1e-6)


def test_a_run_stopped_early_has_its_own_id_and_says_where_it_stopped(engine_store, tmp_path):
    full = eh.run(engine_store, tmp_path, RollingShortStraddle())
    stopped = eh.run(engine_store, tmp_path, RollingShortStraddle(), stop_after=D(2023, 2, 15))
    assert stopped.run_id != full.run_id and full.run_dir.is_dir() and stopped.run_dir.is_dir()
    assert eh.table(stopped, "runs")["sample_end"].tolist() == [D(2023, 2, 15)]
    assert eh.table(full, "runs")["sample_end"].tolist() == [es.LAST_SNAPSHOT]
    assert report.blotter_body(stopped.run_dir)["run"]["sample_end"] == "2023-02-15"


def test_an_expiry_after_the_calendar_settles_on_its_own_date():
    sessions = {D(2026, 10, 27), D(2026, 10, 28)}
    assert settlement.settle_date(D(2026, 11, 20), sessions) == D(2026, 11, 20)
    with pytest.raises(settlement.UnmappedExpiry):
        settlement.settle_date(D(2026, 10, 25), sessions)        # a Sunday inside the calendar


def test_the_run_id_names_the_code(reference_run):
    run = eh.table(reference_run, "runs").iloc[0]
    assert len(run["code_fingerprint"]) == 64
    args = (run["config_hash"], run["data_fingerprint"], run["source_commit"])
    assert reference_run.run_id == make_run_id(*args, run["code_fingerprint"]) != make_run_id(*args, "0" * 64)


def test_a_surface_fill_carries_the_surface_flags_and_says_when_h_model_came_from_another_expiry(tmp_path):
    # ADR-0002 §7. On 2023-02-15 every quote of the 2023-03-17 expiry is crossed: that expiry has no valid quote, so
    # its smile has no node (the surface reads it across expiries, SURFACE_CROSS_EXPIRY) and h_model comes from the
    # nearest other expiry. The held call's buy-to-close is then a surface fill that must say both.
    expiry, day = D(2023, 3, 17), D(2023, 2, 15)
    edits = {(day, es.symbol(expiry, right, k)): {"bid": 9.00, "ask": 8.50} for right in "CP" for k in es.STRIKES}
    store = es.built_store(tmp_path / "store", edits=edits)
    held = es.symbol(expiry, "C", 400.0)
    strategy = eh.Scripted({D(2023, 2, 10): eh.open_legs([(held, -1)], 1), D(2023, 2, 14): eh.close_all("signal")})
    filled = eh.table(eh.run(store, tmp_path / "runs", strategy, sample_end=D(2023, 2, 17)), "fills")
    close = filled[filled["fill_date"] == day].iloc[0]
    assert close["fill_source"] == "surface" and close["qty"] == 1
    assert close["fill_flags"] & fills.H_MODEL_OTHER_EXPIRY and close["fill_flags"] & 2      # 2 = SURFACE_CROSS_EXPIRY
    assert (filled.loc[filled["fill_source"] == "quote", "fill_flags"] == 0).all()
