"""The run ledger: one parquet file per table, written once at the end of the run.

    <runs_root>/run_id=<id>/<table>/part-0.parquet

Determinism (ADR-0001 §7, test 3). IDs are allocated in creation order; rows are sorted by the ERD key
before writing; every table has a fixed schema; files are written through volbt.data.store.write_parquet
(fixed writer settings, no pandas metadata, a .tmp then a rename). The run id is the folder name, never a
column (decision D13), and nothing here holds a clock: created_at and the stage timings go to the
unhashed run_meta.json beside the tables.

Changes against docs/architecture/specs/data_model_ledger_erd.yaml (decisions D11-D15, D24): orders gain
resolved_date and exit_reason; fills gain instrument (share liquidations), fees_cents and leg qty; lots
gain settle_date; position_marks gain qty, bid, ask, in_nav, h_model, spot, forward, tau_years and
log_moneyness; expiry_events gain dividend_amount; risk_events hold `ruin` only in M3; daily_pnl keeps
its attribution and margin columns typed and null (M5, M6); a new table cash_flows holds every cash
movement in integer cents, so cash = initial + sum(cash_flows) exactly.

Milestone 4 (plan sections 3 and 4) adds two tables and fills one column:
    signals         one row per session and signal of the strategy (step 9): the ERD columns, plus iv30_flags,
                    log_var_ratio (the signal s_t), n_window and flags (volbt.signals.base); zscore stays null
    position_daily  one row per position per session from its opening fill to its close: the hedged P&L and
                    its parts (volbt.engine.positions), cumulative, and the position's delta at the close
    positions.entry_signal   the opening intent's entry_signal (null for a strategy that gives none)
A run of a strategy with no signals writes an empty `signals` table; every M3 table keeps its bytes.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa

from volbt.data.store import file_sha256, write_parquet

D, S, I32, I64, F, B, I16 = pa.date32(), pa.string(), pa.int32(), pa.int64(), pa.float64(), pa.bool_(), pa.int16()

SCHEMAS: dict[str, pa.Schema] = {
    "runs": pa.schema([("source_commit", S), ("code_fingerprint", S), ("config_hash", S), ("config_json", S), ("data_fingerprint", S),
                       ("data_source", S), ("execution_mode", S), ("fill_timing", S), ("cap_mode", S),
                       ("chain_mask", S), ("split", S), ("run_purpose", S), ("trial_group", S), ("strategy", S),
                       ("rerun_of", S), ("rerun_reason", S), ("sample_start", D), ("sample_end", D),
                       ("last_session", D), ("status", S)]),
    "positions": pa.schema([("position_id", I64), ("strategy_id", S), ("structure", S), ("created_date", D),
                            ("opened_date", D), ("closed_date", D), ("status", S), ("entry_signal", F),
                            ("exit_reason", S)]),
    "orders": pa.schema([("order_id", I64), ("position_id", I64), ("created_date", D), ("target_fill_date", D),
                         ("resolved_date", D), ("intent", S), ("reduce_only", B), ("structure", S),
                         ("packages_requested", I32), ("packages_after_risk", I32), ("packages_filled", I32),
                         ("risk_action", S), ("status", S), ("cancel_reason", S), ("exit_reason", S)]),
    "order_legs": pa.schema([("order_id", I64), ("leg_no", I16), ("instrument", S), ("osi_symbol", S),
                             ("ratio", I32), ("cap_volume", I64), ("cap_volume_date", D), ("filled", I32),
                             ("cancel_reason", S)]),
    "fills": pa.schema([("fill_id", I64), ("order_id", I64), ("leg_no", I16), ("fill_date", D), ("instrument", S),
                        ("osi_symbol", S), ("qty", I32), ("price_cents", I64), ("price", F), ("bid", F), ("ask", F),
                        ("mid", F), ("half_spread", F), ("k_half_spread", F), ("fees_cents", I64), ("fees", F),
                        ("fill_source", S), ("cap_contracts", I32), ("cap_type", S), ("cap_volume", I64),
                        ("cap_volume_date", D), ("volume_reliable", B)]),
    "lots": pa.schema([("lot_id", I64), ("position_id", I64), ("osi_symbol", S), ("expiry", D), ("settle_date", D),
                       ("strike", F), ("option_right", S), ("qty_open", I32), ("qty_opened", I32),
                       ("avg_open_price", F), ("opened_date", D), ("closed_date", D)]),
    "position_marks": pa.schema([("session_date", D), ("lot_id", I64), ("qty", I32), ("mark_price", F),
                                 ("mark_iv", F), ("mark_source", S), ("quality_flags", I32), ("bid", F), ("ask", F),
                                 ("value_mid_usd", F), ("value_liq_usd", F), ("in_nav", B), ("h_model", F),
                                 ("spot", F), ("forward", F), ("tau_years", F), ("log_moneyness", F),
                                 ("delta_shares", F), ("gamma_1pct_usd", F), ("vega_1vol_usd", F),
                                 ("theta_1d_usd", F), ("pnl_residual_usd", F), ("mark_flags", I32)]),
    "hedges": pa.schema([("session_date", D), ("executed_date", D), ("trigger", S), ("timing", S),
                         ("delta_before_shares", F), ("shares_traded", I32), ("price", F), ("price_cents", I64),
                         ("commission", F), ("slippage", F), ("commission_cents", I64), ("slippage_cents", I64),
                         ("shares_after", I32), ("delta_after_shares", F)]),
    "expiry_events": pa.schema([("event_id", I64), ("session_date", D), ("effective_date", D), ("lot_id", I64),
                                ("osi_symbol", S), ("event_type", S), ("contracts", I32), ("shares_delivered", I32),
                                ("strike", F), ("settlement_price", F), ("dividend_ex_date", D),
                                ("dividend_amount", F), ("decision_method", S), ("decision_iv", F),
                                ("threshold_value", F), ("pin_flag", B)]),
    "risk_events": pa.schema([("event_id", I64), ("session_date", D), ("kind", S), ("greek", S), ("value", F),
                              ("limit_value", F), ("order_id", I64), ("action", S)]),
    "daily_pnl": pa.schema([("session_date", D), ("has_snapshot", B), ("spot", F), ("nav_mid", F), ("nav_liq", F),
                            ("cash", F), ("cash_cents", I64), ("shares", I32), ("share_value", F),
                            ("option_value_mid", F), ("option_value_liq", F), ("option_value_gross", F),
                            ("model_marked_value_gross", F), ("n_open_lots", I32), ("pnl_total", F),
                            ("pnl_delta", F), ("pnl_gamma", F), ("pnl_vega", F), ("pnl_theta", F), ("pnl_fees", F),
                            ("pnl_interest", F), ("pnl_dividends", F), ("pnl_borrow", F), ("pnl_residual", F),
                            ("daily_return", F), ("rf_return", F), ("rate", F), ("margin_req_gross_usd", F),
                            ("short_option_mv_usd", F), ("margin_req_net_usd", F), ("excess_liquidity_usd", F),
                            ("share_nav_model_marked", F), ("mark_quality", S), ("delta_after_hedge_shares", F)]),
    "cash_flows": pa.schema([("flow_id", I64), ("session_date", D), ("kind", S), ("amount_cents", I64),
                             ("ref_id", I64)]),
    "signals": pa.schema([("session_date", D), ("signal_name", S), ("iv30", F), ("iv30_flags", I32),
                          ("rv_forecast", F), ("rv_model", S), ("model_fit_date", D), ("vrp_spread", F),
                          ("zscore", F), ("vix_bucket", S), ("vol_regime", S), ("log_var_ratio", F),
                          ("n_window", I32), ("flags", I32)]),
    "position_daily": pa.schema([("session_date", D), ("position_id", I64), ("status", S), ("n_open_lots", I32),
                                 ("premium_usd", F), ("fills_usd", F), ("open_value_usd", F), ("settled_usd", F),
                                 ("hedge_usd", F), ("pnl_usd", F), ("delta_shares", F)]),
}
SCHEMAS["fills"] = SCHEMAS["fills"].append(pa.field("fill_flags", I32))   # SURFACE_* bits and H_MODEL_OTHER_EXPIRY

SORT_KEYS = {"runs": (), "positions": ("position_id",), "orders": ("order_id",), "order_legs": ("order_id", "leg_no"),
             "fills": ("fill_id",), "lots": ("lot_id",), "position_marks": ("session_date", "lot_id"),
             "hedges": ("session_date",), "expiry_events": ("event_id",), "risk_events": ("event_id",),
             "daily_pnl": ("session_date",), "cash_flows": ("flow_id",), "signals": ("session_date", "signal_name"),
             "position_daily": ("session_date", "position_id")}


def _clean(value):
    """NaN as a null: "not computed" reads as NULL, not as a number (the pricing build's rule)."""
    if isinstance(value, float) and value != value:
        return None
    return value


class Ledger:
    def __init__(self) -> None:
        self.rows: dict[str, list[dict]] = {name: [] for name in SCHEMAS}

    def append(self, table: str, row: dict) -> None:
        self.rows[table].append(row)

    def table(self, name: str) -> pa.Table:
        schema = SCHEMAS[name]
        rows = self.rows[name]
        keys = SORT_KEYS[name]
        if keys:
            rows = sorted(rows, key=lambda r: tuple(r[k] for k in keys))
        columns = {field.name: [_clean(r.get(field.name)) for r in rows] for field in schema}
        return pa.Table.from_pydict(columns, schema=schema)

    def write(self, run_dir: Path) -> dict[str, str]:
        """Write every table; returns {relative file: SHA-256}."""
        out = {}
        for name in SCHEMAS:
            path = Path(run_dir) / name / "part-0.parquet"
            write_parquet(self.table(name), path)
            out[f"{name}/part-0.parquet"] = file_sha256(path)
        return out
