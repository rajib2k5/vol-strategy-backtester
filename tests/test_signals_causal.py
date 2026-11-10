"""ADR-0001 test 6 for the signals (milestone 4, plan section 10, task 5): no signal value up to t0 moves when every
input after t0 changes.

Store A is tests/signal_store.py: made-up bars from 2017-01-03 with clustered vol, so HAR has its 504 training pairs
before the snapshots of 2023-01-03 to 2023-04-28. Store B, one per t0, is A with every value dated after t0 tripled
and permuted (bars, VIX, rates, dividends, quotes and volumes: test_engine_lookahead.perturbed_store), re-priced by
the M2 build. A strategy that never trades declares VrpSignal("har") and VrpSignal("naive"). The full run on A and
the full run on B must write the same `signals` rows for every session up to t0 (every column, model_fit_date
included) and hand the strategy the same values. The engine updates each signal through that session's view at step
9, so an engine that computed the signals from a view at sample_end fails this (the precompute mutant).

The four t0: 2023-02-28 (the eve of a refit), 2023-03-01 (a refit day), 2023-03-16 (the eve of an ex-date and a
monthly expiry) and 2023-04-03 (the -8% gap, also a refit day). Every window holds the missing snapshot of 2023-02-08
and the early-January sessions with no IV30. The plan's entry and stop days belong to part B: nothing trades yet.
"""

from __future__ import annotations

import math
from datetime import date

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import pytest

import engine_helpers as eh
import signal_store as ss
from test_engine_lookahead import perturbed_store
from volbt.engine.loop import EngineError
from volbt.signals.base import RV_MISSING
from volbt.signals.vrp import VrpSignal

D = date
T0S = (D(2023, 2, 28), D(2023, 3, 1), D(2023, 3, 16), D(2023, 4, 3))
FIELDS = ("iv30", "iv30_flags", "rv_forecast", "rv_model", "model_fit_date", "vrp_spread", "vix_bucket", "vol_regime",
          "n_window", "flags")


class Holder:
    """Never trades; declares two signals and records, as text, every value it is handed."""

    name = "SignalHolder"

    def __init__(self) -> None:
        self.signals = (VrpSignal("har"), VrpSignal("naive"))
        self.seen, self.values = {}, {}

    def params(self) -> dict:
        return {"signals": [s.name for s in self.signals]}

    def decide(self, view, book, ctx):
        # repr keeps every bit of a float and makes NaN equal to NaN.
        self.seen[ctx.session_date] = {name: repr(value) for name, value in ctx.signals.items()}
        self.values[ctx.session_date] = dict(ctx.signals)
        return []


def signals_table(result):
    return pq.read_table(result.run_dir / "signals" / "part-0.parquet")


def up_to(table, t0):
    return table.filter(pc.less_equal(table["session_date"], pa.scalar(t0, pa.date32())))


def after(table, t0):
    return table.filter(pc.greater(table["session_date"], pa.scalar(t0, pa.date32())))


@pytest.fixture(scope="module")
def store_a(tmp_path_factory):
    return ss.signal_store(tmp_path_factory.mktemp("signal_store_a"))


@pytest.fixture(scope="module")
def run_a(store_a, tmp_path_factory):
    holder = Holder()
    return eh.run(store_a, tmp_path_factory.mktemp("run_a"), holder), holder


@pytest.fixture(scope="module", params=T0S, ids=str)
def run_b(request, store_a, tmp_path_factory):
    t0 = request.param
    store_b = perturbed_store(store_a, tmp_path_factory.mktemp(f"signal_store_b_{t0}"), t0)
    holder = Holder()
    return t0, eh.run(store_b, tmp_path_factory.mktemp(f"run_b_{t0}"), holder), holder


def test_the_fixture_gives_har_a_fit_every_month_and_the_nan_cases(run_a):
    """The premise: HAR exists from the first snapshot, refits on each month's first session, and the window holds
    sessions with no IV30 (early January, the missing snapshot) and a VIX shock."""
    rows = signals_table(run_a[0]).to_pandas()
    har = rows[rows["signal_name"] == "vrp_har"].set_index("session_date")
    assert len(har) == len(rows) / 2 == len(eh.table(run_a[0], "daily_pnl"))
    assert set(har["model_fit_date"]) == {D(2023, 1, 3), D(2023, 2, 1), D(2023, 3, 1), D(2023, 4, 3)}
    assert not (har["flags"] & RV_MISSING).any() and har["rv_forecast"].notna().all()
    assert har.loc[D(2023, 2, 8), "iv30"] != har.loc[D(2023, 2, 8), "iv30"]            # NaN, written as null
    assert har.loc[D(2023, 1, 3):D(2023, 1, 13), "iv30"].isna().all() and har["iv30"].notna().sum() > 60
    assert {"shock", "post_shock", "calm"} <= set(har["vol_regime"])
    naive = rows[rows["signal_name"] == "vrp_naive"]
    assert naive["model_fit_date"].isna().all() and (naive["rv_forecast"] != har["rv_forecast"].to_numpy()).any()


def test_the_strategy_is_handed_exactly_the_rows_the_table_holds(run_a):
    result, holder = run_a
    rows = signals_table(result).to_pylist()
    assert len(rows) == 2 * len(holder.values)
    for row in rows:
        value = holder.values[row["session_date"]][row["signal_name"]]
        assert value.value == row["log_var_ratio"] or (math.isnan(value.value) and row["log_var_ratio"] is None)
        for name in FIELDS:
            mine = getattr(value, name)
            assert mine == row[name] or (isinstance(mine, float) and math.isnan(mine) and row[name] is None), name


def test_no_signal_value_up_to_t0_moves_when_every_input_after_t0_changes(run_a, run_b):
    t0, result_b, holder_b = run_b
    result_a, holder_a = run_a
    table_a, table_b = signals_table(result_a), signals_table(result_b)
    assert up_to(table_a, t0).num_rows >= 2 * 38
    assert up_to(table_a, t0).equals(up_to(table_b, t0))
    assert {d: v for d, v in holder_a.seen.items() if d <= t0} == {d: v for d, v in holder_b.seen.items() if d <= t0}
    # The premise: the changed future does reach the signals after t0.
    assert not after(table_a, t0).equals(after(table_b, t0))


# --- a signal's state does not survive a run (fix pass, review finding N3) -----------------------------------------

@pytest.fixture(scope="module")
def store_b_0316(store_a, tmp_path_factory):
    return perturbed_store(store_a, tmp_path_factory.mktemp("signal_store_b_reset"), D(2023, 3, 16))


def test_a_strategy_object_run_again_on_another_store_gives_a_fresh_objects_signals(store_a, store_b_0316,
                                                                                     tmp_path_factory):
    """The holder runs on store B (every input after 03-16 changed), then the SAME holder runs on store A from
    2023-04-05, inside the month whose fit (04-03) the B run left behind. Its signals equal a fresh holder's on A from
    04-05: the engine reset the signals. Without the reset the April HAR fit of store B would be reused."""
    reused = Holder()
    on_b = eh.run(store_b_0316, tmp_path_factory.mktemp("reset_b"), reused)
    again = eh.run(store_a, tmp_path_factory.mktemp("reset_a_again"), reused, sample_start=D(2023, 4, 5))
    fresh = eh.run(store_a, tmp_path_factory.mktemp("reset_a_fresh"), Holder(), sample_start=D(2023, 4, 5))
    assert signals_table(again).equals(signals_table(fresh))
    assert signals_table(fresh).num_rows >= 2 * 15
    # The premise: store B's April fit is not store A's, so a carried-over fit would show.
    april = pc.greater_equal(signals_table(on_b)["session_date"], pa.scalar(D(2023, 4, 5), pa.date32()))
    b_april = signals_table(on_b).filter(april)
    assert not b_april.column("rv_forecast").equals(signals_table(fresh).column("rv_forecast"))
    assert set(b_april.column("model_fit_date").to_pylist()) - {None} == {D(2023, 4, 3)}


def test_a_signal_without_reset_is_refused(store_a, tmp_path):
    class NoReset:
        name = "no_reset"

        def params(self):
            return {}

        def update(self, view, n_window):
            raise AssertionError("never reached")

    holder = Holder()
    holder.signals = (NoReset(),)
    with pytest.raises(EngineError, match="reset"):
        eh.run(store_a, tmp_path / "run", holder, sample_end=D(2023, 1, 10))
