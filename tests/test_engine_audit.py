"""The real cash test: tests/ledger_audit.py recomputes every amount of a ledger from the store and the ADRs.

The cash identity test (tests/test_engine_cash.py) proves only that cash moves through Run.flow. Here an auditor
that imports nothing from volbt recomputes every flow, fill price, share count, mark and NAV of a run (its
docstring lists them) and must find no problem: on the made-up fixture under six configurations (the default
suite), and on the recorded development run of the real store (real_data).
"""

from __future__ import annotations

import json
from datetime import date
from fractions import Fraction
from pathlib import Path

import pytest

import engine_helpers as eh
import engine_store as es
from ledger_audit import audit
from volbt import config
from volbt.data.store import Store

D = date


def script():
    """Opens and closes of both signs, an assignment, an expiry and a reduce-only close, on the fixture's dates."""
    symbol = es.symbol
    return eh.Scripted({
        D(2023, 1, 5): eh.open_straddle(D(2023, 2, 17), 400.0),
        D(2023, 2, 21): eh.open_legs([(symbol(D(2023, 3, 17), "P", 435.0), -1), (symbol(D(2023, 3, 17), "C", 365.0), 1)],
                                     packages=10),
        D(2023, 3, 20): eh.open_straddle(D(2023, 4, 21), 400.0),
        D(2023, 4, 10): eh.close_all("signal"),
        D(2023, 4, 12): eh.open_straddle(D(2023, 5, 19), 395.0, sign=1)}, label="audit")


@pytest.fixture(scope="module")
def open_store(tmp_path_factory):
    """Opens 1% below the closes, so a next_open hedge priced at the close is a problem the audit sees."""
    return es.built_store(tmp_path_factory.mktemp("audit_open_store"), open_factor=0.99)


SCENARIOS = {
    "next_close": {},
    "same_close": {"fill_timing": "same_close"},
    "unhedged": {"hedge_mode": "never", "fill_timing": "same_close"},
    "next_open": {"hedge_timing": "next_open"},
    "surface": {"execution_mode": "surface"},
    "band": {"hedge_mode": "band", "hedge_band_pct_nav": Fraction(1, 100)},
}


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_an_independent_audit_of_the_fixture_ledger_finds_no_problem(name, engine_store, open_store, tmp_path):
    store = open_store if name == "next_open" else engine_store
    result = eh.run(store, tmp_path, script(), **SCENARIOS[name])
    problems, info = audit(result.run_dir, store.root)
    assert problems == []
    # the audit had something to check: fills of both kinds of order, hedges, settlement events, many flows
    assert info["fills"] >= 8 and info["events"] >= 1 and info["flows"] > 100, info


@pytest.mark.real_data
def test_an_independent_audit_of_the_recorded_development_run_finds_no_problem():
    pointer = config.work_dir() / "runs" / "app_run.json"
    if not pointer.is_file():
        pytest.skip("no recorded development run: tools/run_backtest.py ... --for-app")
    run_dir = Path(json.loads(pointer.read_text(encoding="utf-8"))["run_dir"])
    problems, info = audit(run_dir, Store().root)
    assert problems == []
    assert info["sessions"] > 2000 and info["fills"] > 400, info
