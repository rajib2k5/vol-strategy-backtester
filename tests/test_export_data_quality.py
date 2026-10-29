"""Tests for the data_quality.json half of tools/export_app_data.py.

The exporter reads aggregates from a built store, which the default run cannot assume, so:
- the default run builds a TINY store (tests/data_quality_store.py) whose every number can be
  checked by hand, and checks the file the exporter derives from it;
- the default run also checks the COMMITTED app/public/data/data_quality.json and its manifest entry;
- the tests marked real_data rebuild the file from the real store (`uv run python tools/build_data.py`
  first) and compare it with the committed one byte for byte.
"""

import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import export_app_data  # noqa: E402
from data_quality_store import SUMMARY, make_store, rows_per_date_frame  # noqa: E402
from test_export import ENVELOPE, FIXED_NOW, SHA, lookup_for, read_json  # noqa: E402

from volbt import contract  # noqa: E402
from volbt.data import flags, quality  # noqa: E402
from volbt.data.store import Store  # noqa: E402

COMMITTED_DIR = REPO / "app" / "public" / "data"
SECTIONS = {"label", "flag_names", "flag_descriptions", "flags_by_year", "sources", "calendar", "cross_vendor", "gate"}


@pytest.fixture
def body(tmp_path):
    return export_app_data.data_quality_body(make_store(tmp_path / "store"))


# --- what the exporter derives from the tiny store ---------------------------------------

def test_the_body_has_exactly_the_agreed_sections(body):
    # No section for quotes: the file holds aggregates only.
    assert set(body) == SECTIONS
    assert body["flag_names"] == list(flags.FLAG_NAMES)
    assert len(body["flag_names"]) == 13


def test_every_flag_has_one_description_in_bit_order(body):
    # A new bit in flags.FLAG_NAMES must come with a description, or the exporter fails here (and with a KeyError).
    assert set(export_app_data.FLAG_DESCRIPTIONS) == set(flags.FLAG_NAMES)
    descriptions = body["flag_descriptions"]
    assert len(descriptions) == 13 and all(text.strip() for text in descriptions)
    # Pinned by bit position, so a list that came out in the wrong order is caught.
    assert descriptions[0] == "the bid is missing"                              # BID_NULL, bit 0
    assert descriptions[2] == "the bid is zero"                                 # ZERO_BID, bit 2
    assert descriptions[12] == "the quote is on the contract's expiry date"     # EXPIRY_DAY, bit 12


def test_flags_by_year_has_one_row_per_source_and_year_with_counts_and_shares(body):
    table = body["flags_by_year"]
    assert set(table) == {"source", "year", "rows", "counts", "shares"}
    assert table["source"] == ["dolthub", "dolthub", "dolthub", "optionsdx", "optionsdx"]
    assert table["year"] == [2019, 2020, 2021, 2010, 2011]
    assert table["rows"] == [10, 1000, 2000, 4000, 8000]
    zeros = [0, 0, 0, 0, 0]
    assert table["counts"] == {
        "BID_NULL": [0, 0, 0, 120, 80],
        "ASK_NULL": [0, 0, 0, 120, 80],
        "ZERO_BID": [1, 100, 300, 400, 0],
        "CROSSED": [0, 5, 8, 0, 16],
        "LOCKED": zeros,
        "WIDE": zeros,
        "STALE": [0, 20, 0, 40, 0],
        "NON_SESSION_DATE": zeros,
        "RELABELLED": zeros,
        "VOLUME_UNRELIABLE": [10, 1000, 2000, 4000, 8000],
        "UNDERLYING_MISMATCH": [0, 0, 0, 0, 400],
        "VENDOR_IV_INVALID": [0, 0, 0, 200, 240],
        "EXPIRY_DAY": zeros,
    }
    assert table["shares"] == {
        "BID_NULL": [0, 0, 0, 0.03, 0.01],
        "ASK_NULL": [0, 0, 0, 0.03, 0.01],
        "ZERO_BID": [0.1, 0.1, 0.15, 0.1, 0],
        "CROSSED": [0, 0.005, 0.004, 0, 0.002],
        "LOCKED": zeros,
        "WIDE": zeros,
        "STALE": [0, 0.02, 0, 0.01, 0],
        "NON_SESSION_DATE": zeros,
        "RELABELLED": zeros,
        "VOLUME_UNRELIABLE": [1, 1, 1, 1, 1],
        "UNDERLYING_MISMATCH": [0, 0, 0, 0, 0.05],
        "VENDOR_IV_INVALID": [0, 0, 0, 0.05, 0.03],
        "EXPIRY_DAY": zeros,
    }


def test_flag_columns_follow_bit_order(body):
    assert list(body["flags_by_year"]["counts"]) == list(flags.FLAG_NAMES)
    assert list(body["flags_by_year"]["shares"]) == list(flags.FLAG_NAMES)


def test_rows_per_source_sum_the_quotes_and_count_the_snapshot_dates(body):
    assert body["sources"] == {"source": ["dolthub", "optionsdx"], "rows": [3010, 12000], "dates": [5, 4]}


def test_the_calendar_table_has_one_row_per_source_and_action(body):
    assert body["calendar"] == {
        "source": ["dolthub", "dolthub", "optionsdx", "optionsdx"],
        "action": ["drop", "session", "drop", "session"],
        "dates": [2, 5, 1, 4],
        "rows": [7, 3010, 6, 12000],
    }


def test_the_cross_vendor_section_carries_quantiles_and_shares_and_no_verdict(body):
    cross = body["cross_vendor"]
    assert set(cross) == {"label", "overlap_dates", "basis", "distributions", "within_thresholds", "by_year"}
    assert cross["basis"].startswith("Measurements, not a test.")
    assert cross["label"].startswith("Both vendors, 2020-01-06 to 2023-12-29: vendor IVs")
    assert cross["overlap_dates"] == 100
    distributions = cross["distributions"]
    assert distributions["key"] == [
        "iv30_diff_pts_dolthub_minus_optionsdx", "spot_dolthub_vs_close_bp", "spot_optionsdx_vs_close_bp",
        "spot_dolthub_vs_open_bp", "spot_optionsdx_vs_open_bp",
    ]
    assert distributions["unit"] == ["vol pts", "bp", "bp", "bp", "bp"]
    assert distributions["n"] == [98, 100, 100, 100, 100]
    assert distributions["mean"] == [0.123457, 1, 0, 6.5, 5.5]          # 0.123456789 is rounded to 6 dp
    assert distributions["mean_abs"] == [0.5, 9, 5, 70, 69.5]
    assert distributions["p05"] == [-0.25, -18, -10, -156, -163]
    assert distributions["p25"] == [0.125, -4.5, -3.5, -37.5, -44]
    assert distributions["median"] == [0.25, 1.5, -0.5, 13, 12]
    assert distributions["p75"] == [0.5, 7.5, 2, 60.5, 63.5]
    assert distributions["p95"] == [1.5, 21, 12.5, 140, 137.5]
    assert len(distributions["label"]) == 5 and all(distributions["label"])
    within = cross["within_thresholds"]
    assert set(within) == {"key", "label", "threshold", "unit", "dates", "share_within"}
    assert within["key"] == ["iv30", "spot"]
    assert within["threshold"] == [1, 25]
    assert within["unit"] == ["vol pts", "bp"]
    assert within["dates"] == [98, 100]
    assert within["share_within"] == [0.96, 0.875]
    assert len(within["label"]) == 2 and all(within["label"])
    assert cross["by_year"] == {"year": [2020, 2021], "dates": [40, 60], "iv30_share_within": [0.95, 0.966667],
                                "spot_dolthub_share_within": [0.8, 0.925],
                                "spot_dolthub_vs_close_median_bp": [2.5, -1.25],
                                "spot_optionsdx_vs_close_median_bp": [1.1, -0.5]}


def test_nothing_in_the_cross_vendor_section_reads_as_a_verdict(body):
    # The thresholds were fitted to the same dates, so a pass/fail could not fail (M1 review, R7).
    def keys(node):
        if isinstance(node, dict):
            for key, value in node.items():
                yield key
                yield from keys(value)
        elif isinstance(node, list):
            for value in node:
                yield from keys(value)

    found = set(keys(body["cross_vendor"]))
    assert not found & {"passed", "failures", "required_share", "tolerances", "pass", "fail", "ok"}
    assert not any(isinstance(v, bool) for v in body["cross_vendor"]["within_thresholds"].values())


def test_the_gate_lists_every_limit_beside_the_worst_value_reached(body):
    gate = body["gate"]
    assert gate["passed"] is True and gate["failures"] == []
    table = gate["thresholds"]
    assert set(table) == {"rule", "source", "what", "bound", "limit", "worst", "unit"}
    rows = {
        (table["rule"][i], table["source"][i], table["what"][i]): (
            table["bound"][i], table["limit"][i], table["worst"][i], table["unit"][i])
        for i in range(len(table["rule"]))
    }
    # 9 flag shares, 5 regimes of dates a year, 2 totals, 2 thin-date, 2 dropped-date, 1 gap
    assert len(rows) == len(table["rule"]) == 21
    share = "{} share of a year's quotes".format
    max_share = quality.GATE_MAX_SHARE
    assert rows[("max_share", "optionsdx", share("BID_NULL"))] == ("max", max_share[("optionsdx", "BID_NULL")], 0.03, "fraction")
    assert rows[("max_share", "optionsdx", share("ASK_NULL"))] == ("max", max_share[("optionsdx", "ASK_NULL")], 0.03, "fraction")
    assert rows[("max_share", "optionsdx", share("CROSSED"))] == ("max", max_share[("optionsdx", "CROSSED")], 0.002, "fraction")
    assert rows[("max_share", "optionsdx", share("VENDOR_IV_INVALID"))] == (
        "max", max_share[("optionsdx", "VENDOR_IV_INVALID")], 0.05, "fraction")
    assert rows[("max_share", "optionsdx", share("UNDERLYING_MISMATCH"))] == (
        "max", max_share[("optionsdx", "UNDERLYING_MISMATCH")], 0.05, "fraction")
    assert rows[("max_share", "dolthub", share("BID_NULL"))] == ("max", max_share[("dolthub", "BID_NULL")], 0, "fraction")
    assert rows[("max_share", "dolthub", share("ASK_NULL"))] == ("max", max_share[("dolthub", "ASK_NULL")], 0, "fraction")
    assert rows[("max_share", "dolthub", share("CROSSED"))] == ("max", max_share[("dolthub", "CROSSED")], 0.005, "fraction")
    assert rows[("max_share", "dolthub", share("VENDOR_IV_INVALID"))] == ("max", max_share[("dolthub", "VENDOR_IV_INVALID")], 0, "fraction")
    # One row per sampling regime (quality.GATE_DATES_PER_YEAR). The tiny store covers OptionsDX
    # 2010-2011 (2 dates each) and DoltHub 2019-2021 (2 dates in each of 2020 and 2021): every span
    # has a year with no date at all, so its thinnest year has 0.
    min_all = quality.GATE_MIN_DATES
    assert rows[("min_dates_per_year", "optionsdx", "snapshot dates in the thinnest year of 2010-2023 (daily)")] == (
        "min", 230, 0, "dates")
    assert rows[("min_dates_per_year", "dolthub", "snapshot dates in the thinnest year of 2020-2023 (Mon/Wed/Fri)")] == (
        "min", 120, 0, "dates")
    regime_2024 = "Mon/Wed/Fri to 09-09 with no dates 07-30 to 08-09, then daily"
    assert rows[("min_dates_per_year", "dolthub", f"snapshot dates in 2024 ({regime_2024})")] == ("min", 140, 0, "dates")
    assert rows[("min_dates_per_year", "dolthub", "snapshot dates in 2025 (daily)")] == ("min", 200, 0, "dates")
    assert rows[("min_dates_per_year", "dolthub", "snapshot dates in 2026 (daily, a partial year: the export ends on "
                 "2026-10-26)")] == ("min", 160, 0, "dates")
    assert sum(rule == "min_dates_per_year" for rule, _, _ in rows) == 5
    assert rows[("min_dates", "optionsdx", "snapshot dates in all")] == ("min", min_all["optionsdx"], 4, "dates")
    assert rows[("min_dates", "dolthub", "snapshot dates in all")] == ("min", min_all["dolthub"], 5, "dates")
    thin = "quotes on the thinnest snapshot date"
    min_rows = quality.GATE_MIN_ROWS_PER_DATE
    assert rows[("min_rows_per_date", "optionsdx", thin)] == ("min", min_rows["optionsdx"], 1500, "quotes")
    # DoltHub's 2019 date holds 10 quotes, but the gate checks DoltHub only from 2020-01-06: the worst is 400.
    assert rows[("min_rows_per_date", "dolthub", thin + " from 2020-01-06")] == ("min", min_rows["dolthub"], 400, "quotes")
    dropped = "vendor dates the calendar drops"
    max_dropped = quality.GATE_MAX_DROPPED_DATES
    assert rows[("max_dropped_dates", "optionsdx", dropped)] == ("max", max_dropped["optionsdx"], 1, "dates")
    assert rows[("max_dropped_dates", "dolthub", dropped)] == ("max", max_dropped["dolthub"], 2, "dates")
    assert rows[("max_underlying_p99_cents", "optionsdx", "99th percentile of |UNDERLYING_LAST minus the SPY close|")] == (
        "max", quality.GATE_MAX_UNDERLYING_P99_CENTS, 24, "cents")


def test_a_failing_gate_is_reported_with_its_failures(tmp_path):
    summary = copy.deepcopy(SUMMARY)
    summary["quality_gate"] = {"passed": False, "failures": ["optionsdx 2010: BID_NULL on 6.00% of rows (limit 5%)"]}
    gate = export_app_data.data_quality_body(make_store(tmp_path, summary))["gate"]
    assert gate["passed"] is False
    assert gate["failures"] == ["optionsdx 2010: BID_NULL on 6.00% of rows (limit 5%)"]


def test_the_same_store_gives_the_same_body_and_the_same_bytes(tmp_path):
    first = export_app_data.data_quality_body(make_store(tmp_path / "a"))
    second = export_app_data.data_quality_body(make_store(tmp_path / "b"))
    assert first == second
    for name, directory in (("a", tmp_path / "out_a"), ("b", tmp_path / "out_b")):
        store = Store(tmp_path / name)
        export_app_data.build_payloads(directory, lambda: (SHA, False), FIXED_NOW,
                                       quality_body=export_app_data.data_quality_body(store))
    assert (tmp_path / "out_a" / "data_quality.json").read_bytes() == (tmp_path / "out_b" / "data_quality.json").read_bytes()


def test_every_number_in_the_file_is_finite_and_has_at_most_six_decimals(tmp_path, body):
    export_app_data.build_payloads(tmp_path, lambda: (SHA, False), FIXED_NOW, quality_body=body)
    written = read_json(tmp_path / "data_quality.json")          # read_json refuses NaN and Infinity

    def numbers(node):
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)):
            yield node
        elif isinstance(node, dict):
            for value in node.values():
                yield from numbers(value)
        elif isinstance(node, list):
            for value in node:
                yield from numbers(value)

    found = list(numbers(written))
    assert len(found) > 100
    assert all(value == round(value, 6) for value in found)


def test_whole_numbers_are_written_without_a_decimal_point(tmp_path, body):
    export_app_data.build_payloads(tmp_path, lambda: (SHA, False), FIXED_NOW, quality_body=body)
    tokens = []

    def note_float(token):
        tokens.append(token)
        return float(token)

    json.loads((tmp_path / "data_quality.json").read_text(encoding="utf-8"), parse_float=note_float)
    assert tokens                                              # the file has real fractions (0.03, 0.125 ...)
    assert [t for t in tokens if float(t).is_integer()] == []  # 1500, never 1500.0


def test_the_file_is_the_envelope_then_the_body(tmp_path, body):
    export_app_data.build_payloads(tmp_path, lambda: (SHA, False), FIXED_NOW, quality_body=body)
    written = read_json(tmp_path / "data_quality.json")
    assert {key: written[key] for key in ENVELOPE} == ENVELOPE
    assert list(written)[:3] == ["schema_version", "generated_at", "source_commit"]
    assert {key: written[key] for key in SECTIONS} == body


def test_the_manifest_lists_data_quality_with_the_current_schema_version(tmp_path, body):
    export_app_data.build_payloads(tmp_path, lambda: (SHA, False), FIXED_NOW, quality_body=body)
    entries = {entry["name"]: entry for entry in read_json(tmp_path / "manifest.json")["datasets"]}
    assert entries["data_quality"]["path"] == "data_quality.json"
    assert entries["data_quality"]["schema_version"] == contract.SCHEMA_VERSION
    assert "no quotes" in entries["data_quality"]["description"]


# --- what the exporter refuses --------------------------------------------------------------

@pytest.mark.parametrize("missing", ["quality_flag_counts", "quality_calendar", "quality_rows_per_date", "build_summary.json"])
def test_a_store_without_the_report_is_refused_and_says_how_to_build_it(tmp_path, missing):
    store = make_store(tmp_path, skip=(missing,))
    with pytest.raises(FileNotFoundError) as error:
        export_app_data.data_quality_body(store)
    assert missing in str(error.value)
    assert "tools/build_data.py" in str(error.value)


def test_the_script_exits_1_and_prints_the_reason_when_the_store_is_not_built(tmp_path, capsys):
    out = tmp_path / "out"
    assert export_app_data.main(["--out-dir", str(out), "--store", str(tmp_path / "no-store")]) == 1
    assert "tools/build_data.py" in capsys.readouterr().err
    assert not out.exists()          # nothing is written when the store cannot be read


def test_a_cross_vendor_difference_with_no_values_is_refused(tmp_path):
    summary = copy.deepcopy(SUMMARY)
    summary["cross_vendor"]["spot_dolthub_vs_close_bp"] = {"n": 0}
    with pytest.raises(ValueError, match="spot_dolthub_vs_close_bp has no values"):
        export_app_data.data_quality_body(make_store(tmp_path, summary))


def test_a_share_that_could_not_be_measured_is_refused_not_written_as_null(tmp_path):
    summary = copy.deepcopy(SUMMARY)
    summary["cross_vendor"]["within_thresholds"]["iv30_share_within"] = None
    with pytest.raises(ValueError, match="measured iv30_share_within is None"):
        export_app_data.data_quality_body(make_store(tmp_path, summary))
    summary = copy.deepcopy(SUMMARY)
    summary["cross_vendor"]["by_year"]["spot_optionsdx_vs_close_median_bp"][1] = None
    with pytest.raises(ValueError, match="by_year spot_optionsdx_vs_close_median_bp 2021 is None"):
        export_app_data.data_quality_body(make_store(tmp_path, summary))


def test_a_gate_limit_with_no_worst_value_is_refused(tmp_path):
    # Remove every DoltHub date from the checked window: there is no thinnest date to report.
    store = make_store(tmp_path)
    frame = rows_per_date_frame()
    store.write_table("quality_rows_per_date", frame[~((frame["source"] == "dolthub") & (frame["quote_date"] >= "2020-01-06"))],
                      sort_by=("source", "quote_date"))
    with pytest.raises(ValueError, match="min_rows_per_date dolthub is nan"):
        export_app_data.data_quality_body(store)


# --- the committed file ----------------------------------------------------------------------

def committed_text(name):
    path = COMMITTED_DIR / name
    if not path.exists():
        pytest.skip("run tools/export_app_data.py first")
    return path.read_text(encoding="utf-8")


def committed_quality_body():
    written = read_json(COMMITTED_DIR / "data_quality.json")
    return {key: value for key, value in written.items() if key not in ENVELOPE}


def test_the_committed_manifest_lists_data_quality_and_the_file_agrees_with_its_entry():
    committed_text("manifest.json")
    manifest = read_json(COMMITTED_DIR / "manifest.json")
    entry = next(d for d in manifest["datasets"] if d["name"] == "data_quality")
    assert entry["path"] == "data_quality.json"
    assert (COMMITTED_DIR / entry["path"]).is_file()
    written = read_json(COMMITTED_DIR / entry["path"])
    assert entry["schema_version"] == written["schema_version"] == contract.SCHEMA_VERSION
    # One exporter run wrote both, so they carry the same stamp.
    assert {key: written[key] for key in ("generated_at", "source_commit")} == {
        key: manifest[key] for key in ("generated_at", "source_commit")}


def test_the_committed_data_quality_file_holds_aggregates_in_the_agreed_sections():
    committed_text("data_quality.json")
    written = read_json(COMMITTED_DIR / "data_quality.json")
    assert set(written) == SECTIONS | set(ENVELOPE)
    assert written["flag_names"] == list(flags.FLAG_NAMES)
    table = written["flags_by_year"]
    assert set(table["counts"]) == set(table["shares"]) == set(flags.FLAG_NAMES)
    # Aggregates: a handful of rows per table (22 source-years), never one row per quote.
    for column in (table["source"], table["rows"], written["sources"]["rows"], written["calendar"]["rows"]):
        assert len(column) < 100
    assert {len(column) for column in (table["source"], table["year"], table["rows"])} == {len(table["source"])}


def test_the_committed_gate_passed_and_every_worst_value_is_inside_its_limit():
    committed_text("data_quality.json")
    gate = read_json(COMMITTED_DIR / "data_quality.json")["gate"]
    assert gate["passed"] is True and gate["failures"] == []
    table = gate["thresholds"]
    for i in range(len(table["rule"])):
        within = table["worst"][i] <= table["limit"][i] if table["bound"][i] == "max" else table["worst"][i] >= table["limit"][i]
        assert within, (table["rule"][i], table["source"][i], table["what"][i])


# --- the real store (not in the default run) -------------------------------------------------

@pytest.fixture(scope="module")
def real_store():
    from volbt import config

    built = Store(config.store_dir())
    if not built.has("option_quotes"):
        pytest.skip("no built store: run uv run python tools/build_data.py")
    return built


@pytest.mark.real_data
@pytest.mark.parametrize("name", ["manifest.json", "illustrative_surface.json", "data_quality.json"])
def test_the_committed_files_equal_a_fresh_export_from_the_real_store(tmp_path, real_store, name):
    # Catches "rebuilt the store or changed the report, forgot to re-run the exporter".
    stamp = read_json(COMMITTED_DIR / "manifest.json")
    now = datetime.strptime(stamp["generated_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    export_app_data.build_payloads(tmp_path, lookup_for(stamp["source_commit"]), now,
                                   quality_body=export_app_data.data_quality_body(real_store))
    assert (tmp_path / name).read_bytes() == (COMMITTED_DIR / name).read_bytes(), (
        f"app/public/data/{name} is stale; run: uv run python tools/export_app_data.py")


@pytest.mark.real_data
def test_the_real_export_reports_the_numbers_the_milestone_document_quotes(real_store):
    body = export_app_data.data_quality_body(real_store)
    sources = dict(zip(body["sources"]["source"], zip(body["sources"]["rows"], body["sources"]["dates"])))
    assert sources == {"dolthub": (174_692, 1_196), "optionsdx": (18_847_316, 3_496)}
    calendar = {(s, a): (d, r) for s, a, d, r in zip(*(body["calendar"][c] for c in ("source", "action", "dates", "rows")))}
    assert ("optionsdx", "relabel") not in calendar                 # removed in round 2 of the M1 review
    assert calendar[("optionsdx", "drop")] == (12, 89_852)
    assert calendar[("dolthub", "drop")] == (103, 11_218)
    cross = body["cross_vendor"]
    assert cross["overlap_dates"] == 572
    assert cross["within_thresholds"]["share_within"] == [0.973684, 0.93007]
    assert cross["within_thresholds"]["dates"] == [570, 572]
    by_year = dict(zip(cross["by_year"]["year"], cross["by_year"]["spot_dolthub_share_within"]))
    assert round(by_year[2020], 3) == 0.854                       # 2020 alone: 85.4% within 25 bp
    assert "passed" not in cross
    assert body["gate"]["passed"] is True


@pytest.mark.real_data
def test_the_real_gate_verdict_agrees_with_the_exported_limits_and_worst_values(real_store):
    # Two independent routes to the same answer: the build's gate said "passed", and the worst value
    # the exporter read from the report tables is inside every limit.
    table = export_app_data.data_quality_body(real_store)["gate"]["thresholds"]
    outside = [
        (table["rule"][i], table["source"][i], table["what"][i])
        for i in range(len(table["rule"]))
        if (table["worst"][i] > table["limit"][i] if table["bound"][i] == "max" else table["worst"][i] < table["limit"][i])
    ]
    assert outside == []
