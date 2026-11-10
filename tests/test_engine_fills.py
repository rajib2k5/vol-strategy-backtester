"""The fill model (ADR-0002 tests 1-8), against volbt.engine.fills and through runs of the engine.

Two kinds of test. The unit tests call the fill functions with hand-worked numbers (the ADR's price table,
the 25% boundary in integers, the cap rules, the package rule, the hedge cost). The run tests drive the
daily loop on tests/engine_store.py's made-up store with single quotes edited (a zero bid, a crossed quote,
a volume, a dropped contract) and read the answer from the run's ledger: fills, orders, order_legs, lots,
cash_flows. Every expected number is worked by hand from the ADR; none comes from the code under test.

The module store is built once (about 5 s); each run on it takes a fraction of a second.
"""

from __future__ import annotations

from datetime import date
from fractions import Fraction

import numpy as np
import pandas as pd
import pytest

import engine_helpers as eh
import engine_store as es
from volbt.data import flags as quality
from volbt.engine import fills
from volbt.strategies.base import LegIntent, OrderIntent

APR = date(2023, 4, 21)
MAR = date(2023, 3, 17)
WEEKLY = date(2023, 3, 24)
K_ALL = (Fraction(0), Fraction(1, 4), Fraction(1, 2), Fraction(3, 4), Fraction(1))
K_SWEEP = (Fraction(1), Fraction(1, 2), Fraction(0))


def sym(expiry, right, strike):
    return es.symbol(expiry, right, float(strike))


def one(df: pd.DataFrame, **where) -> pd.Series:
    """The single row of df matching all of `where`."""
    for column, value in where.items():
        df = df[df[column] == value]
    assert len(df) == 1, f"expected one row for {where}, got {len(df)}"
    return df.iloc[0]


def opens(specs):
    """A script action: one opening order per spec (legs [(symbol, ratio)], packages, structure)."""
    def action(view, book, ctx):
        return [OrderIntent(None, "open", structure, tuple(LegIntent(s, r) for s, r in legs), packages)
                for legs, packages, structure in specs]
    return action


# --- the scenarios: dates, contracts and the edited quotes -----------------------------------------------

# A. quote states on the fill day (opening orders): created 2023-01-18, filled 2023-01-19
OD_A, FD_A = date(2023, 1, 18), date(2023, 1, 19)
BUY_TABLE = sym(APR, "C", 435)      # bid 2.00 / ask 2.10 on FD_A, bought
SELL_TABLE = sym(APR, "P", 365)     # bid 2.00 / ask 2.10 on FD_A, sold
LOCKED = sym(APR, "C", 430)         # bid = ask = 3.16, bought
ZERO_BID_OPEN = sym(APR, "C", 410)  # 0.00 / 0.05, sold to open
CROSSED_OPEN = sym(APR, "P", 385)   # 1.10 / 1.00, sold to open
EDGE_PASS = sym(APR, "P", 390)      # 0.70 / 0.90: exactly 25% of the mid, passes
EDGE_FAIL = sym(APR, "P", 395)      # 0.70 / 0.91: 26.1%, ILLIQUID
MINBID_PASS = sym(APR, "P", 375)    # 0.05 / 0.06: the smallest bid that may open
MINBID_FAIL = sym(APR, "P", 370)    # 0.04 / 0.05: ILLIQUID
LEG_CALL, LEG_PUT = sym(MAR, "C", 400), sym(MAR, "P", 400)   # a straddle whose put is ILLIQUID (0.03 / 0.04)

# B. reduce-only orders: opened 2023-01-24 (fills 01-25), closed by an order created 01-25, filled 2023-01-26
OD_B, CD_B, FD_B = date(2023, 1, 24), date(2023, 1, 25), date(2023, 1, 26)
SHORT_ZERO = sym(APR, "P", 370)     # short; 0.00 / 0.05 on FD_B: buy-to-close at the ask
LONG_ZERO = sym(APR, "P", 365)      # long; 0.00 / 0.05 on FD_B: the sale does not fill, the long is held
SHORT_CROSSED = sym(APR, "C", 420)  # short; crossed on FD_B: buy-to-close off the surface
LONG_CROSSED = sym(APR, "C", 415)   # long; crossed on FD_B: sell-to-close off the surface
PKG_CALL, PKG_PUT = sym(WEEKLY, "C", 400), sym(WEEKLY, "P", 400)   # long straddle, put 0.00 / 0.05 on FD_B

# C. the volume cap: created 2023-02-13 (V_t = the 02-13 volume), filled 2023-02-14
OD_C, FD_C = date(2023, 2, 13), date(2023, 2, 14)
VOL_850 = sym(APR, "C", 405)        # V_t 850, fill-day volume unchanged (1,000)
VOL_850_LOW = sym(APR, "C", 410)    # V_t 850, fill-day volume 50
VOL_850_HIGH = sym(APR, "C", 415)   # V_t 850, fill-day volume 50,000
VOL_5000 = sym(APR, "C", 420)       # V_t 5,000
VOL_NULL = sym(APR, "C", 425)       # V_t null
PKG85_CALL, PKG60_PUT = sym(APR, "C", 400), sym(APR, "P", 400)    # V_t 850 and 600
OD_C2, CD_C2, FD_C2 = date(2023, 2, 21), date(2023, 2, 22), date(2023, 2, 23)
REDUCE_ONLY_CAP = sym(APR, "C", 430)   # opened 90 on 02-22, closed by an order whose V_t is 50

# D. timing: created 2023-03-14, filled 2023-03-15
OD_D, FD_D = date(2023, 3, 14), date(2023, 3, 15)
LOWER_ASK_YESTERDAY = sym(APR, "C", 395)   # the 03-14 quote is $2.00 below the 03-15 quote
ABSENT_TOMORROW = sym(APR, "C", 390)       # dropped on 03-15


def build_edits() -> dict:
    spots = es.spot_path()
    edits: dict = {}

    def edit(day, symbol, **change):
        edits[(day, symbol)] = {**edits.get((day, symbol), {}), **change}

    edit(FD_A, BUY_TABLE, bid=2.00, ask=2.10)
    edit(FD_A, SELL_TABLE, bid=2.00, ask=2.10)
    edit(FD_A, LOCKED, bid=3.16, ask=3.16)
    edit(FD_A, ZERO_BID_OPEN, bid=0.00, ask=0.05)
    edit(FD_A, CROSSED_OPEN, bid=1.10, ask=1.00)
    edit(FD_A, EDGE_PASS, bid=0.70, ask=0.90)
    edit(FD_A, EDGE_FAIL, bid=0.70, ask=0.91)
    edit(FD_A, MINBID_PASS, bid=0.05, ask=0.06)
    edit(FD_A, MINBID_FAIL, bid=0.04, ask=0.05)
    edit(FD_A, LEG_PUT, bid=0.03, ask=0.04)

    edit(FD_B, SHORT_ZERO, bid=0.00, ask=0.05)
    edit(FD_B, LONG_ZERO, bid=0.00, ask=0.05)
    edit(FD_B, SHORT_CROSSED, bid=1.10, ask=1.00)
    edit(FD_B, LONG_CROSSED, bid=1.10, ask=1.00)
    edit(FD_B, PKG_PUT, bid=0.00, ask=0.05)

    edit(OD_C, VOL_850, volume=850.0)
    edit(OD_C, VOL_850_LOW, volume=850.0)
    edit(FD_C, VOL_850_LOW, volume=50.0)
    edit(OD_C, VOL_850_HIGH, volume=850.0)
    edit(FD_C, VOL_850_HIGH, volume=50_000.0)
    edit(OD_C, VOL_5000, volume=5_000.0)
    edit(OD_C, VOL_NULL, volume=float("nan"))
    edit(OD_C, PKG85_CALL, volume=850.0)
    edit(OD_C, PKG60_PUT, volume=600.0)
    edit(CD_C2, REDUCE_ONLY_CAP, volume=50.0)

    natural = pd.DataFrame(es.quotes_on(FD_D, spots[FD_D])).set_index("osi_symbol")
    edit(OD_D, LOWER_ASK_YESTERDAY, bid=round(natural.loc[LOWER_ASK_YESTERDAY, "bid"] - 2.0, 2),
         ask=round(natural.loc[LOWER_ASK_YESTERDAY, "ask"] - 2.0, 2))
    edit(FD_D, ABSENT_TOMORROW, drop=True)
    return edits


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    return es.built_store(tmp_path_factory.mktemp("fills_store"), edits=build_edits())


@pytest.fixture(scope="module")
def runs_root(tmp_path_factory):
    return tmp_path_factory.mktemp("fills_runs")


def natural_quote(day: date, symbol: str) -> pd.Series:
    """The made-up store's own quote of a contract, before any edit."""
    rows = pd.DataFrame(es.quotes_on(day, es.spot_path()[day])).set_index("osi_symbol")
    return rows.loc[symbol]


# --- unit tests: the pure functions ----------------------------------------------------------------------

@pytest.mark.parametrize("k, buy, sell", [
    (Fraction(1), 210, 200),
    (Fraction(1, 2), 208, 202),     # 2.075 -> 2.08 up, 2.025 -> 2.02 down
    (Fraction(0), 205, 205),
    (Fraction(1, 4), 207, 203),     # 2.0625 -> 2.07, 2.0375 -> 2.03
    (Fraction(3, 4), 209, 201),     # 2.0875 -> 2.09, 2.0125 -> 2.01
])
def test_price_table_for_a_2_00_by_2_10_quote(k, buy, sell):
    """ADR-0002 test 1: the integer-cent price of bid 2.00 / ask 2.10 at each k."""
    assert fills.price_cents(200, 210, k, +1) == buy
    assert fills.price_cents(200, 210, k, -1) == sell


def test_prices_at_exact_tick_boundaries_do_not_slip_a_cent():
    """ADR-0002 test 8: the k = 1 sell is 2.00 (not 1.99), the k = 0 sell 2.05 (not 2.04), the k = 1 buy 2.10."""
    assert fills.price_cents(200, 210, Fraction(1), -1) == 200
    assert fills.price_cents(200, 210, Fraction(0), -1) == 205
    assert fills.price_cents(200, 210, Fraction(1), +1) == 210
    # the reason the ADR demands integers: the dollar float form of the k = 1 sell is not 2.00
    assert (2.00 + 2.10) / 2 - (2.10 - 2.00) / 2 != 2.00


@pytest.mark.parametrize("k", K_ALL)
def test_price_property_over_100000_random_penny_quotes(k):
    """ADR-0002 test 8's property test, seeded: integers, k = 1 buy = ask and sell = bid, buy >= sell, and
    every price is the nearest tick outside mid +- k half-spreads (checked as an inequality, not recomputed)."""
    rng = np.random.default_rng(20231 + int(k * 4))
    n = 100_000
    bids = rng.integers(0, 200_000, n)
    spreads = np.where(rng.random(n) < 0.5, rng.integers(0, 40, n), rng.integers(0, 5_000, n))
    quarter = int(k * 4)
    for b, s in zip(bids.tolist(), spreads.tolist()):
        a = b + s
        buy, sell = fills.price_cents(b, a, k, +1), fills.price_cents(b, a, k, -1)
        assert isinstance(buy, (int, np.integer)) and isinstance(sell, (int, np.integer))
        assert b <= sell <= buy <= a
        # buy is the smallest integer >= mid + k h, sell the largest integer <= mid - k h, in eighths of a cent
        assert 8 * buy >= 4 * (b + a) + quarter * s > 8 * (buy - 1)
        assert 8 * sell <= 4 * (b + a) - quarter * s < 8 * (sell + 1)
        if k == 1:
            assert buy == a and sell == b
        if k == 0:
            assert buy - sell == (a + b) % 2


@pytest.mark.parametrize("k", K_SWEEP)
def test_zero_bid_quote_states(k):
    """ADR-0002 test 2 on the pure functions: bid 0.00 / ask 0.05."""
    cfg = eh.config(k=k)
    state = fills.quote_state(0, 5, int(quality.ZERO_BID))
    assert state == fills.ZERO_BID
    # a reduce-only buy fills at the ask whatever k is
    assert fills.leg_price(state, True, +1, 0, 5, None, None, cfg, False) == (5, "quote", None)
    # a reduce-only sell does not fill: the long is held
    assert fills.leg_price(state, True, -1, 0, 5, None, None, cfg, False) == (None, None, "ZERO_BID")
    # an opening order is rejected on either side
    assert fills.leg_price(state, False, -1, 0, 5, None, None, cfg, False) == (None, None, "ZERO_BID")
    assert fills.leg_price(state, False, +1, 0, 5, None, None, cfg, False) == (None, None, "ZERO_BID")


def test_crossed_and_missing_quote_states_on_the_pure_functions():
    """ADR-0002 test 3 and §7: crossed, one-sided, missing and stale are NO_QUOTE; an opening order is not
    filled; a reduce-only order is a surface fill, model mid +- m h rounded outward."""
    cfg = eh.config()
    for state in (fills.quote_state(110, 100, int(quality.CROSSED)),
                  fills.quote_state(None, 100, int(quality.BID_NULL)),
                  fills.quote_state(100, 110, int(quality.STALE)),
                  fills.quote_state(None, None, None)):
        assert state == fills.NO_QUOTE
    assert fills.leg_price(fills.NO_QUOTE, False, -1, 110, 100, 7.2545, 0.01, cfg, False) == (None, None, "NO_QUOTE")
    # surface: buy = ceil(7.2545 + 0.01) = 7.27, sell = floor(7.2545 - 0.01) = 7.24
    assert fills.leg_price(fills.NO_QUOTE, True, +1, 110, 100, 7.2545, 0.01, cfg, False) == (727, "surface", None)
    assert fills.leg_price(fills.NO_QUOTE, True, -1, 110, 100, 7.2545, 0.01, cfg, False) == (724, "surface", None)
    # no surface, no price: the reduce-only order cannot fill either
    assert fills.leg_price(fills.NO_QUOTE, True, +1, 110, 100, None, None, cfg, False) == (None, None, "NO_QUOTE")


@pytest.mark.parametrize("k", K_SWEEP)
def test_locked_quote_fills_at_its_price(k):
    cfg = eh.config(k=k)
    assert fills.quote_state(316, 316, int(quality.LOCKED)) == fills.VALID
    for reduce_only in (False, True):
        for side in (+1, -1):
            assert fills.leg_price(fills.VALID, reduce_only, side, 316, 316, None, None, cfg, False) == (316, "quote", None)


def test_the_25_percent_spread_boundary_in_integers():
    """ADR-0002 §7: exactly 25% of the mid passes, one cent more is ILLIQUID, and so is a bid under 5 cents."""
    cfg = eh.config()
    # (a - b) / mid = 25% exactly when 8 (a - b) = a + b, i.e. a = 9 b / 7; in floats 0.9 - 0.7 is 0.20000000000000007
    assert (0.90 - 0.70) / ((0.90 + 0.70) / 2) > 0.25
    for bid in range(7, 2_000, 7):
        ask = bid * 9 // 7
        assert fills.opening_liquid(bid, ask, cfg), (bid, ask)
        assert not fills.opening_liquid(bid, ask + 1, cfg), (bid, ask + 1)
    assert fills.opening_liquid(70, 90, cfg) and not fills.opening_liquid(70, 91, cfg)
    # the 5-cent minimum bid, with a spread well inside 25%
    assert fills.opening_liquid(5, 6, cfg) and not fills.opening_liquid(4, 5, cfg)
    assert not fills.opening_liquid(0, 5, cfg)


def test_cap_rules_for_one_leg():
    """ADR-0002 §5 / test 4 on leg_cap: (contracts, cap_type, volume_reliable)."""
    volume, hard = eh.config(cap_mode="volume"), eh.config(cap_mode="hard_only")
    d = date(2023, 3, 14)
    assert fills.leg_cap(volume, False, 850, d) == (85, "volume", True)
    assert fills.leg_cap(volume, False, 859, d)[0] == 85           # a floor, not a round
    assert fills.leg_cap(volume, False, 5_000, d)[0] == 100        # min(500, 100)
    assert fills.leg_cap(volume, False, None, d) == (100, "hard", False)     # null is unknown, never 0
    assert fills.leg_cap(hard, False, 850, d) == (100, "hard", True)         # hard_only ignores volume
    assert fills.leg_cap(volume, True, 850, d) == (100, "hard", True)        # reduce-only: the hard cap only
    # volume is unreliable before 2021-01-04: the hard cap, whatever the volume says
    assert fills.leg_cap(volume, False, 850, date(2020, 12, 31)) == (100, "hard", False)
    assert fills.leg_cap(volume, False, 850, date(2015, 6, 1)) == (100, "hard", False)
    assert fills.leg_cap(volume, False, 850, date(2021, 1, 4)) == (85, "volume", True)


def test_package_rule_and_fees_on_the_pure_functions():
    """ADR-0002 test 5: caps 85 and 60 fill 60 packages; 120 contracts pay 120 x $0.70 = $84.00."""
    cfg = eh.config()
    assert fills.package_count(120, [85, 60], [-1, -1]) == 60
    assert fills.package_count(50, [85, 60], [-1, -1]) == 50                 # never more than requested
    assert fills.package_count(100, [100, 101], [1, -2]) == 50               # floor(101 / 2) = 50
    assert fills.option_fee_cents(120, cfg) == 8400
    assert fills.option_fee_cents(-120, cfg) == 8400                         # per contract per side, both signs


def test_hedge_cost_rounds_half_up_in_decimal():
    """ADR-0002 test 6: 1,235 shares cost 618 + 618 cents (each is 6.175 exactly); round() on floats gives 6.17."""
    cfg = eh.config()
    assert fills.stock_cost_cents(1235, cfg) == (618, 618)
    assert fills.stock_cost_cents(-1235, cfg) == (618, 618)
    assert round(1235 * 0.005, 2) == 6.17            # the premise: the float route is wrong by a cent
    assert fills.stock_cost_cents(100, cfg) == (100, 50)       # the $1.00 minimum commission; slippage 0.50
    assert fills.stock_cost_cents(201, cfg) == (101, 101)      # 1.005 -> 1.01 (round() gives 1.0)
    assert fills.stock_cost_cents(0, cfg) == (0, 0)


# --- run tests: the quote states on the fill day -----------------------------------------------------------

@pytest.fixture(scope="module", params=K_SWEEP, ids=lambda k: f"k={k}")
def open_run(request, store, runs_root):
    """The opening-order scenario A, at one k."""
    k = request.param
    script = {OD_A: opens([
        ([(BUY_TABLE, 1)], 5, "custom"), ([(SELL_TABLE, -1)], 5, "custom"), ([(LOCKED, 1)], 5, "custom"),
        ([(ZERO_BID_OPEN, -1)], 5, "custom"), ([(CROSSED_OPEN, -1)], 5, "custom"),
        ([(EDGE_PASS, -1)], 5, "custom"), ([(EDGE_FAIL, -1)], 5, "custom"),
        ([(MINBID_PASS, -1)], 5, "custom"), ([(MINBID_FAIL, -1)], 5, "custom"),
        ([(LEG_CALL, -1), (LEG_PUT, -1)], 5, "short_straddle")])}
    result = eh.run(store, runs_root, eh.Scripted(script), k=k, stop_after=FD_A)
    orders, order_legs = eh.table(result, "orders"), eh.table(result, "order_legs")
    return k, result, orders, order_legs


def order_of(open_run, symbol):
    """(the order row, the legs row) of the single order that names `symbol`."""
    _, _, orders, legs = open_run
    leg = one(legs, osi_symbol=symbol)
    return one(orders, order_id=leg["order_id"]), leg


def fill_of(open_run, symbol):
    result = open_run[1]
    f = eh.table(result, "fills")
    return one(f, osi_symbol=symbol)


def test_price_table_through_a_run(open_run):
    """ADR-0002 test 1 through the loop: bid 2.00 / ask 2.10 bought and sold at each k, in integer cents."""
    k, result = open_run[0], open_run[1]
    buy = {Fraction(1): 210, Fraction(1, 2): 208, Fraction(0): 205}[k]
    sell = {Fraction(1): 200, Fraction(1, 2): 202, Fraction(0): 205}[k]
    bought, sold = fill_of(open_run, BUY_TABLE), fill_of(open_run, SELL_TABLE)
    assert (bought["fill_date"], bought["qty"], bought["price_cents"]) == (FD_A, 5, buy)
    assert (sold["fill_date"], sold["qty"], sold["price_cents"]) == (FD_A, -5, sell)
    assert bought["price"] == buy / 100 and sold["price"] == sell / 100
    assert (bought["bid"], bought["ask"], bought["fill_source"]) == (2.00, 2.10, "quote")
    assert bought["mid"] == pytest.approx(2.05) and bought["half_spread"] == pytest.approx(0.05)
    assert bought["k_half_spread"] == pytest.approx(float(k) * 0.05)
    # the cash follows the integer price exactly: premium = -qty x 100 x cents, and 70 cents a contract
    cash = eh.table(result, "cash_flows")
    premium = one(cash, kind="option_premium", ref_id=bought["fill_id"])
    fee = one(cash, kind="option_fee", ref_id=bought["fill_id"])
    assert premium["amount_cents"] == -5 * 100 * buy
    assert fee["amount_cents"] == -5 * 70 and bought["fees_cents"] == 350
    assert one(cash, kind="option_premium", ref_id=sold["fill_id"])["amount_cents"] == 5 * 100 * sell


def test_locked_quote_fills_at_its_price_through_a_run(open_run):
    locked = fill_of(open_run, LOCKED)
    assert (locked["price_cents"], locked["qty"], locked["half_spread"]) == (316, 5, 0.0)


def test_zero_bid_open_is_rejected_with_zero_bid(open_run):
    """ADR-0002 test 2, opening side: a sell-to-open into 0.00 / 0.05 is rejected, at every k."""
    order, _ = order_of(open_run, ZERO_BID_OPEN)
    assert (order["status"], order["cancel_reason"], order["packages_filled"]) == ("cancelled", "ZERO_BID", 0)
    assert order["resolved_date"] == FD_A
    fills_table = eh.table(open_run[1], "fills")
    assert order["order_id"] not in set(fills_table["order_id"])


def test_crossed_quote_open_is_not_filled(open_run):
    """ADR-0002 test 3, opening side: a crossed 1.10 / 1.00 quote gives NO_QUOTE."""
    order, _ = order_of(open_run, CROSSED_OPEN)
    assert (order["status"], order["cancel_reason"], order["packages_filled"]) == ("cancelled", "NO_QUOTE", 0)
    assert order["order_id"] not in set(eh.table(open_run[1], "fills")["order_id"])


def test_the_25_percent_boundary_and_the_5_cent_minimum_through_a_run(open_run):
    """ADR-0002 §7: 0.70 / 0.90 (exactly 25%) opens and 0.70 / 0.91 is ILLIQUID; a 0.05 bid opens, 0.04 does not."""
    k = open_run[0]
    passed = fill_of(open_run, EDGE_PASS)
    assert passed["qty"] == -5 and passed["price_cents"] == {Fraction(1): 70, Fraction(1, 2): 75, Fraction(0): 80}[k]
    for symbol in (EDGE_FAIL, MINBID_FAIL):
        order, _ = order_of(open_run, symbol)
        assert (order["status"], order["cancel_reason"]) == ("cancelled", "ILLIQUID"), symbol
        assert order["order_id"] not in set(eh.table(open_run[1], "fills")["order_id"])
    smallest = fill_of(open_run, MINBID_PASS)
    assert smallest["qty"] == -5 and smallest["price_cents"] == {Fraction(1): 5, Fraction(1, 2): 5, Fraction(0): 5}[k]


def test_an_opening_package_never_legs(open_run):
    """ADR-0002 §6: one ILLIQUID leg stops the whole straddle: no fill on either leg, no cash, no position."""
    result = open_run[1]
    order, _ = order_of(open_run, LEG_PUT)
    assert (order["status"], order["cancel_reason"], order["packages_filled"]) == ("cancelled", "ILLIQUID", 0)
    f = eh.table(result, "fills")
    assert order["order_id"] not in set(f["order_id"])
    assert not f["osi_symbol"].isin([LEG_CALL, LEG_PUT]).any()
    positions = eh.table(result, "positions")
    assert one(positions, position_id=order["position_id"])["status"] == "not_opened"
    lots = eh.table(result, "lots")
    assert order["position_id"] not in set(lots["position_id"])


# --- run tests: reduce-only orders -------------------------------------------------------------------------

@pytest.fixture(scope="module", params=K_SWEEP, ids=lambda k: f"k={k}")
def close_run(request, store, runs_root):
    k = request.param
    script = {OD_B: opens([
        ([(SHORT_ZERO, -1)], 5, "custom"), ([(LONG_ZERO, 1)], 5, "custom"),
        ([(SHORT_CROSSED, -1)], 5, "custom"), ([(LONG_CROSSED, 1)], 5, "custom"),
        ([(PKG_CALL, 1), (PKG_PUT, 1)], 3, "long_straddle")]),
        CD_B: eh.close_all()}
    result = eh.run(store, runs_root, eh.Scripted(script), k=k, stop_after=date(2023, 1, 30))
    return k, result


def closing(close_run, symbol):
    """(the closing fill row or None, the closing order row, the lot row) of the position holding `symbol`."""
    result = close_run[1]
    lots = eh.table(result, "lots")
    lot = one(lots, osi_symbol=symbol)
    orders = eh.table(result, "orders")
    order = one(orders[orders["intent"] == "close"], position_id=lot["position_id"])
    f = eh.table(result, "fills")
    f = f[(f["order_id"] == order["order_id"]) & (f["osi_symbol"] == symbol)]
    return (f.iloc[0] if len(f) else None), order, lot


def test_zero_bid_buy_to_close_fills_at_the_ask_whatever_k_is(close_run):
    """ADR-0002 test 2, reduce-only side: buying back a short at 0.00 / 0.05 costs 0.05 at every k."""
    fill, order, lot = closing(close_run, SHORT_ZERO)
    assert fill is not None
    assert (fill["fill_date"], fill["qty"], fill["price_cents"], fill["fill_source"]) == (FD_B, 5, 5, "quote")
    assert order["status"] == "filled" and lot["qty_open"] == 0


def test_zero_bid_sale_of_a_long_does_not_fill_and_the_long_is_held(close_run):
    fill, order, lot = closing(close_run, LONG_ZERO)
    assert fill is None
    assert (order["status"], order["cancel_reason"], order["packages_filled"]) == ("cancelled", "ZERO_BID", 0)
    assert lot["qty_open"] == 5 and pd.isna(lot["closed_date"])


def test_crossed_reduce_only_orders_fill_off_the_surface(close_run):
    """ADR-0002 test 3, reduce-only side: a crossed 1.10 / 1.00 quote is a surface fill, near the contract's
    own model price (about 7 and 9), not the 1.05 the crossed quote would suggest."""
    bought, order_b, lot_b = closing(close_run, SHORT_CROSSED)
    sold, order_s, lot_s = closing(close_run, LONG_CROSSED)
    for fill, qty, symbol in ((bought, 5, SHORT_CROSSED), (sold, -5, LONG_CROSSED)):
        assert fill is not None
        assert fill["fill_source"] == "surface" and fill["qty"] == qty and fill["fill_date"] == FD_B
        mid = natural_quote(FD_B, symbol)[["bid", "ask"]].mean()
        assert abs(fill["price_cents"] / 100 - mid) < 0.5 and fill["price_cents"] > 500
    # the buy is at or above the model mid and the sell at or below it (rounded outward by the half-spread)
    assert bought["price_cents"] / 100 >= bought["mid"] and sold["price_cents"] / 100 <= sold["mid"]
    assert order_b["status"] == "filled" and order_s["status"] == "filled"
    assert lot_b["qty_open"] == 0 and lot_s["qty_open"] == 0


def test_reduce_only_package_fills_leg_by_leg(close_run):
    """Decision D6: a long straddle whose put has a zero bid closes its call and holds the put."""
    call_fill, order, call_lot = closing(close_run, PKG_CALL)
    put_fill, _, put_lot = closing(close_run, PKG_PUT)
    k = close_run[0]
    assert call_fill is not None and put_fill is None
    assert call_fill["qty"] == -3 and call_fill["fill_date"] == FD_B
    assert (order["status"], order["cancel_reason"]) == ("partial", "ZERO_BID")
    assert call_lot["qty_open"] == 0
    assert put_lot["qty_open"] == 3 and pd.isna(put_lot["closed_date"])
    positions = eh.table(close_run[1], "positions")
    assert one(positions, position_id=put_lot["position_id"])["status"] == "open"
    # the call leg was sold at its own price from section 2 (the 03-24 400 call, 13.57 / 13.59 on 01-26)
    bid, ask = (round(v * 100) for v in natural_quote(FD_B, PKG_CALL)[["bid", "ask"]])
    assert call_fill["price_cents"] == fills.price_cents(bid, ask, k, -1)


# --- run tests: the volume cap ----------------------------------------------------------------------------

def cap_script():
    return {OD_C: opens([
        ([(VOL_850, -1)], 120, "custom"), ([(VOL_850_LOW, -1)], 120, "custom"), ([(VOL_850_HIGH, -1)], 120, "custom"),
        ([(VOL_5000, -1)], 120, "custom"), ([(VOL_NULL, -1)], 120, "custom"),
        ([(PKG85_CALL, -1), (PKG60_PUT, -1)], 120, "short_straddle")]),
        OD_C2: opens([([(REDUCE_ONLY_CAP, -1)], 90, "custom")]),
        CD_C2: eh.close_all()}


@pytest.fixture(scope="module", params=["volume", "hard_only"])
def cap_run(request, store, runs_root):
    mode = request.param
    result = eh.run(store, runs_root, eh.Scripted(cap_script()), cap_mode=mode, stop_after=date(2023, 2, 28))
    f = eh.table(result, "fills")
    return mode, result, f, eh.table(result, "orders"), eh.table(result, "lots")


def opening_fill(cap_run, symbol):
    f = cap_run[2]
    rows = f[(f["osi_symbol"] == symbol) & (f["fill_date"] == FD_C)]
    return one(rows)


def opening_order(cap_run, symbol):
    f = opening_fill(cap_run, symbol)
    return one(cap_run[3], order_id=f["order_id"])


def test_volume_cap_uses_the_order_dates_volume(cap_run):
    """ADR-0002 test 4: V_t = 850 gives a cap of 85; an order for 120 fills 85 and cancels 35 (CAP)."""
    mode = cap_run[0]
    fill, order = opening_fill(cap_run, VOL_850), opening_order(cap_run, VOL_850)
    if mode == "volume":
        assert fill["qty"] == -85 and fill["cap_contracts"] == 85 and fill["cap_type"] == "volume"
        assert (order["status"], order["cancel_reason"], order["packages_filled"]) == ("partial", "CAP", 85)
    else:
        assert fill["qty"] == -100 and fill["cap_contracts"] == 100 and fill["cap_type"] == "hard"
        assert (order["status"], order["cancel_reason"], order["packages_filled"]) == ("partial", "CAP", 100)
    # the information date is the ORDER date, before the fill date, and the volume is the order date's 850
    assert fill["cap_volume"] == 850 and fill["cap_volume_date"] == OD_C and fill["cap_volume_date"] < fill["fill_date"]
    assert fill["volume_reliable"]
    legs = eh.table(cap_run[1], "order_legs")
    leg = one(legs, order_id=fill["order_id"], leg_no=1)
    assert leg["cap_volume"] == 850 and leg["cap_volume_date"] == OD_C


def test_the_fill_days_volume_does_not_change_the_fill(cap_run):
    """ADR-0002 test 4's mutant check: the 02-14 volume set to 50 or to 50,000 leaves the fill alone."""
    base = opening_fill(cap_run, VOL_850)
    for symbol in (VOL_850_LOW, VOL_850_HIGH):
        changed = opening_fill(cap_run, symbol)
        for column in ("qty", "cap_contracts", "cap_type", "cap_volume", "cap_volume_date", "volume_reliable"):
            assert changed[column] == base[column], (symbol, column)
        assert opening_order(cap_run, symbol)["packages_filled"] == opening_order(cap_run, VOL_850)["packages_filled"]


def test_an_order_date_volume_of_5000_gives_the_hard_cap_of_100(cap_run):
    """ADR-0002 test 4: min(500, 100) = 100; the order for 120 fills 100."""
    fill = opening_fill(cap_run, VOL_5000)
    assert fill["qty"] == -100 and fill["cap_contracts"] == 100 and fill["cap_volume"] == 5000
    assert opening_order(cap_run, VOL_5000)["packages_filled"] == 100


def test_a_null_volume_is_unknown_not_zero(cap_run):
    """ADR-0002 test 4: a null V_t gives a cap of 100 with cap_type hard, in either cap mode."""
    fill = opening_fill(cap_run, VOL_NULL)
    assert fill["qty"] == -100 and fill["cap_contracts"] == 100
    assert fill["cap_type"] == "hard" and not fill["volume_reliable"]
    assert pd.isna(fill["cap_volume"])


def test_the_package_rule_through_a_run(cap_run):
    """ADR-0002 test 5: call-leg cap 85 and put-leg cap 60 fill 60 calls and 60 puts, fees 120 x $0.70 = $84.00."""
    mode, result, f, orders, _ = cap_run
    call = opening_fill(cap_run, PKG85_CALL)
    put = opening_fill(cap_run, PKG60_PUT)
    assert call["order_id"] == put["order_id"]
    if mode == "volume":
        assert (call["cap_contracts"], put["cap_contracts"]) == (85, 60)
        assert (call["qty"], put["qty"]) == (-60, -60)
        assert call["fees_cents"] + put["fees_cents"] == 8400
        cash = eh.table(result, "cash_flows")
        fees = cash[(cash["kind"] == "option_fee") & cash["ref_id"].isin([call["fill_id"], put["fill_id"]])]
        assert fees["amount_cents"].sum() == -8400
        order = one(orders, order_id=call["order_id"])
        assert (order["status"], order["cancel_reason"], order["packages_filled"]) == ("partial", "CAP", 60)
    else:
        assert (call["qty"], put["qty"]) == (-100, -100)
        assert call["fees_cents"] + put["fees_cents"] == 14_000


def test_the_remainder_is_never_carried(cap_run):
    """ADR-0002 §6: the 35 contracts the cap cancelled are not filled the next session or later."""
    mode, result, f, orders, _ = cap_run
    order = opening_order(cap_run, VOL_850)
    mine = f[f["order_id"] == order["order_id"]]
    assert len(mine) == 1 and mine.iloc[0]["fill_date"] == FD_C
    assert order["resolved_date"] == FD_C
    lots = eh.table(result, "lots")
    lot = one(lots, osi_symbol=VOL_850)
    assert lot["qty_opened"] == (-85 if mode == "volume" else -100)
    # the run went on for ten more sessions and no later fill of that order exists
    assert result.last_session > FD_C and not (f[f["order_id"] == order["order_id"]]["fill_date"] > FD_C).any()


def test_reduce_only_orders_get_the_hard_cap_only(cap_run):
    """ADR-0002 §5: a close whose V_t is 50 (a 5-contract volume cap) still closes all 90 contracts."""
    mode, result, f, orders, _ = cap_run
    opened = f[(f["osi_symbol"] == REDUCE_ONLY_CAP) & (f["fill_date"] == CD_C2)]
    closed = f[(f["osi_symbol"] == REDUCE_ONLY_CAP) & (f["fill_date"] == FD_C2)]
    assert len(opened) == 1 and opened.iloc[0]["qty"] == -90
    close = one(closed)
    assert close["qty"] == 90 and close["cap_contracts"] == 100 and close["cap_type"] == "hard"
    assert close["cap_volume"] == 50 and close["cap_volume_date"] == CD_C2
    lots = eh.table(result, "lots")
    assert one(lots, osi_symbol=REDUCE_ONLY_CAP)["qty_open"] == 0


# --- run tests: timing -------------------------------------------------------------------------------------

def timing_run(store, runs_root, fill_timing):
    script = {OD_D: opens([([(LOWER_ASK_YESTERDAY, 1)], 5, "custom"), ([(ABSENT_TOMORROW, 1)], 5, "custom")])}
    return eh.run(store, runs_root, eh.Scripted(script), fill_timing=fill_timing, stop_after=date(2023, 3, 17))


def test_an_order_fills_against_the_next_sessions_quotes(store, runs_root):
    """ADR-0002 test 7: created from the 03-14 snapshot, filled against 03-15, even though 03-14's ask was lower."""
    result = timing_run(store, runs_root, "next_close")
    f = eh.table(result, "fills")
    fill = one(f, osi_symbol=LOWER_ASK_YESTERDAY)
    tomorrow, yesterday = natural_quote(FD_D, LOWER_ASK_YESTERDAY), natural_quote(OD_D, LOWER_ASK_YESTERDAY)
    edited_yesterday_ask = round(tomorrow["ask"] - 2.0, 2)
    assert edited_yesterday_ask < tomorrow["ask"]
    assert fill["fill_date"] == FD_D
    assert fill["price_cents"] == round(tomorrow["ask"] * 100)          # k = 1 buy: the 03-15 ask, not 03-14's
    assert fill["price_cents"] != round(edited_yesterday_ask * 100) and fill["price_cents"] != round(yesterday["ask"] * 100)
    assert eh.table(result, "runs").iloc[0]["fill_timing"] == "next_close"


def test_a_contract_absent_on_the_fill_day_is_cancelled_with_no_quote(store, runs_root):
    """ADR-0002 test 7: the order for a contract missing from the 03-15 snapshot is cancelled with NO_QUOTE."""
    result = timing_run(store, runs_root, "next_close")
    legs = eh.table(result, "order_legs")
    leg = one(legs, osi_symbol=ABSENT_TOMORROW)
    order = one(eh.table(result, "orders"), order_id=leg["order_id"])
    assert (order["status"], order["cancel_reason"], order["resolved_date"]) == ("cancelled", "NO_QUOTE", FD_D)
    assert leg["order_id"] not in set(eh.table(result, "fills")["order_id"])


def test_same_close_fills_are_dated_the_order_day(store, runs_root):
    """ADR-0002 test 7: fill_timing = same_close is stamped in the run and the fills are dated 03-14."""
    result = timing_run(store, runs_root, "same_close")
    assert eh.table(result, "runs").iloc[0]["fill_timing"] == "same_close"
    f = eh.table(result, "fills")
    assert set(f["fill_date"]) == {OD_D}
    # same-close fills use the 03-14 quote (the edited, lower one) ...
    fill = one(f, osi_symbol=LOWER_ASK_YESTERDAY)
    assert fill["price_cents"] == round((natural_quote(FD_D, LOWER_ASK_YESTERDAY)["ask"] - 2.0) * 100)
    # ... so the contract that is absent on 03-15 is simply filled on 03-14
    assert one(f, osi_symbol=ABSENT_TOMORROW)["qty"] == 5


def test_orders_wait_over_a_session_with_no_snapshot(store, runs_root):
    """ADR-0002 §1: an order created on 2023-02-07 is not filled on 02-08 (no snapshot) but on 02-09."""
    assert es.MISSING_SNAPSHOT == date(2023, 2, 8)
    script = {date(2023, 2, 7): eh.open_straddle(MAR, 400.0, contracts=5)}
    result = eh.run(store, runs_root, eh.Scripted(script), stop_after=date(2023, 2, 10))
    f, orders = eh.table(result, "fills"), eh.table(result, "orders")
    assert set(f["fill_date"]) == {date(2023, 2, 9)} and len(f) == 2
    order = orders.iloc[0]
    assert (order["created_date"], order["status"], order["resolved_date"]) == (date(2023, 2, 7), "filled", date(2023, 2, 9))
    pnl = eh.table(result, "daily_pnl")
    assert not one(pnl, session_date=es.MISSING_SNAPSHOT)["has_snapshot"]
    assert one(pnl, session_date=date(2023, 2, 8))["n_open_lots"] == 0       # still flat on the session in between
    assert one(pnl, session_date=date(2023, 2, 9))["n_open_lots"] == 2
