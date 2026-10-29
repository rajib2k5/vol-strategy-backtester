"""OptionsDX wide rows become long rows: one per contract, call and put apart."""

from datetime import date
from pathlib import Path

import duckdb
import pyarrow.parquet as pq

from volbt.data import optionsdx, quotes

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "optionsdx_20rows.parquet"


def long_rows():
    with duckdb.connect() as con:
        return quotes.to_pandas(con.sql(optionsdx.long_rows_sql([FIXTURE])).to_arrow_table())


def test_twenty_wide_rows_give_forty_long_rows_with_the_raw_columns():
    rows = long_rows()
    assert len(rows) == 40
    assert tuple(rows.columns) == quotes.RAW_COLUMNS
    assert sorted(set(rows["call_put"])) == ["C", "P"]


def test_one_row_read_both_ways():
    # The first fixture row with every value present (some rows are there for their nulls).
    wide = next(r for r in pq.read_table(FIXTURE).to_pylist() if None not in r.values())
    rows = long_rows()
    day = date.fromisoformat(wide["[QUOTE_DATE]"].strip())
    match = rows[(rows["vendor_date"] == day) & (rows["strike"] == wide["[STRIKE]"])]
    call = match[match["call_put"] == "C"].iloc[0]
    put = match[match["call_put"] == "P"].iloc[0]
    assert (call["bid"], call["ask"], call["vendor_iv"]) == (wide["[C_BID]"], wide["[C_ASK]"], wide["[C_IV]"])
    assert (put["bid"], put["ask"], put["underlying_last"]) == (wide["[P_BID]"], wide["[P_ASK]"], wide["[UNDERLYING_LAST]"])
    bid_size, ask_size = (int(x) for x in wide["[C_SIZE]"].split(" x "))
    assert (call["bid_size"], call["ask_size"]) == (bid_size, ask_size)
    assert call["expiry"] == date.fromisoformat(wide["[EXPIRE_DATE]"].strip())


def test_the_files_are_listed_in_year_order(tmp_path):
    folder = tmp_path / optionsdx.DATASET_DIR
    folder.mkdir()
    for year in (2011, 2010):
        (folder / f"spy_eod_{year}.parquet").write_bytes(FIXTURE.read_bytes())
    assert [p.name for p in optionsdx.files(tmp_path)] == ["spy_eod_2010.parquet", "spy_eod_2011.parquet"]
