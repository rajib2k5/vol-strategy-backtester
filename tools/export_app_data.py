"""Write the JSON files the React app reads into app/public/data/.

Run:  uv run python tools/export_app_data.py [--out-dir DIR] [--store DIR]

This is the ONLY place Python hands data to the app. The shape of every file is
the contract described in src/volbt/contract.py: an envelope (schema_version,
generated_at, source_commit) followed by the file's own fields. Change a field
name here and the app breaks, so bump SCHEMA_VERSION when you do.

Three datasets:
  illustrative_surface.json  an ILLUSTRATIVE SSVI surface (not market data), milestone 0.
  data_quality.json          aggregates of the built option-chain store (milestone 1): flag counts per
                             source and year, rows per source, the calendar fixes, the cross-vendor
                             agreement (measurements, no verdict) and the quality-gate result. Counts,
                             shares and quantiles only, never a quote. It is read from data/store/, so run tools/build_data.py first; pass
                             --store to read another store.
  surface_frames.json        REAL SPY implied-vol surfaces (milestone 2) on a fixed grid, for a few
                             labelled dates: read from the pricing build's smile_fits, so run
                             tools/build_pricing.py first. Each grid cell is an IV off the de-Americanised
                             OTM smiles (ADR-0004's interpolation rules), never a quote.
  blotter.json and           one engine run's fills and expiry events, and its positions with the count
  positions_timeline.json    open each session (milestone 3; volbt.engine.report). The run is the one
                             tools/run_backtest.py --for-app recorded in work_dir()/runs/app_run.json, or
                             --run-dir: a development-split run only (decision D19). No P&L is written.
  signals_timeline.json and  milestone 4 (schema 0.5.0, plan section 8): one development run's VRP signal (IV30,
  strategy_positions.json    RV^, ex-post RV, log variance ratio, the HAR fits, the forecast test's result or null)
                             and the positions of development runs of the M4 strategies (legs, entry signal, exit
                             reason; no prices, no P&L). signals_timeline_body and strategy_positions_body refuse a
                             run that is not on the development split and any date after 2019-12-31. They are built
                             and tested here; the real export waits for the forecast test and the grid (part B2). The forecast test's result is
                             checked against its pre-registration in docs/validation/prereg (id, SHA-256, threshold,
                             fragile band, simulated sizes; see checked_forecast_test). main() does not build these
                             two files yet, so no CLI path feeds a result in.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

from datetime import date, timedelta

import numpy as np
import pandas as pd

from volbt import build, config, illustrative
from volbt.engine import report as engine_report
from volbt.contract import GitLookup, SCHEMA_VERSION, build_envelope, git_state
from volbt.data import flags, quality
from volbt.data.mask import WINDOW
from volbt.data import store as store_module
from volbt.data.store import Store, data_fingerprint
from volbt.pricing import smile
from volbt.signals import har
from volbt.signals.realised import total_log_returns

# Resolved from this file's location, never from the current directory, so the script
# writes to the same place wherever it is run from. (`volbt` itself comes from the editable
# install that `uv sync` / `uv run` sets up; see [build-system] in pyproject.toml.)
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = REPO_ROOT / "app" / "public" / "data"

SURFACE_FILE = "illustrative_surface.json"
DATA_QUALITY_FILE = "data_quality.json"
SURFACE_FRAMES_FILE = "surface_frames.json"
BLOTTER_FILE = "blotter.json"
POSITIONS_FILE = "positions_timeline.json"
APP_RUN_FILE = "app_run.json"
SIGNALS_TIMELINE_FILE = "signals_timeline.json"
STRATEGY_POSITIONS_FILE = "strategy_positions.json"
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


# The name of each vendor as the app shows it (app/src/lib/contract.ts DATA_SOURCE_NAMES); the app refuses a file
# whose label does not name the vendor of its run.data_source (M2 round 3, N4: the label once said OptionsDX always).
DATA_SOURCE_NAMES = {"optionsdx": "OptionsDX", "dolthub": "DoltHub"}


def surface_frames_label(source: str) -> str:
    """surface_frames.json's label, naming the vendor of the quotes."""
    if source not in DATA_SOURCE_NAMES:
        raise ValueError(f"{source!r} is not a data source the app knows ({', '.join(DATA_SOURCE_NAMES)})")
    return (f"SPY implied-vol surfaces from de-Americanised out-of-the-money quotes ({DATA_SOURCE_NAMES[source]}), "
            "read on a fixed grid of log-moneyness and days to expiry")


# The labelled dates of surface_frames.json: one calm, two stressed, and the high-rate date the ADRs
# measure on. A few dates, not ADR-0001's weekly series: enough to compare regimes, and small.
SURFACE_FRAME_DATES = (
    (date(2017, 11, 3), "calm: VIX near its 2017 low"),
    (date(2018, 2, 5), "shock: the February 2018 volatility spike"),
    (date(2020, 3, 16), "stress: the March 2020 crash"),
    (date(2023, 6, 15), "high rates: the reference date of ADR-0008"),
)
SURFACE_FRAMES_SOURCE = "optionsdx"
# ADR-0001 §5: a results file says the unit of every number it holds; the app never guesses.
SURFACE_UNITS = {
    "grid_moneyness": "log-moneyness ln(K/F), F the de-Americanised parity forward of each tenor",
    "grid_dte": "calendar days to expiry",
    "iv": "implied volatility, decimal (0.20 = 20%)",
    "atm_iv_30d": "implied volatility at k = 0 and 30 days, decimal",
    "spot": "USD, the SPY close",
    "vix_close": "index points, the Cboe VIX close",
    "quoted_share": "fraction of grid cells read without strike or tenor extrapolation",
    "cell_flags": ("bitmask of SURFACE_EXTRAP_STRIKE (1), SURFACE_CROSS_EXPIRY (2), SURFACE_EXTRAP_TENOR (4), "
                   "SURFACE_CALENDAR_ADJUSTED (8)"),
    "expiries_used": "listed expiries with a usable smile (5 or more valid OTM quotes)",
}


# The app's IV ceilings (app/src/lib/contract.ts MAX_IV, MAX_EXTRAPOLATED_IV and ivCeiling). The method does not
# bound a wing (Lee's slope from a node that can sit far from the grid), so the exporter checks each frame against
# them and refuses one the app would refuse, rather than write it (M2 round 3, X1 and T1).
MAX_IV = 5.0
MAX_EXTRAPOLATED_IV = 10.0


def iv_ceilings(cell_flags) -> np.ndarray:
    """Per cell, the highest IV the app accepts, the rule of contract.ts ivCeiling.

    MAX_EXTRAPOLATED_IV beyond the quoted strikes (SURFACE_EXTRAP_STRIKE), and past the back expiry where the calendar
    adjustment moved the value (SURFACE_CALENDAR_ADJUSTED on a row after the last row inside the listed expiries; on
    any row when none is inside): there smile.surface_iv's running maximum can read the back smile beyond its last
    node while the cell's own reading is inside it, so the cell carries no strike bit. MAX_IV everywhere else: the
    value is read inside some smile's quoted strikes, so a solved IV bounds it.
    """
    cells = np.asarray(cell_flags, dtype=int)
    inside = np.flatnonzero((cells[:, 0] & smile.SURFACE_EXTRAP_TENOR) == 0)   # the tenor bit is row-wide
    past = np.arange(cells.shape[0]) > (inside[-1] if inside.size else -1)
    high = ((cells & smile.SURFACE_EXTRAP_STRIKE) != 0) | (past[:, None] & ((cells & smile.SURFACE_CALENDAR_ADJUSTED) != 0))
    return np.where(high, MAX_EXTRAPOLATED_IV, MAX_IV)


def check_frame_ivs(frame: dict, grid_k, grid_dte) -> None:
    """ValueError naming the first cell whose IV is not in (0, its ceiling], and how many there are: the app would
    refuse the file. atm_iv_30d is the 30-day k = 0 cell itself, so it is checked with it."""
    iv = np.asarray(frame["iv"], dtype=float)
    ceiling = iv_ceilings(frame["cell_flags"])
    bad = np.argwhere(~((iv > 0) & (iv <= ceiling)))
    if bad.size:
        i, j = bad[0]
        raise ValueError(
            f"the {frame['date']} frame reads IV {iv[i, j]} at {grid_dte[i]} days, k = {grid_k[j]} (cell flags "
            f"{frame['cell_flags'][i][j]}), outside (0, {ceiling[i, j]:g}], the app's ceiling for that cell "
            f"({len(bad)} such cell(s)); the app would refuse the file, so it is not written")


def frame_dates(texts: list[str]) -> tuple[tuple[date, str], ...]:
    """The --frame values (YYYY-MM-DD=LABEL) as (date, label), sorted by date, as the app needs them (M2 round 3, N1).

    ValueError for a date given twice (the exporter does not choose between its labels), a value without "=", a
    date that is not one, or an empty label (the app refuses one).
    """
    chosen: dict[date, str] = {}
    for text in texts:
        day_text, sep, label = text.partition("=")
        if not sep or not label.strip():
            raise ValueError(f"--frame {text!r}: expected YYYY-MM-DD=LABEL with a non-empty label")
        try:
            day = date.fromisoformat(day_text)
        except ValueError:
            raise ValueError(f"--frame {text!r}: {day_text!r} is not a date YYYY-MM-DD") from None
        if day in chosen:
            raise ValueError(f"--frame {day.isoformat()} is given twice ({chosen[day]!r} and {label!r}): give each date once")
        chosen[day] = label
    return tuple(sorted(chosen.items()))


def frame_input_files(store: Store, frames, source: str) -> list[Path]:
    """The input files the frames depend on: the option_quotes partition of each frame's year, and
    the tables the pricing build and this export read beside them (rates, dividends, spy_bars, vix).

    Each of those tables must be its one part-0.parquet (Store.checked_table_file raises InconsistentStore
    otherwise): the export reads every parquet in a table's folder, so a second one would change what it
    ships and not the data_fingerprint (M2 round 4, decision G1)."""
    years = sorted({str(day.year) for day, _ in frames})
    files = [store.partition_file("option_quotes", {"source": source, "year": year}) for year in years]
    return files + [store.checked_table_file(name) for name in (*build.REFERENCE_TABLES, "vix")]


def surface_frames_body(store: Store, frames=SURFACE_FRAME_DATES, source: str = SURFACE_FRAMES_SOURCE) -> dict:
    """surface_frames.json after the envelope: run, units, illustrative (ADR-0001 §5), then the frames.

    `run` names what made the frames. config_hash is the pricing build's code fingerprint (every
    volbt module it imports, the library versions and the store's write settings,
    volbt.build.code_fingerprint). data_fingerprint is ADR-0001 §7's: the SHA-256 over the sorted
    (path, size, SHA-256) list of the input files (frame_input_files; paths relative to the store
    root), and nothing else. data_last_date is the last quote date the source has, so no frame can
    claim a date after its data. The execution fields belong to a backtest and are null here.
    """
    days = [day for day, _ in frames]
    if any(later <= earlier for earlier, later in zip(days, days[1:])):
        raise ValueError(f"frames must be in strictly increasing date order, as the app needs them: got "
                         f"{', '.join(day.isoformat() for day in days)} (main() sorts --frame dates)")
    label = surface_frames_label(source)
    read_store_json(store, build.INPUTS_FILE)       # the build ran: its fingerprints are on disk
    # config_hash must name the code that priced EVERY partition (M2 round 2, decision E5): a filtered
    # build after a code change leaves partitions priced by older code, and the summary of a build
    # before it would name code that did not price the rest.
    code = build.code_fingerprint()
    build.require_current(store, code)
    summary = read_store_json(store, build.SUMMARY_FILE)
    if summary.get("code_fingerprint") != code:
        raise build.PricingNotCurrent(f"{build.SUMMARY_FILE} names code {summary.get('code_fingerprint')!r}, not the "
                                      f"current {code}: partitions priced by older code: run a full build")
    # The export is a reader that checks before and after (M2 round 4, decision G2; ADR-0001 amendment 4). It
    # checked, then read: a quotes rewrite landing in between shipped the old IVs under the new quotes'
    # data_fingerprint. So the fingerprint is taken before the frames are read, and after them the store must
    # still be current and the fingerprint the same.
    fingerprint = data_fingerprint(frame_input_files(store, frames, source), store.root)
    body = build.surface_frames_body(store, list(frames), source=source)
    for frame in body["frames"]:
        check_frame_ivs(frame, body["grid_moneyness"], body["grid_dte"])
    last = store.query("SELECT max(quote_date) AS d FROM option_quotes WHERE source = ?", [source])["d"].iloc[0]
    build.require_current(store, code)
    after = data_fingerprint(frame_input_files(store, frames, source), store.root)
    if after != fingerprint:
        raise build.PricingNotCurrent(f"the frames' input files changed while the export read them (data_fingerprint "
                                      f"{fingerprint[:12]} before, {after[:12]} after): one writer at a time "
                                      "(ADR-0001); export again")
    dates = [day.isoformat() for day, _ in frames]
    run = {"run_id": f"pricing-{summary['code_fingerprint'][:12]}", "config_hash": summary["code_fingerprint"],
           "data_fingerprint": fingerprint,
           "data_source": source, "data_last_date": pd.Timestamp(last).date().isoformat(), "execution_mode": None,
           "fill_timing": None, "cap_mode": None, "chain_mask": "none", "sample_start": min(dates),
           "sample_end": max(dates)}
    return {"run": run, "units": SURFACE_UNITS, "illustrative": False, "label": label, **body}


def read_store_json(store: Store, name: str) -> dict:
    """A JSON file the pricing build wrote next to its tables; FileNotFoundError naming the fix if absent."""
    path = store.root / name
    if not path.is_file():
        raise FileNotFoundError(f"{store.root} has no {name}; run the pricing build first: uv run python tools/build_pricing.py")
    return json.loads(path.read_text(encoding="utf-8"))


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


ENGINE_DATASETS = [
    {"name": "blotter", "path": BLOTTER_FILE,
     "description": ("Milestone-3 fills and expiry events of one diagnostic engine run of the reference strategy on "
                     "the development split. Exercises the engine; not a strategy result; no P&L.")},
    {"name": "positions_timeline", "path": POSITIONS_FILE,
     "description": ("Milestone-3 positions of the same run, from open to close, and the count open each session. "
                     "Not a strategy result; no P&L.")},
]


def engine_bodies(run_dir: Path, splits: tuple[str, ...] = ("development",)) -> tuple[dict, dict]:
    """(blotter, positions_timeline) after the envelope, from one development-split run's ledger (D19).

    `splits` widens the guard only for runs on MADE-UP stores (tests/engine_store.py is dated 2023, so its runs are
    'validation'): the committed app files come from the real development run."""
    blotter = engine_report.blotter_body(run_dir)
    if not re.fullmatch(r"[0-9a-f]{40}(-dirty)?", blotter["run"]["engine_commit"]):
        raise ValueError(f"{run_dir}: engine_commit {blotter['run']['engine_commit']!r} names no commit; the app refuses "
                         "it (run tools/run_backtest.py inside the git work tree)")
    if blotter["run"]["split"] not in splits:
        raise ValueError(f"{run_dir}: only a development-split run may feed the app (decision D19), not "
                         f"{blotter['run']['split']!r}")
    return blotter, engine_report.positions_timeline_body(run_dir)


# --- milestone 4: signals_timeline.json and strategy_positions.json (plan section 8) ---------------------------------

DEVELOPMENT_END = date(2019, 12, 31)       # decision D19: nothing after it is shown
RV_WINDOW_DAYS = 30
SIGNALS_UNITS = {
    "iv30": "annualised implied vol, decimal (0.20 = 20%)",
    "rv_forecast": "annualised forecast vol over the next 30 calendar days, decimal",
    "rv_realised": "annualised realised vol over the next 30 calendar days, ex post, decimal",
    "log_var_ratio": "ln(IV30^2 / RV^2), dimensionless",
    "n_window": "sessions in (t, t + 30 calendar days]",
    "coef": "HAR coefficients [constant, daily, weekly, monthly] on daily squared log returns",
}
STRATEGY_POSITIONS_UNITS = {"ratio": "contracts per package, signed: + long, - short",
                            "entry_signal": "ln(IV30^2 / RV^2) at the entry decision, dimensionless"}
SIGNAL_FLAG_NAMES = ["RV_FALLBACK", "RV_MISSING", "IV30_MISSING", "WINDOW_EMPTY"]
SIGNAL_THRESHOLDS = {"short_entry": [0.0, 0.4], "long_entry": 0.0, "exit_band": 0.4}
STRATEGY_STRUCTURES = ("short_straddle", "long_straddle", "short_strangle", "straddle_calendar")
FORECAST_TEST_KEYS = ("prereg_id", "prereg_sha256", "window", "n", "q", "block", "draws", "mean_d", "ewc_t", "se", "p",
                      "p_holm", "ci", "alpha", "threshold", "worst_simulated_size", "effective_size", "fragile_band",
                      "fragile", "decision", "label")
EFFECTIVE_SIZE_RATES = ("worst_matched_battery_seed", "worst_matched_second_seed")
EFFECTIVE_SIZE_ABC = ("abc_size_battery_seed", "abc_size_second_seed")
PREREG_DIR = REPO_ROOT / "docs" / "validation" / "prereg"      # <id>.json, <id>.md, <id>.sha256 of each pre-registration
PREREG_ID = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]*")        # a plain file name: no "/", and no leading "."
M4_DATASETS = [
    {"name": "signals_timeline", "path": SIGNALS_TIMELINE_FILE,
     "description": ("Milestone-4 VRP signal of one development run: IV30, the forecast and ex-post realised vol, the "
                     "log variance ratio, the HAR fits and the forecast test. In-sample development data; no P&L.")},
    {"name": "strategy_positions", "path": STRATEGY_POSITIONS_FILE,
     "description": ("Milestone-4 positions of development runs of the four structures: legs, entry signal and exit "
                     "reason. Development trials; no prices, no P&L.")},
]


def m4_run(run_dir: Path, splits: tuple[str, ...], last_date: date) -> dict:
    """The run block of a run an M4 dataset may show: its split in `splits` (development; tests on MADE-UP stores widen
    it) and its sample ending by `last_date` (2019-12-31; tests widen it); else ValueError (decision D19)."""
    run = engine_report.run_block(run_dir)
    if not re.fullmatch(r"[0-9a-f]{40}(-dirty)?", run["engine_commit"]):
        raise ValueError(f"{run_dir}: engine_commit {run['engine_commit']!r} names no commit; the app refuses it")
    if run["split"] not in splits:
        raise ValueError(f"{run_dir}: only a development-split run may feed the app (decision D19), not "
                         f"{run['split']!r}")
    if date.fromisoformat(run["sample_end"]) > last_date:
        raise ValueError(f"{run_dir}: the run ends {run['sample_end']}, after {last_date}: nothing after the "
                         "development split may be shown (decision D19)")
    return run


def check_dates(days, last_date: date, what: str) -> None:
    late = [d for d in days if d is not None and d > last_date]
    if late:
        raise ValueError(f"{what}: {len(late)} date(s) after {last_date}, the first {late[0]} (decision D19)")


def number(value, digits: int = DECIMALS):
    """A finite float rounded to `digits`, or None for a null or NaN."""
    if value is None or not math.isfinite(float(value)):
        return None
    return round(float(value), digits)


def realised_vol(days: list[date], bar_days, v, last_date: date) -> list[float | None]:
    """sqrt(365/30 * sum of r_u^2 over the sessions u in (t, t + 30 days]) for each t; None where that window ends
    after last_date or holds no session."""
    bar_days = np.asarray(bar_days).astype("datetime64[D]")
    cumulative = np.concatenate([[0.0], np.cumsum(v)])
    out = []
    for t in days:
        end = t + timedelta(days=RV_WINDOW_DAYS)
        if end > last_date:
            out.append(None)
            continue
        lo = int(np.searchsorted(bar_days, np.datetime64(t, "D"), "right"))
        hi = int(np.searchsorted(bar_days, np.datetime64(end, "D"), "right"))
        total = cumulative[hi] - cumulative[lo]
        out.append(number(math.sqrt(total * 365 / RV_WINDOW_DAYS)) if hi > lo and total > 0 else None)
    return out


def unit_number(value, what: str) -> float:
    """`value` as a float in [0, 1] (a rate or a size), else ValueError."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ValueError(f"the forecast test's {what} is {value!r}, not a number in [0, 1]")
    return float(value)


def open_unit_number(value, what: str) -> float:
    """`value` as a float strictly inside (0, 1) (a level or a band edge), else ValueError. A bool is refused."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value < 1:
        raise ValueError(f"the forecast test's {what} is {value!r}, not a number in (0, 1)")
    return float(value)


def checked_effective_size(effective_size) -> dict:
    """The part of the result's effective_size the app shows: its threshold (a number in (0, 1)), the two ABC-weighted
    sizes and, for each seed, the worst matched size as {rate, null_side}. Other keys are dropped. A missing key, a
    size outside [0, 1], or an ABC-weighted size above the worst matched size of the same seed is a ValueError."""
    if not isinstance(effective_size, dict):
        raise ValueError("the forecast test's effective_size must be a dict")
    out = {}
    if "threshold" not in effective_size:
        raise ValueError("the forecast test's effective_size lacks 'threshold'")
    out["threshold"] = open_unit_number(effective_size["threshold"], "effective_size.threshold")
    for key in EFFECTIVE_SIZE_ABC:
        if key not in effective_size:
            raise ValueError(f"the forecast test's effective_size lacks {key!r}")
        out[key] = unit_number(effective_size[key], f"effective_size.{key}")
    for key in EFFECTIVE_SIZE_RATES:
        worst = effective_size.get(key)
        if not isinstance(worst, dict) or "rate" not in worst or "null_side" not in worst:
            raise ValueError(f"the forecast test's effective_size.{key} must hold 'rate' and 'null_side'")
        if not isinstance(worst["null_side"], str) or not worst["null_side"].strip():
            raise ValueError(f"the forecast test's effective_size.{key}.null_side must be a non-empty string")
        out[key] = {"rate": unit_number(worst["rate"], f"effective_size.{key}.rate"), "null_side": worst["null_side"]}
    for abc, worst in zip(EFFECTIVE_SIZE_ABC, EFFECTIVE_SIZE_RATES):
        if out[abc] > out[worst]["rate"]:
            raise ValueError(f"the forecast test's effective_size.{abc} {out[abc]!r} is above its {worst} rate "
                             f"{out[worst]['rate']!r}")
    return {key: out[key] for key in ("threshold", *EFFECTIVE_SIZE_ABC, *EFFECTIVE_SIZE_RATES)}


def checked_fragile_band(band, p: float, fragile) -> list:
    """The pre-registered fragile band [lo, hi) as a list of two numbers in (0, 1) with lo < hi, and `fragile`, which
    must be a bool equal to lo <= p < hi. Else ValueError."""
    if not isinstance(band, (list, tuple)) or len(band) != 2:
        raise ValueError(f"the forecast test's fragile_band is {band!r}, not [lo, hi]")
    lo = open_unit_number(band[0], "fragile_band[0]")
    hi = open_unit_number(band[1], "fragile_band[1]")
    if not lo < hi:
        raise ValueError(f"the forecast test's fragile_band lo {lo!r} is not below hi {hi!r}")
    if not isinstance(fragile, bool):
        raise ValueError(f"the forecast test's fragile is {fragile!r}, not a bool")
    if fragile != (lo <= p < hi):
        raise ValueError(f"the forecast test's fragile is {fragile!r} but p {p!r} against the band [{lo!r}, {hi!r}) "
                         f"makes it {lo <= p < hi!r}")
    return [lo, hi]


def _same(a, b) -> bool:
    return json.loads(json.dumps(a)) == json.loads(json.dumps(b))


def check_against_preregistration(result: dict, prereg_dir: Path) -> None:
    """The result against the pre-registration it names, in `prereg_dir` (<id>.json and <id>.sha256): prereg_id a
    plain file name with a .json there; a .sha256 file whose SHA-256 is the result's prereg_sha256 and whose line for
    <id>.json is the SHA-256 of the .json's bytes, checked before the .json is read (fix pass 5, item G6; review F
    claim 6: an edited working .json was used); the .json's "id" the same; the result's q, block and draws those of
    the .json's "test" (item G6); and the result's threshold, alpha, fragile_band, worst_simulated_size (the .json's
    size.worst.high.rate) and every effective_size key it carries equal to the .json's. Else ValueError."""
    prereg_id = result["prereg_id"]
    if not isinstance(prereg_id, str) or not PREREG_ID.fullmatch(prereg_id):
        raise ValueError(f"the forecast test's prereg_id {prereg_id!r} is not a plain file name "
                         "(only letters, digits, '.', '_' and '-', not starting with '.')")
    json_path = Path(prereg_dir) / f"{prereg_id}.json"
    if not json_path.is_file():
        raise ValueError(f"the forecast test names the pre-registration {prereg_id!r}, but {json_path} does not exist")
    sha_path = Path(prereg_dir) / f"{prereg_id}.sha256"
    if not sha_path.is_file():
        raise ValueError(f"the pre-registration {prereg_id!r} has no {sha_path.name} in {prereg_dir}")
    sha_bytes = sha_path.read_bytes()
    digest = hashlib.sha256(sha_bytes).hexdigest()
    if result["prereg_sha256"] != digest:
        raise ValueError(f"the forecast test's prereg_sha256 {result['prereg_sha256']!r} differs from the SHA-256 "
                         f"{digest} of {sha_path.name}")
    json_bytes = json_path.read_bytes()
    lines = [line.partition("  ") for line in sha_bytes.decode("utf-8", errors="replace").splitlines()]
    named = [line[0] for line in lines if line[2] == json_path.name]
    if named != [hashlib.sha256(json_bytes).hexdigest()]:
        raise ValueError(f"{json_path.name} does not match its line in {sha_path.name} (the working .json was edited "
                         "after it was frozen, or the line is missing)")
    prereg = json.loads(json_bytes)
    if not isinstance(prereg, dict) or prereg.get("id") != prereg_id:
        raise ValueError(f"{json_path}: its id {prereg.get('id') if isinstance(prereg, dict) else prereg!r} "
                         f"differs from the forecast test's prereg_id {prereg_id!r}")
    test = prereg.get("test")
    for key in ("q", "block", "draws"):
        want = test.get(key) if isinstance(test, dict) else None
        if not (type(result[key]) is int and type(want) is int and result[key] == want):
            raise ValueError(f"the forecast test's {key} {result[key]!r} differs from the pre-registration's test "
                             f"{key} {want!r}")
    registered = {"threshold": prereg.get("threshold"), "alpha": prereg.get("threshold"),
                  "fragile_band": prereg.get("fragile_band")}
    worst = prereg.get("size")
    for step in ("worst", "high", "rate"):
        worst = worst.get(step) if isinstance(worst, dict) else None
    registered["worst_simulated_size"] = worst
    for key, want in registered.items():
        if not _same(result[key], want):
            raise ValueError(f"the forecast test's {key} {result[key]!r} differs from the pre-registration's {want!r}")
    registered_size = prereg.get("effective_size")
    if not isinstance(registered_size, dict):
        raise ValueError(f"{json_path}: it has no effective_size")
    for key, value in result["effective_size"].items():
        if key not in registered_size or not _same(value, registered_size[key]):
            raise ValueError(f"the forecast test's effective_size.{key} {value!r} differs from the pre-registration's "
                             f"{registered_size.get(key)!r}")


def checked_forecast_test(result: dict | None, rv_model: str, prereg_dir: Path = PREREG_DIR) -> dict | None:
    """score_prereg's result, with k = 1, as the timeline carries it; None (not scored yet) stays None.

    Checked: every key present; threshold and alpha numbers (not bool) in (0, 1) and equal; p and p_holm in [0, 1] and
    p_holm == p (k = 1); the decision follows p < threshold and equals the timeline's rv_model; the label says proxy;
    effective_size (see checked_effective_size) has threshold == threshold, and each ABC size is at most the worst
    matched size of its seed; worst_simulated_size is in [0, 1] and at least the worst matched battery-seed size;
    fragile_band is [lo, hi] in (0, 1) and fragile is a bool equal to lo <= p < hi; and the result agrees with the
    pre-registration it names in `prereg_dir` (check_against_preregistration: file name, the .sha256 file's SHA-256
    and its line for the .json, id, the test's q, block and draws, threshold, alpha, fragile_band,
    worst_simulated_size and every effective_size key). effective_size passes through as its
    threshold, the two ABC-weighted sizes and the worst matched size of each seed (rate and null side); its other keys
    are dropped."""
    if result is None:
        return None
    missing = [key for key in FORECAST_TEST_KEYS if key not in result]
    if missing:
        raise ValueError(f"the forecast test's result lacks {missing}")
    threshold = open_unit_number(result["threshold"], "threshold")
    alpha = open_unit_number(result["alpha"], "alpha")
    if threshold != alpha:
        raise ValueError(f"the forecast test's threshold {result['threshold']!r} differs from its alpha "
                         f"{result['alpha']!r}")
    p = unit_number(result["p"], "p")
    if result["decision"] != ("har" if p < threshold else "naive"):
        raise ValueError(f"the forecast test's decision {result['decision']!r} does not follow p < threshold")
    if result["decision"] != rv_model:
        raise ValueError(f"the timeline's signal uses {rv_model!r}; the forecast test chose {result['decision']!r}")
    if not str(result["label"]).startswith("proxy"):
        raise ValueError("the forecast test's label must say it is a proxy")
    if unit_number(result["p_holm"], "p_holm") != p:
        raise ValueError(f"the forecast test's p_holm {result['p_holm']!r} differs from its p {result['p']!r} "
                         "(k = 1)")
    out = {key: result[key] for key in FORECAST_TEST_KEYS}
    out["ci"] = list(out["ci"])
    out["effective_size"] = checked_effective_size(out["effective_size"])
    if out["effective_size"]["threshold"] != threshold:
        raise ValueError(f"the forecast test's effective_size.threshold {out['effective_size']['threshold']!r} "
                         f"differs from its threshold {result['threshold']!r}")
    worst_size = unit_number(out["worst_simulated_size"], "worst_simulated_size")
    matched = out["effective_size"]["worst_matched_battery_seed"]["rate"]
    if worst_size < matched:
        raise ValueError(f"the forecast test's worst_simulated_size {worst_size!r} is below the worst matched "
                         f"battery-seed size {matched!r}")
    out["fragile_band"] = checked_fragile_band(out["fragile_band"], p, out["fragile"])
    check_against_preregistration(result, prereg_dir)
    return {"prereg_id": out.pop("prereg_id"), "prereg_sha256": out.pop("prereg_sha256"), "window": out.pop("window"),
            "k": 1, **out}


def signals_timeline_body(run_dir: Path, store: Store, signal_name: str | None = None,
                          forecast_test: dict | None = None, *, splits: tuple[str, ...] = ("development",),
                          last_date: date = DEVELOPMENT_END, prereg_dir: Path = PREREG_DIR) -> dict:
    """signals_timeline.json after the envelope, from one run's `signals` table (module docstring).

    forecast_test is checked by checked_forecast_test against the pre-registrations in `prereg_dir`.

    rv_realised and the fits are recomputed through a view of `store` at last_date on the run's split: the ex-post
    variance over each window, and har.fit at each model_fit_date the run used (the same call, on the same returns, as
    the signal's own fit: a fit dated F reads no return after F)."""
    run_dir = Path(run_dir)
    meta = engine_report.check_ledger(run_dir)
    run = m4_run(run_dir, splits, last_date)
    rows = engine_report.table(run_dir, "signals")
    names = sorted({row["signal_name"] for row in rows})
    name = signal_name if signal_name is not None else (names[0] if len(names) == 1 else None)
    if name not in names:
        raise ValueError(f"{run_dir}: name one of the run's signals {names}, not {signal_name!r}")
    rows = sorted((row for row in rows if row["signal_name"] == name), key=lambda row: row["session_date"])
    models = {row["rv_model"] for row in rows}
    if len(models) != 1:
        raise ValueError(f"{run_dir}: the signal {name} has rv_model {sorted(models)}")
    rv_model = models.pop()
    days = [row["session_date"] for row in rows]
    check_dates(days, last_date, f"{run_dir} signals")
    view = store_module.view(last_date, run["split"], store)
    bar_days, r = total_log_returns(view.spy_bars(), view.dividends())
    v = r ** 2
    fit_dates = sorted({row["model_fit_date"] for row in rows if row["model_fit_date"] is not None})
    check_dates(fit_dates, last_date, f"{run_dir} fits")
    fits = []
    for fit_date in fit_dates:
        fit = har.fit(v, bar_days, fit_date)
        if fit is None:
            raise ValueError(f"{run_dir}: the run used a HAR fit dated {fit_date} that the store cannot give again")
        fits.append({"fit_date": engine_report.iso(fit_date), "coef": [float(f"{c:.12g}") for c in fit.coef],
                     "n_pairs": fit.n_pairs})
    iv30 = [number(row["iv30"]) for row in rows]
    rv_forecast = [number(row["rv_forecast"]) for row in rows]
    ratio = [number(row["log_var_ratio"]) if iv is not None and rv is not None else None
             for row, iv, rv in zip(rows, iv30, rv_forecast)]
    body = {
        "run": run, "units": SIGNALS_UNITS, "illustrative": False,
        "label": (f"In-sample development data: the {name} signal ({rv_model}) of run {run['run_id'][:12]}, "
                  f"{run['sample_start']} to {run['sample_end']} ({run['data_source']}); no P&L"),
        "signal": {"name": name, "rv_model": rv_model, "window_days": RV_WINDOW_DAYS, "horizon": har.HORIZON,
                   "min_pairs": har.MIN_PAIRS},
        "thresholds": SIGNAL_THRESHOLDS,
        "dates": [engine_report.iso(d) for d in days],
        "iv30": iv30, "rv_forecast": rv_forecast, "rv_realised": realised_vol(days, bar_days, v, last_date),
        "log_var_ratio": ratio,
        "model_fit_date": [engine_report.iso(row["model_fit_date"]) for row in rows],
        "n_window": [int(row["n_window"]) for row in rows], "flags": [int(row["flags"]) for row in rows],
        "flag_names": SIGNAL_FLAG_NAMES, "fits": fits,
        "forecast_test": checked_forecast_test(forecast_test, rv_model, prereg_dir),
    }
    if engine_report.check_ledger(run_dir) != meta:
        raise engine_report.LedgerChanged(f"{run_dir}: run_meta.json changed while the signals were read")
    return body


def strategy_positions_body(runs, banner: str, *, splits: tuple[str, ...] = ("development",),
                            last_date: date = DEVELOPMENT_END) -> dict:
    """strategy_positions.json after the envelope. `runs`: [(run_dir, n_trials_group)], the development runs of M4
    strategies the Strategies tab shows; each position's legs, entry signal and exit reason (no price, no P&L)."""
    if not banner:
        raise ValueError("the Strategies tab needs its banner")
    out = []
    for run_dir, n_trials_group in runs:
        run_dir = Path(run_dir)
        meta = engine_report.check_ledger(run_dir)
        run = m4_run(run_dir, splits, last_date)
        if type(n_trials_group) is not int or n_trials_group < 1:
            raise ValueError(f"{run_dir}: n_trials_group must be an int >= 1, not {n_trials_group!r}")
        row = engine_report.table(run_dir, "runs")[0]
        params = json.loads(row["config_json"])["strategy"]["params"]
        entry = {p["position_id"]: p["entry_signal"] for p in engine_report.table(run_dir, "positions")}
        positions = []
        for p in engine_report.positions_timeline_body(run_dir)["positions"]:
            if p["structure"] not in STRATEGY_STRUCTURES:
                raise ValueError(f"{run_dir}: position {p['position_id']} is a {p['structure']!r}, not an M4 structure")
            check_dates([date.fromisoformat(d) for d in (p["opened"], p["closed"]) if d is not None], last_date,
                        f"{run_dir} position {p['position_id']}")
            positions.append({"position_id": p["position_id"], "structure": p["structure"], "opened": p["opened"],
                              "closed": p["closed"], "legs": p["legs"],
                              "entry_signal": number(entry[p["position_id"]]), "exit_reason": p["exit_reason"]})
        out.append({"run": run, "strategy": run["strategy"], "params": params, "trial_group": row["trial_group"],
                    "n_trials_group": n_trials_group, "positions": positions})
        if engine_report.check_ledger(run_dir) != meta:
            raise engine_report.LedgerChanged(f"{run_dir}: run_meta.json changed while the positions were read")
    if not out:
        raise ValueError("strategy_positions.json needs at least one run")
    return {"units": STRATEGY_POSITIONS_UNITS, "illustrative": False,
            "label": "Development trials of the milestone-4 strategies: entries and exits only, in-sample, no P&L",
            "banner": banner, "runs": out}


def app_run_dir(runs_root: Path | None = None) -> Path:
    """The run tools/run_backtest.py --for-app recorded; FileNotFoundError naming the fix if there is none."""
    path = (runs_root or config.work_dir() / "runs") / APP_RUN_FILE
    if not path.is_file():
        raise FileNotFoundError(f"no {path}: run the development run first: uv run python tools/run_backtest.py "
                                "--start 2010-01-04 --end 2019-12-31 --split development --for-app")
    return Path(json.loads(path.read_text(encoding="utf-8"))["run_dir"])


def manifest_payload(envelope: dict, engine: bool = False, m4: tuple[str, ...] = ()) -> dict:
    """The manifest.json content: the list of datasets the app can load (the engine's two when `engine`, and the
    milestone-4 datasets named in `m4`)."""
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
            {
                "name": "surface_frames",
                "path": SURFACE_FRAMES_FILE,
                "schema_version": SCHEMA_VERSION,
                "description": (
                    "Milestone-2 SPY implied-vol surfaces on a fixed grid for a few labelled dates, "
                    "from the de-Americanised OTM smiles of the pricing build. Market data."
                ),
            },
        ] + ([{**entry, "schema_version": SCHEMA_VERSION} for entry in ENGINE_DATASETS] if engine else [])
        + [{**entry, "schema_version": SCHEMA_VERSION} for entry in M4_DATASETS if entry["name"] in m4],
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
    out_dir: Path = DEFAULT_OUT_DIR, git_lookup: GitLookup = git_state, now=None, *, quality_body: dict,
    frames_body: dict, blotter_body: dict | None = None, positions_body: dict | None = None,
    signals_body: dict | None = None, strategy_body: dict | None = None,
) -> dict[str, dict]:
    """Write every JSON file into out_dir; return {file name: content}.

    quality_body and frames_body are data_quality.json's and surface_frames.json's content after
    the envelope (see data_quality_body and surface_frames_body). They are parameters so that a
    test, which cannot assume a built store, can pass them.
    """
    # One envelope for all files, so every file in a run has the same timestamp.
    envelope = build_envelope(git_lookup, now)
    engine = blotter_body is not None and positions_body is not None
    m4 = tuple(name for name, body in (("signals_timeline", signals_body), ("strategy_positions", strategy_body))
               if body is not None)
    payloads = {
        MANIFEST_FILE: manifest_payload(envelope, engine, m4),
        SURFACE_FILE: surface_payload(envelope),
        DATA_QUALITY_FILE: {**envelope, **quality_body},
        SURFACE_FRAMES_FILE: {**envelope, **frames_body},
    }
    if engine:
        payloads[BLOTTER_FILE] = {**envelope, **blotter_body}
        payloads[POSITIONS_FILE] = {**envelope, **positions_body}
    if signals_body is not None:
        payloads[SIGNALS_TIMELINE_FILE] = {**envelope, **signals_body}
    if strategy_body is not None:
        payloads[STRATEGY_POSITIONS_FILE] = {**envelope, **strategy_body}
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads.items():
        write_json(out_dir / name, payload)
    return payloads


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--frame", action="append", default=None, metavar="YYYY-MM-DD=LABEL",
                        help="a date and label for surface_frames.json (repeatable, in any order: the frames are "
                             "written by date, and a date given twice is refused; default: the four dates of "
                             "SURFACE_FRAME_DATES)")
    parser.add_argument("--store", type=Path, default=None,
                        help="the built store to read data_quality.json and surface_frames.json from "
                             "(default: the store under work_dir())")
    parser.add_argument("--run-dir", type=Path, default=None,
                        help="the engine run (a run_id=... folder) blotter.json and positions_timeline.json come from "
                             "(default: the one tools/run_backtest.py --for-app recorded)")
    parser.add_argument("--allow-split", action="append", default=[], choices=("validation", "holdout"),
                        help="also accept a run of this split: ONLY for a run on a made-up store (the tests'), never "
                             "for real data after 2019 (decision D19)")
    args = parser.parse_args(argv)
    try:
        dates = SURFACE_FRAME_DATES if not args.frame else frame_dates(args.frame)
    except ValueError as error:
        parser.error(str(error))                     # exits 2 with the usage line, before any store is read
    store = Store(args.store)
    try:
        body = data_quality_body(store)
        frames = surface_frames_body(store, dates)
        blotter, positions = engine_bodies(args.run_dir or app_run_dir(), ("development", *args.allow_split))
    except FileNotFoundError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    for name in build_payloads(args.out_dir, quality_body=body, frames_body=frames, blotter_body=blotter,
                               positions_body=positions):
        print("wrote", args.out_dir / name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
