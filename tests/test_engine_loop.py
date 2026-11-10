"""The daily loop (ADR-0001 §1): tests 5 and 7, the cancel at settlement (D12), orders over a session without a
snapshot (D15), ruin (ADR-0007 §5), one mark per open lot, the NAV identity, a strategy that cannot move the book,
and the intents the engine refuses. On tests/engine_store.py's made-up store.

Fixture facts used here (each re-checked by an assertion where a test relies on it): the 2023-02-17 expiry settles
at S_set 402.79; 2023-02-08 has bars but no option snapshot; on 2023-04-03 (the -8% gap) a short 2023-04-21 415
put is early-assigned for 2023-04-04.
"""

from dataclasses import FrozenInstanceError
from datetime import date

import numpy as np
import pytest

import engine_helpers as eh
import engine_store as es
from volbt.data.store import file_sha256, view
from volbt.engine.loop import EngineError
from volbt.strategies.base import LegIntent, OrderIntent
from volbt.strategies.reference import RollingShortStraddle

D = date
FEB17 = D(2023, 2, 17)                          # a monthly expiry, S_set 402.79
PUT_405 = es.symbol(FEB17, "P", 405.0)          # ITM by 2.21 at that settlement
CALL_400_MAR = es.symbol(D(2023, 3, 17), "C", 400.0)
# The gappy store: no option snapshot on the session after the February expiry (Presidents' Day comes between)
# nor on the 2023-03-10 weekly's expiry day.
NO_SNAPSHOT = (D(2023, 2, 21), D(2023, 3, 10))


@pytest.fixture(scope="module")
def gappy_store(tmp_path_factory):
    spots = es.spot_path()
    edits = {(day, row["osi_symbol"]): {"drop": True} for day in NO_SNAPSHOT for row in es.quotes_on(day, spots[day])}
    return es.built_store(tmp_path_factory.mktemp("gappy_store"), edits=edits)


def rows_on(frame, column, day):
    return frame[frame[column] == day]


# --- ADR-0001 test 5: fill -> expiry -> mark -> hedge -------------------------------------------------------------

def test_a_pending_buy_and_an_expiring_itm_short_put_are_booked_fill_expiry_mark_hedge(engine_store, tmp_path):
    strategy = eh.Scripted({D(2023, 2, 14): eh.open_legs([(PUT_405, -1)], 10, "short_put"),
                            D(2023, 2, 16): eh.open_legs([(CALL_400_MAR, 1)], 5, "long_call")})
    result = eh.run(engine_store, tmp_path, strategy, sample_end=D(2023, 2, 21))
    fills, events, marks, hedges, flows, lots, pnl = (eh.table(result, name) for name in (
        "fills", "expiry_events", "position_marks", "hedges", "cash_flows", "lots", "daily_pnl"))

    buy = rows_on(fills, "fill_date", FEB17)
    assert buy[["osi_symbol", "qty"]].values.tolist() == [[CALL_400_MAR, 5]]       # the pending buy fills at t
    event = rows_on(events, "session_date", FEB17)
    assert event[["osi_symbol", "event_type", "shares_delivered", "settlement_price"]].values.tolist() == [
        [PUT_405, "assigned", 1000, 402.79]]

    # The cash flows of the day, in the order they were booked (flow ids are allocated in creation order).
    stage = {"option_premium": "fill", "option_fee": "fill", "settlement": "expiry", "hedge_trade": "hedge",
             "hedge_commission": "hedge", "hedge_slippage": "hedge"}
    day = rows_on(flows, "session_date", FEB17).sort_values("flow_id")
    assert [stage[kind] for kind in day["kind"] if kind in stage] == ["fill", "fill", "expiry", "hedge", "hedge",
                                                                       "hedge"]
    assert day[day["kind"] == "option_premium"]["ref_id"].tolist() == buy["fill_id"].tolist()
    assert day[day["kind"] == "settlement"]["ref_id"].tolist() == event["event_id"].tolist()

    # Mark after fill and expiry: the new lot has its mark on its fill day; the settled put only its INTRINSIC row.
    new_lot = lots.loc[lots["osi_symbol"] == CALL_400_MAR, "lot_id"].item()
    put_lot = lots.loc[lots["osi_symbol"] == PUT_405, "lot_id"].item()
    day_marks = rows_on(marks, "session_date", FEB17)
    source = day_marks.set_index("lot_id")[["mark_source", "in_nav"]]
    assert day_marks["lot_id"].tolist() == sorted([new_lot, put_lot])
    assert source.loc[new_lot].tolist() == ["QUOTE_MID", True]
    assert source.loc[put_lot].tolist() == ["INTRINSIC", False]

    # Hedge after mark: it saw the shares the expiry delivered and the delta of the lot that filled today.
    hedge = rows_on(hedges, "session_date", FEB17).iloc[0]
    before = int(hedge["shares_after"] - hedge["shares_traded"])
    assert before == rows_on(pnl, "session_date", D(2023, 2, 16))["shares"].item() + 1000
    in_nav = day_marks[day_marks["in_nav"]]
    assert in_nav["lot_id"].tolist() == [new_lot]
    assert hedge["delta_before_shares"] == pytest.approx(before + in_nav["delta_shares"].sum(), abs=1e-9)
    assert hedge["shares_traded"] != 0


# --- ADR-0001 test 7 and D12: an order on a lot that is no longer held is cancelled LOT_REMOVED -------------------

@pytest.mark.parametrize("legs", [[("P", -1)], [("C", -1), ("P", -1)]], ids=["short put", "short straddle"])
def test_an_early_assignment_decided_at_t_cancels_the_close_order_queued_at_t(engine_store, tmp_path, legs):
    t, t1, expiry = D(2023, 4, 3), D(2023, 4, 4), D(2023, 4, 21)
    put = es.symbol(expiry, "P", 415.0)
    opening = [(es.symbol(expiry, right, 415.0), ratio) for right, ratio in legs]
    strategy = eh.Scripted({D(2023, 3, 17): eh.open_legs(opening, 10), t: eh.close_all("signal")})
    result = eh.run(engine_store, tmp_path, strategy, sample_end=D(2023, 4, 6))
    orders, fills, events, flows, lots = (eh.table(result, name) for name in (
        "orders", "fills", "expiry_events", "cash_flows", "lots"))

    close = orders[orders["intent"] == "close"]
    assert close["created_date"].tolist() == [t]
    event = events[events["event_type"] == "early_assigned"]
    assert event[["session_date", "effective_date", "osi_symbol", "contracts", "shares_delivered"]].values.tolist() == [
        [t, t1, put, -10, 1000]]
    # At t+1 the assignment is booked first: shares at K, -100 K cash per contract, before any other flow.
    first = rows_on(flows, "session_date", t1).sort_values("flow_id").iloc[0]
    assert (first["kind"], first["ref_id"], first["amount_cents"]) == ("early_settlement", event["event_id"].item(),
                                                                       -1000 * 41500)
    # Then the order is cancelled, the whole package, and nothing of it fills.
    assert close[["status", "cancel_reason", "resolved_date", "packages_filled"]].values.tolist() == [
        ["cancelled", "LOT_REMOVED", t1, 0]]
    assert close["order_id"].item() not in set(fills["order_id"])
    assert lots.loc[lots["osi_symbol"] == put, ["qty_open", "closed_date"]].values.tolist() == [[0, t1]]
    if len(legs) == 2:
        call = es.symbol(expiry, "C", 415.0)
        assert lots.loc[lots["osi_symbol"] == call, ["qty_open", "closed_date"]].values.tolist() == [[-10, None]]


def test_an_order_waiting_on_a_lot_that_settles_today_is_cancelled_lot_removed(gappy_store, tmp_path):
    # D12. The close order queued on 03-09 cannot fill on 03-10 (no snapshot), so it is still pending when step 4
    # settles its lots: the put is assigned (S_set 409.68 < 415), the call expires.
    expiry = D(2023, 3, 10)
    strategy = eh.Scripted({D(2023, 3, 6): eh.open_straddle(expiry, 415.0), D(2023, 3, 9): eh.close_all("dte")})
    result = eh.run(gappy_store, tmp_path, strategy, sample_end=D(2023, 3, 14))
    orders, fills, events, pnl = (eh.table(result, name) for name in ("orders", "fills", "expiry_events", "daily_pnl"))

    assert rows_on(pnl, "session_date", expiry)["has_snapshot"].tolist() == [False]
    assert sorted(rows_on(events, "session_date", expiry)["event_type"]) == ["assigned", "expired_worthless"]
    assert rows_on(events, "session_date", expiry)["settlement_price"].tolist() == [409.68, 409.68]
    close = orders[orders["intent"] == "close"]
    assert close[["created_date", "target_fill_date", "status", "cancel_reason", "resolved_date"]].values.tolist() == [
        [D(2023, 3, 9), expiry, "cancelled", "LOT_REMOVED", expiry]]
    assert close["order_id"].item() not in set(fills["order_id"])


# --- D15: option orders wait for a snapshot, share orders do not -----------------------------------------------------

def test_an_option_order_waits_over_the_missing_snapshot_and_fills_at_the_next_one(engine_store, tmp_path):
    created, missing, filled = D(2023, 2, 7), es.MISSING_SNAPSHOT, D(2023, 2, 9)
    strategy = eh.Scripted({created: eh.open_straddle(D(2023, 3, 17), 400.0)})
    result = eh.run(engine_store, tmp_path, strategy, sample_end=D(2023, 2, 10))
    orders, fills, pnl = (eh.table(result, name) for name in ("orders", "fills", "daily_pnl"))

    assert rows_on(pnl, "session_date", missing)[["has_snapshot", "n_open_lots"]].values.tolist() == [[False, 0]]
    columns = ["created_date", "target_fill_date", "resolved_date", "status", "packages_filled"]
    assert orders[columns].values.tolist() == [[created, missing, filled, "filled", 10]]
    assert fills["fill_date"].tolist() == [filled, filled]
    symbols = fills["osi_symbol"].tolist()
    on_fill_day = view(filled, "validation", engine_store).quotes(filled, symbols)
    on_order_day = view(created, "validation", engine_store).quotes(created, symbols)
    quoted = ["osi_symbol", "bid", "ask"]
    assert fills[quoted].values.tolist() == on_fill_day[quoted].values.tolist()
    assert on_fill_day[["bid", "ask"]].values.tolist() != on_order_day[["bid", "ask"]].values.tolist()
    assert rows_on(pnl, "session_date", filled)["n_open_lots"].tolist() == [2]


def test_a_share_order_fills_on_a_session_without_a_snapshot_while_an_option_order_waits(gappy_store, tmp_path):
    # Unhedged: the short put assigned on 02-17 leaves +1,000 shares, liquidated at the 02-21 close (ADR-0003 §3),
    # a session with no option snapshot; the straddle ordered the same evening waits for 02-22.
    no_snapshot, next_snapshot = NO_SNAPSHOT[0], D(2023, 2, 22)
    strategy = eh.Scripted({D(2023, 2, 14): eh.open_legs([(PUT_405, -1)], 10, "short_put"),
                            FEB17: eh.open_straddle(D(2023, 3, 17), 400.0)})
    result = eh.run(gappy_store, tmp_path, strategy, sample_end=D(2023, 2, 23), hedge_mode="never")
    orders, fills, pnl = (eh.table(result, name) for name in ("orders", "fills", "daily_pnl"))

    assert rows_on(pnl, "session_date", no_snapshot)[["has_snapshot", "shares"]].values.tolist() == [[False, 0]]
    shares = orders[orders["intent"] == "share_liquidation"]
    assert shares[["created_date", "target_fill_date", "resolved_date", "status"]].values.tolist() == [
        [FEB17, no_snapshot, no_snapshot, "filled"]]
    share_fill = fills[fills["order_id"] == shares["order_id"].item()]
    close_0221 = view(no_snapshot, "validation", gappy_store).spy_bars()["close"].iloc[-1]
    assert share_fill[["instrument", "fill_date", "qty", "price"]].values.tolist() == [
        ["share", no_snapshot, -1000, close_0221]]
    straddle = orders[(orders["intent"] == "open") & (orders["created_date"] == FEB17)]
    assert straddle[["target_fill_date", "resolved_date", "status"]].values.tolist() == [
        [no_snapshot, next_snapshot, "filled"]]
    assert fills.loc[fills["order_id"] == straddle["order_id"].item(), "fill_date"].tolist() == [next_snapshot] * 2


# --- ruin (ADR-0007 §5) ---------------------------------------------------------------------------------------------

def test_nav_mid_at_or_below_zero_is_ruin_and_the_run_stops_on_that_session(engine_store, tmp_path):
    # 500 deep-ITM April calls bought on credit (cash goes to about -$700k), unhedged, then the -8% gap.
    calls = [es.symbol(D(2023, 4, 21), "C", strike) for strike in (365.0, 370.0, 375.0, 380.0, 385.0)]

    def buy(view, book, ctx):
        return [OrderIntent(None, "open", "long_call", (LegIntent(symbol, 1),), 100) for symbol in calls]

    # A close order scripted for the gap day shows whether step 9 ran after the ruin.
    strategy = eh.Scripted({D(2023, 3, 30): buy, es.GAP_DATE: eh.close_all("risk")})
    result = eh.run(engine_store, tmp_path, strategy, hedge_mode="never")
    pnl, risk, runs, positions, orders = (eh.table(result, name) for name in (
        "daily_pnl", "risk_events", "runs", "positions", "orders"))

    assert result.status == "ruin" and result.last_session == es.GAP_DATE
    assert runs[["status", "last_session"]].values.tolist() == [["ruin", es.GAP_DATE]]
    assert pnl["session_date"].max() == es.GAP_DATE
    assert result.sessions == len([d for d in es.sessions() if es.FIRST_SNAPSHOT <= d <= es.GAP_DATE])
    ruin_day = rows_on(pnl, "session_date", es.GAP_DATE).iloc[0]
    assert ruin_day["nav_mid"] <= 0 < pnl.iloc[-2]["nav_mid"]
    assert risk[["session_date", "kind", "action"]].values.tolist() == [[es.GAP_DATE, "ruin", "stop"]]
    assert risk["value"].item() == ruin_day["nav_mid"]
    assert positions["exit_reason"].tolist() == ["ruin"] * 5
    assert (orders["created_date"] < es.GAP_DATE).all()                  # no decision after the ruin
    for name, column in (("position_marks", "session_date"), ("cash_flows", "session_date"), ("hedges", "session_date"),
                         ("fills", "fill_date"), ("expiry_events", "session_date")):
        table = eh.table(result, name)
        assert not (table[column] > es.GAP_DATE).any(), name


# --- marks and NAV on whole runs ------------------------------------------------------------------------------------

RUNS = ("reference exit_dte 0", "reference exit_dte 7", "reference exit_dte 0, unhedged, gappy store")


@pytest.fixture(scope="module")
def reference_runs(engine_store, gappy_store, tmp_path_factory):
    root = tmp_path_factory.mktemp("reference_runs")
    return {RUNS[0]: eh.run(engine_store, root / "a", RollingShortStraddle(exit_dte=0)),
            RUNS[1]: eh.run(engine_store, root / "b", RollingShortStraddle(exit_dte=7)),
            RUNS[2]: eh.run(gappy_store, root / "c", RollingShortStraddle(exit_dte=0), hedge_mode="never")}


def open_at_close(lots, day):
    """lot_ids open at the close of `day`: opened on or before it and not closed on or before it."""
    return sorted(int(lot.lot_id) for lot in lots.itertuples()
                  if lot.opened_date <= day and (lot.closed_date is None or lot.closed_date > day))


@pytest.mark.parametrize("name", RUNS)
def test_exactly_one_mark_per_open_lot_per_session(reference_runs, name):
    result = reference_runs[name]
    marks, lots, pnl, events = (eh.table(result, n) for n in ("position_marks", "lots", "daily_pnl", "expiry_events"))
    assert len(lots) >= 6 and len(pnl) == result.sessions
    in_nav = marks[marks["in_nav"]]
    assert not in_nav.duplicated(["session_date", "lot_id"]).any()
    for row in pnl.itertuples():
        marked = sorted(in_nav.loc[in_nav["session_date"] == row.session_date, "lot_id"].astype(int))
        assert marked == open_at_close(lots, row.session_date), row.session_date
        assert row.n_open_lots == len(marked)
    # Out of NAV: one INTRINSIC row for each lot settled at expiry, on its settlement day (D11), and nothing else.
    settled = events[events["event_type"].isin(["assigned", "exercised", "expired_worthless"])]
    out = marks[~marks["in_nav"]]
    assert set(out["mark_source"]) <= {"INTRINSIC"}
    assert sorted(zip(out["session_date"], out["lot_id"])) == sorted(zip(settled["session_date"], settled["lot_id"]))
    assert len(settled) >= (4 if "exit_dte 0" in name else 0)               # exit_dte 0 holds to expiry
    if "gappy" in name:
        assert {"STALE_SURFACE", "INTRINSIC", "QUOTE_MID"} <= set(marks["mark_source"])


@pytest.mark.parametrize("name", RUNS)
def test_the_nav_identity_holds_on_every_session(reference_runs, name):
    # NAV_mid = cash + shares S + sum qty 100 mark over the lots in NAV (ADR-0004); NAV_liq the same at the liq values.
    result = reference_runs[name]
    marks, pnl = eh.table(result, "position_marks"), eh.table(result, "daily_pnl")
    spots = es.spot_path()
    assert np.allclose(marks["value_mid_usd"], marks["qty"] * 100 * marks["mark_price"], rtol=0, atol=1e-9)
    for row in pnl.itertuples():
        assert row.spot == spots[row.session_date] and row.cash == row.cash_cents / 100
        day = marks[(marks["session_date"] == row.session_date) & marks["in_nav"]]
        base = row.cash_cents / 100 + row.shares * row.spot
        assert abs(row.nav_mid - (base + float(np.sum(day["value_mid_usd"].to_numpy())))) <= 1e-6, row.session_date
        assert abs(row.nav_liq - (base + float(np.sum(day["value_liq_usd"].to_numpy())))) <= 1e-6, row.session_date
    assert (pnl["shares"] != 0).any() and (pnl["n_open_lots"] > 0).sum() > 40


# --- a strategy cannot move the engine's book ----------------------------------------------------------------------

class Vandal:
    """The reference strategy under its own name and parameters (so its run hashes like the reference's), which
    after each decision tries to write to the BookState it was handed, then forces writes into that copy."""

    def __init__(self):
        self.inner = RollingShortStraddle(exit_dte=0)
        self.name = self.inner.name
        self.engine_book = None        # the engine's own Book, handed over by on_session_end
        self.digests, self.writes = [], []

    def params(self):
        return self.inner.params()

    def on_session_end(self, day, book):
        self.engine_book = book

    def decide(self, view, book, ctx):
        before = self.engine_book.digest() if self.engine_book is not None else None
        intents = self.inner.decide(view, book, ctx)
        attempts = [lambda: setattr(book, "cash_cents", 0), lambda: setattr(book, "shares", 10**6),
                    lambda: setattr(book, "positions", ()), lambda: setattr(book, "pending", ())]
        for position in book.positions:
            attempts.append(lambda p=position: setattr(p, "status", "closed"))
            attempts += [lambda lot=lot: setattr(lot, "qty", 0) for lot in position.lots]
        for order in book.pending:
            attempts.append(lambda o=order: setattr(o, "intent", "close"))
        for attempt in attempts:
            try:
                attempt()
                self.writes.append("written")
            except FrozenInstanceError:
                self.writes.append("frozen")
        # Past the frozen check: the copy changes, the engine's book must not.
        object.__setattr__(book, "cash_cents", 0)
        for position in book.positions:
            for lot in position.lots:
                object.__setattr__(lot, "qty", 0)
        after = self.engine_book.digest() if self.engine_book is not None else None
        self.digests.append((ctx.session_date, before, after))
        return intents


def test_a_strategy_cannot_move_the_engine_book(engine_store, tmp_path):
    vandal = Vandal()
    vandalised = eh.run(engine_store, tmp_path / "vandal", vandal, on_session_end=vandal.on_session_end)
    plain = eh.run(engine_store, tmp_path / "plain", RollingShortStraddle(exit_dte=0))

    assert vandal.writes and set(vandal.writes) == {"frozen"}
    assert vandal.writes.count("frozen") > 4 * len(vandal.digests)          # lot and position writes were tried
    checked = [(day, before, after) for day, before, after in vandal.digests if before is not None]
    assert len(checked) == vandalised.sessions - 1
    assert [day for day, before, after in checked if before != after] == []
    # And the run is the reference run, byte for byte (the same name and parameters: the same config_hash).
    assert vandalised.digest == plain.digest and vandalised.files == plain.files
    for name in plain.files:
        assert file_sha256(vandalised.run_dir / name) == file_sha256(plain.run_dir / name), name


# --- intents the engine refuses -------------------------------------------------------------------------------------

def held_put_then(day, action):
    """Short 10 of the 02-17 405 put (ordered 02-03, filled 02-06), then `action` on `day`."""
    return eh.Scripted({D(2023, 2, 3): eh.open_legs([(PUT_405, -1)], 10, "short_put"), day: action})


def close_put(ratio, packages, count=1):
    def action(view, book, ctx):
        position = book.open_positions()[0]
        return [OrderIntent(position.position_id, "close", position.structure, (LegIntent(PUT_405, ratio),), packages,
                            "signal")] * count
    return action


def test_a_close_of_exactly_the_held_quantity_is_accepted(engine_store, tmp_path):
    # The control for the refusals below: the same strategy with a valid close runs and fills.
    result = eh.run(engine_store, tmp_path, held_put_then(D(2023, 2, 6), close_put(1, 10)), sample_end=D(2023, 2, 9))
    fills = eh.table(result, "fills")
    assert fills[["fill_date", "qty"]].values.tolist() == [[D(2023, 2, 6), -10], [D(2023, 2, 7), 10]]


@pytest.mark.parametrize("strategy, match", [
    (held_put_then(D(2023, 2, 6), close_put(-1, 1)), "must reduce"),          # sells more of a short
    (held_put_then(D(2023, 2, 6), close_put(1, 11)), "must reduce"),          # buys back more than is held
    (held_put_then(D(2023, 2, 6), close_put(1, 10, count=2)), "two orders for position"),
    # The close queued on 02-07 waits over the missing snapshot: a second one on 02-08 is refused.
    (eh.Scripted({D(2023, 2, 3): eh.open_legs([(PUT_405, -1)], 10), D(2023, 2, 7): close_put(1, 10),
                  es.MISSING_SNAPSHOT: close_put(1, 10)}), "already has a pending order"),
    (eh.Scripted({D(2023, 2, 7): eh.open_legs([(es.symbol(D(2023, 3, 17), "C", 402.0), -1)], 1)}),
     "not in the snapshot"),                                                  # a strike that is not listed
    (eh.Scripted({es.MISSING_SNAPSHOT: eh.open_straddle(D(2023, 3, 17), 400.0)}), "not in the snapshot"),
], ids=["sells more", "buys back too many", "two in one session", "second while pending", "unlisted strike",
        "open without a snapshot"])
def test_an_invalid_intent_raises_engine_error(engine_store, tmp_path, strategy, match):
    with pytest.raises(EngineError, match=match):
        eh.run(engine_store, tmp_path, strategy, sample_end=D(2023, 2, 10))


def test_a_chain_mask_other_than_none_raises():
    # ADR-0009 §4's masked runs need a pricing build on masked chains, which M3 does not have.
    assert eh.config(chain_mask="none").chain_mask == "none"
    for mask in ("masked", "drop_10pct", ""):
        with pytest.raises(ValueError, match="chain_mask"):
            eh.config(chain_mask=mask)
