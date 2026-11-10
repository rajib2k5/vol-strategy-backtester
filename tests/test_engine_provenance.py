"""The engine's provenance guards: what a run and an export refuse (milestone 3).

Written by the mutation run: before these, mutants 35 (run_inputs without Store.checked_partitions), 37
(check_ledger without the hash comparison), 38 (the cached reader without its own check_not_after) and 40 (no
fingerprint re-check after the run) survived the whole suite. Each test passes on the code and fails on its mutant.
"""

import shutil
from datetime import date

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import engine_helpers as eh
import engine_store as es
from volbt.data.store import InconsistentStore, Store, YearCache, view
from volbt.engine import report
from volbt.engine.loop import StoreChanged
from volbt.view import LookAheadError

D = date


def copied(engine_store, root) -> Store:
    shutil.copytree(engine_store.root, root)
    return Store(root)


def test_a_stray_file_in_an_input_partition_stops_the_run_without_a_store_check(engine_store, tmp_path):
    store = copied(engine_store, tmp_path / "store")
    partition = store.partition_file("option_quotes", {"source": "optionsdx", "year": 2023}).parent
    (partition / "part-0.parquet.tmp").write_bytes(b"a crashed write")
    with pytest.raises(InconsistentStore):
        eh.run(store, tmp_path / "runs", eh.Scripted({}), check=False, sample_end=D(2023, 1, 10))
    assert not (tmp_path / "runs").exists() or not any((tmp_path / "runs").iterdir())


def test_a_ledger_file_changed_after_the_run_is_refused(engine_store, tmp_path):
    strategy = eh.Scripted({D(2023, 1, 4): eh.open_straddle(D(2023, 2, 17), 400.0, 1)})
    result = eh.run(engine_store, tmp_path / "runs", strategy, sample_end=D(2023, 1, 10))
    path = result.run_dir / "fills" / "part-0.parquet"
    fills = pq.read_table(path).to_pandas()
    assert len(fills)
    fills.loc[0, "price"] = fills.loc[0, "price"] + 1.0
    pq.write_table(pa.Table.from_pandas(fills, schema=pq.read_schema(path), preserve_index=False), path)
    with pytest.raises(report.LedgerChanged):
        report.blotter_body(result.run_dir)


def test_the_cached_private_reader_serves_nothing_after_as_of(engine_store):
    as_of, later = D(2023, 3, 16), D(2023, 3, 17)
    market = view(as_of, "validation", engine_store, cache=YearCache(engine_store, "optionsdx"))
    assert len(market.quotes(as_of))                            # the cache has loaded 2023
    with pytest.raises(LookAheadError):
        market._read("quotes", "optionsdx", "2023", later)


def test_an_input_changed_during_the_run_is_refused_without_a_store_check(engine_store, tmp_path):
    store = copied(engine_store, tmp_path / "store")

    def change_vix(t, book):
        if t == D(2023, 1, 5):
            path = store.checked_table_file("vix")
            frame = pq.read_table(path).to_pandas()
            frame["close"] = frame["close"] + 1.0
            pq.write_table(pa.Table.from_pandas(frame, schema=pq.read_schema(path), preserve_index=False), path)

    with pytest.raises(StoreChanged):
        eh.run(store, tmp_path / "runs", eh.Scripted({}), check=False, sample_end=D(2023, 1, 10),
               on_session_end=change_vix)
    assert list((tmp_path / "runs").glob("run_id=*")) == []           # nothing written, not even the staging folder
