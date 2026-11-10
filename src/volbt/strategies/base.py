"""What a strategy sees and what it returns (milestone 3).

A strategy is called once per session, at step 9 of the daily loop (ADR-0001 §1), with three things:

    view   the MarketView for that session (volbt.view): every market read, bounded by as_of
    book   a BookState: a FROZEN copy of the engine's book at the close (cash, shares, positions, lots,
           pending orders). Writing to it raises: a strategy cannot move the engine's state.
    ctx    a SessionContext: the session, the next session on the exchange calendar, the whole calendar (dates
           only, decision D3), and the run's mode

and it returns a list of OrderIntent. The engine checks each intent, turns it into an order with its
own ids, and fills it at the next snapshot (ADR-0002 §1). An intent is a request, not a trade: the fill
model decides what, if anything, fills.

Every class here is a frozen dataclass of plain values (dates, strings, ints, tuples), so a BookState can
be handed to strategy code without handing over anything the engine still uses.

May import (volbt): pricing, signals, view (ADR-0001 §4); the import test applies the allow-list.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

INTENTS = ("open", "close", "reduce_risk", "margin_liquidation")
REDUCE_ONLY_INTENTS = ("close", "reduce_risk", "margin_liquidation")
EXIT_REASONS = ("profit_target", "stop", "dte", "signal", "risk", "margin")    # a strategy's: the engine refuses others


@dataclass(frozen=True)
class LegIntent:
    """One leg of a package: a contract and its signed contracts per package (+ buy, - sell)."""

    osi_symbol: str
    ratio: int


@dataclass(frozen=True)
class OrderIntent:
    """A package order: `packages` times each leg's ratio.

    position_id None opens a new position (intent "open"); a reduce-only intent names the position whose
    lots it reduces and says why (exit_reason, one of EXIT_REASONS).
    """

    position_id: int | None
    intent: str
    structure: str
    legs: tuple[LegIntent, ...]
    packages: int
    exit_reason: str | None = None


@dataclass(frozen=True)
class LotState:
    lot_id: int
    position_id: int
    osi_symbol: str
    expiry: date
    strike: float
    right: str          # "C" or "P"
    qty: int            # signed contracts: + long, - short


@dataclass(frozen=True)
class PositionState:
    position_id: int
    structure: str
    status: str         # "pending" (its opening order has not filled yet), "open" or "closed"
    opened_date: date | None
    lots: tuple[LotState, ...]


@dataclass(frozen=True)
class PendingOrderState:
    order_id: int
    position_id: int | None
    intent: str
    created_date: date


@dataclass(frozen=True)
class BookState:
    """The book at the close of `session_date`, after fills, settlement, marks and the hedge."""

    session_date: date
    cash_cents: int
    shares: int
    positions: tuple[PositionState, ...]      # pending and open positions, by position_id
    pending: tuple[PendingOrderState, ...]    # orders not yet filled or cancelled, by order_id

    def open_positions(self) -> tuple[PositionState, ...]:
        return tuple(p for p in self.positions if p.status == "open")

    def has_pending(self, position_id: int | None) -> bool:
        return any(o.position_id == position_id for o in self.pending)


@dataclass(frozen=True)
class SessionContext:
    session_date: date
    next_session: date | None     # the next session on the exchange calendar (decision D3), None after the last
    has_snapshot: bool            # whether this session has an option snapshot
    data_source: str
    execution_mode: str
    sessions: frozenset           # every session on the exchange calendar, future ones included (D3): dates only


class Strategy(Protocol):
    """The interface the engine calls. `name` and `params()` go into the run's config_hash."""

    name: str

    def params(self) -> dict[str, Any]: ...

    def decide(self, view: Any, book: BookState, ctx: SessionContext) -> list[OrderIntent]: ...
