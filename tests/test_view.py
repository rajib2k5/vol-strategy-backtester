"""ADR-0001 test 2: the MarketView look-ahead guard, the split guard, and no public store reference."""

import json
import subprocess
import sys
import textwrap
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

import volbt.data
import volbt.view
from volbt.data import store as store_module
from volbt.data.store import Store, StoreView, view
from volbt.view import SPLITS, LookAheadError, MarketView, SplitError

D = date
TUE, WED = D(2023, 3, 14), D(2023, 3, 15)


@pytest.fixture
def tiny_store(tmp_path):
    store = Store(tmp_path / "store")
    store.write_table("spy_bars", pd.DataFrame({"date": [TUE, WED], "open": [390.0, 391.0], "high": [395.0, 396.0],
                                                "low": [389.0, 388.0], "close": [394.0, 392.0],
                                                "adj_close": [390.0, 388.0], "volume": [1, 2]}), sort_by=("date",))
    store.write_table("rates", pd.DataFrame({"date": [TUE, WED], "dgs3mo_pct": [4.9, 4.8], "r_cc": [0.048, 0.047]}),
                      sort_by=("date",))
    store.write_table("vix", pd.DataFrame({"date": [TUE, WED], "open": [1.0] * 2, "high": [1.0] * 2,
                                           "low": [1.0] * 2, "close": [23.7, 22.9]}), sort_by=("date",))
    quotes = pd.DataFrame({"source": ["optionsdx"] * 3, "quote_date": [TUE, TUE, WED],
                           "osi_symbol": ["SPY   230317C00390000", "SPY   230317P00390000", "SPY   230317C00390000"],
                           "bid": [5.0, 1.0, 4.0], "year": [2023, 2023, 2023]})
    store.write_table("option_quotes", quotes, sort_by=("quote_date", "osi_symbol"), partition_by=("source", "year"))
    store.write_table("dividends", pd.DataFrame({"ex_date": [TUE, WED], "amount": [1.5, 1.6]}), sort_by=("ex_date",))
    return store


def test_reading_the_next_day_raises_look_ahead(tiny_store):
    market = view(as_of=TUE, split="validation", store=tiny_store)
    with pytest.raises(LookAheadError):
        market.chain(WED)


def test_reading_today_returns_only_today(tiny_store):
    market = view(as_of=TUE, split="validation", store=tiny_store)
    chain = market.chain(TUE)
    assert list(chain["osi_symbol"]) == ["SPY   230317C00390000", "SPY   230317P00390000"]
    assert {d.date() for d in chain["quote_date"]} == {TUE}


def test_history_reads_stop_at_as_of(tiny_store):
    market = view(as_of=TUE, split="validation", store=tiny_store)
    assert market.sessions() == [TUE]
    assert len(market.spy_bars()) == 1 and len(market.rates()) == 1 and len(market.vix()) == 1
    assert list(market.dividends()["amount"]) == [1.5]
    later = view(as_of=WED, split="validation", store=tiny_store)
    assert later.sessions() == [TUE, WED]


def test_a_view_after_the_split_end_raises_split_error(tiny_store):
    # ADR-0001 test 2: a development run asking for 2020-01-02.
    with pytest.raises(SplitError):
        view(as_of=D(2020, 1, 2), split="development", store=tiny_store)
    view(as_of=SPLITS["development"][1], split="development", store=tiny_store)   # the last day is fine


def test_an_unknown_split_is_refused(tiny_store):
    with pytest.raises(ValueError):
        view(as_of=TUE, split="training", store=tiny_store)


def test_the_concrete_view_satisfies_the_protocol(tiny_store):
    market = view(as_of=TUE, split="validation", store=tiny_store)
    for name in [n for n in dir(MarketView) if not n.startswith("_")]:
        assert hasattr(market, name), name


def reachable_data_objects(root, depth=4):
    """Walk public attributes from `root`; return the paths that reach an object from volbt.data."""
    found, seen = [], {id(root)}

    def is_data(obj):
        module = getattr(type(obj), "__module__", "") or ""
        if isinstance(obj, type(volbt.data)):   # a module object
            module = obj.__name__
        return module.startswith("volbt.data")

    def walk(obj, path, level):
        if level == 0:
            return
        for name in dir(obj):
            if name.startswith("_"):
                continue
            try:
                value = getattr(obj, name)
            except Exception:
                continue
            if id(value) in seen or isinstance(value, (int, float, str, bytes, bool, type(None))):
                continue
            seen.add(id(value))
            if is_data(value):
                found.append(f"{path}.{name}")
            walk(value, f"{path}.{name}", level - 1)

    walk(root, "view", depth)
    return found


def test_no_public_attribute_reaches_the_store(tiny_store):
    market = view(as_of=TUE, split="validation", store=tiny_store)
    assert reachable_data_objects(market) == []


def test_the_walk_would_see_a_public_store_reference(tiny_store):
    # Proves the walk can fail: a view-like object that exposes its store is caught.
    class Leaky:
        def __init__(self, store):
            self.store = store

    assert reachable_data_objects(Leaky(tiny_store)) == ["view.store"]


def test_nothing_can_be_attached_to_a_view(tiny_store):
    market = view(as_of=TUE, split="validation", store=tiny_store)
    with pytest.raises(AttributeError):
        market.store = tiny_store
    assert isinstance(market, StoreView) and StoreView.__module__ == store_module.__name__


# --- R1 (M1 review): nothing a view serves depends on data after as_of ---------------------------

MON = D(2023, 3, 13)


def two_futures(tmp_path, variant: int) -> Store:
    """A store whose data on or before TUE is fixed, and whose data after TUE depends on `variant`.

    adj_close differs on EVERY date, the past included, because a dividend-adjusted price is
    scaled by every later dividend: changing the WED dividend changes adj_close on MON and TUE.
    """
    later = 1.0 + variant
    store = Store(tmp_path / f"store{variant}")
    store.write_table("spy_bars", pd.DataFrame({
        "date": [MON, TUE, WED], "open": [389.0, 390.0, 391.0 * later], "high": [394.0, 395.0, 396.0 * later],
        "low": [388.0, 389.0, 388.0 * later], "close": [393.0, 394.0, 392.0 * later],
        "adj_close": [380.0 / later, 381.0 / later, 388.0], "volume": [3, 1, 2 * (1 + variant)]}), sort_by=("date",))
    store.write_table("dividends", pd.DataFrame({"ex_date": [MON, WED], "amount": [1.0, 1.5 * later]}),
                      sort_by=("ex_date",))
    store.write_table("rates", pd.DataFrame({"date": [MON, TUE, WED], "dgs3mo_pct": [4.9, 4.9, 4.8 * later],
                                             "r_cc": [0.048, 0.048, 0.047 * later]}), sort_by=("date",))
    store.write_table("vix", pd.DataFrame({"date": [MON, TUE, WED], "open": [1.0, 1.0, later], "high": [1.0, 1.0, later],
                                           "low": [1.0, 1.0, later], "close": [24.1, 23.7, 22.9 * later]}),
                      sort_by=("date",))
    quotes = pd.DataFrame({"source": ["optionsdx"] * 3, "quote_date": [MON, TUE, WED],
                           "osi_symbol": ["SPY   230317C00390000"] * 3, "bid": [5.5, 5.0, 4.0 * later],
                           "year": [2023] * 3})
    store.write_table("option_quotes", quotes, sort_by=("quote_date", "osi_symbol"), partition_by=("source", "year"))
    return store


def test_changing_only_the_future_changes_nothing_a_view_serves(tmp_path):
    # Metamorphic: two stores that agree up to TUE and disagree after it, adj_close included.
    first, second = (view(as_of=TUE, split="validation", store=two_futures(tmp_path, v)) for v in (0, 1))
    assert first.sessions() == second.sessions() == [MON, TUE]
    for name in ("spy_bars", "dividends", "rates", "vix"):
        a, b = getattr(first, name)(), getattr(second, name)()
        assert len(a) and a.equals(b), name
    for day in (MON, TUE):
        assert first.chain(day).equals(second.chain(day))


def test_the_bars_have_no_adjusted_close(tiny_store):
    bars = view(as_of=WED, split="validation", store=tiny_store).spy_bars()
    assert list(bars.columns) == ["date", "open", "high", "low", "close", "volume"]


def test_dividends_after_as_of_are_not_served(tiny_store):
    assert list(view(as_of=TUE, split="validation", store=tiny_store).dividends()["amount"]) == [1.5]
    assert list(view(as_of=WED, split="validation", store=tiny_store).dividends()["amount"]) == [1.5, 1.6]


class LyingDate(date):
    """A date that says it is never after anything: the reviewer's probe."""

    def __gt__(self, other):
        return False

    def __le__(self, other):
        return True


def test_a_date_subclass_that_lies_about_order_gets_no_chain(tiny_store):
    market = view(as_of=TUE, split="validation", store=tiny_store)
    with pytest.raises(TypeError, match="must be a datetime.date"):
        market.chain(LyingDate(2023, 3, 15))


@pytest.mark.parametrize("value", [datetime(2023, 3, 14), pd.Timestamp(2023, 3, 14), "2023-03-14",
                                   pd.Timestamp(2023, 3, 14).to_pydatetime(), LyingDate(2023, 3, 14)])
def test_only_a_plain_date_is_accepted_even_for_today(tiny_store, value):
    # datetime and Timestamp are subclasses of date; they are refused, not truncated (state the choice).
    market = view(as_of=TUE, split="validation", store=tiny_store)
    with pytest.raises(TypeError):
        market.chain(value)


def test_the_checked_date_is_a_rebuilt_plain_date():
    from volbt.view import exact_date

    day = store_module.check_not_after(D(2023, 3, 14), TUE, "x")
    assert type(day) is date and day == TUE
    for rule in (exact_date, store_module.plain_date):     # the published rule and the store's own copy
        assert type(rule(D(2023, 3, 14), "x")) is date
        with pytest.raises(TypeError):
            rule(LyingDate(2023, 3, 14), "x")


@pytest.mark.parametrize("as_of", [LyingDate(2030, 1, 2), datetime(2019, 12, 31), pd.Timestamp(2019, 12, 31)])
def test_a_view_needs_a_plain_as_of_date(tiny_store, as_of):
    # A lying as_of would pass the split check and bound every read at a later date.
    with pytest.raises(TypeError):
        view(as_of=as_of, split="development", store=tiny_store)


def test_the_private_reader_serves_nothing_after_as_of(tiny_store):
    # Code that reaches _read anyway (the import test bans it in strategies and signals) gets
    # only the view's own queries, each bounded by the view's own as_of.
    market = view(as_of=TUE, split="validation", store=tiny_store)
    read = market._read
    with pytest.raises(ValueError, match="only its own queries"):
        read("SELECT osi_symbol FROM option_quotes WHERE quote_date > ?", [TUE])
    assert read("chain", "optionsdx", "2023", WED).empty          # the SQL bound holds without check_not_after
    assert len(read("chain", "optionsdx", "2023", TUE)) == 2
    with pytest.raises(TypeError):
        read("sessions", WED)                                     # cannot supply the bound itself


# --- round 2 of the M1 review: the bound depends on nothing a strategy can rebind ----------------
#
# volbt.view is the one volbt module a strategy may import. The reviewer's runtime_bypass.py
# rebound `volbt.view.exact_date` to add a day: the view built for Tuesday then had as_of
# Wednesday and served Wednesday's bars, dividends and VIX. The store now checks with its own code.

def a_day_later(value, what):
    return date(value.year, value.month, value.day) + timedelta(days=1)


def test_the_splits_cannot_be_changed_in_place():
    for table in (SPLITS, store_module.SPLITS):
        with pytest.raises(TypeError):
            table["development"] = (D(2010, 1, 4), D(2026, 10, 26))      # the reviewer's patch_splits
        assert all(type(span) is tuple for span in table.values())
    assert SPLITS["development"] == (D(2010, 1, 4), D(2019, 12, 31))


def test_the_store_s_split_table_equals_the_published_one():
    # Two copies on purpose (store.py says why); this keeps them the same table.
    assert dict(store_module.SPLITS) == dict(SPLITS)
    assert store_module.SPLITS is not SPLITS


def test_rebinding_volbt_view_moves_no_bound(tiny_store, monkeypatch):
    # runtime_bypass.py's monkeypatch, done after the store is imported (the order an engine has),
    # plus the split table rebound wholesale. Each is what a strategy could do at import time.
    monkeypatch.setattr(volbt.view, "exact_date", a_day_later)
    monkeypatch.setattr(volbt.view, "SPLITS", {name: (D(2010, 1, 4), D(2030, 1, 1)) for name in SPLITS})
    market = view(as_of=TUE, split="validation", store=tiny_store)
    assert market.as_of == TUE
    assert market.sessions() == [TUE]
    assert [d.date() for d in market.spy_bars()["date"]] == [TUE]
    assert list(market.dividends()["amount"]) == [1.5]
    assert list(market.vix()["close"]) == [23.7]
    assert [d.date() for d in market.rates()["date"]] == [TUE]
    with pytest.raises(LookAheadError):
        market.chain(WED)
    with pytest.raises(SplitError):
        view(as_of=D(2023, 3, 14), split="development", store=tiny_store)


# Run in a fresh interpreter, so volbt.data.store is imported only AFTER volbt.view was rebound.
REBIND_FIRST = textwrap.dedent("""
    import json, sys
    from datetime import date, timedelta
    import volbt.view as vv

    def later(value, what=""):
        return date(value.year, value.month, value.day) + timedelta(days=1)

    vv.exact_date = later
    vv.check_split = lambda as_of, split: later(as_of)
    vv.check_not_after = lambda requested, as_of, what: later(requested)
    vv.SPLITS = {name: (date(2010, 1, 4), date(2030, 1, 1)) for name in vv.SPLITS}

    from volbt.data.store import Store, view       # first imported here

    market = view(as_of=date(2023, 3, 14), split="validation", store=Store(sys.argv[1]))
    out = {"as_of": str(market.as_of), "bars": [str(d.date()) for d in market.spy_bars()["date"]]}
    try:
        out["chain_wed"] = len(market.chain(date(2023, 3, 15)))
    except Exception as error:
        out["chain_wed"] = type(error).__name__
    try:
        view(as_of=date(2023, 3, 14), split="development", store=Store(sys.argv[1]))
        out["development_2023"] = "served"
    except Exception as error:
        out["development_2023"] = type(error).__name__
    print(json.dumps(out))
""")


def test_rebinding_volbt_view_before_the_store_is_imported_moves_no_bound(tiny_store):
    src = Path(volbt.data.__file__).resolve().parents[2]
    result = subprocess.run([sys.executable, "-c", REBIND_FIRST, str(tiny_store.root)], capture_output=True,
                            text=True, cwd=tiny_store.root, env={"PYTHONPATH": str(src), "PATH": "/usr/bin:/bin"})
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"as_of": "2023-03-14", "bars": ["2023-03-14"],
                                         "chain_wed": "LookAheadError", "development_2023": "SplitError"}
