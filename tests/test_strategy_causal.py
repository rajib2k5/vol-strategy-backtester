"""Milestone 4, part B (plan section 10, task 9): ADR-0001 test 6 for each of the four structures, and what their runs
on the made-up signal store open and close.

Store A is tests/signal_store.py (HAR fits from the first snapshot; snapshots 2023-01-03 to 04-28). Store B, one per
t0, is A with every value dated after t0 tripled and permuted (test_engine_lookahead.perturbed_store), re-priced. Each
structure runs on A and on each B with its gated entry (the long straddle: `always`) and every exit on. Up to t0 the
`signals` rows and every decision (the values in ctx.signals and the intents returned) must be identical: a decision
at t reads nothing dated after t. The five t0: 2023-02-21 and 2023-03-20 (the entry days of the straddles and the
strangle in run A), 2023-03-02 (DTE exits are decided), 2023-03-17 (a monthly expiry, an ex-date and the calendar's
entry) and 2023-04-03 (the -8% gap, a refit day: signal exits). A one-session peek shows only in a decision taken on
t0 itself (on t0 - 1 the peeked session is t0, which B leaves as it is), so each structure must place an order on
each of its ENTRY_T0S, in run A (fix pass 2, review C claim 5).

What the perturbation changes after t0: every value (bids, asks, volumes, closes, rates, dividend amounts, VIX),
tripled and permuted. What it does not change, so a strategy that reads only these after t0 passes unseen: the
contracts listed (symbols, expiries, strikes) and the dates each is quoted on, the snapshot dates, the dividend
ex-dates and the dates of the bars, rates and VIX. Made-up values only.
"""

from __future__ import annotations

from datetime import date

import pyarrow as pa
import pyarrow.compute as pc
import pytest

import engine_helpers as eh
import signal_store as ss
from test_engine_lookahead import perturbed_store
from volbt.strategies import expiry as ex
from volbt.strategies.rules import EntryRule, ExitRules
from volbt.strategies.vol import VolStrategy

D = date
T0S = (D(2023, 2, 21), D(2023, 3, 2), D(2023, 3, 17), D(2023, 3, 20), D(2023, 4, 3))
# The t0 on which each structure opens a position in run A (measured, fix pass 2): a decision taken on t0 itself.
ENTRY_T0S = {"short_straddle": (D(2023, 2, 21), D(2023, 3, 20)), "long_straddle": (D(2023, 2, 21), D(2023, 3, 20)),
             "short_strangle": (D(2023, 2, 21), D(2023, 3, 20)), "straddle_calendar": (D(2023, 3, 17),)}
CASES = {
    "short_straddle": ("short", EntryRule("above", 0.0), ExitRules(14, 1.0, 0.5, -0.4)),
    "long_straddle": ("long", EntryRule(), ExitRules(14, 1.0, 0.5, None, 0.4)),
    "short_strangle": ("short", EntryRule("above", 0.0), ExitRules(14, 1.0, 0.5, -0.4)),
    "straddle_calendar": ("short", EntryRule("above", 0.0), ExitRules(14, 1.0, 0.5, -0.4)),
}


class Recorder(VolStrategy):
    """VolStrategy that writes down, as text, what it was handed and what it returned at each session."""

    def __init__(self, structure: str) -> None:
        side, entry, exits = CASES[structure]
        super().__init__(structure, side, entry, exits)
        self.log, self.decisions = {}, {}

    def decide(self, view, book, ctx):
        orders = super().decide(view, book, ctx)
        self.log[ctx.session_date] = repr((sorted((k, repr(v)) for k, v in ctx.signals.items()), orders))
        self.decisions[ctx.session_date] = (orders, ctx)
        return orders


def contract(osi: str) -> tuple[date, str, float]:
    """(expiry, right, strike) of an OSI symbol, "SPY   230317C00400000"."""
    body = osi[6:]
    return D(2000 + int(body[0:2]), int(body[2:4]), int(body[4:6])), body[6], int(body[7:]) / 1000


def up_to(table, t0):
    return table.filter(pc.less_equal(table["session_date"], pa.scalar(t0, pa.date32())))


@pytest.fixture(scope="module")
def store_a(tmp_path_factory):
    return ss.signal_store(tmp_path_factory.mktemp("strategy_store_a"))


@pytest.fixture(scope="module")
def runs_a(store_a, tmp_path_factory):
    out = {}
    for structure in CASES:
        recorder = Recorder(structure)
        out[structure] = (eh.run(store_a, tmp_path_factory.mktemp(f"a_{structure}"), recorder), recorder)
    return out


@pytest.fixture(scope="module", params=T0S, ids=str)
def runs_b(request, store_a, tmp_path_factory):
    t0 = request.param
    store_b = perturbed_store(store_a, tmp_path_factory.mktemp(f"strategy_store_b_{t0}"), t0)
    out = {}
    for structure in CASES:
        recorder = Recorder(structure)
        out[structure] = (eh.run(store_b, tmp_path_factory.mktemp(f"b_{structure}_{t0}"), recorder), recorder)
    return t0, out


@pytest.mark.parametrize("structure", list(CASES))
def test_no_decision_up_to_t0_moves_when_every_input_after_t0_changes(runs_a, runs_b, structure):
    t0, out_b = runs_b
    (result_a, rec_a), (result_b, rec_b) = runs_a[structure], out_b[structure]
    signals_a, signals_b = eh.table(result_a, "signals"), eh.table(result_b, "signals")
    before_a = signals_a[signals_a["session_date"] <= t0].reset_index(drop=True)
    before_b = signals_b[signals_b["session_date"] <= t0].reset_index(drop=True)
    assert len(before_a) >= 34 and before_a.equals(before_b)             # 34 sessions up to 2023-02-21
    assert {d: v for d, v in rec_a.log.items() if d <= t0} == {d: v for d, v in rec_b.log.items() if d <= t0}
    # The premise: decisions were taken by t0, and the changed future reaches the signals after it.
    assert any(orders for d, (orders, _) in rec_a.decisions.items() if d <= t0)
    if t0 in ENTRY_T0S[structure]:
        # On its entry days the structure opens a position on t0 itself, in run A and in run B alike.
        assert any(order.intent == "open" for order in rec_a.decisions[t0][0]), (structure, t0)
        assert rec_a.log[t0] == rec_b.log[t0]
    assert not signals_a[signals_a["session_date"] > t0].reset_index(drop=True).equals(
        signals_b[signals_b["session_date"] > t0].reset_index(drop=True))


@pytest.mark.parametrize("structure", list(CASES))
def test_each_structure_opens_its_legs_in_its_window_and_closes_at_14_dte(runs_a, structure):
    result, recorder = runs_a[structure]
    opens, closes = 0, {}
    for t, (orders, ctx) in recorder.decisions.items():
        for order in orders:
            legs = [(contract(leg.osi_symbol), leg.ratio) for leg in order.legs]
            if order.intent == "open":
                opens += 1
                expiries = sorted({e for (e, _, _), _ in legs})
                front = expiries[0]
                lo, hi = (22, 35) if structure == "straddle_calendar" else (50, 60)
                assert lo <= ex.dte(front, t, ctx.sessions) <= hi, (t, front)
                assert all((e - t).days <= 180 for e in expiries)
                rights = sorted((e, r, ratio) for (e, r, _), ratio in legs)
                strikes = {k for (_, _, k), _ in legs}
                if structure == "straddle_calendar":
                    back = expiries[1]
                    assert (back.year * 12 + back.month) - (front.year * 12 + front.month) == 1
                    assert rights == [(front, "C", -1), (front, "P", -1), (back, "C", 1), (back, "P", 1)]
                    assert len(strikes) == 1
                else:
                    ratio = 1 if structure == "long_straddle" else -1
                    assert rights == [(front, "C", ratio), (front, "P", ratio)]
                    calls = [k for (_, r, k), _ in legs if r == "C"]
                    puts = [k for (_, r, k), _ in legs if r == "P"]
                    assert (calls[0] > puts[0]) if structure == "short_strangle" else (calls == puts)
            else:
                closes[order.exit_reason] = closes.get(order.exit_reason, 0) + 1
                if order.exit_reason == "dte":
                    front = min(e for (e, _, _), _ in legs)
                    assert ex.dte(front, ctx.next_session, ctx.sessions) <= 14
    assert opens >= 2 and sum(closes.values()) >= 1
    assert structure == "long_straddle" or closes.get("dte", 0) >= 1
    # At most two positions pending or open at any session; one position per (front) expiry.
    daily = eh.table(result, "position_daily")
    counts = daily[daily["status"].isin(["pending", "open"])].groupby("session_date")["position_id"].nunique()
    assert counts.max() <= 2
    lots = eh.table(result, "lots")
    fronts = lots.groupby("position_id")["expiry"].min()
    assert fronts.is_unique and len(fronts) == opens


def test_the_same_object_run_twice_decides_the_same(store_a, runs_a, tmp_path):
    """The engine calls reset() before a run (loop.Run.__init__): the expiries the first run held are forgotten."""
    result, recorder = runs_a["short_straddle"]
    again = eh.run(store_a, tmp_path / "again", recorder)
    assert eh.table(again, "positions").equals(eh.table(result, "positions"))
    assert len(eh.table(result, "positions")) >= 2


def test_a_stop_or_target_refuses_a_hedge_that_leaves_the_pnl_uncomputed(store_a, tmp_path):
    with pytest.raises(ValueError, match="computed"):
        eh.run(store_a, tmp_path / "every_2", Recorder("short_strangle"), hedge_every_n=2)
    dte_only = VolStrategy("short_strangle", "short", EntryRule(), ExitRules(14))
    assert len(eh.table(eh.run(store_a, tmp_path / "dte_only", dte_only, hedge_every_n=2), "positions")) >= 2
