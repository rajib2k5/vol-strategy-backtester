"""option_quotes: the clean long table, one row per (source, quote_date, osi_symbol), with its flags.

Input: raw long rows from any source, with the columns RAW_COLUMNS (optionsdx.long_rows_sql
and dolthub.long_rows_sql produce them). Output: CLEAN_COLUMNS.

Four steps:
1. One snapshot per (source, vendor date). An OptionsDX date must have exactly one
   UNDERLYING_LAST (measured: it does); otherwise we stop.
2. The calendar decides each vendor date: kept as a session, or dropped (calendar.py).
3. DuckDB joins the SPY close and, for every contract, its previous snapshot (bid, ask and the
   SPY close then), using a window LAG over the contract ordered by date.
4. numpy sets the 13 flag bits (flags.py) and builds the OSI symbol (osi.py).

Rows are flagged, never deleted, except the non-session rows the calendar drops. The table
returned with the clean rows (`date_map`) says what happened to every vendor date and how many
rows it held, so the quality report can count the drops.
"""

from __future__ import annotations

import duckdb
import pandas as pd
import pyarrow as pa

from volbt.data.calendar import build_date_map, sessions_from_bars
from volbt.data.flags import quote_flags
from volbt.data.osi import osi_symbols

RAW_SCHEMA = pa.schema([
    ("source", pa.string()), ("vendor_date", pa.date32()), ("expiry", pa.date32()),
    ("strike", pa.float64()), ("call_put", pa.string()), ("bid", pa.float64()), ("ask", pa.float64()),
    ("last", pa.float64()), ("volume", pa.float64()), ("bid_size", pa.int64()), ("ask_size", pa.int64()),
    ("vendor_iv", pa.float64()), ("vendor_delta", pa.float64()), ("vendor_gamma", pa.float64()),
    ("vendor_vega", pa.float64()), ("vendor_theta", pa.float64()), ("vendor_rho", pa.float64()),
    ("underlying_last", pa.float64()),
])
RAW_COLUMNS = tuple(RAW_SCHEMA.names)

CLEAN_COLUMNS = (
    "source", "quote_date", "osi_symbol", "expiry", "strike", "call_put", "bid", "ask", "last",
    "volume", "bid_size", "ask_size", "vendor_iv", "vendor_delta", "vendor_gamma", "vendor_vega",
    "vendor_theta", "vendor_rho", "underlying_last", "spy_close", "vendor_quote_date",
    "quality_flags", "year",
)
# The key of option_quotes. osi_symbol is a function of (call_put, expiry, strike) for one root.
KEY = ("source", "quote_date", "osi_symbol")


def to_pandas(table: pa.Table) -> pd.DataFrame:
    """Arrow -> pandas keeping dates as dates (datetime.date) and nullable integers as integers."""
    mapping = {pa.date32(): pd.ArrowDtype(pa.date32()), pa.int64(): pd.Int64Dtype(), pa.int32(): pd.Int32Dtype()}
    return table.to_pandas(types_mapper=mapping.get)


def snapshot_summary(con: duckdb.DuckDBPyConnection, raw: str) -> pd.DataFrame:
    """source, vendor_date, underlying_last, rows. Raises if a date carries two underlyings."""
    frame = to_pandas(con.sql(f"""
        SELECT source, vendor_date,
               min(underlying_last) AS underlying_last, max(underlying_last) AS underlying_max,
               count(*) AS rows
        FROM {raw} GROUP BY source, vendor_date ORDER BY source, vendor_date""").to_arrow_table())
    two = frame[frame["underlying_last"].notna() & (frame["underlying_last"] != frame["underlying_max"])]
    if len(two):
        raise ValueError(f"more than one UNDERLYING_LAST on {two[['source', 'vendor_date']].to_dict('records')[:5]}")
    return frame.drop(columns="underlying_max")


def _arrow_dates(frame: pd.DataFrame, columns: dict[str, pa.DataType]) -> pa.Table:
    return pa.Table.from_pandas(frame[list(columns)], schema=pa.schema(list(columns.items())), preserve_index=False)


def clean(con: duckdb.DuckDBPyConnection, raw: str, bars: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Clean the raw long rows in table/view `raw` of connection `con`. Returns (clean, date_map)."""
    date_map = build_date_map(snapshot_summary(con, raw), bars)
    con.register("date_map", _arrow_dates(date_map, {
        "source": pa.string(), "vendor_date": pa.date32(), "quote_date": pa.date32(),
        "action": pa.string(), "flags": pa.int32()}))
    con.register("sessions", _arrow_dates(sessions_from_bars(bars), {"date": pa.date32(), "close": pa.float64()}))
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE clean_stage AS
        WITH mapped AS (
            SELECT r.*, m.quote_date, m.flags AS date_flags,
                   CAST(round(r.strike * 1000) AS BIGINT) AS strike_milli
            FROM {raw} AS r
            JOIN date_map AS m ON m.source = r.source AND m.vendor_date = r.vendor_date
            WHERE m.action <> 'drop'
        )
        SELECT mapped.*, s.close AS spy_close,
               -- The same contract's previous snapshot: one source, one side, one expiry, one strike.
               lag(mapped.bid) OVER contract AS prev_bid,
               lag(mapped.ask) OVER contract AS prev_ask,
               lag(s.close) OVER contract AS prev_spy_close
        FROM mapped JOIN sessions AS s ON s.date = mapped.quote_date
        WINDOW contract AS (PARTITION BY mapped.source, mapped.call_put, mapped.expiry, mapped.strike_milli
                            ORDER BY mapped.quote_date)""")
    clashes = con.execute("""
        SELECT count(*) FROM (SELECT 1 FROM clean_stage
                              GROUP BY source, quote_date, call_put, expiry, strike_milli HAVING count(*) > 1)
    """).fetchall()[0][0]
    if clashes:
        raise ValueError(f"{clashes} contracts appear twice on one quote date after the calendar step")
    stage = to_pandas(con.sql("""
        SELECT * FROM clean_stage ORDER BY source, quote_date, call_put, expiry, strike_milli
    """).to_arrow_table())
    con.execute("DROP TABLE clean_stage")

    stage["osi_symbol"] = osi_symbols(stage["expiry"], stage["call_put"], stage["strike"]).to_numpy()
    stage["quality_flags"] = quote_flags(stage)
    stage["vendor_quote_date"] = stage["vendor_date"]
    stage["year"] = pd.to_datetime(stage["quote_date"]).dt.year.astype("int32")
    clean_rows = stage[list(CLEAN_COLUMNS)].sort_values(list(KEY), kind="stable").reset_index(drop=True)
    return clean_rows, date_map


def clean_quotes(raw: pd.DataFrame, bars: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The same as `clean`, for a raw table held in pandas (tests and small inputs)."""
    with duckdb.connect() as con:
        con.register("raw_quotes", pa.Table.from_pandas(raw[list(RAW_COLUMNS)], schema=RAW_SCHEMA,
                                                         preserve_index=False))
        return clean(con, "raw_quotes", bars)
