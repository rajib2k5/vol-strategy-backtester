"""IV30, the VIX regimes and the VRP signal (milestone 4, plan sections 4 and 10, task 4; EGV E6 of section 7).

On tests/engine_store.py's made-up store, on hand-built views (a small class with the view's methods and literal
frames), and one real-data check against M2's exported frames dated before 2020.
"""

from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import engine_store as es
from volbt.data.store import Store, YearCache, view
from volbt.engine.surface import DaySurface
from volbt.pricing import smile
from volbt.signals import regime
from volbt.signals.base import IV30_MISSING, RV_MISSING, WINDOW_EMPTY
from volbt.signals.iv30 import iv30
from volbt.signals.vrp import VrpSignal

REPO = Path(__file__).resolve().parents[1]


# --- iv30.py -------------------------------------------------------------------------------------------------------

def test_iv30_is_the_engine_surface_s_30_day_atm_read_and_nan_where_the_read_extrapolates_in_tenor(engine_store):
    """E6: on every session of the snapshot window, iv30 equals DaySurface.atm_iv_30d() bit for bit, except where
    30 days lies before the front expiry (SURFACE_EXTRAP_TENOR: early January, the front monthly 45 days out),
    where it is NaN; and NaN with no flags on the session with no snapshot."""
    cache = YearCache(engine_store, "optionsdx")
    seen = {"equal": 0, "tenor": 0, "missing": 0}
    for day in es.sessions():
        if not es.FIRST_SNAPSHOT <= day <= es.LAST_SNAPSHOT:
            continue
        v = view(day, "validation", engine_store, cache)
        sigma, flags = iv30(v, day)
        surface = DaySurface.from_view(v, day, "optionsdx", 400.0, 0.05, ((), ()), [])
        if surface is None:
            assert day == es.MISSING_SNAPSHOT and math.isnan(sigma) and flags == 0
            seen["missing"] += 1
        elif flags & smile.SURFACE_EXTRAP_TENOR:
            assert math.isnan(sigma) and math.isfinite(surface.atm_iv_30d())
            seen["tenor"] += 1
        else:
            assert sigma == surface.atm_iv_30d()
            seen["equal"] += 1
    assert seen["missing"] == 1 and seen["tenor"] >= 5 and seen["equal"] >= 60
    assert math.isnan(iv30(view(date(2023, 1, 3), "validation", engine_store, cache), date(2023, 1, 3))[0])


@pytest.mark.real_data
def test_iv30_equals_m2_s_exported_atm_iv_30d_on_the_frames_before_2020():
    """E6 on the real store: surface_frames.json's atm_iv_30d (6 decimals) for its frames dated before 2020."""
    from volbt import config

    frames = [f for f in json.loads((REPO / "app/public/data/surface_frames.json").read_text())["frames"]
              if f["date"] <= "2019-12-31"]
    assert len(frames) == 2
    store = Store(config.store_dir())
    if not store.has("smile_fits"):
        pytest.skip("no built store: run tools/build_data.py and tools/build_pricing.py")
    for frame in frames:
        day = date.fromisoformat(frame["date"])
        sigma, _ = iv30(view(day, "development", store), day)
        assert abs(sigma - frame["atm_iv_30d"]) <= 5e-7, (day, sigma, frame["atm_iv_30d"])


# --- regime.py (ADR-0010 test 3) -----------------------------------------------------------------------------------

def test_vix_buckets_at_their_boundaries():
    assert regime.vix_bucket(19.99) == "15-20" and regime.vix_bucket(20.00) == "20-30"
    assert [regime.vix_bucket(x) for x in (14.99, 15.0, 29.99, 30.0)] == ["<15", "15-20", "20-30", ">=30"]


def test_a_shock_is_a_rise_of_25_percent_or_5_points():
    assert regime.shock_days([17.0, 37.0]).tolist() == [False, True]         # made up, near 2018-02-05: +118%
    assert regime.shock_days([30.0, 33.0]).tolist() == [False, False]         # +10% and +3 points
    assert regime.shock_days([20.0, 25.0, 10.0, 12.4, 24.0, 29.0]).tolist() == \
        [False, True, False, False, True, True]                              # +25%; -60%; +24%; +140%; +5 points


def test_the_21_sessions_after_a_shock_are_post_shock():
    closes = [20.0, 20.0, 30.0] + [30.0] * 22
    labels = regime.regime_labels(closes)
    assert labels[:3] == [None, "calm", "shock"]
    assert labels[3:24] == ["post_shock"] * 21 and labels[24] == "calm"


def test_a_strategy_sees_the_labels_of_the_previous_vix_session():
    days = [date(2023, 3, 1) + timedelta(days=i) for i in range(30)]
    closes = [19.0] * 5 + [26.0] + [26.0] * 24          # the shock on the sixth day (+36.8%)
    frame = pd.DataFrame({"date": pd.to_datetime(days), "close": closes})
    assert regime.lagged_regime(frame, days[0]) == (None, None)
    assert regime.lagged_regime(frame, days[1]) == ("15-20", None)
    assert regime.lagged_regime(frame, days[5]) == ("15-20", "calm")       # the shock day itself: not yet
    assert regime.lagged_regime(frame, days[6]) == ("20-30", "shock")
    assert regime.lagged_regime(frame, days[27]) == ("20-30", "post_shock")
    assert regime.lagged_regime(frame, days[28]) == ("20-30", "calm")
    # A session with no VIX row of its own still reads the last row before it.
    assert regime.lagged_regime(frame.drop(index=6), days[6]) == ("20-30", "shock")


# --- vrp.py --------------------------------------------------------------------------------------------------------

class HandView:
    """The view methods VrpSignal reads, from literal frames."""

    def __init__(self, as_of, closes, smiles, vix_closes=(20.0, 20.0)):
        self.as_of = as_of
        days = [as_of - timedelta(days=len(closes) - 1 - i) for i in range(len(closes))]
        self.bars = pd.DataFrame({"date": pd.to_datetime(days), "close": closes})
        self.smile_frame = smiles
        self.vix_frame = pd.DataFrame({"date": pd.to_datetime([as_of - timedelta(days=len(vix_closes) - i)
                                                               for i in range(len(vix_closes))]),
                                       "close": list(vix_closes)})

    def spy_bars(self):
        return self.bars

    def dividends(self):
        return pd.DataFrame({"ex_date": pd.to_datetime([]), "amount": []})

    def smiles(self, day, source="optionsdx"):
        return self.smile_frame

    def vix(self):
        return self.vix_frame


def flat_smiles(sigma=0.2, taus=(20 / 365, 40 / 365)) -> pd.DataFrame:
    """Two expiries with a flat smile at `sigma`: total variance sigma^2 tau at five nodes."""
    k = np.linspace(-0.2, 0.2, 5)
    return pd.DataFrame({"tau_years": list(taus), "k_nodes": [k, k], "total_var_nodes": [np.full(5, sigma ** 2 * t)
                                                                                         for t in taus],
                         "n_points": [5, 5]})


def alternating_closes(n=23, step=0.01):
    """n closes whose returns alternate +step, -step: every r^2 is step^2."""
    return [100.0 * math.exp(step * (i % 2)) for i in range(n)]


def test_the_signal_is_the_log_ratio_of_implied_to_forecast_variance_over_the_window():
    """By hand: r^2 = 1e-4 on 22 returns, so the naive y^ = 1e-4; n = 21 sessions gives RV^ = sqrt(21e-4 365/30)
    = 0.159844; IV30 = 0.2 on a flat smile; s = ln(0.04 / 0.02555) = 0.448242."""
    out = VrpSignal("naive").update(HandView(date(2017, 6, 30), alternating_closes(), flat_smiles()), 21)
    assert out.rv_model == "naive" and out.model_fit_date is None and out.n_window == 21 and out.flags == 0
    assert out.rv_forecast == pytest.approx(math.sqrt(21e-4 * 365 / 30), rel=1e-9)
    assert out.iv30 == pytest.approx(0.2, rel=1e-12)
    assert out.value == pytest.approx(math.log(0.04 / (21e-4 * 365 / 30)), rel=1e-9)
    assert out.value == pytest.approx(0.448242, abs=5e-7)
    assert out.vrp_spread == pytest.approx(0.2 - 0.159844, abs=5e-7)
    assert (out.vix_bucket, out.vol_regime) == ("20-30", "calm")
    # The window counts: 17 sessions instead of 21 moves s by ln(21/17).
    assert VrpSignal("naive").update(HandView(date(2017, 6, 30), alternating_closes(), flat_smiles()), 17).value \
        == pytest.approx(out.value + math.log(21 / 17), rel=1e-9)


def test_with_no_smile_or_too_few_returns_the_signal_is_nan_and_flagged():
    no_smile = flat_smiles().iloc[0:0]
    out = VrpSignal("naive").update(HandView(date(2017, 6, 30), alternating_closes(), no_smile), 21)
    assert math.isnan(out.value) and math.isnan(out.iv30) and out.flags == IV30_MISSING
    assert out.iv30_flags == 0          # C25: no usable smile is not SURFACE_EXTRAP_TENOR; the VRP flag says why
    assert out.rv_forecast == pytest.approx(math.sqrt(21e-4 * 365 / 30), rel=1e-9)
    short = VrpSignal("naive").update(HandView(date(2017, 6, 30), alternating_closes(22), flat_smiles()), 21)
    assert math.isnan(short.value) and math.isnan(short.rv_forecast) and short.flags == RV_MISSING
    har = VrpSignal("har").update(HandView(date(2017, 6, 30), alternating_closes(), flat_smiles()), 21)
    assert har.rv_model == "har" and har.model_fit_date is None and har.flags == RV_MISSING and math.isnan(har.value)


def test_an_empty_window_is_flagged():
    """N5: n_window = 0 leaves RV^ and s undefined; the NaN carries WINDOW_EMPTY, not flags 0."""
    out = VrpSignal("naive").update(HandView(date(2017, 6, 30), alternating_closes(), flat_smiles()), 0)
    assert math.isnan(out.value) and math.isnan(out.rv_forecast) and out.flags == WINDOW_EMPTY
    assert out.iv30 == pytest.approx(0.2, rel=1e-12) and out.n_window == 0


def test_an_unknown_rv_model_is_refused_and_the_name_says_the_model():
    with pytest.raises(ValueError, match="rv_model"):
        VrpSignal("garch")
    assert VrpSignal("har").name == "vrp_har" and VrpSignal("naive", name="s").name == "s"
    assert VrpSignal("har").params() == {"rv_model": "har", "source": "optionsdx", "horizon": 21,
                                         "min_pairs": 504, "window_days": 30}
