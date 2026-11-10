"""The milestone-4 interface (plan sections 3 and 10, task 1): what a strategy sees and returns, the run config's
split rules and the run-gate hook. On tests/engine_store.py's made-up store.
"""

from __future__ import annotations

import dataclasses
from datetime import date
from fractions import Fraction
from types import MappingProxyType

import pytest

import engine_helpers as eh
import engine_store as es
from volbt import build
from volbt.engine.loop import EngineError, intake, run_backtest
from volbt.engine.run_config import RunConfig, config_hash, config_json, trial_hash
from volbt.strategies.base import LegIntent, OrderIntent
from volbt.strategies.reference import RollingShortStraddle

D = date
EXPIRY = D(2023, 3, 17)


def straddle_legs(sign=-1):
    return (LegIntent(es.symbol(EXPIRY, "C", 400.0), sign), LegIntent(es.symbol(EXPIRY, "P", 400.0), sign))


# --- intake and entry_signal ---------------------------------------------------------------------------------------

def test_intake_copies_entry_signal_as_a_plain_float():
    """The engine checks and books intake's copy (loop.intake), so the copy must carry the new field."""
    copied = intake(OrderIntent(None, "open", "short_straddle", straddle_legs(), 10, entry_signal=Fraction(1, 4)))
    assert copied.entry_signal == 0.25 and type(copied.entry_signal) is float
    assert intake(OrderIntent(None, "open", "short_straddle", straddle_legs(), 10)).entry_signal is None


def test_a_reduce_only_order_with_an_entry_signal_is_refused(engine_store, tmp_path):
    def close_with_signal(view, book, ctx):
        position = book.open_positions()[0]
        legs = tuple(LegIntent(lot.osi_symbol, 1) for lot in position.lots)
        return [OrderIntent(position.position_id, "close", position.structure, legs, 10, "signal", entry_signal=0.1)]

    strategy = eh.Scripted({D(2023, 2, 1): eh.open_straddle(EXPIRY, 400.0), D(2023, 2, 6): close_with_signal})
    with pytest.raises(EngineError, match="carries no entry_signal"):
        eh.run(engine_store, tmp_path, strategy, sample_end=D(2023, 2, 10))


class Watcher(eh.Scripted):
    """Opens one straddle with an entry signal and records the context and the book it is shown."""

    def __init__(self) -> None:
        super().__init__({D(2023, 2, 1): self.open_with_signal})
        self.contexts, self.books = {}, {}

    @staticmethod
    def open_with_signal(view, book, ctx):
        return [OrderIntent(None, "open", "short_straddle", straddle_legs(), 10, entry_signal=0.37)]

    def decide(self, view, book, ctx):
        self.contexts[ctx.session_date], self.books[ctx.session_date] = ctx, book
        return super().decide(view, book, ctx)


@pytest.fixture(scope="module")
def watched(engine_store, tmp_path_factory):
    strategy = Watcher()
    result = eh.run(engine_store, tmp_path_factory.mktemp("watched"), strategy, sample_end=D(2023, 2, 15))
    return result, strategy


def test_the_entry_signal_reaches_the_positions_table_and_the_book(watched):
    result, strategy = watched
    assert eh.table(result, "positions")["entry_signal"].tolist() == [0.37]
    shown = strategy.books[D(2023, 2, 15)].open_positions()[0]
    assert shown.entry_signal == 0.37 and shown.premium_usd > 0 and shown.pnl_usd is not None
    assert all(lot.mark_price is not None and lot.mark_price > 0 for lot in shown.lots)


def test_the_context_is_read_only_and_carries_the_close_s_nav(watched):
    result, strategy = watched
    nav = dict(zip(*[eh.table(result, "daily_pnl")[c] for c in ("session_date", "nav_mid")]))
    assert {day: ctx.nav_mid_usd for day, ctx in strategy.contexts.items()} == nav
    ctx = strategy.contexts[D(2023, 2, 15)]
    assert type(ctx.signals) is MappingProxyType and dict(ctx.signals) == {}
    with pytest.raises(TypeError):
        ctx.signals["vrp"] = 1.0
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.nav_mid_usd = 0.0


# --- the run config ------------------------------------------------------------------------------------------------

def test_a_trial_past_2019_needs_a_prereg_id_and_no_diagnostic_runs_on_the_holdout():
    with pytest.raises(ValueError, match="prereg_id"):
        RunConfig(D(2020, 1, 2), D(2020, 6, 30), "validation", run_purpose="trial")
    assert RunConfig(D(2020, 1, 2), D(2020, 6, 30), "validation", run_purpose="trial", prereg_id="p").prereg_id == "p"
    assert RunConfig(D(2019, 1, 2), D(2019, 12, 31), "development", run_purpose="trial").prereg_id is None
    assert RunConfig(D(2020, 1, 2), D(2020, 6, 30), "validation").run_purpose == "diagnostic"
    with pytest.raises(ValueError, match="holdout"):
        RunConfig(D(2024, 1, 2), D(2024, 6, 28), "holdout", prereg_id="p")
    for bad in ("", 5, " ", "\t\n"):
        with pytest.raises(ValueError, match="prereg_id"):
            RunConfig(D(2019, 1, 2), D(2019, 12, 31), "development", prereg_id=bad)


def test_without_a_prereg_id_the_config_hash_is_the_one_m3_recorded():
    """The M3 development run (data/runs, 2026-11-09) recorded config_hash 9700548f...: adding the field must not
    rename every M3 trial."""
    cfg = RunConfig(D(2010, 1, 4), D(2019, 12, 31), "development")
    strategy = RollingShortStraddle(contracts=10, target_dte=30, min_dte=21, exit_dte=7, max_dte=180)
    assert config_hash(cfg, strategy) == "9700548f21bfbcfa14d8eee263c0827284c61f9a63ee8f56c09d90e0447e9286"
    assert "prereg_id" not in config_json(cfg, strategy)["engine"]
    named = dataclasses.replace(cfg, prereg_id="2026-11-09-x")
    assert config_json(named, strategy)["engine"]["prereg_id"] == "2026-11-09-x"
    assert config_hash(named, strategy) != config_hash(cfg, strategy)


# --- the run gate --------------------------------------------------------------------------------------------------

def gated_run(store, root, cfg, strategy, gate):
    return run_backtest(cfg, strategy, store=store, runs_root=root, source_commit="0" * 40,
                        store_check=build.require_current, run_gate=gate)


def test_the_run_gate_is_asked_once_before_anything_and_its_recorder_after_the_write(engine_store, tmp_path):
    calls, records = [], []
    strategy = eh.Scripted({})

    def gate(cfg, strat, hash_value):
        calls.append((cfg.sample_end, strat, hash_value))
        return lambda run_id, chash: records.append((run_id, chash, (tmp_path / "ok" / f"run_id={run_id}").is_dir()))

    cfg = eh.config(sample_end=D(2023, 1, 10))
    result = gated_run(engine_store, tmp_path / "ok", cfg, strategy, gate)
    assert calls == [(D(2023, 1, 10), strategy, trial_hash(cfg, strategy))]
    assert records == [(result.run_id, result.config_hash, True)] and result.run_dir.is_dir()

    def refuse(cfg, strat, hash_value):
        raise PermissionError("not listed")

    with pytest.raises(PermissionError, match="not listed"):
        gated_run(engine_store, tmp_path / "refused", cfg, eh.Scripted({}), refuse)
    assert not (tmp_path / "refused").exists() or not any((tmp_path / "refused").rglob("*.parquet"))


def test_a_run_past_2019_without_a_gate_is_refused_before_the_store_is_read(tmp_path):
    """Fails closed (fix pass, item 3 i and iv): the store is a stub whose every read raises, so a refusal made after a
    read would surface as the stub's error, not the engine's or the gate's."""
    class Unreadable:
        def __getattr__(self, name):
            raise AssertionError(f"the store was read ({name}) before the gate")

    strategy = eh.Scripted({})
    cfg = eh.config(sample_end=D(2023, 1, 10))
    with pytest.raises(EngineError, match="needs a run_gate"):
        run_backtest(cfg, strategy, store=Unreadable(), runs_root=tmp_path / "none", run_gate=None)

    def refuse(cfg, strat, hash_value):
        raise PermissionError("refused by the gate")

    with pytest.raises(PermissionError, match="refused by the gate"):
        run_backtest(cfg, strategy, store=Unreadable(), runs_root=tmp_path / "none", run_gate=refuse,
                     store_check=build.require_current)
    assert not (tmp_path / "none").exists()


def test_the_trial_hash_leaves_out_where_a_trial_runs_and_nothing_else():
    """Item 3 iii, fix pass 2 item 4: a configuration's validation trial (OptionsDX quotes) and its holdout trial
    (DoltHub surface) share a trial_hash (their config_hash and run id differ); a change to the configuration itself
    changes it."""
    strategy = RollingShortStraddle()
    validation = RunConfig(D(2020, 1, 2), D(2023, 12, 29), "validation", run_purpose="trial", prereg_id="2026-x")
    holdout = RunConfig(D(2024, 1, 2), D(2026, 10, 26), "holdout", run_purpose="trial", prereg_id="2026-y",
                        data_source="dolthub", execution_mode="surface")
    development = RunConfig(D(2010, 1, 4), D(2019, 12, 31), "development")
    assert trial_hash(validation, strategy) == trial_hash(holdout, strategy) == trial_hash(development, strategy)
    assert len({config_hash(c, strategy) for c in (validation, holdout, development)}) == 3
    assert trial_hash(dataclasses.replace(holdout, hedge_every_n=2), strategy) != trial_hash(holdout, strategy)
    assert trial_hash(holdout, RollingShortStraddle(exit_dte=8)) != trial_hash(holdout, strategy)
    assert trial_hash(dataclasses.replace(development, seed=1), strategy) != trial_hash(development, strategy)
    # fix pass 4, item F6a/O1: the trial_group is a label, so it places a run and does not define a configuration
    relabelled = dataclasses.replace(holdout, trial_group="anything_else")
    assert trial_hash(relabelled, strategy) == trial_hash(holdout, strategy)
    assert config_hash(relabelled, strategy) != config_hash(holdout, strategy)


def test_a_seed_other_than_0_is_refused_for_every_run_the_gate_can_accept_past_2019():
    """Fix pass 4, item F6b (review E claim 4): no code draws from the seed, and it is in the trial_hash, so a run the
    run gate can accept past 2019 (a trial, or a diagnostic that names its kind) has seed 0: a seed changed there would
    be a new trial_hash for the same run. A development run may change it, and so may a run past 2019 that names no
    kind, which only a test's made-up gate passes (ADR-0001 test 3 runs seed 7 on the made-up store's 2022-2023
    sessions); the M3 config_hash keeps the field."""
    for window in ((D(2020, 1, 2), D(2023, 12, 29), "validation"), (D(2019, 6, 3), D(2020, 1, 2), "validation")):
        RunConfig(*window, diagnostic_kind="smoke")
        with pytest.raises(ValueError, match="no code draws from the seed"):
            RunConfig(*window, diagnostic_kind="smoke", seed=1)
        with pytest.raises(ValueError, match="no code draws from the seed"):
            RunConfig(*window, run_purpose="trial", prereg_id="2026-x", seed=1)
        assert RunConfig(*window, seed=7).seed == 7
    with pytest.raises(ValueError, match="no code draws from the seed"):
        RunConfig(D(2024, 1, 2), D(2026, 10, 26), "holdout", run_purpose="trial", prereg_id="2026-y",
                  data_source="dolthub", execution_mode="surface", seed=7)
    assert RunConfig(D(2010, 1, 4), D(2019, 12, 31), "development", seed=7).seed == 7
    assert RunConfig(D(2010, 1, 4), D(2019, 12, 31), "development", run_purpose="trial", seed=7).seed == 7
    cfg = RunConfig(D(2010, 1, 4), D(2019, 12, 31), "development")
    assert config_json(cfg, RollingShortStraddle())["engine"]["seed"] == 0


def test_a_trial_past_2019_runs_on_its_splits_source_and_mode():
    """Fix pass 2, item 4 (review B claim 4a): ADR-0010 §1's protocol, validation on OptionsDX quotes and the holdout
    on the DoltHub surface; any other pair is refused for a trial past 2019, never for a diagnostic or a development
    trial."""
    window = {"validation": (D(2020, 1, 2), D(2023, 12, 29)), "holdout": (D(2024, 1, 2), D(2026, 10, 26))}
    allowed = {"validation": ("optionsdx", "quote"), "holdout": ("dolthub", "surface")}
    for split, (start, end) in window.items():
        for source in ("optionsdx", "dolthub"):
            for mode in ("quote", "surface"):
                make = lambda: RunConfig(start, end, split, run_purpose="trial", prereg_id="p", data_source=source,
                                         execution_mode=mode)
                if (source, mode) == allowed[split]:
                    assert make().split == split
                else:
                    with pytest.raises(ValueError, match="its split's data and execution"):
                        make()
    with pytest.raises(ValueError, match="its split's data and execution"):
        RunConfig(D(2010, 1, 4), D(2020, 6, 30), "development", run_purpose="trial", prereg_id="p")
    assert RunConfig(D(2020, 1, 2), D(2023, 12, 29), "validation", data_source="dolthub").run_purpose == "diagnostic"
    assert RunConfig(D(2010, 1, 4), D(2019, 12, 31), "development", run_purpose="trial", data_source="dolthub",
                     execution_mode="surface").prereg_id is None


def test_a_vol_strategy_validated_on_optionsdx_and_held_out_on_dolthub_is_one_trial():
    """Fix pass 2, item 4: VolStrategy reads its VrpSignal from the run's source, so its parameters name the source;
    the trial_hash leaves out a "source" equal to the run's data source (and keeps one that differs)."""
    from volbt.strategies.rules import EntryRule, ExitRules
    from volbt.strategies.vol import VolStrategy

    def vol(source):
        return VolStrategy("short_straddle", "short", EntryRule(), ExitRules(7), rv_model="har", source=source)

    validation = RunConfig(D(2020, 1, 2), D(2023, 12, 29), "validation", run_purpose="trial", prereg_id="p")
    holdout = RunConfig(D(2024, 1, 2), D(2026, 10, 26), "holdout", run_purpose="trial", prereg_id="p",
                        data_source="dolthub", execution_mode="surface")
    assert trial_hash(validation, vol("optionsdx")) == trial_hash(holdout, vol("dolthub"))
    assert config_hash(validation, vol("optionsdx")) != config_hash(holdout, vol("dolthub"))
    assert trial_hash(holdout, vol("optionsdx")) != trial_hash(holdout, vol("dolthub"))


# --- signals a strategy declares -----------------------------------------------------------------------------------

class Constant:
    """A signal that returns whatever it is given."""

    def __init__(self, name, value):
        self.name, self.value = name, value

    def params(self):
        return {}

    def reset(self):
        pass

    def update(self, view, n_window):
        return self.value


class Declares(eh.Scripted):
    def __init__(self, signals):
        super().__init__({})
        self.signals = signals


class Signals:
    """A strategy whose parameters say nothing of its signals (review B's attack)."""

    name = "vrp-straddle"

    def __init__(self, *signals):
        self.signals = signals

    def params(self):
        return {"contracts": 10}


def test_signal_parameters_define_the_trial():
    """Fix pass 2, item 5 (review B claim 4b): two strategies that differ only in their signal's RV model are two
    trials (config_hash and trial_hash differ); a strategy with no signals keeps its pre-M4 config_json."""
    from volbt.signals.vrp import VrpSignal

    cfg = RunConfig(D(2020, 1, 2), D(2023, 12, 29), "validation", run_purpose="trial", prereg_id="p")
    har, naive = Signals(VrpSignal("har", name="vrp")), Signals(VrpSignal("naive", name="vrp"))
    assert config_hash(cfg, har) != config_hash(cfg, naive) and trial_hash(cfg, har) != trial_hash(cfg, naive)
    assert config_json(cfg, har)["signals"] == [{"name": "vrp", "params": {
        "rv_model": "har", "source": "optionsdx", "horizon": 21, "min_pairs": 504, "window_days": 30}}]
    assert "signals" not in config_json(cfg, RollingShortStraddle())


def test_a_signal_without_params_is_refused(engine_store, tmp_path):
    """Fix pass 2, item 5: the engine refuses a signal whose parameters it cannot record: in config_json (so in the
    trial_hash a gate is asked with, before anything is read) and when a Run takes the strategy's signals."""
    from volbt.data.store import session_calendar
    from volbt.engine.loop import Run

    class NoParams(Constant):
        params = None

    strategy = Declares((NoParams("s", None),))
    with pytest.raises(ValueError, match="no params"):
        config_json(eh.config(), strategy)
    with pytest.raises(ValueError, match="no params"):
        eh.run(engine_store, tmp_path / "a", strategy, sample_end=D(2023, 1, 10))
    assert not (tmp_path / "a").exists()
    calendar = session_calendar(engine_store)
    with pytest.raises(EngineError, match="no params"):
        Run(eh.config(), strategy, engine_store, calendar, calendar[:5])


def test_the_runs_row_carries_the_callers_rerun_of_and_reason(engine_store, tmp_path):
    """Fix pass 2, item 8 (review B N3): runs.rerun_of and runs.rerun_reason are the values the caller gives."""
    import pyarrow.parquet as pq

    def rerun(result):
        row = pq.read_table(result.run_dir / "runs" / "part-0.parquet").to_pylist()[0]
        return row["rerun_of"], row["rerun_reason"]

    first = eh.run(engine_store, tmp_path / "first", eh.Scripted({}), sample_end=D(2023, 1, 10))
    assert rerun(first) == (None, None)
    again = run_backtest(eh.config(sample_end=D(2023, 1, 10)), eh.Scripted({}), store=engine_store,
                         runs_root=tmp_path / "again", source_commit="0" * 40, run_gate=eh.made_up_gate,
                         rerun_of=first.run_id, rerun_reason="defect #1")
    assert rerun(again) == (first.run_id, "defect #1")
    for bad in ("", " ", 5):
        with pytest.raises(EngineError, match="non-blank"):
            run_backtest(eh.config(sample_end=D(2023, 1, 10)), eh.Scripted({}), store=engine_store,
                         runs_root=tmp_path / "bad", run_gate=eh.made_up_gate, rerun_reason=bad)


def test_signal_names_must_be_distinct_and_values_must_be_signal_values(engine_store, tmp_path):
    with pytest.raises(EngineError, match="distinct"):
        eh.run(engine_store, tmp_path / "a", Declares((Constant("s", None), Constant("s", None))),
               sample_end=D(2023, 1, 10))
    with pytest.raises(EngineError, match="not a SignalValue"):
        eh.run(engine_store, tmp_path / "b", Declares((Constant("s", 0.5),)), sample_end=D(2023, 1, 10))


# --- fix pass 3, item D6 (review D claim 6): what a diagnostic past 2019 is -----------------------------------------

def test_a_diagnostic_kind_names_a_validation_diagnostic_that_fits_its_config():
    """RunConfig.diagnostic_kind is one of DIAGNOSTIC_KINDS (ADR-0010 §1's volume cap and ADR-0009 §4's runs S, M
    and M'; plan section 6's smoke and budget runs), on a validation diagnostic, with the fields that kind needs."""
    from volbt.engine.run_config import DIAGNOSTIC_KINDS

    base = dict(sample_start=D(2021, 1, 4), sample_end=D(2021, 6, 30), split="validation")
    fits = {"volume_cap": dict(cap_mode="volume"), "surface_s": dict(execution_mode="surface"),
            "masked_m": dict(execution_mode="surface", chain_mask="dolthub"),
            "masked_m_prime": dict(execution_mode="surface", chain_mask="dolthub_daily"), "smoke": {}, "budget": {}}
    assert set(fits) == set(DIAGNOSTIC_KINDS)
    for kind, extra in fits.items():
        if kind.startswith("masked"):           # named, but a masked chain needs a masked pricing build (not yet)
            with pytest.raises(ValueError, match="masked run needs"):
                RunConfig(**base, **extra, diagnostic_kind=kind)
            continue
        assert RunConfig(**base, **extra, diagnostic_kind=kind).diagnostic_kind == kind
    with pytest.raises(ValueError, match="diagnostic_kind"):
        RunConfig(**base, diagnostic_kind="exploration")
    with pytest.raises(ValueError, match="validation diagnostic"):
        RunConfig(**base, run_purpose="trial", prereg_id="p", diagnostic_kind="smoke")
    with pytest.raises(ValueError, match="validation diagnostic"):
        RunConfig(D(2019, 1, 2), D(2019, 12, 31), "development", diagnostic_kind="smoke")
    with pytest.raises(ValueError, match="needs"):
        RunConfig(**base, diagnostic_kind="volume_cap")                             # cap_mode hard_only
    with pytest.raises(ValueError, match="needs"):
        RunConfig(**base, diagnostic_kind="surface_s")                              # quote mode
    with pytest.raises(ValueError, match="needs"):
        RunConfig(**base, fill_timing="same_close", diagnostic_kind="smoke")


def test_the_diagnostic_kind_is_dropped_when_none_and_is_a_placement_field():
    """None keeps every M3 hash (9700548f...); a kind enters config_json and config_hash, not the trial_hash."""
    from volbt.engine.run_config import TRIAL_PLACEMENT

    cfg = RunConfig(D(2010, 1, 4), D(2019, 12, 31), "development")
    strategy = RollingShortStraddle(contracts=10, target_dte=30, min_dte=21, exit_dte=7, max_dte=180)
    assert "diagnostic_kind" not in config_json(cfg, strategy)["engine"]
    assert config_hash(cfg, strategy) == "9700548f21bfbcfa14d8eee263c0827284c61f9a63ee8f56c09d90e0447e9286"
    assert "diagnostic_kind" in TRIAL_PLACEMENT and "trial_group" in TRIAL_PLACEMENT and "seed" not in TRIAL_PLACEMENT
    plain = RunConfig(D(2020, 1, 2), D(2020, 6, 30), "validation")
    smoke, budget = (dataclasses.replace(plain, diagnostic_kind=kind) for kind in ("smoke", "budget"))
    assert config_json(smoke, strategy)["engine"]["diagnostic_kind"] == "smoke"
    assert len({config_hash(c, strategy) for c in (plain, smoke, budget)}) == 3
    assert trial_hash(plain, strategy) == trial_hash(smoke, strategy) == trial_hash(budget, strategy)
