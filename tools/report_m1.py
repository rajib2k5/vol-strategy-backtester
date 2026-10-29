"""Print the milestone-1 numbers that docs/milestones/01-data-layer.md quotes, from the built store.

Run:  uv run python tools/build_data.py      (once: builds data/store/)
      uv run python tools/report_m1.py

Each block is labelled with the section of the milestone doc that cites it. Nothing here
computes a new rule: it only counts what the build wrote.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from volbt import config
from volbt.data import flags
from volbt.data.store import Store


def main() -> None:
    store = Store()
    query = store.query
    summary = json.loads((store.root / "build_summary.json").read_text(encoding="utf-8"))

    print("== rows per source")
    print(query("SELECT source, count(*) AS n, count(DISTINCT quote_date) AS dates FROM option_quotes "
                "GROUP BY 1 ORDER BY 1").to_string(index=False))

    print("\n== guess 1: share of the 2010-2012 OptionsDX chain that survives a filter")
    early = query("""SELECT count(*) AS n,
                     sum(CASE WHEN quality_flags & 4 <> 0 THEN 1 ELSE 0 END) AS zero_bid,
                     sum(CASE WHEN quality_flags & 15 <> 0 THEN 1 ELSE 0 END) AS no_mid
                     FROM option_quotes WHERE source = 'optionsdx' AND year IN ('2010', '2011', '2012')""")
    n, zero_bid, no_mid = (int(early[c].iloc[0]) for c in ("n", "zero_bid", "no_mid"))
    print(f"rows {n:,}; ZERO_BID {zero_bid:,}; survive a zero-bid filter {1 - zero_bid / n:.2%}; "
          f"survive dropping any of BID_NULL/ASK_NULL/ZERO_BID/CROSSED {1 - no_mid / n:.2%}")

    print("\n== flag totals per source (rows carrying each bit)")
    counts = query("SELECT * FROM quality_flag_counts ORDER BY source, year")
    totals = counts.drop(columns="year").groupby("source").sum()
    print(totals.T.to_string())
    print("\n== worst source-year share per gated flag")
    for name in ("BID_NULL", "ASK_NULL", "CROSSED", "VENDOR_IV_INVALID", "UNDERLYING_MISMATCH"):
        for source, part in counts.groupby("source"):
            share = part[name] / part["rows"]
            print(f"{source:9s} {name:20s} {share.max():.2%} ({int(part.loc[share.idxmax(), 'year'])})")

    print("\n== snapshot dates per source and year (the gate's coverage inputs)")
    dates = query("SELECT source, year(quote_date) AS year, count(*) AS dates, min(rows) AS fewest_rows "
                  "FROM quality_rows_per_date GROUP BY 1, 2 ORDER BY 1, 2")
    print(dates.to_string(index=False))
    print(query("SELECT source, count(*) AS dates FROM quality_rows_per_date GROUP BY 1 ORDER BY 1").to_string(index=False))

    print("\n== vendor IV: what VENDOR_IV_INVALID counts (null or <= 0), and IV above 5 (not flagged)")
    print(query("""SELECT source, count(*) AS n,
                   sum(CASE WHEN vendor_iv IS NULL THEN 1 ELSE 0 END) AS iv_null,
                   sum(CASE WHEN vendor_iv = 0 THEN 1 ELSE 0 END) AS iv_zero,
                   sum(CASE WHEN vendor_iv < 0 THEN 1 ELSE 0 END) AS iv_negative,
                   min(vendor_iv) AS iv_min,
                   max(CASE WHEN vendor_iv < 0 THEN vendor_iv END) AS iv_negative_max,
                   sum(CASE WHEN vendor_iv = 0 AND bid = 0 AND ask = 0 THEN 1 ELSE 0 END) AS iv_zero_bid_ask_zero,
                   sum(CASE WHEN vendor_iv > 5 THEN 1 ELSE 0 END) AS iv_above_5,
                   max(vendor_iv) AS iv_max
                   FROM option_quotes GROUP BY 1 ORDER BY 1""").to_string(index=False))
    print("tiny positive vendor IVs, not flagged (M2 recomputes IV from quotes):")
    print(query("""SELECT source,
                   sum(CASE WHEN vendor_iv > 0 AND vendor_iv <= 0.0005 THEN 1 ELSE 0 END) AS iv_above_0_to_0005,
                   sum(CASE WHEN vendor_iv > 0 AND vendor_iv < 0.01 THEN 1 ELSE 0 END) AS iv_above_0_below_001,
                   sum(CASE WHEN vendor_iv > 0 AND vendor_iv <= 0.0005 AND quality_flags & 2048 <> 0
                       THEN 1 ELSE 0 END) AS of_them_flagged,
                   min(CASE WHEN vendor_iv > 0 THEN vendor_iv END) AS smallest_positive
                   FROM option_quotes GROUP BY 1 ORDER BY 1""").to_string(index=False))

    print("\n== the most common flag masks")
    masks = query("SELECT source, quality_flags, count(*) AS n FROM option_quotes GROUP BY 1, 2 ORDER BY n DESC LIMIT 6")
    for row in masks.itertuples(index=False):
        print(f"{row.source:9s} {int(row.quality_flags):5d} {flags.flag_names(int(row.quality_flags))} {row.n:,}")

    print("\n== calendar: OptionsDX vendor dates that are not SPY sessions")
    closures = query("SELECT * FROM calendar_actions WHERE source = 'optionsdx' AND action <> 'session' "
                     "ORDER BY vendor_date")
    gap = np.rint(closures["underlying_last"] * 100 - closures["prev_close"] * 100).astype(int)
    print(f"dates {len(closures)}; long rows {int(closures['rows'].sum()):,}; wide rows {int(closures['rows'].sum()) // 2:,}; "
          f"UNDERLYING_LAST minus the previous session's close, cents: {sorted(set(gap))}")
    print(closures[["vendor_date", "action", "quote_date", "underlying_last", "prev_session", "prev_close", "rows"]]
          .to_string(index=False))
    print("the quality report's non-session check (a diagnostic; every non-session date is dropped):",
          json.dumps(summary["non_session_dates"]))

    print("\n== calendar: DoltHub vendor dates dropped")
    dropped = query("SELECT * FROM calendar_actions WHERE source = 'dolthub' AND action = 'drop' ORDER BY vendor_date")
    weekday = pd.to_datetime(dropped["vendor_date"]).dt.day_name().value_counts().to_dict()
    year = pd.to_datetime(dropped["vendor_date"]).dt.year.value_counts().sort_index().to_dict()
    print(f"dates {len(dropped)}; rows {int(dropped['rows'].sum()):,}; by weekday {weekday}; by year {year}")

    print("\n== OptionsDX sessions without a snapshot, 2010-01-04 .. 2023-12-29")
    bars = query("SELECT date FROM spy_bars WHERE date BETWEEN '2010-01-04' AND '2023-12-29' ORDER BY date")
    vendor = query("SELECT vendor_date FROM calendar_actions WHERE source = 'optionsdx' ORDER BY vendor_date")
    clean = query("SELECT DISTINCT quote_date FROM option_quotes WHERE source = 'optionsdx' ORDER BY quote_date")
    sessions = set(bars["date"])
    print(f"sessions {len(sessions)}; missing against vendor dates {len(sessions - set(vendor['vendor_date']))}; "
          f"missing after the calendar step {len(sessions - set(clean['quote_date']))}")

    print("\n== UNDERLYING_LAST minus the SPY close, per OptionsDX date (cents)")
    print(json.dumps(summary["underlying_minus_close_cents"]))
    underlying = query("SELECT * FROM quality_underlying ORDER BY quote_date")
    print(f"dates beyond 0.10%: {int((underlying['diff_bp'].abs() > 10).sum())}; worst:")
    print(underlying.reindex(underlying["diff_cents"].abs().sort_values(ascending=False).index).head(5).to_string(index=False))

    print("\n== chain_mask")
    print(query("SELECT mask, count(*) AS pairs, count(DISTINCT quote_date) AS dates FROM chain_mask "
                "GROUP BY 1 ORDER BY 1").to_string(index=False))
    kept = query("""SELECT count(*) AS n FROM option_quotes q JOIN chain_mask m ON m.quote_date = q.quote_date
                    AND m.expiry = q.expiry AND m.strike_milli = CAST(round(q.strike * 1000) AS BIGINT)
                    WHERE q.source = 'optionsdx' AND m.mask = 'dolthub'""")["n"].iloc[0]
    window = query("SELECT count(*) AS n FROM option_quotes WHERE source = 'optionsdx' "
                   "AND quote_date BETWEEN '2020-01-06' AND '2023-12-29'")["n"].iloc[0]
    print(f"OptionsDX rows kept by chain_mask = dolthub: {kept:,} of {window:,} ({kept / window:.2%})")

    print("\n== cross-vendor check (vendor IVs; raw-mid parity)")
    print(json.dumps(summary["cross_vendor"], indent=1))
    overlap = query("SELECT * FROM cross_vendor_overlap ORDER BY quote_date")
    for column in ("iv30_diff_pts", "spot_dolthub_vs_close_bp", "spot_optionsdx_vs_close_bp"):
        values = overlap[column].dropna().abs()
        print(column, {limit: f"{(values <= limit).mean():.1%}" for limit in (0.5, 1, 2, 5, 10, 15, 20, 25, 50)})
    year = pd.to_datetime(overlap["quote_date"]).dt.year
    for column in ("spot_dolthub_vs_close_bp", "spot_optionsdx_vs_close_bp"):
        print(column, "median by year, bp:",
              {int(y): round(float(v), 2) for y, v in overlap.groupby(year)[column].median().items()})
    print("spot_dolthub_vs_close_bp within 25 bp by year:",
          {int(y): f"{(part.dropna().abs() <= 25).mean():.1%}"
           for y, part in overlap.groupby(year)["spot_dolthub_vs_close_bp"]})
    rates = query("SELECT year(date) AS year, avg(dgs3mo_pct) AS mean_dgs3mo_pct FROM rates "
                  "WHERE date BETWEEN '2020-01-06' AND '2023-12-29' GROUP BY 1 ORDER BY 1")
    print("mean DGS3MO by year, %:", {int(r.year): round(float(r.mean_dgs3mo_pct), 2) for r in rates.itertuples()})
    worst = overlap.reindex(overlap["iv30_diff_pts"].abs().sort_values(ascending=False).index).head(6)
    print(worst[["quote_date", "iv30_dolthub", "iv30_optionsdx", "iv30_diff_pts"]].to_string(index=False))

    print("\n== labelled hypothesis test: DoltHub rows dated on non-sessions")
    print(json.dumps(summary["previous_session_test"], indent=1))

    print("\n== DoltHub export evidence (run in the private mirror)")
    evidence = json.loads((config.raw_dir() / "dolthub" / "option_chain_spy.export.json").read_text())
    print(json.dumps({k: evidence[k] for k in ("rows", "ran_in", "dolt_status_before", "dolt_status_after",
                                                "wall_seconds")}, indent=1))

    print("\n== VIX3M")
    vix3m = query("SELECT min(date) AS first, max(date) AS last, count(*) AS n FROM vix3m")
    print(vix3m.to_string(index=False))


if __name__ == "__main__":
    main()
