"""The engine's book: cash in integer cents, SPY shares, lots, positions and orders.

    Lot        one contract held inside a position (one per leg); its quantity changes only through fills
               and expiry events. lot_ids are allocated in creation order (ADR-0001 §7), never by
               iterating a set.
    Position   a structure (here a straddle) made of lots, from its opening order to its last lot's close
    Order      a package request with its legs, created after snapshot t, resolved at a later snapshot

Book.state(t) hands a strategy a FROZEN copy (volbt.strategies.base.BookState): nothing in it is the
engine's own object, so writing to it raises and cannot move the book. Book.digest() is a SHA-256 of the
whole book, so a test can show that a strategy's decide() changed nothing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date

from volbt.strategies.base import EXIT_REASONS, BookState, LotState, PendingOrderState, PositionState

# Why a position closed. A strategy gives one of EXIT_REASONS with its close order (the engine refuses any other,
# loop.check_intent); the engine itself closes lots on expiry, an early assignment or exercise, and ruin. The union is
# every positions.exit_reason a ledger can hold; the exporter refuses any other, and the app's EXIT_REASONS
# (app/src/lib/contract.ts) is the same set (tests/test_contract.py). The order is each side's own: the app's is its
# legend's.
ENGINE_EXIT_REASONS = ("expiry", "assignment", "exercise", "ruin")
POSITION_EXIT_REASONS = EXIT_REASONS + ENGINE_EXIT_REASONS


@dataclass
class Lot:
    lot_id: int
    position_id: int
    osi_symbol: str
    expiry: date
    strike: float
    right: str                   # "C" or "P"
    qty: int                     # signed contracts open now
    opened_date: date
    settle_date: date            # the session the contract settles on (its expiry, or D16's map)
    avg_open_price: float = 0.0  # USD per share, over the contracts opened
    opened_qty: int = 0          # contracts opened in total (signed), for the average
    closed_date: date | None = None


@dataclass
class Position:
    position_id: int
    strategy_id: str
    structure: str
    created_date: date
    legs: tuple                  # ((osi_symbol, ratio), ...) of the opening order
    status: str = "pending"      # pending, open, closed, not_opened
    opened_date: date | None = None
    closed_date: date | None = None
    exit_reason: str | None = None


@dataclass
class OrderLeg:
    leg_no: int
    instrument: str              # "option" or "share"
    osi_symbol: str | None
    ratio: int                   # signed contracts (or shares) per package
    cap_volume: int | None = None
    cap_volume_date: date | None = None
    filled: int = 0              # signed contracts (or shares) filled
    cancel_reason: str | None = None


@dataclass
class Order:
    order_id: int
    position_id: int | None
    created_date: date
    target_fill_date: date | None
    intent: str
    reduce_only: bool
    structure: str | None
    packages_requested: int
    legs: list = field(default_factory=list)
    exit_reason: str | None = None
    status: str = "pending"      # pending, filled, partial, cancelled, rejected
    cancel_reason: str | None = None
    resolved_date: date | None = None
    packages_filled: int = 0


class Book:
    def __init__(self, cash_cents: int) -> None:
        self.cash_cents = int(cash_cents)
        self.shares = 0
        self.lots: dict[int, Lot] = {}
        self.positions: dict[int, Position] = {}
        self.orders: dict[int, Order] = {}
        self.ids = {"lot": 0, "position": 0, "order": 0, "fill": 0, "event": 0, "flow": 0, "risk": 0}

    def next_id(self, kind: str) -> int:
        self.ids[kind] += 1
        return self.ids[kind]

    def open_lots(self) -> list[Lot]:
        """Lots with contracts open, in lot_id order."""
        return [lot for lot in self.lots.values() if lot.qty != 0]

    def pending(self) -> list[Order]:
        return [order for order in self.orders.values() if order.status == "pending"]

    def lot_for(self, position_id: int, osi_symbol: str) -> Lot | None:
        for lot in self.lots.values():
            if lot.position_id == position_id and lot.osi_symbol == osi_symbol:
                return lot
        return None

    def position_lots(self, position_id: int) -> list[Lot]:
        return [lot for lot in self.lots.values() if lot.position_id == position_id]

    def state(self, session: date) -> BookState:
        positions = []
        for position in self.positions.values():
            if position.status not in ("pending", "open"):
                continue
            lots = tuple(LotState(lot.lot_id, lot.position_id, lot.osi_symbol, lot.expiry, lot.strike, lot.right,
                                  lot.qty) for lot in self.position_lots(position.position_id))
            positions.append(PositionState(position.position_id, position.structure, position.status,
                                           position.opened_date, lots))
        pending = tuple(PendingOrderState(o.order_id, o.position_id, o.intent, o.created_date) for o in self.pending())
        return BookState(session, self.cash_cents, self.shares, tuple(positions), pending)

    def digest(self) -> str:
        """SHA-256 of everything in the book, in id order."""
        payload = {"cash_cents": self.cash_cents, "shares": self.shares, "ids": self.ids,
                   "lots": [asdict(lot) for lot in self.lots.values()],
                   "positions": [asdict(p) for p in self.positions.values()],
                   "orders": [asdict(o) for o in self.orders.values()]}
        text = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
