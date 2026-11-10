"""Tests written after the milestone-3 round-2 review: each one fails on a mutant or a bug that review found.

    a reduce-only order must give one of the strategy exit reasons (EXIT_REASONS was never enforced), and the
        exporter refuses a position exit reason the app would refuse (close_all("roll") was exported)
    an opening order on an expiry more than 180 days out is refused (a scripted 363-DTE straddle filled)
    a run stopped on a weekend names the session before it (Friday and Saturday stops gave two run ids)
    a closing fill pays the option fee (O5: no fee on closing fills survived the suite)
    a surface sell priced under 1 cent does not fill (O6: survived every behaviour test)
    hedge_timing next_open trades at the next session's open (O9: a hedge at the close survived), and the last
        session's plan is dropped (documented, not booked)
    a cached view's frames own their memory: no buffer behind a frame holds more than its rows, and the reviewer's
        as_strided attack finds no future smile row (it found 72 at 2015-03-02 through zero-copy slices)
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import engine_helpers as eh
import engine_store as es
from volbt.data.store import Store, YearCache, view
from volbt.engine import fills, loop, report
from volbt.engine.loop import EngineError
from volbt.strategies.base import EXIT_REASONS
from volbt.strategies.reference import RollingShortStraddle

D = date


@pytest.fixture(scope="module")
def reference_run(engine_store, tmp_path_factory):
    return eh.run(engine_store, tmp_path_factory.mktemp("round2_ref"), RollingShortStraddle())


# --- exit reasons ---------------------------------------------------------------------------------------------------

OPEN_THEN_CLOSE = {D(2023, 1, 5): eh.open_straddle(D(2023, 2, 17), 400.0)}


def test_a_close_with_an_exit_reason_outside_the_strategy_list_is_refused(engine_store, tmp_path):
    for reason in ("roll", "expiry", None):          # unknown; the engine's own; none at all
        strategy = eh.Scripted({**OPEN_THEN_CLOSE, D(2023, 1, 10): eh.close_all(reason)})
        with pytest.raises(EngineError, match="exit_reason"):
            eh.run(engine_store, tmp_path / str(reason), strategy)
    strategy = eh.Scripted({**OPEN_THEN_CLOSE, D(2023, 1, 10): eh.close_all("signal")})
    assert eh.run(engine_store, tmp_path / "signal", strategy).status == "ok"


def test_the_exporter_refuses_a_position_exit_reason_the_app_would_refuse(engine_store, tmp_path, monkeypatch):
    """A ledger written by an engine that let "roll" through (here: the check widened) cannot reach the app."""
    monkeypatch.setattr(loop, "EXIT_REASONS", EXIT_REASONS + ("roll",))
    strategy = eh.Scripted({**OPEN_THEN_CLOSE, D(2023, 1, 10): eh.close_all("roll")})
    result = eh.run(engine_store, tmp_path, strategy)
    assert eh.table(result, "positions")["exit_reason"].tolist() == ["roll"]
    with pytest.raises(ValueError, match="'roll' is not one of"):
        report.positions_timeline_body(result.run_dir)


# --- the 180-day ceiling ---------------------------------------------------------------------------------------------

FAR = D(2023, 7, 3)        # 181 days after 2023-01-03, 180 after 01-04; after the fixture's last bar (2023-06-30)


@pytest.fixture(scope="module")
def far_store(tmp_path_factory):
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(es, "EXPIRIES", sorted(es.EXPIRIES + [FAR]))
        return es.built_store(tmp_path_factory.mktemp("far_store"))


def test_an_opening_order_more_than_180_days_out_is_refused_and_180_fills(far_store, tmp_path):
    assert (FAR - D(2023, 1, 3)).days == 181 and (FAR - D(2023, 1, 4)).days == 180
    with pytest.raises(EngineError, match="more than 180 days"):
        eh.run(far_store, tmp_path / "181", eh.Scripted({D(2023, 1, 3): eh.open_straddle(FAR, 400.0)}),
               sample_end=D(2023, 1, 10))
    result = eh.run(far_store, tmp_path / "180", eh.Scripted({D(2023, 1, 4): eh.open_straddle(FAR, 400.0)}),
                    sample_end=D(2023, 1, 10))
    lots = eh.table(result, "lots")
    assert set(lots["expiry"]) == {FAR} and set(lots["qty_open"]) == {-10}


# --- a stopped run's id ----------------------------------------------------------------------------------------------

def test_a_run_stopped_on_a_weekend_or_holiday_names_the_session_before_it(engine_store, tmp_path):
    """Friday 2023-02-17, Saturday 02-18 and Monday 02-20 (a holiday in the fixture) all stop after the same
    sessions, so they are one run: one id, sample_end 02-17."""
    assert D(2023, 2, 20) in es.HOLIDAYS
    results = [eh.run(engine_store, tmp_path / str(stop), RollingShortStraddle(), stop_after=stop)
               for stop in (D(2023, 2, 17), D(2023, 2, 18), D(2023, 2, 20))]
    assert len({r.run_id for r in results}) == 1
    assert [eh.table(r, "runs")["sample_end"].iloc[0] for r in results] == [D(2023, 2, 17)] * 3
    full = eh.run(engine_store, tmp_path / "full", RollingShortStraddle())
    assert full.run_id != results[0].run_id


# --- costs and prices ------------------------------------------------------------------------------------------------

def test_every_option_fill_opening_or_closing_pays_70_cents_a_contract(reference_run):
    """ADR-0002 §3: $0.70 per contract per SIDE, so a closing fill pays it too."""
    fills_table, flows = eh.table(reference_run, "fills"), eh.table(reference_run, "cash_flows")
    orders = eh.table(reference_run, "orders").set_index("order_id")
    options = fills_table[fills_table["instrument"] == "option"]
    closing = options[[bool(orders.loc[o, "reduce_only"]) for o in options["order_id"]]]
    assert len(closing) >= 2 and len(options) > len(closing)
    fees = flows[flows["kind"] == "option_fee"].groupby("ref_id")["amount_cents"].sum()
    for fill_id, qty, fees_cents in zip(options["fill_id"], options["qty"], options["fees_cents"]):
        assert fees.get(fill_id) == -70 * abs(qty), fill_id
        assert fees_cents == 70 * abs(qty)


def test_a_surface_sell_priced_under_one_cent_is_cancelled_no_quote():
    """ADR-0002 §7 and decision B13: a model price minus m h_model that rounds down to 0 cents does not fill."""
    cfg = eh.config()
    assert cfg.surface_half_spread_mult == 1
    for surface_mode in (False, True):
        # 0.012 - 0.005 = 0.007: 0 cents after rounding down
        assert fills.leg_price(fills.NO_QUOTE, True, -1, None, None, 0.012, 0.005, cfg, surface_mode) == (
            None, None, "NO_QUOTE")
        # 0.020 - 0.005 = 0.015: 1 cent, the smallest price that fills
        assert fills.leg_price(fills.NO_QUOTE, True, -1, None, None, 0.020, 0.005, cfg, surface_mode) == (
            1, "surface", None)


# --- hedge_timing next_open ------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def open_store(tmp_path_factory):
    """The fixture with opens 1% below the closes, so a hedge at the open and one at the close differ."""
    return es.built_store(tmp_path_factory.mktemp("open_store"), open_factor=0.99)


def test_next_open_hedges_trade_at_the_next_session_s_open_and_the_last_plan_is_dropped(open_store, tmp_path):
    result = eh.run(open_store, tmp_path, RollingShortStraddle(), hedge_timing="next_open")
    hedges, daily = eh.table(result, "hedges"), eh.table(result, "daily_pnl")
    bars = pq.read_table(open_store.root / "spy_bars" / "part-0.parquet").to_pandas()
    sessions = list(daily["session_date"])
    following = dict(zip(sessions, sessions[1:]))
    open_cents = {as_day(d): int(round(o * 100)) for d, o in zip(bars["date"], bars["open"])}
    close_cents = {as_day(d): int(round(c * 100)) for d, c in zip(bars["date"], bars["close"])}
    assert len(hedges) > 0 and (hedges["shares_traded"] != 0).any()
    for planned, executed, price_cents in zip(hedges["session_date"], hedges["executed_date"], hedges["price_cents"]):
        assert executed == following[planned]
        assert price_cents == open_cents[executed] != close_cents[executed]
    # One plan a session (hedge_mode time, every session); the last one has no next open in the run (item 18).
    assert list(hedges["session_date"]) == sessions[:-1]


def as_day(value) -> date:
    return date(value.year, value.month, value.day)


# --- the year cache's frames own their memory (item 12) -----------------------------------------------------------

def numpy_root(array: np.ndarray) -> np.ndarray:
    """The widest numpy array behind `array`: follow .base while it is an ndarray."""
    while isinstance(array.base, np.ndarray):
        array = array.base
    return array


def memory_problems(frame) -> list[str]:
    """Each buffer behind `frame` that may hold more than the frame's own rows (or whose size cannot be known)."""
    problems, rows = [], len(frame)
    numeric_width = sum(frame[c].dtype.itemsize for c in frame.columns
                        if isinstance(frame[c].dtype, np.dtype) and frame[c].dtype != object)
    for name in frame.columns:
        column = frame[name]
        if hasattr(column.array, "__arrow_array__"):
            # pandas' Arrow-backed strings: validity bits, offsets and string data, each sized to these rows
            for chunk in column.array.__arrow_array__().chunks:
                width = 8 if pa.types.is_large_string(chunk.type) else 4
                validity, offsets, data = chunk.buffers()
                used = int(np.frombuffer(offsets, dtype=np.int64 if width == 8 else np.int32)[-1]) if offsets else 0
                if chunk.offset != 0 or offsets.size > (len(chunk) + 1) * width or (data is not None and data.size > used) \
                        or (validity is not None and validity.size > (len(chunk) + 7) // 8):
                    problems.append(f"{name}: Arrow buffers {[b.size if b else 0 for b in chunk.buffers()]} "
                                    f"for {len(chunk)} rows at offset {chunk.offset}")
        elif column.dtype == object:
            arrays = [value for value in column if isinstance(value, np.ndarray)]
            need = sum(a.nbytes for a in arrays)
            for a in arrays:
                root = numpy_root(a)
                if not root.flags.owndata or root.nbytes > need:
                    problems.append(f"{name}: an element's memory is {root.nbytes} bytes, owned {root.flags.owndata}, "
                                    f"for {need} bytes of elements")
                    break
        else:
            root = numpy_root(column.to_numpy())
            if not root.flags.owndata or root.nbytes > rows * numeric_width:
                problems.append(f"{name}: {root.nbytes} bytes, owned {root.flags.owndata}, for {rows} rows")
    return problems


def test_no_frame_a_cached_view_returns_holds_memory_beyond_its_rows(engine_store):
    t = D(2023, 2, 1)
    v = view(t, "validation", engine_store, YearCache(engine_store, "optionsdx"))
    some = sorted(v.quotes(t)["osi_symbol"])[:7]
    frames = {"chain": v.chain(t), "quotes": v.quotes(t), "quotes(symbols)": v.quotes(t, some),
              "quote_ivs": v.quote_ivs(t), "quote_ivs(symbols)": v.quote_ivs(t, some), "forwards": v.forwards(t),
              "smiles": v.smiles(t), "spy_bars": v.spy_bars(), "rates": v.rates(), "dividends": v.dividends(),
              "vix": v.vix()}
    assert len(frames["quotes(symbols)"]) == 7 and len(frames["smiles"]) > 0
    assert frames["quotes"]["osi_symbol"].dtype != object            # strings are Arrow-backed: their buffers count
    assert {name: memory_problems(frame) for name, frame in frames.items()} == {name: [] for name in frames}


PROBE = Path(__file__).resolve().parent / "leak_probe.py"


def run_probe(root, source: str, as_of: str, split: str, n: int) -> dict:
    """tests/leak_probe.py in a fresh interpreter (its docstring says why)."""
    done = subprocess.run([sys.executable, "-B", str(PROBE), str(root), source, as_of, split, str(n)],
                          capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_the_as_strided_attack_reads_no_future_smile_row_on_the_fixture(engine_store):
    found = run_probe(engine_store.root, "optionsdx", "2023-02-01", "validation", 512)
    assert found["sessions_checked"] == 30
    assert (found["future_rows"], found["symbols_in_buffers"]) == (0, found["frame_rows"])


@pytest.mark.real_data
def test_the_as_strided_attack_reads_no_future_smile_row_on_the_real_store():
    """The reviewer's own case: 2015-03-02, 4,000 values past the last smile row."""
    store = Store()
    if not store.has("smile_fits"):
        pytest.skip("no built store")
    found = run_probe(store.root, "optionsdx", "2015-03-02", "development", 4000)
    assert found["sessions_checked"] == 30
    assert (found["future_rows"], found["symbols_in_buffers"]) == (0, found["frame_rows"])
