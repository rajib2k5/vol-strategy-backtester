"""Milestone 4, part B (plan section 5, task 9): the development grid, m4_grid(rv_model).

36 configurations per rv_model, 10 per short-vol structure and 6 for the long straddle; 36 distinct config_hashes and
36 distinct trial_hashes for each of "har" and "naive" (72 in all: the RV model is in the strategy's params); every
configuration computes its position P&L (volbt.engine.positions.computed), fixed at FixedPackages(10), exit_dte 14,
k = 1, next_close fills and the hard cap. Hashes only: nothing runs.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from fractions import Fraction

import pytest

from volbt.engine import positions
from volbt.engine.run_config import RunConfig, config_hash, trial_hash
from volbt.strategies.grid import TRIAL_GROUP, m4_grid

DEV = dict(sample_start=date(2010, 1, 4), sample_end=date(2019, 12, 31), split="development")


def configs(rv_model):
    return [(entry, RunConfig(**DEV, **entry.engine)) for entry in m4_grid(rv_model)]


@pytest.mark.parametrize("rv_model", ["har", "naive"])
def test_36_configurations_36_config_hashes_and_36_trial_hashes(rv_model):
    rows = configs(rv_model)
    assert len(rows) == 36
    assert len({config_hash(cfg, entry.strategy) for entry, cfg in rows}) == 36
    assert len({trial_hash(cfg, entry.strategy) for entry, cfg in rows}) == 36
    assert len({entry.label for entry, _ in rows}) == 36
    assert Counter(entry.strategy.structure for entry, _ in rows) == {
        "short_straddle": 10, "short_strangle": 10, "straddle_calendar": 10, "long_straddle": 6}
    assert {entry.strategy.signal.rv_model for entry, _ in rows} == {rv_model}


def test_the_two_rv_models_are_72_distinct_trials():
    hashes = {config_hash(cfg, entry.strategy) for rv in ("har", "naive") for entry, cfg in configs(rv)}
    assert len(hashes) == 72


def test_every_configuration_computes_its_pnl_and_holds_the_fixed_choices():
    for entry, cfg in configs("har"):
        assert positions.computed(cfg), entry.label
        assert (cfg.trial_group, cfg.run_purpose, cfg.k, cfg.fill_timing, cfg.cap_mode, cfg.data_source,
                cfg.execution_mode) == (TRIAL_GROUP, "trial", Fraction(1), "next_close", "hard_only", "optionsdx",
                                        "quote")
        params = entry.strategy.params()
        assert params["exits"]["exit_dte"] == 14 and params["sizer"] == {"name": "FixedPackages", "n": 10}
        assert params["max_open"] == 2
        assert params.get("entry_dte", params.get("front_dte")) == ([22, 35] if params["structure"] ==
                                                                      "straddle_calendar" else [50, 60])
    stops = [entry for entry, _ in configs("har") if entry.strategy.exits.stop is not None]
    assert len(stops) == 3 * 5 + 3 and all(e.strategy.exits.params()["stop"] == 1.0 and
                                            e.strategy.exits.params()["target"] == 0.5 for e in stops)


def test_the_signal_levels_and_gates_are_the_plans():
    seen = Counter()
    for entry, _ in configs("har"):
        strategy = entry.strategy
        gate, theta = strategy.entry.gate, strategy.entry.theta
        if strategy.side == "short":
            assert strategy.exits.signal_above is None
            if strategy.exits.signal_below is not None:
                assert gate == "above" and strategy.exits.signal_below == pytest.approx(theta - 0.4)
        else:
            assert strategy.exits.signal_below is None and gate in ("always", "below")
            assert theta in (None, 0.0) and strategy.exits.signal_above in (None, 0.4)
        seen[(strategy.side, gate, theta)] += 1
    assert seen == {("short", "always", None): 6, ("short", "above", 0.0): 12, ("short", "above", 0.4): 12,
                    ("long", "always", None): 2, ("long", "below", 0.0): 4}
