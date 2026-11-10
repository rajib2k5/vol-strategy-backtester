"""Marks (ADR-0004 tests 1-4, 6-8 and 11; ADR-0008 test 9; decision D4), through marks.mark_lots and in runs.

The hand-worked tests price one lot with marks.mark_lots against a DaySurface built from hand-made nodes (a flat
or skewed smile, no dividends), so the ADR's inputs are exact: S = F = K = 400, tau = 30/365, r = 0, surface IV
0.20. The runs use tests/engine_store.py's store: the session fixture `engine_store` (the reference strategy, and
its 2023-02-08 session without a snapshot), and a copy with these quotes and closes edited, holding from
2023-01-18 one long 395 put, one short 390 put, one short 375 call and one long 420 call, all expiring 2023-03-17:

    2023-01-25   the 395 put quoted 1.00 / 1.20
    2023-01-26   the 395 and 390 puts quoted 0 / 0.04
    2023-02-01   the 2023-03-10 weekly's 415-425 calls quoted at IV 0.25 (the calendar constraint then lifts the
                 surface above the held 420 call's own IV)
    2023-02-02   the 375 call quoted at twice its price, the close held at 02-01's (MARK_JUMP)
    2023-02-08   no snapshot (as in the fixture), the close 3% below 02-07's
    2023-02-14   the 395 put crossed 1.10 / 1.00, the close 3% below 02-13's
    2023-02-22   the 395 put not quoted, the close 3% below 02-21's
    2023-03-01   no quote at all for the 2023-03-17 expiry (listed: 03-10 and 03-24)
"""

import math
from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

import engine_helpers as eh
import engine_store as es
from volbt.data import flags as quality
from volbt.data.store import session_calendar, view
from volbt.engine import marks
from volbt.engine import surface as surf
from volbt.engine.book import Lot
from volbt.engine.surface import DaySurface
from volbt.pricing import black76, lattice, smile
from volbt.strategies.reference import RollingShortStraddle

D = date
CFG = eh.config()
DAY = D(2023, 2, 1)
EXPIRY = DAY + timedelta(days=30)
CALENDAR = es.sessions()


def flat(sigma):
    return lambda k: np.full_like(k, sigma)


def skew(k):
    return 0.20 - 0.25 * k


def day_surface(spot, forward, rate, sigma_at=flat(0.20), day=DAY, expiry=EXPIRY) -> DaySurface:
    """A one-expiry surface through 13 nodes of sigma_at(k), with no dividend paid (so none projected)."""
    tau = (expiry - day).days / 365
    nodes = np.linspace(-0.30, 0.30, 13)
    return DaySurface(day, day, spot, rate, {expiry: (forward, forward)},
                      [(tau, nodes, sigma_at(nodes) ** 2 * tau)], ([], []), CALENDAR)


def lot(right, strike, qty=1, lot_id=1, expiry=EXPIRY) -> Lot:
    return Lot(lot_id, 1, es.symbol(expiry, right, strike), expiry, strike, right, qty, D(2023, 1, 3), expiry)


def quote(bid, ask, *, iv=None, in_smile=False, is_otm=True, k=0.0, iv_flags=0) -> marks.Quote:
    bits = int(quality.mid_flags(quality.cents([bid]), quality.cents([ask]))[0])
    return marks.Quote(bid, ask, bits, 1000.0, k, is_otm, in_smile, iv, iv_flags)


def mark(held, quotes, surface, spot, rate, *, has_snapshot=True, previous=None, atm_change=0.0, spot_change=0.0,
         cfg=CFG):
    return marks.mark_lots(held, surface.session, spot, rate, {held[0].osi_symbol: quotes} if quotes else {}, surface,
                           cfg, has_snapshot, previous or {}, atm_change, spot_change)


# --- ADR-0004 tests 1 and 2: the quote's mid, and NAV_liq ------------------------------------------------------------

def test_a_valid_quote_is_marked_at_its_mid():
    surface = day_surface(400.0, 400.0, 0.0)
    for qty, liq in ((1, 100.0), (-1, -120.0)):        # NAV_liq: a long at the bid, a short at the ask
        row, = mark([lot("C", 420.0, qty)], quote(1.00, 1.20, iv=0.2, in_smile=True), surface, 400.0, 0.0)
        assert (row["mark_source"], row["mark_price"]) == ("QUOTE_MID", 1.10)
        assert row["value_mid_usd"] == pytest.approx(qty * 110.0, abs=1e-9)
        assert row["value_liq_usd"] == pytest.approx(liq, abs=1e-9)


def test_a_zero_bid_is_marked_at_half_the_ask_and_nav_liq_counts_a_long_at_0_and_a_short_at_its_ask():
    surface = day_surface(400.0, 400.0, 0.0)
    long_row, = mark([lot("P", 300.0, 1)], quote(0.0, 0.04), surface, 400.0, 0.0)
    short_row, = mark([lot("P", 300.0, -1)], quote(0.0, 0.04), surface, 400.0, 0.0)
    for row, value in ((long_row, 2.0), (short_row, -2.0)):
        assert (row["mark_source"], row["mark_price"]) == ("ZERO_BID_MID", 0.02)
        assert row["value_mid_usd"] == pytest.approx(value, abs=1e-9)
    assert long_row["value_liq_usd"] == 0.0
    assert short_row["value_liq_usd"] == pytest.approx(-4.0, abs=1e-9)


# --- ADR-0004 tests 3 and 4, ADR-0008 test 9: model marks -----------------------------------------------------------

def american(spot, strike, tau, rate, sigma, is_call):
    return float(lattice.crr(spot, strike, tau, rate, sigma, is_call, None, None, 500)["price"][0])


def test_a_crossed_quote_is_marked_on_the_lattice_at_the_surface_iv():
    # ADR-0004 test 3: crossed 1.10 / 1.00, surface IV 0.20, S = F = K = 400, 30 days, r = 0 -> 9.1486.
    row, = mark([lot("P", 400.0)], quote(1.10, 1.00), day_surface(400.0, 400.0, 0.0), 400.0, 0.0)
    assert row["mark_source"] == "SURFACE_MODEL"
    assert row["mark_iv"] == pytest.approx(0.20, abs=1e-12)
    assert row["mark_price"] == american(400.0, 400.0, 30 / 365, 0.0, 0.20, False)
    assert row["mark_price"] == pytest.approx(9.1486, abs=0.01)
    assert row["mark_price"] != pytest.approx(1.05, abs=0.5)                      # not the crossed mid


def test_a_missing_quote_moves_with_spot_and_is_never_the_previous_mark():
    # ADR-0004 test 4: the same put, missing the next day while S falls from 400 to 380, sigma unchanged. Rule 3
    # (a session with a snapshot) and rule 4 (none: the previous surface, re-priced at today's spot) both raise the
    # mark toward the put's value at 380; neither keeps the previous day's.
    first, = mark([lot("P", 400.0)], quote(1.10, 1.00), day_surface(400.0, 400.0, 0.0), 400.0, 0.0)
    next_day = DAY + timedelta(days=1)
    target = american(380.0, 400.0, 29 / 365, 0.0, 0.20, False)
    assert target == pytest.approx(float(black76.price(380.0, 400.0, 29 / 365, 0.0, 0.20, False)), abs=0.01)
    today = day_surface(380.0, 380.0, 0.0, day=next_day)
    missing, = mark([lot("P", 400.0)], None, today, 380.0, 0.0, previous={1: first["mark_price"]})
    stale = day_surface(400.0, 400.0, 0.0).stale_copy(next_day, 380.0, 0.0, ([], []))
    held_over, = mark([lot("P", 400.0)], None, stale, 380.0, 0.0, has_snapshot=False,
                      previous={1: first["mark_price"]})
    assert (missing["mark_source"], held_over["mark_source"]) == ("SURFACE_MODEL", "STALE_SURFACE")
    for row in (missing, held_over):
        assert row["mark_price"] > first["mark_price"] + 10
        assert row["mark_price"] == pytest.approx(target, abs=1e-9)
    assert held_over["mark_flags"] & surf.FORWARD_CARRY


def test_model_marks_are_american_not_black76():
    # ADR-0008 test 9: put, S = K = 450, r = 5%, sigma 0.15, 30 days, no dividend: 6.9574 on N = 500, not 6.8162.
    rows = [{"strike": 450.0, "tau": 30 / 365, "sigma": 0.15, "right": "P", "div_times": [], "div_amounts": []}]
    price = float(marks.model_prices(rows, 450.0, 0.05, 500)[0])
    assert price == pytest.approx(6.9574, abs=5e-5)
    forward = 450.0 * math.exp(0.05 * 30 / 365)
    assert float(black76.price(forward, 450.0, 30 / 365, 0.05, 0.15, False)) == pytest.approx(6.8162, abs=5e-5)
    row, = mark([lot("P", 450.0)], None, day_surface(450.0, forward, 0.05, flat(0.15)), 450.0, 0.05)
    assert row["mark_source"] == "SURFACE_MODEL" and row["mark_price"] == pytest.approx(6.9574, abs=5e-5)


# --- ADR-0004 test 8 and the M2 amendment: greeks from our Black-76, at which IV --------------------------------------

def test_greeks_are_black76_at_the_quotes_own_iv():
    # ADR-0004 test 8: S = F = K = 400, sigma 0.20 (the quote's own, in the smile), 30 days, r = 0: delta 0.5114,
    # whatever a vendor said (the engine's Quote has no vendor greek to read). The surface here is at 0.30, so a
    # delta at the surface IV would not pass.
    row, = mark([lot("C", 400.0)], quote(9.10, 9.20, iv=0.20, in_smile=True),
                day_surface(400.0, 400.0, 0.0, flat(0.30)), 400.0, 0.0)
    assert row["mark_iv"] == 0.20
    assert row["delta_shares"] / 100 == pytest.approx(0.5114, abs=5e-5)


def test_an_itm_quote_takes_the_surface_iv_at_its_strike_and_an_in_smile_quote_its_own():
    surface = day_surface(400.0, 400.0, 0.0, skew)
    k_itm, k_otm = math.log(380 / 400), math.log(420 / 400)
    itm, = mark([lot("C", 380.0)], quote(21.00, 21.10, iv=0.35, is_otm=False, k=k_itm), surface, 400.0, 0.0)
    otm, = mark([lot("C", 420.0)], quote(2.00, 2.02, iv=0.25, in_smile=True, k=k_otm), surface, 400.0, 0.0)
    surface_itm = float(surface.iv(EXPIRY, k_itm)[0][0])
    assert itm["mark_source"] == "QUOTE_MID" and itm["mark_price"] == pytest.approx(21.05, abs=1e-12)
    assert itm["mark_iv"] == surface_itm != pytest.approx(0.35) and surface_itm != float(surface.iv(EXPIRY, 0.0)[0][0])
    assert itm["mark_flags"] & surf.GREEKS_OTM_IV
    assert otm["mark_iv"] == 0.25 and not otm["mark_flags"] & surf.GREEKS_OTM_IV
    for row, sigma, strike in ((itm, surface_itm, 380.0), (otm, 0.25, 420.0)):
        expected = black76.greeks_usd(1, 400.0, 400.0, strike, 30 / 365, 0.0, sigma, True)
        for name in ("delta_shares", "gamma_1pct_usd", "vega_1vol_usd", "theta_1d_usd"):
            assert row[name] == pytest.approx(float(expected[name]), rel=1e-12)


def test_surface_mode_model_marks_every_lot_even_when_quoted():
    # Decision D4: in surface mode a valid quote is not used; the lot is SURFACE_MODEL at the surface IV.
    surface_cfg = replace(CFG, execution_mode="surface")
    row, = mark([lot("P", 400.0)], quote(9.00, 9.02, iv=0.30, in_smile=True), day_surface(400.0, 400.0, 0.0), 400.0,
                0.0, cfg=surface_cfg)
    assert row["mark_source"] == "SURFACE_MODEL"
    assert row["mark_price"] == american(400.0, 400.0, 30 / 365, 0.0, 0.20, False)


# --- MARK_JUMP and DEGRADED ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("bid, ask, spot_change, atm_change, flagged", [
    (1.59, 1.61, 0.005, 0.01, True),          # +60% while spot and ATM vol barely moved
    (0.39, 0.41, -0.005, -0.01, True),        # -60%
    (1.49, 1.51, 0.0, 0.0, False),            # exactly +50% is not "more than 50%"
    (1.59, 1.61, 0.011, 0.0, False),          # spot moved 1.1%
    (1.59, 1.61, 0.0, -0.021, False),         # ATM vol moved 2.1 points
])
def test_mark_jump(bid, ask, spot_change, atm_change, flagged):
    row, = mark([lot("C", 420.0)], quote(bid, ask, iv=0.2, in_smile=True), day_surface(400.0, 400.0, 0.0), 400.0, 0.0,
                previous={1: 1.00}, atm_change=atm_change, spot_change=spot_change)
    assert bool(row["mark_flags"] & surf.MARK_JUMP) is flagged
    assert row["mark_source"] == "QUOTE_MID" and row["mark_price"] == pytest.approx((bid + ask) / 2, abs=1e-12)


def nav_row(value, source, in_nav=True):
    return {"value_mid_usd": value, "mark_source": source, "in_nav": in_nav}


def test_degraded_above_20_percent_of_gross_option_value():
    # ADR-0004 test 6: gross $100k, $25k of it by rule 3: 25% > 20% -> DEGRADED. The model-marked lots here are a
    # long and a short whose net is 0: the share is of GROSS value.
    rows = [nav_row(75_000.0, "QUOTE_MID"), nav_row(12_500.0, "SURFACE_MODEL"), nav_row(-12_500.0, "STALE_SURFACE"),
            nav_row(50_000.0, "INTRINSIC", in_nav=False)]
    gross, model, share = marks.model_share(rows)
    assert (gross, model, share) == (100_000.0, 25_000.0, 0.25)
    assert marks.mark_quality(gross, model, CFG) == "DEGRADED"
    # Exactly 20% is OK; a cent above is DEGRADED.
    exact = [nav_row(80_000.0, "QUOTE_MID"), nav_row(-20_000.0, "SURFACE_MODEL")]
    assert marks.mark_quality(*marks.model_share(exact)[:2], CFG) == "OK"
    above = [nav_row(79_999.99, "ZERO_BID_MID"), nav_row(20_000.01, "SURFACE_MODEL")]
    assert marks.mark_quality(*marks.model_share(above)[:2], CFG) == "DEGRADED"
    assert marks.model_share([]) == (0.0, 0.0, 0.0) and marks.mark_quality(0.0, 0.0, CFG) == "OK"


# --- in runs -------------------------------------------------------------------------------------------------------

def surface_on(store, day: date) -> DaySurface:
    """The surface of a snapshot day as step 1 builds it, through that day's view."""
    day_view = view(day, "validation", store)
    rates = day_view.rates()
    rate = float(rates.loc[rates["date"] < pd.Timestamp(day), "r_cc"].iloc[-1])
    paid_rows = day_view.dividends()
    paid = ([d.date() for d in pd.to_datetime(paid_rows["ex_date"])], [float(a) for a in paid_rows["amount"]])
    return DaySurface.from_view(day_view, day, "optionsdx", float(day_view.spy_bars()["close"].iloc[-1]), rate, paid,
                                session_calendar(store))


@pytest.fixture(scope="module")
def reference(engine_store, tmp_path_factory):
    return eh.run(engine_store, tmp_path_factory.mktemp("marks_reference"), RollingShortStraddle(exit_dte=0),
                  sample_end=D(2023, 3, 10))


def test_a_missing_snapshot_marks_every_lot_stale_from_the_previous_smile(engine_store, reference):
    # ADR-0004 test 7 on the fixture: no snapshot on 2023-02-08, so every lot is STALE_SURFACE, at the 02-07
    # surface's IV at the lot's log-moneyness, re-priced at the 02-08 close; the day is DEGRADED.
    feb07, feb08 = D(2023, 2, 7), es.MISSING_SNAPSHOT
    marks_ = eh.table(reference, "position_marks")
    pnl = eh.table(reference, "daily_pnl").set_index("session_date")
    day = marks_[marks_["session_date"] == feb08]
    open_lots = eh.table(reference, "lots")
    assert len(day) == pnl.loc[feb08, "n_open_lots"] == 2 and not pnl.loc[feb08, "has_snapshot"]
    assert set(day["mark_source"]) == {"STALE_SURFACE"}
    previous = surface_on(engine_store, feb07)
    before = marks_[marks_["session_date"] == feb07].set_index("lot_id")["mark_price"]
    for row in day.itertuples():
        held = open_lots.set_index("lot_id").loc[row.lot_id]
        assert row.spot == es.spot_path()[feb08] == pnl.loc[feb08, "spot"]
        assert row.mark_iv == float(previous.iv(held.expiry, row.log_moneyness)[0][0])
        assert row.mark_price == american(row.spot, held.strike, row.tau_years, pnl.loc[feb08, "rate"], row.mark_iv,
                                          held.option_right == "C")
        assert row.mark_flags & surf.FORWARD_CARRY
        assert row.mark_price != before[row.lot_id]
    assert pnl.loc[feb08, "share_nav_model_marked"] == 1.0 and pnl.loc[feb08, "mark_quality"] == "DEGRADED"
    assert pnl.loc[feb07, "mark_quality"] == "OK"


HELD = {"long_395_put": ("P", 395.0, 1), "short_390_put": ("P", 390.0, -1), "short_375_call": ("C", 375.0, -1),
        "long_420_call": ("C", 420.0, 1)}
MAR17 = D(2023, 3, 17)
JUMP_DAY = D(2023, 2, 2)


def held_symbol(name):
    right, strike, _ = HELD[name]
    return es.symbol(MAR17, right, strike)


@pytest.fixture(scope="module")
def edited(tmp_path_factory):
    path = es.spot_path()
    moves = {JUMP_DAY: path[D(2023, 2, 1)]}             # the 02-02 close held at 02-01's; three days 3% down
    moves.update({day: round(path[before] * 0.97, 2) for day, before in (
        (es.MISSING_SNAPSHOT, D(2023, 2, 7)), (D(2023, 2, 14), D(2023, 2, 13)), (D(2023, 2, 22), D(2023, 2, 21)))})
    spots = es.spot_path(moves)
    jump = next(row for row in es.quotes_on(JUMP_DAY, spots[JUMP_DAY])
                if row["osi_symbol"] == held_symbol("short_375_call"))
    edits = {(D(2023, 1, 25), held_symbol("long_395_put")): {"bid": 1.00, "ask": 1.20},
             (D(2023, 1, 26), held_symbol("long_395_put")): {"bid": 0.0, "ask": 0.04},
             (D(2023, 1, 26), held_symbol("short_390_put")): {"bid": 0.0, "ask": 0.04},
             (JUMP_DAY, held_symbol("short_375_call")): {"bid": 2 * jump["bid"], "ask": 2 * jump["ask"]},
             (D(2023, 2, 14), held_symbol("long_395_put")): {"bid": 1.10, "ask": 1.00},
             (D(2023, 2, 22), held_symbol("long_395_put")): {"drop": True}}
    march_1 = D(2023, 3, 1)
    edits.update({(march_1, row["osi_symbol"]): {"drop": True} for row in es.quotes_on(march_1, spots[march_1])
                  if row["expiry"] == MAR17})
    # On 02-01 the 03-10 weekly's 415-425 calls at IV 0.25: their total variance is above the 03-17 smile's at the
    # 420 call's k, so the calendar constraint raises the surface there above that call's own IV.
    feb_1, weekly = D(2023, 2, 1), D(2023, 3, 10)
    tau, rate = (weekly - feb_1).days / 365, es.rate_before(feb_1)
    forward = es.carry_forward(feb_1, weekly, spots[feb_1], rate)
    for strike in (415.0, 420.0, 425.0):
        mid_c = int(round(float(black76.price(forward, strike, tau, rate, 0.25, True)) * 100))
        edits[(feb_1, es.symbol(weekly, "C", strike))] = {"bid": (mid_c - 1) / 100, "ask": (mid_c + 1) / 100}
    store = es.built_store(tmp_path_factory.mktemp("marks_store"), edits=edits, spot_moves=moves)
    legs = [(held_symbol(name), qty) for name, (_, _, qty) in HELD.items()]
    strategy = eh.Scripted({D(2023, 1, 17): eh.open_legs(legs, 1, "custom")})
    result = eh.run(store, tmp_path_factory.mktemp("marks_runs"), strategy, sample_end=D(2023, 3, 10))
    return store, result


def marks_of(result, name):
    lots = eh.table(result, "lots").set_index("osi_symbol")["lot_id"]
    frame = eh.table(result, "position_marks")
    return frame[frame["lot_id"] == lots[held_symbol(name)]].set_index("session_date")


def test_quote_mid_and_zero_bid_marks_in_a_run(edited):
    _, result = edited
    long_put, short_put = marks_of(result, "long_395_put"), marks_of(result, "short_390_put")
    mid = long_put.loc[D(2023, 1, 25)]
    assert (mid.mark_source, mid.mark_price, mid.bid, mid.ask) == ("QUOTE_MID", 1.10, 1.00, 1.20)
    assert mid.value_liq_usd == pytest.approx(100.0, abs=1e-9)
    long_zero, short_zero = long_put.loc[D(2023, 1, 26)], short_put.loc[D(2023, 1, 26)]
    for row in (long_zero, short_zero):
        assert (row.mark_source, row.mark_price) == ("ZERO_BID_MID", 0.02)
    assert long_zero.value_liq_usd == 0.0 and short_zero.value_liq_usd == pytest.approx(-4.0, abs=1e-9)
    pnl = eh.table(result, "daily_pnl").set_index("session_date").loc[D(2023, 1, 26)]
    frame = eh.table(result, "position_marks")
    day = frame[frame["session_date"] == D(2023, 1, 26)]
    assert pnl.nav_liq == pytest.approx(pnl.cash_cents / 100 + pnl.shares * pnl.spot + day["value_liq_usd"].sum(),
                                        abs=1e-6)


def test_rules_3_and_4_move_with_spot_and_never_carry_the_last_mid(edited):
    # A crossed day (02-14), a missing quote (02-22) and a missing snapshot (02-08), each with the close 3% lower:
    # the long put's mark rises with spot and is never the previous day's mark. On the two snapshot days it is the
    # CRR price at that day's surface IV, with the 03-17 dividend the surface projects.
    store, result = edited
    put = marks_of(result, "long_395_put")
    rates = eh.table(result, "daily_pnl").set_index("session_date")["rate"]
    days = sorted(put.index)
    for day, source in ((D(2023, 2, 14), "SURFACE_MODEL"), (D(2023, 2, 22), "SURFACE_MODEL"),
                        (es.MISSING_SNAPSHOT, "STALE_SURFACE")):
        row, before = put.loc[day], put.loc[days[days.index(day) - 1]]
        assert row.mark_source == source
        assert row.spot == pytest.approx(before.spot * 0.97, abs=0.006)
        assert row.mark_price > before.mark_price + 0.5
        if source == "SURFACE_MODEL":
            surface = surface_on(store, day)
            times, amounts = surface.schedule(MAR17)
            assert len(times) == 1 and row.mark_iv == float(surface.iv(MAR17, row.log_moneyness)[0][0])
            price = lattice.crr(row.spot, 395.0, row.tau_years, rates[day], row.mark_iv, False, [times], [amounts], 500)
            assert row.mark_price == float(price["price"][0])
    assert put.loc[D(2023, 2, 14), "mark_price"] != pytest.approx(1.05, abs=0.5)        # not the crossed mid


def test_cross_expiry_when_the_own_expiry_is_absent(edited):
    # ADR-0004 test 11: on 2023-03-01 the 03-17 expiry has no quote; it lies between the listed 03-10 and 03-24, so
    # every lot is marked by w linear in tau between them (SURFACE_CROSS_EXPIRY), on the carry forward, without
    # raising and without a stale mark.
    store, result = edited
    march_1 = D(2023, 3, 1)
    surface = surface_on(store, march_1)
    for name in HELD:
        rows = marks_of(result, name)
        row = rows.loc[march_1]
        assert row.mark_source == "SURFACE_MODEL"
        assert row.mark_flags & smile.SURFACE_CROSS_EXPIRY and row.mark_flags & surf.FORWARD_CARRY
        assert row.mark_iv == float(surface.iv(MAR17, row.log_moneyness)[0][0])
        assert row.mark_price != rows.loc[D(2023, 2, 28), "mark_price"]
    assert rows.loc[D(2023, 2, 28), "mark_source"] == "QUOTE_MID"


def test_greeks_use_the_surface_iv_for_an_itm_quote_and_the_own_iv_in_the_smile_in_a_run(edited):
    store, result = edited
    day = D(2023, 2, 1)
    ivs = view(day, "validation", store).quote_ivs(day).set_index("osi_symbol")
    surface = surface_on(store, day)
    itm = marks_of(result, "short_375_call").loc[day]
    assert itm.mark_source == "QUOTE_MID" and not ivs.loc[held_symbol("short_375_call"), "in_smile"]
    assert itm.mark_flags & surf.GREEKS_OTM_IV
    assert itm.mark_iv == float(surface.iv(MAR17, ivs.loc[held_symbol("short_375_call"), "log_moneyness"])[0][0])
    for name in ("long_395_put", "long_420_call"):
        row = marks_of(result, name).loc[day]
        assert ivs.loc[held_symbol(name), "in_smile"] and row.mark_source == "QUOTE_MID"
        assert row.mark_iv == ivs.loc[held_symbol(name), "iv"] and not row.mark_flags & surf.GREEKS_OTM_IV
    # At the 420 call the calendar constraint moved the surface off the node: its own IV is not the surface's.
    k_420 = ivs.loc[held_symbol("long_420_call"), "log_moneyness"]
    sigma, bits = surface.iv(MAR17, k_420)
    assert bits[0] & smile.SURFACE_CALENDAR_ADJUSTED
    assert float(sigma[0]) > ivs.loc[held_symbol("long_420_call"), "iv"] + 0.02


def test_every_greek_is_black76_at_the_mark_iv_and_no_vendor_column_is_read(edited):
    store, result = edited
    served = view(D(2023, 2, 1), "validation", store).quotes(D(2023, 2, 1)).columns
    assert not [c for c in served if "delta" in c or "gamma" in c or "vega" in c or "theta" in c or c.endswith("_iv")]
    frame = eh.table(result, "position_marks")
    rates = eh.table(result, "daily_pnl").set_index("session_date")["rate"]
    lots = eh.table(result, "lots").set_index("lot_id")
    rows = frame[frame["mark_source"] != "INTRINSIC"]
    assert len(rows) == 4 * 37 and rows["mark_iv"].notna().all()          # 4 lots, 2023-01-18 to 03-10
    for row in rows.itertuples():
        held = lots.loc[row.lot_id]
        expected = black76.greeks_usd(row.qty, row.spot, row.forward, held.strike, row.tau_years,
                                      rates[row.session_date], row.mark_iv, held.option_right == "C")
        assert row.delta_shares == pytest.approx(float(expected["delta_shares"]), rel=1e-12, abs=1e-12)
        assert row.vega_1vol_usd == pytest.approx(float(expected["vega_1vol_usd"]), rel=1e-12, abs=1e-12)


def test_mark_jump_in_a_run(edited):
    # The ITM 375 call's quote doubles on 02-02 while the close is 02-01's and the smile (OTM quotes) is unchanged:
    # flagged MARK_JUMP, and still the mark.
    _, result = edited
    call = marks_of(result, "short_375_call")
    row, before = call.loc[JUMP_DAY], call.loc[D(2023, 2, 1)]
    assert row.spot == before.spot and row.mark_price / before.mark_price > 1.9
    assert row.mark_flags & surf.MARK_JUMP and row.mark_source == "QUOTE_MID"
    assert row.mark_price == pytest.approx((row.bid + row.ask) / 2, abs=1e-12)
    assert not before.mark_flags & surf.MARK_JUMP
    assert not marks_of(result, "long_420_call").loc[JUMP_DAY, "mark_flags"] & surf.MARK_JUMP


def test_surface_mode_marks_every_quoted_lot_from_the_surface(engine_store, tmp_path):
    # Decision D4: execution_mode "surface" model-marks every lot, quoted or not (STALE_SURFACE on 02-08).
    result = eh.run(engine_store, tmp_path, RollingShortStraddle(exit_dte=0), execution_mode="surface",
                    sample_end=D(2023, 3, 10))
    frame = eh.table(result, "position_marks")
    rows = frame[frame["mark_source"] != "INTRINSIC"]
    assert len(rows) > 40 and rows["bid"].notna().sum() > 40                  # most of them have a valid quote
    on_snapshot = rows["session_date"] != es.MISSING_SNAPSHOT
    assert set(rows.loc[on_snapshot, "mark_source"]) == {"SURFACE_MODEL"}
    assert set(rows.loc[~on_snapshot, "mark_source"]) == {"STALE_SURFACE"}
    pnl = eh.table(result, "daily_pnl")
    with_lots = pnl[pnl["n_open_lots"] > 0]
    assert (with_lots["share_nav_model_marked"] == 1.0).all() and set(with_lots["mark_quality"]) == {"DEGRADED"}
