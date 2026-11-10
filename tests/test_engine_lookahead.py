"""Look-ahead through the engine (the M3 plan §4): the perturb-the-future test, the prefix property, and M1's view
guards extended to the year cache. On tests/engine_store.py's made-up store.

t0 = 2023-03-16, the eve of an ex-date that is also a monthly expiry: the reference strategy with exit_dte 0 holds a
short 2023-03-17 400 straddle whose call is in the money, and the call rule assigns it early on the PROJECTED
dividend 1.818 (fewer than 8 paid, so the last paid one), not the 1.616 that is booked on 03-17.

    (a)  store B equals store A up to t0 and has every later value tripled and permuted (bars, VIX, rates, dividends,
         quotes, volumes; the set of session dates and each contract kept), its derived tables rebuilt by the M2
         pricing build. A run stopped at t0 writes the same bytes on A and on B, and leaves the same book. Also at a
         second t0, the 2023-04-03 gap, where an early put assignment reads sigma for a later expiry.
    (b)  the prefix property: the full run's rows dated <= t0 equal the rows of the run stopped at t0.
    view a cached view serves nothing after its as_of, and no public attribute of it reaches volbt.data.
"""

from datetime import date

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import engine_helpers as eh
import engine_store as es
import volbt.data
from volbt import build
from volbt.data import flags
from volbt.data.store import Store, YearCache, file_sha256, view
from volbt.strategies.reference import RollingShortStraddle

D = date
T0 = D(2023, 3, 16)
PARTITION = {"source": "optionsdx", "year": 2023}
DAY_TABLES = {"option_quotes": "osi_symbol", "quote_iv": "osi_symbol", "expiry_forwards": "expiry",
              "smile_fits": "expiry"}
REFERENCE_TABLES = {"spy_bars": "date", "rates": "date", "dividends": "ex_date", "vix": "date"}
# The values of each input table that the perturbation multiplies by 3 and permutes.
FUTURE_VALUES = {"spy_bars": ["open", "high", "low", "close", "adj_close", "volume"], "rates": ["dgs3mo_pct", "r_cc"],
                 "dividends": ["amount"], "vix": ["open", "high", "low", "close"]}


def reference_frame(store, name):
    return pq.read_table(store.checked_table_file(name)).to_pandas()


def as_dates(series):
    return pd.to_datetime(series).dt.date.to_numpy()


def tripled_and_reversed(values, future):
    """`values` with the entries at `future` (indices in date order) tripled and reversed across those dates."""
    out = values.copy()
    moved = out[future][::-1] * 3
    out[future] = np.round(moved, 6) if np.issubdtype(out.dtype, np.floating) else moved
    return out


def perturbed_store(source: Store, root, t0: date) -> Store:
    """Store B: source's inputs with every value dated after t0 tripled and permuted, then priced by the M2 build."""
    target = Store(root)
    quotes = pq.read_table(source.partition_file("option_quotes", PARTITION)).to_pandas()
    quotes["source"], quotes["year"] = PARTITION["source"], PARTITION["year"]
    day = as_dates(quotes["quote_date"])
    later = sorted({d for d in day if d > t0})
    swap = dict(zip(later, later[::-1]))                  # a permutation of the future snapshot dates
    spots = quotes.groupby(day)[["spy_close", "underlying_last"]].first()
    parts = []
    for _, contract in quotes.groupby("osi_symbol", sort=True):
        # Each contract keeps its identity and its quote dates; its future bids, asks and volumes move between them.
        contract = contract.iloc[np.argsort(as_dates(contract["quote_date"]), kind="stable")].copy()
        future = np.flatnonzero(as_dates(contract["quote_date"]) > t0)
        for column in ("bid", "ask"):
            contract[column] = np.round(tripled_and_reversed(contract[column].to_numpy(), future), 2)
        contract["volume"] = tripled_and_reversed(contract["volume"].to_numpy(), future)
        parts.append(contract)
    quotes = pd.concat(parts, ignore_index=True)
    day = as_dates(quotes["quote_date"])
    future = day > t0
    for column in ("spy_close", "underlying_last"):
        quotes.loc[future, column] = [round(3 * spots.loc[swap[d], column], 2) for d in day[future]]
    bid, ask = flags.cents(quotes["bid"].to_numpy()), flags.cents(quotes["ask"].to_numpy())
    bits = flags.mid_flags(bid, ask).astype(np.int64)
    bits |= np.where(as_dates(quotes["expiry"]) == day, flags.EXPIRY_DAY, 0)
    quotes["quality_flags"] = np.where(future, bits, quotes["quality_flags"].to_numpy())
    target.write_table("option_quotes", quotes, sort_by=("quote_date", "osi_symbol"), partition_by=("source", "year"))
    for name, column in REFERENCE_TABLES.items():
        frame = reference_frame(source, name).sort_values(column, kind="stable").reset_index(drop=True)
        future = np.flatnonzero(as_dates(frame[column]) > t0)
        for value in FUTURE_VALUES[name]:
            frame[value] = tripled_and_reversed(frame[value].to_numpy(), future)
        target.write_table(name, frame, sort_by=(column,))
    build.build_pricing(target)
    return target


# The second t0, the -8% gap: the short 2023-04-21 415 put is deep in the money and the put rule assigns it early with
# the N = 500 lattice at the surface IV of its strike. At 03-16 the only early decision is for a contract expiring
# at t0 + 1, whose sigma no later surface has, so a sigma read from t0 + 1 shows only at this t0.
T0S = (T0, es.GAP_DATE)
EARLY_AT_T0 = {T0: (es.symbol(D(2023, 3, 17), "C", 400.0), "call_closed_form", D(2023, 3, 17)),
               es.GAP_DATE: (es.symbol(D(2023, 4, 21), "P", 415.0), "crr", D(2023, 4, 4))}


@pytest.fixture(scope="module")
def stores_b(engine_store, tmp_path_factory):
    return {t0: perturbed_store(engine_store, tmp_path_factory.mktemp(f"store_b_{t0}"), t0) for t0 in T0S}


def ledger_files(result):
    return sorted(path.relative_to(result.run_dir).as_posix() for path in result.run_dir.rglob("*.parquet"))


@pytest.mark.parametrize("t0", T0S)
def test_store_b_equals_store_a_up_to_t0_and_differs_after_it(engine_store, stores_b, t0):
    # The premise of (a): what a session <= t0 can read is the same in A and B, and the future is not.
    store_b = stores_b[t0]
    for name, key in {**DAY_TABLES, **REFERENCE_TABLES}.items():
        if name in DAY_TABLES:
            a, b = (pq.read_table(s.partition_file(name, PARTITION)).to_pandas() for s in (engine_store, store_b))
            column = "quote_date"
        else:
            a, b = reference_frame(engine_store, name), reference_frame(store_b, name)
            column = key
        past_a, past_b = (f[as_dates(f[column]) <= t0].reset_index(drop=True) for f in (a, b))
        future_a, future_b = (f[as_dates(f[column]) > t0].reset_index(drop=True) for f in (a, b))
        assert len(past_a) and pa.Table.from_pandas(past_a).equals(pa.Table.from_pandas(past_b)), name
        assert len(future_a) == len(future_b), name
        if len(future_a):                   # no dividend goes ex after the gap: that table has no future rows
            assert not pa.Table.from_pandas(future_a).equals(pa.Table.from_pandas(future_b)), name
        assert sorted(set(as_dates(future_a[column]))) == sorted(set(as_dates(future_b[column]))), name
    if t0 == T0:
        dividends = reference_frame(store_b, "dividends")
        assert dividends.loc[as_dates(dividends["ex_date"]) == D(2023, 3, 17), "amount"].tolist() == [
            pytest.approx(4.848)]          # 3 x 1.616


@pytest.mark.parametrize("t0", T0S)
def test_a_run_stopped_at_t0_writes_the_same_ledger_on_a_and_on_b(engine_store, stores_b, tmp_path, t0):
    runs = {name: eh.run(store, tmp_path / name, RollingShortStraddle(exit_dte=0), stop_after=t0)
            for name, store in (("a", engine_store), ("b", stores_b[t0]))}
    a, b = runs["a"], runs["b"]
    assert a.last_session == b.last_session == t0
    assert a.digest == b.digest
    files = ledger_files(a)
    assert files == ledger_files(b) and len(files) == 14
    # runs/part-0.parquet names each store's data_fingerprint, which differs by design (B's inputs differ after
    # t0); every other ledger file must be the same bytes, and the runs rows equal in every other column.
    for name in files:
        if name != "runs/part-0.parquet":
            assert file_sha256(a.run_dir / name) == file_sha256(b.run_dir / name), name
    run_a, run_b = eh.table(a, "runs"), eh.table(b, "runs")
    assert (run_a["data_fingerprint"] != run_b["data_fingerprint"]).all()
    others = [c for c in run_a.columns if c != "data_fingerprint"]
    assert run_a[others].equals(run_b[others])
    # The case t0 was chosen for: an ITM short lot assigned early, decided at t0 for t0 + 1.
    events = eh.table(a, "expiry_events")
    early = events[events["session_date"] == t0]
    columns = ["osi_symbol", "decision_method", "effective_date"]
    assert early["event_type"].tolist() == ["early_assigned"] and early["decision_iv"].notna().all()
    assert [tuple(row) for row in early[columns].values.tolist()] == [EARLY_AT_T0[t0]]
    if t0 == T0:
        assert early["dividend_amount"].tolist() == [1.818]           # projected, not the 1.616 booked on 03-17


@pytest.mark.parametrize("t0", T0S)
def test_the_future_of_store_b_does_reach_the_ledger_one_session_later(engine_store, stores_b, tmp_path, t0):
    # So (a) is not vacuous: stopped one session after t0, the two ledgers differ.
    t1 = next(d for d in es.sessions() if d > t0)
    a = eh.run(engine_store, tmp_path / "a", RollingShortStraddle(exit_dte=0), stop_after=t1)
    b = eh.run(stores_b[t0], tmp_path / "b", RollingShortStraddle(exit_dte=0), stop_after=t1)
    assert a.digest != b.digest
    assert file_sha256(a.run_dir / "daily_pnl/part-0.parquet") != file_sha256(b.run_dir / "daily_pnl/part-0.parquet")


# --- (b) the prefix property ----------------------------------------------------------------------------------------

# Each dated table: the date that places a row in the prefix. Rows dated <= t0 must be equal in every column, except
# the outcome columns below, which are compared where the date that settles them is <= t0 in the full run (and must
# still be unsettled, null, in the stopped run otherwise).
DATED = {"daily_pnl": "session_date", "position_marks": "session_date", "hedges": "session_date",
         "cash_flows": "session_date", "fills": "fill_date", "expiry_events": "session_date",
         "risk_events": "session_date", "orders": "created_date", "lots": "opened_date", "positions": "created_date"}
OUTCOMES = {"orders": [("resolved_date", ("resolved_date", "status", "cancel_reason", "packages_filled"))],
            "lots": [("closed_date", ("closed_date", "qty_open"))],
            "positions": [("opened_date", ("opened_date",)), ("closed_date", ("closed_date", "status", "exit_reason"))]}


def ledger(result, name) -> pa.Table:
    """A ledger table as Arrow: its fixed schema, nulls as nulls, values compared exactly."""
    return pq.read_table(result.run_dir / name / "part-0.parquet")


def on_or_before(values, t0) -> np.ndarray:
    """True where a date is set and <= t0 (a null date is not settled)."""
    return np.array([day is not None and day <= t0 for day in values], dtype=bool)


def assert_prefix(full, stopped, t0):
    for name, column in DATED.items():
        whole, prefix = ledger(full, name), ledger(stopped, name)
        assert all(day <= t0 for day in prefix[column].to_pylist()), name
        head = whole.filter(pa.array(on_or_before(whole[column].to_pylist(), t0)))
        assert head.num_rows == prefix.num_rows, name
        outcomes = OUTCOMES.get(name, [])
        decision = [c for c in head.column_names if not any(c in columns for _, columns in outcomes)]
        assert head.select(decision).equals(prefix.select(decision)), name
        for when, columns in outcomes:
            done = on_or_before(head[when].to_pylist(), t0)
            assert head.filter(pa.array(done)).select(list(columns)).equals(
                prefix.filter(pa.array(done)).select(list(columns))), (name, when)
            assert prefix.filter(pa.array(~done))[when].null_count == int((~done).sum()), (name, when)
    # order_legs: placed by their order's created_date; filled and cancel_reason settle with the order.
    orders = eh.table(full, "orders").set_index("order_id")
    legs, prefix = ledger(full, "order_legs"), ledger(stopped, "order_legs")
    ids = legs["order_id"].to_pylist()
    head = legs.filter(pa.array(on_or_before([orders.at[i, "created_date"] for i in ids], t0)))
    decision = [c for c in head.column_names if c not in ("filled", "cancel_reason")]
    assert head.select(decision).equals(prefix.select(decision))
    done = pa.array(on_or_before([orders.at[i, "resolved_date"] for i in head["order_id"].to_pylist()], t0))
    assert head.filter(done).select(["filled", "cancel_reason"]).equals(
        prefix.filter(done).select(["filled", "cancel_reason"]))


STRATEGIES = {
    "exit_dte 0": lambda: RollingShortStraddle(exit_dte=0),
    "exit_dte 7": lambda: RollingShortStraddle(exit_dte=7),
    # An opening order queued on 02-07 that waits over the missing snapshot, and a close in March.
    "scripted": lambda: eh.Scripted({D(2023, 2, 7): eh.open_straddle(D(2023, 3, 17), 400.0),
                                     D(2023, 3, 8): eh.close_all("signal")}),
}


@pytest.fixture(scope="module")
def full_runs(engine_store, tmp_path_factory):
    root = tmp_path_factory.mktemp("full_runs")
    return {name: eh.run(engine_store, root / str(i), make()) for i, (name, make) in enumerate(STRATEGIES.items())}


@pytest.mark.parametrize("strategy, t0", [
    ("exit_dte 0", es.MISSING_SNAPSHOT),     # stale marks, no snapshot
    ("exit_dte 0", D(2023, 2, 17)),          # a settlement, and an opening order created that evening
    ("exit_dte 0", T0),                      # an early assignment decided for t0 + 1
    ("exit_dte 0", es.GAP_DATE),             # an early put assignment decided for t0 + 1
    ("exit_dte 7", D(2023, 2, 9)),           # a close order created at t0, filled after it
    ("exit_dte 7", D(2023, 3, 9)),
    ("scripted", es.MISSING_SNAPSHOT),       # an order waiting over t0
    ("scripted", D(2023, 3, 8)),
], ids=["missing snapshot", "settlement", "ex-date eve", "gap", "close order", "close order 2", "waiting order",
        "scripted close"])
def test_the_full_run_up_to_t0_equals_the_run_stopped_at_t0(engine_store, full_runs, tmp_path, strategy, t0):
    stopped = eh.run(engine_store, tmp_path, STRATEGIES[strategy](), stop_after=t0)
    full = full_runs[strategy]
    assert stopped.last_session == t0 and full.last_session == es.LAST_SNAPSHOT
    assert_prefix(full, stopped, t0)
    # Something settles after t0 in each case, so the outcome rule is exercised, not only the decision columns.
    orders, events = eh.table(full, "orders"), eh.table(full, "expiry_events")
    unsettled = (orders["created_date"] <= t0) & ~on_or_before(orders["resolved_date"], t0)
    effective_later = (events["session_date"] <= t0) & (events["effective_date"] > t0)
    open_lots = eh.table(stopped, "lots")["closed_date"].isna()
    assert unsettled.any() or effective_later.any() or open_lots.any()


# --- the cached view: M1's guards (tests/test_view.py) for the year cache ------------------------------------------

AS_OF = T0


def changed_after(frame, column, as_of):
    """`frame` with every row dated after as_of changed in every value column (dates and identifiers kept)."""
    frame = frame.copy()
    later = as_dates(frame[column]) > as_of
    for name in frame.columns:
        values = frame[name]
        if pd.api.types.is_bool_dtype(values):
            frame.loc[later, name] = ~values[later]
        elif pd.api.types.is_float_dtype(values):
            frame.loc[later, name] = values[later] * 3 + 1
        elif pd.api.types.is_integer_dtype(values):
            frame.loc[later, name] = values[later] + 1
        elif values.map(lambda v: isinstance(v, (list, np.ndarray))).any():
            frame.loc[later, name] = values[later].map(lambda v: [x * 3 + 1 for x in v])
    return frame


def copied_store(source, root, change: bool) -> Store:
    """The tables a YearCache reads, copied from `source`; with `change`, every row after AS_OF changed."""
    target = Store(root)
    for name, key in DAY_TABLES.items():
        arrow = pq.read_table(source.partition_file(name, PARTITION))
        frame = arrow.to_pandas()
        if change:
            frame = changed_after(frame, "quote_date", AS_OF)
        target.write_partition(name, pa.Table.from_pandas(frame, schema=arrow.schema, preserve_index=False), PARTITION,
                               ("quote_date", key))
    for name, column in REFERENCE_TABLES.items():
        frame = reference_frame(source, name)
        target.write_table(name, changed_after(frame, column, AS_OF) if change else frame, sort_by=(column,))
    return target


@pytest.fixture(scope="module")
def two_futures(engine_store, tmp_path_factory):
    root = tmp_path_factory.mktemp("two_futures")
    return copied_store(engine_store, root / "same", False), copied_store(engine_store, root / "changed", True)


def same(a, b) -> bool:
    return (list(a.columns) == list(b.columns) and a.index.equals(b.index)
            and pa.Table.from_pandas(a, preserve_index=False).equals(pa.Table.from_pandas(b, preserve_index=False)))


def everything_served(market, days):
    """Every view method's output at the view's as_of: the history reads and each day read for `days`."""
    out = {name: getattr(market, name)() for name in ("spy_bars", "dividends", "rates", "vix")}
    out["sessions"] = pd.DataFrame({"date": market.sessions()})
    for day in days:
        quotes = market.quotes(day)
        some = list(quotes["osi_symbol"].iloc[::7])
        out[f"chain {day}"] = market.chain(day)
        out[f"quotes {day}"] = quotes
        out[f"quotes {day} some"] = market.quotes(day, some)
        out[f"quote_ivs {day}"] = market.quote_ivs(day)
        out[f"quote_ivs {day} some"] = market.quote_ivs(day, some)
        out[f"forwards {day}"] = market.forwards(day)
        out[f"smiles {day}"] = market.smiles(day)
    return out


def test_changing_every_cached_row_after_as_of_changes_nothing_a_cached_view_serves(two_futures):
    first, second = (view(AS_OF, "validation", s, cache=YearCache(s, "optionsdx")) for s in two_futures)
    days = [d for d in es.sessions() if es.FIRST_SNAPSHOT <= d <= AS_OF]
    a, b = everything_served(first, days), everything_served(second, days)
    assert a.keys() == b.keys()
    for name in a:
        assert same(a[name], b[name]), name
    assert len(a[f"quotes {AS_OF}"]) and len(a[f"smiles {AS_OF}"]) and len(a["sessions"]) == len(
        [d for d in es.sessions() if d <= AS_OF])
    # The two stores do differ: one session later, through the same kind of cached view, the reads part.
    later = D(2023, 3, 17)
    a, b = (everything_served(view(later, "validation", s, cache=YearCache(s, "optionsdx")), [later])
            for s in two_futures)
    assert [name for name in a if not same(a[name], b[name])] == [name for name in a if name != "sessions"]


def reachable_data_objects(root, depth=4):
    """Walk public attributes from `root`; return the paths that reach an object from volbt.data (as test_view.py)."""
    found, seen = [], {id(root)}

    def is_data(obj):
        module = getattr(type(obj), "__module__", "") or ""
        if isinstance(obj, type(volbt.data)):
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


def test_no_public_attribute_of_a_cached_view_reaches_the_store_or_the_cache(engine_store):
    cache = YearCache(engine_store, "optionsdx")
    market = view(AS_OF, "validation", engine_store, cache=cache)
    market.quotes(AS_OF)                                    # the cache has loaded its year
    assert reachable_data_objects(market) == []
    assert [name for name in dir(cache) if not name.startswith("_")] == []      # and the cache has no public reader

    class Leaky:                                             # the walk would see a cache reference
        def __init__(self, cache):
            self.cache = cache

    assert reachable_data_objects(Leaky(cache)) == ["view.cache"]
