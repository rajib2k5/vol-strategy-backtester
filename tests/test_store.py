"""The store: parquet written byte-deterministically, read back through DuckDB in a stated order."""

import hashlib
from datetime import date

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from volbt.data.store import Store, data_fingerprint, write_json


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frame(order):
    rows = [("optionsdx", date(2021, 1, 4), "SPY   210115C00370000", 1.5, 2021),
            ("optionsdx", date(2020, 12, 31), "SPY   210115C00370000", 1.4, 2020),
            ("dolthub", date(2021, 1, 4), "SPY   210115P00370000", 0.9, 2021)]
    rows = [rows[i] for i in order]
    return pd.DataFrame(rows, columns=["source", "quote_date", "osi_symbol", "bid", "year"])


def test_partitions_are_hive_folders_without_the_partition_columns(tmp_path):
    store = Store(tmp_path)
    written = store.write_table("option_quotes", frame([0, 1, 2]), sort_by=("quote_date", "osi_symbol"),
                                partition_by=("source", "year"))
    assert [p.relative_to(tmp_path).as_posix() for p in written] == [
        "option_quotes/source=dolthub/year=2021/part-0.parquet",
        "option_quotes/source=optionsdx/year=2020/part-0.parquet",
        "option_quotes/source=optionsdx/year=2021/part-0.parquet"]
    assert pq.read_schema(written[0]).names == ["quote_date", "osi_symbol", "bid"]
    back = store.read_table("option_quotes", order_by="source, quote_date")
    assert list(back["source"]) == ["dolthub", "optionsdx", "optionsdx"]
    assert list(back["year"]) == ["2021", "2020", "2021"]   # folder names come back as text


def test_the_same_rows_in_any_order_give_the_same_bytes(tmp_path):
    a, b = Store(tmp_path / "a"), Store(tmp_path / "b")
    a.write_table("t", frame([0, 1, 2]), sort_by=("quote_date", "osi_symbol"), partition_by=("source", "year"))
    b.write_table("t", frame([2, 0, 1]), sort_by=("quote_date", "osi_symbol"), partition_by=("source", "year"))
    assert [sha(p) for p in a.files()] == [sha(p) for p in b.files()]


def test_the_same_rows_from_pandas_or_from_arrow_give_the_same_bytes(tmp_path):
    # pandas attaches schema metadata (its own version, each column's pandas dtype); an arrow
    # table built directly has none. Same rows, so the bytes must be the same too: otherwise a
    # store's hash would depend on the library versions and the route the rows took.
    rows = frame([0, 1, 2])
    # The arrow types are the ones pandas gives these columns in the pinned environment (uv.lock).
    arrow = pa.table({"source": pa.array(rows["source"], pa.large_string()),
                      "quote_date": pa.array(rows["quote_date"], pa.date32()),
                      "osi_symbol": pa.array(rows["osi_symbol"], pa.large_string()),
                      "bid": pa.array(rows["bid"], pa.float64()),
                      "year": pa.array(rows["year"], pa.int64())})
    a, b = Store(tmp_path / "a"), Store(tmp_path / "b")
    a.write_table("t", rows, sort_by=("quote_date", "osi_symbol"))
    b.write_table("t", arrow, sort_by=("quote_date", "osi_symbol"))
    assert [sha(p) for p in a.files()] == [sha(p) for p in b.files()]


def test_different_rows_give_different_bytes(tmp_path):
    a, b = Store(tmp_path / "a"), Store(tmp_path / "b")
    a.write_table("t", frame([0, 1, 2]), sort_by=("quote_date",))
    changed = frame([0, 1, 2])
    changed.loc[0, "bid"] = 1.51
    b.write_table("t", changed, sort_by=("quote_date",))
    assert sha(a.files()[0]) != sha(b.files()[0])


def test_rewriting_a_table_removes_partitions_that_are_gone(tmp_path):
    store = Store(tmp_path)
    store.write_table("t", frame([0, 1, 2]), sort_by=("quote_date",), partition_by=("source",))
    store.write_table("t", frame([0, 1]), sort_by=("quote_date",), partition_by=("source",))
    assert [p.parent.name for p in store.files()] == ["source=optionsdx"]


def test_reads_need_an_explicit_order(tmp_path):
    store = Store(tmp_path)
    store.write_table("t", frame([0, 1, 2]), sort_by=("quote_date",))
    with pytest.raises(TypeError):
        store.read_table("t")   # order_by is a required argument


def test_the_fingerprint_depends_on_bytes_and_names_not_on_location(tmp_path):
    for folder in ("x", "y"):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "a.csv").write_text("1,2\n")
    fx = data_fingerprint([tmp_path / "x" / "a.csv"], tmp_path / "x")
    assert fx == data_fingerprint([tmp_path / "y" / "a.csv"], tmp_path / "y")
    (tmp_path / "y" / "a.csv").write_text("1,3\n")
    assert fx != data_fingerprint([tmp_path / "y" / "a.csv"], tmp_path / "y")


def test_json_is_stable_and_refuses_nan(tmp_path):
    write_json({"b": 1, "a": [1.5]}, tmp_path / "s.json")
    assert (tmp_path / "s.json").read_bytes() == b'{\n "a": [\n  1.5\n ],\n "b": 1\n}\n'
    with pytest.raises(ValueError):
        write_json({"x": float("nan")}, tmp_path / "n.json")
