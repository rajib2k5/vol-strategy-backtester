"""Tests written after the milestone-3 round-3 review: each one fails on the code that review found broken.

    an intent is read once at intake: a legs object that answers differently on later reads is booked as it was
        checked, or refused (it passed the checks with front-month legs and booked a 181-DTE straddle), and only an
        OrderIntent itself is taken
    an opening order carries no exit_reason (an open with "ruin" was booked with it)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace

import pytest

import engine_helpers as eh
import engine_store as es
from volbt.engine.loop import EngineError
from volbt.strategies.base import LegIntent, OrderIntent

D = date
FAR = D(2023, 7, 3)        # 181 days after 2023-01-03; after the fixture's last bar (2023-06-30)
FRONT = es.MONTHLIES[0]    # 2023-02-17


@pytest.fixture(scope="module")
def far_store(tmp_path_factory):
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(es, "EXPIRIES", sorted(es.EXPIRIES + [FAR]))
        return es.built_store(tmp_path_factory.mktemp("far_store_r3"))


def straddle(expiry: date) -> tuple[LegIntent, ...]:
    return LegIntent(es.symbol(expiry, "C", 400.0), -1), LegIntent(es.symbol(expiry, "P", 400.0), -1)


class Flip:
    """The reviewer's legs object (p3_flip.py): `first` on its first `reads` iterations, `later` after them."""

    def __init__(self, first, later, reads: int = 5) -> None:
        self.first, self.later, self.reads, self.n = first, later, reads, 0

    def __iter__(self):
        self.n += 1
        return iter(self.first if self.n <= self.reads else self.later)

    def __len__(self) -> int:
        return 2

    def __bool__(self) -> bool:
        return True


def flip_open(first, later, reads: int = 5):
    def action(view, book, ctx):
        return [OrderIntent(None, "open", "short_straddle", Flip(first, later, reads), 10)]
    return action


def test_a_legs_object_that_changes_between_reads_is_booked_as_checked(far_store, tmp_path):
    """Front-month legs on the first read, 181-DTE legs after it: the engine books the front month."""
    result = eh.run(far_store, tmp_path / "near_first", eh.Scripted({D(2023, 1, 3): flip_open(straddle(FRONT), straddle(FAR))}),
                    sample_end=D(2023, 1, 10))
    assert result.status == "ok"
    assert set(eh.table(result, "lots")["expiry"]) == {FRONT}
    legs = eh.table(result, "order_legs")
    assert set(legs["osi_symbol"]) == {leg.osi_symbol for leg in straddle(FRONT)}
    # the other way round, a single read already names the 181-DTE legs, and the 180-day check refuses them
    with pytest.raises(EngineError, match="more than 180 days"):
        eh.run(far_store, tmp_path / "far_first", eh.Scripted({D(2023, 1, 3): flip_open(straddle(FAR), straddle(FRONT), 1)}),
               sample_end=D(2023, 1, 10))


@dataclass(frozen=True)
class LookAlike(OrderIntent):
    """A subclass could turn any field into a property that answers differently on each read."""


def test_only_an_order_intent_itself_is_taken(engine_store, tmp_path):
    fields = (None, "open", "short_straddle", straddle(FRONT), 10)
    for tag, made in (("subclass", LookAlike(*fields)),
                      ("namespace", SimpleNamespace(position_id=None, intent="open", structure="short_straddle",
                                                    legs=straddle(FRONT), packages=10, exit_reason=None))):
        strategy = eh.Scripted({D(2023, 1, 3): lambda view, book, ctx, made=made: [made]})
        with pytest.raises(EngineError, match="OrderIntent objects"):
            eh.run(engine_store, tmp_path / tag, strategy, sample_end=D(2023, 1, 10))
    plain = eh.Scripted({D(2023, 1, 3): lambda view, book, ctx: [OrderIntent(*fields)]})
    assert eh.run(engine_store, tmp_path / "plain", plain, sample_end=D(2023, 1, 10)).status == "ok"


def test_an_opening_order_with_an_exit_reason_is_refused(engine_store, tmp_path):
    """The reviewer's p3_cap.py: OrderIntent(None, "open", ..., "ruin") was booked with exit_reason "ruin"."""
    for reason in ("ruin", "dte"):          # the engine's own; a strategy's
        strategy = eh.Scripted({D(2023, 1, 3): lambda view, book, ctx, reason=reason:
                                [OrderIntent(None, "open", "short_straddle", straddle(FRONT), 10, reason)]})
        with pytest.raises(EngineError, match="opening order has no exit_reason"):
            eh.run(engine_store, tmp_path / reason, strategy, sample_end=D(2023, 1, 10))
