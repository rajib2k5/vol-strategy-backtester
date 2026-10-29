"""ADR-0009 test 1: the schema pin. The loaders accept exactly the vendor columns and types.

The fixtures are SYNTHETIC (tools/make_fixtures.py writes them, 20 rows each): they have the
pinned names, order and types, and made-up values. The real files are checked against the same
pin by the real_data tests in tests/test_real_data.py. Every mutant below is one realistic way a
vendor file could change between two downloads.
"""

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from volbt.data import dolthub, optionsdx, reference
from volbt.data.schema import (CBOE_COLUMNS, DOLTHUB_COLUMNS, FRED_DGS3MO_COLUMNS, OPTIONSDX_COLUMNS,
                               YFINANCE_SPY_COLUMNS, SchemaError, check_dolthub_schema)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
OPTIONSDX_FIXTURE = FIXTURES / "optionsdx_20rows.parquet"


def test_the_pins_have_33_and_13_columns():
    assert len(OPTIONSDX_COLUMNS) == 33
    assert len(DOLTHUB_COLUMNS) == 13
    assert OPTIONSDX_COLUMNS[0] == ("[QUOTE_UNIXTIME]", "int64")
    assert OPTIONSDX_COLUMNS[-1] == ("[STRIKE_DISTANCE_PCT]", "double")
    assert DOLTHUB_COLUMNS[3] == ("strike", "decimal(7,2)")


def test_the_optionsdx_fixture_passes_and_has_20_rows():
    optionsdx.check_file(OPTIONSDX_FIXTURE)
    assert pq.read_metadata(OPTIONSDX_FIXTURE).num_rows == 20


def _write_mutant(tmp_path: Path, table: pa.Table) -> Path:
    path = tmp_path / "mutant.parquet"
    pq.write_table(table, path)
    return path


def _fixture() -> pa.Table:
    return pq.read_table(OPTIONSDX_FIXTURE)


def test_a_renamed_column_fails(tmp_path):
    table = _fixture()
    names = table.column_names
    names[17] = "C_BID"  # the brackets dropped
    with pytest.raises(SchemaError, match=r"column 17 is 'C_BID'"):
        optionsdx.check_file(_write_mutant(tmp_path, table.rename_columns(names)))


def test_a_changed_type_fails(tmp_path):
    table = _fixture()
    index = table.column_names.index("[QUOTE_DATE]")
    # A vendor that starts shipping real dates instead of "YYYY-MM-DD" strings.
    as_date = pa.compute.strptime(table["[QUOTE_DATE]"], format="%Y-%m-%d", unit="s").cast(pa.date32())
    with pytest.raises(SchemaError, match=r"\[QUOTE_DATE\]' date32"):
        optionsdx.check_file(_write_mutant(tmp_path, table.set_column(index, "[QUOTE_DATE]", as_date)))


def test_float32_prices_fail(tmp_path):
    table = _fixture()
    index = table.column_names.index("[C_BID]")
    with pytest.raises(SchemaError, match="float"):
        optionsdx.check_file(_write_mutant(
            tmp_path, table.set_column(index, "[C_BID]", table["[C_BID]"].cast(pa.float32()))))


def test_a_dropped_column_fails(tmp_path):
    with pytest.raises(SchemaError, match="expected 33 columns, found 32"):
        optionsdx.check_file(_write_mutant(tmp_path, _fixture().drop_columns(["[C_SIZE]"])))


def test_reordered_columns_fail(tmp_path):
    table = _fixture()
    names = table.column_names
    swapped = names[:17] + [names[18], names[17]] + names[19:]  # [C_ASK] before [C_BID]
    with pytest.raises(SchemaError, match="column 17"):
        optionsdx.check_file(_write_mutant(tmp_path, table.select(swapped)))


def test_the_dolthub_describe_fixture_passes():
    rows = dolthub.parse_describe((FIXTURES / "dolthub_describe.csv").read_text(encoding="utf-8"))
    check_dolthub_schema(rows, "fixture")
    assert len(rows) == 13


@pytest.mark.parametrize("mutate, message", [
    (lambda rows: rows[:-1], "expected 13 columns, found 12"),
    (lambda rows: [*rows[:3], ("strike", "decimal(8,2)"), *rows[4:]], "column 3"),
    (lambda rows: [*rows[:7], ("iv", "decimal(5,4)"), *rows[8:]], "column 7 is 'iv'"),
    (lambda rows: [*rows, ("volume", "int")], "found 14"),
])
def test_dolthub_schema_mutants_fail(mutate, message):
    rows = dolthub.parse_describe((FIXTURES / "dolthub_describe.csv").read_text(encoding="utf-8"))
    with pytest.raises(SchemaError, match=message):
        check_dolthub_schema(mutate(rows), "mutant")


def test_upper_case_sql_types_are_accepted():
    # Some dolt versions print DECIMAL(7,2); the type is the same.
    rows = [(name, sql_type.upper()) for name, sql_type in DOLTHUB_COLUMNS]
    check_dolthub_schema(rows, "upper")


def test_the_dolthub_rows_parse_with_the_pinned_types():
    table = dolthub.parse_spy_rows((FIXTURES / "dolthub_spy_20rows.csv").read_text(encoding="utf-8"))
    assert table.num_rows == 20
    assert table.column_names == [name for name, _ in DOLTHUB_COLUMNS]
    assert table.schema.field("date").type == pa.date32()
    assert table.schema.field("expiration").type == pa.date32()
    assert table.schema.field("strike").type == pa.float64()
    assert set(table["call_put"].to_pylist()) <= {"Call", "Put"}
    assert table["act_symbol"].to_pylist() == ["SPY"] * 20
    # 290.00 Call, bid 65.95, ask 66.75 (made-up values): the first row, read exactly.
    first = table.slice(0, 1).to_pylist()[0]
    assert (first["strike"], first["bid"], first["ask"], first["vol"]) == (290.0, 65.95, 66.75, 0.3977)


# --- The DoltHub rows file: the 13 pinned names, in order -----------------------------------------------

DOLTHUB_ROWS = FIXTURES / "dolthub_spy_20rows.csv"


@pytest.mark.parametrize("mutate, message", [
    (lambda names: names[:-1], "expected 13 columns, found 12"),
    (lambda names: [*names, "volume"], "expected 13 columns, found 14"),
    (lambda names: [*names[:7], "iv", *names[8:]], "column 7 is 'iv', expected 'vol'"),
    (lambda names: [*names[:5], names[6], names[5], *names[7:]], "column 5 is 'ask', expected 'bid'"),
])
def test_dolthub_rows_with_a_changed_header_fail(mutate, message):
    header, body = DOLTHUB_ROWS.read_text(encoding="utf-8").split("\n", 1)
    mutant = ",".join(mutate(header.split(","))) + "\n" + body
    with pytest.raises(SchemaError, match=message):
        dolthub.parse_spy_rows(mutant)


# --- The reference downloads: header and column types ------------------------------------------------------

REFERENCE = FIXTURES / "reference"


def test_the_reference_pins_name_every_column_and_type():
    # Spelled out here, not read from the module: a test that took the lists from the code
    # under test would shrink with it.
    assert YFINANCE_SPY_COLUMNS == (
        ("Date", "str"), ("Open", "float64"), ("High", "float64"), ("Low", "float64"), ("Close", "float64"),
        ("Adj Close", "float64"), ("Volume", "int64"), ("Dividends", "float64"), ("Stock Splits", "float64"),
        ("Capital Gains", "float64"))
    assert FRED_DGS3MO_COLUMNS == (("observation_date", "str"), ("DGS3MO", "float64"))
    assert CBOE_COLUMNS == (("DATE", "str"), ("OPEN", "float64"), ("HIGH", "float64"), ("LOW", "float64"),
                            ("CLOSE", "float64"))


def test_the_reference_fixtures_pass_their_pins():
    bars, dividends = reference.parse_spy_csv(REFERENCE / "yfinance" / "SPY_daily.csv")
    assert (len(bars), len(dividends)) == (19, 1)
    assert len(reference.parse_fred_csv(REFERENCE / "fred" / "DGS3MO.csv")) == 19
    assert len(reference.parse_cboe_csv(REFERENCE / "cboe" / "VIX_History.csv")) == 19
    assert len(reference.parse_cboe_csv(REFERENCE / "cboe" / "VIX3M_History.csv")) == 19


@pytest.mark.parametrize("relative, parse, old, new, message", [
    ("yfinance/SPY_daily.csv", reference.parse_spy_csv, ",Close,", ",Last,", "column 4 is 'Last' float64"),
    ("yfinance/SPY_daily.csv", reference.parse_spy_csv, ",Capital Gains", "", "expected 10 columns, found 9"),
    ("fred/DGS3MO.csv", reference.parse_fred_csv, "observation_date", "date", "column 0 is 'date' str"),
    ("cboe/VIX_History.csv", reference.parse_cboe_csv, "OPEN,HIGH", "HIGH,OPEN", "column 1 is 'HIGH'"),
    ("cboe/VIX3M_History.csv", reference.parse_cboe_csv, ",CLOSE", ",SETTLE", "column 4 is 'SETTLE'"),
])
def test_a_reference_file_with_a_changed_header_fails(tmp_path, relative, parse, old, new, message):
    text = (REFERENCE / relative).read_text(encoding="utf-8").replace(old, new, 1)
    mutant = tmp_path / "mutant.csv"
    mutant.write_text(text, encoding="utf-8", newline="\n")
    with pytest.raises(SchemaError, match=message):
        parse(mutant)


def test_a_reference_column_with_a_changed_type_fails(tmp_path):
    # Volume as a decimal: a vendor that starts to ship fractional shares.
    frame = pd.read_csv(REFERENCE / "yfinance" / "SPY_daily.csv")
    frame["Volume"] = frame["Volume"] + 0.5
    mutant = tmp_path / "spy.csv"
    frame.to_csv(mutant, index=False, lineterminator="\n")
    with pytest.raises(SchemaError, match="column 6 is 'Volume' float64, expected 'Volume' int64"):
        reference.parse_spy_csv(mutant)
    # A Cboe price column that holds text reads as strings (pandas would turn "n/a" into a null).
    vix = (REFERENCE / "cboe" / "VIX_History.csv").read_text(encoding="utf-8").splitlines()
    vix[1] = "01/03/2022,oops," + vix[1].split(",", 2)[2]
    mutant = tmp_path / "vix.csv"
    mutant.write_text("\n".join(vix) + "\n", encoding="utf-8", newline="\n")
    with pytest.raises(SchemaError, match="column 1 is 'OPEN' str, expected 'OPEN' float64"):
        reference.parse_cboe_csv(mutant)
