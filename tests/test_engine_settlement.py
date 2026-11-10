"""Settlement on expiration day (ADR-0003 tests 1-4 and 8; decisions D11, D12, D16), as booked events.

The rule is checked twice: on settlement.is_exercised / settle_lot with the ADR's own numbers, and through runs of
the engine on a made-up store. That store is tests/engine_store.py's, moved up by 12.5% so that the ADR's strikes
(440, 450, 460) are listed: strikes 410-490, every spot x 1.125, and these closes set by hand:

    expiry       S_set    the day before   held (opened the session before, so no early decision interferes)
    2023-02-17   450.00   452.00           a long 450 straddle, two long 440 calls
    2023-03-10   450.01   452.00           a short 450 straddle, a short 455 put
    2023-03-17   450.00   445.00           a long 460 put (03-17 is also the ex-date: waiting for the dividend
                                           beats early exercise, so the put reaches expiry)
    2023-03-24   449.99   452.00           a long 450 straddle
    2023-04-21   451.00   452.00           a short 450 call, with no option snapshot on 04-21

plus a weekly expiring on Good Friday 2023-04-07 (not a session, not in D16's map), the expiring 02-17 calls quoted
far from their intrinsic value on 02-17, and an adjusted close that is not the close.
"""

from datetime import date

import numpy as np
import pyarrow.parquet as pq
import pytest

import engine_helpers as eh
import engine_store as es
from volbt import build
from volbt.engine import settlement
from volbt.engine.book import Lot
from volbt.engine.settlement import UnmappedExpiry

D = date
FEB17, MAR10, MAR17, MAR24, APR21 = D(2023, 2, 17), D(2023, 3, 10), D(2023, 3, 17), D(2023, 3, 24), D(2023, 4, 21)
GOOD_FRIDAY = D(2023, 4, 7)
STRIKES = np.arange(410.0, 491.0, 5.0)
SCALE = 1.125
CLOSES = {D(2023, 2, 16): 452.00, FEB17: 450.00, D(2023, 3, 9): 452.00, MAR10: 450.01,
          D(2023, 3, 16): 445.00, MAR17: 450.00, D(2023, 3, 23): 452.00, MAR24: 449.99,
          D(2023, 4, 20): 452.00, APR21: 451.00}
sym = es.symbol


def lot(right: str, strike: float, qty: int, expiry: date = FEB17) -> Lot:
    return Lot(1, 1, sym(expiry, right, strike), expiry, strike, right, qty, D(2023, 1, 3), expiry)


def settle(right: str, strike: float, qty: int, s_set: float) -> dict:
    return settlement.settle_lot(lot(right, strike, qty), int(round(s_set * 100)), int(round(strike * 100)), 50)


# --- the rule itself, with the ADR's numbers ----------------------------------------------------------------------

def test_ex_by_ex_at_the_one_cent_threshold():
    # ADR-0003 test 1: at S_set = 450.00 a 450 call and a 450 put both expire; a 449.99 call and a 450.01 put are
    # in the money by $0.01 and are exercised. One cent the other way is out of the money.
    assert not settlement.is_exercised("C", 45000, 45000)
    assert not settlement.is_exercised("P", 45000, 45000)
    assert settlement.is_exercised("C", 45000, 44999)
    assert settlement.is_exercised("P", 45000, 45001)
    assert not settlement.is_exercised("C", 45000, 45001)
    assert not settlement.is_exercised("P", 45000, 44999)


def test_settle_lot_at_the_threshold():
    assert settle("C", 450.0, 1, 450.00)["event_type"] == "expired_worthless"
    assert settle("P", 450.0, 1, 450.00)["event_type"] == "expired_worthless"
    assert settle("C", 450.0, 1, 450.00)["shares_delivered"] == 0 == settle("C", 450.0, 1, 450.00)["cash_cents"]
    assert settle("C", 449.99, 1, 450.00)["event_type"] == "exercised"
    assert settle("P", 450.01, -1, 450.00)["event_type"] == "assigned"


def test_two_long_440_calls_deliver_200_shares_for_88000_and_conserve_nav_at_intrinsic():
    # ADR-0003 test 2: +200 shares, cash -$88,000; the shares are worth $90,000 at S_set, so the settlement adds
    # +$2,000, the calls' intrinsic value 2 x 100 x 10.
    event = settle("C", 440.0, 2, 450.00)
    assert (event["event_type"], event["contracts"], event["shares_delivered"]) == ("exercised", 2, 200)
    assert event["cash_cents"] == -8_800_000
    assert event["shares_delivered"] * 45000 + event["cash_cents"] == 2 * 100 * 1000


@pytest.mark.parametrize("right, qty, shares, event_type", [("C", 1, 100, "exercised"), ("C", -1, -100, "assigned"),
                                                            ("P", 1, -100, "exercised"), ("P", -1, 100, "assigned")])
def test_the_delivery_table(right, qty, shares, event_type):
    # ADR-0003 §2: long call +100, short call -100, long put -100, short put +100, at K, cash -/+ 100 K.
    strike = 440.0 if right == "C" else 460.0
    event = settle(right, strike, qty, 450.00)
    assert (event["event_type"], event["shares_delivered"]) == (event_type, shares)
    assert event["cash_cents"] == -shares * int(strike * 100)


def test_the_pin_flag():
    # ADR-0003 test 8: at 450.30 a short 450 call is assigned (ITM by 0.30) and flagged; at 451.00 it is assigned
    # and not flagged. The band is |S_set - K| <= $0.50, for SHORT contracts only.
    pinned = settle("C", 450.0, -1, 450.30)
    assert (pinned["event_type"], pinned["pin_flag"]) == ("assigned", True)
    clear = settle("C", 450.0, -1, 451.00)
    assert (clear["event_type"], clear["pin_flag"]) == ("assigned", False)
    assert settle("C", 450.0, -1, 450.50)["pin_flag"] is True
    assert settle("C", 450.0, -1, 450.51)["pin_flag"] is False
    assert settle("P", 450.0, -1, 450.30) == {"event_type": "expired_worthless", "contracts": -1,
                                              "shares_delivered": 0, "cash_cents": 0, "pin_flag": True}
    for s_set in (450.00, 450.30, 449.70):
        assert settle("C", 450.0, 1, s_set)["pin_flag"] is False         # a long contract is never flagged
        assert settle("P", 450.0, 3, s_set)["pin_flag"] is False


def test_the_d16_map_of_non_session_expiries():
    sessions = {D(2015, 12, 18), D(2018, 12, 4), D(2018, 12, 21), D(2018, 12, 24), FEB17}
    assert settlement.settle_date(D(2015, 12, 19), sessions) == D(2015, 12, 18)     # a Saturday LEAP
    # the day of mourning: OCC Information Memo #44125 settles SPY options on Tuesday 12-04's closing prices
    assert settlement.settle_date(D(2018, 12, 5), sessions) == D(2018, 12, 4)
    assert settlement.settle_date(FEB17, sessions) == FEB17                         # a session settles itself
    for unmapped in (D(2018, 12, 23), D(2018, 12, 25)):
        with pytest.raises(UnmappedExpiry):
            settlement.settle_date(unmapped, sessions)


# --- through the engine ---------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def store(tmp_path_factory):
    moves = {day: round(spot * SCALE, 2) for day, spot in es.spot_path().items()}
    moves.update(CLOSES)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(es, "STRIKES", STRIKES)
        patch.setattr(es, "EXPIRIES", sorted(es.EXPIRIES + [GOOD_FRIDAY]))
        # The expiring calls quoted far from intrinsic on their expiry day (S_set 450: intrinsic 0 and 10).
        edits = {(FEB17, sym(FEB17, "C", 450.0)): {"bid": 3.00, "ask": 3.02},
                 (FEB17, sym(FEB17, "C", 440.0)): {"bid": 12.00, "ask": 12.02}}
        edits.update({(APR21, row["osi_symbol"]): {"drop": True} for row in es.quotes_on(APR21, moves[APR21])})
        made = es.make_engine_store(tmp_path_factory.mktemp("settle_store"), edits=edits, spot_moves=moves)
    bars = pq.read_table(made.checked_table_file("spy_bars")).to_pandas()
    bars["adj_close"] = (bars["close"] * 0.97).round(2)          # the dividend-adjusted close is never S_set
    made.write_table("spy_bars", bars, sort_by=("date",))
    build.build_pricing(made)
    return made


def straddle(expiry, strike, sign):
    return eh.open_straddle(expiry, strike, 1, sign)


def both(*actions):
    return lambda view, book, ctx: [order for action in actions for order in action(view, book, ctx)]


@pytest.fixture(scope="module")
def unhedged(store, tmp_path_factory):
    """Every expiry of the table above, with hedge_mode never (ADR-0003 §3: delivered shares are liquidated)."""
    strategy = eh.Scripted({
        D(2023, 2, 15): both(straddle(FEB17, 450.0, 1), eh.open_legs([(sym(FEB17, "C", 440.0), 2)])),
        D(2023, 3, 8): both(straddle(MAR10, 450.0, -1), eh.open_legs([(sym(MAR10, "P", 455.0), -1)])),
        D(2023, 3, 15): eh.open_legs([(sym(MAR17, "P", 460.0), 1)]),
        D(2023, 3, 22): straddle(MAR24, 450.0, 1),
        D(2023, 4, 19): eh.open_legs([(sym(APR21, "C", 450.0), -1)]),
        D(2023, 4, 20): eh.close_all()})
    return eh.run(store, tmp_path_factory.mktemp("unhedged_runs"), strategy, hedge_mode="never")


@pytest.fixture(scope="module")
def hedged(store, tmp_path_factory):
    """ADR-0003 test 3's book: one long 460 put, hedged at every close."""
    strategy = eh.Scripted({D(2023, 3, 15): eh.open_legs([(sym(MAR17, "P", 460.0), 1)])})
    return eh.run(store, tmp_path_factory.mktemp("hedged_runs"), strategy, sample_end=D(2023, 3, 21))


def events_on(result, day):
    events = eh.table(result, "expiry_events")
    return {row.osi_symbol: row for row in events[events["session_date"] == day].itertuples()}


def flows_on(result, day):
    flows = eh.table(result, "cash_flows")
    return flows[flows["session_date"] == day].sort_values("flow_id")


def pnl_on(result, day):
    pnl = eh.table(result, "daily_pnl")
    return pnl[pnl["session_date"] == day].iloc[0]


def test_ex_by_ex_at_the_threshold_through_a_run(unhedged):
    feb, mar10, mar24 = events_on(unhedged, FEB17), events_on(unhedged, MAR10), events_on(unhedged, MAR24)
    # S_set 450.00: the 450 call and put both expire worthless.
    assert feb[sym(FEB17, "C", 450.0)].event_type == feb[sym(FEB17, "P", 450.0)].event_type == "expired_worthless"
    # S_set 450.01: the call is ITM by a cent (a short one is assigned), the put expires.
    assert mar10[sym(MAR10, "C", 450.0)].event_type == "assigned"
    assert mar10[sym(MAR10, "P", 450.0)].event_type == "expired_worthless"
    # S_set 449.99: the put is ITM by a cent (a long one is exercised), the call expires.
    assert mar24[sym(MAR24, "P", 450.0)].event_type == "exercised"
    assert mar24[sym(MAR24, "C", 450.0)].event_type == "expired_worthless"
    for day, events in ((FEB17, feb), (MAR10, mar10), (MAR24, mar24)):
        assert {row.settlement_price for row in events.values()} == {CLOSES[day]}
        assert {row.effective_date for row in events.values()} == {day}


def test_s_set_is_the_unadjusted_close_never_the_option_quote(store, unhedged):
    bars = pq.read_table(store.checked_table_file("spy_bars")).to_pandas()
    close = {row.date.date() if hasattr(row.date, "date") else row.date: (row.close, row.adj_close)
             for row in bars.itertuples()}
    events = eh.table(unhedged, "expiry_events")
    for row in events.itertuples():
        assert row.settlement_price == close[row.session_date][0] != close[row.session_date][1]
    # The 450 call was quoted 3.00/3.02 on its expiry day and the 440 calls 12.00/12.02: both settle at intrinsic.
    feb = events_on(unhedged, FEB17)
    flows = flows_on(unhedged, FEB17)
    settled = flows[flows["kind"] == "settlement"]
    assert settled["ref_id"].tolist() == [feb[sym(FEB17, "C", 440.0)].event_id]       # nothing for the 450 call
    assert settled["amount_cents"].tolist() == [-8_800_000]
    marks = eh.table(unhedged, "position_marks")
    lots = eh.table(unhedged, "lots").set_index("osi_symbol")["lot_id"]
    intrinsic = marks[(marks["session_date"] == FEB17)].set_index("lot_id")["mark_price"]
    assert intrinsic[lots[sym(FEB17, "C", 450.0)]] == 0.0
    assert intrinsic[lots[sym(FEB17, "C", 440.0)]] == 10.0


def test_two_long_440_calls_through_a_run_deliver_200_shares_and_add_their_intrinsic_value(unhedged):
    event = events_on(unhedged, FEB17)[sym(FEB17, "C", 440.0)]
    assert (event.event_type, event.contracts, event.shares_delivered) == ("exercised", 2, 200)
    flows = flows_on(unhedged, FEB17)
    cash = flows.loc[(flows["kind"] == "settlement") & (flows["ref_id"] == event.event_id), "amount_cents"].item()
    assert cash == -8_800_000
    marks = eh.table(unhedged, "position_marks")
    row = marks[(marks["session_date"] == FEB17) & (marks["lot_id"] == event.lot_id)].iloc[0]
    assert (row.mark_source, row.mark_price, row.value_mid_usd) == ("INTRINSIC", 10.0, 2000.0)
    # Settlement conserves NAV relative to an intrinsic valuation: 200 x 450 - 88,000 = 2,000.
    assert event.shares_delivered * event.settlement_price + cash / 100 == row.value_mid_usd == 2000.0
    day = pnl_on(unhedged, FEB17)
    assert day.shares == 200 and day.n_open_lots == 0
    assert day.nav_mid == pytest.approx(day.cash_cents / 100 + 200 * 450.00, abs=1e-9)


def test_the_delivery_table_through_a_run(unhedged):
    events = eh.table(unhedged, "expiry_events").set_index("osi_symbol")
    flows = eh.table(unhedged, "cash_flows")
    expected = {sym(FEB17, "C", 440.0): (2, 200), sym(MAR10, "C", 450.0): (-1, -100),
                sym(MAR10, "P", 455.0): (-1, 100), sym(MAR17, "P", 460.0): (1, -100),
                sym(MAR24, "P", 450.0): (1, -100), sym(APR21, "C", 450.0): (-1, -100)}
    for symbol, (contracts, shares) in expected.items():
        event = events.loc[symbol]
        assert (event.contracts, event.shares_delivered) == (contracts, shares)
        cash = flows.loc[(flows["kind"] == "settlement") & (flows["ref_id"] == event.event_id), "amount_cents"].item()
        assert cash == -shares * int(round(event.strike * 100))
    pnl = eh.table(unhedged, "daily_pnl").set_index("session_date")["shares"]
    assert pnl[FEB17] == 200 and pnl[MAR17] == -100 and pnl[MAR24] == -100 and pnl[APR21] == -100
    assert pnl[MAR10] == 0                     # the short call's -100 and the short 455 put's +100 net out


def test_the_pin_flag_through_a_run(unhedged):
    mar10, mar24, apr21 = events_on(unhedged, MAR10), events_on(unhedged, MAR24), events_on(unhedged, APR21)
    # S_set 450.01: both short 450s are inside the band, the assigned call and the put that expires.
    assert mar10[sym(MAR10, "C", 450.0)].pin_flag and mar10[sym(MAR10, "P", 450.0)].pin_flag
    assert not mar10[sym(MAR10, "P", 455.0)].pin_flag                 # assigned, $4.99 from its strike
    assert not any(row.pin_flag for row in mar24.values())             # longs are never flagged
    call = apr21[sym(APR21, "C", 450.0)]
    assert (call.event_type, call.pin_flag) == ("assigned", False)     # S_set 451.00: ITM by 1.00


def test_a_settled_lot_gets_one_intrinsic_row_out_of_nav(unhedged):
    # D11: a row at intrinsic for each lot settled today, kept out of NAV (the shares and cash are in it).
    marks = eh.table(unhedged, "position_marks")
    events = eh.table(unhedged, "expiry_events")
    settled = marks[marks["mark_source"] == "INTRINSIC"].set_index(["session_date", "lot_id"]).sort_index()
    assert list(settled.index) == sorted(zip(events["session_date"], events["lot_id"]))
    assert not settled["in_nav"].any()
    for event in events.itertuples():
        row = settled.loc[(event.session_date, event.lot_id)]
        value = max(event.settlement_price - event.strike, 0.0) if event.osi_symbol[12] == "C" else \
            max(event.strike - event.settlement_price, 0.0)
        assert row.qty == event.contracts and row.mark_price == pytest.approx(value, abs=1e-9)
        assert row.value_mid_usd == pytest.approx(event.contracts * 100 * value, abs=1e-9)
    # On a settlement day with nothing else open, no option value is in NAV.
    for day in (FEB17, MAR17, MAR24):
        row = pnl_on(unhedged, day)
        assert row.n_open_lots == 0 and row.option_value_mid == 0.0 and row.option_value_gross == 0.0
        assert row.nav_mid == pytest.approx(row.cash_cents / 100 + row.shares * row.spot, abs=1e-9)


def test_hedged_netting_trades_nothing_on_the_expiry_day(hedged):
    # ADR-0003 test 3: the long 460 put's hedge is +100 shares; S_set 450 exercises it (-100), the book is flat,
    # the day-t hedge (step 6, after settlement) trades 0 shares and no liquidation order is created.
    hedges = eh.table(hedged, "hedges").set_index("session_date")
    assert hedges.loc[D(2023, 3, 16), "shares_after"] == 100
    event = events_on(hedged, MAR17)[sym(MAR17, "P", 460.0)]
    assert (event.event_type, event.shares_delivered) == ("exercised", -100)
    expiry_day = hedges.loc[MAR17]
    assert expiry_day.delta_before_shares == 0.0 and expiry_day.shares_traded == 0 and expiry_day.shares_after == 0
    assert pnl_on(hedged, MAR17).shares == 0
    orders = eh.table(hedged, "orders")
    assert orders["intent"].tolist() == ["open"]
    assert not flows_on(hedged, MAR17)["kind"].isin(["hedge_trade", "share_trade"]).any()


def test_unhedged_shares_are_liquidated_at_the_next_close(unhedged):
    # ADR-0003 test 4: the same put without a hedge leaves -100 shares; a reduce-only order buys them back,
    # created at t and filled at the t+1 close, at the ADR-0002 §4 cost ($0.005 a share, $1.00 minimum, plus
    # $0.005 a share of slippage: 100 + 50 cents).
    next_day = D(2023, 3, 20)
    orders = eh.table(unhedged, "orders")
    order = orders[(orders["intent"] == "share_liquidation") & (orders["created_date"] == MAR17)].iloc[0]
    assert order.reduce_only and order.status == "filled"
    assert order.target_fill_date == order.resolved_date == next_day
    legs = eh.table(unhedged, "order_legs")
    assert legs.loc[legs["order_id"] == order.order_id, ["instrument", "ratio", "filled"]].values.tolist() == [
        ["share", 100, 100]]
    fills = eh.table(unhedged, "fills")
    fill = fills[fills["order_id"] == order.order_id].iloc[0]
    close_next = pnl_on(unhedged, next_day).spot
    assert (fill.fill_date, fill.instrument, fill.qty, fill.price_cents) == (next_day, "share", 100,
                                                                            int(round(close_next * 100)))
    assert fill.fees_cents == 150
    flows = flows_on(unhedged, next_day).set_index("kind")["amount_cents"]
    assert (flows["share_trade"], flows["share_commission"], flows["share_slippage"]) == (
        -100 * int(round(close_next * 100)), -100, -50)
    # The P&L from t to t+1 is -100 (S_t+1 - S_t), the cost, and the day's interest and borrow fee.
    before, after = pnl_on(unhedged, MAR17), pnl_on(unhedged, next_day)
    assert (before.shares, after.shares) == (-100, 0)
    carry = (flows["interest"] + flows["borrow_fee"]) / 100
    assert after.nav_mid - before.nav_mid == pytest.approx(-100 * (close_next - before.spot) - 1.50 + carry, abs=1e-6)
    # Every settlement that delivered shares got exactly one such order, for the opposite quantity.
    events = eh.table(unhedged, "expiry_events")
    delivered = events.groupby("session_date")["shares_delivered"].sum()
    liquidations = orders[orders["intent"] == "share_liquidation"].merge(legs, on="order_id")
    assert dict(zip(liquidations["created_date"], liquidations["ratio"])) == {
        day: -shares for day, shares in delivered.items() if shares != 0}


def test_an_order_on_a_settled_lot_is_cancelled_lot_removed(unhedged):
    # D12: the close order for the short 450 call was created on 04-20; 04-21 has no option snapshot, so it waits
    # (ADR-0002 §1), the call is assigned at step 4, and the order is cancelled with the lot.
    orders = eh.table(unhedged, "orders")
    close = orders[orders["intent"] == "close"].iloc[0]
    assert close.created_date == D(2023, 4, 20)
    assert (close.status, close.cancel_reason, close.resolved_date) == ("cancelled", "LOT_REMOVED", APR21)
    assert close.packages_filled == 0
    assert not pnl_on(unhedged, APR21).has_snapshot
    assert events_on(unhedged, APR21)[sym(APR21, "C", 450.0)].event_type == "assigned"


def test_a_run_refuses_to_open_a_contract_with_an_unmapped_non_session_expiry(store, tmp_path):
    # D16: Good Friday 2023-04-07 is not a session and no source maps it, so opening it stops the run.
    assert GOOD_FRIDAY not in set(es.sessions())
    strategy = eh.Scripted({D(2023, 3, 27): eh.open_legs([(sym(GOOD_FRIDAY, "C", 450.0), 1)])})
    with pytest.raises(UnmappedExpiry, match="2023-04-07"):
        eh.run(store, tmp_path, strategy, sample_end=D(2023, 3, 31))
