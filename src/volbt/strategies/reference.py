"""The milestone-3 reference strategy: a rolling short straddle, there to run the engine end to end.

It is NOT a strategy result. M4 builds the real structures and signals; this one exists so that every
part of the daily loop (fills, settlement, marks, the hedge, early exercise) runs on real data before
then, and its runs are labelled run_purpose = "diagnostic", trial_group = "m3_engine_reference".

    Entry  when flat, sell `contracts` ATM straddles on the standard monthly expiry nearest 30 DTE
           that has at least 21 DTE (and at most 180: strategies.expiry), at the listed strike
           nearest that expiry's parity forward (a tie goes to the lower strike).
    Exit   a close order when DTE at the NEXT session will be <= exit_dte (ADR-0003 §1: it fills at
           that session's close). exit_dte = 0 means hold to expiry (ADR-0003's sweep value 0), which
           exercises settlement.
    Hedge  the engine's, at every close (ADR-0005); with hedge.mode = never the engine liquidates
           delivered shares instead.

A size of 10 sits inside ADR-0002's 7-12 straddles at the default capital.
"""

from __future__ import annotations

import math
from datetime import date

from volbt.strategies.base import BookState, LegIntent, OrderIntent, SessionContext
from volbt.strategies.expiry import MAX_EXPIRY_DAYS, nearest_monthly


def as_date(value) -> date:
    """A Timestamp or a date from a view's DataFrame, as a plain date."""
    return date(value.year, value.month, value.day)


class RollingShortStraddle:
    name = "RollingShortStraddle"

    def __init__(self, contracts: int = 10, target_dte: int = 30, min_dte: int = 21, exit_dte: int = 7,
                 max_dte: int = MAX_EXPIRY_DAYS) -> None:
        if contracts < 1 or exit_dte < 0 or not (0 <= min_dte <= target_dte <= max_dte <= MAX_EXPIRY_DAYS):
            raise ValueError("RollingShortStraddle: need contracts >= 1, exit_dte >= 0 and "
                             f"0 <= min_dte <= target_dte <= max_dte <= {MAX_EXPIRY_DAYS}")
        self.contracts, self.target_dte, self.min_dte = contracts, target_dte, min_dte
        self.exit_dte, self.max_dte = exit_dte, max_dte

    def params(self) -> dict:
        return {"contracts": self.contracts, "target_dte": self.target_dte, "min_dte": self.min_dte,
                "exit_dte": self.exit_dte, "max_dte": self.max_dte}

    def decide(self, view, book: BookState, ctx: SessionContext) -> list[OrderIntent]:
        orders = [order for order in (self.exit_order(position, book, ctx) for position in book.open_positions())
                  if order is not None]
        if book.positions or book.pending or not ctx.has_snapshot:
            return orders
        entry = self.entry_order(view, ctx)
        return orders + ([entry] if entry is not None else [])

    def exit_order(self, position, book: BookState, ctx: SessionContext) -> OrderIntent | None:
        lots = [lot for lot in position.lots if lot.qty != 0]
        if not lots or self.exit_dte == 0 or ctx.next_session is None or book.has_pending(position.position_id):
            return None
        if (min(lot.expiry for lot in lots) - ctx.next_session).days > self.exit_dte:
            return None
        packages = math.gcd(*(abs(lot.qty) for lot in lots))
        legs = tuple(LegIntent(lot.osi_symbol, -lot.qty // packages) for lot in lots)
        return OrderIntent(position.position_id, "close", position.structure, legs, packages, "dte")

    def entry_order(self, view, ctx: SessionContext) -> OrderIntent | None:
        today = view.as_of
        forwards = view.forwards(today, source=ctx.data_source)
        forwards = forwards[forwards["tau_years"] > 0]
        by_expiry = {as_date(e): float(f) for e, f in zip(forwards["expiry"], forwards["forward"])}
        expiry = nearest_monthly(list(by_expiry), today, ctx.sessions, self.target_dte, self.min_dte, self.max_dte)
        if expiry is None:
            return None
        quotes = view.quotes(today, source=ctx.data_source)
        quotes = quotes[[as_date(e) == expiry for e in quotes["expiry"]]]
        symbols = {}
        for strike, right, symbol in zip(quotes["strike"], quotes["call_put"], quotes["osi_symbol"]):
            symbols.setdefault(float(strike), {})[str(right)] = str(symbol)
        strikes = sorted(k for k, sides in symbols.items() if "C" in sides and "P" in sides)
        if not strikes:
            return None
        forward = by_expiry[expiry]
        strike = min(strikes, key=lambda k: (abs(k - forward), k))
        legs = (LegIntent(symbols[strike]["C"], -1), LegIntent(symbols[strike]["P"], -1))
        return OrderIntent(None, "open", "short_straddle", legs, self.contracts)
