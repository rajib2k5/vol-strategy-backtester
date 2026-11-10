"""Print the numbers the milestone-3 walkthrough quotes, one labelled block each, from engine run ledgers.

Run:  uv run python tools/report_m3.py [--dev RUN_DIR] [--run RUN_DIR ...]

--dev is the development run (default: the one tools/run_backtest.py --for-app recorded); each --run is any other
run (the 2010-2023 budget run, the DoltHub surface run). The split protocol (decision D19): for a run whose sample
ends after 2019-12-31 this prints HEALTH metrics only, never a P&L, a NAV level, a return or a Sharpe ratio. The
development run's trace of one 2015 position prints its trades and marks, which are development-split data.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

from volbt import config
from volbt.engine.settlement import NON_SESSION_EXPIRIES

LAST_DEVELOPMENT_DAY = date(2019, 12, 31)


def table(run_dir: Path, name: str):
    return pq.read_table(run_dir / name / "part-0.parquet").to_pandas()


def block(title: str) -> None:
    print(f"\n== {title} ==")


def health(run_dir: Path) -> None:
    run = table(run_dir, "runs").iloc[0]
    meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))
    daily, marks, fills = table(run_dir, "daily_pnl"), table(run_dir, "position_marks"), table(run_dir, "fills")
    orders, events, flows = table(run_dir, "orders"), table(run_dir, "expiry_events"), table(run_dir, "cash_flows")
    hedges = table(run_dir, "hedges")
    block(f"health: {run.data_source} {run.execution_mode} {run.split} {run.sample_start} to {run.sample_end}")
    print(f"run_id {run_dir.name.removeprefix('run_id=')}  status {run.status}  sessions {len(daily)}  "
          f"snapshot sessions {int(daily.has_snapshot.sum())}")
    print(f"timings {json.dumps(meta['timings'], sort_keys=True)}  counters {json.dumps(meta['counters'], sort_keys=True)}")
    by_day = flows.groupby("session_date").amount_cents.sum().reindex(daily.session_date, fill_value=0)
    reconciles = bool((daily.cash_cents.to_numpy() == 100_000_000 + by_day.cumsum().to_numpy()).all())
    in_nav = marks[marks.in_nav]
    values = in_nav.groupby("session_date").value_mid_usd.sum().reindex(daily.session_date, fill_value=0.0).to_numpy()
    identity = np.abs(daily.nav_mid.to_numpy() - (daily.cash_cents.to_numpy() / 100 + daily.shares.to_numpy()
                                                   * daily.spot.to_numpy() + values)).max()
    print(f"cash = initial + sum(cash_flows) exactly, every session: {reconciles}; NAV identity max error {identity:.2e} USD")
    print(f"marks per open lot per session: duplicates {int(in_nav.duplicated(['session_date', 'lot_id']).sum())}")
    shares = in_nav.mark_source.value_counts(normalize=True)
    print("mark sources (share of in-NAV marks): " + ", ".join(f"{k} {v:.4f}" for k, v in shares.items()))
    flagged = {name: int(((in_nav.mark_flags & bit) > 0).sum()) for name, bit in
               (("SURFACE_EXTRAP_STRIKE", 1), ("SURFACE_CROSS_EXPIRY", 2), ("SURFACE_EXTRAP_TENOR", 4),
                ("SURFACE_CALENDAR_ADJUSTED", 8), ("IV_FAIL", 16), ("MARK_JUMP", 32), ("GREEKS_OTM_IV", 64),
                ("FORWARD_CARRY", 128))}
    print(f"mark flags (in-NAV marks with the bit): {json.dumps(flagged)}")
    degraded = daily[daily.mark_quality == "DEGRADED"]
    years = degraded.session_date.map(lambda d: d.year).value_counts().sort_index()
    print(f"DEGRADED days {len(degraded)} of {len(daily)}; by year {dict(years.items())}")
    print("orders: " + ", ".join(f"{i}/{s}/{c}: {n}" for (i, s, c), n in
                                 orders.fillna({"cancel_reason": "-"}).groupby(["intent", "status", "cancel_reason"]).size().items()))
    options = fills[fills.instrument == "option"]
    quoted = options[options.fill_source == "quote"]
    at_side = (np.where(quoted.qty > 0, quoted.price == quoted.ask, quoted.price == quoted.bid)).mean() if len(quoted) else float("nan")
    print(f"option fills {len(options)} (quote {len(quoted)}, surface {int((options.fill_source == 'surface').sum())}); "
          f"share fills {int((fills.instrument == 'share').sum())}; quote fills at the far side (k = 1) {at_side:.4f}; "
          f"cap_volume_date < fill_date on all {bool((options.cap_volume_date < options.fill_date).all())}")
    print(f"hedge rows {len(hedges)}, shares traded {int(hedges.shares_traded.abs().sum())}, "
          f"max |delta after| {hedges.delta_after_shares.abs().max():.4f} shares")
    for _, e in events.iterrows():
        print(f"event {e.event_type} {e.osi_symbol} decided {e.session_date} effective {e.effective_date} "
              f"contracts {e.contracts} shares {e.shares_delivered} method {e.decision_method} "
              f"iv {e.decision_iv if e.decision_iv == e.decision_iv else None} threshold "
              f"{e.threshold_value if e.threshold_value == e.threshold_value else None} pin {e.pin_flag}")
    if run.sample_end > LAST_DEVELOPMENT_DAY:
        print("P&L, NAV levels and returns: not printed (decision D19: this run's sample ends after 2019)")


def trace(run_dir: Path) -> None:
    """One 2015 position from order to close: the development run's walkthrough example."""
    run = table(run_dir, "runs").iloc[0]
    if run.split != "development":
        return
    positions, orders, fills = table(run_dir, "positions"), table(run_dir, "orders"), table(run_dir, "fills")
    marks, lots, hedges = table(run_dir, "position_marks"), table(run_dir, "lots"), table(run_dir, "hedges")
    chosen = positions[positions.opened_date.map(lambda d: d is not None and d.year == 2015 and d.month == 3)].iloc[0]
    block(f"trace: position {chosen.position_id} ({chosen.structure}), opened {chosen.opened_date}, closed "
          f"{chosen.closed_date}, exit {chosen.exit_reason}")
    for _, o in orders[orders.position_id == chosen.position_id].iterrows():
        print(f"order {o.order_id} {o.intent} created {o.created_date} target {o.target_fill_date} resolved "
              f"{o.resolved_date} status {o.status} packages {o.packages_filled}/{o.packages_requested}")
        for _, f in fills[fills.order_id == o.order_id].iterrows():
            print(f"  fill {f.fill_id} {f.fill_date} {f.osi_symbol.strip()} qty {f.qty} price {f.price:.2f} bid "
                  f"{f.bid:.2f} ask {f.ask:.2f} fees {f.fees:.2f} cap {f.cap_contracts} {f.cap_type} "
                  f"(V_t {f.cap_volume}, {f.cap_volume_date})")
    ids = lots[lots.position_id == chosen.position_id].lot_id.tolist()
    rows = marks[marks.lot_id.isin(ids)].sort_values(["session_date", "lot_id"])
    days = sorted(rows.session_date.unique())
    for day in [days[0], days[1], days[len(days) // 2], days[-1]]:
        for _, m in rows[rows.session_date == day].iterrows():
            print(f"  mark {day} lot {m.lot_id} {m.mark_source} {m.mark_price:.3f} iv {m.mark_iv:.4f} delta "
                  f"{m.delta_shares:.1f} sh, vega {m.vega_1vol_usd:.0f} USD/vol pt, flags {m.mark_flags}")
        h = hedges[hedges.session_date == day]
        if len(h):
            print(f"  hedge {day}: delta before {h.delta_before_shares.iloc[0]:.2f}, traded {h.shares_traded.iloc[0]}, "
                  f"after {h.delta_after_shares.iloc[0]:.2f}; cost {h.commission.iloc[0] + h.slippage.iloc[0]:.2f}")
    print(f"marked on {len(days)} sessions, sources {dict(rows.mark_source.value_counts().items())}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dev", type=Path, default=None)
    parser.add_argument("--run", type=Path, action="append", default=[])
    args = parser.parse_args(argv)
    dev = args.dev
    if dev is None:
        pointer = config.work_dir() / "runs" / "app_run.json"
        dev = Path(json.loads(pointer.read_text(encoding="utf-8"))["run_dir"]) if pointer.is_file() else None
    block("non-session expiries mapped (decision D16)")
    for expiry, settle in sorted(NON_SESSION_EXPIRIES.items()):
        print(f"{expiry} -> settles at the {settle} close")
    for run_dir in ([dev] if dev else []) + args.run:
        health(run_dir)
    if dev:
        trace(dev)
    return 0


if __name__ == "__main__":
    sys.exit(main())
