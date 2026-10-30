"""The M2 pricing build (volbt.build): partitioned, incremental, byte-deterministic, and right.

The store is tests/pricing_store.py's made-up American chain, whose true forward and smile are
known, so the build's output can be checked against the answer it should find.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pyarrow
import pytest
import scipy

import pricing_store
from volbt import build
from volbt.data import store as store_module
from volbt.data.store import Store


def digest(root):
    """{relative path: SHA-256} of every pricing output file under a store root (not the timings)."""
    files = [p for name in build.PRICING_TABLES for p in sorted((root / name).rglob("*.parquet"))]
    files += [root / build.SUMMARY_FILE, root / build.INPUTS_FILE]
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    store = pricing_store.make_store(tmp_path_factory.mktemp("pricing"))
    summary = build.build_pricing(store)
    return store, summary


def test_three_tables_partitioned_by_source_and_year(built):
    store, _ = built
    expected = [{"source": "dolthub", "year": "2023"}, {"source": "optionsdx", "year": "2022"},
                {"source": "optionsdx", "year": "2023"}]
    for name in build.PRICING_TABLES:
        assert store.partitions(name) == expected


def test_quote_iv_has_exactly_one_row_per_quote(built):
    store, _ = built
    joined = store.query("""SELECT count(*) AS quotes, count(q.osi_symbol) AS priced FROM option_quotes o
                            LEFT JOIN quote_iv q USING (source, quote_date, osi_symbol)""")
    assert joined["quotes"][0] == joined["priced"][0] == len(store.read_table("quote_iv", order_by="osi_symbol"))
    dupes = store.query("SELECT count(*) - count(DISTINCT (source, quote_date, osi_symbol)) AS d FROM quote_iv")
    assert dupes["d"][0] == 0


def test_one_forward_and_one_smile_per_listed_expiry(built):
    store, _ = built
    listed = store.query("SELECT count(DISTINCT (source, quote_date, expiry)) AS n FROM option_quotes")["n"][0]
    for name in ("expiry_forwards", "smile_fits"):
        assert len(store.read_table(name, order_by="source, quote_date, expiry")) == listed


def test_forwards_recover_the_true_forward_of_the_american_chain(built):
    store, _ = built
    rows = store.query("SELECT quote_date, expiry, forward, method FROM expiry_forwards WHERE tau_years > 0 "
                       "ORDER BY source, quote_date, expiry")
    for row in rows.itertuples(index=False):
        day, expiry = row.quote_date.date(), row.expiry.date()
        truth, _, _ = pricing_store.true_forward(day, expiry, pricing_store.SPOT[day], pricing_store.rate_on(day))
        assert row.method == "parity_median5_deam"
        # Cent-rounded quotes with a 2-cent spread, and last-paid dividends at projected dates in
        # the lattice: within 1 bp of the truth.
        assert abs(row.forward / truth - 1) < 1e-4, (day, expiry, row.forward, truth)


def test_otm_ivs_recover_the_smile(built):
    store, _ = built
    rows = store.query("SELECT log_moneyness, iv FROM quote_iv WHERE iv IS NOT NULL ORDER BY source, quote_date, osi_symbol")
    truth = pricing_store.smile_sigma(rows["log_moneyness"].to_numpy())
    assert np.max(np.abs(rows["iv"].to_numpy() - truth)) < 0.003     # 0.3 vol points: cent rounding on short expiries
    assert np.median(np.abs(rows["iv"].to_numpy() - truth)) < 0.0003


def test_the_crossed_quote_is_left_out_of_the_forward_and_the_smile(built):
    store, _ = built
    day, expiry = pricing_store.CROSSED_DATE, pricing_store.CROSSED_EXPIRY
    forward = store.query("SELECT n_pairs_valid FROM expiry_forwards WHERE source = 'optionsdx' AND quote_date = ? "
                          "AND expiry = ?", [day, expiry])
    dolthub = store.query("SELECT n_pairs_valid FROM expiry_forwards WHERE source = 'dolthub' AND quote_date = ? "
                          "AND expiry = ?", [day, expiry])
    assert forward["n_pairs_valid"][0] == dolthub["n_pairs_valid"][0] - 1
    smiles = store.query("SELECT source, n_points FROM smile_fits WHERE quote_date = ? AND expiry = ? ORDER BY source",
                         [day, expiry])
    assert smiles["n_points"].tolist() == [13, 12]                    # dolthub, optionsdx
    quote = store.query("SELECT iv, iv_flags, iv_fail_reason FROM quote_iv WHERE source = 'optionsdx' AND "
                        "quote_date = ? AND osi_symbol = 'SPY   230714P00438000'", [day])
    assert pd.isna(quote["iv"][0]) and quote["iv_flags"][0] == 0 and pd.isna(quote["iv_fail_reason"][0])


def test_the_expiry_day_rows(built):
    store, _ = built
    rows = store.query("SELECT method, forward, spot FROM expiry_forwards WHERE tau_years = 0 ORDER BY source")
    assert rows["method"].tolist() == ["expiry_day", "expiry_day"] and (rows["forward"] == rows["spot"]).all()
    ivs = store.query("SELECT count(iv) AS n, count(*) AS rows FROM quote_iv WHERE expiry = quote_date")
    assert ivs["n"][0] == 0 and ivs["rows"][0] == 52


def test_the_summary_counts(built):
    _, summary = built
    pooled = {row["source"]: row for row in summary["quotes"] if row["year"] is None and row["tenor"] is None}
    # 3 dates x 3 expiries x 13 OTM quotes, less the crossed put (no mid). Every one is valid and
    # in its smile here: no zero bid, nothing stale.
    assert pooled["optionsdx"]["otm_attempted"] == pooled["optionsdx"]["solved"] == 3 * 3 * 13 - 1
    assert pooled["optionsdx"]["otm_valid"] == pooled["optionsdx"]["in_smile"] == 3 * 3 * 13 - 1
    assert pooled["optionsdx"]["iv_fail"] == 0 and pooled["dolthub"]["solved"] == 3 * 13
    assert all(row["parity_outlier"] == 0 and row["forward_fallback"] == 0 for row in summary["quotes"])
    assert all(row["parity_raw"] == 0 for row in summary["forwards"])


def test_the_summary_counts_a_wide_quote_as_valid_but_not_smile_ok(tmp_path):
    # Round 4 (finding N-B): the made-up store has no WIDE quote, so the reviewer's mutant R4-F2a (the
    # summary's smile_ok on NOT_VALID, a WIDE quote counted as smile-ok) survived the default suite. One
    # OTM put of optionsdx 2023-06-15 made WIDE (bid 0.05, the ask moved so the mid stays): it is valid
    # and solved, and neither smile-ok nor in the smile.
    from volbt.data import flags as quality

    store = pricing_store.make_store(tmp_path / "wide")
    part = {"source": "optionsdx", "year": "2023"}
    quotes = pd.read_parquet(store.partition_file("option_quotes", part))
    put = (pd.to_datetime(quotes["quote_date"]) == pd.Timestamp(2023, 6, 15)) & \
        (quotes["osi_symbol"] == "SPY   230714P00418000")
    mid = float((quotes.loc[put, "bid"] + quotes.loc[put, "ask"]).iloc[0] / 2)
    bid, ask = 0.05, round(2 * mid - 0.05, 2)
    bits = int(quality.mid_flags(quality.cents([bid]), quality.cents([ask]))[0])
    assert put.sum() == 1 and bits == quality.WIDE
    quotes.loc[put, ["bid", "ask", "quality_flags"]] = [bid, ask, bits]
    store.write_partition("option_quotes", quotes, part, sort_by=("quote_date", "osi_symbol"))
    summary = build.build_pricing(store)
    pooled = [row for row in summary["quotes"] if row["source"] == "optionsdx" and row["year"] is None
              and row["tenor"] is None][0]
    assert pooled["otm_valid"] == pooled["solved"] == 3 * 3 * 13 - 1 and pooled["otm_valid_wide"] == 1
    assert pooled["otm_smile_ok"] == pooled["in_smile"] == pooled["otm_valid"] - 1


def test_the_summary_tenor_buckets_have_their_edges_in_the_right_bucket(tmp_path):
    # Expiries 0, 60, 61, 180 and 181 days out, 26 quotes each: 60 is in 0-60, 180 in 61-180, and
    # the expiry day is in no bucket (code mutants M18 and M21).
    store = pricing_store.make_tenor_store(tmp_path / "tenor")
    summary = build.build_pricing(store)
    per_tenor = {row["tenor"]: row["quotes"] for row in summary["quotes"] if row["year"] is None and row["tenor"]}
    assert per_tenor == {"0-60": 26, "61-180": 52, "181+": 26}
    pooled = [row for row in summary["quotes"] if row["year"] is None and row["tenor"] is None]
    assert pooled[0]["quotes"] == 4 * 26
    forwards = {row["tenor"]: row["expiries"] for row in summary["forwards"] if row["year"] is None and row["tenor"]}
    assert forwards == {"0-60": 1, "61-180": 2, "181+": 1}


def test_two_builds_give_identical_bytes(built, tmp_path):
    store, _ = built
    again = pricing_store.make_store(tmp_path / "again")
    build.build_pricing(again)
    assert digest(again.root) == digest(store.root)
    assert len(digest(store.root)) == 3 * 3 + 2


def test_a_parallel_build_equals_a_serial_one(built, tmp_path):
    store, _ = built
    parallel = pricing_store.make_store(tmp_path / "parallel")
    build.build_pricing(parallel, workers=3)
    assert digest(parallel.root) == digest(store.root)


def test_an_unchanged_partition_is_skipped_and_a_changed_one_rebuilt(tmp_path):
    store = pricing_store.make_store(tmp_path / "incremental")
    build.build_pricing(store)
    before = digest(store.root)
    build.build_pricing(store)
    timings = store.root / build.TIMINGS_FILE
    assert json.loads(timings.read_text())["partitions"] == []
    assert digest(store.root) == before
    # Change one quote of optionsdx/2022: only that partition is priced again.
    quotes = store.read_table("option_quotes", order_by="source, quote_date, osi_symbol")
    part = quotes[quotes["year"] == "2022"].drop(columns=["source", "year"]).copy()
    part.loc[part.index[0], "ask"] += 0.01
    store.write_partition("option_quotes", part, {"source": "optionsdx", "year": "2022"}, ("quote_date", "osi_symbol"))
    build.build_pricing(store)
    rebuilt = json.loads(timings.read_text())["partitions"]
    assert [(r["source"], r["year"]) for r in rebuilt] == [("optionsdx", "2022")]
    after = digest(store.root)
    assert after["quote_iv/source=dolthub/year=2023/part-0.parquet"] == before["quote_iv/source=dolthub/year=2023/part-0.parquet"]


def test_force_rebuilds_everything_to_the_same_bytes(tmp_path):
    store = pricing_store.make_store(tmp_path / "force")
    build.build_pricing(store)
    before = digest(store.root)
    shutil.rmtree(store.table_dir("smile_fits") / "source=dolthub")     # a missing output is rebuilt too
    build.build_pricing(store, force=True)
    assert digest(store.root) == before


def test_surface_frames_body(built):
    store, _ = built
    body = build.surface_frames_body(store, [(date(2023, 6, 15), "made-up date")])
    assert body["grid_moneyness"][0] == -0.3 and body["grid_moneyness"][-1] == 0.2 and len(body["grid_moneyness"]) == 26
    assert body["grid_dte"] == list(build.GRID_DTE)
    frame = body["frames"][0]
    assert frame["label"] == "made-up date" and frame["spot"] == 442.6 and frame["vix_close"] == 13.6
    assert frame["expiries_used"] == 3                     # the expiry-day smile has no nodes
    iv = np.array(frame["iv"])
    assert iv.shape == (11, 26) and np.all(np.isfinite(iv)) and np.all(iv > 0)
    # The smile's own ATM vol is 0.18, so the 30-day ATM IV (between the 15- and 29-day expiries) is too.
    assert frame["atm_iv_30d"] == pytest.approx(0.18, abs=0.003)
    assert 0 < frame["quoted_share"] < 1
    flags = np.array(frame["cell_flags"])
    # 7 days is shorter than the 15-day front expiry: tenor extrapolation on that whole row.
    assert np.all(flags[0] & 4) and body["cell_flag_names"][2] == "SURFACE_EXTRAP_TENOR"


def test_surface_frames_refuses_a_date_without_smiles(built):
    store, _ = built
    with pytest.raises(ValueError, match="no usable smile"):
        build.surface_frames_body(store, [(date(2023, 6, 16), "no data")])


def test_write_partition_leaves_the_other_partitions_alone(tmp_path):
    store = Store(tmp_path)
    frame = pd.DataFrame({"source": ["a", "a", "b"], "year": [1, 2, 1], "x": [3, 2, 1]})
    store.write_table("t", frame, sort_by=("x",), partition_by=("source", "year"))
    other = (store.table_dir("t") / "source=b" / "year=1" / "part-0.parquet").read_bytes()
    store.write_partition("t", pd.DataFrame({"x": [9, 8]}), {"source": "a", "year": 1}, ("x",))
    assert (store.table_dir("t") / "source=b" / "year=1" / "part-0.parquet").read_bytes() == other
    back = store.read_table("t", order_by="source, year, x")
    assert back["x"].tolist() == [8, 9, 2, 1]


def snapshot_rows():
    """One made-up expiry, 9 strikes, European mids at sigma 0.20 on F = 400.66: a zero-bid OTM put
    at 380 and a stale OTM call at 420 (flags as option_quotes carries them)."""
    from volbt.data import flags as quality
    from volbt.data.osi import osi_symbol
    from volbt.pricing import black76

    day, expiry = date(2023, 6, 14), date(2023, 7, 14)
    rate = 0.05
    tau = (expiry - day).days / 365
    forward = 400.0 * np.exp(rate * tau)
    rows = []
    for strike in range(380, 425, 5):
        for call_put in ("C", "P"):
            mid = float(black76.price(forward, strike, tau, rate, 0.20, call_put == "C"))
            bid, ask, bits = round(mid - 0.01, 2), round(mid + 0.01, 2), 0
            if (strike, call_put) == (380, "P"):
                bid, ask, bits = 0.0, 0.10, quality.ZERO_BID
            if (strike, call_put) == (420, "C"):
                bits = quality.STALE
            rows.append({"quote_date": day, "osi_symbol": osi_symbol("SPY", expiry, call_put, strike), "expiry": expiry,
                         "strike": float(strike), "call_put": call_put, "bid": bid, "ask": ask, "spy_close": 400.0,
                         "quality_flags": bits})
    reference = {"rate_days": np.array(["2023-06-13"], dtype="datetime64[D]"), "r_cc": np.array([rate]),
                 "ex_dates": [], "amounts": [], "sessions": []}
    return pd.DataFrame(rows), day, reference


def test_a_zero_bid_or_stale_quote_gets_an_iv_but_enters_neither_the_forward_nor_the_smile():
    quotes, day, reference = snapshot_rows()
    out = build.price_snapshot(quotes, day, reference)
    assert int(out["expiry_forwards"]["n_pairs_valid"][0]) == 7          # 9 strikes less 380 and 420
    assert out["smile_fits"]["n_points"] == [7]                           # 9 OTM quotes less the two
    q = out["quote_iv"]
    solved = dict(zip(q["osi_symbol"], q["iv"]))
    assert np.isfinite(solved["SPY   230714P00380000"])                  # ADR-0004 rule 2: ask/2 is still a mid
    assert np.isfinite(solved["SPY   230714C00420000"])
    # ...a descriptive IV only: in_smile says which IVs are the smile's (D6). M3 marks the two others
    # off surface_iv at their k, as it does every ITM quote.
    in_smile = dict(zip(q["osi_symbol"], q["in_smile"]))
    assert not in_smile["SPY   230714P00380000"] and not in_smile["SPY   230714C00420000"]
    otm = [sym for sym, otm in zip(q["osi_symbol"], q["is_otm"]) if otm]
    assert sum(in_smile[sym] for sym in otm) == 7 and not any(in_smile[sym] for sym in in_smile if sym not in otm)


def test_a_wide_quote_keeps_its_iv_and_its_pair_but_is_not_a_smile_node():
    # Round 3 (code finding N-1; decision F2): a WIDE quote (ask - bid > mid) was a smile node. On
    # 2014-09-15 the 11-day expiry's stub puts (bid 0.03, ask 4.84) gave IVs of 0.80-0.87 between
    # tight neighbours at 0.33-0.38 and, through the calendar constraint, lifted 13 later expiries.
    # It keeps its quote_iv row and its IV, and its strike still enters the forward's pairs; it is
    # not a node.
    from volbt.data import flags as quality

    quotes, day, reference = snapshot_rows()
    plain = build.price_snapshot(quotes, day, reference)
    put = quotes["osi_symbol"] == "SPY   230714P00390000"
    mid = float((quotes.loc[put, "bid"] + quotes.loc[put, "ask"]).iloc[0] / 2)
    quotes.loc[put, ["bid", "ask", "quality_flags"]] = [0.05, round(2 * mid - 0.05, 2), quality.WIDE]
    assert quality.mid_flags(quotes.loc[put, "bid"].to_numpy(), quotes.loc[put, "ask"].to_numpy())[0] == quality.WIDE
    out = build.price_snapshot(quotes, day, reference)
    q = out["quote_iv"]
    row = list(q["osi_symbol"]).index("SPY   230714P00390000")
    assert q["is_otm"][row] and np.isfinite(q["iv"][row]) and np.isfinite(q["eep"][row]) and not q["in_smile"][row]
    assert out["smile_fits"]["n_points"] == [plain["smile_fits"]["n_points"][0] - 1] == [6]
    assert int(out["expiry_forwards"]["n_pairs_valid"][0]) == int(plain["expiry_forwards"]["n_pairs_valid"][0]) == 7
    k390 = float(np.log(390 / out["expiry_forwards"]["forward"][0]))
    assert not np.isclose(out["smile_fits"]["k_nodes"][0], k390, rtol=0, atol=1e-9).any()


def test_a_quote_with_a_zero_ask_has_no_mid_and_no_iv_fail():
    # bid 0 and ask 0: ZERO_BID, not NO_MID, so only `ask > 0` keeps it from a mid of 0 (code mutant
    # M20: 106,485 such quotes would have been IV_FAIL "below_lower_bound").
    from volbt.data import flags as quality

    quotes, day, reference = snapshot_rows()
    put = quotes["osi_symbol"] == "SPY   230714P00385000"
    quotes.loc[put, ["bid", "ask", "quality_flags"]] = [0.0, 0.0, quality.ZERO_BID]
    q = build.price_snapshot(quotes, day, reference)["quote_iv"]
    row = list(q["osi_symbol"]).index("SPY   230714P00385000")
    assert np.isnan(q["iv"][row]) and np.isnan(q["eep"][row]) and np.isnan(q["iv_raw"][row])
    assert q["iv_flags"][row] == 0 and q["iv_fail_reason"][row] == 0 and not q["in_smile"][row]


def test_the_rate_is_the_last_one_dated_strictly_before_the_quote_date():
    # DGS3MO for day t is published after the 16:00 ET snapshot of t (H.15 at 16:15 ET on t + 1):
    # the snapshot of t may use the value of t - 1 at the latest (M2 review amendment, D3).
    reference = {"rate_days": np.array(["2023-06-13", "2023-06-14", "2023-06-16"], dtype="datetime64[D]"),
                 "r_cc": np.array([0.051, 0.052, 0.053])}
    assert build.rate_on(reference, date(2023, 6, 14)) == 0.051
    assert build.rate_on(reference, date(2023, 6, 15)) == 0.052
    assert build.rate_on(reference, date(2023, 6, 16)) == 0.052
    with pytest.raises(ValueError, match="no DGS3MO rate"):
        build.rate_on(reference, date(2023, 6, 13))


def test_a_change_in_the_pricing_code_reprices_every_partition(tmp_path):
    # A real edit to a fingerprinted file (M2 round 2, code claim 5: the old test monkeypatched
    # code_fingerprint itself, so it tested nothing about what is hashed). The volbt package is
    # copied, a fresh interpreter builds with the copy: unchanged, it prices nothing; with one
    # comment added to pricing/smile.py, it prices every partition.
    store = pricing_store.make_store(tmp_path / "code")
    build.build_pricing(store)
    package = tmp_path / "copy" / "volbt"
    shutil.copytree(build.PACKAGE_DIR, package, ignore=shutil.ignore_patterns("__pycache__"))
    script = ("import json, sys\nfrom pathlib import Path\nfrom volbt import build\nfrom volbt.data.store import Store\n"
              f"assert Path(build.__file__).resolve().is_relative_to(Path({str(package)!r}).resolve())\n"
              f"build.build_pricing(Store(Path({str(store.root)!r})))\n")

    def rebuilt_by_copy() -> int:
        env = {**os.environ, "PYTHONPATH": str(package.parent)}
        subprocess.run([sys.executable, "-c", script], check=True, timeout=600, env=env, capture_output=True)
        return len(json.loads((store.root / build.TIMINGS_FILE).read_text())["partitions"])

    assert rebuilt_by_copy() == 0
    with open(package / "pricing" / "smile.py", "a", encoding="utf-8") as handle:
        handle.write("\n# an edit\n")
    assert rebuilt_by_copy() == 3


def rebuilt_after(store) -> list:
    build.build_pricing(store)
    return json.loads((store.root / build.TIMINGS_FILE).read_text())["partitions"]


@pytest.mark.parametrize("table", ["rates", "dividends", "spy_bars"])      # literal: not the constant under test
def test_a_change_in_a_reference_table_reprices_every_partition(tmp_path, table):
    # The fingerprint covers rates, dividends and spy_bars (code mutant M19 dropped the dividends).
    store = pricing_store.make_store(tmp_path / table)
    build.build_pricing(store)
    order = {"rates": "date", "dividends": "ex_date", "spy_bars": "date"}[table]
    frame = store.read_table(table, order_by=order)
    column = {"rates": "r_cc", "dividends": "amount", "spy_bars": "volume"}[table]
    frame.loc[frame.index[0], column] += 1
    store.write_table(table, frame, sort_by=(order,))
    assert len(rebuilt_after(store)) == 3


@pytest.fixture(scope="module")
def library_store(tmp_path_factory):
    store = pricing_store.make_store(tmp_path_factory.mktemp("library"))
    build.build_pricing(store)
    return store


@pytest.mark.parametrize("library", ["numpy", "scipy", "pandas", "pyarrow", "duckdb"])   # literal: not the constant
def test_a_new_library_version_reprices_every_partition(library_store, monkeypatch, library):
    # The bytes depend on numpy, scipy, pandas, pyarrow and duckdb (parquet-cpp-arrow names itself
    # in every footer): a version change must not leave old files beside new ones. Each library in
    # turn (the review's mutant R27 dropped four of the five and survived a pyarrow-only test).
    store = library_store
    assert rebuilt_after(store) == []
    module = {"numpy": np, "scipy": scipy, "pandas": pd, "pyarrow": pyarrow, "duckdb": duckdb}[library]
    monkeypatch.setattr(module, "__version__", "99.0.0")
    assert len(rebuilt_after(store)) == 3
    monkeypatch.undo()
    assert len(rebuilt_after(store)) == 3                         # and back: the store is current again


def test_a_new_python_version_reprices_every_partition(library_store, monkeypatch):
    # The review's mutant R28 dropped the Python version from the fingerprint and survived.
    store = library_store
    assert rebuilt_after(store) == []
    monkeypatch.setattr(build.platform, "python_version", lambda: "3.99.0")
    assert len(rebuilt_after(store)) == 3
    monkeypatch.undo()
    assert len(rebuilt_after(store)) == 3


def test_a_new_store_write_setting_reprices_every_partition(tmp_path, monkeypatch):
    # The M2 review changed COMPRESSION_LEVEL: nothing was re-priced, yet a forced build wrote
    # different bytes. Now it is in the fingerprint.
    store = pricing_store.make_store(tmp_path / "settings")
    build.build_pricing(store)
    before = digest(store.root)
    monkeypatch.setattr(store_module, "COMPRESSION_LEVEL", 9)
    assert len(rebuilt_after(store)) == 3
    after = digest(store.root)
    assert after["quote_iv/source=optionsdx/year=2023/part-0.parquet"] != before["quote_iv/source=optionsdx/year=2023/part-0.parquet"]


def test_the_fingerprint_covers_every_volbt_module_the_build_imports(tmp_path):
    # A fresh interpreter runs a build and lists every volbt module it loaded: each one's source
    # must be among the files code_fingerprint hashes (the M2 review found store.py, flags.py and
    # config.py outside it).
    store = pricing_store.make_store(tmp_path / "modules")
    script = ("import json, sys\nfrom pathlib import Path\nfrom volbt import build\nfrom volbt.data.store import Store\n"
              f"build.build_pricing(Store(Path({str(store.root)!r})))\n"
              "print(json.dumps(sorted((m, getattr(sys.modules[m], '__file__', None)) for m in list(sys.modules)"
              " if m == 'volbt' or m.startswith('volbt.'))))\n")
    run = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True, timeout=600)
    loaded = json.loads(run.stdout.strip().splitlines()[-1])
    hashed = {path.resolve() for path in build.fingerprinted_files()}
    assert len(loaded) >= 10 and all(file for _, file in loaded)
    missing = [name for name, file in loaded if Path(file).resolve() not in hashed]
    assert missing == [], missing
    assert any(name == "volbt.data.store" for name, _ in loaded) and any(name == "volbt.pricing.deam" for name, _ in loaded)


def test_a_pricing_partition_whose_quotes_are_gone_is_deleted(tmp_path):
    # The review deleted option_quotes/source=dolthub: its pricing partitions stayed, and the
    # summary still counted 78 DoltHub quotes.
    store = pricing_store.make_store(tmp_path / "orphans")
    build.build_pricing(store)
    store.delete_partition("option_quotes", {"source": "dolthub", "year": "2023"})
    summary = build.build_pricing(store)
    for name in build.PRICING_TABLES:
        assert {"source": "dolthub", "year": "2023"} not in store.partitions(name)
        assert not (store.table_dir(name) / "source=dolthub").exists()
    assert all(row["source"] != "dolthub" for block in summary.values() if isinstance(block, list) for row in block)
    assert "source=dolthub/year=2023" not in json.loads((store.root / build.INPUTS_FILE).read_text())


# --- orphan deletion is data deletion (M2 round 2, code claim 1; decision E2) -------------------------

def pricing_files(root: Path) -> dict:
    """{path: SHA-256} of every file under the three pricing tables, links followed."""
    out = {}
    for name in build.PRICING_TABLES:
        for path in sorted((root / name).rglob("*")):
            if path.is_file():
                out[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


@pytest.fixture
def priced_store(tmp_path):
    store = pricing_store.make_store(tmp_path / "store")
    build.build_pricing(store)
    return store


def test_a_filtered_build_deletes_nothing_and_its_summary_refuses_until_a_full_build(priced_store):
    # The review's mutant R31 deleted every partition a filtered build did not ask for and survived the
    # suite. A filtered build now deletes nothing, not even a true orphan, and the summary refuses
    # while the orphan is there.
    store = priced_store
    store.delete_partition("option_quotes", {"source": "dolthub", "year": "2023"})
    before = pricing_files(store.root)
    with pytest.raises(build.PricingNotCurrent, match="quote_iv partitions whose quotes are gone"):
        build.build_pricing(store, years=["2022"])
    assert pricing_files(store.root) == before
    assert not (store.root / build.SUMMARY_FILE).exists()       # the old summary no longer describes the store
    with pytest.raises(build.PricingNotCurrent):
        build.build_pricing(store, sources=["optionsdx"])
    assert pricing_files(store.root) == before
    build.build_pricing(store)                                    # unfiltered: the orphan goes
    assert not (store.table_dir("quote_iv") / "source=dolthub").exists()


def test_with_no_option_quotes_the_build_raises_and_deletes_nothing(priced_store):
    # The review removed option_quotes: the build deleted all 21 pricing files, then crashed.
    # Round 4 (finding N-B): the summary too. The reviewer's mutant R4-F1b, which removed it before this
    # check, survived the default suite.
    store = priced_store
    before = pricing_files(store.root)
    summary = (store.root / build.SUMMARY_FILE).read_bytes()
    shutil.rmtree(store.table_dir("option_quotes"))
    with pytest.raises(ValueError, match="no option_quotes partition: nothing to price, and nothing was deleted"):
        build.build_pricing(store)
    assert pricing_files(store.root) == before and len(before) == 9
    assert (store.root / build.SUMMARY_FILE).read_bytes() == summary


@pytest.mark.parametrize("inside", [False, True], ids=["link-out-of-the-store", "link-inside-the-store"])
def test_a_symlinked_quotes_partition_is_refused_before_anything_is_deleted(priced_store, tmp_path, inside):
    # Moved to another disk and linked back: Store.partitions did not see it, so its pricing was "orphan".
    # A link to a folder inside the store root is refused too: no resolve() check would catch it.
    store = priced_store
    folder = store.table_dir("option_quotes") / "source=optionsdx" / "year=2022"
    target = (store.root / "elsewhere") if inside else (tmp_path / "moved")
    shutil.move(str(folder), str(target))
    folder.symlink_to(target, target_is_directory=True)
    before = pricing_files(store.root)
    with pytest.raises(store_module.InconsistentStore, match="year=2022 is a symlink: the store's tables must be real"):
        build.build_pricing(store)
    assert pricing_files(store.root) == before
    assert (store.table_dir("quote_iv") / "source=optionsdx" / "year=2022" / "part-0.parquet").is_file()


def test_a_symlinked_pricing_table_is_refused_and_nothing_outside_the_store_is_deleted(priced_store, tmp_path):
    store = priced_store
    outside = tmp_path / "outside_quote_iv"
    shutil.move(str(store.table_dir("quote_iv")), str(outside))
    store.table_dir("quote_iv").symlink_to(outside, target_is_directory=True)
    shutil.rmtree(store.table_dir("option_quotes") / "source=dolthub")
    with pytest.raises(store_module.InconsistentStore, match="quote_iv is a symlink: the store's tables must be real folders$"):
        build.build_pricing(store)
    assert (outside / "source=dolthub" / "year=2023" / "part-0.parquet").is_file()
    assert (store.table_dir("smile_fits") / "source=dolthub" / "year=2023" / "part-0.parquet").is_file()


def test_a_quotes_partition_left_as_a_tmp_file_is_an_inconsistent_store(priced_store):
    # A crashed M1 write leaves part-0.parquet.tmp: the partition is not gone, it is half-written.
    store = priced_store
    part = store.partition_file("option_quotes", {"source": "optionsdx", "year": "2023"})
    part.rename(part.with_name("part-0.parquet.tmp"))
    before = pricing_files(store.root)
    with pytest.raises(store_module.InconsistentStore, match="part-0.parquet.tmp"):
        build.build_pricing(store)
    assert pricing_files(store.root) == before


def test_a_stray_folder_in_a_pricing_table_is_refused_before_any_deletion(priced_store):
    # The review's backup folder inside a partition crashed the build half-way through its deletions.
    store = priced_store
    stray = store.table_dir("quote_iv") / "source=optionsdx" / "year=2023" / "backup"
    stray.mkdir()
    shutil.copy(stray.parent / "part-0.parquet", stray / "old.parquet")
    shutil.rmtree(store.table_dir("option_quotes") / "source=dolthub")
    before = pricing_files(store.root)
    with pytest.raises(store_module.InconsistentStore, match="a folder inside the partition"):
        build.build_pricing(store)
    assert pricing_files(store.root) == before                     # the dolthub orphans are still there too


@pytest.mark.parametrize("where", ["quote_iv", "quote_iv/source=optionsdx"])
def test_a_stray_file_between_the_partition_folders_is_refused(priced_store, where):
    # A note or a backup left beside the source= or year= folders: not what write_partition leaves.
    store = priced_store
    (store.root / where / "notes.txt").write_text("kept by hand")
    shutil.rmtree(store.table_dir("option_quotes") / "source=dolthub")
    before = pricing_files(store.root)
    with pytest.raises(store_module.InconsistentStore, match="notes.txt: a file where only (source|year)=<value> folders belong"):
        build.build_pricing(store)
    assert pricing_files(store.root) == before


def test_delete_partition_refuses_a_symlink_or_a_path_outside_the_table(tmp_path):
    store = Store(tmp_path / "store")
    store.write_table("t", pd.DataFrame({"source": ["a"], "year": [1], "x": [1]}), sort_by=("x",),
                      partition_by=("source", "year"))
    outside = tmp_path / "outside"
    (outside / "year=1").mkdir(parents=True)
    (outside / "year=1" / "keep.txt").write_text("live data")
    (store.table_dir("t") / "source=b").symlink_to(outside, target_is_directory=True)
    with pytest.raises(store_module.InconsistentStore, match="source=b is a symlink$"):
        store.delete_partition("t", {"source": "b", "year": "1"})
    with pytest.raises(store_module.InconsistentStore, match=": it resolves outside "):
        store.delete_partition("t", {"source": "a", "year": "1/../../../../outside"})   # resolves to `outside`
    assert (outside / "year=1" / "keep.txt").read_text() == "live data"
    store.delete_partition("t", {"source": "a", "year": "1"})
    assert not (store.table_dir("t") / "source=a").exists()


# --- provenance after a partial build (M2 round 2, design claim 3; decision E5) ------------------------

def test_a_filtered_build_after_a_code_change_cannot_produce_a_summary(priced_store, monkeypatch):
    # --year 2022 after a code change re-prices 2022 only; the summary (and so the export's
    # config_hash) would name the new code for partitions the old code priced.
    store = priced_store
    monkeypatch.setattr(build.FINGERPRINT_LIBRARIES["numpy"], "__version__", "99.0.0")
    with pytest.raises(build.PricingNotCurrent, match="partitions priced by older code: run a full build") as raised:
        build.build_pricing(store, years=["2022"])
    assert "source=optionsdx/year=2023" in str(raised.value) and "year=2022" not in str(raised.value)
    rebuilt = json.loads((store.root / build.TIMINGS_FILE).read_text())["partitions"]
    assert [(r["source"], r["year"]) for r in rebuilt] == [("optionsdx", "2022")]
    assert not (store.root / build.SUMMARY_FILE).exists()
    summary = build.build_pricing(store)                          # the full build re-prices the other two
    assert len(json.loads((store.root / build.TIMINGS_FILE).read_text())["partitions"]) == 2
    assert summary["code_fingerprint"] == build.code_fingerprint()
    recorded = json.loads((store.root / build.INPUTS_FILE).read_text())
    assert {entry["code"] for entry in recorded.values()} == {build.code_fingerprint()}


def test_the_summary_refuses_a_partition_with_no_recorded_code(priced_store):
    store = priced_store
    recorded = json.loads((store.root / build.INPUTS_FILE).read_text())
    recorded["source=optionsdx/year=2023"] = recorded["source=optionsdx/year=2023"]["inputs"]   # the old format
    (store.root / build.INPUTS_FILE).write_text(json.dumps(recorded))
    with pytest.raises(build.PricingNotCurrent, match=r"older code.*source=optionsdx/year=2023"):
        build.pricing_summary(store)
    assert build.pricing_problems(store) != []
    build.build_pricing(store)                                    # the build re-prices it, and all is current
    assert build.pricing_problems(store) == []


@pytest.mark.parametrize("table", ["expiry_forwards", "quote_iv", "smile_fits"])        # literal: not the constant
def test_the_summary_refuses_a_quotes_partition_without_its_pricing(priced_store, table):
    # A pricing partition removed by hand (or never written by a filtered build): the summary would
    # describe fewer quotes than the store holds.
    store = priced_store
    store.delete_partition(table, {"source": "optionsdx", "year": "2022"})
    with pytest.raises(build.PricingNotCurrent, match=rf"quotes partitions with no {table}: \['source=optionsdx/year=2022'\]"):
        build.pricing_summary(store)


# --- provenance covers the inputs (round 3, code claim 6; decisions F1 and F5) --------------------------

def exporter():
    """tools/export_app_data.py, imported from the tools folder (it is a script, not a volbt module)."""
    tools = str(Path(__file__).resolve().parent.parent / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import export_app_data

    return export_app_data


def test_quotes_rewritten_with_the_code_unchanged_are_refused_by_the_summary_and_the_export(priced_store):
    # The round-3 reviewer rewrote optionsdx/2023's bids and asks x1.30 with the code unchanged:
    # pricing_problems() was [], the summary and the export accepted the store, and the frame shipped
    # the old IV (0.180069) under the new quotes' data fingerprint (a rebuild gives 0.233795).
    export_app_data = exporter()

    store = priced_store
    frames = ((date(2023, 6, 15), "made-up"),)
    before = export_app_data.surface_frames_body(store, frames, source="optionsdx")["frames"][0]["iv"][3][15]
    part = {"source": "optionsdx", "year": "2023"}
    quotes = pd.read_parquet(store.partition_file("option_quotes", part))
    quotes["bid"], quotes["ask"] = (quotes["bid"] * 1.30).round(2), (quotes["ask"] * 1.30).round(2)
    store.write_partition("option_quotes", quotes, part, sort_by=("quote_date", "osi_symbol"))
    problems = build.pricing_problems(store)
    assert problems == ["partitions whose quotes or reference tables changed since they were priced: run a build "
                        "(tools/build_pricing.py): ['source=optionsdx/year=2023']"]
    with pytest.raises(build.PricingNotCurrent, match=r"quotes or reference tables changed.*source=optionsdx/year=2023"):
        build.pricing_summary(store)
    with pytest.raises(build.PricingNotCurrent, match=r"quotes or reference tables changed.*source=optionsdx/year=2023"):
        export_app_data.surface_frames_body(store, frames, source="optionsdx")
    build.build_pricing(store)                                     # re-prices 2023 only
    assert [r["year"] for r in json.loads((store.root / build.TIMINGS_FILE).read_text())["partitions"]] == ["2023"]
    after = export_app_data.surface_frames_body(store, frames, source="optionsdx")["frames"][0]["iv"][3][15]
    assert build.pricing_problems(store) == [] and after > before + 0.03


def test_a_changed_reference_table_is_refused_until_every_partition_is_repriced(priced_store):
    store = priced_store
    rates = store.read_table("rates", order_by="date")
    rates["r_cc"] = rates["r_cc"] + 0.001
    store.write_table("rates", rates, sort_by=("date",))
    problems = build.pricing_problems(store)
    assert len(problems) == 1 and all(k in problems[0] for k in ("source=dolthub/year=2023", "source=optionsdx/year=2022",
                                                                 "source=optionsdx/year=2023"))
    with pytest.raises(build.PricingNotCurrent, match="quotes or reference tables changed"):
        build.pricing_summary(store)


def test_a_build_interrupted_after_deleting_orphans_leaves_no_summary_and_the_export_refuses(priced_store, monkeypatch):
    # The round-3 reviewer: a build killed after it deleted the orphans left the previous summary,
    # which still counted the deleted DoltHub rows, and the export accepted it.
    export_app_data = exporter()

    store = priced_store
    store.delete_partition("option_quotes", {"source": "dolthub", "year": "2023"})

    def killed(*args):
        raise KeyboardInterrupt("killed while pricing")

    monkeypatch.setattr(build, "price_partition", killed)
    with pytest.raises(KeyboardInterrupt):
        build.build_pricing(store, force=True)
    assert not (store.table_dir("quote_iv") / "source=dolthub").exists()      # the orphans went first
    assert not (store.root / build.SUMMARY_FILE).exists()
    with pytest.raises(FileNotFoundError, match="has no pricing_summary.json"):
        export_app_data.surface_frames_body(store, ((date(2023, 6, 15), "x"),), source="optionsdx")


def test_the_summary_is_removed_before_the_build_deletes_or_writes_anything(priced_store, monkeypatch):
    store = priced_store
    store.delete_partition("option_quotes", {"source": "dolthub", "year": "2023"})
    seen = []
    real = store.delete_partition

    def deleting(name, partition):
        seen.append((store.root / build.SUMMARY_FILE).exists())
        return real(name, partition)

    monkeypatch.setattr(store, "delete_partition", deleting)
    build.build_pricing(store)
    assert seen == [False, False, False] and (store.root / build.SUMMARY_FILE).exists()


@pytest.mark.parametrize("filters", [{"sources": []}, {"years": []}, {"sources": [], "years": ["2022"]}],
                         ids=["sources", "years", "both"])
def test_an_empty_filter_list_raises_before_anything_is_read_or_deleted(priced_store, filters):
    # Round 3 (code finding N-3; decision F5): sources=[] or years=[] meant "no filter", so it deleted
    # the orphans of an unfiltered build. Unfiltered is None only; an empty list names nothing.
    store = priced_store
    store.delete_partition("option_quotes", {"source": "dolthub", "year": "2023"})
    before = pricing_files(store.root)
    summary = (store.root / build.SUMMARY_FILE).read_bytes()
    with pytest.raises(ValueError, match=r"=\[\] names no partition: pass None to price every partition"):
        build.build_pricing(store, **filters)
    assert pricing_files(store.root) == before and (store.root / build.SUMMARY_FILE).read_bytes() == summary


def test_a_none_filter_is_unfiltered_and_deletes_the_orphans(priced_store):
    store = priced_store
    store.delete_partition("option_quotes", {"source": "dolthub", "year": "2023"})
    build.build_pricing(store, sources=None, years=None)
    assert not (store.table_dir("quote_iv") / "source=dolthub").exists() and build.pricing_problems(store) == []


def test_the_summary_means_are_exact_whatever_the_thread_count(priced_store):
    # mean_r_cc was avg(): its bits depended on the order DuckDB's threads met the rows. Now it is
    # build.exact_mean: the sum taken exactly in rationals (fractions.Fraction) over n, rounded once.
    from fractions import Fraction

    store = priced_store
    rows = store.query("SELECT source, r_cc FROM expiry_forwards WHERE tau_years > 0")
    blocks = build.summary_blocks(store)
    pooled = blocks["forwards"][blocks["forwards"]["year"].isna() & blocks["forwards"]["tenor"].isna()]
    for row in pooled.itertuples(index=False):
        values = rows[rows["source"] == row.source]["r_cc"].tolist()
        exact = float(sum(Fraction(v) for v in values) / len(values))
        assert row.mean_r_cc == exact
    assert build.exact_mean([0.1, 0.2, 0.3, 1e16, -1e16]) == build.exact_mean([1e16, 0.3, -1e16, 0.2, 0.1]) == 0.12


# --- a reference table is its one file (round 4, finding 1a; decision G1) ----------------------------------

ONE_FILE = r"an unpartitioned table's folder must hold exactly the file part-0.parquet"


def spoil_reference_table(store, table: str, how: str, elsewhere: Path) -> Path:
    """Leave `table`'s folder as the writer never does; returns the path that must survive the refusals."""
    folder = store.table_dir(table)
    if how == "second parquet":
        # The round-4 reviewer's attack: a second rates file with the last date's rate 2 points higher.
        rates = store.read_table(table, order_by="date").tail(1)
        rates = rates.assign(dgs3mo_pct=rates["dgs3mo_pct"] + 2.0, r_cc=rates["r_cc"] + 0.02)
        store_module.write_parquet(pyarrow.Table.from_pandas(rates.reset_index(drop=True), preserve_index=False),
                                   folder / "part-1.parquet")
        return folder / "part-1.parquet"
    if how == "symlinked part-0":
        elsewhere.mkdir()
        shutil.move(str(folder / "part-0.parquet"), str(elsewhere / "part-0.parquet"))
        (folder / "part-0.parquet").symlink_to(elsewhere / "part-0.parquet")
        return elsewhere / "part-0.parquet"
    (folder / "notes.txt").write_text("kept by hand")                                  # "a stray file"
    return folder / "notes.txt"


@pytest.mark.parametrize("how, message", [
    ("second parquet", ONE_FILE + r", it holds \['part-0.parquet', 'part-1.parquet'\]"),
    ("symlinked part-0", r"rates/part-0.parquet is a symlink: the store's tables must be real folders and files"),
    ("stray file", ONE_FILE + r", it holds \['notes.txt', 'part-0.parquet'\]"),
])
def test_a_reference_table_that_is_not_its_one_file_is_refused_by_the_build_the_summary_and_the_export(
        priced_store, tmp_path, how, message):
    # The round-4 reviewer added rates/part-1.parquet: Store.connect reads rates/**/*.parquet, so the rate used for
    # 2023-06-15 moved from 0.0522 to 0.0722, while partition_fingerprint and the export's data_fingerprint hashed
    # part-0.parquet alone: pricing_problems() was [], the summary and the export accepted the store, an incremental
    # build re-priced nothing, and the frame shipped IV 0.180069 (0.179531 after --force).
    export_app_data = exporter()

    store = priced_store
    kept = spoil_reference_table(store, "rates", how, tmp_path / "elsewhere")
    if how == "second parquet":                             # the attack is live: pricing reads the extra row
        assert len(build.reference_inputs(store)["r_cc"]) == len(pricing_store.RATE_PCT) + 1
    with pytest.raises(store_module.InconsistentStore, match=message):
        build.pricing_summary(store)
    with pytest.raises(store_module.InconsistentStore, match=message):
        export_app_data.surface_frames_body(store, ((date(2023, 6, 15), "made-up"),), source="optionsdx")
    store.delete_partition("option_quotes", {"source": "dolthub", "year": "2023"})    # orphans a build would delete
    before = pricing_files(store.root)
    summary, inputs = ((store.root / name).read_bytes() for name in (build.SUMMARY_FILE, build.INPUTS_FILE))
    for force in (False, True):
        with pytest.raises(store_module.InconsistentStore, match=message):
            build.build_pricing(store, force=force)
    assert pricing_files(store.root) == before and (store.table_dir("quote_iv") / "source=dolthub").exists()
    assert (store.root / build.SUMMARY_FILE).read_bytes() == summary
    assert (store.root / build.INPUTS_FILE).read_bytes() == inputs and kept.is_file()


def test_a_second_vix_file_is_refused_by_the_export(priced_store):
    # The export reads vix beside the pricing tables (each frame's vix_close), the pricing build does not.
    export_app_data = exporter()

    store = priced_store
    shutil.copy(store.table_dir("vix") / "part-0.parquet", store.table_dir("vix") / "part-1.parquet")
    assert build.pricing_problems(store) == []
    with pytest.raises(store_module.InconsistentStore, match=r"vix: " + ONE_FILE):
        export_app_data.surface_frames_body(store, ((date(2023, 6, 15), "made-up"),), source="optionsdx")


@pytest.mark.parametrize("how", ["clean", "second parquet", "a crashed write's tmp", "a folder", "no part-0",
                                 "part-0 a folder", "symlinked folder", "symlinked part-0", "no table"])
def test_checked_table_file_accepts_exactly_the_one_file_write_table_leaves(tmp_path, how):
    store = Store(tmp_path / "store")
    store.write_table("t", pd.DataFrame({"date": [date(2023, 6, 14)], "x": [1.0]}), sort_by=("date",))
    folder, part = store.table_dir("t"), store.table_dir("t") / "part-0.parquet"
    if how == "second parquet":
        shutil.copy(part, folder / "part-1.parquet")
    elif how == "a crashed write's tmp":
        shutil.copy(part, folder / "part-0.parquet.tmp")
    elif how == "a folder":
        (folder / "backup").mkdir()
        shutil.copy(part, folder / "backup" / "part-0.parquet")
    elif how == "no part-0":
        part.rename(folder / "part-0.parquet.tmp")
    elif how == "part-0 a folder":
        part.unlink()
        part.mkdir()
    elif how == "symlinked folder":
        shutil.move(str(folder), str(tmp_path / "moved"))
        folder.symlink_to(tmp_path / "moved", target_is_directory=True)
    elif how == "symlinked part-0":
        shutil.move(str(part), str(tmp_path / "moved.parquet"))
        part.symlink_to(tmp_path / "moved.parquet")
    elif how == "no table":
        shutil.rmtree(folder)
    if how == "clean":
        assert store.checked_table_file("t") == part and part.is_file()
        return
    message = {"symlinked folder": r"/t is a symlink: the store's tables must be real folders$",
               "symlinked part-0": r"part-0.parquet is a symlink", "no table": r"no such table folder"}.get(how, ONE_FILE)
    with pytest.raises(store_module.InconsistentStore, match=message):
        store.checked_table_file("t")


# --- the export checks before and after it reads (round 4, finding 1b; decision G2) -----------------------

@pytest.mark.parametrize("rewritten, message", [
    ("the frame's quotes", r"quotes or reference tables changed.*source=optionsdx/year=2023"),
    ("another year's quotes", r"quotes or reference tables changed.*source=optionsdx/year=2022"),
    ("vix", r"the frames' input files changed while the export read them"),
])
def test_an_input_rewritten_while_the_export_reads_the_frames_is_refused(priced_store, monkeypatch, rewritten, message):
    # The round-4 reviewer forced the interleaving inside build.surface_frames_body: the export checked
    # require_current, THEN read the smiles and hashed the inputs, so a quotes rewrite (x1.30) in between shipped
    # the old IV 0.180069 under the new quotes' data_fingerprint (a rebuild gives 0.233795). Each case here is
    # caught by one check alone: another year's quotes only by the second require_current (that year is not in
    # the frame's data_fingerprint), vix only by the data_fingerprint taken before and after (the pricing record
    # does not cover it), the frame's own quotes by both.
    export_app_data = exporter()

    store = priced_store
    frames = ((date(2023, 6, 15), "made-up"),)
    real = build.surface_frames_body

    def rewrite_after_reading(*args, **kwargs):
        body = real(*args, **kwargs)                           # the smiles of the inputs as they were
        if rewritten == "vix":
            vix = store.read_table("vix", order_by="date")
            store.write_table("vix", vix.assign(close=vix["close"] + 1.0), sort_by=("date",))
        else:
            part = {"source": "optionsdx", "year": "2023" if rewritten == "the frame's quotes" else "2022"}
            quotes = pd.read_parquet(store.partition_file("option_quotes", part))
            quotes["bid"], quotes["ask"] = (quotes["bid"] * 1.30).round(2), (quotes["ask"] * 1.30).round(2)
            store.write_partition("option_quotes", quotes, part, sort_by=("quote_date", "osi_symbol"))
        return body

    monkeypatch.setattr(build, "surface_frames_body", rewrite_after_reading)
    with pytest.raises(build.PricingNotCurrent, match=message):
        export_app_data.surface_frames_body(store, frames, source="optionsdx")
    monkeypatch.setattr(build, "surface_frames_body", real)
    if rewritten == "vix":                                     # vix needs no re-price: the export now succeeds
        assert export_app_data.surface_frames_body(store, frames, source="optionsdx")["frames"][0]["vix_close"] == 14.6


def test_quoted_share_is_the_share_of_cells_without_an_extrapolation_flag(built):
    store, _ = built
    frame = build.surface_frames_body(store, [(date(2023, 6, 15), "made-up date")])["frames"][0]
    flags = np.array(frame["cell_flags"])
    extrapolated = (flags & 1) | (flags & 4)
    assert frame["quoted_share"] == round(float((extrapolated == 0).mean()), 6)
    # 7 days: shorter than the front expiry (tenor extrapolation); 90 days and up: past the back one.
    assert (extrapolated[0] != 0).all() and (extrapolated[build.GRID_DTE.index(90):] != 0).all()


def test_a_frame_never_lets_rounding_make_total_variance_fall():
    # Two smiles that cross everywhere: the 400-day w is below the 10-day w at every k, so the
    # calendar floor holds w flat from 10 days on and each IV is sqrt(w / tau). Rounded to 6
    # decimals alone, 123 of those cells would show w falling by ~1e-7; the frame raises each by
    # one unit of the last decimal instead, so w, computed as the app computes it, never falls.
    k = np.linspace(-0.4, 0.3, 15)
    smiles = [(10 / 365, k, 0.0130 + 0.02 * k**2), (400 / 365, k, 0.0100 + 0.01 * k**2)]
    frame = build.surface_frame(smiles)
    iv = np.array(frame["iv"])
    w = iv * iv * np.array(build.GRID_DTE, dtype=float)[:, None] / 365
    assert int((np.diff(w, axis=0) < 0).sum()) == 0
    assert ((np.array(frame["cell_flags"]) & 8) != 0).sum() > 200
    # The 30-day ATM IV is the grid's own cell, not a second reading of the surface.
    assert frame["atm_iv_30d"] == frame["iv"][build.GRID_DTE.index(30)][build.GRID_MONEYNESS.index(0.0)]


def test_a_frame_whose_surface_falls_is_refused_not_written(monkeypatch):
    # The rounding bump is for rounding only: if surface_iv itself let w fall, four raises of 1e-6
    # would not mend it, and the frame is refused here instead of written for the app to refuse.
    from volbt.pricing import smile

    def falling(k, tau, expiries):
        return np.full(np.shape(k), 0.20 if tau < 100 / 365 else 0.10), np.zeros(np.shape(k), dtype=np.int32)

    monkeypatch.setattr(smile, "surface_iv", falling)
    with pytest.raises(ValueError, match="even after 4 raises"):
        build.surface_frame([(30 / 365, np.linspace(-0.3, 0.2, 6), np.full(6, 0.01))])
