"""The run's configuration: every ADR default in one frozen object, its hash, and the run id.

Exact types where money or a fraction is involved: k is a Fraction (ADR-0002 §2 is integer-cent
arithmetic with k = n/4), costs per share are Decimal (ADR-0002 §4), prices and fees are integer cents.

    config_hash(cfg, strategy)   SHA-256 of the canonical JSON of the config and the strategy's name and
                                 parameters: what defines a trial (ADR-0010 §2)
    make_run_id(h, fp, commit, code)  SHA-256 of (config_hash, data_fingerprint, commit, code_fingerprint),
                                 decision D13 as amended by the M3 review: the run's folder name, never a
                                 column. The code fingerprint is there because a "-dirty" commit names no code.
                                 A change of seed changes config_hash and so the folder, and leaves every
                                 ledger file but runs/ byte-identical (ADR-0001 test 3).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction

EXECUTION_MODES = ("quote", "surface")
FILL_TIMINGS = ("next_close", "same_close")
CAP_MODES = ("hard_only", "volume")
CHAIN_MASKS = ("none",)                    # ADR-0009 §4's masked runs need a masked pricing build: not in M3
SPLITS = ("development", "validation", "holdout")
RUN_PURPOSES = ("trial", "diagnostic")
HEDGE_MODES = ("time", "band", "never")
HEDGE_TIMINGS = ("same_close", "next_open")
K_VALUES = (Fraction(0), Fraction(1, 4), Fraction(1, 2), Fraction(3, 4), Fraction(1))
SOURCES = ("optionsdx", "dolthub")


@dataclass(frozen=True)
class RunConfig:
    sample_start: date
    sample_end: date
    split: str
    data_source: str = "optionsdx"
    execution_mode: str = "quote"             # ADR-0002 §7: "surface" fills and marks every lot off the surface
    fill_timing: str = "next_close"           # ADR-0002 §1; same_close is a diagnostic
    cap_mode: str = "hard_only"               # ADR-0002 §5, ADR-0010 §1
    chain_mask: str = "none"
    run_purpose: str = "diagnostic"
    trial_group: str = "m3_engine_reference"
    seed: int = 0                             # no random draw in M3; in the hash so a seed change is a new run
    initial_nav_cents: int = 100_000_000      # ADR-0007 §1: $1,000,000 in cash
    k: Fraction = Fraction(1)                 # ADR-0002 §2: the fill at mid +- k half-spreads
    fee_per_contract_cents: int = 70          # ADR-0002 §3, per contract per side
    assignment_fee_per_contract_cents: int = 0
    stock_commission_per_share: Decimal = Decimal("0.005")   # ADR-0002 §4
    stock_commission_min: Decimal = Decimal("1.00")
    stock_half_spread: Decimal = Decimal("0.005")
    participation_rate: Fraction = Fraction(1, 10)            # ADR-0002 §5
    max_contracts_per_line: int = 100
    volume_reliable_from: date = date(2021, 1, 4)
    open_min_bid_cents: int = 5                               # ADR-0002 §7
    open_max_rel_spread: Fraction = Fraction(1, 4)
    surface_half_spread_mult: Fraction = Fraction(1)          # m of ADR-0002 §7
    h_model_band: float = 0.05                                # +- log-moneyness for h_model
    hedge_mode: str = "time"                                  # ADR-0005 §2
    hedge_every_n: int = 1
    hedge_band_pct_nav: Fraction | None = None
    hedge_timing: str = "same_close"
    borrow_fee: Decimal = Decimal("0.0025")                   # ADR-0005 §1, per year on short shares
    negative_cash_spread: Decimal = Decimal("0.0050")         # ADR-0007 §2, on a negative balance
    pin_band_cents: int = 50                                  # ADR-0003 §4
    exercise_tree_steps: int = 500                            # ADR-0003 §5, ADR-0008 §8
    exercise_tol: float = 0.005
    degraded_share: Fraction = Fraction(1, 5)                 # ADR-0004: DEGRADED above 20%
    mark_jump_move: float = 0.5                               # ADR-0004: MARK_JUMP
    mark_jump_spot: float = 0.01
    mark_jump_atm_vol: float = 0.02

    def __post_init__(self) -> None:
        checks = (("execution_mode", EXECUTION_MODES), ("fill_timing", FILL_TIMINGS), ("cap_mode", CAP_MODES),
                  ("chain_mask", CHAIN_MASKS), ("split", SPLITS), ("run_purpose", RUN_PURPOSES),
                  ("hedge_mode", HEDGE_MODES), ("hedge_timing", HEDGE_TIMINGS), ("data_source", SOURCES))
        values = asdict(self)
        for name, allowed in checks:
            if values[name] not in allowed:
                raise ValueError(f"RunConfig.{name} = {values[name]!r}: expected one of {allowed}"
                                 + (" (a masked run needs a pricing build on masked chains: not built in M3)"
                                    if name == "chain_mask" else ""))
        if type(self.sample_start) is not date or type(self.sample_end) is not date or self.sample_end < self.sample_start:
            raise ValueError("RunConfig: sample_start and sample_end must be plain dates, start <= end")
        if self.k not in K_VALUES or not isinstance(self.k, Fraction):
            raise ValueError(f"RunConfig.k must be one of {[str(k) for k in K_VALUES]} as a Fraction")
        if self.hedge_mode == "band" and self.hedge_band_pct_nav is None:
            raise ValueError("hedge_mode 'band' needs hedge_band_pct_nav")
        if self.hedge_mode == "time" and self.hedge_every_n < 1:
            raise ValueError("hedge_every_n must be at least 1")
        # ADR-0010 test 9: the volume cap is a validation diagnostic from 2021-01-04, never a rule of record.
        if self.cap_mode == "volume" and (self.run_purpose != "diagnostic" or self.split != "validation"
                                          or self.sample_start < self.volume_reliable_from
                                          or self.data_source != "optionsdx"):
            raise ValueError("cap_mode 'volume' is a diagnostic: run_purpose 'diagnostic', split 'validation', "
                             "OptionsDX, from 2021-01-04 (ADR-0010 §1, test 9)")


def _canonical(value):
    if isinstance(value, Fraction):
        return f"{value.numerator}/{value.denominator}"
    if isinstance(value, (Decimal, date)):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    return value


def config_json(cfg: RunConfig, strategy) -> dict:
    """The config and the strategy as plain JSON values, every field present."""
    return {"engine": {name: _canonical(value) for name, value in asdict(cfg).items()},
            "strategy": {"name": strategy.name, "params": _canonical(strategy.params())}}


def config_hash(cfg: RunConfig, strategy) -> str:
    text = json.dumps(config_json(cfg, strategy), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_run_id(config_hash_value: str, data_fingerprint: str, commit: str, code_fingerprint: str) -> str:
    """Decision D13: the run's id names what produced it, and nothing else (no clock, no uuid)."""
    text = (f"config_hash={config_hash_value}\ndata_fingerprint={data_fingerprint}\ncommit={commit}\n"
            f"code_fingerprint={code_fingerprint}")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
