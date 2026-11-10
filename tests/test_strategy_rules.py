"""Milestone 4, part B (plan section 5, task 9): the entry and exit rules, and VolStrategy's decisions on made-up books.

Entries: `always` enters on any s, a gated entry only on a finite s on its side of theta. Exits: stop > profit_target
> signal > dte, stop and target on the engine's hedged pnl against |premium|, a NaN s holds the signal exit only, a
NaN pnl is refused when a stop or target is on. VolStrategy: one close order per position (none while one is
pending), at most 2 positions pending or open, one position per expiry until reset(), the calendar's back leg or no
entry, the strategy's own source only. Made-up values.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

import strategy_fakes as sf
from volbt.strategies.base import LegIntent
from volbt.strategies.rules import EntryRule, ExitRules, exit_reason
from volbt.strategies.vol import VolStrategy

D = date
NAN = float("nan")
SESSIONS = sf.weekdays(D(2023, 1, 2), D(2023, 12, 29), {D(2023, 4, 7)})


# --- the rules -----------------------------------------------------------------------------------------------------

def test_always_enters_on_any_s_and_a_gate_needs_a_finite_s_on_its_side():
    assert EntryRule().allows(NAN) and EntryRule().allows(-5.0)
    above, below = EntryRule("above", 0.4), EntryRule("below", 0.0)
    assert [above.allows(s) for s in (0.39, 0.4, 0.41, NAN, math.inf * 0)] == [False, True, True, False, False]
    assert [below.allows(s) for s in (0.01, 0.0, -0.3, NAN)] == [False, True, True, False]
    for bad in (dict(gate="above"), dict(gate="always", theta=0.0), dict(gate="sideways", theta=0.0),
                dict(gate="below", theta=NAN)):
        with pytest.raises(ValueError):
            EntryRule(**bad)


def test_the_exits_go_stop_then_target_then_signal_then_dte():
    rules = ExitRules(14, stop=1.0, target=0.5, signal_below=0.0)
    # (pnl, premium, s, dte_next): each row also meets every rule after its own.
    assert exit_reason(rules, -1000.0, 1000.0, -0.1, 14) == "stop"
    assert exit_reason(rules, -999.0, 1000.0, -0.1, 14) == "signal"
    assert exit_reason(rules, 500.0, -1000.0, -0.1, 14) == "profit_target"      # a debit: |premium|
    assert exit_reason(rules, 499.0, 1000.0, 0.0, 14) == "signal"
    assert exit_reason(rules, 0.0, 1000.0, 0.01, 14) == "dte"
    assert exit_reason(rules, 0.0, 1000.0, 0.01, 15) is None
    assert exit_reason(rules, 0.0, 0.0, 0.01, 30) == "stop"                       # premium 0: both hold, stop wins
    long_rules = ExitRules(14, signal_above=0.4)
    assert [exit_reason(long_rules, NAN, 1.0, s, 20) for s in (0.39, 0.4)] == [None, "signal"]


def test_a_nan_s_holds_only_the_signal_exit():
    rules = ExitRules(14, stop=1.0, target=0.5, signal_below=0.0)
    assert exit_reason(rules, 0.0, 1000.0, NAN, 20) is None
    assert exit_reason(rules, 0.0, 1000.0, NAN, 14) == "dte"
    assert exit_reason(rules, -2000.0, 1000.0, NAN, 20) == "stop"


def test_a_stop_or_target_refuses_a_pnl_the_engine_did_not_compute():
    for rules in (ExitRules(14, stop=1.0), ExitRules(14, target=0.5)):
        with pytest.raises(ValueError, match="computed"):
            exit_reason(rules, NAN, 1000.0, 0.1, 30)
    assert exit_reason(ExitRules(14, signal_below=0.0), NAN, 1000.0, 0.1, 14) == "dte"


# --- VolStrategy's decisions ---------------------------------------------------------------------------------------

E1, E2, E3 = D(2023, 6, 16), D(2023, 7, 21), D(2023, 8, 18)
T = E2 - timedelta(days=55)                          # 2023-05-27 is a Saturday: use the Friday before
T = T - timedelta(days=1) if T.weekday() == 5 else T


def view_at(t, expiries=(E1, E2, E3), **kw):
    return sf.FakeView(t, {e: 401.0 + i for i, e in enumerate(expiries)}, range(380, 421, 5), **kw)


def short_straddle(**kw):
    return VolStrategy("short_straddle", "short", kw.pop("entry", EntryRule()), kw.pop("exits", ExitRules(14)), **kw)


def test_an_entry_opens_the_atm_straddle_on_the_monthly_at_50_to_60_dte_with_its_signal():
    t = T
    assert 50 <= (E2 - t).days <= 60
    orders = short_straddle().decide(view_at(t), sf.book(t), sf.context(t, SESSIONS, s=NAN))
    assert len(orders) == 1 and orders[0].intent == "open" and orders[0].packages == 10
    assert orders[0].legs == (LegIntent(sf.symbol(E2, "C", 400), -1), LegIntent(sf.symbol(E2, "P", 400), -1))
    assert orders[0].entry_signal is None and orders[0].structure == "short_straddle"
    gated = short_straddle(entry=EntryRule("above", 0.4))
    assert gated.decide(view_at(t), sf.book(t), sf.context(t, SESSIONS, s=0.39)) == []
    assert gated.decide(view_at(t), sf.book(t), sf.context(t, SESSIONS, s=NAN)) == []
    assert gated.decide(view_at(t), sf.book(t), sf.context(t, SESSIONS, s=0.4))[0].entry_signal == 0.4
    long = VolStrategy("long_straddle", "long", EntryRule("below", 0.0), ExitRules(14))
    assert [leg.ratio for leg in long.decide(view_at(t), sf.book(t), sf.context(t, SESSIONS, s=-0.2))[0].legs] == [1, 1]
    assert short_straddle().decide(view_at(t), sf.book(t), sf.context(t, SESSIONS, has_snapshot=False)) == []


def test_at_most_two_positions_pending_or_open():
    t, strategy = T, short_straddle()
    one = [sf.straddle_position(1, E3)]
    assert len(strategy.decide(view_at(t), sf.book(t, one), sf.context(t, SESSIONS))) == 1
    strategy.reset()
    two = one + [sf.straddle_position(2, E3, strike=405.0)]
    assert strategy.decide(view_at(t), sf.book(t, two), sf.context(t, SESSIONS)) == []
    strategy.reset()
    pending = one + [sf.straddle_position(2, E3, status="pending")]
    assert strategy.decide(view_at(t), sf.book(t, pending), sf.context(t, SESSIONS)) == []
    three = short_straddle(max_open=3)
    assert len(three.decide(view_at(t), sf.book(t, two), sf.context(t, SESSIONS))) == 1


def test_one_position_per_expiry_until_reset():
    t, strategy = T, short_straddle()
    held = [sf.straddle_position(7, E2)]
    assert strategy.decide(view_at(t), sf.book(t, held), sf.context(t, SESSIONS)) == []
    later = t + timedelta(days=3)
    later = later + timedelta(days=2) if later.weekday() >= 5 else later
    # The position on E2 has closed; E2 is still at 50-60 DTE: no second position on it.
    assert 50 <= (E2 - later).days <= 60
    assert strategy.decide(view_at(later), sf.book(later), sf.context(later, SESSIONS)) == []
    strategy.reset()
    assert len(strategy.decide(view_at(later), sf.book(later), sf.context(later, SESSIONS))) == 1


def test_one_close_order_per_position_and_none_while_one_is_pending():
    t = E1 - timedelta(days=15)                        # 2023-06-01; the next session 06-02 is 14 days out
    strategy = short_straddle()
    position = sf.straddle_position(3, E1, qty=-10)
    orders = strategy.decide(view_at(t), sf.book(t, [position]), sf.context(t, SESSIONS))
    closes = [o for o in orders if o.intent == "close"]
    assert len(closes) == 1 and closes[0].exit_reason == "dte" and closes[0].packages == 10
    assert closes[0].legs == (LegIntent(sf.symbol(E1, "C", 400), 1), LegIntent(sf.symbol(E1, "P", 400), 1))
    assert [o for o in strategy.decide(view_at(t), sf.book(t, [position], pending_ids=[3]), sf.context(t, SESSIONS))
            if o.intent == "close"] == []
    early = t - timedelta(days=1)                      # next session 06-01: 15 days out
    assert [o for o in strategy.decide(view_at(early), sf.book(early, [position]), sf.context(early, SESSIONS))
            if o.intent == "close"] == []


def test_the_strategy_exit_order_follows_the_precedence_and_refuses_an_uncomputed_pnl():
    t = E1 - timedelta(days=15)
    strategy = short_straddle(exits=ExitRules(14, stop=1.0, target=0.5, signal_below=0.0))
    stopped = sf.straddle_position(3, E1, pnl=-10_000.0, premium=10_000.0)
    assert strategy.decide(view_at(t), sf.book(t, [stopped]), sf.context(t, SESSIONS, s=-1.0))[0].exit_reason == "stop"
    with pytest.raises(ValueError, match="computed"):
        strategy.decide(view_at(t), sf.book(t, [sf.straddle_position(3, E1, pnl=NAN)]), sf.context(t, SESSIONS))


def test_the_calendar_needs_the_next_monthly_listed():
    t = D(2023, 5, 12)                                 # E1 2023-06-16 at 35 DTE, the back E2 2023-07-21
    calendar = VolStrategy("straddle_calendar", "short", EntryRule(), ExitRules(14))
    order = calendar.decide(view_at(t), sf.book(t), sf.context(t, SESSIONS))[0]
    assert [(leg.osi_symbol, leg.ratio) for leg in order.legs] == [
        (sf.symbol(E1, "C", 400), -1), (sf.symbol(E1, "P", 400), -1), (sf.symbol(E2, "C", 400), 1),
        (sf.symbol(E2, "P", 400), 1)]
    calendar.reset()
    assert calendar.decide(view_at(t, expiries=(E1, E3)), sf.book(t), sf.context(t, SESSIONS)) == []


def test_the_strategy_refuses_a_run_on_another_source_and_a_side_that_is_not_its_structures():
    with pytest.raises(ValueError, match="source"):
        short_straddle().decide(view_at(T), sf.book(T), sf.context(T, SESSIONS, source="dolthub"))
    with pytest.raises(ValueError):
        VolStrategy("short_straddle", "long", EntryRule(), ExitRules(14))
    with pytest.raises(ValueError):
        VolStrategy("long_straddle", "long", EntryRule("above", 0.0), ExitRules(14))
    with pytest.raises(ValueError):
        VolStrategy("short_strangle", "short", EntryRule(), ExitRules(14, signal_above=0.4))
