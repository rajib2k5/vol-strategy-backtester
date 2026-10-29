"""The M1 job end to end on the 20-row fixtures: the gate stops a bad build, and a build is
byte-deterministic (ADR-0001 §7): the same inputs give the same bytes, whatever order the rows
arrive in."""

import hashlib
import json
import shutil
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from volbt.data import dolthub, pipeline, quality
from volbt.data.store import Store, write_parquet

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def make_inputs(root: Path, reverse_rows: bool = False) -> tuple[Path, list[Path]]:
    raw = root / "raw"
    shutil.copytree(FIXTURES / "reference", raw)
    rows = dolthub.parse_spy_rows((FIXTURES / "dolthub_spy_20rows.csv").read_text(encoding="utf-8"))
    odx = pq.read_table(FIXTURES / "optionsdx_20rows.parquet")
    if reverse_rows:
        rows, odx = rows.take(list(range(rows.num_rows))[::-1]), odx.take(list(range(odx.num_rows))[::-1])
    write_parquet(rows, raw / pipeline.DOLTHUB_EXPORT)
    kaggle = root / "kaggle"
    kaggle.mkdir()
    pq.write_table(odx, kaggle / "spy_eod_2022.parquet")
    return raw, [kaggle / "spy_eod_2022.parquet"]


def permissive(tables):
    return quality.GateResult(passed=True)


def hashes(store: Store) -> dict[str, str]:
    files = [*store.files(), store.root / "build_summary.json"]
    return {p.relative_to(store.root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def test_the_real_gate_refuses_the_tiny_fixture_and_writes_no_quotes(tmp_path):
    raw, paths = make_inputs(tmp_path)
    store = Store(tmp_path / "store")
    store.write_table("option_quotes", __import__("pandas").DataFrame({"x": [1]}), sort_by=("x",))  # an old build
    with pytest.raises(pipeline.QualityGateError, match="fewer than 1000 rows"):
        pipeline.build(raw=raw, store=store, optionsdx_paths=paths)
    assert not store.table_dir("option_quotes").exists()
    assert store.has("quality_flag_counts")   # the report is kept, so the failure can be read


def test_two_builds_from_the_same_inputs_are_byte_identical(tmp_path):
    first = Store(tmp_path / "a" / "store")
    second = Store(tmp_path / "b" / "store")
    raw_a, paths_a = make_inputs(tmp_path / "a")
    raw_b, paths_b = make_inputs(tmp_path / "b", reverse_rows=True)
    pipeline.build(raw=raw_a, store=first, optionsdx_paths=paths_a, gate=permissive)
    pipeline.build(raw=raw_b, store=second, optionsdx_paths=paths_b, gate=permissive)
    a, b = hashes(first), hashes(second)
    assert "option_quotes/source=optionsdx/year=2022/part-0.parquet" in a
    # The OptionsDX input file differs (rows reversed), so the input fingerprint differs: compare
    # everything else, then the fingerprint on its own.
    summary_a = json.loads((first.root / "build_summary.json").read_text())
    summary_b = json.loads((second.root / "build_summary.json").read_text())
    assert summary_a.pop("input_fingerprint") != summary_b.pop("input_fingerprint")
    assert summary_a == summary_b
    a.pop("build_summary.json"), b.pop("build_summary.json")
    assert a == b


def test_a_rebuild_of_the_same_folder_is_byte_identical(tmp_path):
    raw, paths = make_inputs(tmp_path)
    store = Store(tmp_path / "store")
    pipeline.build(raw=raw, store=store, optionsdx_paths=paths, gate=permissive)
    before = hashes(store)
    pipeline.build(raw=raw, store=store, optionsdx_paths=paths, gate=permissive)
    assert hashes(store) == before


def test_the_fixture_build_drops_every_closure_date_and_keeps_the_diagnostic(tmp_path):
    raw, paths = make_inputs(tmp_path)
    store = Store(tmp_path / "store")
    summary = pipeline.build(raw=raw, store=store, optionsdx_paths=paths, gate=permissive)
    # Three closure dates in the fixture (01-17, 06-20, 07-04), 8 long rows. Each carries the
    # previous session's close and that session has no fixture snapshot: exactly the case the
    # relabel rule used to move. Now all three are dropped, and the check is only reported.
    assert summary["dropped_optionsdx"] == ["2022-01-17", "2022-06-20", "2022-07-04"]
    assert summary["non_session_dates"]["optionsdx"] == {
        "dates": 3, "rows": 8, "underlying_equals_previous_close": 3, "no_underlying": 0,
        "previous_session_has_no_snapshot": 3}
    assert "relabelled" not in summary
    assert [r["vendor_date"] for r in summary["juneteenth_2022"]] == ["2022-06-20"]
    assert summary["rows"] == {"dolthub": 20, "optionsdx": 32}
    clean_dates = store.query("SELECT DISTINCT quote_date FROM option_quotes WHERE source = 'optionsdx'")["quote_date"]
    assert not {d.date().isoformat() for d in clean_dates} & {"2022-01-14", "2022-06-17", "2022-07-01"}
    assert store.has("quality_non_session_dates")
    quotes = store.read_table("option_quotes", order_by="source, quote_date, osi_symbol")
    assert quotes.groupby(["source", "quote_date", "osi_symbol"]).size().max() == 1   # the table's key
    assert store.has("chain_mask") and store.has("cross_vendor_overlap")
