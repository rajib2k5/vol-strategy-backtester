"""The engine on the real store (marked real_data): the 60-second budget, determinism and health checks.

Decision D19: runs after 2019 report HEALTH metrics only. Nothing here prints or asserts a P&L, a NAV level or
a return of the 2010-2023 or the DoltHub run; the assertions are about mechanics (cash reconciles, one mark per
lot, the hedge's residual, fill prices against quotes, the cap's information date, the mark sources).

ADR-0001's revisit trigger: "a 14-year, single-strategy run takes longer than 60 s". The budget run is the
reference strategy on OptionsDX 2010-01-04 to 2023-12-29, timed inside run_backtest (store checks and
fingerprints included), run twice; the two ledgers must be byte-identical.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import pytest

from volbt import build, config
from volbt.data.store import Store
from volbt.engine import report
from volbt.engine.loop import run_backtest
from volbt.engine.run_config import RunConfig
from volbt.strategies.reference import RollingShortStraddle

pytestmark = pytest.mark.real_data

BUDGET_SECONDS = 60.0
REPO = Path(__file__).resolve().parent.parent
COMMIT = "0" * 40


def table(run_dir, name):
    return pq.read_table(Path(run_dir) / name / "part-0.parquet").to_pandas()


@pytest.fixture(scope="module")
def store():
    store = Store()
    if not store.has("smile_fits"):
        pytest.skip("no built store: run tools/build_data.py and tools/build_pricing.py")
    return store


@pytest.fixture(scope="module")
def budget_runs(store, tmp_path_factory):
    cfg = RunConfig(sample_start=date(2010, 1, 4), sample_end=date(2023, 12, 29), split="validation")
    return [run_backtest(cfg, RollingShortStraddle(), store=store, runs_root=tmp_path_factory.mktemp(f"budget{i}"),
                         source_commit=COMMIT, store_check=build.require_current) for i in range(2)]


@pytest.fixture(scope="module")
def dolthub_run(store, tmp_path_factory):
    cfg = RunConfig(sample_start=date(2020, 1, 2), sample_end=date(2023, 12, 29), split="validation",
                    data_source="dolthub", execution_mode="surface")
    return run_backtest(cfg, RollingShortStraddle(), store=store, runs_root=tmp_path_factory.mktemp("dolthub"),
                        source_commit=COMMIT, store_check=build.require_current)


def test_the_14_year_run_fits_the_60_second_budget_twice_with_equal_hashes(budget_runs):
    first, second = budget_runs
    for run in budget_runs:
        assert run.status == "ok" and run.sessions == 3522 and run.last_session == date(2023, 12, 29)
        assert run.timings["total_s"] < BUDGET_SECONDS, run.timings
    assert first.files == second.files and first.digest == second.digest and first.run_id == second.run_id
    print("budget timings:", [run.timings for run in budget_runs])


def health(run_dir, mode: str) -> dict:
    """The mechanical checks of one run; returns the counts it measured (no P&L)."""
    daily, flows = table(run_dir, "daily_pnl"), table(run_dir, "cash_flows")
    # Cash reconciles exactly on every session: initial + the cumulative flows up to that session's close.
    by_day = flows.groupby("session_date")["amount_cents"].sum().reindex(daily["session_date"], fill_value=0)
    assert (daily["cash_cents"].to_numpy() == 100_000_000 + by_day.cumsum().to_numpy()).all()
    # One mark per open lot per session, and only for lots open that day.
    marks, lots = table(run_dir, "position_marks"), table(run_dir, "lots")
    in_nav = marks[marks["in_nav"]]
    assert not in_nav.duplicated(["session_date", "lot_id"]).any()
    assert (daily.set_index("session_date")["n_open_lots"]
            == in_nav.groupby("session_date").size().reindex(daily["session_date"], fill_value=0)).all()
    opened = lots.set_index("lot_id")["opened_date"]
    assert (in_nav["session_date"].to_numpy() >= opened.loc[in_nav["lot_id"]].to_numpy()).all()
    # The hedge leaves at most half a share of delta (whole shares, half away from zero).
    hedges = table(run_dir, "hedges")
    assert hedges["delta_after_shares"].abs().max() <= 0.5
    fills = table(run_dir, "fills")
    options = fills[fills["instrument"] == "option"]
    # The cap's information date is before the fill date (next_close).
    assert (options["cap_volume_date"] < options["fill_date"]).all()
    quoted = options[options["fill_source"] == "quote"]
    if mode == "quote":
        # k = 1: a buy at the ask, a sell at the bid (a zero-bid buy at the ask too).
        assert (np.where(quoted["qty"] > 0, quoted["price"] == quoted["ask"], quoted["price"] == quoted["bid"])).all()
    else:
        assert quoted.empty and set(marks["mark_source"]) <= {"SURFACE_MODEL", "STALE_SURFACE", "INTRINSIC"}
    shares = marks[marks["in_nav"]]["mark_source"].value_counts(normalize=True).round(4).to_dict()
    return {"sessions": len(daily), "degraded": int((daily["mark_quality"] == "DEGRADED").sum()),
            "mark_source_share": shares, "option_fills": len(options), "surface_fills": int((options["fill_source"] == "surface").sum()),
            "early_events": int(table(run_dir, "expiry_events")["event_type"].str.startswith("early").sum())}


def test_the_budget_run_is_healthy(budget_runs):
    measured = health(budget_runs[0].run_dir, "quote")
    assert measured["mark_source_share"]["QUOTE_MID"] > 0.9
    print("optionsdx 2010-2023 health:", json.dumps(measured, sort_keys=True))


def test_the_dolthub_surface_run_is_healthy(dolthub_run):
    measured = health(dolthub_run.run_dir, "surface")
    assert dolthub_run.status == "ok" and measured["surface_fills"] == measured["option_fills"]
    print("dolthub 2020-2023 surface health:", json.dumps(measured, sort_keys=True))


def test_the_committed_engine_datasets_are_the_recorded_development_run():
    """blotter.json and positions_timeline.json equal a fresh read of the run tools/run_backtest.py --for-app
    recorded (the ledger is git-ignored, so this runs where that run exists)."""
    pointer = config.work_dir() / "runs" / "app_run.json"
    if not pointer.is_file():
        pytest.skip("no recorded development run: tools/run_backtest.py ... --for-app")
    run_dir = Path(json.loads(pointer.read_text(encoding="utf-8"))["run_dir"])
    envelope = ("schema_version", "generated_at", "source_commit")
    for name, body in (("blotter.json", report.blotter_body(run_dir)),
                       ("positions_timeline.json", report.positions_timeline_body(run_dir))):
        committed = json.loads((REPO / "app" / "public" / "data" / name).read_text(encoding="utf-8"))
        assert {k: v for k, v in committed.items() if k not in envelope} == json.loads(json.dumps(body)), name
        assert body["run"]["split"] == "development" and body["run"]["sample_end"] <= "2019-12-31"
        assert (REPO / "app" / "public" / "data" / name).stat().st_size < 10 * 1024 * 1024
