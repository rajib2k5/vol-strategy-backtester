"""The volbt.build step runner: steps read through the store and write through the store."""

from datetime import date

import pandas as pd

from volbt import build
from volbt.data.store import Store


def test_a_step_reads_and_writes_through_the_store(tmp_path):
    store = Store(tmp_path)
    store.write_table("spy_bars", pd.DataFrame({"date": [date(2022, 1, 3), date(2022, 1, 4), date(2023, 1, 3)],
                                                "close": [411.26, 409.87, 332.14]}), sort_by=("date",))

    def closes_per_year(tables):
        bars = tables["spy_bars"]
        years = pd.to_datetime(bars["date"]).dt.year.rename("year")
        return bars.groupby(years).size().rename("sessions").reset_index()

    step = build.Step("sessions_per_year", (("spy_bars", "date"),), closes_per_year, sort_by=("year",))
    assert build.run((step,), store) == {"sessions_per_year": 2}
    back = store.read_table("sessions_per_year", order_by="year")
    assert list(back["year"]) == [2022, 2023] and list(back["sessions"]) == [2, 1]


def test_a_later_step_can_read_an_earlier_step_s_table(tmp_path):
    store = Store(tmp_path)
    store.write_table("a", pd.DataFrame({"x": [1, 2]}), sort_by=("x",))
    double = build.Step("b", (("a", "x"),), lambda t: t["a"].assign(x=t["a"]["x"] * 2), sort_by=("x",))
    total = build.Step("c", (("b", "x"),), lambda t: pd.DataFrame({"s": [t["b"]["x"].sum()]}), sort_by=("s",))
    build.run((double, total), store)
    assert store.read_table("c", order_by="s")["s"].tolist() == [6]


def test_the_m2_pricing_build_writes_the_three_tables_adr_0001_names():
    # ADR-0001 §4: volbt.build owns the pricing build of these three tables (tests/test_pricing_build.py).
    assert build.PRICING_TABLES == ("expiry_forwards", "quote_iv", "smile_fits")
