"""Cross-vendor check: OptionsDX against DoltHub where both exist (ADR-0009 §5).

Two numbers per date, each computed the same way from each vendor's quotes:

    iv30   the 30-day at-the-money implied vol, from the vendor's OWN IV column. These are
           VENDOR IVs: fine for asking "do two vendors agree?", not the model IVs that M2
           computes. ATM is the listed strike nearest the SPY close; the call and put IVs there
           are averaged; 30 days is interpolated linearly in total variance (sigma^2 * tau)
           between the two expiries around it, with tau in calendar days / 365. A point whose
           vendor IV is invalid (VENDOR_IV_INVALID: null, zero or negative) at either vendor is
           left out.
    spot   the SPY price implied by put-call parity. For European options
           C - P = DF * (F - K), so F_K = K + (C_mid - P_mid) / DF at each strike. F is the
           median F_K over the 5 strikes nearest the one where C and P are closest (ADR-0008
           §3), and the spot is F * DF + PV(dividends to expiry). Raw mids: no American
           correction (that is M2), so a few bp of bias is expected at high rates.

Both vendors are measured on exactly the same points: the (expiry, strike, side) rows both
list that day. So a difference between them is a difference in their quotes, not in which
strikes they happen to list.

Comparing the spot with the SPY close and with the SPY open says when DoltHub's snapshot was
taken; OptionsDX, stamped 16:00 (ADR-0002), is the yardstick for how far the method itself
misses at the close.

The same machinery runs the LABELLED 2019 TEST: DoltHub's 2019 rows are dated on Saturdays,
so there is no same-date overlap. We test the hypothesis that they are the previous session's
close by comparing them with that session and with the next one. It is a hypothesis test,
never counted as overlap. DoltHub's rows on market closures get the same test.
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd

from volbt.data.flags import ASK_NULL, BID_NULL, CROSSED, VENDOR_IV_INVALID, ZERO_BID
from volbt.data.mask import WINDOW, as_dates, strike_milli
from volbt.data.reference import spy_dividends_pv

# A quote with any of these bits has no usable mid.
NO_MID = BID_NULL | ASK_NULL | ZERO_BID | CROSSED
TARGET_DAYS = 30
PARITY_STRIKES = 5
PARITY_MIN_DAYS = 7          # skip expiries closer than a week: tiny tau, noisy parity
DAYS_PER_YEAR = 365

# Thresholds, chosen on 2026-10-29 AFTER looking at the 2020-23 distributions (573 overlap
# dates; docs/milestones/01-data-layer.md, "Cross-vendor check"). They are MEASUREMENTS, not a
# test: we report the share of dates inside each one. A pass/fail on them could not fail,
# because they were fitted to the same dates (M1 review, R7), so there is no verdict.
# IV: the four Nov-2021 dates where DoltHub's own vol column is wrong (0.67-0.73 at the money
# against 0.12-0.15) fall outside 1 vol point.
THRESHOLD_IV30_PTS = 1.0
# Spot: against the open the typical miss is ~70 bp, so 25 bp separates "near the close" from it.
THRESHOLD_SPOT_BP = 25.0


def _one_vendor(rows: pd.DataFrame) -> pd.DataFrame:
    keep = ["expiry", "strike_milli", "call_put", "bid", "ask", "vendor_iv", "quality_flags"]
    out = rows.assign(strike_milli=strike_milli(rows["strike"]), expiry=as_dates(rows["expiry"]).to_numpy())
    return out[keep]


def common_points(rows_a: pd.DataFrame, rows_b: pd.DataFrame) -> pd.DataFrame:
    """The (expiry, strike, side) rows both vendors list, side by side (suffixes _a, _b)."""
    return _one_vendor(rows_a).merge(_one_vendor(rows_b), on=["expiry", "strike_milli", "call_put"],
                                     suffixes=("_a", "_b"))


def atm_iv30(points: pd.DataFrame, as_of: date, spot: float, suffix: str) -> float:
    """30-day ATM vendor IV on the common points, for the vendor with column suffix `suffix`.

    A point whose vendor IV is invalid (null, zero or negative: VENDOR_IV_INVALID) at EITHER
    vendor is left out for both, so the two vendors stay on exactly the same points and an
    ATM strike with a zero IV on one side is not averaged in.
    """
    both = points.dropna(subset=["vendor_iv_a", "vendor_iv_b"])
    invalid = (both["quality_flags_a"] | both["quality_flags_b"]) & VENDOR_IV_INVALID
    both = both[invalid == 0]
    nodes = []
    for expiry, group in both.groupby("expiry", sort=True):
        days = (expiry - as_of).days
        sides = group.pivot_table(index="strike_milli", columns="call_put", values=f"vendor_iv_{suffix}")
        if days <= 0 or not {"C", "P"} <= set(sides.columns):
            continue
        sides = sides.dropna(subset=["C", "P"])
        if sides.empty:
            continue
        # The strike nearest the SPY close; the same strike for both vendors (common points).
        atm = sides.index[np.argmin(np.abs(sides.index.to_numpy() / 1000 - spot))]
        nodes.append((days, (sides.loc[atm, "C"] + sides.loc[atm, "P"]) / 2))
    below = [n for n in nodes if n[0] <= TARGET_DAYS]
    above = [n for n in nodes if n[0] > TARGET_DAYS]
    if not below or not above:
        return math.nan
    (d1, iv1), (d2, iv2) = below[-1], above[0]
    t1, t2, t = d1 / DAYS_PER_YEAR, d2 / DAYS_PER_YEAR, TARGET_DAYS / DAYS_PER_YEAR
    # Linear in total variance w = iv^2 * tau, then back to a vol.
    w = iv1**2 * t1 + (iv2**2 * t2 - iv1**2 * t1) * (t - t1) / (t2 - t1)
    return math.sqrt(w / t) if w > 0 else math.nan


def parity_spot(points: pd.DataFrame, as_of: date, r_cc: float, dividends: pd.DataFrame,
                suffix: str) -> tuple[float, date | None]:
    """(implied spot, expiry used) from put-call parity on the front usable expiry."""
    usable = points[((points["quality_flags_a"] & NO_MID) == 0) & ((points["quality_flags_b"] & NO_MID) == 0)]
    for expiry, group in usable.groupby("expiry", sort=True):
        days = (expiry - as_of).days
        if days < PARITY_MIN_DAYS:
            continue
        mid = (group[f"bid_{suffix}"] + group[f"ask_{suffix}"]) / 2
        sides = group.assign(mid=mid).pivot_table(index="strike_milli", columns="call_put", values="mid")
        if not {"C", "P"} <= set(sides.columns):
            continue
        sides = sides.dropna(subset=["C", "P"])
        if len(sides) < 3:
            continue
        tau = days / DAYS_PER_YEAR
        discount = math.exp(-r_cc * tau)
        strikes = sides.index.to_numpy() / 1000
        gap = (sides["C"] - sides["P"]).to_numpy()
        forwards = strikes + gap / discount
        nearest = np.argsort(np.abs(strikes - strikes[np.argmin(np.abs(gap))]), kind="stable")[:PARITY_STRIKES]
        forward = float(np.median(forwards[nearest]))
        pv = spy_dividends_pv(dividends["ex_date"], dividends["amount"], as_of, expiry, r_cc)
        return forward * discount + pv, expiry
    return math.nan, None


def rate_on(rates: pd.DataFrame, day: date) -> float:
    """The last DGS3MO continuous rate published on or before `day`."""
    known = rates[rates["date"] <= day]
    return float(known["r_cc"].iloc[-1]) if len(known) else math.nan


def compare_pair(rows_d: pd.DataFrame, rows_o: pd.DataFrame, as_of: date, spot: float, r_cc: float,
                 dividends: pd.DataFrame) -> dict:
    """iv30 and parity spot for DoltHub rows (a) and OptionsDX rows (b) on their common points."""
    points = common_points(rows_d, rows_o)
    spot_d, expiry_d = parity_spot(points, as_of, r_cc, dividends, "a")
    spot_o, _ = parity_spot(points, as_of, r_cc, dividends, "b")
    return {"common_points": len(points),
            "iv30_dolthub": atm_iv30(points, as_of, spot, "a"),
            "iv30_optionsdx": atm_iv30(points, as_of, spot, "b"),
            "spot_dolthub": spot_d, "spot_optionsdx": spot_o, "parity_expiry": expiry_d}


OVERLAP_COLUMNS = ["quote_date", "spy_close", "spy_open", "common_points", "iv30_dolthub", "iv30_optionsdx",
                   "spot_dolthub", "spot_optionsdx", "parity_expiry"]
PREVIOUS_COLUMNS = ["vendor_date", "weekday", "prev_session", "next_session", "close_prev", "close_next",
                    "common_points", "iv30_dolthub", "spot_dolthub", "iv30_optionsdx_prev",
                    "spot_optionsdx_prev", "iv30_optionsdx_next"]


def overlap_table(clean: pd.DataFrame, bars: pd.DataFrame, rates: pd.DataFrame,
                  dividends: pd.DataFrame, window=WINDOW) -> pd.DataFrame:
    """One row per date both vendors have inside `window`."""
    dates = as_dates(clean["quote_date"]).to_numpy()
    inside = clean[(dates >= window[0]) & (dates <= window[1])].assign(day=dates[(dates >= window[0]) & (dates <= window[1])])
    by_source = {s: dict(tuple(g.groupby("day", sort=True))) for s, g in inside.groupby("source")}
    dolt, odx = by_source.get("dolthub", {}), by_source.get("optionsdx", {})
    bar = bars.set_index("date")
    rows = []
    for day in sorted(set(dolt) & set(odx)):
        close, open_ = float(bar.loc[day, "close"]), float(bar.loc[day, "open"])
        result = compare_pair(dolt[day], odx[day], day, close, rate_on(rates, day), dividends)
        rows.append({"quote_date": day, "spy_close": close, "spy_open": open_, **result})
    return add_differences(pd.DataFrame(rows, columns=OVERLAP_COLUMNS))


def add_differences(table: pd.DataFrame) -> pd.DataFrame:
    table = table.astype({c: float for c in ("iv30_dolthub", "iv30_optionsdx", "spot_dolthub",
                                             "spot_optionsdx", "spy_close", "spy_open")})
    table["iv30_diff_pts"] = (table["iv30_dolthub"] - table["iv30_optionsdx"]) * 100
    for vendor in ("dolthub", "optionsdx"):
        table[f"spot_{vendor}_vs_close_bp"] = (table[f"spot_{vendor}"] / table["spy_close"] - 1) * 1e4
        table[f"spot_{vendor}_vs_open_bp"] = (table[f"spot_{vendor}"] / table["spy_open"] - 1) * 1e4
    return table


def previous_session_test(raw_dolthub: pd.DataFrame, clean: pd.DataFrame, bars: pd.DataFrame,
                          rates: pd.DataFrame, dividends: pd.DataFrame, vendor_dates: list[date]) -> pd.DataFrame:
    """LABELLED HYPOTHESIS TEST, not overlap: are DoltHub rows dated on a non-session (a 2019
    Saturday, a holiday) the previous session's close? For each such date d, with p the
    session before d and n the session after it, compare DoltHub's rows on d with OptionsDX on
    p and on n, and DoltHub's parity spot with the SPY close on p and n. tau runs from p, as the
    hypothesis says."""
    sessions = sorted(bars["date"])
    bar = bars.set_index("date")
    odx = clean[clean["source"] == "optionsdx"]
    odx_days = as_dates(odx["quote_date"]).to_numpy()
    raw_days = as_dates(raw_dolthub["quote_date"]).to_numpy()
    rows = []
    for d in vendor_dates:
        before = [s for s in sessions if s < d]
        after = [s for s in sessions if s > d]
        if not before or not after:
            continue
        p, n = before[-1], after[0]
        rows_d = raw_dolthub[raw_days == d]
        record = {"vendor_date": d, "weekday": d.strftime("%A"), "prev_session": p, "next_session": n,
                  "close_prev": float(bar.loc[p, "close"]), "close_next": float(bar.loc[n, "close"])}
        # DoltHub's numbers with tau from p (the hypothesis), OptionsDX's from its own session.
        on_prev = compare_pair(rows_d, odx[odx_days == p], p, record["close_prev"], rate_on(rates, p), dividends)
        on_next = compare_pair(rows_d, odx[odx_days == n], n, record["close_next"], rate_on(rates, n), dividends)
        record.update({"common_points": on_prev["common_points"], "iv30_dolthub": on_prev["iv30_dolthub"],
                       "spot_dolthub": on_prev["spot_dolthub"], "iv30_optionsdx_prev": on_prev["iv30_optionsdx"],
                       "spot_optionsdx_prev": on_prev["spot_optionsdx"], "iv30_optionsdx_next": on_next["iv30_optionsdx"]})
        rows.append(record)
    table = pd.DataFrame(rows, columns=PREVIOUS_COLUMNS).astype(
        {c: float for c in ("close_prev", "close_next", "iv30_dolthub", "spot_dolthub", "iv30_optionsdx_prev",
                            "spot_optionsdx_prev", "iv30_optionsdx_next")})
    for tag in ("prev", "next"):
        table[f"spot_vs_close_{tag}_bp"] = (table["spot_dolthub"] / table[f"close_{tag}"] - 1) * 1e4
        table[f"iv30_diff_{tag}_pts"] = (table["iv30_dolthub"] - table[f"iv30_optionsdx_{tag}"]) * 100
    return table


def distribution(values) -> dict:
    """Quantiles of a series, ignoring NaN; n counts the non-NaN values."""
    clean_values = pd.Series(values, dtype=float).dropna()
    if clean_values.empty:
        return {"n": 0}
    q = clean_values.quantile([0.05, 0.25, 0.5, 0.75, 0.95])
    return {"n": int(len(clean_values)), "mean": float(clean_values.mean()),
            "p05": float(q[0.05]), "p25": float(q[0.25]), "median": float(q[0.5]),
            "p75": float(q[0.75]), "p95": float(q[0.95]),
            "mean_abs": float(clean_values.abs().mean())}


def share_within(values, threshold: float) -> dict:
    """{dates, share}: how many non-NaN values there are, and the share with |value| <= threshold."""
    clean_values = pd.Series(values, dtype=float).dropna().abs()
    return {"dates": int(len(clean_values)),
            "share": float((clean_values <= threshold).mean()) if len(clean_values) else math.nan}


def within_thresholds(overlap: pd.DataFrame) -> dict:
    """The share of overlap dates inside each chosen threshold. A measurement: nothing passes or fails."""
    iv = share_within(overlap["iv30_diff_pts"], THRESHOLD_IV30_PTS)
    spot = share_within(overlap["spot_dolthub_vs_close_bp"], THRESHOLD_SPOT_BP)
    return {"iv30_pts": THRESHOLD_IV30_PTS, "iv30_dates": iv["dates"], "iv30_share_within": iv["share"],
            "spot_bp": THRESHOLD_SPOT_BP, "spot_dates": spot["dates"], "spot_share_within": spot["share"]}


def by_year(overlap: pd.DataFrame) -> dict:
    """The same shares, and both parity spots' median miss of the close, for each calendar year.

    Pooled numbers hide that the years differ: 2020 sits well below the pooled spot share, and
    OptionsDX's parity spot drifts down as rates rise (the American put premium, which the
    European identity used here does not remove).
    """
    years = pd.to_datetime(overlap["quote_date"]).dt.year
    table: dict[str, list] = {name: [] for name in (
        "year", "dates", "iv30_share_within", "spot_dolthub_share_within",
        "spot_dolthub_vs_close_median_bp", "spot_optionsdx_vs_close_median_bp")}
    for year, part in overlap.groupby(years, sort=True):
        table["year"].append(int(year))
        table["dates"].append(int(len(part)))
        table["iv30_share_within"].append(share_within(part["iv30_diff_pts"], THRESHOLD_IV30_PTS)["share"])
        table["spot_dolthub_share_within"].append(
            share_within(part["spot_dolthub_vs_close_bp"], THRESHOLD_SPOT_BP)["share"])
        for vendor in ("dolthub", "optionsdx"):
            median = part[f"spot_{vendor}_vs_close_bp"].dropna().median()
            table[f"spot_{vendor}_vs_close_median_bp"].append(float(median) if pd.notna(median) else math.nan)
    return table
