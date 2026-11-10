"""Helpers for the engine tests (not a test file): a scripted strategy, a run wrapper, ledger readers."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import pyarrow.parquet as pq

import engine_store as es
from volbt import build
from volbt.engine.loop import run_backtest
from volbt.engine.run_config import RunConfig
from volbt.strategies.base import LegIntent, OrderIntent


class Scripted:
    """A test strategy: on each date in `script` it returns the intents that function builds from (view, book, ctx).

    script: {date: callable(view, book, ctx) -> list[OrderIntent]}. Every other session it returns [].
    """

    name = "Scripted"

    def __init__(self, script: dict, label: str = "scripted") -> None:
        self.script, self.label = script, label
        self.calls = []

    def params(self) -> dict:
        return {"label": self.label}

    def decide(self, view, book, ctx):
        self.calls.append(ctx.session_date)
        action = self.script.get(ctx.session_date)
        return list(action(view, book, ctx)) if action else []


def open_straddle(expiry: date, strike: float, contracts: int = 10, sign: int = -1):
    """A script action that opens a straddle (sign -1 short, +1 long) at a fixed strike."""
    def action(view, book, ctx):
        legs = (LegIntent(es.symbol(expiry, "C", strike), sign), LegIntent(es.symbol(expiry, "P", strike), sign))
        return [OrderIntent(None, "open", "short_straddle" if sign < 0 else "long_straddle", legs, contracts)]
    return action


def open_legs(legs: list[tuple[str, int]], packages: int = 1, structure: str = "custom"):
    def action(view, book, ctx):
        return [OrderIntent(None, "open", structure, tuple(LegIntent(s, r) for s, r in legs), packages)]
    return action


def close_all(exit_reason: str = "signal"):
    """A script action that closes every open lot of every open position (one order per position)."""
    def action(view, book, ctx):
        out = []
        for position in book.open_positions():
            lots = [lot for lot in position.lots if lot.qty != 0]
            if lots and not book.has_pending(position.position_id):
                out.append(OrderIntent(position.position_id, "close", position.structure,
                                       tuple(LegIntent(lot.osi_symbol, -lot.qty) for lot in lots), 1, exit_reason))
        return out
    return action


def config(**overrides) -> RunConfig:
    base = RunConfig(sample_start=es.FIRST_SNAPSHOT, sample_end=es.LAST_SNAPSHOT, split="validation")
    return replace(base, **overrides)


def made_up_gate(cfg, strategy, trial_hash):
    """A run gate that passes every run and records none: the made-up stores' sessions are in 2022-2023, past the
    development split, and run_backtest refuses such a run without a gate (tests/test_prereg.py tests the real one)."""
    return None


def run(store, root: Path, strategy, check: bool = True, **kwargs):
    """run_backtest on `store` with the store check of tools/run_backtest.py and made_up_gate (or kwargs'
    run_gate); the other kwargs go to RunConfig."""
    stop_after = kwargs.pop("stop_after", None)
    on_session_end = kwargs.pop("on_session_end", None)
    commit = kwargs.pop("source_commit", "0" * 40)
    gate = kwargs.pop("run_gate", made_up_gate)
    return run_backtest(config(**kwargs), strategy, store=store, runs_root=Path(root), stop_after=stop_after,
                        on_session_end=on_session_end, source_commit=commit,
                        store_check=build.require_current if check else None, run_gate=gate)


def table(result_or_dir, name: str):
    """One ledger table as a pandas DataFrame."""
    run_dir = getattr(result_or_dir, "run_dir", result_or_dir)
    return pq.read_table(Path(run_dir) / name / "part-0.parquet").to_pandas()
