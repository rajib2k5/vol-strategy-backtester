"""Print the numbers docs/milestones/02-pricing-core.md quotes, one labelled block each.

Run:  uv run python tools/report_m2.py [--store DIR] [--frames FILE]

Reads the pricing build's tables and pricing_summary.json (uv run python tools/build_pricing.py
first) and the exported app/public/data/surface_frames.json. Nothing here is used by the build: it
is a reader for the walkthrough, so every number the document quotes can be re-measured with one
command. A block named in the document as [report], "<block>" is the block printed under that
title here. The synthetic blocks (ADR-0008 test 8, the clean long-dated chains, the dividend rules,
theta, the exercise boundary, the premium in z) need no store beyond the dividends table.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from volbt import build
from volbt.data.store import Store
from volbt.pricing import black76, chain, dividends, exercise, lattice, smile
from volbt.pricing import iv as ivm

REPO_ROOT = Path(__file__).resolve().parents[1]
FRAMES_FILE = REPO_ROOT / "app" / "public" / "data" / "surface_frames.json"
# The quotes PARITY_OUTLIER can flag: a strike with a valid call AND a valid put (build.NOT_VALID clear, ask above 0).
PAIRABLE = f"""
    SELECT source, year, quote_date, expiry, strike FROM option_quotes
    WHERE expiry > quote_date AND quality_flags & {build.NOT_VALID} = 0 AND ask > 0
    GROUP BY ALL HAVING count(DISTINCT call_put) = 2"""


def block(title: str) -> None:
    print(f"\n=== {title} ===")


def rows(summary: dict, name: str, year=None, tenor="any"):
    for row in summary[name]:
        if row["year"] == year and (tenor == "any" or row["tenor"] == tenor):
            yield row


def synthetic(rate: float, days: int, dividend_day, sigma: float, strikes, truth_steps: int = 2000,
              procedure_steps: int = lattice.DEAM_TREE_STEPS, with_partner: bool = False):
    """(F error bp, max OTM IV error vol pts, PARITY_OUTLIER count, quotes[, premiums at the partner's IV]),
    with and without de-Americanisation. `dividend_day` is one day or a list of days, each $1.638367."""
    spot, dividend = 442.61, 1.638367
    tau, when = days / 365, np.atleast_1d(np.asarray(dividend_day, dtype=float)) / 365
    amounts = np.full(when.size, dividend)
    both = np.concatenate([strikes, strikes])
    calls = np.r_[np.ones(strikes.size, bool), np.zeros(strikes.size, bool)]
    prices = lattice.crr(spot, both, tau, rate, sigma, calls, [when], [amounts], steps=truth_steps)["price"]
    truth = (spot - (amounts * np.exp(-rate * when)).sum()) * np.exp(rate * tau)
    out = []
    for deamericanise in (True, False):
        priced = chain.price_chain(spot, rate, [tau], [when], [amounts], np.zeros(both.size, int), both, calls,
                                   prices, np.ones(both.size, bool), deamericanise=deamericanise, steps=procedure_steps)
        q = priced["quotes"]
        market = prices >= MARKET_MID_MIN
        failed = (q["iv_flags"] & chain.IV_FAIL) != 0
        row = ((priced["expiries"]["forward"][0] / truth - 1) * 1e4,
               np.nanmax(np.abs(q["iv"][q["is_otm"] & market] - sigma)) * 100,
               int(((q["iv_flags"] & chain.PARITY_OUTLIER) != 0).sum()), both.size)
        out.append(row + (int(q["premium_from_partner"].sum()), int((failed & market).sum()), int((failed & ~market).sum()))
                   if with_partner else row)
    return out


# The clean chains of tests/test_forward.py (kind, rate, days, sigma): its table states their bounds. The
# last eight were added in round 3 (decisions F3 and F4), and the one chain of the round-3 grid that still
# fails (r 10%, 700 days, sigma 0.08, one dividend) is printed last.
CLEAN_CHAINS = ([("one", 0.0521594, d, s) for d in (365, 540, 700) for s in (0.12, 0.15, 0.20)]
                + [(kind, 0.0521594, 700, s) for s in (0.08, 0.10) for kind in ("one", "quarterly")]
                + [("quarterly", 0.0521594, 540, 0.12)]
                + [c for r in (0.08, 0.10) for c in (("one", r, 365, 0.12), ("quarterly", r, 450, 0.12),
                                                     ("quarterly", r, 700, 0.15))]
                + [("one", 0.08, 700, 0.12), ("one", 0.08, 365, 0.08), ("one", 0.10, 700, 0.12), ("one", 0.10, 540, 0.10),
                   ("quarterly", 0.10, 700, 0.10), ("quarterly", 0.08, 700, 0.08), ("one", 0.08, 540, 0.10),
                   ("quarterly", 0.10, 365, 0.08)])
STILL_FAILING_CHAIN = ("one", 0.10, 700, 0.08)
# Half a tick: the smallest mid the store holds (a zero bid, a $0.01 ask). Below it a synthetic chain's
# deep-OTM prices ($2e-5 to $5e-4) cannot pin an American IV (tests/test_forward.py, MARKET_MID_MIN).
MARKET_MID_MIN = 0.005


def dividend_rules(store: Store) -> dict:
    """Mean and max absolute % error of four no-look-ahead amount rules over SPY's ex-dates since 2009."""
    paid = store.read_table("dividends", order_by="ex_date")
    days = [d.date() for d in paid["ex_date"]]
    amount = paid["amount"].to_numpy(float)
    errors = {"last paid": [], "same quarter a year earlier": [], "trailing four-quarter mean": [],
              "same quarter a year earlier x trailing growth (the rule)": []}
    for i, day in enumerate(days):
        if day < date(2009, 1, 1):
            continue
        a = amount[i]
        errors["last paid"].append(amount[i - 1] / a - 1)
        errors["same quarter a year earlier"].append(amount[i - 4] / a - 1)
        errors["trailing four-quarter mean"].append(amount[i - 4:i].mean() / a - 1)
        rule = dividends.projected_amount(days, list(amount), day - timedelta(days=1), day)
        errors["same quarter a year earlier x trailing growth (the rule)"].append(rule / a - 1)
    return {name: np.array(values) for name, values in errors.items()}


def boundary(strike, rate, sigma, tau, tol) -> float:
    """The spot below which ADR-0003's put rule exercises (continuation - (K - S) <= tol), by bisection."""
    lo, hi = 300.0, strike
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        root = lattice.crr(mid, strike, tau, rate, sigma, False, steps=lattice.EXERCISE_TREE_STEPS)
        if float(root["continuation"][0]) - (strike - mid) <= tol:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", type=Path, default=None)
    parser.add_argument("--frames", type=Path, default=FRAMES_FILE)
    args = parser.parse_args(argv)
    store = Store(args.store)
    path = store.root / "pricing_summary.json"
    if not path.is_file():
        print(f"error: no {path}; run: uv run python tools/build_pricing.py", file=sys.stderr)
        return 1
    summary = json.loads(path.read_text(encoding="utf-8"))
    timings = json.loads((store.root / "pricing_timings.json").read_text(encoding="utf-8"))
    print(f"pricing build {summary['code_fingerprint']}")

    block("IV solve")
    for row in rows(summary, "quotes", tenor=None):
        print(f"{row['source']}: {row['otm_attempted']:,} OTM quotes with a mid, {row['solved']:,} solved "
              f"({row['solved'] / row['otm_attempted']:.4%}); of them valid (bid > 0, not STALE) {row['otm_valid']:,}, "
              f"of which WIDE {row['otm_valid_wide']:,} ({row['otm_valid_wide'] / row['otm_valid']:.2%}, not smile nodes since "
              f"round 3); valid and not WIDE {row['otm_smile_ok']:,}, in the smile {row['in_smile']:,} "
              f"({row['in_smile'] / row['otm_smile_ok']:.4%}); IV_FAIL {row['iv_fail']:,} "
              f"(on valid quotes {row['iv_fail_valid']:,}) = below the lower bound {row['fail_below_lower_bound']:,}, above "
              f"the upper bound {row['fail_above_upper_bound']:,}, no root in [1e-4, 5] {row['fail_no_root']:,}, unresolved "
              f"{row['fail_unresolved']:,}, no American IV {row['fail_american']:,} (below the lattice floor "
              f"{row['fail_american_below_floor']:,}, above A(5) {row['fail_american_above_cap']:,}, no convergence "
              f"{row['fail_american_no_convergence']:,}, unidentified {row['fail_american_unidentified']:,}); premium at "
              f"the partner's American IV {row['premium_from_partner']:,}; Newton {row['newton']:,}, bisection {row['bisection']:,} "
              f"({row['bisection'] / row['solved']:.1%}); quotes in all {row['quotes']:,}")

    pairable = store.query(f"""
        WITH p AS ({PAIRABLE})
        SELECT o.source, {build.TENOR.replace('expiry', 'o.expiry').replace('quote_date', 'o.quote_date')} AS tenor,
               o.year, count(*) AS pairable
        FROM option_quotes o JOIN p USING (source, year, quote_date, expiry, strike)
        GROUP BY GROUPING SETS ((o.source, tenor), (o.source, tenor, o.year)) ORDER BY ALL""")
    pairs = {(r.source, r.tenor, r.year if isinstance(r.year, str) else None): int(r.pairable)
             for r in pairable.itertuples(index=False)}

    block("IV flags by tenor")
    for row in rows(summary, "quotes"):
        if row["tenor"] is not None:
            can = pairs.get((row["source"], row["tenor"], None))
            print(f"{row['source']} {row['tenor']:>7}: quotes {row['quotes']:,}; IV_FAIL {row['iv_fail']:,}; PARITY_OUTLIER "
                  f"{row['parity_outlier']:,} ({row['parity_outlier'] / row['quotes']:.2%} of all quotes, "
                  f"{row['parity_outlier'] / can:.2%} of the {can:,} the test can flag); FORWARD_FALLBACK "
                  f"{row['forward_fallback']:,}")

    block("PARITY_OUTLIER beyond 180 days, by year (OptionsDX)")
    for row in summary["quotes"]:
        if row["source"] == "optionsdx" and row["year"] and row["tenor"] == "181+":
            can = pairs.get(("optionsdx", "181+", row["year"]))
            print(f"{row['year']}: {row['parity_outlier']:,} of {row['quotes']:,} ({row['parity_outlier'] / row['quotes']:.1%}; "
                  f"{row['parity_outlier'] / can:.1%} of the {can:,} the test can flag)")

    block("PARITY_OUTLIER beyond 180 days: which side of F, and how wide the quotes are (OptionsDX)")
    where = store.query(f"""
        WITH x AS (
            SELECT q.year, q.iv_flags & 2 <> 0 AS flagged, q.log_moneyness > 0 AS above_f,
                   (o.ask - o.bid) / ((o.ask + o.bid) / 2) AS rel_spread,
                   (o.quality_flags & {build.NOT_VALID}) = 0 AND o.ask > 0 AS valid
            FROM quote_iv q JOIN option_quotes o USING (source, year, quote_date, osi_symbol)
            WHERE q.source = 'optionsdx' AND q.expiry - q.quote_date > 180)
        SELECT year, count(*) FILTER (flagged) AS flagged, avg(above_f::INTEGER) FILTER (flagged) AS above,
               median(rel_spread) FILTER (flagged AND valid) AS spread_flagged,
               median(rel_spread) FILTER (NOT flagged AND valid) AS spread_clean
        FROM x GROUP BY year ORDER BY year""")
    for r in where.itertuples(index=False):
        print(f"{r.year}: {r.flagged:,} flagged, {r.above:.0%} with K above F; median relative spread (valid quotes) "
              f"{r.spread_flagged:.3f} flagged against {r.spread_clean:.3f} not ({r.spread_flagged / r.spread_clean:.1f}x)")

    block("forward against the carry forward (DGS3MO and the projected dividends), bp")
    for row in rows(summary, "forwards"):
        if row["tenor"] is not None:
            print(f"{row['source']} {row['tenor']:>7}: expiries {row['expiries']:,} (fallback {row['fallback']}, raw parity "
                  f"{row['parity_raw']}); de-Americanised median {row['vs_carry_bp_median']:+.2f}, 5-95% "
                  f"{row['vs_carry_bp_p05']:+.2f} to {row['vs_carry_bp_p95']:+.2f}; raw median {row['raw_vs_carry_bp_median']:+.2f}; "
                  f"dispersion (MAD/F) median {row['mad_bp_median']:.2f}, p95 {row['mad_bp_p95']:.2f}; F_K slope median "
                  f"{row['fk_slope_median']:+.4f}")

    block("de-Americanisation size")
    for row in rows(summary, "forwards"):
        if row["tenor"] is not None:
            print(f"{row['source']} {row['tenor']:>7}: F - F_raw median {row['deam_shift_bp_median']:+.2f} bp, "
                  f"p95 {row['deam_shift_bp_p95']:+.2f}, max {row['deam_shift_bp_max']:+.2f}")
    for row in rows(summary, "quotes"):
        if row["tenor"] is not None:
            print(f"{row['source']} {row['tenor']:>7}: IV(raw mid) - IV(de-Am mid), vol pts: median "
                  f"{row['deam_iv_pts_median']:.4f}, p95 {row['deam_iv_pts_p95']:.3f}, p99 {row['deam_iv_pts_p99']:.3f}, "
                  f"max {row['deam_iv_pts_max']:.2f}; beyond |k| > 0.15: {row['beyond_015']:,} quotes, "
                  f"{row['beyond_015_above_002']:,} corrected by more than 0.02, p99 {row['deam_iv_pts_beyond_015_p99']:.3f}, "
                  f"max {row['deam_iv_pts_beyond_015_max']:.3f}")
    tails = store.query(f"""
        SELECT source, {build.TENOR} AS tenor, quantile_cont((forward / forward_raw - 1) * 1e4, [0.05, 0.5, 0.95]) AS q,
               min((forward / forward_raw - 1) * 1e4) AS low
        FROM expiry_forwards WHERE method = 'parity_median5_deam' AND tau_years > 0 GROUP BY ALL ORDER BY ALL""")
    for r in tails.itertuples(index=False):
        print(f"{r.source} {r.tenor:>7}: F - F_raw 5-95% {r.q[0]:+.2f} to {r.q[2]:+.2f} bp, min {r.low:+.2f} (negative where the "
              f"near-K* ITM calls' dividend premium outweighs the puts')")
    example = store.query("""SELECT forward, forward_raw, forward_carry FROM expiry_forwards WHERE source = 'optionsdx'
                             AND quote_date = '2010-03-17' AND expiry = '2010-03-19'""").iloc[0]
    print(f"example, OptionsDX 2010-03-17, expiry 2010-03-19 (an ex-date): raw parity {(example['forward_raw'] / example['forward_carry'] - 1) * 1e4:+.1f} bp "
          f"from the carry forward, de-Americanised {(example['forward'] / example['forward_carry'] - 1) * 1e4:+.1f} bp")
    total = store.query("""SELECT count(*) FILTER (abs(log_moneyness) > 0.15 AND (iv_raw - iv) * 100 > 0.02) AS n,
                                  count(*) FILTER (abs(log_moneyness) > 0.15 AND iv IS NOT NULL) AS of
                           FROM quote_iv WHERE source = 'optionsdx' AND expiry > quote_date""").iloc[0]
    print(f"optionsdx all tenors: {int(total['n']):,} of {int(total['of']):,} quotes beyond |k| > 0.15 corrected by more than 0.02")

    block("de-Americanisation by year, 0-60 days")
    for name in ("forwards", "quotes"):
        for row in summary[name]:
            if row["year"] and row["tenor"] == "0-60":
                if name == "forwards":
                    print(f"{row['source']} {row['year']} mean r {row['mean_r_cc']:.4f}: F shift median "
                          f"{row['deam_shift_bp_median']:+.2f} bp, p95 {row['deam_shift_bp_p95']:+.2f}; F vs carry median "
                          f"{row['vs_carry_bp_median']:+.2f} (raw {row['raw_vs_carry_bp_median']:+.2f})")
                else:
                    print(f"{row['source']} {row['year']}: IV shift p95 {row['deam_iv_pts_p95']:.3f} vol pts, "
                          f"p99 {row['deam_iv_pts_p99']:.3f}")

    block("the largest IV corrections, 0-60 days")
    top = store.query("""
        SELECT q.source, q.quote_date, q.osi_symbol, q.expiry - q.quote_date AS days, round(q.log_moneyness, 4) AS k,
               round(q.iv_raw, 4) AS iv_raw, round(q.iv, 4) AS iv, round(q.iv_american, 4) AS iv_am, round(q.eep, 3) AS eep,
               o.bid, o.ask, o.spy_close, (SELECT min(ex_date) FROM dividends d WHERE d.ex_date > q.quote_date) AS next_ex
        FROM quote_iv q JOIN option_quotes o USING (source, year, quote_date, osi_symbol)
        WHERE q.expiry - q.quote_date <= 60 AND q.iv IS NOT NULL
        ORDER BY q.iv_raw - q.iv DESC, q.source, q.quote_date, q.osi_symbol LIMIT 6""")
    print(top.to_string(index=False))
    spans = store.query("""
        SELECT count(*) FILTER ((q.iv_raw - q.iv) * 100 > 3) AS above3,
               count(*) FILTER ((q.iv_raw - q.iv) * 100 > 3 AND month(d.ex_date) = 3) AS march,
               count(*) FILTER ((q.iv_raw - q.iv) * 100 > 3 AND month(d.ex_date) = 6) AS june,
               count(*) FILTER ((q.iv_raw - q.iv) * 100 > 3 AND month(d.ex_date) = 9) AS september,
               count(*) FILTER ((q.iv_raw - q.iv) * 100 > 3 AND month(d.ex_date) = 12) AS december
        FROM quote_iv q LEFT JOIN dividends d ON d.ex_date > q.quote_date AND d.ex_date <= q.expiry
        WHERE q.source = 'optionsdx' AND q.expiry - q.quote_date <= 60 AND q.iv IS NOT NULL""").iloc[0]
    print(f"optionsdx 0-60 days: {int(spans['above3']):,} (quote, ex-date) pairs corrected by more than 3 vol points; the "
          f"ex-date inside the option's life is in March {int(spans['march']):,}, June {int(spans['june']):,}, September "
          f"{int(spans['september']):,}, December {int(spans['december']):,}")

    block("smiles and leave-one-out interpolation error, vol pts")
    for row in rows(summary, "smiles"):
        if row["tenor"] is not None:
            print(f"{row['source']} {row['tenor']:>7}: {row['smiles']:,} smiles, {row['usable']:,} usable (5+ nodes), "
                  f"median {row['nodes_median']:.0f} nodes, ATM outside the nodes {row['atm_outside_nodes']}")
    for row in rows(summary, "leave_one_out"):
        print(f"{row['source']} {row['tenor'] or 'all':>7}: {row['points']:,} interior nodes; median {row['median_pts']:.3f}, "
              f"p90 {row['p90_pts']:.3f}; |k| <= 0.15 median {row['median_pts_k015']:.3f}, p90 {row['p90_pts_k015']:.3f}; "
              f"|k| <= 0.05 median {row['median_pts_k005']:.3f}, p90 {row['p90_pts_k005']:.3f}")

    block("DoltHub's smile read at OptionsDX-only strikes, 2020-2023, 0-60 days, vol pts")
    # The error an in-grid DoltHub model mark carries: DoltHub's piecewise-linear smile read at the
    # strikes OptionsDX quoted and DoltHub did not, inside DoltHub's nodes, against OptionsDX's own IV.
    frames = store.query("""
        SELECT s.source, s.quote_date, s.expiry, s.tau_years, s.k_nodes, s.total_var_nodes, f.forward
        FROM smile_fits s JOIN expiry_forwards f USING (source, year, quote_date, expiry)
        WHERE s.fit_flags & 1 = 0 AND s.quote_date >= '2020-01-01' AND s.quote_date < '2024-01-01'
              AND s.expiry - s.quote_date BETWEEN 1 AND 60 ORDER BY s.source, s.quote_date, s.expiry""")
    by = {source: part.set_index(["quote_date", "expiry"]) for source, part in frames.groupby("source")}
    errors = []
    for key in by["dolthub"].index.intersection(by["optionsdx"].index):
        d, o = by["dolthub"].loc[key], by["optionsdx"].loc[key]
        kd, wd, ko, wo = (np.asarray(x, dtype=float) for x in (d.k_nodes, d.total_var_nodes, o.k_nodes, o.total_var_nodes))
        strike_d, strike_o = np.round(d.forward * np.exp(kd), 2), np.round(o.forward * np.exp(ko), 2)
        off = ~np.isin(strike_o, strike_d)
        k = np.log(strike_o[off] / d.forward)
        inside = (k > kd[0]) & (k < kd[-1])
        read = np.interp(k[inside], kd, wd)
        errors.append(np.abs(np.sqrt(read / d.tau_years) - np.sqrt(wo[off][inside] / o.tau_years)) * 100)
    errors = np.concatenate(errors)
    print(f"{errors.size:,} strikes; error against OptionsDX's IV median {np.median(errors):.3f}, p90 {np.quantile(errors, 0.9):.3f}")

    block("the calendar constraint at the smiles' own nodes (250 random dates per source, seed 1)")
    # Each in_smile node read back with surface_iv at its own (k, tau): moved where the bit is set.
    # A move is "by a quote" when the new value is the running maximum of the QUOTED values (k inside
    # the expiry's own nodes) of the expiries up to it (round 2, design claim 1: 78.2% were not).
    for source in ("optionsdx", "dolthub"):
        dates = store.query("SELECT DISTINCT quote_date FROM smile_fits WHERE source = ? ORDER BY quote_date",
                            [source])["quote_date"].to_numpy()
        pick = sorted(np.random.default_rng(1).choice(dates, size=min(250, len(dates)), replace=False))
        nodes = moved = not_by_quote = down = core_nodes = core_moved = 0
        moves, worst = [], (0.0, None)
        for day in pick:
            smiles = build.usable_smiles(store.query(
                "SELECT tau_years, k_nodes, total_var_nodes, n_points FROM smile_fits WHERE source = ? AND quote_date = ? "
                "ORDER BY expiry", [source, day]))
            for i, (tau, kn, wn) in enumerate(smiles):
                sig, fl = smile.surface_iv(kn, tau, smiles)
                m = (fl & smile.SURFACE_CALENDAR_ADJUSTED) != 0
                quoted = np.max([np.where(b, -np.inf, v) for v, b in
                                 (smile.smile_variance(kn, e[1], e[2]) for e in smiles[: i + 1])], axis=0)
                core = (np.abs(kn) <= 0.15) & (tau * 365 <= 60)
                nodes += kn.size
                moved += int(m.sum())
                down += int((m & (sig**2 * tau < wn)).sum())
                not_by_quote += int((m & ~np.isclose(sig**2 * tau, quoted, rtol=1e-12, atol=0)).sum())
                core_nodes, core_moved = core_nodes + int(core.sum()), core_moved + int((m & core).sum())
                move = (sig - np.sqrt(wn / tau)) * 100
                moves.extend(move[m].tolist())
                if m.any() and np.abs(move[m]).max() > abs(worst[0]):
                    j = int(np.argmax(np.where(m, np.abs(move), -1.0)))
                    worst = (float(move[j]), f"{str(day)[:10]}, {tau * 365:.0f} days, k = {kn[j]:+.3f}, own IV "
                                             f"{np.sqrt(wn[j] / tau):.4f}, surface IV {sig[j]:.4f}")
        moves = np.array(moves) if moves else np.zeros(1)
        print(f"{source}: {len(pick)} dates, {nodes:,} nodes; moved {moved:,} ({moved / nodes:.2%}), of them down {down}, "
              f"not by a shorter expiry's quote {not_by_quote}; 0-60 days and |k| <= 0.15: {core_moved:,} of {core_nodes:,} "
              f"({core_moved / max(core_nodes, 1):.2%}); moves in vol points median {np.median(moves):.3f}, p90 "
              f"{np.quantile(moves, 0.9):.3f}, above 5 points {int((moves > 5).sum()):,}, largest {moves.max():.2f} "
              f"({worst[1]})")

    block("deep in-the-money call mids below S - K beyond 180 days (OptionsDX, valid pairs, k = ln(K/F) < -0.4)")
    below = store.query(f"""
        WITH q AS (SELECT o.quote_date, o.expiry, o.strike, o.call_put, (o.bid + o.ask) / 2 AS mid, o.spy_close
                   FROM option_quotes o WHERE o.source = 'optionsdx' AND o.expiry - o.quote_date > 180
                         AND o.quality_flags & {build.NOT_VALID} = 0 AND o.ask > 0)
        SELECT count(*) AS pairs, count(*) FILTER (c.mid < c.spy_close - c.strike) AS below,
               count(*) FILTER (c.mid < c.spy_close - c.strike - 0.05) AS below_5c,
               count(*) FILTER (c.mid < c.spy_close - c.strike - 0.001 * c.spy_close) AS below_10bp,
               quantile_cont(c.spy_close - c.strike - c.mid, 0.5) FILTER (c.mid < c.spy_close - c.strike) AS median_short,
               quantile_cont(c.spy_close - c.strike - c.mid, 0.9) FILTER (c.mid < c.spy_close - c.strike) AS p90_short
        FROM q c JOIN q p ON c.quote_date = p.quote_date AND c.expiry = p.expiry AND c.strike = p.strike
                          AND c.call_put = 'C' AND p.call_put = 'P'
        JOIN expiry_forwards f ON f.source = 'optionsdx' AND f.quote_date = c.quote_date AND f.expiry = c.expiry
        WHERE f.method IN ('parity_median5_deam', 'parity_median5_raw') AND ln(c.strike / f.forward) < -0.4""")
    b = below.iloc[0]
    print(f"{int(b['below']):,} of {int(b['pairs']):,} deep ITM call mids are below S - K (no American model prices "
          f"them: exercising would pay more); short by a median ${b['median_short']:.3f}, p90 ${b['p90_short']:.3f}; "
          f"by more than $0.05: {int(b['below_5c']):,}; by more than 0.10% of S: {int(b['below_10bp']):,} "
          f"({b['below_10bp'] / b['pairs']:.2%} of the pairs)")

    block("ADR-0008 test 8 and its 60-day case (synthetic, N = 2,000 truth)")
    for label, case in (("r 5.22%, 29 days, D at 1 day, sigma 0.12", (0.0521594, 29, 1, 0.12, np.arange(418.0, 468.0))),
                        ("r 0.25%, the same chain", (0.0025, 29, 1, 0.12, np.arange(418.0, 468.0))),
                        ("r 5%, 60 days, D at 30 days, sigma 0.20", (0.05, 60, 30, 0.20, np.arange(410.0, 476.0)))):
        (with_bp, with_iv, _, _), (without_bp, without_iv, _, _) = synthetic(*case)
        print(f"{label}: with §3a F {with_bp:+.3f} bp, max IV error {with_iv:.4f} vol pts; without {without_bp:+.3f} bp, "
              f"{without_iv:.4f}")

    block("the 60-day case by the procedure's step count (truth N = 2,000)")
    for steps in (200, 500, 1000, 2000):
        (bp, iv_pts, _, _), _ = synthetic(0.05, 60, 30, 0.20, np.arange(410.0, 476.0), procedure_steps=steps)
        print(f"procedure N = {steps}: F {bp:+.3f} bp, max OTM IV error {iv_pts:.4f} vol points")

    block("clean long-dated American chains (D 1.638367 at 1 day or every 91 days from 1 day, $2 strikes 332-574, "
          "N = 2,000 truth, procedure N = 200)")
    worst = 0.0
    for kind, rate, days, sigma in CLEAN_CHAINS + [STILL_FAILING_CHAIN]:
        when = np.arange(1, days, 91) if kind == "quarterly" else [1]
        (bp, iv_pts, outliers, n, partner, fail, fail_tiny), (raw_bp, _, raw_outliers, _, _, _, _) = synthetic(
            rate, days, when, sigma, np.arange(332.0, 575.0, 2.0), with_partner=True)
        (own_bp, _, own_outliers, _, _, _, _), _ = synthetic(rate, days, when, sigma, np.arange(332.0, 575.0, 2.0),
                                                              truth_steps=lattice.DEAM_TREE_STEPS, with_partner=True)
        if (kind, rate, days, sigma) != STILL_FAILING_CHAIN:
            worst = max(worst, abs(bp))
        print(f"{'STILL FAILING: ' if (kind, rate, days, sigma) == STILL_FAILING_CHAIN else ''}"
              f"r {rate:.4f}, {days} days, sigma {sigma:.2f}, {len(when)} dividend(s): F {bp:+.3f} bp, PARITY_OUTLIER "
              f"{outliers}/{n}, IV_FAIL {fail} (and {fail_tiny} below half a tick), max OTM IV error {iv_pts:.4f} vol "
              f"pts, premium at the partner's IV {partner}; truth on N = 200: F {own_bp:+.4f} bp, {own_outliers} "
              f"flagged; without de-Americanisation F {raw_bp:+.1f} bp, PARITY_OUTLIER {raw_outliers}/{n}")
    print(f"largest |F error| over the {len(CLEAN_CHAINS)} listed chains {worst:.3f} bp")

    block("the sigma 0.08 chain by the procedure's step count (r 5.22%, 700 days, one dividend, truth N = 2,000)")
    for steps in (200, 500, 1000):
        (bp, iv_pts, outliers, n, _, fail, _), _ = synthetic(0.0521594, 700, [1], 0.08, np.arange(332.0, 575.0, 2.0),
                                                              procedure_steps=steps, with_partner=True)
        print(f"procedure N = {steps}: F {bp:+.3f} bp, PARITY_OUTLIER {outliers}/{n}, IV_FAIL {fail}, max OTM IV error "
              f"{iv_pts:.4f} vol points")

    block("IV solver accuracy (random Black-76 prices, F = 442, r -1% to 7%)")
    rng = np.random.default_rng(29)
    for label, n, k_range, s_range, t_range, side in (
            ("sigma 0.01-4, tau 1 day-3 years, OTM", 200000, (-1.0, 0.6), (0.01, 4.0), (1 / 365, 3.0), "otm"),
            ("the same, ITM", 200000, (-1.0, 0.6), (0.01, 4.0), (1 / 365, 3.0), "itm"),
            ("sigma 0.5-2.4, tau 1-30 years, OTM calls near the upper bound", 20000, (0.0, 0.5), (0.5, 2.4), (1.0, 30.0), "call")):
        k, tau = rng.uniform(*k_range, n), np.exp(rng.uniform(np.log(t_range[0]), np.log(t_range[1]), n))
        sigma = np.exp(rng.uniform(np.log(s_range[0]), np.log(s_range[1]), n))
        rate, strike = rng.uniform(-0.01, 0.07, n), 442.0 * np.exp(k)
        call = (k >= 0) if side == "otm" else (k < 0) if side == "itm" else np.ones(n, bool)
        price = black76.price(442.0, strike, tau, rate, sigma, call)
        lower, upper = black76.price_bounds(442.0, strike, tau, rate, call)
        out = ivm.implied_vol(price, 442.0, strike, tau, rate, call)
        ok = out["fail"] == ivm.FAIL_NONE
        err = np.abs(out["iv"][ok] / sigma[ok] - 1)
        down = black76.price(442.0, strike, tau, rate, sigma * (1 - 1e-6), call)
        up = black76.price(442.0, strike, tau, rate, sigma * (1 + 1e-6), call)
        resolvable = (down < price) & (price < up) & (price > lower) & (price < upper)
        unresolved = out["fail"] == ivm.FAIL_UNRESOLVED
        print(f"{label}: {n:,} cases, solved {int(ok.sum()):,}; relative sigma error max {err.max():.2e}, above 1e-10 "
              f"{int((err > 1e-10).sum()):,}, above 1e-8 {int((err > 1e-8).sum()):,}, above 1e-6 {int((err > 1e-6).sum()):,}; "
              f"unresolved {int(unresolved.sum()):,}, of them pinned to 1e-6 by the float price {int((unresolved & resolvable).sum()):,}")

    block("dividend projection rules, SPY ex-dates since 2009 (no look-ahead)")
    for name, err in dividend_rules(store).items():
        print(f"{name}: {err.size} ex-dates, mean absolute error {np.mean(np.abs(err)):.2%}, largest {np.max(np.abs(err)):.1%}, "
              f"mean signed {np.mean(err):+.2%}")

    block("theta: F held fixed against S held fixed (one long ATM call, S = K = 400, sigma 0.20, 30 days, r 5%)")
    spot, strike, tau, rate, sigma = 400.0, 400.0, 30 / 365, 0.05, 0.20
    forward = spot * np.exp(rate * tau)
    held_f = float(black76.greeks_usd(1, spot, forward, strike, tau, rate, sigma, True)["theta_1d_usd"])
    day = 1 / 365
    later = float(black76.price(spot * np.exp(rate * (tau - day)), strike, tau - day, rate, sigma, True))
    earlier = float(black76.price(spot * np.exp(rate * (tau + day)), strike, tau + day, rate, sigma, True))
    held_s = (later - earlier) / 2 * 100
    now = float(black76.price(forward, strike, tau, rate, sigma, True))
    one_day = (later - now) * 100
    d1, _ = black76.d1_d2(forward, strike, tau, sigma)
    analytic = (float(black76.greeks(spot, forward, strike, tau, rate, sigma, True)["theta"])
                - float(np.exp(-rate * tau) * black76.ndtr(d1)) * rate * forward) / 365 * 100
    print(f"theta_1d_usd with F fixed {held_f:+.2f}; with S fixed {analytic:+.2f} (analytic: theta_F - DF N(d1) r F), "
          f"{held_s:+.2f} (central difference over one day), {one_day:+.2f} (one day forward, the review's figure); the gap "
          f"{held_f - analytic:+.2f} per contract per day lands in ADR-0005's attribution residual unless M6 attributes it")

    block("the 420 put at 5% (ADR-0003 test 7)")
    decision = exercise.put_early_exercise(420.0, 450.0, 0.05, 0.20, 30 / 365)
    fires, lhs, rhs = exercise.put_prefilter(420.0, 450.0, 0.05, 0.20, 30 / 365)
    print(f"S = 420: exercise {decision['exercise']}, waiting worth {decision['margin']:.4f} more (N = 500); the "
          f"textbook inequality {lhs:.4f} > {rhs:.4f} fires: {fires}")
    print(f"exercise optimal below S = {boundary(450.0, 0.05, 0.20, 30 / 365, 0.0):.2f}; the rule with its $0.005 tolerance "
          f"fires below S = {boundary(450.0, 0.05, 0.20, 30 / 365, exercise.EXERCISE_TOL):.2f}")

    block("the premium in vol points at z = k / (sigma sqrt tau) = -3, r 5.5%, a $1.70 dividend every 91 days")
    spot, rate = 440.0, 0.055
    for days in (90, 180, 365, 730):
        tau = days / 365
        when = np.arange(30, days + 1, 91) / 365
        values = []
        for sigma in (0.10, 0.15, 0.20, 0.30, 0.45):
            pv = (1.7 * np.exp(-rate * when)).sum()
            fwd = (spot - pv) * np.exp(rate * tau)
            k = fwd * np.exp(-3 * sigma * np.sqrt(tau))
            premium = lattice.early_exercise_premium(spot, k, tau, rate, sigma, False, [when], [np.full(when.size, 1.7)])
            values.append(float(premium[0] / black76.vega(fwd, k, tau, rate, sigma) * 100))
        print(f"{days} days: sigma 0.10-0.45 -> " + ", ".join(f"{v:.3f}" for v in values) + " vol pts")

    block("data flow: OptionsDX 2023-06-15, SPY 440 put expiring 2023-07-14")
    quote = store.query("""
        SELECT o.bid, o.ask, o.quality_flags, o.spy_close, o.vendor_iv, q.log_moneyness, q.is_otm, q.in_smile, q.iv_raw,
               q.iv_american, q.eep, q.iv, q.solver, q.iterations
        FROM option_quotes o JOIN quote_iv q USING (source, year, quote_date, osi_symbol)
        WHERE o.source = 'optionsdx' AND o.quote_date = '2023-06-15' AND o.osi_symbol = 'SPY   230714P00440000'""").iloc[0]
    expiry = store.query("""SELECT * FROM expiry_forwards WHERE source = 'optionsdx' AND quote_date = '2023-06-15'
                            AND expiry = '2023-07-14'""").iloc[0]
    smile_row = store.query("""SELECT n_points, atm_iv, fit_flags FROM smile_fits WHERE source = 'optionsdx'
                               AND quote_date = '2023-06-15' AND expiry = '2023-07-14'""").iloc[0]
    neighbour = store.query("""SELECT q.iv FROM quote_iv q WHERE q.source = 'optionsdx' AND q.quote_date = '2023-06-15'
                               AND q.osi_symbol = 'SPY   230714C00443000'""").iloc[0]
    day_quotes = store.query("SELECT count(*) AS n FROM option_quotes WHERE source = 'optionsdx' AND quote_date = '2023-06-15'")
    year_quotes = store.query("SELECT count(*) AS n FROM option_quotes WHERE source = 'optionsdx' AND year = '2023'")
    rate_row = store.query("SELECT date, dgs3mo_pct, r_cc FROM rates WHERE date < '2023-06-15' ORDER BY date DESC LIMIT 1").iloc[0]
    sched = dividends.schedule([d.date() for d in store.read_table("dividends", order_by="ex_date")["ex_date"]],
                               store.read_table("dividends", order_by="ex_date")["amount"].tolist(), date(2023, 6, 15),
                               date(2023, 7, 14), [d.date() for d in store.read_table("spy_bars", order_by="date")["date"]])
    paid = store.read_table("dividends", order_by="ex_date")
    june = float(paid[paid["ex_date"] == "2023-06-16"]["amount"].iloc[0])
    paid = paid[(paid["ex_date"] > "2021-06-01") & (paid["ex_date"] <= "2023-06-15")]["amount"].tolist()
    print(f"the June 2023 amount: June 2022's {paid[-4]} x trailing growth {sum(paid[-4:]) / sum(paid[-8:-4]):.4f} = "
          f"{paid[-4] * sum(paid[-4:]) / sum(paid[-8:-4]):.4f}; last paid {paid[-1]}; SPY paid {june}")
    print(f"2023 partition {int(year_quotes['n'][0]):,} quotes; the date {int(day_quotes['n'][0]):,}; rate DGS3MO "
          f"{rate_row['dgs3mo_pct']} dated {rate_row['date'].date()} -> r {rate_row['r_cc']:.6f}; dividends {sched}")
    print(f"quote: bid {quote['bid']}, ask {quote['ask']}, flags {quote['quality_flags']}, SPY {quote['spy_close']}, vendor IV "
          f"{quote['vendor_iv']:.5f}")
    print(f"expiry: pairs {expiry['n_pairs_valid']}, forward_raw {expiry['forward_raw']:.4f}, forward {expiry['forward']:.4f} "
          f"({(expiry['forward'] / expiry['forward_raw'] - 1) * 1e4:+.2f} bp), carry {expiry['forward_carry']:.4f} (F "
          f"{(expiry['forward'] / expiry['forward_carry'] - 1) * 1e4:+.2f} bp from it), K* {expiry['k_star']}, F_K slope "
          f"{expiry['fk_slope_per_strike']:+.4f}, de-Americanised quotes {expiry['n_deamericanised']}, method {expiry['method']}")
    print(f"the put: k {quote['log_moneyness']:+.4f}, OTM {quote['is_otm']}, in the smile {quote['in_smile']}, iv_raw "
          f"{quote['iv_raw']:.4f}, American IV {quote['iv_american']:.4f}, premium {quote['eep']:.4f}, iv {quote['iv']:.4f} "
          f"({quote['solver']}, {quote['iterations']} steps); the 443 call iv {neighbour['iv']:.4f}; the smile: "
          f"{smile_row['n_points']} nodes, ATM IV {smile_row['atm_iv']:.4f}, fit_flags {smile_row['fit_flags']}")

    block("the dividend drop's timing (OptionsDX 2023-03-16, SPY 400 call expiring 2023-03-17, the ex-date)")
    from volbt.pricing import deam as deam_module

    reference = build.reference_inputs(store)
    day, expiry = date(2023, 3, 16), date(2023, 3, 17)
    call = store.query("SELECT bid, ask, spy_close FROM option_quotes WHERE source = 'optionsdx' AND quote_date = ? "
                       "AND expiry = ? AND strike = 400 AND call_put = 'C'", [day, expiry])
    mid, spot, rate = float((call["bid"] + call["ask"]).iloc[0] / 2), float(call["spy_close"].iloc[0]), build.rate_on(reference, day)
    times, amounts = dividends.schedule(reference["ex_dates"], reference["amounts"], day, expiry, reference["sessions"])
    tau = (expiry - day).days / 365
    after = deam_module.american_iv([mid], spot, [400.0], [tau], rate, [True], [times], [amounts])
    at_ex = deam_module.american_iv([mid], spot, [400.0], [tau], rate, [True], [[tau]], [amounts])
    at_ex_sigma = lattice.early_exercise_premium(spot, 400.0, tau, rate, after["iv"], True, [[tau]], [amounts])
    print(f"mid {mid:.3f}, S {spot:.2f}, D {amounts[0]:.4f}: drop just after today's close (the build) American IV "
          f"{after['iv'][0]:.4f}, premium {after['premium'][0]:.4f}; drop at the ex-date's time (the first version) "
          f"American IV {at_ex['iv'][0]:.4f}, premium {at_ex['premium'][0]:.4f}, and {at_ex_sigma[0]:.4f} at the build's IV")

    block("the real snapshots of code claim 12 (OptionsDX 2019-03-14 and 2023-06-15)")
    for day in ("2019-03-14", "2023-06-15"):
        counts = store.query(f"""SELECT {build.TENOR} AS tenor, count(*) AS quotes,
                                        count(*) FILTER (iv_flags & 2 <> 0) AS outliers, count(iv) AS ivs
                                 FROM quote_iv WHERE source = 'optionsdx' AND quote_date = ? AND expiry > quote_date
                                 GROUP BY ALL ORDER BY tenor""", [day])
        fwd = store.query(f"""SELECT count(*) AS n, max(abs(forward / forward_carry - 1)) * 1e4 AS worst
                              FROM expiry_forwards WHERE source = 'optionsdx' AND quote_date = ? AND tau_years > 0
                              AND expiry - quote_date <= 60""", [day]).iloc[0]
        print(f"{day}: " + "; ".join(f"{r.tenor} {r.quotes:,} quotes, {r.ivs:,} IVs, {r.outliers} PARITY_OUTLIER"
                                     for r in counts.itertuples(index=False))
              + f"; {int(fwd['n'])} expiries within 60 days, the farthest {fwd['worst']:.2f} bp from its carry forward")

    block("the rate's date: DGS3MO dated strictly before the quote date, against dated on it (OptionsDX 2023-03-20)")
    import pandas as pd

    reference = build.reference_inputs(store)
    day = date(2023, 3, 20)
    quotes = store.query(f"SELECT {build.QUOTE_COLUMNS} FROM option_quotes WHERE source = 'optionsdx' AND year = '2023' "
                         "AND quote_date = ? ORDER BY quote_date, osi_symbol", [day])
    quotes["quote_date"] = pd.to_datetime(quotes["quote_date"]).dt.date
    quotes["expiry"] = pd.to_datetime(quotes["expiry"]).dt.date
    before = build.price_snapshot(quotes, day, reference)
    on_day = dict(reference)
    on_day["rate_days"] = reference["rate_days"] - np.timedelta64(1, "D")    # a value dated t now counts for t
    same_day = build.price_snapshot(quotes, day, on_day)
    near = np.asarray(before["expiry_forwards"]["tau_years"]) * 365 <= 60
    shift = np.abs(np.asarray(same_day["expiry_forwards"]["forward"]) / np.asarray(before["expiry_forwards"]["forward"]) - 1)[near]
    short = np.array([(e - day).days <= 60 for e in quotes["expiry"]])
    iv_shift = np.abs(np.asarray(same_day["quote_iv"]["iv"]) - np.asarray(before["quote_iv"]["iv"]))[short]
    print(f"r {before['expiry_forwards']['r_cc'][0]:.6f} (dated before) against {same_day['expiry_forwards']['r_cc'][0]:.6f} "
          f"(dated on the day); 0-60 days: forwards move up to {np.nanmax(shift) * 1e4:.2f} bp, IVs up to "
          f"{np.nanmax(iv_shift) * 100:.4f} vol points")

    block("the American IV solve's cost: lattice walks per quote (OptionsDX 2019-03-14 and 2023-06-15, the OTM quotes with a mid)")
    from volbt.pricing import deam

    for day in (date(2019, 3, 14), date(2023, 6, 15)):
        quotes = store.query(f"SELECT {', '.join('o.' + c.strip() for c in build.QUOTE_COLUMNS.split(','))} FROM option_quotes o "
                             "JOIN quote_iv q USING (source, year, quote_date, osi_symbol) WHERE o.source = 'optionsdx' AND "
                             "o.year = ? AND o.quote_date = ? AND q.is_otm ORDER BY o.quote_date, o.osi_symbol", [str(day.year), day])
        quotes["expiry"] = pd.to_datetime(quotes["expiry"]).dt.date
        bits = quotes["quality_flags"].to_numpy(np.int64)
        keep = ((bits & build.NO_MID) == 0) & (quotes["ask"].to_numpy(float) > 0) & (quotes["expiry"] > day).to_numpy()
        quotes = quotes[keep]
        schedules = [dividends.schedule(reference["ex_dates"], reference["amounts"], day, e, reference["sessions"])
                     for e in quotes["expiry"]]
        width = max(len(t) for t, _ in schedules)
        times, amounts = np.zeros((len(quotes), width)), np.zeros((len(quotes), width))
        for row, (t, a) in enumerate(schedules):
            times[row, :len(t)], amounts[row, :len(a)] = t, a
        got = deam.american_iv(((quotes["bid"] + quotes["ask"]) / 2).to_numpy(float), float(quotes["spy_close"].iloc[0]),
                               quotes["strike"].to_numpy(float), np.array([(e - day).days / 365 for e in quotes["expiry"]]),
                               build.rate_on(reference, day), (quotes["call_put"] == "C").to_numpy(), times, amounts)
        walks = got["walks"].astype(int)
        print(f"{day}: {len(quotes):,} quotes; walks mean {walks.mean():.2f}, by count " +
              ", ".join(f"{n}: {c:,}" for n, c in enumerate(np.bincount(walks)) if c))

    block("the surface frames")
    if args.frames.is_file():
        written = json.loads(args.frames.read_text(encoding="utf-8"))
        dte = np.array(written["grid_dte"], dtype=float)[:, None]
        for frame in written["frames"]:
            iv = np.array(frame["iv"])
            flags = np.array(frame["cell_flags"])
            falls = int((np.diff(iv * iv * dte / 365, axis=0) < 0).sum())
            print(f"{frame['date']} (VIX {frame['vix_close']}): 30-day ATM IV {frame['atm_iv_30d']:.4f}, quoted share "
                  f"{frame['quoted_share']:.3f}, {frame['expiries_used']} expiries; moved by the calendar constraint {int(((flags & 8) != 0).sum())} "
                  f"of {flags.size} cells; cells where w falls with tenor {falls}")
        print(f"{args.frames.name}: {args.frames.stat().st_size:,} bytes; run data_fingerprint {written['run']['data_fingerprint']}, "
              f"config_hash {written['run']['config_hash']}")
    else:
        print(f"no {args.frames}: run tools/export_app_data.py")

    block("build time")
    seconds = sorted(timings["partitions"], key=lambda r: -r["seconds"])
    print(f"total {timings['total_seconds']} s with {timings['workers']} workers, finished {timings['finished_at']}; "
          f"{len(seconds)} partitions priced"
          + (f"; slowest {seconds[0]['source']}/{seconds[0]['year']} {seconds[0]['seconds']} s for {seconds[0]['quotes']:,} quotes"
             if seconds else ": nothing re-priced"))
    for row in seconds:
        print(f"  {row['source']}/{row['year']}: {row['quotes']:,} quotes in {row['seconds']} s")
    logs = sorted((store.root.parent / "logs").glob("pricing_timings_*.json"))
    for kept in logs:
        record = json.loads(kept.read_text(encoding="utf-8"))
        print(f"kept {kept.name}: {record['total_seconds']} s, {len(record['partitions'])} partitions, {record['workers']} workers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
