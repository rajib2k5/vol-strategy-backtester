"""The app's two engine datasets, built from one run's ledger: blotter and positions_timeline (ADR-0001 §5).

    blotter_body(run_dir)             fills[{fill_id, date, instrument, osi_symbol, qty, price, mid,
                                      half_spread, fees, fill_source, intent}] and events[] (decision D24:
                                      without them a position closed by expiry has no closing trade)
    positions_timeline_body(run_dir)  positions[{position_id, structure, opened, closed, legs[], exit_reason}],
                                      dates[] and open_count[]

The envelope is added by tools/export_app_data.py, as in M2. Each body carries the `run`, `units` and
`illustrative: false` blocks, with ADR-0001 §7's rounding (prices 4 dp, USD 2 dp). No P&L, NAV, return or
Sharpe is written: the committed files come from the development run of a diagnostic reference strategy
(decision D19), and a reader must not take its trades for a result.

The reader checks before and after it reads (ADR-0001 amendment 4): every ledger file must have the
SHA-256 run_meta.json recorded when the run wrote it, before the read and after it, and the folder's run_id
must be the hash of the config_hash, data_fingerprint, commit and code_fingerprint the runs table names (decision
D13 as amended by the M3 review).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pyarrow.parquet as pq

from volbt.data.store import file_sha256
from volbt.engine.book import POSITION_EXIT_REASONS
from volbt.engine.run_config import make_run_id

BLOTTER_UNITS = {"qty": "contracts (options) or shares (SPY), signed: + bought, - sold", "price": "USD per share",
                 "mid": "USD per share", "half_spread": "USD per share", "fees": "USD", "strike": "USD per share",
                 "settlement_price": "USD per share", "shares_delivered": "shares, signed: + received, - delivered"}
POSITIONS_UNITS = {"open_count": "positions open at the session's close",
                   "ratio": "contracts per package, signed: + long, - short"}
PRICE_DP, USD_DP = 4, 2


class LedgerChanged(ValueError):
    """A ledger file is not the one its run wrote, or the run_id does not name its own provenance."""


def check_ledger(run_dir: Path) -> dict:
    """run_meta.json after checking every recorded file's SHA-256 and the run_id's derivation.

    A guard against accidents (a file edited, replaced or truncated after the run, a folder renamed), not against
    tampering: the hashes it checks are read from run_meta.json in the same folder, so whoever edits a table and its
    hash in run_meta.json together passes. Nothing signs the files (M3 round-2 review, finding CR-b).
    """
    run_dir = Path(run_dir)
    meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))
    for name, digest in sorted(meta["files"].items()):
        if file_sha256(run_dir / name) != digest:
            raise LedgerChanged(f"{run_dir / name} is not the file the run wrote (SHA-256 differs)")
    run = table(run_dir, "runs")[0]
    expected = make_run_id(run["config_hash"], run["data_fingerprint"], run["source_commit"], run["code_fingerprint"])
    if run_dir.name != f"run_id={expected}" or meta["run_id"] != expected:
        raise LedgerChanged(f"{run_dir.name}: the run_id is not SHA-256(config_hash, data_fingerprint, commit, "
                            "code_fingerprint) of its runs table")
    return meta


def table(run_dir: Path, name: str) -> list[dict]:
    return pq.read_table(Path(run_dir) / name / "part-0.parquet").to_pylist()


def iso(day) -> str | None:
    return None if day is None else date(day.year, day.month, day.day).isoformat()


def rounded(value, digits: int):
    return None if value is None else round(float(value), digits)


def run_block(run_dir: Path) -> dict:
    run = table(run_dir, "runs")[0]
    return {"run_id": Path(run_dir).name.removeprefix("run_id="), "config_hash": run["config_hash"],
            "data_fingerprint": run["data_fingerprint"], "engine_commit": run["source_commit"],
            "data_source": run["data_source"], "execution_mode": run["execution_mode"],
            "fill_timing": run["fill_timing"], "cap_mode": run["cap_mode"], "chain_mask": run["chain_mask"],
            "split": run["split"], "run_purpose": run["run_purpose"], "strategy": run["strategy"],
            "status": run["status"], "sample_start": iso(run["sample_start"]), "sample_end": iso(run["sample_end"])}


def label(run: dict) -> str:
    return (f"Diagnostic run of the milestone-3 reference strategy {run['strategy']} on the {run['split']} split, "
            f"{run['sample_start']} to {run['sample_end']} ({run['data_source']}, {run['execution_mode']} mode): it "
            "exercises the engine and is not a strategy result")


def blotter_body(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    meta = check_ledger(run_dir)
    intents = {o["order_id"]: o["intent"] for o in table(run_dir, "orders")}
    fills = [{"fill_id": f["fill_id"], "date": iso(f["fill_date"]), "instrument": f["instrument"],
              "osi_symbol": f["osi_symbol"], "qty": f["qty"], "price": rounded(f["price"], PRICE_DP),
              "mid": rounded(f["mid"], PRICE_DP), "half_spread": rounded(f["half_spread"], PRICE_DP),
              "fees": rounded(f["fees"], USD_DP), "fill_source": f["fill_source"], "intent": intents[f["order_id"]]}
             for f in table(run_dir, "fills")]
    events = [{"event_id": e["event_id"], "date": iso(e["session_date"]), "effective_date": iso(e["effective_date"]),
               "osi_symbol": e["osi_symbol"], "event_type": e["event_type"], "contracts": e["contracts"],
               "shares_delivered": e["shares_delivered"], "strike": rounded(e["strike"], PRICE_DP),
               "settlement_price": rounded(e["settlement_price"], PRICE_DP), "pin_flag": bool(e["pin_flag"])}
              for e in table(run_dir, "expiry_events")]
    run = run_block(run_dir)
    body = {"run": run, "units": BLOTTER_UNITS, "illustrative": False, "label": label(run), "fills": fills,
            "events": events}
    if check_ledger(run_dir) != meta:
        raise LedgerChanged(f"{run_dir}: run_meta.json changed while the blotter was read")
    return body


def positions_timeline_body(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    meta = check_ledger(run_dir)
    opening = {o["position_id"]: o["order_id"] for o in table(run_dir, "orders") if o["intent"] == "open"}
    legs_of: dict[int, list] = {}
    for leg in table(run_dir, "order_legs"):
        legs_of.setdefault(leg["order_id"], []).append({"osi_symbol": leg["osi_symbol"], "ratio": int(leg["ratio"])})
    positions = []
    for p in table(run_dir, "positions"):
        if p["opened_date"] is None:
            continue                     # its opening order never filled: no position was ever held
        if p["exit_reason"] is not None and p["exit_reason"] not in POSITION_EXIT_REASONS:
            # The app refuses any other reason (its EXIT_REASONS is the same set), so the file must never hold one.
            raise ValueError(f"position {p['position_id']}: exit_reason {p['exit_reason']!r} is not one of "
                             f"{POSITION_EXIT_REASONS}")
        legs = legs_of[opening[p["position_id"]]]
        positions.append({"position_id": p["position_id"], "structure": p["structure"], "opened": iso(p["opened_date"]),
                          "closed": iso(p["closed_date"]), "legs": legs, "exit_reason": p["exit_reason"]})
    dates = [row["session_date"] for row in table(run_dir, "daily_pnl")]
    spans = [(date.fromisoformat(p["opened"]), date.fromisoformat(p["closed"]) if p["closed"] else None)
             for p in positions]
    open_count = [sum(1 for opened, closed in spans if opened <= d and (closed is None or closed > d)) for d in dates]
    run = run_block(run_dir)
    body = {"run": run, "units": POSITIONS_UNITS, "illustrative": False, "label": label(run), "positions": positions,
            "dates": [iso(d) for d in dates], "open_count": open_count}
    if check_ledger(run_dir) != meta:
        raise LedgerChanged(f"{run_dir}: run_meta.json changed while the positions were read")
    return body
