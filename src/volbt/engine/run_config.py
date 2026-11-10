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

The split protocol in the config (milestone 4, plan section 6). A trial run whose sample ends after the
development split (2019-12-31) must name its pre-registration (`prereg_id`): every post-2019 trial is scored
against a frozen, committed file. No diagnostic may run on the holdout (ADR-0010 §1: it is run once per frozen
configuration, never to look). A trial past 2019 runs on its split's data and execution (ADR-0010 §1's protocol):
validation on OptionsDX quotes, the holdout on the DoltHub surface (TRIAL_EXECUTION; fix pass 2, review B claim 4a).
The pre-registration's own checks (a listed trial_hash, a validation record before the holdout, at most two re-runs,
an unspent window) are the run gate's (tools/prereg.py), which the tool passes in.

A diagnostic past 2019 names what it is (`diagnostic_kind`, DIAGNOSTIC_KINDS; fix pass 3, review D claim 6): one of
ADR-0010 §1's validation diagnostics (the volume cap; ADR-0009 §4's runs S, M and M') or plan section 6's smoke and
budget runs. RunConfig checks that a named kind fits the config (below); the run gate refuses a diagnostic past 2019
that names none, and records the kind.

The seed (fix pass 4, item F6b; review E claim 4): no code draws from it, and it is part of the trial_hash, so a
seed changed past 2019 would be a new trial_hash for the same runs. RunConfig refuses a seed other than 0 for every
run the run gate can accept past the development split: a trial, or a diagnostic that names its diagnostic_kind (the
gate refuses a diagnostic past 2019 that names none). A development run, and a run past 2019 that names no kind (only
a test's made-up gate passes one: ADR-0001 test 3 runs seed 7 on the made-up store's 2022-2023 sessions), may still
change it (default taken 2026-11-10, owner can override). The field stays in config_json, so the M3 config_hash stays
9700548f....
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction

from volbt.view import SPLITS as SPLIT_DATES

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
# The data source and execution mode of a trial past 2019, set by its split (ADR-0010 §1: the validation run of
# record on OptionsDX quotes, the holdout on the DoltHub surface); no other split may hold a trial past 2019.
TRIAL_EXECUTION = {"validation": ("optionsdx", "quote"), "holdout": ("dolthub", "surface")}
# The diagnostics a run past 2019 may be (fix pass 3, item D6), each with the config fields it fixes. All run on the
# validation split. volume_cap: ADR-0010 §1's capacity haircut. surface_s, masked_m, masked_m_prime: ADR-0009 §4's
# runs S, M and M' (M and M' need a masked pricing build: chain_mask "dolthub" and "dolthub_daily" are not in
# CHAIN_MASKS yet, so RunConfig refuses them). smoke and budget: plan section 6's smoke (tools/smoke_m4.py) and the
# 60-second budget runs (M3's and M4's), on the rule of record's cap and fill timing.
DIAGNOSTIC_KINDS = {
    "volume_cap": {"cap_mode": "volume"},
    "surface_s": {"data_source": "optionsdx", "execution_mode": "surface", "chain_mask": "none"},
    "masked_m": {"data_source": "optionsdx", "execution_mode": "surface", "chain_mask": "dolthub"},
    "masked_m_prime": {"data_source": "optionsdx", "execution_mode": "surface", "chain_mask": "dolthub_daily"},
    "smoke": {"cap_mode": "hard_only", "fill_timing": "next_close"},
    "budget": {"cap_mode": "hard_only", "fill_timing": "next_close"},
}


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
    # No code draws from the seed. A future random strategy must define what the seed means before it may change
    # past 2019 (fix pass 4, item F6b). It stays in config_json and the hashes, so a seed change is a new run.
    seed: int = 0
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
    prereg_id: str | None = None                              # milestone 4: a post-2019 trial's pre-registration
    diagnostic_kind: str | None = None                        # fix pass 3: which diagnostic (DIAGNOSTIC_KINDS)

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
        if self.prereg_id is not None and (type(self.prereg_id) is not str or not self.prereg_id.strip()):
            raise ValueError("RunConfig.prereg_id must be a string with a non-blank character, or None")
        if (self.run_purpose == "trial" and self.sample_end > SPLIT_DATES["development"][1]
                and self.prereg_id is None):
            raise ValueError("a trial run past the development split needs its pre-registration: prereg_id "
                             "(milestone 4, plan section 6)")
        if (self.run_purpose == "trial" and self.sample_end > SPLIT_DATES["development"][1]
                and TRIAL_EXECUTION.get(self.split) != (self.data_source, self.execution_mode)):
            raise ValueError(f"a trial past the development split runs on its split's data and execution: "
                             f"{TRIAL_EXECUTION} (ADR-0010 §1), not split {self.split!r} on "
                             f"({self.data_source!r}, {self.execution_mode!r})")
        if (self.seed != 0 and self.sample_end > SPLIT_DATES["development"][1]
                and (self.run_purpose == "trial" or self.diagnostic_kind is not None)):
            raise ValueError(f"RunConfig.seed = {self.seed!r}: no code draws from the seed, so a trial or a named "
                             "diagnostic past the development split has seed 0; a future random strategy must define "
                             "what the seed means before it may change (fix pass 4, item F6b)")
        if self.split == "holdout" and self.run_purpose == "diagnostic":
            raise ValueError("no diagnostic runs on the holdout: it is run once per frozen configuration "
                             "(ADR-0010 §1; milestone 4, plan section 6)")
        if self.diagnostic_kind is not None:
            kind = self.diagnostic_kind
            if kind not in DIAGNOSTIC_KINDS:
                raise ValueError(f"RunConfig.diagnostic_kind = {kind!r}: expected None or one of "
                                 f"{tuple(DIAGNOSTIC_KINDS)}")
            if self.run_purpose != "diagnostic" or self.split != "validation":
                raise ValueError(f"diagnostic_kind {kind!r} names a validation diagnostic: run_purpose "
                                 f"'diagnostic' and split 'validation', not {self.run_purpose!r} on {self.split!r}")
            wrong = {name: value for name, value in DIAGNOSTIC_KINDS[kind].items() if values[name] != value}
            if wrong:
                raise ValueError(f"diagnostic_kind {kind!r} needs {DIAGNOSTIC_KINDS[kind]}; this config has "
                                 f"{ {name: values[name] for name in wrong} }")


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
    """The config and the strategy as plain JSON values, every field present but a `prereg_id` or a `diagnostic_kind`
    of None (fix pass 3: so every earlier config keeps its hash), and, when
    the strategy declares signals, "signals": [{name, params}] in its order (fix pass 2, review B claim 4b: two
    strategies that differ only in a signal's parameters are two trials). A signal without params() is refused.

    A run with no pre-registration and a strategy with no signals keeps the config_hash it had before milestone 4
    added both, so every M3 trial keeps its identity (default taken 2026-11-09, owner can override)."""
    engine = {name: _canonical(value) for name, value in asdict(cfg).items()}
    for name in ("prereg_id", "diagnostic_kind"):
        if engine[name] is None:
            del engine[name]
    out = {"engine": engine, "strategy": {"name": strategy.name, "params": _canonical(strategy.params())}}
    signals = tuple(getattr(strategy, "signals", ()))
    if signals:
        for signal in signals:
            if not callable(getattr(signal, "params", None)):
                raise ValueError(f"signal {getattr(signal, 'name', signal)!r} has no params(): a signal's "
                                 "parameters define the trial")
        out["signals"] = [{"name": signal.name, "params": _canonical(signal.params())} for signal in signals]
    return out


def config_hash(cfg: RunConfig, strategy) -> str:
    text = json.dumps(config_json(cfg, strategy), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# The fields that place a run of a configuration rather than define it (milestone 4 fix pass, item 3); the data
# source and execution mode are set by the split for a trial past 2019 (TRIAL_EXECUTION; fix pass 2, item 4); the
# diagnostic_kind says why a run of it was made (fix pass 3, item D6); the trial_group is a free label, so a new
# label is not a new configuration and does not reset the run gate's count of re-runs (fix pass 4, item F6a/O1).
TRIAL_PLACEMENT = ("split", "sample_start", "sample_end", "run_purpose", "prereg_id", "data_source", "execution_mode",
                   "diagnostic_kind", "trial_group")
RUN_SOURCE = "<the run's data_source>"


def _placed(value, source: str):
    """`value` with every "source" entry equal to the run's data source replaced by RUN_SOURCE, at any depth."""
    if isinstance(value, dict):
        return {k: RUN_SOURCE if k == "source" and v == source else _placed(v, source) for k, v in value.items()}
    if isinstance(value, list):
        return [_placed(v, source) for v in value]
    return value


def trial_hash(cfg: RunConfig, strategy) -> str:
    """The configuration's hash without TRIAL_PLACEMENT: one trial's validation run and its holdout run share it, so
    the run gate can find the validation run of record of a holdout run (ADR-0010 test 4b) and count a validation
    trial's re-runs (test 8). A strategy or signal parameter named "source" that equals the run's data source is
    left out with it (VolStrategy reads its VrpSignal from the run's source; default taken 2026-11-09, owner can
    override). The run id and config_hash keep every field (decision D13; the M3 regression gate)."""
    data = config_json(cfg, strategy)
    for name in TRIAL_PLACEMENT:
        data["engine"].pop(name, None)
    for key in ("strategy", "signals"):
        if key in data:
            data[key] = _placed(data[key], cfg.data_source)
    text = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_run_id(config_hash_value: str, data_fingerprint: str, commit: str, code_fingerprint: str) -> str:
    """Decision D13: the run's id names what produced it, and nothing else (no clock, no uuid)."""
    text = (f"config_hash={config_hash_value}\ndata_fingerprint={data_fingerprint}\ncommit={commit}\n"
            f"code_fingerprint={code_fingerprint}")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
