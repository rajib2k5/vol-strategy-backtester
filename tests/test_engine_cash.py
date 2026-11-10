"""Cash in integer cents: interest, dividends, the borrow fee, the return columns (ADR-0007 tests 1 and 7, ADR-0005
§1 and §6, ADR-0002 §4's rounding rule).

Hand-worked numbers first (the ADR's $428.80, $46.99, 0.4287%), then runs of the engine on tests/engine_store.py's
made-up store, where the ledger's own prior-close cash, rate and dates give the hand value of every interest and
borrow-fee flow, and `cash_cents = initial + sum(cash_flows)` is checked on every session as an exact integer
identity.
"""

from __future__ import annotations

import math
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import pytest

import engine_helpers as eh
import engine_store as es
from volbt.data.reference import r_cc_from_dgs3mo
from volbt.engine import cash, loop
from volbt.strategies.base import LegIntent, OrderIntent
from volbt.strategies.reference import RollingShortStraddle

SPREAD = Decimal("0.0050")
APR = date(2023, 4, 21)


# --- hand-worked unit tests ---------------------------------------------------------------------------------

def test_dgs3mo_5_25_converts_to_5_2159_percent_continuous():
    """ADR-0007 test 1, first line."""
    assert round(float(r_cc_from_dgs3mo(5.25)) * 100, 4) == 5.2159


def test_a_million_from_friday_to_monday_earns_428_80():
    """ADR-0007 test 1: $1,000,000 at r_cc 5.2159%, d = 3 calendar days, earns $428.80 (cents: 42880)."""
    rate = float(r_cc_from_dgs3mo(5.25))
    assert cash.interest_cents(100_000_000, rate, 3, SPREAD) == 42_880
    assert cash.interest_cents(100_000_000, rate, 1, SPREAD) == 14_291       # one day: 142.91 (a third of 428.80)
    assert cash.interest_cents(100_000_000, rate, 0, SPREAD) == 0
    assert cash.interest_cents(0, rate, 3, SPREAD) == 0


def test_negative_cash_pays_the_rate_plus_half_a_point():
    """ADR-0007 test 1: -$100,000 for three days pays 100,000 (e^(0.057159 x 3/365) - 1) = $46.99, a negative flow."""
    rate = float(r_cc_from_dgs3mo(5.25))
    assert cash.interest_cents(-10_000_000, rate, 3, SPREAD) == -4_699
    # without the 0.50% spread it would be 42.88 x 0.1 = $42.88: the spread is what makes it 46.99
    assert cash.interest_cents(-10_000_000, rate, 3, Decimal("0")) == -4_288
    # a positive balance never pays the spread
    assert cash.interest_cents(10_000_000, rate, 3, SPREAD) == 4_288


def test_borrow_fee_on_a_thousand_short_shares_is_a_negative_flow_in_exact_cents():
    """ADR-0005 §1: 1,000 shares short at $400.00 for 3 days at 0.25%: 400,000 x 0.0025 x 3/365 = $8.22."""
    fee = Decimal("0.0025")
    assert cash.borrow_fee_cents(-1000, 40_000, 3, fee) == -822
    assert cash.borrow_fee_cents(-1000, 40_000, 1, fee) == -274         # 2.7397 -> 2.74
    assert cash.borrow_fee_cents(1000, 40_000, 3, fee) == 0             # long shares pay no borrow fee
    assert cash.borrow_fee_cents(0, 40_000, 3, fee) == 0
    assert cash.borrow_fee_cents(-1000, 40_000, 0, fee) == 0


def test_dividend_rounding_is_half_up_on_the_exact_decimal():
    """ADR-0002 §4's rule for money, on the dividend: shares x amount in Decimal, ROUND_HALF_UP."""
    assert cash.dividend_cents(-100, 1.505) == -15_050                      # -150.50 exactly
    assert cash.dividend_cents(100, 1.505) == 15_050
    # the half-cent cases: 1 x 1.505 = 150.5 cents, which banker's rounding (Python's round) takes to 150
    assert cash.dividend_cents(1, 1.505) == 151
    assert cash.dividend_cents(-1, 1.505) == -151                           # half away from zero
    assert cash.dividend_cents(5, 1.505) == 753                             # 752.5
    assert cash.dividend_cents(-5, 1.505) == -753
    assert cash.dividend_cents(0, 1.505) == 0
    assert round(150.5) == 150 and round(752.5) == 752                      # the premise: round() would be a cent short


def test_cents_rounds_half_up_away_from_zero():
    assert cash.cents(Decimal("6.175")) == 618 and cash.cents(Decimal("-6.175")) == -618
    assert cash.cents(Decimal("0.005")) == 1 and cash.cents(Decimal("0.004")) == 0
    assert cash.cents(Decimal("2.5")) == 250


# --- the loop's own steps, called on a hand-made state -----------------------------------------------------------

def bare_run(store, **overrides) -> loop.Run:
    """A Run object with no sessions played: the loop's steps can be called on state a test sets by hand."""
    calendar = [date(2023, 1, 3), date(2023, 1, 4), date(2023, 1, 5), date(2023, 1, 6), date(2023, 1, 9)]
    return loop.Run(eh.config(**overrides), eh.Scripted({}), store, calendar, calendar)


def test_a_nav_of_1_004_287_after_1_000_000_is_a_daily_return_of_0_4287_percent(engine_store):
    """ADR-0007 test 7, through the loop's snapshot step (step 7): the daily_pnl row carries NAV_mid and the
    return, and the risk-free return of the previous session's rate over the three calendar days."""
    run = bare_run(engine_store)
    friday, monday = date(2023, 1, 6), date(2023, 1, 9)
    run.prev = {"t": friday, "nav_mid": 1_000_000.0, "rate": 0.05}
    run.book.cash_cents = 100_428_700
    run.today = {"t": monday, "has_snapshot": True, "spot": 400.0, "marks": [], "flows": {}, "rate": 0.05}
    run.step_07_snapshot(monday)
    row = run.ledger.rows["daily_pnl"][-1]
    assert row["session_date"] == monday and row["cash_cents"] == 100_428_700
    assert row["nav_mid"] == 1_004_287.0
    assert row["daily_return"] == pytest.approx(0.004287, abs=1e-12)
    assert row["rf_return"] == pytest.approx(math.expm1(0.05 * 3 / 365), abs=1e-15)      # e^(r d / 365) - 1, d = 3


def test_the_first_session_has_no_return(engine_store):
    run = bare_run(engine_store)
    day = date(2023, 1, 3)
    run.today = {"t": day, "has_snapshot": True, "spot": 400.0, "marks": [], "flows": {}, "rate": 0.05}
    run.step_07_snapshot(day)
    row = run.ledger.rows["daily_pnl"][-1]
    assert row["nav_mid"] == 1_000_000.0 and row["daily_return"] is None and row["rf_return"] is None


# --- runs ---------------------------------------------------------------------------------------------------------

def hand_interest(cash_cents: int, rate: float, days: int, spread: Decimal) -> int:
    """ADR-0007 §2 worked in floats and rounded half up: cash (e^(r d/365) - 1), r + 0.50% when cash is negative."""
    used = rate + (float(spread) if cash_cents < 0 else 0.0)
    amount = cash_cents * math.expm1(used * days / 365)
    return int(Decimal(repr(amount)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def hand_borrow(shares: int, spot: float, days: int, fee: float = 0.0025) -> int:
    if shares >= 0:
        return 0
    amount = -shares * round(spot * 100) * math.expm1(fee * days / 365)
    return -int(Decimal(repr(amount)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def flows_by_day(flows, kind: str) -> dict:
    rows = flows[flows["kind"] == kind]
    return {day: int(total) for day, total in rows.groupby("session_date")["amount_cents"].sum().items()}


@pytest.fixture(scope="module")
def reference_runs(engine_store, tmp_path_factory):
    """The reference strategy over the whole sample: held to expiry, and closed 7 days before it."""
    root = tmp_path_factory.mktemp("cash_runs")
    return {exit_dte: eh.run(engine_store, root, RollingShortStraddle(exit_dte=exit_dte)) for exit_dte in (0, 7)}


@pytest.fixture(scope="module")
def negative_cash_run(engine_store, tmp_path_factory):
    """Four 100-lot long deep-ITM calls, unhedged: they cost about $1.27M, so cash goes negative."""
    symbols = [es.symbol(APR, "C", strike) for strike in (365.0, 370.0, 375.0, 380.0)]

    def buy(view, book, ctx):
        return [OrderIntent(None, "open", "custom", (LegIntent(s, 1),), 100) for s in symbols]

    return eh.run(engine_store, tmp_path_factory.mktemp("negative_cash"), eh.Scripted({date(2023, 1, 10): buy}),
                  hedge_mode="never", stop_after=date(2023, 3, 10))


@pytest.fixture(scope="module")
def short_shares_run(engine_store, tmp_path_factory):
    """A hedged short put: the hedge sells shares, so the book is short stock for weeks (the borrow fee)."""
    def action(view, book, ctx):
        return [OrderIntent(None, "open", "custom", (LegIntent(es.symbol(APR, "P", 380.0), -1),), 50)]

    return eh.run(engine_store, tmp_path_factory.mktemp("short_shares"), eh.Scripted({date(2023, 1, 10): action}),
                  stop_after=date(2023, 3, 3))


@pytest.mark.parametrize("which", ["held_to_expiry", "closed_at_7_dte", "negative_cash"])
def test_cash_equals_initial_plus_the_sum_of_cash_flows_on_every_session(which, reference_runs, negative_cash_run):
    """Decision D7, exactly (integers, no tolerance), on a run with fills, hedges, settlement, early assignment,
    a dividend and interest every session."""
    result = {"held_to_expiry": reference_runs[0], "closed_at_7_dte": reference_runs[7],
              "negative_cash": negative_cash_run}[which]
    pnl, flows = eh.table(result, "daily_pnl"), eh.table(result, "cash_flows")
    initial = eh.config().initial_nav_cents
    assert str(pnl["cash_cents"].dtype) == "int64" and str(flows["amount_cents"].dtype) == "int64"
    assert len(pnl) > 25
    per_day = flows.groupby("session_date")["amount_cents"].sum().to_dict()
    running = initial
    for _, row in pnl.sort_values("session_date").iterrows():
        running += int(per_day.get(row["session_date"], 0))
        assert int(row["cash_cents"]) == running, row["session_date"]
        assert row["cash"] == int(row["cash_cents"]) / 100
    # flow ids are 1, 2, 3, ... in creation order and no zero flow is booked
    assert flows["flow_id"].tolist() == list(range(1, len(flows) + 1))
    assert (flows["amount_cents"] != 0).all()


def test_the_reference_runs_exercise_every_kind_of_flow(reference_runs):
    """A guard on the test above: the identity was checked on runs that really booked each kind."""
    kinds = set()
    for result in reference_runs.values():
        kinds |= set(eh.table(result, "cash_flows")["kind"])
    assert {"interest", "option_premium", "option_fee", "hedge_trade", "hedge_commission", "hedge_slippage",
            "settlement", "early_settlement", "dividend", "borrow_fee"} <= kinds


def check_interest(result, spread: Decimal = SPREAD) -> set:
    """Every session's interest flow is the hand value from the PRIOR session's closing cash and rate and the
    calendar days since it. Returns the set of day gaps checked."""
    pnl = eh.table(result, "daily_pnl").sort_values("session_date").reset_index(drop=True)
    booked = flows_by_day(eh.table(result, "cash_flows"), "interest")
    assert pnl.loc[0, "session_date"] not in booked                       # nothing before the first close
    gaps = set()
    for i in range(1, len(pnl)):
        prior, today = pnl.iloc[i - 1], pnl.iloc[i]
        days = (today["session_date"] - prior["session_date"]).days
        gaps.add(days)
        expected = hand_interest(int(prior["cash_cents"]), float(prior["rate"]), days, spread)
        assert booked.get(today["session_date"], 0) == expected, (today["session_date"], days)
        assert today["pnl_interest"] == expected / 100
    return gaps


def test_interest_uses_the_prior_close_balance_the_previous_rate_and_calendar_days(reference_runs):
    """ADR-0007 §2 and decision D8, through the loop. Friday to Monday is 3 days, the long weekend of 2023-01-16 is
    4; fill days, settlement days and the ex-date change the cash during the day, but the interest is on the
    balance the previous close left."""
    for result in reference_runs.values():
        gaps = check_interest(result)
        assert {1, 3, 4} <= gaps


def test_interest_on_a_negative_balance_adds_the_half_point(negative_cash_run):
    pnl = eh.table(negative_cash_run, "daily_pnl")
    assert (pnl["cash_cents"] < -10_000_000).any()                       # cash really is negative, by over $100,000
    check_interest(negative_cash_run)
    # and the flows on those days are costs
    flows = flows_by_day(eh.table(negative_cash_run, "cash_flows"), "interest")
    negative_days = pnl[pnl["cash_cents"].shift(1) < 0]["session_date"]
    assert len(negative_days) >= 20 and all(flows[d] < 0 for d in negative_days)


def test_the_borrow_fee_on_short_hedge_shares_through_a_run(short_shares_run):
    """ADR-0005 §1 and decision D9: 0.25% a year on the short shares' prior-close market value, a negative flow
    on each session that follows a close with short shares, nothing after a flat or long close."""
    pnl = eh.table(short_shares_run, "daily_pnl").sort_values("session_date").reset_index(drop=True)
    booked = flows_by_day(eh.table(short_shares_run, "cash_flows"), "borrow_fee")
    assert (pnl["shares"] < -100).sum() >= 15 and (pnl["shares"] == 0).sum() >= 3
    for i in range(1, len(pnl)):
        prior, today = pnl.iloc[i - 1], pnl.iloc[i]
        days = (today["session_date"] - prior["session_date"]).days
        expected = hand_borrow(int(prior["shares"]), float(prior["spot"]), days)
        assert booked.get(today["session_date"], 0) == expected, today["session_date"]
        assert today["pnl_borrow"] == expected / 100
        if prior["shares"] < 0:
            assert expected < 0
    # three days over a weekend cost three times one day
    monday = pnl[pnl["session_date"] == date(2023, 1, 23)].index[0]
    assert (pnl.loc[monday, "session_date"] - pnl.loc[monday - 1, "session_date"]).days == 3
    assert pnl.loc[monday - 1, "shares"] < 0 and booked[date(2023, 1, 23)] < 0


def test_a_dividend_is_booked_on_the_ex_date_at_the_amount_paid_on_the_shares_held(engine_store, tmp_path):
    """ADR-0005 §6 through a run: a hedged long 430 put holds +100 hedge shares at the 2023-03-16 close; the
    2023-03-17 ex-date pays 100 x the BOOKED 1.616 (not the projected 1.818) = +$161.60, once, at step 2."""
    put = es.symbol(date(2023, 3, 17), "P", 430.0)

    def action(view, book, ctx):
        return [OrderIntent(None, "open", "custom", (LegIntent(put, 1),), 1)]

    result = eh.run(engine_store, tmp_path, eh.Scripted({date(2023, 3, 9): action}), stop_after=date(2023, 3, 20))
    pnl, flows = eh.table(result, "daily_pnl"), eh.table(result, "cash_flows")
    assert int(pnl[pnl["session_date"] == date(2023, 3, 16)].iloc[0]["shares"]) == 100
    dividends = flows[flows["kind"] == "dividend"]
    assert dividends["session_date"].tolist() == [date(2023, 3, 17)]
    assert dividends["amount_cents"].tolist() == [16_160]
    assert pnl[pnl["session_date"] == date(2023, 3, 17)].iloc[0]["pnl_dividends"] == 161.60
