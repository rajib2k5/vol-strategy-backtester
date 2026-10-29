"""The test fixtures are synthetic, shaped like the vendor files, and written only by tools/make_fixtures.py.

Three things are checked here:
1. The generator and the committed files agree, and nothing else sits in tests/fixtures/.
2. What the generator writes passes the schema pin (src/volbt/data/schema.py) through the real
   loaders. The generator spells its columns out on its own, so renaming one there fails here.
3. The shapes the other tests count on: quote dates on SPY sessions, bids at or below asks
   (but two crossed legs), the nulls, and OSI symbols that read back to the same contract.

That no row is a copy of a real vendor row is checked against the real data, by the tests
marked real_data in tests/test_real_data.py.
"""

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import duckdb
import pyarrow.parquet as pq
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import make_fixtures  # noqa: E402

from volbt.data import dolthub, optionsdx, quotes, reference  # noqa: E402
from volbt.data.osi import osi_symbol, parse_osi  # noqa: E402
from volbt.data.schema import DOLTHUB_COLUMNS, check_dolthub_schema  # noqa: E402

FIXTURES = REPO / "tests" / "fixtures"
OPTIONSDX = FIXTURES / "optionsdx_20rows.parquet"

# Dates the vendor stamped on a market closure: not SPY sessions, on purpose (the calendar tests need them).
CLOSURES = {"2022-01-17": date(2022, 1, 14), "2022-06-20": date(2022, 6, 17), "2022-07-04": date(2022, 7, 1)}


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    folder = tmp_path_factory.mktemp("fresh_fixtures")
    return folder, make_fixtures.write_all(folder)


def committed_files() -> set[Path]:
    return {p.relative_to(FIXTURES) for p in FIXTURES.rglob("*") if p.is_file() and p.name != "README.md"}


def spy_bars():
    bars, _ = reference.parse_spy_csv(FIXTURES / "reference" / "yfinance" / "SPY_daily.csv")
    return bars


def long_rows():
    with duckdb.connect() as con:
        return quotes.to_pandas(con.sql(optionsdx.long_rows_sql([OPTIONSDX])).to_arrow_table())


# --- 1. The generator and the committed files -------------------------------------------------------

def test_the_generator_writes_exactly_the_committed_files(generated):
    _, written = generated
    assert set(written) == committed_files()


def test_a_fresh_run_equals_the_committed_fixtures(generated):
    folder, written = generated
    for relative in written:
        if relative.suffix == ".parquet":
            fresh, committed = pq.read_table(folder / relative), pq.read_table(FIXTURES / relative)
            assert fresh.equals(committed), f"{relative} differs from a fresh run of tools/make_fixtures.py"
        else:
            assert (folder / relative).read_bytes() == (FIXTURES / relative).read_bytes(), \
                f"{relative} differs from a fresh run of tools/make_fixtures.py"


# --- 2. What the generator writes follows the pin, through the real loaders ------------------------------

def test_the_generated_files_pass_the_schema_pin(generated):
    folder, _ = generated
    optionsdx.check_file(folder / "optionsdx_20rows.parquet")
    describe = dolthub.parse_describe((folder / "dolthub_describe.csv").read_text(encoding="utf-8"))
    check_dolthub_schema(describe, "generated describe")
    rows = dolthub.parse_spy_rows((folder / "dolthub_spy_20rows.csv").read_text(encoding="utf-8"))
    assert rows.column_names == [name for name, _ in DOLTHUB_COLUMNS]
    reference.parse_spy_csv(folder / "reference" / "yfinance" / "SPY_daily.csv")
    reference.parse_fred_csv(folder / "reference" / "fred" / "DGS3MO.csv")
    reference.parse_cboe_csv(folder / "reference" / "cboe" / "VIX_History.csv")
    reference.parse_cboe_csv(folder / "reference" / "cboe" / "VIX3M_History.csv")


# --- 3. The shapes other tests count on --------------------------------------------------------------------

def test_quote_dates_are_spy_sessions_except_the_three_closures():
    sessions = set(spy_bars()["date"])
    optionsdx_days = {date.fromisoformat(d.strip()) for d in pq.read_table(OPTIONSDX)["[QUOTE_DATE]"].to_pylist()}
    closures = {date.fromisoformat(d) for d in CLOSURES}
    assert optionsdx_days - sessions == closures
    assert not closures & sessions
    dolthub_days = set(dolthub.parse_spy_rows(
        (FIXTURES / "dolthub_spy_20rows.csv").read_text(encoding="utf-8"))["date"].to_pylist())
    assert dolthub_days == {date(2022, 6, 15)} <= sessions


def test_a_closure_dated_row_carries_the_previous_sessions_close():
    # The calendar drops these rows; the quality report's non-session check compares each
    # UNDERLYING_LAST with the previous close, as the real closure dates do (0 cents on all 12).
    close = dict(zip(spy_bars()["date"], spy_bars()["close"]))
    table = pq.read_table(OPTIONSDX).to_pylist()
    for vendor_day, previous in CLOSURES.items():
        underlying = {row["[UNDERLYING_LAST]"] for row in table if row["[QUOTE_DATE]"] == vendor_day}
        assert underlying == {close[previous]}, vendor_day


def test_one_underlying_per_optionsdx_date():
    by_day: dict[str, set[float]] = {}
    for row in pq.read_table(OPTIONSDX).to_pylist():
        by_day.setdefault(row["[QUOTE_DATE]"], set()).add(row["[UNDERLYING_LAST]"])
    assert all(len(values) == 1 for values in by_day.values())


def test_optionsdx_bids_sit_at_or_below_asks_except_two_crossed_legs():
    rows = long_rows()
    both = rows.dropna(subset=["bid", "ask"])
    crossed = both[both["bid"] > both["ask"]]
    # A crossed call on 01-04 and a crossed put on 01-06: the rows the CROSSED flag is tested on.
    assert sorted(zip(crossed["call_put"], crossed["vendor_date"])) == [("C", date(2022, 1, 4)), ("P", date(2022, 1, 6))]
    assert (rows["bid"] == 0).sum() == 15            # zero-bid legs, for ZERO_BID
    assert rows["bid"].isna().sum() == rows["ask"].isna().sum() == 2


def test_dolthub_bids_are_positive_and_at_or_below_asks():
    table = dolthub.parse_spy_rows((FIXTURES / "dolthub_spy_20rows.csv").read_text(encoding="utf-8"))
    assert table.num_rows == 20
    for row in table.to_pylist():
        assert 0 < row["bid"] <= row["ask"], row


def test_the_nulls_are_where_the_flag_tests_need_them():
    table = pq.read_table(OPTIONSDX)
    nulls = {name: table[name].null_count for name in table.column_names if table[name].null_count}
    assert nulls == {"[C_IV]": 15, "[C_VOLUME]": 11, "[C_LAST]": 1, "[C_BID]": 1, "[C_ASK]": 1,
                     "[P_BID]": 1, "[P_ASK]": 1, "[P_LAST]": 1, "[P_VOLUME]": 3}


def test_osi_symbols_read_back_to_the_same_contract():
    rows = long_rows()
    dolt = dolthub.parse_spy_rows((FIXTURES / "dolthub_spy_20rows.csv").read_text(encoding="utf-8")).to_pylist()
    contracts = [("SPY", r.expiry, r.call_put, r.strike) for r in rows.itertuples()]
    contracts += [("SPY", r["expiration"], r["call_put"][0], r["strike"]) for r in dolt]    # "Call" -> "C"
    assert len(contracts) == 60
    for root, expiry, side, strike in contracts:
        assert parse_osi(osi_symbol(root, expiry, side, strike)) == (root, expiry, side, Decimal(str(strike)))
