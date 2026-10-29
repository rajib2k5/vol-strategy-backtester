"""Checks on the FULL vendor data and the built store. Not in the default run.

Run after `uv run python tools/build_data.py`:   uv run pytest -m real_data

These are also the only tests that hold the REAL vendor files against the pinned schema
(src/volbt/data/schema.py). The fixtures in tests/fixtures/ are synthetic: they copy the pin
and invent the values, and no vendor row is committed.
"""

import json
import shutil
from datetime import date
from pathlib import Path

import duckdb
import pyarrow.parquet as pq
import pytest

from volbt import config
from volbt.data import dolthub, optionsdx, pipeline, reference
from volbt.data.schema import DOLTHUB_COLUMNS, check_dolthub_schema
from volbt.data.store import Store

pytestmark = pytest.mark.real_data
D = date
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="module")
def store():
    built = Store(config.store_dir())
    if not built.has("option_quotes"):
        pytest.skip("no built store: run uv run python tools/build_data.py")
    return built


def test_every_optionsdx_file_passes_the_schema_pin():
    paths = optionsdx.files()
    assert len(paths) == 14
    for path in paths:
        optionsdx.check_file(path)     # raises SchemaError on any difference from the pinned 33 columns


def shared_clone_listing():
    """(relative path, size, mtime ns, ctime ns) of every entry of the SHARED clone: ctime moves on any write."""
    clone = config.dolthub_options_dir()
    return [(p.relative_to(clone).as_posix(), p.lstat().st_size, p.lstat().st_mtime_ns, p.lstat().st_ctime_ns)
            for p in sorted(clone.rglob("*"))]


def test_the_real_dolthub_option_chain_in_the_mirror_matches_the_pin():
    mirror = config.dolthub_mirror_dir()
    if not (mirror / ".dolt").is_dir():
        pytest.skip(f"no DoltHub mirror at {mirror}")
    if not shutil.which("dolt"):
        pytest.skip("dolt is not on PATH")
    before = shared_clone_listing()
    assert dolthub.CLEAN_STATUS in dolthub.dolt_status()            # in the mirror, like every dolt call
    rows = dolthub.parse_describe(dolthub.dolt_sql(dolthub.SQL_DESCRIBE))
    check_dolthub_schema(rows, "real DoltHub option_chain")
    assert [(name, sql_type.lower()) for name, sql_type in rows] == list(DOLTHUB_COLUMNS)
    assert shared_clone_listing() == before     # the shared clone: not a byte, not a timestamp


def test_the_exported_dolthub_rows_have_the_pinned_columns():
    export = config.raw_dir() / pipeline.DOLTHUB_EXPORT
    if not export.exists():
        pytest.skip("no DoltHub export: run uv run python tools/build_data.py --export-dolthub --no-build")
    schema = pq.read_schema(export)
    assert schema.names == [name for name, _ in DOLTHUB_COLUMNS]
    assert [field.type for field in schema] == list(dolthub.SPY_CSV_TYPES.values())


@pytest.mark.parametrize("relative, parse", [
    ("yfinance/SPY_daily.csv", reference.parse_spy_csv),
    ("fred/DGS3MO.csv", reference.parse_fred_csv),
    ("cboe/VIX_History.csv", reference.parse_cboe_csv),
    ("cboe/VIX3M_History.csv", reference.parse_cboe_csv),
])
def test_the_real_reference_downloads_match_their_pins(relative, parse):
    path = config.raw_dir() / relative
    if not path.exists():
        pytest.skip(f"{path} is not downloaded: run uv run python tools/build_data.py --fetch --no-build")
    parse(path)     # raises SchemaError on a changed header or column type


def test_the_synthetic_optionsdx_fixture_holds_no_real_row():
    # The same date, expiry, strike and all four quotes would be a copied row.
    cols = ", ".join(f'"{c}"' for c in ["[QUOTE_DATE]", "[EXPIRE_DATE]", "[STRIKE]", "[C_BID]", "[C_ASK]",
                                        "[P_BID]", "[P_ASK]", "[UNDERLYING_LAST]"])
    fixture = (FIXTURES / "optionsdx_20rows.parquet").as_posix()
    real_files = [path.as_posix() for path in optionsdx.files()]
    shared = duckdb.sql(f"SELECT count(*) FROM (SELECT {cols} FROM read_parquet('{fixture}') "
                        f"INTERSECT SELECT {cols} FROM read_parquet({real_files}))").fetchall()[0][0]
    assert shared == 0


def test_the_synthetic_dolthub_fixture_holds_no_real_row():
    export = config.raw_dir() / pipeline.DOLTHUB_EXPORT
    if not export.exists():
        pytest.skip("no DoltHub export: run uv run python tools/build_data.py --export-dolthub --no-build")
    # The same date, expiry, strike, side, bid and ask would be a copied row.
    cols = '"date", expiration, strike, call_put, bid, ask'
    fixture_rows = dolthub.parse_spy_rows((FIXTURES / "dolthub_spy_20rows.csv").read_text(encoding="utf-8"))
    real_rows = pq.read_table(export)
    shared = duckdb.sql(f"SELECT count(*) FROM (SELECT {cols} FROM fixture_rows "
                        f"INTERSECT SELECT {cols} FROM real_rows)").fetchall()[0][0]
    assert shared == 0


@pytest.mark.parametrize("relative, parse, column", [
    ("yfinance/SPY_daily.csv", lambda path: reference.parse_spy_csv(path)[0], "close"),
    ("cboe/VIX_History.csv", reference.parse_cboe_csv, "close"),
    ("cboe/VIX3M_History.csv", reference.parse_cboe_csv, "close"),
    ("fred/DGS3MO.csv", reference.parse_fred_csv, "dgs3mo_pct"),
])
def test_the_synthetic_reference_fixtures_hold_no_real_value(relative, parse, column):
    real_path = config.raw_dir() / relative
    if not real_path.exists():
        pytest.skip(f"{real_path} is not downloaded: run uv run python tools/build_data.py --fetch --no-build")
    # On each of the 19 fixture dates, the fixture's value is not the real value of that date.
    merged = parse(FIXTURES / "reference" / relative).merge(parse(real_path), on="date", suffixes=("_fixture", "_real"))
    assert len(merged) == 19
    assert not (merged[f"{column}_fixture"] == merged[f"{column}_real"]).any()


def test_twelve_closure_dates_hold_44926_wide_rows(store):
    actions = store.query("SELECT * FROM calendar_actions WHERE source = 'optionsdx' AND action <> 'session' "
                          "ORDER BY vendor_date")
    assert len(actions) == 12
    assert int(actions["rows"].sum()) == 2 * 44926   # long rows: a call and a put per wide row


def test_all_twelve_closure_dates_are_dropped_and_2022_06_17_is_missing(store):
    # Round 2 of the M1 review: the relabel rule is gone, so 2022-06-20 is dropped like the others.
    actions = store.query("SELECT * FROM calendar_actions WHERE source = 'optionsdx' AND action <> 'session' "
                          "ORDER BY vendor_date")
    assert list(actions["action"]) == ["drop"] * 12
    odx_dates = store.query("SELECT DISTINCT quote_date FROM option_quotes WHERE source = 'optionsdx'")["quote_date"]
    assert D(2022, 6, 17) not in {d.date() for d in odx_dates}
    # The diagnostic: every closure date carries the previous session's close to the cent, and only
    # 06-20's previous session has no snapshot of its own. That close is read from the downloaded
    # SPY file, not typed here.
    check = store.query("SELECT * FROM quality_non_session_dates WHERE source = 'optionsdx' ORDER BY vendor_date")
    assert len(check) == 12 and (check["underlying_minus_prev_close_cents"] == 0).all()
    assert [d.date() for d in check.loc[~check["prev_session_has_snapshot"], "vendor_date"]] == [D(2022, 6, 20)]
    spy_bars, _ = reference.parse_spy_csv(config.raw_dir() / "yfinance" / "SPY_daily.csv")
    june_17_close = float(spy_bars.loc[spy_bars["date"] == D(2022, 6, 17), "close"].iloc[0])
    june = check[[d.date() == D(2022, 6, 20) for d in check["vendor_date"]]]
    assert june["underlying_last"].iloc[0] == june["prev_close"].iloc[0] == june_17_close


def test_the_mask_on_2022_06_13_to_06_15(store):
    # ADR-0009 test 7, on the real chains.
    def pairs(sql):
        return {(e.date(), k) for e, k in store.query(sql).itertuples(index=False)}

    dolthub_wed = pairs("SELECT DISTINCT expiry, CAST(round(strike * 1000) AS BIGINT) FROM option_quotes "
                        "WHERE source = 'dolthub' AND quote_date = '2022-06-15'")
    optionsdx_wed = pairs("SELECT DISTINCT expiry, CAST(round(strike * 1000) AS BIGINT) FROM option_quotes "
                          "WHERE source = 'optionsdx' AND quote_date = '2022-06-15'")
    masked_wed = pairs("SELECT DISTINCT q.expiry, CAST(round(q.strike * 1000) AS BIGINT) FROM option_quotes q "
                       "JOIN chain_mask m ON m.quote_date = q.quote_date AND m.expiry = q.expiry "
                       "AND m.strike_milli = CAST(round(q.strike * 1000) AS BIGINT) "
                       "WHERE q.source = 'optionsdx' AND q.quote_date = '2022-06-15' AND m.mask = 'dolthub'")
    assert masked_wed == dolthub_wed & optionsdx_wed and len(masked_wed) > 0
    tuesday = store.query("SELECT count(*) AS n FROM chain_mask WHERE mask = 'dolthub' AND quote_date = '2022-06-14'")
    assert tuesday["n"].iloc[0] == 0
    carried = pairs("SELECT expiry, strike_milli FROM chain_mask WHERE mask = 'dolthub_daily' "
                    "AND quote_date = '2022-06-14'")
    monday = pairs("SELECT expiry, strike_milli FROM chain_mask WHERE mask = 'dolthub' AND quote_date = '2022-06-13'")
    assert carried == monday


def test_the_build_passed_its_gate_and_measured_the_cross_vendor_shares(store):
    summary = json.loads((store.root / "build_summary.json").read_text())
    assert summary["quality_gate"]["passed"] is True
    cross = summary["cross_vendor"]
    assert "tolerances" not in cross and "passed" not in json.dumps(cross)   # measurements, no verdict
    within = cross["within_thresholds"]
    assert (within["iv30_dates"], within["spot_dates"]) == (570, 572)
    assert (round(within["iv30_share_within"], 3), round(within["spot_share_within"], 3)) == (0.974, 0.930)
    assert cross["by_year"]["year"] == [2020, 2021, 2022, 2023] and sum(cross["by_year"]["dates"]) == 572
    assert summary["rows"]["optionsdx"] == 2 * 9468584 - 2 * 44926                # every closure row dropped


def test_vendor_iv_invalid_counts_null_zero_and_negative_ivs(store):
    # R5 of the M1 review: 216,665 negative and 5,983 zero OptionsDX IVs (216,700 and 5,984 with the
    # 2022-06-20 rows the first build relabelled), 70 zero DoltHub vols.
    counts = store.query("""SELECT source, sum(CASE WHEN quality_flags & 2048 <> 0 THEN 1 ELSE 0 END) AS flagged,
                            sum(CASE WHEN vendor_iv IS NULL OR vendor_iv <= 0 THEN 1 ELSE 0 END) AS invalid,
                            sum(CASE WHEN vendor_iv < 0 THEN 1 ELSE 0 END) AS negative,
                            sum(CASE WHEN vendor_iv = 0 THEN 1 ELSE 0 END) AS zero
                            FROM option_quotes GROUP BY 1 ORDER BY 1""")
    by_source = {r.source: (int(r.flagged), int(r.invalid), int(r.negative), int(r.zero)) for r in counts.itertuples()}
    assert by_source == {"dolthub": (70, 70, 0, 70), "optionsdx": (1_277_951, 1_277_951, 216_665, 5_983)}


def test_the_dolthub_export_ran_in_a_clean_mirror():
    evidence = json.loads((config.raw_dir() / "dolthub" / "option_chain_spy.export.json").read_text())
    assert evidence["ran_in"] == "the private mirror, config.dolthub_mirror_dir()"
    assert "nothing to commit, working tree clean" in evidence["dolt_status_before"]
    assert "nothing to commit, working tree clean" in evidence["dolt_status_after"]
    assert evidence["rows"] == 185910
