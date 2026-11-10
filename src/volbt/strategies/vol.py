"""VolStrategy: milestone 4's strategy, one structure on the VRP signal (plan sections 3 and 5).

    VolStrategy(structure, side, entry, exits, sizer, rv_model, source)

At each session's step 9 it reads s_t, the log variance ratio of its own VrpSignal (ctx.signals; the engine updates
the signal through the session's view and resets it before each run), and returns:

  1. for each open position with no pending order, ONE close order (D22) when an exit holds: rules.exit_reason, in
     the order stop > profit_target > signal > dte, the DTE counted from the next session to the settlement date of
     the position's earliest open lot (strategies.expiry.dte). The order closes every open lot, at packages = the gcd
     of the lots' |qty| (as the M3 reference strategy);
  2. at most one opening order, when the session has a snapshot, fewer than `max_open` (2) positions are pending or
     open (a position with a close order pending still counts), no opening order is pending, and the entry rule
     allows s. The expiry: the standard monthly at entry_dte (50-60) days to settlement at the session (the calendar:
     the front at front_dte, 22-35, and the back = the next calendar month's standard monthly, listed, at most 180
     days out, else no entry), and not the (front) expiry of a position this run has already held: one position per
     expiry. The contracts: strategies.structures. The opening order carries s as its entry_signal (None when s is
     not a number, which only `always` enters on).

The run state (the expiries held) is cleared by reset(), which the engine calls before each run, so the same object
run twice gives the same decisions. Every read is through the session's view or ctx: a decision at t uses no data
dated after t (ADR-0001 test 6, tests/test_strategy_causal.py).

May import (volbt): pricing, signals, view (ADR-0001 §4).
"""

from __future__ import annotations

import math

from volbt.signals.vrp import VrpSignal
from volbt.strategies import expiry as expiries
from volbt.strategies import structures
from volbt.strategies.base import BookState, LegIntent, OrderIntent, SessionContext
from volbt.strategies.rules import EntryRule, ExitRules, exit_reason, finite
from volbt.strategies.sizing import FixedPackages

ENTRY_DTE = (50, 60)        # straddles and the strangle: the standard monthly at 50-60 days to settlement
FRONT_DTE = (22, 35)        # the calendar's front
MAX_OPEN = 2


class VolStrategy:
    name = "VolStrategy"

    def __init__(self, structure: str, side: str, entry: EntryRule, exits: ExitRules, sizer=None,
                 rv_model: str = "har", source: str = "optionsdx", max_open: int = MAX_OPEN,
                 strangle_delta: float = structures.STRANGLE_DELTA) -> None:
        if structure not in structures.STRUCTURES:
            raise ValueError(f"structure must be one of {structures.STRUCTURES}, not {structure!r}")
        if side != structures.SIDES[structure]:
            raise ValueError(f"{structure} is {structures.SIDES[structure]} vol, not {side!r}")
        if type(entry) is not EntryRule or type(exits) is not ExitRules:
            raise ValueError("VolStrategy takes an EntryRule and an ExitRules")
        if entry.gate == ("below" if side == "short" else "above"):
            raise ValueError(f"a {side}-vol structure enters on s {'>=' if side == 'short' else '<='} theta, "
                             f"not with gate {entry.gate!r}")
        if (exits.signal_below if side == "long" else exits.signal_above) is not None:
            raise ValueError(f"a {side}-vol structure exits when s falls to a level (short) or rises to one (long)")
        if type(max_open) is not int or max_open < 1:
            raise ValueError(f"max_open must be an int >= 1, not {max_open!r}")
        self.structure, self.side, self.entry, self.exits = structure, side, entry, exits
        self.sizer = sizer if sizer is not None else FixedPackages()
        self.max_open, self.strangle_delta = max_open, float(strangle_delta)
        self.signal = VrpSignal(rv_model, source)
        self.signals = (self.signal,)
        self.source = source
        self.reset()

    def reset(self) -> None:
        """Start a run: forget the expiries held (the engine calls this before each run)."""
        self.held: dict[int, object] = {}         # position_id -> its (front) expiry, once seen open
        self.calendar = None
        self.last_session = None

    def params(self) -> dict:
        out = {"structure": self.structure, "side": self.side, "entry": self.entry.params(),
               "exits": self.exits.params(), "sizer": self.sizer.params(), "signal": self.signal.params(),
               "max_open": self.max_open}
        if self.structure == "straddle_calendar":
            out["front_dte"] = list(FRONT_DTE)
        else:
            out["entry_dte"] = list(ENTRY_DTE)
        if self.structure == "short_strangle":
            out["delta"] = self.strangle_delta
        return out

    # --- the decision ---------------------------------------------------------------------------------------------

    def decide(self, view, book: BookState, ctx: SessionContext) -> list[OrderIntent]:
        if ctx.data_source != self.source:
            raise ValueError(f"VolStrategy reads {self.source} signals; the run's source is {ctx.data_source}")
        if ctx.sessions is not self.calendar:
            self.calendar = ctx.sessions
            self.last_session = max(ctx.sessions) if ctx.sessions else None
        value = ctx.signals.get(self.signal.name)
        s = float(value.value) if value is not None else float("nan")
        for position in book.positions:
            if position.status == "open" and position.lots and position.position_id not in self.held:
                self.held[position.position_id] = min(lot.expiry for lot in position.lots)
        orders = []
        for position in book.open_positions():
            order = self.exit_order(position, book, ctx, s)
            if order is not None:
                orders.append(order)
        if (not ctx.has_snapshot or len(book.positions) >= self.max_open
                or any(position.status == "pending" for position in book.positions) or not self.entry.allows(s)):
            return orders
        entry = self.entry_order(view, book, ctx, s)
        return orders + ([entry] if entry is not None else [])

    def settles(self, lot_expiry, ctx: SessionContext):
        settle = expiries.settle_date(lot_expiry, ctx.sessions, self.last_session)
        return settle if settle is not None else lot_expiry

    def exit_order(self, position, book: BookState, ctx: SessionContext, s: float) -> OrderIntent | None:
        lots = [lot for lot in position.lots if lot.qty != 0]
        if not lots or book.has_pending(position.position_id):
            return None
        dte_next = None
        if ctx.next_session is not None:
            dte_next = (min(self.settles(lot.expiry, ctx) for lot in lots) - ctx.next_session).days
        reason = exit_reason(self.exits, position.pnl_usd, position.premium_usd, s, dte_next)
        if reason is None:
            return None
        packages = math.gcd(*(abs(lot.qty) for lot in lots))
        legs = tuple(LegIntent(lot.osi_symbol, -lot.qty // packages) for lot in lots)
        return OrderIntent(position.position_id, "close", position.structure, legs, packages, reason)

    def entry_order(self, view, book: BookState, ctx: SessionContext, s: float) -> OrderIntent | None:
        t = ctx.session_date
        chain = structures.Chain(view, t, ctx.data_source, ctx.execution_mode == "surface")
        held = set(self.held.values())
        lo, hi = FRONT_DTE if self.structure == "straddle_calendar" else ENTRY_DTE
        window = [e for e in expiries.monthly_in_window(chain.expiries, t, lo, hi, ctx.sessions, self.last_session)
                  if e not in held]
        if not window:
            return None
        front = window[0]
        if self.structure == "straddle_calendar":
            back = expiries.next_monthly(chain.expiries, front, ctx.sessions)
            if back is None or (back - t).days > expiries.MAX_EXPIRY_DAYS \
                    or expiries.settle_date(back, ctx.sessions, self.last_session) is None:
                return None
            legs = structures.straddle_calendar(chain.symbols(front), chain.symbols(back), chain.forward(front))
        elif self.structure == "short_strangle":
            legs = structures.delta_strangle(chain.deltas(front), self.strangle_delta)
        else:
            legs = structures.atm_straddle(chain.symbols(front), chain.forward(front),
                                           -1 if self.side == "short" else 1)
        if legs is None:
            return None
        packages = self.sizer.packages(view, book, ctx, legs)
        return OrderIntent(None, "open", self.structure, legs, packages, entry_signal=s if finite(s) else None)
