"""The delta hedge (ADR-0005 tests 1, 2, 3, 5, 6 and the weekly schedule; ADR-0003 test 3).

The hedge's decisions are worked by hand: 1,234.5 shares round to 1,235 (half away from zero), a 1% band at NAV
$1M and S 400 is 25 shares, every_n_sessions = 5 hedges on the run's sessions 1, 6, 11. The loop's own steps 2 and 6
are called on a hand-made state for the exact ADR numbers, and the engine is run on tests/engine_store.py's made-up
store for the sign, the schedule, the band and the netting of delivered shares on an expiry day.

ADR-0005 test 1 is checked on 100 straddles (S = F = K = 400, sigma 0.20, 30/365, r = 0): the integer hedge is -229
shares and the hedged one-day P&L for S -> 404 is the Black-76 repricing at 29/365 less 229 x $4, to the cent.
"""

from __future__ import annotations

from datetime import date
from fractions import Fraction

import pytest

import engine_helpers as eh
import engine_store as es
from volbt.engine import hedge, loop, marks
from volbt.pricing import black76
from volbt.strategies.base import LegIntent, OrderIntent
from volbt.strategies.reference import RollingShortStraddle

APR = date(2023, 4, 21)
MAR = date(2023, 3, 17)


# --- rounding and the hand-worked decisions ----------------------------------------------------------------

def test_round_half_away_from_zero():
    """ADR-0005 §1: 1,234.5 -> 1,235 and -1,234.5 -> -1,235; Python's round() gives 1,234 (banker's rounding)."""
    assert round(1234.5) == 1234 and round(2.5) == 2                      # the premise
    for value, expected in ((1234.5, 1235), (-1234.5, -1235), (2.5, 3), (-2.5, -3), (0.5, 1), (-0.5, -1),
                            (2.4999, 2), (-2.4999, -2), (1234.6, 1235), (1234.4, 1234), (0.0, 0), (0.49, 0)):
        assert hedge.round_half_away(value) == expected, value


def test_the_hedge_sells_a_positive_net_delta_and_buys_a_negative_one():
    """ADR-0005 test 2: net +1,234.6 shares -> sell 1,235. The sign: a positive net delta sells (negative trade)."""
    assert hedge.hedge_shares(1234.6) == -1235
    assert hedge.hedge_shares(-1234.6) == 1235
    assert hedge.hedge_shares(1234.5) == -1235 and hedge.hedge_shares(-1234.5) == 1235
    assert hedge.hedge_shares(0.0) == 0 and hedge.hedge_shares(0.3) == 0
    assert hedge.hedge_shares(30.0) == -30


def test_band_hedging_trades_only_when_the_exposure_exceeds_the_band():
    """ADR-0005 test 3: band 1%, NAV $1M, S = 400 (band = 25 shares): 20 shares no trade, 30 shares sell 30."""
    cfg = eh.config(hedge_mode="band", hedge_band_pct_nav=Fraction(1, 100))
    assert hedge.hedge_due(cfg, 0, 20.0, 400.0, 1_000_000.0) == (False, "band")
    assert hedge.hedge_due(cfg, 0, 30.0, 400.0, 1_000_000.0) == (True, "band")
    assert hedge.hedge_shares(30.0) == -30
    # the edge: exactly 25 shares is 10,000 = 1% of NAV, which is not above the band; a hundredth more is
    assert hedge.hedge_due(cfg, 0, 25.0, 400.0, 1_000_000.0) == (False, "band")
    assert hedge.hedge_due(cfg, 0, 25.01, 400.0, 1_000_000.0) == (True, "band")
    # short deltas count the same, and the band scales with NAV
    assert hedge.hedge_due(cfg, 0, -30.0, 400.0, 1_000_000.0)[0] is True
    assert hedge.hedge_due(cfg, 0, 30.0, 400.0, 2_000_000.0)[0] is False


def test_every_n_sessions_5_is_due_on_the_runs_sessions_1_6_11():
    """ADR-0005 test 4's schedule (indices 0, 5, 10 of the run); never is never."""
    cfg = eh.config(hedge_mode="time", hedge_every_n=5)
    due = [i for i in range(16) if hedge.hedge_due(cfg, i, 10.0, 400.0, 1e6) == (True, "schedule")]
    assert due == [0, 5, 10, 15]
    daily = eh.config(hedge_mode="time", hedge_every_n=1)
    assert all(hedge.hedge_due(daily, i, 0.0, 400.0, 1e6)[0] for i in range(6))
    never = eh.config(hedge_mode="never")
    assert not any(hedge.hedge_due(never, i, 9_999.0, 400.0, 1e6)[0] for i in range(6))


# --- the loop's steps on a hand-made state -------------------------------------------------------------------

def bare_run(store, **overrides) -> loop.Run:
    calendar = [date(2023, 1, 3), date(2023, 1, 4), date(2023, 1, 5)]
    return loop.Run(eh.config(**overrides), eh.Scripted({}), store, calendar, calendar)


def set_day(run: loop.Run, day: date, spot: float, lots: list[tuple[float, float]]) -> None:
    """lots: (delta_shares, value_mid_usd) of each open lot at the close of `day`."""
    run.today = {"t": day, "spot": spot, "flows": {}, "has_snapshot": True, "rate": 0.0,
                 "marks": [{"in_nav": True, "delta_shares": d, "value_mid_usd": v} for d, v in lots]}


def test_net_delta_1234_6_sells_1235_shares_for_618_plus_618_cents(engine_store):
    """ADR-0005 test 2 through step 6: sold at the close, commission 618 and slippage 618 cents (6.175 each,
    half up), the proceeds in cash, the hedge row recording the trade."""
    run = bare_run(engine_store)
    day = date(2023, 1, 3)
    set_day(run, day, 400.0, [(1234.6, 0.0)])
    start = run.book.cash_cents
    run.step_06_hedge(day, 0)
    assert run.book.shares == -1235
    row = run.ledger.rows["hedges"][-1]
    assert (row["session_date"], row["executed_date"], row["trigger"]) == (day, day, "schedule")
    assert (row["shares_traded"], row["price_cents"], row["shares_after"]) == (-1235, 40_000, -1235)
    assert (row["commission_cents"], row["slippage_cents"]) == (618, 618)
    assert row["delta_before_shares"] == pytest.approx(1234.6)
    assert row["delta_after_shares"] == pytest.approx(-0.4)
    assert run.book.cash_cents == start + 1235 * 40_000 - 618 - 618
    kinds = {(f["kind"], f["amount_cents"]) for f in run.ledger.rows["cash_flows"]}
    assert kinds == {("hedge_trade", 49_400_000), ("hedge_commission", -618), ("hedge_slippage", -618)}


def test_band_mode_leaves_20_shares_alone_and_sells_30(engine_store):
    cfg = dict(hedge_mode="band", hedge_band_pct_nav=Fraction(1, 100))
    day = date(2023, 1, 3)
    small = bare_run(engine_store, **cfg)
    set_day(small, day, 400.0, [(20.0, 0.0)])
    small.step_06_hedge(day, 0)
    assert small.ledger.rows["hedges"] == [] and small.book.shares == 0
    large = bare_run(engine_store, **cfg)
    set_day(large, day, 400.0, [(30.0, 0.0)])
    large.step_06_hedge(day, 0)
    row = large.ledger.rows["hedges"][-1]
    assert (row["trigger"], row["shares_traded"]) == ("band", -30)
    assert large.book.shares == -30
    # the commission is the $1.00 minimum, slippage 30 x 0.005 = 0.15
    assert (row["commission_cents"], row["slippage_cents"]) == (100, 15)


def test_hedge_shares_already_held_count_in_the_net_delta(engine_store):
    run = bare_run(engine_store)
    day = date(2023, 1, 3)
    run.book.shares = 100
    set_day(run, day, 400.0, [(-99.6, 0.0)])
    run.step_06_hedge(day, 0)
    assert run.book.shares == 100 and run.ledger.rows["hedges"][-1]["shares_traded"] == 0     # net +0.4 -> 0
    run.book.shares = 150
    set_day(run, day, 400.0, [(-99.6, 0.0)])
    run.step_06_hedge(day, 1)
    assert run.book.shares == 100 and run.ledger.rows["hedges"][-1]["shares_traded"] == -50   # net +50.4 -> sell 50


def test_a_dividend_on_100_short_shares_costs_150_dollars_at_step_2_of_the_ex_date(engine_store):
    """ADR-0005 test 5: holding -100 shares at the close before a $1.50 ex-date -> cash -$150.00 at step 2."""
    ex_date = date(2023, 3, 17)
    run = bare_run(engine_store)
    run.book.shares = -100
    run.today = {"t": ex_date, "paid": ([date(2022, 12, 16), ex_date], [1.818, 1.50]), "flows": {}}
    start = run.book.cash_cents
    run.step_02_start_of_day(ex_date)
    assert run.book.cash_cents == start - 15_000
    assert [(f["kind"], f["amount_cents"], f["session_date"]) for f in run.ledger.rows["cash_flows"]] == \
        [("dividend", -15_000, ex_date)]
    # long shares receive it; flat books and other days get nothing
    long = bare_run(engine_store)
    long.book.shares = 100
    long.today = {"t": ex_date, "paid": ([ex_date], [1.50]), "flows": {}}
    long.step_02_start_of_day(ex_date)
    assert long.book.cash_cents == start + 15_000
    flat = bare_run(engine_store)
    flat.today = {"t": ex_date, "paid": ([ex_date], [1.50]), "flows": {}}
    flat.step_02_start_of_day(ex_date)
    assert flat.book.cash_cents == start and flat.ledger.rows["cash_flows"] == []
    other = bare_run(engine_store)
    other.book.shares = -100
    other.today = {"t": date(2023, 3, 16), "paid": ([ex_date], [1.50]), "flows": {}}
    other.step_02_start_of_day(date(2023, 3, 16))
    assert other.book.cash_cents == start


# --- ADR-0005 test 1 on 100 straddles ---------------------------------------------------------------------------

def straddle_marks(spot: float, forward: float, tau: float, strike: float = 400.0, sigma: float = 0.20,
                   contracts: int = 100):
    """(delta_shares, value_mid_usd) of `contracts` long calls and of `contracts` long puts, from the pricing library."""
    rows = []
    for is_call in (True, False):
        greeks = black76.greeks_usd(contracts, spot, forward, strike, tau, 0.0, sigma, is_call)
        price = float(black76.price(forward, strike, tau, 0.0, sigma, is_call))
        rows.append((float(greeks["delta_shares"]), contracts * 100 * price))
    return rows


def test_100_straddles_hedged_with_an_integer_229_shares_repriced_to_the_cent(engine_store):
    """ADR-0005 test 1: net delta 228.7 shares -> sell 229; for S -> 404 and one day less (29/365) the hedged P&L is
    the Black-76 repricing of the 100 straddles less 229 x $4, which also fixes the sign of the hedge trade."""
    run = bare_run(engine_store)
    day0, day1 = date(2023, 1, 3), date(2023, 1, 4)
    tau0, tau1 = 30 / 365, 29 / 365
    book0 = straddle_marks(400.0, 400.0, tau0)
    assert sum(d for d, _ in book0) == pytest.approx(228.7, abs=0.05)        # ADR-0005: delta +2.287 shares per straddle
    set_day(run, day0, 400.0, book0)
    run.step_06_hedge(day0, 0)
    assert run.book.shares == -229
    assert run.ledger.rows["hedges"][-1]["shares_traded"] == -229
    nav0 = marks.nav(run.book.cash_cents, run.book.shares, 400.0, [v for _, v in book0])
    # one day later: spot 404, forward 404 (r = 0), the same sigma, 29 days left, no other cash flow
    book1 = straddle_marks(404.0, 404.0, tau1)
    nav1 = marks.nav(run.book.cash_cents, run.book.shares, 404.0, [v for _, v in book1])
    reprice = sum(v for _, v in book1) - sum(v for _, v in book0)             # 100 straddles, USD
    expected = reprice - 229 * (404.0 - 400.0)
    assert nav1 - nav0 == pytest.approx(expected, abs=0.005)
    # the ADR's own table: -$2.82 per straddle at S -> 404 with a fractional hedge of 228.7 shares
    assert reprice - 228.7 * 4 == pytest.approx(-282, abs=0.5)
    assert expected == pytest.approx(-282.88, abs=0.005)
    # a hedge with the wrong sign (+229 shares) would have lost 2 x 229 x 4 = $1,832 more
    assert abs((nav1 - nav0) - (reprice + 229 * 4)) > 1_800


# --- runs: sign, schedule, band, netting -------------------------------------------------------------------------

def assert_hedge_rows_are_flat_to_half_a_share(result) -> None:
    hedges, pnl = eh.table(result, "hedges"), eh.table(result, "daily_pnl")
    by_day = pnl.set_index("session_date")
    assert len(hedges) > 0
    for _, row in hedges.iterrows():
        assert abs(row["shares_traded"] + row["delta_before_shares"]) <= 0.5 + 1e-9, row["session_date"]
        assert abs(row["delta_after_shares"]) <= 0.5 + 1e-9
        assert row["price"] == by_day.loc[row["session_date"], "spot"]            # at the same close
        assert row["shares_after"] == by_day.loc[row["session_date"], "shares"]


@pytest.fixture(scope="module")
def short_put_run(engine_store, tmp_path_factory):
    def action(view, book, ctx):
        return [OrderIntent(None, "open", "custom", (LegIntent(es.symbol(APR, "P", 380.0), -1),), 50)]

    return eh.run(engine_store, tmp_path_factory.mktemp("hedge_short_put"), eh.Scripted({date(2023, 1, 10): action}),
                  stop_after=date(2023, 3, 3))


@pytest.fixture(scope="module")
def long_put_run(engine_store, tmp_path_factory):
    put = es.symbol(MAR, "P", 430.0)

    def action(view, book, ctx):
        return [OrderIntent(None, "open", "custom", (LegIntent(put, 1),), 1)]

    return eh.run(engine_store, tmp_path_factory.mktemp("hedge_long_put"), eh.Scripted({date(2023, 3, 9): action}),
                  stop_after=date(2023, 3, 20))


def test_a_short_put_has_positive_delta_so_the_hedge_sells(short_put_run):
    """The hedge sign through a run: a short put is long delta, the first hedge after the fill is a SALE of about
    its delta, and every later hedge returns the book to within half a share of zero."""
    hedges = eh.table(short_put_run, "hedges")
    first = hedges[hedges["shares_traded"] != 0].iloc[0]
    assert first["session_date"] == date(2023, 1, 11)                          # the fill day: the first close with a lot
    assert first["delta_before_shares"] > 100 and first["shares_traded"] < -100
    assert first["shares_after"] == first["shares_traded"]
    assert_hedge_rows_are_flat_to_half_a_share(short_put_run)
    assert (eh.table(short_put_run, "daily_pnl").query("session_date >= @first.session_date")["shares"] < 0).sum() >= 15


def test_a_long_put_has_negative_delta_so_the_hedge_buys(long_put_run):
    hedges = eh.table(long_put_run, "hedges")
    first = hedges[hedges["shares_traded"] != 0].iloc[0]
    assert first["session_date"] == date(2023, 3, 10)
    assert first["delta_before_shares"] == pytest.approx(-98.26, abs=0.5) and first["shares_traded"] == 98
    assert_hedge_rows_are_flat_to_half_a_share(long_put_run)


def test_a_hedged_book_trades_zero_shares_on_the_expiry_day_after_delivery(long_put_run):
    """ADR-0005 test 6 = ADR-0003 test 3: one long ITM put and +100 hedge shares; the put is exercised on the
    expiry day, delivers -100 shares, and the hedge that day trades 0 shares; no liquidation order exists."""
    pnl = eh.table(long_put_run, "daily_pnl").set_index("session_date")
    assert pnl.loc[date(2023, 3, 16), "shares"] == 100 and pnl.loc[date(2023, 3, 16), "n_open_lots"] == 1
    events = eh.table(long_put_run, "expiry_events")
    assert len(events) == 1
    event = events.iloc[0]
    assert (event["session_date"], event["event_type"], event["shares_delivered"]) == (MAR, "exercised", -100)
    assert event["settlement_price"] == 410.80 and event["strike"] == 430.0
    assert pnl.loc[MAR, "shares"] == 0 and pnl.loc[MAR, "n_open_lots"] == 0
    hedges = eh.table(long_put_run, "hedges").set_index("session_date")
    # step 6 ran AFTER settlement: it saw 100 - 100 = 0 shares and no lot, not the expiring put's delta of -99.9
    assert hedges.loc[MAR, "delta_before_shares"] == 0.0 and hedges.loc[MAR, "shares_traded"] == 0
    flows = eh.table(long_put_run, "cash_flows")
    on_expiry = flows[flows["session_date"] == MAR]
    assert not on_expiry["kind"].isin(["hedge_trade", "hedge_commission", "hedge_slippage"]).any()
    assert on_expiry[on_expiry["kind"] == "settlement"]["amount_cents"].tolist() == [100 * 43_000]    # -(-100) x $430
    orders = eh.table(long_put_run, "orders")
    assert set(orders["intent"]) == {"open"}                                 # no share_liquidation order
    # and the shares stay at zero afterwards
    assert (pnl.loc[MAR:, "shares"] == 0).all()


def test_every_n_sessions_5_hedges_only_on_sessions_1_6_11(engine_store, tmp_path):
    """ADR-0005 test 4's schedule through a run: hedge rows only on the run's session indices 0, 5, 10, ..."""
    result = eh.run(engine_store, tmp_path, RollingShortStraddle(exit_dte=0), hedge_every_n=5)
    sessions = eh.table(result, "daily_pnl").sort_values("session_date")["session_date"].tolist()
    expected = set(sessions[::5])
    hedges = eh.table(result, "hedges")
    traded = hedges[hedges["shares_traded"] != 0]
    assert len(traded) >= 10 and set(traded["session_date"]) <= expected
    assert set(hedges["session_date"]) <= expected and set(hedges["trigger"]) == {"schedule"}
    # a session that is not on the schedule leaves the hedge shares alone (no early event or delivery on those days)
    pnl = eh.table(result, "daily_pnl").sort_values("session_date").reset_index(drop=True)
    events = set(eh.table(result, "expiry_events")["session_date"]) | set(eh.table(result, "expiry_events")["effective_date"])
    for i in range(1, len(pnl)):
        if pnl.loc[i, "session_date"] not in expected and pnl.loc[i, "session_date"] not in events:
            assert pnl.loc[i, "shares"] == pnl.loc[i - 1, "shares"], pnl.loc[i, "session_date"]
    # every session is hedged when n = 1
    daily = eh.run(engine_store, tmp_path, RollingShortStraddle(exit_dte=0))
    assert set(eh.table(daily, "hedges")["session_date"]) == set(sessions)


def test_band_hedging_through_a_run_trades_only_when_the_exposure_is_above_the_band(engine_store, tmp_path):
    """ADR-0005 §4: with band 1% a hedge happens when |net delta x S| exceeds 1% of NAV and the book is flat to
    half a share afterwards; on the other sessions the exposure stays inside the band."""
    result = eh.run(engine_store, tmp_path, RollingShortStraddle(exit_dte=0), hedge_mode="band",
                    hedge_band_pct_nav=Fraction(1, 100))
    hedges, pnl = eh.table(result, "hedges"), eh.table(result, "daily_pnl")
    assert set(hedges["trigger"]) == {"band"} and len(hedges) >= 20
    merged = pnl.merge(hedges[["session_date", "delta_before_shares"]], on="session_date", how="left")
    hedged = merged[merged["delta_before_shares"].notna()]
    assert (hedged["delta_before_shares"].abs() * hedged["spot"] / hedged["nav_mid"] > 0.0099).all()
    quiet = merged[merged["delta_before_shares"].isna() & (merged["n_open_lots"] > 0)]
    assert len(quiet) >= 3
    assert (quiet["delta_after_hedge_shares"].abs() * quiet["spot"] / quiet["nav_mid"] < 0.0101).all()
    assert (quiet["delta_after_hedge_shares"].abs() > 0).all()
    assert_hedge_rows_are_flat_to_half_a_share(result)


def test_hedge_never_leaves_the_shares_alone(engine_store, tmp_path):
    result = eh.run(engine_store, tmp_path, RollingShortStraddle(exit_dte=7), hedge_mode="never", stop_after=date(2023, 2, 8))
    assert len(eh.table(result, "hedges")) == 0
    assert (eh.table(result, "daily_pnl")["shares"] == 0).all()
