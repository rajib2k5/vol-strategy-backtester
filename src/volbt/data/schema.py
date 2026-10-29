"""The pinned vendor schemas, and the checks that refuse anything else.

A vendor can rename a column, change its type or drop it between two downloads. Code that
reads columns by name would then fail far from the cause, or worse, carry on with a wrong
column. So every loader first compares what it was given with the exact list below, in
order, and raises SchemaError naming the first difference. The lists were measured on
2026-10-28 (ADR-0009, "Columns" and "Table option_chain").
"""

from __future__ import annotations

# OptionsDX (Kaggle parquet): 33 columns, one wide row per (date, expiry, strike). The names
# really do contain the square brackets. Types are pyarrow type names.
OPTIONSDX_COLUMNS: tuple[tuple[str, str], ...] = (
    ("[QUOTE_UNIXTIME]", "int64"),
    ("[QUOTE_READTIME]", "string"),
    ("[QUOTE_DATE]", "string"),
    ("[QUOTE_TIME_HOURS]", "double"),
    ("[UNDERLYING_LAST]", "double"),
    ("[EXPIRE_DATE]", "string"),
    ("[EXPIRE_UNIX]", "int64"),
    ("[DTE]", "double"),
    ("[C_DELTA]", "double"),
    ("[C_GAMMA]", "double"),
    ("[C_VEGA]", "double"),
    ("[C_THETA]", "double"),
    ("[C_RHO]", "double"),
    ("[C_IV]", "double"),
    ("[C_VOLUME]", "double"),
    ("[C_LAST]", "double"),
    ("[C_SIZE]", "string"),
    ("[C_BID]", "double"),
    ("[C_ASK]", "double"),
    ("[STRIKE]", "double"),
    ("[P_BID]", "double"),
    ("[P_ASK]", "double"),
    ("[P_SIZE]", "string"),
    ("[P_LAST]", "double"),
    ("[P_DELTA]", "double"),
    ("[P_GAMMA]", "double"),
    ("[P_VEGA]", "double"),
    ("[P_THETA]", "double"),
    ("[P_RHO]", "double"),
    ("[P_IV]", "double"),
    ("[P_VOLUME]", "double"),
    ("[STRIKE_DISTANCE]", "double"),
    ("[STRIKE_DISTANCE_PCT]", "double"),
)

# DoltHub `option_chain`: 13 columns, as `DESCRIBE option_chain` prints them (SQL types).
# Primary key (date, act_symbol, expiration, strike, call_put).
DOLTHUB_COLUMNS: tuple[tuple[str, str], ...] = (
    ("date", "date"),
    ("act_symbol", "varchar(64)"),
    ("expiration", "date"),
    ("strike", "decimal(7,2)"),
    ("call_put", "varchar(64)"),
    ("bid", "decimal(7,2)"),
    ("ask", "decimal(7,2)"),
    ("vol", "decimal(5,4)"),
    ("delta", "decimal(5,4)"),
    ("gamma", "decimal(5,4)"),
    ("theta", "decimal(5,4)"),
    ("vega", "decimal(5,4)"),
    ("rho", "decimal(5,4)"),
)


class SchemaError(ValueError):
    """The vendor data does not have exactly the pinned columns and types."""


def check_columns(found: list[tuple[str, str]], expected: tuple[tuple[str, str], ...], where: str) -> None:
    """Raise SchemaError unless `found` equals `expected`: same names, same types, same order."""
    if len(found) != len(expected):
        raise SchemaError(f"{where}: expected {len(expected)} columns, found {len(found)}: "
                          f"{[name for name, _ in found]}")
    # Compare position by position, so the message names the first column that differs.
    for position, (got, want) in enumerate(zip(found, expected)):
        if got != want:
            raise SchemaError(f"{where}: column {position} is {got[0]!r} {got[1]}, "
                              f"expected {want[0]!r} {want[1]}")


def check_optionsdx_schema(schema, where: str) -> None:
    """Check a pyarrow schema read from an OptionsDX parquet file (no data is read)."""
    found = [(field.name, str(field.type)) for field in schema]
    check_columns(found, OPTIONSDX_COLUMNS, where)


def check_dolthub_schema(describe_rows: list[tuple[str, str]], where: str) -> None:
    """Check the (Field, Type) pairs of `DESCRIBE option_chain`. Dolt may print types in upper case."""
    found = [(name, sql_type.lower()) for name, sql_type in describe_rows]
    check_columns(found, DOLTHUB_COLUMNS, where)


# --- The DoltHub rows file and the reference downloads -----------------------------------------------
# The pins above were measured on 2026-10-28. The ones below were measured on 2026-10-29. The test
# fixtures in tests/fixtures/ are SYNTHETIC (tools/make_fixtures.py): they copy these lists and
# invent the values. Only the tests marked real_data compare the real vendor files with the lists.
#
# The reference downloads are CSV text, so a column's "type" is what pandas.read_csv gives it on
# the full downloads. "str" is pandas 3's string dtype: the date columns stay strings until the
# parser reads them with an explicit format.
#   yfinance Ticker('SPY').history(auto_adjust=False, actions=True): "2022-06-17 00:00:00-04:00"
#   FRED DGS3MO: "2022-06-17"; an empty cell on a bond-market holiday
#   Cboe VIX and VIX3M history: "06/17/2022"
YFINANCE_SPY_COLUMNS: tuple[tuple[str, str], ...] = (
    ("Date", "str"),
    ("Open", "float64"),
    ("High", "float64"),
    ("Low", "float64"),
    ("Close", "float64"),
    ("Adj Close", "float64"),
    ("Volume", "int64"),
    ("Dividends", "float64"),
    ("Stock Splits", "float64"),
    ("Capital Gains", "float64"),
)
FRED_DGS3MO_COLUMNS: tuple[tuple[str, str], ...] = (
    ("observation_date", "str"),
    ("DGS3MO", "float64"),
)
CBOE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("DATE", "str"),
    ("OPEN", "float64"),
    ("HIGH", "float64"),
    ("LOW", "float64"),
    ("CLOSE", "float64"),
)


def check_dolthub_rows_header(header: str, where: str) -> None:
    """Check the first line of the SPY rows that dolt prints as CSV: the 13 pinned names, in order."""
    found = header.strip().split(",")
    expected = [name for name, _ in DOLTHUB_COLUMNS]
    if len(found) != len(expected):
        raise SchemaError(f"{where}: expected {len(expected)} columns, found {len(found)}: {found}")
    for position, (got, want) in enumerate(zip(found, expected)):
        if got != want:
            raise SchemaError(f"{where}: column {position} is {got!r}, expected {want!r}")


def _check_frame(frame, expected: tuple[tuple[str, str], ...], where: str) -> None:
    check_columns([(str(name), str(dtype)) for name, dtype in frame.dtypes.items()], expected, where)


def check_yfinance_frame(frame, where: str) -> None:
    """Check a SPY CSV read with pandas. No 'Adj Close' means an adjusted download: say so."""
    if "Adj Close" not in frame.columns:
        raise SchemaError(f"{where}: no 'Adj Close' column; was it fetched with auto_adjust=False?")
    _check_frame(frame, YFINANCE_SPY_COLUMNS, where)


def check_fred_frame(frame, where: str) -> None:
    """Check the DGS3MO CSV, read with pandas (empty and '.' cells as nulls)."""
    _check_frame(frame, FRED_DGS3MO_COLUMNS, where)


def check_cboe_frame(frame, where: str) -> None:
    """Check a Cboe VIX or VIX3M history CSV read with pandas."""
    _check_frame(frame, CBOE_COLUMNS, where)
