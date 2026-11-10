"""The hedged position P&L (milestone 4, plan sections 3 and 10, task 2; adversarial claim 8 of section 7).

    pnl_t = fills + open lots + settled lots + H_t,   H_t = sum over u <= t of -Delta_{u-1} (S_u + D_u - S_{u-1})

The identity the tests check, on tests/engine_store.py's made-up store with the daily hedge at the close: for the
whole book, summed over its positions,

    sum of pnl_t = NAV_mid,t - NAV_0 - (interest + borrow fee + share and hedge costs)_{<= t}
                   - sum over u <= t of (N_{u-1} + Delta_{u-1}) (S_u + D_u - S_{u-1})

with N the book's shares and Delta the positions' delta at the previous close. The last term is the residual of the
module docstring: the hedge trades whole shares, so it is at most 0.5 share times the move each session. Both sides
come from different tables (daily_pnl and cash_flows against position_daily), so a P&L that misses a fill, a
delivery, a dividend or a hedge increment breaks it by that amount. What is left is the cents the dividend flows
round off: under 1 cent here.
"""

from __future__ import annotations

from datetime import date
from fractions import Fraction

import numpy as np
import pytest

import engine_helpers as eh
import engine_store as es
from volbt.engine import positions
from volbt.strategies.base import LegIntent, OrderIntent

D = date
COSTS = ("interest", "borrow_fee", "hedge_commission", "hedge_slippage", "share_commission", "share_slippage")


# --- the functions ---------------------------------------------------------------------------------------------------

def test_one_session_of_the_hedge_term():
    # Short 50 shares of delta: S 400 -> 404 with a 1.00 dividend makes the hedge (long 50 shares) earn 50 x 5.
    assert positions.hedge_increment(-50.0, 400.0, 404.0, 1.0) == 250.0
    assert positions.hedge_increment(30.0, 400.0, 398.0, 0.0) == 60.0


def test_a_delivery_is_valued_at_spot_plus_the_dividend_and_the_cash_at_the_strike():
    # A short 10-lot 400 call assigned on the ex-date: -1,000 shares, +$400,000.
    assert positions.delivery_value(-1000, 40_000_000, 410.0, 1.616) == pytest.approx(-1000 * 411.616 + 400_000.0)
    assert positions.delivery_value(1000, -40_000_000, 390.0) == pytest.approx(390_000.0 - 400_000.0)


def test_the_pnl_adds_its_four_parts():
    assert positions.open_value([{"value_mid_usd": -700.0, "delta_shares": -40.0},
                                 {"value_mid_usd": -650.0, "delta_shares": 35.5}]) == (-1350.0, -4.5)
    assert positions.position_pnl(-12_345, 100.0, -50.0, 25.0) == pytest.approx(-48.45)


# --- the identity through the engine ---------------------------------------------------------------------------------

def open_intent(expiry, strike, packages=10, sign=-1, entry_signal=None):
    def action(view, book, ctx):
        legs = (LegIntent(es.symbol(expiry, "C", strike), sign), LegIntent(es.symbol(expiry, "P", strike), sign))
        return [OrderIntent(None, "open", "short_straddle" if sign < 0 else "long_straddle", legs, packages,
                            entry_signal=entry_signal)]
    return action


def close_part(packages, structure=None):
    """Close `packages` of every leg of the open position (of `structure`, if given)."""
    def action(view, book, ctx):
        out = []
        for position in book.open_positions():
            if structure is not None and position.structure != structure:
                continue
            legs = tuple(LegIntent(lot.osi_symbol, 1 if lot.qty < 0 else -1) for lot in position.lots if lot.qty)
            out.append(OrderIntent(position.position_id, "close", position.structure, legs, packages, "signal"))
        return out
    return action


def identity_gap(result):
    """Per session: sum of position pnl minus the right-hand side of the module docstring's identity."""
    daily = eh.table(result, "daily_pnl").set_index("session_date")
    flows = eh.table(result, "cash_flows")
    per_day = eh.table(result, "position_daily")
    dividends = dict(es.DIVIDENDS)
    costs = flows[flows["kind"].isin(COSTS)].groupby("session_date")["amount_cents"].sum()
    last_pnl, gaps = {}, {}
    cum_costs = residual = 0.0
    previous = None
    for day, row in daily.iterrows():
        rows = per_day[per_day["session_date"] == day]
        for pid, pnl in zip(rows["position_id"], rows["pnl_usd"]):
            last_pnl[pid] = pnl
        cum_costs += costs.get(day, 0) / 100
        if previous is not None:
            before = per_day[per_day["session_date"] == previous]
            delta = before.loc[before["status"] == "open", "delta_shares"].sum()
            move = row["spot"] + dividends.get(day, 0.0) - daily.loc[previous, "spot"]
            residual += (daily.loc[previous, "shares"] + delta) * move
        nav_change = row["nav_mid"] - 1_000_000.0
        gaps[day] = sum(last_pnl.values()) - (nav_change - cum_costs - residual)
        previous = day
    return gaps


@pytest.fixture(scope="module")
def ex_date_run(engine_store, tmp_path_factory):
    """One short 2023-03-17 400 straddle from 02-22: its call is assigned early on the 03-17 ex-date (decided at
    03-16 on the projected dividend), its put expires the same day."""
    strategy = eh.Scripted({D(2023, 2, 21): open_intent(D(2023, 3, 17), 400.0)})
    return eh.run(engine_store, tmp_path_factory.mktemp("ex_date"), strategy, sample_end=D(2023, 3, 24))


@pytest.fixture(scope="module")
def partial_run(engine_store, tmp_path_factory):
    """One short 2023-04-21 400 straddle from 03-21, 4 of its 10 packages closed on 03-29, across the -8% gap of
    04-03, the rest closed on 04-05."""
    strategy = eh.Scripted({D(2023, 3, 20): open_intent(D(2023, 4, 21), 400.0),
                            D(2023, 3, 28): close_part(4), D(2023, 4, 4): close_part(6)})
    return eh.run(engine_store, tmp_path_factory.mktemp("partial"), strategy, sample_end=D(2023, 4, 12))


class Recorder(eh.Scripted):
    """Scripted, and records what the book shows of each position at every session."""

    def __init__(self, script: dict) -> None:
        super().__init__(script)
        self.seen = {}

    def decide(self, view, book, ctx):
        self.seen[ctx.session_date] = {p.position_id: (p.pnl_usd, p.premium_usd, p.entry_signal,
                                                       tuple(lot.mark_price for lot in p.lots))
                                       for p in book.positions if p.status == "open"}
        return super().decide(view, book, ctx)


@pytest.fixture(scope="module")
def overlap_run(engine_store, tmp_path_factory):
    """A short 2023-04-21 405 straddle (02-22 to 03-30) and a long 2023-03-17 395 straddle (03-02 to its expiry)."""
    strategy = Recorder({D(2023, 2, 21): open_intent(D(2023, 4, 21), 405.0, entry_signal=0.41),
                         D(2023, 3, 1): open_intent(D(2023, 3, 17), 395.0, packages=5, sign=1),
                         D(2023, 3, 29): close_part(10, "short_straddle")})
    result = eh.run(engine_store, tmp_path_factory.mktemp("overlap"), strategy, sample_end=D(2023, 4, 6))
    return result, strategy


def test_across_an_ex_date_and_an_early_assignment_the_pnl_is_the_hedged_nav_change(ex_date_run):
    events = eh.table(ex_date_run, "expiry_events")
    assert sorted(zip(events["effective_date"], events["event_type"])) == [(D(2023, 3, 17), "early_assigned"),
                                                                           (D(2023, 3, 17), "expired_worthless")]
    gaps = identity_gap(ex_date_run)
    assert len(gaps) == len(eh.table(ex_date_run, "daily_pnl")) and max(abs(g) for g in gaps.values()) < 0.01
    rows = eh.table(ex_date_run, "position_daily")
    last = rows.iloc[-1]
    assert (last["session_date"], last["status"], last["n_open_lots"]) == (D(2023, 3, 17), "closed", 0)
    assert last["settled_usd"] != 0 and last["open_value_usd"] == 0
    assert rows["premium_usd"].nunique() == 1 and rows["premium_usd"].iloc[0] > 0      # a credit
    assert (rows["hedge_usd"] != 0).any()


def test_across_a_partial_close_and_a_gap_the_pnl_is_the_hedged_nav_change(partial_run):
    gaps = identity_gap(partial_run)
    assert max(abs(g) for g in gaps.values()) < 0.01
    rows = eh.table(partial_run, "position_daily").set_index("session_date")
    fills = eh.table(partial_run, "fills")
    assert sorted(set(fills["fill_date"])) == [D(2023, 3, 21), D(2023, 3, 29), D(2023, 4, 5)]
    # The partial close moves fills_usd by its own cash and leaves two open lots of 6.
    assert rows.loc[D(2023, 3, 29), "fills_usd"] != rows.loc[D(2023, 3, 28), "fills_usd"]
    assert rows.loc[D(2023, 3, 29), "n_open_lots"] == 2 and rows.loc[D(2023, 4, 5), "status"] == "closed"


def test_two_overlapping_positions_share_the_hedge_and_add_up_to_the_book(overlap_run):
    result, strategy = overlap_run
    gaps = identity_gap(result)
    assert max(abs(g) for g in gaps.values()) < 0.01
    rows = eh.table(result, "position_daily")
    both = rows.groupby("session_date")["position_id"].nunique()
    assert (both == 2).sum() >= 10                      # they overlap for at least ten sessions
    # What the strategy saw at each session is that session's position_daily row.
    for day, seen in strategy.seen.items():
        for pid, (pnl, premium, entry, marks) in seen.items():
            row = rows[(rows["session_date"] == day) & (rows["position_id"] == pid)].iloc[0]
            assert (pnl, premium) == (row["pnl_usd"], row["premium_usd"])
            assert all(mark is not None for mark in marks)
    long_premium = rows.loc[rows["position_id"] == rows["position_id"].max(), "premium_usd"].iloc[0]
    assert long_premium < 0                             # a debit
    positions_table = eh.table(result, "positions").set_index("position_id")
    assert positions_table["entry_signal"].tolist()[0] == 0.41 and np.isnan(positions_table["entry_signal"].iloc[1])


# --- H and the hedge, recomputed (fix pass after the M4 part A review, item 5) ---------------------------------------

def recomputed_hedge(result):
    """{(session, position_id): H} from the in-NAV lot marks, the spot and the dividends alone: Delta of a position
    at a close is the sum of its lots' mark deltas (the last finite one carried when a lot has no delta), and
    H_t = sum over u <= t of -Delta_{u-1} (S_u + D_u - S_{u-1}). Not position_daily's delta_shares."""
    marks = eh.table(result, "position_marks")
    lots = eh.table(result, "lots").set_index("lot_id")["position_id"]
    marks = marks[marks["in_nav"]].assign(position_id=lambda m: m["lot_id"].map(lots))
    spot = eh.table(result, "daily_pnl").set_index("session_date")["spot"]
    days = eh.table(result, "position_daily")[["session_date", "position_id"]]
    dividends = dict(es.DIVIDENDS)
    out, delta, hedge, previous = {}, {}, {}, None
    for day in spot.index:
        for pid in sorted(set(days.loc[days["session_date"] == day, "position_id"])):
            if previous is not None:
                hedge[pid] = hedge.get(pid, 0.0) - delta.get(pid, 0.0) * (spot[day] + dividends.get(day, 0.0)
                                                                           - spot[previous])
            out[(day, pid)] = hedge.get(pid, 0.0)
            today = marks[(marks["session_date"] == day) & (marks["position_id"] == pid)]["delta_shares"]
            delta[pid] = float(today.sum()) if np.isfinite(today).all() else delta.get(pid, 0.0)
        previous = day
    return out


@pytest.mark.parametrize("name", ["ex_date_run", "partial_run", "overlap_run"])
def test_h_is_the_hedge_recomputed_from_the_lot_marks_spot_and_dividends(name, request):
    result = request.getfixturevalue(name)
    result = result[0] if isinstance(result, tuple) else result
    rows = eh.table(result, "position_daily")
    expected = recomputed_hedge(result)
    assert len(expected) == len(rows) and any(abs(h) > 100 for h in expected.values())
    for day, pid, h in zip(rows["session_date"], rows["position_id"], rows["hedge_usd"]):
        assert h == pytest.approx(expected[(day, pid)], abs=1e-6), (day, pid)


@pytest.mark.parametrize("name", ["ex_date_run", "partial_run", "overlap_run"])
def test_under_the_daily_hedge_the_books_shares_offset_the_positions_deltas(name, request):
    """|N + sum of Delta| <= 0.5 share at every close the book hedged, Delta from position_daily (the delta H uses)."""
    result = request.getfixturevalue(name)
    result = result[0] if isinstance(result, tuple) else result
    daily = eh.table(result, "daily_pnl").set_index("session_date")
    hedged = set(eh.table(result, "hedges")["executed_date"])
    rows = eh.table(result, "position_daily")
    total = rows.groupby("session_date")["delta_shares"].sum()
    checked = [day for day in total.index if day in hedged]
    assert len(checked) >= 10
    for day in checked:
        assert abs(daily.loc[day, "shares"] + total[day]) <= 0.5, day


def lagged_runs(engine_store, root):
    script = {D(2023, 3, 20): open_intent(D(2023, 4, 21), 400.0), D(2023, 4, 4): close_part(10)}
    return {name: eh.run(engine_store, root / name, eh.Scripted(dict(script)), sample_end=D(2023, 4, 12), **kw)
            for name, kw in (("every_5", {"hedge_every_n": 5}), ("next_open", {"hedge_timing": "next_open"}),
                             ("never", {"hedge_mode": "never"}), ("daily", {}))}


@pytest.fixture(scope="module")
def hedge_modes(engine_store, tmp_path_factory):
    return lagged_runs(engine_store, tmp_path_factory.mktemp("hedge_modes"))


def test_a_hedge_that_lags_the_positions_delta_gives_no_position_pnl(hedge_modes):
    """Every 5 sessions or at the next open the book's shares lag the positions' delta (the premise: |N + sum of
    Delta| > 0.5 share at some close), so hedge_usd and pnl_usd are null; with no hedge H is 0 and the P&L finite."""
    for name in ("every_5", "next_open"):
        result = hedge_modes[name]
        rows = eh.table(result, "position_daily")
        daily = eh.table(result, "daily_pnl").set_index("session_date")
        gap = rows.groupby("session_date")["delta_shares"].sum() + daily["shares"].reindex(
            rows["session_date"].unique()).to_numpy()
        assert (gap.abs() > 0.5).any(), name
        assert len(rows) > 10 and rows["hedge_usd"].isna().all() and rows["pnl_usd"].isna().all(), name
        assert rows["open_value_usd"].notna().all() and rows["delta_shares"].notna().all(), name
    never = eh.table(hedge_modes["never"], "position_daily")
    assert (never["hedge_usd"] == 0).all() and np.isfinite(never["pnl_usd"]).all()
    daily_rows = eh.table(hedge_modes["daily"], "position_daily")
    assert np.isfinite(daily_rows["pnl_usd"]).all() and (daily_rows["hedge_usd"] != 0).any()


def test_same_close_fills_are_hedged_late_and_give_no_position_pnl(engine_store, tmp_path):
    """Fix pass 2, item 6 (review B claim 5): with fill_timing "same_close", pass 9b fills lots after the close's
    hedge, so the book's shares lag the positions' delta (review B's script: |N + sum Delta| 525 shares); the engine
    computes no position P&L there, as under any other lagging hedge."""
    script = {D(2023, 3, 20): open_intent(D(2023, 4, 21), 400.0), D(2023, 3, 28): close_part(4),
              D(2023, 4, 4): close_part(6)}
    result = eh.run(engine_store, tmp_path / "same_close", eh.Scripted(script), sample_end=D(2023, 4, 12),
                    fill_timing="same_close")
    rows = eh.table(result, "position_daily")
    daily = eh.table(result, "daily_pnl").set_index("session_date")
    total = rows.groupby("session_date")["delta_shares"].sum()
    gap = (daily["shares"].reindex(total.index) + total).abs()
    assert gap.max() > 500 and (gap > 0.5).sum() >= 3                                       # the premise
    assert len(rows) > 10 and rows["hedge_usd"].isna().all() and rows["pnl_usd"].isna().all()
    assert rows["open_value_usd"].notna().all() and rows["delta_shares"].notna().all()


def test_which_hedges_give_a_position_pnl():
    assert positions.computed(eh.config()) and positions.computed(eh.config(hedge_mode="never"))
    assert not positions.computed(eh.config(fill_timing="same_close"))
    assert not positions.computed(eh.config(fill_timing="same_close", hedge_mode="never"))
    assert not positions.computed(eh.config(hedge_every_n=2))
    assert not positions.computed(eh.config(hedge_timing="next_open"))
    assert not positions.computed(eh.config(hedge_mode="band", hedge_band_pct_nav=Fraction(1, 100)))
