"""Early exercise and assignment (ADR-0003 tests 5-7, §5), through early.decide_lot and as booked events.

decide_lot is the engine's step-10 decision for one lot; the hand-worked numbers of the ADR are its oracle. The
booked events come from runs on two made-up stores:

- tests/engine_store.py's own (the session fixture `engine_store`), where the reference strategy's short
  2023-03-17 400 call is early-assigned on 2023-03-16 (t + 1 is the ex-date and the expiry) and a 2023-04-21 415
  put on 2023-04-03 (the -8% gap). Its dividends make the projection on 03-16 the last one paid, 1.818, while
  1.616 is booked on 03-17.
- a copy moved up by 12.5% (strikes 410-490, every spot x 1.125) with S = 450.00 on 2023-03-16 and 1.80 booked
  on 2023-03-17: ADR-0003 test 5 with its own numbers, a short 440 call.
"""

import math
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

import numpy as np
import pandas as pd
import pytest
from scipy.optimize import brentq

import engine_helpers as eh
import engine_store as es
from volbt.data.store import session_calendar, view
from volbt.engine import early
from volbt.engine.book import Lot
from volbt.engine.surface import DaySurface
from volbt.pricing import black76, dividends, exercise, lattice
from volbt.strategies.reference import RollingShortStraddle

D = date
MAR16, MAR17, APR03, APR04 = D(2023, 3, 16), D(2023, 3, 17), D(2023, 4, 3), D(2023, 4, 4)
CALENDAR = es.sessions()
CFG = eh.config()
sym = es.symbol


def lot(right: str, strike: float, expiry: date, qty: int = -1) -> Lot:
    return Lot(1, 1, sym(expiry, right, strike), expiry, strike, right, qty, D(2023, 1, 3), expiry)


def paid(amount: float):
    """One dividend paid, so the projection is that amount (fewer than 8 paid: the last one)."""
    return [D(2022, 12, 16)], [amount]


# --- calls: ADR-0003 tests 5 and 6 --------------------------------------------------------------------------------

def test_a_short_call_is_assigned_the_day_before_an_ex_date_that_is_its_expiry():
    # ADR-0003 test 5: D = 1.80, short 440 call, S = 450, r = 5%. tau from the ex-date to expiry is 0, so the
    # threshold K (1 - e^0) + P_E(tau = 0) is 0 < 1.80.
    decision = early.decide_lot(lot("C", 440.0, MAR17), MAR16, MAR17, 450.0, 0.05, 0.20, paid(1.80), CALENDAR, CFG)
    assert decision["exercise"] is True and decision["method"] == "call_closed_form"
    assert decision["threshold"] == 0.0 and decision["dividend"] == 1.80 and decision["ex_date"] == MAR17
    assert early.event_type(-1) == "early_assigned" and early.event_type(3) == "early_exercised"


def test_no_assignment_with_30_days_left_after_the_ex_date():
    # ADR-0003 test 6: the interest term 440 (1 - e^(-0.05 x 30/365)) = 1.8045 plus a European put of 3.00 gives
    # 4.80 > 1.80. The ADR gives P_E, not sigma: sigma is the one at which Black-76 prices that put at 3.00.
    tau, ex_stock = 30 / 365, 450.0 - 1.80
    sigma = brentq(lambda s: float(black76.price(ex_stock * math.exp(0.05 * tau), 440.0, tau, 0.05, s, False)) - 3.00,
                   0.01, 1.0, xtol=1e-14)
    decision = early.decide_lot(lot("C", 440.0, MAR17 + timedelta(days=30)), MAR16, MAR17, 450.0, 0.05, sigma,
                                paid(1.80), CALENDAR, CFG)
    assert decision["exercise"] is False and decision["method"] == "call_closed_form"
    assert decision["threshold"] == pytest.approx(4.8045, abs=5e-5)


def test_the_interest_term_decides_when_the_dividend_beats_the_put_alone():
    # Deeper in the money the put is worth 1.48 < D = 1.80 < 1.48 + 1.8045: only the interest on K stops the
    # assignment (Cboe's "put < dividend" heuristic would assign it).
    expiry = MAR17 + timedelta(days=30)
    decision = early.decide_lot(lot("C", 440.0, expiry), MAR16, MAR17, 460.0, 0.05, 0.15, paid(1.80), CALENDAR, CFG)
    put = decision["threshold"] - 440 * (1 - math.exp(-0.05 * 30 / 365))
    assert put < 1.80 < decision["threshold"]
    assert decision["exercise"] is False


def test_the_call_rule_applies_only_on_the_eve_of_a_projected_ex_date_and_only_in_the_money():
    not_eve = early.decide_lot(lot("C", 440.0, MAR17), D(2023, 3, 15), MAR16, 450.0, 0.05, 0.2, paid(1.80),
                               CALENDAR, CFG)
    out_of_the_money = early.decide_lot(lot("C", 455.0, MAR17), MAR16, MAR17, 450.0, 0.05, 0.2, paid(1.80),
                                        CALENDAR, CFG)
    assert not_eve is None and out_of_the_money is None


def boundary(decide, low: float, high: float) -> float:
    """The spot where `decide` switches from False to True, by bisection to a tenth of a cent."""
    while high - low > 0.001:
        middle = (low + high) / 2
        low, high = (low, middle) if decide(middle) else (middle, high)
    return (low + high) / 2


def test_the_closed_form_agrees_with_the_lattice_optimum_within_5_cents():
    # ADR-0003 test 6: K = 450, sigma 0.20, r = 5%, 7 days from the ex-date to expiry, D = 1.70. The closed form
    # (decide_lot, one ex-date left) fires from S = 462.60, the lattice optimum from 462.61.
    expiry = MAR17 + timedelta(days=7)

    def closed_form(spot):
        return early.decide_lot(lot("C", 450.0, expiry), MAR16, MAR17, spot, 0.05, 0.20, paid(1.70), CALENDAR,
                                CFG)["exercise"]

    def lattice_optimum(spot):
        root = lattice.crr(spot, 450.0, 7 / 365, 0.05, 0.20, True, [[dividends.DROP_AFTER_CLOSE]], [[1.70]], 500)
        return root["continuation"][0] <= spot - 450.0

    closed, tree = boundary(closed_form, 451.0, 480.0), boundary(lattice_optimum, 451.0, 480.0)
    assert closed == pytest.approx(462.60, abs=0.01) and tree == pytest.approx(462.61, abs=0.01)
    assert abs(closed - tree) < 0.05


# --- puts: ADR-0003 test 7 -----------------------------------------------------------------------------------------

# K = 450, 30 days, sigma 0.20, N = 500, tol $0.005: case -> (spot, rate, the decision day, margin, assigned). The
# decision day puts no projected ex-date within 30 days, except in c: the 2023-03-17 ex-date drops just after the
# close of 03-16, 10 days after 03-06 (the ADR's dividend time 10/365; dividends.drop_time).
TABLE = {"a": (420.0, 0.05, APR03, 0.5201, False), "b": (400.0, 0.05, APR03, -0.0037, True),
         "c": (395.0, 0.05, D(2023, 3, 6), 1.0986, False), "d": (390.0, 0.0025, APR03, 0.0167, False)}


@pytest.mark.parametrize("case", sorted(TABLE))
def test_the_deep_itm_put_table(case):
    spot, rate, day, margin, assigned = TABLE[case]
    decision = early.decide_lot(lot("P", 450.0, day + timedelta(days=30)), day, day + timedelta(days=1), spot, rate,
                                0.20, paid(1.70), CALENDAR, CFG)
    assert decision["method"] == "crr" and decision["sigma"] == 0.20
    assert decision["threshold"] == pytest.approx(margin, abs=5e-5)
    assert decision["exercise"] is assigned
    if case == "c":
        assert dividends.schedule(*paid(1.70), day, day + timedelta(days=30), CALENDAR)[1] == [1.70]


def test_case_c_with_the_ex_date_itself_10_days_out_is_not_assigned_either():
    # With the engine's clock the dividend of an ex-date 10 days out drops after the close of day 9 (9/365):
    # the margin is larger than the ADR's 1.0986, and the decision is the same.
    day = D(2023, 3, 7)
    decision = early.decide_lot(lot("P", 450.0, day + timedelta(days=30)), day, day + timedelta(days=1), 395.0, 0.05,
                                0.20, paid(1.70), CALENDAR, CFG)
    assert decision["method"] == "crr" and decision["exercise"] is False and decision["threshold"] > 1.0986


def test_the_lattice_is_not_called_when_the_prefilter_fails(monkeypatch):
    # ADR-0003 test 7: at r = 5% and S = 430 the old inequality does not fire, so the put is not exercised and the
    # lattice is never run. A patched crr records every call (and still prices, so case a shows the patch works).
    calls = []
    real = lattice.crr

    def counting(*args, **kwargs):
        calls.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(lattice, "crr", counting)
    monkeypatch.setattr(exercise, "crr", counting)
    put = lot("P", 450.0, APR03 + timedelta(days=30))
    decision = early.decide_lot(put, APR03, APR04, 430.0, 0.05, 0.20, paid(1.70), CALENDAR, CFG)
    assert decision == {"exercise": False, "method": "prefilter", "sigma": 0.20, "dividend": None, "threshold": None,
                        "ex_date": None}
    assert calls == []
    early.decide_lot(put, APR03, APR04, 420.0, 0.05, 0.20, paid(1.70), CALENDAR, CFG)
    assert len(calls) == 1


def test_an_out_of_the_money_put_is_not_decided():
    assert early.decide_lot(lot("P", 450.0, APR03 + timedelta(days=30)), APR03, APR04, 450.0, 0.05, 0.2, paid(1.70),
                            CALENDAR, CFG) is None


# --- booked: ADR-0003 test 5 with its own numbers --------------------------------------------------------------------

@pytest.fixture(scope="module")
def test5_run(tmp_path_factory):
    moves = {day: round(spot * 1.125, 2) for day, spot in es.spot_path().items()}
    moves[MAR16] = 450.00
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(es, "STRIKES", np.arange(410.0, 491.0, 5.0))
        patch.setattr(es, "DIVIDENDS", es.DIVIDENDS[:-1] + [(MAR17, 1.80)])
        store = es.built_store(tmp_path_factory.mktemp("test5_store"), spot_moves=moves)
    strategy = eh.Scripted({D(2023, 3, 13): eh.open_legs([(sym(MAR17, "C", 440.0), -1)], 1, "short_call")})
    return eh.run(store, tmp_path_factory.mktemp("test5_runs"), strategy, hedge_mode="never",
                  sample_end=D(2023, 3, 24))


def test_test5_books_minus_100_shares_and_44000_then_the_dividend_at_the_start_of_t_plus_1(test5_run):
    events = eh.table(test5_run, "expiry_events")
    assert len(events) == 1
    event = events.iloc[0]
    assert (event.session_date, event.effective_date, event.event_type) == (MAR16, MAR17, "early_assigned")
    assert (event.contracts, event.shares_delivered, event.strike) == (-1, -100, 440.0)
    assert (event.decision_method, event.threshold_value, event.dividend_ex_date) == ("call_closed_form", 0.0, MAR17)
    assert event.dividend_amount == 1.818              # projected from the dividends paid by 03-16, not the 1.80
    flows = eh.table(test5_run, "cash_flows")
    assert not flows.loc[flows["session_date"] == MAR16, "kind"].isin(["early_settlement", "dividend"]).any()
    day = flows[flows["session_date"] == MAR17].sort_values("flow_id")
    # In this order: the shares at K (cash +$44,000), then the dividend on them (-100 x 1.80 = -$180).
    assert day[["kind", "amount_cents"]].values.tolist()[:2] == [["early_settlement", 4_400_000],
                                                                 ["dividend", -18_000]]
    assert day["ref_id"].iloc[0] == event.event_id
    # The -100 shares booked before 03-17 opened are bought back at the 03-17 close: the book is unhedged
    # (ADR-0003 §3 and §5), so a share_liquidation order created on 03-16 fills at the next close.
    share_fills = eh.table(test5_run, "fills").query("instrument == 'share'")
    assert share_fills[["fill_date", "qty"]].values.tolist() == [[MAR17, 100]]
    shares = eh.table(test5_run, "daily_pnl").set_index("session_date")["shares"]
    assert (shares[MAR16], shares[MAR17]) == (0, 0)
    lots = eh.table(test5_run, "lots")
    assert (lots["qty_open"].item(), lots["closed_date"].item()) == (0, MAR17)


def test_an_unhedged_book_liquidates_early_assigned_shares(test5_run):
    # ADR-0003 §5: liquidation of early-delivered shares follows point 3. This was an xfail (strict) until the engine
    # created the share_liquidation order at step 10 (the -100 shares used to be held to the end of the run).
    # The shares must come from the early assignment (an expiry assignment on 03-17 gets its order at step 4).
    assert eh.table(test5_run, "expiry_events")["event_type"].tolist() == ["early_assigned"]
    orders = eh.table(test5_run, "orders")
    legs = eh.table(test5_run, "order_legs")
    liquidations = orders[orders["intent"] == "share_liquidation"].merge(legs, on="order_id")
    assert liquidations["ratio"].tolist() == [100]
    assert eh.table(test5_run, "daily_pnl")["shares"].iloc[-1] == 0


# --- booked: the reference strategy on the fixture --------------------------------------------------------------------

@pytest.fixture(scope="module")
def reference(engine_store, tmp_path_factory):
    return eh.run(engine_store, tmp_path_factory.mktemp("early_reference"), RollingShortStraddle(exit_dte=0))


def surface_on(store, day: date) -> DaySurface:
    """The day's surface as step 1 builds it, through that day's view."""
    day_view = view(day, "validation", store)
    rates = day_view.rates()
    rate = float(rates.loc[rates["date"] < pd.Timestamp(day), "r_cc"].iloc[-1])
    paid_rows = day_view.dividends()
    paid_by = ([d.date() for d in pd.to_datetime(paid_rows["ex_date"])], [float(a) for a in paid_rows["amount"]])
    spot = float(day_view.spy_bars()["close"].iloc[-1])
    return DaySurface.from_view(day_view, day, "optionsdx", spot, rate, paid_by, session_calendar(store))


def surface_sigma(store, day: date, expiry: date, strike: float) -> float:
    surface = surface_on(store, day)
    forward, _ = surface.forward(expiry)
    return float(surface.iv(expiry, math.log(strike / forward))[0][0])


def test_the_march_call_assignment_uses_the_projected_dividend_and_is_booked_on_the_ex_date(engine_store, reference):
    events = eh.table(reference, "expiry_events")
    call = events[events["event_type"] == "early_assigned"].iloc[0]
    assert call.osi_symbol == sym(MAR17, "C", 400.0)
    assert (call.session_date, call.effective_date, call.dividend_ex_date) == (MAR16, MAR17, MAR17)
    assert call.decision_method == "call_closed_form"
    # The projection from the dividends paid by 03-16 (fewer than 8: the last, 2022-12-16's 1.818), never the
    # 1.616 that goes ex on 03-17 and is booked then.
    assert call.dividend_amount == 1.818
    flows = eh.table(reference, "cash_flows")
    assert flows.loc[flows["kind"] == "dividend", "session_date"].tolist() == [MAR17]
    # Every contract of the short lot is assigned: -10 contracts, -1,000 shares, +$400,000.
    assert (call.contracts, call.shares_delivered) == (-10, -1000)
    early_cash = flows[flows["kind"] == "early_settlement"]
    booked = early_cash[early_cash["ref_id"] == call.event_id]
    assert booked[["session_date", "amount_cents"]].values.tolist() == [[MAR17, 40_000_000]]
    lots = eh.table(reference, "lots").set_index("lot_id")
    assert (lots.loc[call.lot_id, "qty_open"], lots.loc[call.lot_id, "closed_date"]) == (0, MAR17)


def test_the_early_shares_arrive_at_the_start_of_t_plus_1_before_the_dividend(reference):
    # Mutant 16 (booked on day t) moves the flow to 03-16; mutant 19 (dividend first) pays it on the shares held
    # before the assignment.
    flows = eh.table(reference, "cash_flows").sort_values("flow_id")
    pnl = eh.table(reference, "daily_pnl").set_index("session_date")
    day = flows[flows["session_date"] == MAR17]
    assert day["kind"].tolist()[:2] == ["early_settlement", "dividend"]
    held = int(pnl.loc[MAR16, "shares"]) - 1000            # the hedge at the 03-16 close, then the assignment
    expected = int((Decimal(held) * Decimal("1.616") * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    assert day.loc[day["kind"] == "dividend", "amount_cents"].item() == expected
    marks = eh.table(reference, "position_marks")
    call_lot = eh.table(reference, "expiry_events").query("event_type == 'early_assigned'")["lot_id"].iloc[0]
    assert sorted(marks.loc[marks["lot_id"] == call_lot, "session_date"])[-1] == MAR16   # no mark once it is gone


def test_decision_iv_is_the_surface_iv_at_the_lots_log_moneyness(engine_store, reference):
    # sigma is the day's surface IV at the lot's k for its expiry (ADR-0003 §5), never t+1's (look-ahead).
    events = eh.table(reference, "expiry_events").set_index("session_date")
    call, put = events.loc[MAR16], events.loc[APR03]
    assert call.decision_iv == surface_sigma(engine_store, MAR16, MAR17, 400.0)
    assert call.decision_iv != float(surface_on(engine_store, MAR16).iv(MAR17, 0.0)[0][0])    # not the ATM IV
    assert put.decision_iv == surface_sigma(engine_store, APR03, D(2023, 4, 21), 415.0)
    assert put.decision_iv != surface_sigma(engine_store, APR04, D(2023, 4, 21), 415.0)
    # The put went through the lattice: assigned at a margin within the $0.005 tolerance, on all 10 contracts.
    assert (put.event_type, put.decision_method, put.contracts, put.shares_delivered) == (
        "early_assigned", "crr", -10, 1000)
    assert put.threshold_value <= 0.005 and put.effective_date == APR04


def test_a_long_itm_put_that_qualifies_is_exercised_by_us(engine_store, tmp_path):
    put = sym(D(2023, 4, 21), "P", 415.0)
    strategy = eh.Scripted({D(2023, 3, 20): eh.open_legs([(put, 1)], 2, "long_put")})
    result = eh.run(engine_store, tmp_path, strategy, sample_end=D(2023, 4, 6))
    events = eh.table(result, "expiry_events")
    assert events[["session_date", "effective_date", "osi_symbol", "event_type", "contracts", "shares_delivered",
                   "decision_method"]].values.tolist() == [[APR03, APR04, put, "early_exercised", 2, -200, "crr"]]
    flows = eh.table(result, "cash_flows")
    booked = flows[(flows["kind"] == "early_settlement")]
    assert booked[["session_date", "amount_cents", "ref_id"]].values.tolist() == [
        [APR04, 8_300_000, events["event_id"].item()]]


def test_a_pending_close_on_an_early_assigned_lot_is_cancelled_lot_removed(engine_store, tmp_path):
    # The close order created on 03-16 would fill at the 03-17 close, but the call it names is assigned at the start
    # of 03-17: the whole package is cancelled (ADR-0001 §1.2), and the put it named expires at 03-17's settlement.
    strategy = eh.Scripted({D(2023, 3, 1): eh.open_straddle(MAR17, 400.0, 1, -1), MAR16: eh.close_all()})
    result = eh.run(engine_store, tmp_path, strategy, sample_end=D(2023, 3, 20))
    orders = eh.table(result, "orders")
    close = orders[orders["intent"] == "close"].iloc[0]
    assert (close.created_date, close.status, close.cancel_reason, close.resolved_date) == (
        MAR16, "cancelled", "LOT_REMOVED", MAR17)
    events = eh.table(result, "expiry_events").set_index("osi_symbol")
    assert events.loc[sym(MAR17, "C", 400.0), "event_type"] == "early_assigned"
    assert events.loc[sym(MAR17, "P", 400.0), "event_type"] == "expired_worthless"
