"""Entry and exit rules of milestone 4 (plan section 5).

Entries (EntryRule), on the VRP signal s_t = ln(IV30^2 / RV^2) of ctx.signals:
    always   enters whatever s is (NaN included)
    above    short vol: enters when s >= theta (theta in {0, 0.4})
    below    long vol: enters when s <= theta (theta = 0)
A gated entry needs a finite s: a NaN s (no IV30, no forecast) never enters.

Exits (ExitRules, exit_reason), checked at each session's decision for every open position, the FIRST that holds in
this order (PRECEDENCE: stop > profit_target > signal > dte):
    stop            pnl <= -stop * |premium|      (stop = 1.0)
    profit_target   pnl >= +target * |premium|    (target = 0.5)
    signal          short vol: s <= signal_below (theta - 0.4); long vol: s >= signal_above (+0.4). A NaN s holds:
                    the other exits still apply
    dte             DTE at the NEXT session <= exit_dte (14), counted to the settlement date of the position's
                    earliest open lot (strategies.expiry.dte): the close order fills at that session (ADR-0003 §1)
pnl and premium are the engine's (PositionState.pnl_usd, the HEDGED position P&L, and premium_usd, credit > 0); a
debit structure (long straddle, calendar) compares with |premium| the same way. With a premium of 0 both the stop and
the target hold at a pnl of 0 and the stop wins (the precedence). pnl_usd is NaN unless the engine computes it
(volbt.engine.positions.computed: the daily hedge at the close, or no hedge): a rule with a stop or a target refuses
such a pnl (ValueError) rather than never stopping. The signal level is a level, not a cross: a gated entry is on the
other side of it (s >= theta > theta - 0.4; s <= 0 < 0.4), so reaching it is the plan's crossing. Default taken
2026-11-09, owner can override.

May import (volbt): pricing, signals, view (ADR-0001 §4).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

GATES = ("always", "above", "below")
PRECEDENCE = ("stop", "profit_target", "signal", "dte")
EXIT_DTE = 14           # ADR-0003 §1 as amended in M4 (plan section 5)
STOP = 1.0              # pnl <= -1.0 |premium|
TARGET = 0.5            # pnl >= +0.5 |premium|
SIGNAL_BAND = 0.4       # the signal exit sits 0.4 beyond the entry threshold


def finite(value) -> bool:
    return value is not None and isinstance(value, (int, float)) and math.isfinite(value)


@dataclass(frozen=True)
class EntryRule:
    gate: str = "always"
    theta: float | None = None

    def __post_init__(self) -> None:
        if self.gate not in GATES:
            raise ValueError(f"EntryRule.gate must be one of {GATES}, not {self.gate!r}")
        if (self.gate == "always") != (self.theta is None) or (self.theta is not None and not finite(self.theta)):
            raise ValueError("EntryRule: 'always' takes no theta; 'above' and 'below' take a finite theta")

    def allows(self, s: float) -> bool:
        if self.gate == "always":
            return True
        if not finite(s):
            return False
        return s >= self.theta if self.gate == "above" else s <= self.theta

    def params(self) -> dict:
        return {"gate": self.gate, "theta": self.theta}


@dataclass(frozen=True)
class ExitRules:
    exit_dte: int = EXIT_DTE
    stop: float | None = None
    target: float | None = None
    signal_below: float | None = None
    signal_above: float | None = None

    def __post_init__(self) -> None:
        if type(self.exit_dte) is not int or self.exit_dte < 0:
            raise ValueError(f"ExitRules.exit_dte must be an int >= 0, not {self.exit_dte!r}")
        for name, value in (("stop", self.stop), ("target", self.target)):
            if value is not None and not (finite(value) and value > 0):
                raise ValueError(f"ExitRules.{name} must be None or a number > 0, not {value!r}")
        if self.signal_below is not None and self.signal_above is not None:
            raise ValueError("ExitRules: a signal exit is below (short vol) or above (long vol), not both")
        for value in (self.signal_below, self.signal_above):
            if value is not None and not finite(value):
                raise ValueError(f"ExitRules: a signal level must be a finite number, not {value!r}")

    @property
    def needs_pnl(self) -> bool:
        return self.stop is not None or self.target is not None

    def params(self) -> dict:
        return {"exit_dte": self.exit_dte, "stop": self.stop, "target": self.target,
                "signal_below": self.signal_below, "signal_above": self.signal_above}


def exit_reason(rules: ExitRules, pnl_usd: float | None, premium_usd: float | None, s: float,
                dte_next: int | None) -> str | None:
    """The exit that holds for one open position, by PRECEDENCE, or None (module docstring).

    dte_next: days from the next session to the settlement date of the position's earliest open lot (None: no next
    session, or no lot; then no DTE exit)."""
    if rules.needs_pnl:
        if not finite(pnl_usd) or not finite(premium_usd):
            raise ValueError("a stop or a profit target needs the engine's position P&L, and it is not a number here "
                             f"(pnl_usd {pnl_usd!r}, premium_usd {premium_usd!r}): the run's hedge must be daily at "
                             "the close or 'never' (volbt.engine.positions.computed)")
        size = abs(premium_usd)
        if rules.stop is not None and pnl_usd <= -rules.stop * size:
            return "stop"
        if rules.target is not None and pnl_usd >= rules.target * size:
            return "profit_target"
    if finite(s):
        if rules.signal_below is not None and s <= rules.signal_below:
            return "signal"
        if rules.signal_above is not None and s >= rules.signal_above:
            return "signal"
    if dte_next is not None and dte_next <= rules.exit_dte:
        return "dte"
    return None
