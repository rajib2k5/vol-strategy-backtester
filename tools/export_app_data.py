"""Write the JSON files the React app reads into app/public/data/.

Run:  uv run python tools/export_app_data.py [--out-dir DIR] [--store DIR]

This is the ONLY place Python hands data to the app. The shape of every file is
the contract described in src/volbt/contract.py: an envelope (schema_version,
generated_at, source_commit) followed by the file's own fields. Change a field
name here and the app breaks, so bump SCHEMA_VERSION when you do.

Two datasets:
  illustrative_surface.json  an ILLUSTRATIVE SSVI surface (not market data), milestone 0.
  data_quality.json          aggregates of the built option-chain store (milestone 1): flag counts per
                             source and year, rows per source, the calendar fixes, the cross-vendor
                             agreement (measurements, no verdict) and the quality-gate result. Counts,
                             shares and quantiles only, never a quote. It is read from data/store/, so run tools/build_data.py first; pass
                             --store to read another store.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import pandas as pd

from volbt import illustrative
from volbt.contract import GitLookup, SCHEMA_VERSION, build_envelope, git_state
from volbt.data import flags, quality
from volbt.data.mask import WINDOW
from volbt.data.store import Store

# Resolved from this file's location, never from the current directory, so the script
# writes to the same place wherever it is run from. (`volbt` itself comes from the editable
# install that `uv sync` / `uv run` sets up; see [build-system] in pyproject.toml.)
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = REPO_ROOT / "app" / "public" / "data"

SURFACE_FILE = "illustrative_surface.json"
DATA_QUALITY_FILE = "data_quality.json"
MANIFEST_FILE = "manifest.json"
SURFACE_LABEL = "Illustrative SSVI surface — not market data"
# Six decimals is far more than the 3D plot can show and keeps the files small.
DECIMALS = 6

DATA_QUALITY_LABEL = "Data-quality aggregates of the built option-chain store: counts and quantiles, no quotes"
# One line per quality flag for the app's table (ADR-0009 §3; src/volbt/data/flags.py has the rules). A
# test requires a line for every flag in flags.FLAG_NAMES, so a new bit cannot be exported without one.
FLAG_DESCRIPTIONS = {
    "BID_NULL": "the bid is missing",
    "ASK_NULL": "the ask is missing",
    "ZERO_BID": "the bid is zero",
    "CROSSED": "the bid is above the ask",
    "LOCKED": "the bid equals the ask, above zero",
    "WIDE": "the spread is wider than the mid (bid above zero)",
    "STALE": "bid and ask unchanged since the contract's last snapshot while SPY moved 0.5% or more",
    "NON_SESSION_DATE": "the vendor dated the row on a day SPY did not trade",
    "RELABELLED": "reserved and never set: the calendar no longer moves a non-session row (removed in M1)",
    "VOLUME_UNRELIABLE": "volume missing, OptionsDX before 2021-01-04, or any DoltHub row",
    "UNDERLYING_MISMATCH": "UNDERLYING_LAST is more than 0.10% from the SPY close",
    "VENDOR_IV_INVALID": "the vendor's implied vol is missing, zero or negative",
    "EXPIRY_DAY": "the quote is on the contract's expiry date",
}
# The quantile columns of data_quality.json's cross_vendor.distributions, in the order the app reads
# them. `n` (a count) and `mean` are written too; see distributions().
QUANTILES = ("p05", "p25", "median", "p75", "p95")
# (key in build_summary.json's cross_vendor, row label, unit), in the order the app lists them.
DISTRIBUTIONS = (
    ("iv30_diff_pts_dolthub_minus_optionsdx", "30-day ATM IV, DoltHub minus OptionsDX", "vol pts"),
    ("spot_dolthub_vs_close_bp", "DoltHub parity spot against the SPY close", "bp"),
    ("spot_optionsdx_vs_close_bp", "OptionsDX parity spot against the SPY close", "bp"),
    ("spot_dolthub_vs_open_bp", "DoltHub parity spot against the SPY open", "bp"),
    ("spot_optionsdx_vs_open_bp", "OptionsDX parity spot against the SPY open", "bp"),
)
# The thresholds crossvendor.within_thresholds measures against, as
# (key, row label, threshold key, unit, dates key, share key) in build_summary.json's within_thresholds.
THRESHOLD_ROWS = (
    ("iv30", "30-day ATM IV: |DoltHub minus OptionsDX|", "iv30_pts", "vol pts", "iv30_dates", "iv30_share_within"),
    ("spot", "Parity spot: |DoltHub / SPY close minus 1|", "spot_bp", "bp", "spot_dates", "spot_share_within"),
)
# Said once in the file, because nothing else in cross_vendor may read as a verdict.
THRESHOLD_BASIS = (
    "Measurements, not a test. The thresholds were chosen on 2026-10-29 after looking at these same "
    "overlap dates, so a pass or fail on them could not fail; each row is the share of dates inside its threshold."
)
# The per-year columns of build_summary.json's cross_vendor.by_year, in the order the file lists them.
BY_YEAR_COLUMNS = ("iv30_share_within", "spot_dolthub_share_within",
                   "spot_dolthub_vs_close_median_bp", "spot_optionsdx_vs_close_median_bp")


def surface_payload(
    envelope: dict,
    rho=illustrative.RHO,
    eta=illustrative.ETA,
    sigma_short=illustrative.SIGMA_ATM_SHORT,
    sigma_long=illustrative.SIGMA_ATM_LONG,
) -> dict:
    """The illustrative_surface.json content."""
    k_grid, dte_grid, iv = illustrative.iv_grid(rho, eta, sigma_short, sigma_long)
    # Never ship a surface that fails the no-arbitrage rules, even a pretend one.
    # Pass the SAME term structure the grid was built from, or the check would vouch for a
    # different surface than the one written below.
    checks = illustrative.no_arbitrage_checks(dte_grid, rho, eta, sigma_short, sigma_long)
    if not all(checks.values()):
        raise ValueError(f"SSVI parameters violate no-arbitrage conditions: {checks}")
    return {
        **envelope,
        "illustrative": True,
        "label": SURFACE_LABEL,
        # .tolist() turns numpy numbers into plain Python ones that json can write.
        "moneyness": k_grid.round(DECIMALS).tolist(),
        "dte": dte_grid.tolist(),
        # iv[i_dte][j_k]: one row per expiry, one column per log-moneyness.
        "iv": iv.round(DECIMALS).tolist(),
        "params": {
            "model": "SSVI",
            "rho": rho,
            "eta": eta,
            "sigma_atm_short": sigma_short,
            "sigma_atm_long": sigma_long,
        },
    }


def manifest_payload(envelope: dict) -> dict:
    """The manifest.json content: the list of datasets the app can load."""
    return {
        **envelope,
        "datasets": [
            {
                "name": "illustrative_surface",
                "path": SURFACE_FILE,
                "schema_version": SCHEMA_VERSION,
                "description": (
                    "Illustrative SSVI implied-vol surface for the milestone-0 3D hero. "
                    "Not market data."
                ),
            },
            {
                "name": "data_quality",
                "path": DATA_QUALITY_FILE,
                "schema_version": SCHEMA_VERSION,
                "description": (
                    "Milestone-1 data-quality aggregates: quote flags per source and year, rows per "
                    "source, the calendar fixes, the cross-vendor agreement and the quality-gate "
                    "result. Counts and quantiles only; no quotes."
                ),
            },
        ],
    }


def _number(value, what: str) -> int | float:
    """A finite number rounded to DECIMALS, written as a whole number when it is one (1000, not 1000.0).

    A missing or NaN value is an error, never a null in the file.
    """
    if value is None or not math.isfinite(value):
        raise ValueError(f"{what} is {value!r}: the store has no number to export")
    rounded = round(float(value), DECIMALS)
    return int(rounded) if rounded.is_integer() else rounded


def flags_by_year(counts: pd.DataFrame) -> dict:
    """Per (source, year), column-wise: the quotes, and the quotes carrying each flag as a count and as a share."""
    rows = [int(n) for n in counts["rows"]]
    return {
        "source": [str(source) for source in counts["source"]],
        "year": [int(year) for year in counts["year"]],
        "rows": rows,
        "counts": {name: [int(n) for n in counts[name]] for name in flags.FLAG_NAMES},
        # The share is computed here because the app never divides: every number it shows is in the file.
        "shares": {
            name: [_number(int(n) / total, f"the share of {name}") for n, total in zip(counts[name], rows)]
            for name in flags.FLAG_NAMES
        },
    }


def sources_table(per_date: pd.DataFrame) -> dict:
    """Per source: its quotes and the number of snapshot dates they sit on."""
    by_source = per_date.groupby("source", sort=True).agg(rows=("rows", "sum"), dates=("rows", "size"))
    return {
        "source": [str(source) for source in by_source.index],
        "rows": [int(n) for n in by_source["rows"]],
        "dates": [int(n) for n in by_source["dates"]],
    }


def calendar_table(calendar: pd.DataFrame) -> dict:
    """Per (source, action): vendor dates and quotes. The action is session (kept) or drop."""
    return {
        "source": [str(source) for source in calendar["source"]],
        "action": [str(action) for action in calendar["action"]],
        "dates": [int(n) for n in calendar["dates"]],
        "rows": [int(n) for n in calendar["rows"]],
    }


def distributions_table(cross_vendor: dict) -> dict:
    """The quantiles of each cross-vendor difference, column-wise: one row per difference."""
    table: dict[str, list] = {name: [] for name in ("key", "label", "unit", "n", "mean", "mean_abs", *QUANTILES)}
    for key, label, unit in DISTRIBUTIONS:
        stats = cross_vendor[key]
        if not stats.get("n"):
            raise ValueError(f"cross-vendor {key} has no values: the vendors have no overlap to export")
        table["key"].append(key)
        table["label"].append(label)
        table["unit"].append(unit)
        table["n"].append(int(stats["n"]))
        for name in ("mean", "mean_abs", *QUANTILES):
            table[name].append(_number(stats[name], f"cross-vendor {key}.{name}"))
    return table


def within_thresholds_table(within: dict) -> dict:
    """The share of overlap dates inside each chosen threshold, column-wise. No pass, no fail."""
    table: dict[str, list] = {name: [] for name in ("key", "label", "threshold", "unit", "dates", "share_within")}
    for key, label, threshold_key, unit, dates_key, share_key in THRESHOLD_ROWS:
        table["key"].append(key)
        table["label"].append(label)
        table["threshold"].append(_number(within[threshold_key], f"threshold {threshold_key}"))
        table["unit"].append(unit)
        table["dates"].append(int(within[dates_key]))
        table["share_within"].append(_number(within[share_key], f"measured {share_key}"))
    return table


def by_year_table(by_year: dict) -> dict:
    """The cross-vendor shares and median spot misses per calendar year, column-wise."""
    table: dict[str, list] = {"year": [int(y) for y in by_year["year"]], "dates": [int(n) for n in by_year["dates"]]}
    for column in BY_YEAR_COLUMNS:
        table[column] = [_number(v, f"cross-vendor by_year {column} {year}") for v, year in zip(by_year[column], by_year["year"])]
    return table


def thresholds_table(
    counts: pd.DataFrame, calendar: pd.DataFrame, per_date: pd.DataFrame, underlying_p99_cents: float
) -> dict:
    """Every quality-gate limit beside the worst value the store reached, column-wise.

    The limits are quality.py's own constants. bound says which side fails: "max" means the worst
    value must stay at or below the limit, "min" at or above it.
    """
    rows = []
    for (source, flag), limit in quality.GATE_MAX_SHARE.items():
        part = counts[counts["source"] == source]
        rows.append(("max_share", source, f"{flag} share of a year's quotes", "max", limit,
                     (part[flag] / part["rows"]).max(), "fraction"))
    # One row per sampling regime: a source's minimum dates a year differs by regime (quality.py).
    for source, first, last, minimum, regime in quality.GATE_DATES_PER_YEAR:
        years = pd.to_datetime(per_date.loc[per_date["source"] == source, "quote_date"]).dt.year
        fewest = min(int((years == year).sum()) for year in range(first, last + 1))
        span = f"the thinnest year of {first}-{last}" if last > first else str(first)
        rows.append(("min_dates_per_year", source, f"snapshot dates in {span} ({regime})", "min", minimum,
                     fewest, "dates"))
    for source in quality.GATE_SOURCES:
        years = per_date.loc[per_date["source"] == source, "quote_date"]
        rows.append(("min_dates", source, "snapshot dates in all", "min", quality.GATE_MIN_DATES[source],
                     len(years), "dates"))
    for source, minimum in quality.GATE_MIN_ROWS_PER_DATE.items():
        dates = per_date[per_date["source"] == source]
        what = "quotes on the thinnest snapshot date"
        if source == "dolthub":  # the gate checks DoltHub only from its cross-vendor window
            dates = dates[dates["quote_date"] >= pd.Timestamp(quality.DOLTHUB_CHECKED_FROM)]
            what += f" from {quality.DOLTHUB_CHECKED_FROM.isoformat()}"
        rows.append(("min_rows_per_date", source, what, "min", minimum, dates["rows"].min(), "quotes"))
    for source, limit in quality.GATE_MAX_DROPPED_DATES.items():
        dropped = calendar[(calendar["source"] == source) & (calendar["action"] == "drop")]["dates"].sum()
        rows.append(("max_dropped_dates", source, "vendor dates the calendar drops", "max", limit, dropped, "dates"))
    rows.append(("max_underlying_p99_cents", "optionsdx", "99th percentile of |UNDERLYING_LAST minus the SPY close|",
                 "max", quality.GATE_MAX_UNDERLYING_P99_CENTS, underlying_p99_cents, "cents"))
    names = ("rule", "source", "what", "bound", "limit", "worst", "unit")
    table: dict[str, list] = {name: [] for name in names}
    for rule, source, what, bound, limit, worst, unit in rows:
        for name, value in zip(names, (rule, source, what, bound, limit, worst, unit)):
            if name in ("limit", "worst"):
                value = _number(value, f"the gate's {name} for {rule} {source}")
            table[name].append(value)
    return table


STORE_TABLES = ("quality_flag_counts", "quality_calendar", "quality_rows_per_date")
SUMMARY_FILE = "build_summary.json"


def data_quality_body(store: Store) -> dict:
    """The data_quality.json content after the envelope, read from a built store.

    Only aggregates leave the store: counts, shares and quantiles. Nothing read here is a quote.
    The same store always gives the same body: every read is ordered and every number is rounded.
    """
    summary_path = store.root / SUMMARY_FILE
    missing = [name for name in STORE_TABLES if not store.has(name)] + ([] if summary_path.is_file() else [SUMMARY_FILE])
    if missing:
        raise FileNotFoundError(
            f"{store.root} has no {', '.join(missing)}; build the store first: uv run python tools/build_data.py"
        )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    counts = store.read_table("quality_flag_counts", order_by="source, year")
    calendar = store.read_table("quality_calendar", order_by="source, action")
    per_date = store.read_table("quality_rows_per_date", order_by="source, quote_date")
    cross_vendor = summary["cross_vendor"]
    verdict = summary["quality_gate"]
    return {
        "label": DATA_QUALITY_LABEL,
        "flag_names": list(flags.FLAG_NAMES),
        "flag_descriptions": [FLAG_DESCRIPTIONS[name] for name in flags.FLAG_NAMES],
        "flags_by_year": flags_by_year(counts),
        "sources": sources_table(per_date),
        "calendar": calendar_table(calendar),
        "cross_vendor": {
            "label": f"Both vendors, {WINDOW[0].isoformat()} to {WINDOW[1].isoformat()}: {cross_vendor['label']}",
            "overlap_dates": int(cross_vendor["overlap_dates"]),
            "basis": THRESHOLD_BASIS,
            "distributions": distributions_table(cross_vendor),
            "within_thresholds": within_thresholds_table(cross_vendor["within_thresholds"]),
            "by_year": by_year_table(cross_vendor["by_year"]),
        },
        "gate": {
            "passed": bool(verdict["passed"]),
            "failures": list(verdict["failures"]),
            "thresholds": thresholds_table(
                counts, calendar, per_date, summary["underlying_minus_close_cents"]["p99_abs"]
            ),
        },
    }


def write_json(path: Path, payload: dict) -> None:
    # allow_nan=False makes json raise on NaN/Infinity instead of writing them:
    # those are not valid JSON and the browser's JSON.parse would reject the file.
    text = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False)
    # newline="\n": without it, Windows text mode turns every "\n" into "\r\n", so the same
    # export would give different bytes (and a git diff) depending on the OS.
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


def build_payloads(
    out_dir: Path = DEFAULT_OUT_DIR, git_lookup: GitLookup = git_state, now=None, *, quality_body: dict
) -> dict[str, dict]:
    """Write every JSON file into out_dir; return {file name: content}.

    quality_body is data_quality.json's content after the envelope (see data_quality_body). It is a
    parameter so that a test, which cannot assume a built store, can pass one.
    """
    # One envelope for all files, so every file in a run has the same timestamp.
    envelope = build_envelope(git_lookup, now)
    payloads = {
        MANIFEST_FILE: manifest_payload(envelope),
        SURFACE_FILE: surface_payload(envelope),
        DATA_QUALITY_FILE: {**envelope, **quality_body},
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads.items():
        write_json(out_dir / name, payload)
    return payloads


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--store", type=Path, default=None,
                        help="the built store to read data_quality.json from (default: the store under work_dir())")
    args = parser.parse_args(argv)
    try:
        body = data_quality_body(Store(args.store))
    except FileNotFoundError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    for name in build_payloads(args.out_dir, quality_body=body):
        print("wrote", args.out_dir / name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
