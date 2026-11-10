"""Milestone 4's development grid (plan section 5): 36 configurations, each one trial.

    m4_grid(rv_model) -> [GridEntry(label, strategy, engine)], 36 entries for rv_model "har" or "naive"

Each short-vol structure (short_straddle, short_strangle, straddle_calendar) gives 10:
    always x {dte, dte + pt/sl}                                                         2
    s >= theta, theta in {0, 0.4}, x {dte, dte + signal, dte + pt/sl, dte + both}       8
and the long straddle 6:
    always x {dte, dte + pt/sl}                                                         2
    s <= 0 x {dte, dte + signal, dte + pt/sl, dte + both}                               4
dte: exit_dte 14; pt/sl: the profit target at +0.5 |premium| and the stop at -1.0 |premium|; signal: the exit at
theta - 0.4 (short vol) or +0.4 (long). Fixed, not tuned: FixedPackages(10), the 50-60 DTE entry window (22-35 for the
calendar's front), at most 2 positions open, one per expiry.

`engine` holds the RunConfig fields the grid fixes (strategies may not import the engine, so they are plain values;
the tool that runs the grid builds RunConfig(sample_start, sample_end, split, **engine)): trial_group "m4_vol",
run_purpose "trial", OptionsDX in quote mode, fills at the next close, the hard cap only, and the daily hedge at the
close (hedge_mode "time", every 1 session, timing "same_close"), under which the engine computes each position's
hedged P&L (volbt.engine.positions.computed), as the stop and the target need. k stays RunConfig's default, 1.

Both rv_models are built: the forecast test (docs/validation/prereg) chooses one before the grid runs (part B2).

May import (volbt): pricing, signals, view (ADR-0001 §4).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from volbt.strategies.rules import EXIT_DTE, SIGNAL_BAND, STOP, TARGET, EntryRule, ExitRules
from volbt.strategies.sizing import FixedPackages
from volbt.strategies.vol import VolStrategy

TRIAL_GROUP = "m4_vol"
THETAS = (0.0, 0.4)          # the short-vol entry thresholds
LONG_THETA = 0.0             # the long straddle enters at s <= 0
LONG_EXIT = 0.4              # and exits on the signal at s >= +0.4
SHORT_STRUCTURES = ("short_straddle", "short_strangle", "straddle_calendar")
ENGINE = {"trial_group": TRIAL_GROUP, "run_purpose": "trial", "data_source": "optionsdx", "execution_mode": "quote",
          "fill_timing": "next_close", "cap_mode": "hard_only", "hedge_mode": "time", "hedge_every_n": 1,
          "hedge_timing": "same_close"}


@dataclass(frozen=True)
class GridEntry:
    label: str
    strategy: VolStrategy
    engine: dict = field(default_factory=dict)


def exits(signal_below: float | None = None, signal_above: float | None = None, pt_sl: bool = False) -> ExitRules:
    return ExitRules(EXIT_DTE, STOP if pt_sl else None, TARGET if pt_sl else None, signal_below, signal_above)


def exit_name(signal: bool, pt_sl: bool) -> str:
    return "dte" + ("+signal" if signal else "") + ("+pt_sl" if pt_sl else "")


def m4_grid(rv_model: str) -> list[GridEntry]:
    """The 36 development configurations for one RV model (module docstring), in a fixed order."""
    out = []

    def add(structure: str, side: str, entry: EntryRule, rules: ExitRules, name: str) -> None:
        strategy = VolStrategy(structure, side, entry, rules, FixedPackages(), rv_model, ENGINE["data_source"])
        out.append(GridEntry(f"{structure}/{name}", strategy, dict(ENGINE)))

    for structure in SHORT_STRUCTURES:
        for pt_sl in (False, True):
            add(structure, "short", EntryRule(), exits(pt_sl=pt_sl), "always/" + exit_name(False, pt_sl))
        for theta in THETAS:
            for signal, pt_sl in ((False, False), (True, False), (False, True), (True, True)):
                rules = exits(signal_below=theta - SIGNAL_BAND if signal else None, pt_sl=pt_sl)
                add(structure, "short", EntryRule("above", theta), rules, f"above_{theta}/" + exit_name(signal, pt_sl))
    for pt_sl in (False, True):
        add("long_straddle", "long", EntryRule(), exits(pt_sl=pt_sl), "always/" + exit_name(False, pt_sl))
    for signal, pt_sl in ((False, False), (True, False), (False, True), (True, True)):
        rules = exits(signal_above=LONG_EXIT if signal else None, pt_sl=pt_sl)
        add("long_straddle", "long", EntryRule("below", LONG_THETA), rules, f"below_{LONG_THETA}/" +
            exit_name(signal, pt_sl))
    return out
