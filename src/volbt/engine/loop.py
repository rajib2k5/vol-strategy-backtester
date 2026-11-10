"""The daily loop (ADR-0001 §1): eleven steps per session, in a fixed order.

    1  step_01_load            the session's view (t, split, the year cache), its surface, S_t, the rate
                               dated strictly before t, the dividends paid by t
    2  step_02_start_of_day    the early events decided at t-1 (shares at K), dividends with ex-date t on
                               the shares, interest from t-1 to t on the PRIOR-CLOSE balance at the
                               previous session's rate (+0.50% when negative), the borrow fee; then every
                               pending order with a leg on a removed lot is cancelled (LOT_REMOVED)
    3  step_03_fill            share orders at this close in any case (D15); option orders created before
                               t against snapshot t, on snapshot sessions only (otherwise they wait)
    4  step_04_settle          contracts settling at t (ADR-0003); an unhedged book gets a share order for
                               t+1; pending orders on settled lots are cancelled (D12)
    5  step_05_mark            one mark per lot (ADR-0004), an INTRINSIC row for each lot settled today
                               (D11), greeks, NAV_mid and NAV_liq, DEGRADED, MARK_JUMP
    6  step_06_hedge           net delta, delivered shares included; -round_half_away(net) at S_t
    7  step_07_snapshot        the daily_pnl row; each position's hedged P&L (volbt.engine.positions), its
                               position_daily row
    8  step_08_eod_risk        passes through in M3, except ruin: NAV_mid <= 0 stops the run (ADR-0007 §5)
    9  step_09_decide          the strategy's signals updated through the view (their `signals` rows, then
                               ctx.signals), then strategy.decide(view, book.state(t), ctx), each intent read
                               once (intake), checked, stamped with V_t; with fill_timing = same_close a fill
                               pass 9b on snapshot t (D17)
    10 step_10_early           early exercise and assignment for t+1 (ADR-0003 §5)
    11 step_11_write           the rows are appended; on_session_end(t, book)

Why fills come before marks: an order created at t-1 fills at t's close, so its new lot gets its first
mark the same day (ADR-0001 test 5: fill -> expiry -> mark -> hedge).

Look-ahead. Every market read of a session goes through THAT session's StoreView (ADR-0001 §4), the
engine's own reads included, so the view's bound covers its marks, fills and decisions. The one exception
is the session calendar, dates only (decision D3). The year cache sits behind the views; the engine holds
its handle and never reads it directly.

Provenance. run_backtest checks the store before it reads (store_check, which tools/run_backtest.py passes
as volbt.build.require_current: the pricing tables must come from the current code over the current
inputs) and takes the data_fingerprint over every input file; after the run it checks both again and
refuses (StoreChanged) if the store is no longer current or a file changed, writing the ledger into
place only then. A run's config_hash and data_fingerprint never name code or data that did not make it.
"""

from __future__ import annotations

import hashlib
import json
import math
import platform
import shutil
import time
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
import scipy

from volbt import config
from volbt.data import osi
from volbt.data import store as store_module
from volbt.data.store import Store, YearCache, data_fingerprint, file_sha256, session_calendar, write_json
from volbt.engine import closures, early, fills, hedge, marks, positions, settlement
from volbt.engine import surface as surf
from volbt.engine.book import ENGINE_EXIT_REASONS, Book, Lot, Order, OrderLeg, Position
from volbt.engine.cash import borrow_fee_cents, dividend_cents, interest_cents
from volbt.engine.ledger import Ledger
from volbt.engine.run_config import SPLIT_DATES, RunConfig, config_hash, config_json, make_run_id, trial_hash
from volbt.signals.base import SignalValue
from volbt.strategies.base import EXIT_REASONS, INTENTS, REDUCE_ONLY_INTENTS, LegIntent, OrderIntent, SessionContext
from volbt.strategies.expiry import MAX_EXPIRY_DAYS

DAYS_PER_YEAR = 365
SIGNAL_WINDOW_DAYS = 30      # n_window: sessions in (t, t + 30 calendar days] (plan section 4)
INPUT_TABLES = ("option_quotes", "quote_iv", "expiry_forwards", "smile_fits")
REFERENCE_TABLES = ("rates", "dividends", "spy_bars", "vix")


class EngineError(RuntimeError):
    """The run cannot go on: an invalid order intent, a lot with no possible mark, an unmapped expiry."""


class StoreChanged(RuntimeError):
    """The store changed while the run read it, or is not current: the run is not written."""


@dataclass
class RunResult:
    run_id: str
    run_dir: Path
    status: str
    config_hash: str
    data_fingerprint: str
    source_commit: str
    sessions: int
    last_session: date | None
    digest: str
    files: dict
    timings: dict = field(default_factory=dict)


def run_inputs(store: Store, source: str, first_year: int, last_year: int) -> list[Path]:
    """Every file a run of `source` over [first_year, last_year] reads, after the store's own checks.

    The four day tables' partitions (checked_partitions: exactly what the writer leaves) and the reference
    tables (checked_table_file: each its one part-0.parquet). The year before the first is included: the
    cache keeps it for rule 4 across New Year.
    """
    files = []
    for table in INPUT_TABLES:
        for part in store.checked_partitions(table):
            if part["source"] == source and first_year - 1 <= int(part["year"]) <= last_year:
                files.append(store.partition_file(table, part))
    for table in REFERENCE_TABLES:
        if store.table_dir(table).exists():
            files.append(store.checked_table_file(table))
    return files


def as_date(value) -> date:
    return date(value.year, value.month, value.day)


PACKAGE_DIR = Path(__file__).resolve().parents[1]
LIBRARIES = {"numpy": np, "scipy": scipy, "pandas": pd, "pyarrow": pa, "duckdb": duckdb}


def code_fingerprint() -> str:
    """SHA-256 over every volbt source file and the library and Python versions (M3 review: a "-dirty" commit names
    no code, so the run id needs this too). Like volbt.build.code_fingerprint, which the engine may not import."""
    lines = [f"{path.relative_to(PACKAGE_DIR).as_posix()}\t{file_sha256(path)}" for path in sorted(PACKAGE_DIR.rglob("*.py"))]
    lines += [f"{name}=={module.__version__}" for name, module in LIBRARIES.items()]
    lines.append(f"python=={platform.python_version()}")
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def intake(intent) -> OrderIntent:
    """The intent as the engine checks and books it: every field read ONCE, into plain values (M3 round-3 review: a
    legs object that answered differently on later reads passed the checks with front-month legs and booked a
    181-DTE straddle). Anything but an OrderIntent itself is refused."""
    if type(intent) is not OrderIntent:
        raise EngineError(f"a strategy returns OrderIntent objects, not {type(intent).__name__}")
    legs = tuple(LegIntent(str(leg.osi_symbol), int(leg.ratio)) for leg in intent.legs)
    position_id, exit_reason, entry_signal = intent.position_id, intent.exit_reason, intent.entry_signal
    return OrderIntent(None if position_id is None else int(position_id), str(intent.intent), str(intent.structure),
                       legs, int(intent.packages), None if exit_reason is None else str(exit_reason),
                       None if entry_signal is None else float(entry_signal))


class Run:
    """One backtest: the state the eleven steps share. See the module docstring."""

    def __init__(self, cfg: RunConfig, strategy, store: Store, calendar: list[date], sessions: list[date]) -> None:
        self.cfg, self.strategy, self.store = cfg, strategy, store
        # The engine owns the strategy's signal objects (plan section 3): their state lives in one place.
        self.signals = tuple(getattr(strategy, "signals", ()))
        names = [signal.name for signal in self.signals]
        if len(set(names)) != len(names) or not all(isinstance(name, str) and name for name in names):
            raise EngineError(f"a strategy's signals need distinct, non-empty names: {names}")
        # Each run starts its signals from a clean state: a fit left by another run (or another store) is dropped.
        for signal in self.signals:
            if not callable(getattr(signal, "reset", None)):
                raise EngineError(f"signal {signal.name!r} has no reset(): the engine resets each signal before a run")
            if not callable(getattr(signal, "params", None)):
                raise EngineError(f"signal {signal.name!r} has no params(): its parameters enter config_json "
                                  "(fix pass 2, review B claim 4b)")
            signal.reset()
        # Milestone 4, part B: a strategy that keeps run state (VolStrategy: the expiries it has held) clears it too.
        reset = getattr(strategy, "reset", None)
        if callable(reset):
            reset()
        self.cache = YearCache(store, cfg.data_source)
        self.calendar = calendar
        self.session_set = frozenset(calendar)   # handed to the strategy in its SessionContext (D3): never mutable
        self.calendar_index = {day: i for i, day in enumerate(calendar)}
        self.sessions = sessions
        self.book = Book(cfg.initial_nav_cents)
        self.ledger = Ledger()
        self.status = "ok"
        self.prev: dict | None = None            # what the previous session's close left
        self.early_pending: list[dict] = []      # decided at t-1, booked at the start of t
        self.next_open_hedge: dict | None = None
        self.today: dict = {}
        self.counters = {"lattice_marks": 0, "early_lattice": 0, "stale_surface_days": 0, "sessions": 0}

    # --- helpers ---------------------------------------------------------------------------------

    def next_session(self, day: date) -> date | None:
        index = self.calendar_index.get(day)
        if index is None or index + 1 >= len(self.calendar):
            return None
        return self.calendar[index + 1]

    def n_window(self, day: date) -> int:
        """Sessions in (day, day + 30 calendar days], from the calendar (decision D3; plan section 4), a closure
        without notice counted as a session until its announcement date (volbt.engine.closures)."""
        return closures.n_window(self.calendar, day, days=SIGNAL_WINDOW_DAYS)

    def dividend_today(self) -> float:
        """The dividend per share with ex-date today (0 on other sessions)."""
        t = self.today
        return float(sum(amount for ex_date, amount in zip(*t["paid"]) if ex_date == t["t"]))

    def flow(self, kind: str, amount_cents: int, ref_id: int | None = None) -> None:
        """Every cash movement goes through here: the book's cash and the cash_flows table move together."""
        amount_cents = int(amount_cents)
        if amount_cents == 0:
            return
        self.book.cash_cents += amount_cents
        self.ledger.append("cash_flows", {"flow_id": self.book.next_id("flow"), "session_date": self.today["t"],
                                          "kind": kind, "amount_cents": amount_cents, "ref_id": ref_id})
        self.today["flows"][kind] = self.today["flows"].get(kind, 0) + amount_cents

    def quotes_for(self, symbols) -> dict:
        """osi_symbol -> marks.Quote for the symbols on today's snapshot (none on a session without one)."""
        t = self.today
        if not t["has_snapshot"] or not symbols:
            return {}
        view, source = t["view"], self.cfg.data_source
        rows = view.quotes(t["t"], sorted(set(symbols)), source=source)
        ivs = view.quote_ivs(t["t"], sorted(set(symbols)), source=source)
        iv_by = {s: (lm, otm, sm, v, fl) for s, lm, otm, sm, v, fl in
                 zip(ivs["osi_symbol"], ivs["log_moneyness"], ivs["is_otm"], ivs["in_smile"], ivs["iv"], ivs["iv_flags"])}
        out = {}
        for s, bid, ask, flags, volume in zip(rows["osi_symbol"], rows["bid"], rows["ask"], rows["quality_flags"],
                                              rows["volume"]):
            lm, otm, sm, v, fl = iv_by.get(s, (None, None, None, None, None))
            out[str(s)] = marks.Quote(None if bid != bid else float(bid), None if ask != ask else float(ask),
                                      int(flags), None if volume != volume else float(volume),
                                      None if lm is None or lm != lm else float(lm), None if otm is None else bool(otm),
                                      None if sm is None else bool(sm), None if v is None or v != v else float(v),
                                      None if fl is None else int(fl))
        return out

    def contract(self, symbol: str) -> tuple[date, float, str]:
        _, expiry, right, strike = osi.parse_osi(symbol)
        return expiry, float(strike), right

    def model_mid(self, symbol: str) -> tuple[float | None, float | None]:
        """(the American model price at the surface IV, h_model, fill_flags) of a contract today, for a surface fill."""
        surface = self.today["surface"]
        if surface is None or not surface.usable:
            return None, None, 0
        expiry, strike, right = self.contract(symbol)
        tau = (expiry - self.today["t"]).days / DAYS_PER_YEAR
        if tau <= 0:
            return None, None, 0
        forward, forward_flags = surface.forward(expiry)
        k = math.log(strike / forward)
        sigmas, bits = surface.iv(expiry, k)
        sigma = float(sigmas[0])
        times, amounts = surface.schedule(expiry)
        price = marks.model_prices([{"strike": strike, "tau": tau, "sigma": sigma, "right": right,
                                     "div_times": times, "div_amounts": amounts}],
                                   self.today["spot"], self.today["rate"], self.cfg.exercise_tree_steps)[0]
        self.counters["lattice_marks"] += 1
        h, other_expiry = surface.h_model(expiry, k, self.cfg.h_model_band)
        # ADR-0002 §7: a surface fill carries the mark's surface flags (and says when h_model came from another expiry).
        return float(price), h, int(bits[0]) | (fills.H_MODEL_OTHER_EXPIRY if other_expiry else 0)

    def cancel(self, order: Order, reason: str, status: str = "cancelled") -> None:
        order.status, order.cancel_reason, order.resolved_date = status, reason, self.today["t"]
        if order.intent == "open" and order.position_id is not None:
            position = self.book.positions[order.position_id]
            if position.status == "pending":
                position.status = "not_opened"

    def cancel_on_lots(self, removed: set[int]) -> None:
        """Cancel every pending order with a leg on a removed lot, the whole package (LOT_REMOVED)."""
        if not removed:
            return
        for order in self.book.pending():
            for leg in order.legs:
                lot = self.book.lot_for(order.position_id, leg.osi_symbol) if order.position_id is not None else None
                if lot is not None and lot.lot_id in removed:
                    self.cancel(order, "LOT_REMOVED")
                    break

    def close_lot(self, lot: Lot, reason: str) -> None:
        lot.qty, lot.closed_date = 0, self.today["t"]
        position = self.book.positions[lot.position_id]
        if all(other.qty == 0 for other in self.book.position_lots(position.position_id)):
            position.status, position.closed_date = "closed", self.today["t"]
            position.exit_reason = position.exit_reason or reason

    # --- the steps -------------------------------------------------------------------------------

    def step_01_load(self, t: date) -> None:
        cfg = self.cfg
        view = store_module.view(t, cfg.split, self.store, self.cache)
        bars = view.spy_bars()
        last = bars.iloc[-1]
        if as_date(last["date"]) != t:
            raise EngineError(f"{t} is a session with no SPY bar")
        rates = view.rates()
        dated = rates[(rates["date"] < np.datetime64(t)) & rates["r_cc"].notna()]
        if not len(dated):
            raise EngineError(f"no DGS3MO rate dated before {t}")
        paid_rows = view.dividends()
        paid = ([as_date(d) for d in paid_rows["ex_date"]], [float(a) for a in paid_rows["amount"]])
        spot = float(last["close"])
        rate = float(dated["r_cc"].iloc[-1])
        surface = surf.DaySurface.from_view(view, t, cfg.data_source, spot, rate, paid, self.calendar)
        has_snapshot = surface is not None
        if surface is None or not surface.usable:
            previous = self.prev["surface"] if self.prev else None
            if previous is not None:
                surface = previous.stale_copy(t, spot, rate, paid)
                self.counters["stale_surface_days"] += 1
        self.today = {"t": t, "view": view, "spot": spot, "spot_cents": fills.to_cents(spot),
                      "open": float(last["open"]), "rate": rate, "paid": paid, "surface": surface,
                      "has_snapshot": has_snapshot, "flows": {}, "settled": [], "marks": [], "new_orders": []}

    def step_02_start_of_day(self, t: date) -> None:
        book, removed = self.book, set()
        # 1. the early events decided at t-1: shares at K, cash -/+ 100 K.
        for event in self.early_pending:
            lot = book.lots[event["lot_id"]]
            if lot.qty == 0:
                continue
            shares = settlement.delivered_shares(lot.right, lot.qty)
            book.shares += shares
            cash = -shares * fills.to_cents(lot.strike)
            self.flow("early_settlement", cash, event["event_id"])
            # Booked before the dividends below, so the delivered shares carry today's dividend (engine.positions).
            book.positions[lot.position_id].settled_usd += positions.delivery_value(
                shares, cash, self.today["spot"], self.dividend_today())
            removed.add(lot.lot_id)
            self.close_lot(lot, "exercise" if lot.qty > 0 else "assignment")
        self.early_pending = []
        # 2. dividends with ex-date t, on the shares held now (after the early bookings: ADR-0003 test 5).
        for ex_date, amount in zip(*self.today["paid"]):
            if ex_date == t and book.shares != 0:
                self.flow("dividend", dividend_cents(book.shares, amount))
        # 3. interest from t-1 to t on the prior-close balance, at the previous session's rate (D8).
        if self.prev is not None:
            days = (t - self.prev["t"]).days
            self.flow("interest", interest_cents(self.prev["cash_cents"], self.prev["rate"], days,
                                                 self.cfg.negative_cash_spread))
            # 4. the borrow fee on the short shares' prior-close market value (D9).
            self.flow("borrow_fee", borrow_fee_cents(self.prev["shares"], self.prev["spot_cents"], days,
                                                     self.cfg.borrow_fee))
        # 5. orders with a leg on a lot those events removed.
        self.cancel_on_lots(removed)

    def fill_share_order(self, order: Order) -> None:
        t = self.today
        leg = order.legs[0]
        qty = leg.ratio * order.packages_requested
        commission, slippage = fills.stock_cost_cents(qty, self.cfg)
        fill_id = self.book.next_id("fill")
        self.book.shares += qty
        self.flow("share_trade", -qty * t["spot_cents"], fill_id)
        self.flow("share_commission", -commission, fill_id)
        self.flow("share_slippage", -slippage, fill_id)
        leg.filled = qty
        order.status, order.resolved_date, order.packages_filled = "filled", t["t"], order.packages_requested
        self.ledger.append("fills", {
            "fill_id": fill_id, "order_id": order.order_id, "leg_no": leg.leg_no, "fill_date": t["t"],
            "instrument": "share", "osi_symbol": None, "qty": qty, "price_cents": t["spot_cents"],
            "price": t["spot_cents"] / 100, "bid": None, "ask": None, "mid": None, "half_spread": None,
            "k_half_spread": None, "fees_cents": commission + slippage, "fees": (commission + slippage) / 100,
            "fill_source": "close", "cap_contracts": None, "cap_type": "none", "cap_volume": None,
            "cap_volume_date": None, "volume_reliable": False, "fill_flags": 0})

    def fill_option_order(self, order: Order, quotes: dict) -> None:
        cfg, t, book = self.cfg, self.today, self.book
        surface_mode = cfg.execution_mode == "surface"
        results = []
        for leg in order.legs:
            quote = quotes.get(leg.osi_symbol)
            bid_c, ask_c = (fills.to_cents(quote.bid), fills.to_cents(quote.ask)) if quote else (None, None)
            state = fills.quote_state(bid_c, ask_c, quote.flags if quote else None)
            cap, cap_type, reliable = fills.leg_cap(cfg, order.reduce_only, leg.cap_volume, order.created_date)
            side = 1 if leg.ratio > 0 else -1
            model_mid, h, flags = (None, None, 0)
            if surface_mode or (order.reduce_only and state == fills.NO_QUOTE):
                model_mid, h, flags = self.model_mid(leg.osi_symbol)
            price, source, reason = fills.leg_price(state, order.reduce_only, side, bid_c, ask_c, model_mid, h, cfg,
                                                    surface_mode)
            results.append({"leg": leg, "quote": quote, "bid_c": bid_c, "ask_c": ask_c, "cap": cap,
                            "cap_type": cap_type, "reliable": reliable, "price": price, "source": source,
                            "reason": reason, "model_mid": model_mid, "h": h, "flags": flags})
        if not order.reduce_only:
            # Opening packages fill whole or not at all (ADR-0002 §6): one leg that cannot fill stops them all.
            stopped = [r["reason"] for r in results if r["reason"] is not None]
            if stopped:
                self.cancel(order, stopped[0])
                return
            n = fills.package_count(order.packages_requested, [r["cap"] for r in results],
                                    [r["leg"].ratio for r in results])
            if n == 0:
                self.cancel(order, "CAP")
                return
            for r in results:
                r["qty"] = n * r["leg"].ratio
            order.packages_filled = n
        else:
            # Reduce-only packages fill leg by leg (decision D6).
            for r in results:
                lot = book.lot_for(order.position_id, r["leg"].osi_symbol)
                want = order.packages_requested * r["leg"].ratio
                room = min(abs(want), r["cap"], abs(lot.qty) if lot is not None else 0)
                r["qty"] = 0 if r["reason"] is not None else int(math.copysign(room, want))
                if r["reason"] is None and abs(r["qty"]) < abs(want):
                    r["reason"] = "CAP"
            order.packages_filled = min(abs(r["qty"]) // abs(r["leg"].ratio) for r in results)
        for r in results:
            if r["qty"] != 0:
                self.book_option_fill(order, r)
            if r["reason"] is not None:
                r["leg"].cancel_reason = r["reason"]
        reasons = [r["reason"] for r in results if r["reason"] is not None]
        filled_any = any(r["qty"] != 0 for r in results)
        if not reasons:
            order.status = "filled"
        elif filled_any:
            order.status, order.cancel_reason = "partial", reasons[0]
        else:
            order.status, order.cancel_reason = "cancelled", reasons[0]
        order.resolved_date = t["t"]
        if not order.reduce_only and order.status in ("filled", "partial") and order.packages_filled < order.packages_requested:
            order.status, order.cancel_reason = "partial", "CAP"

    def book_option_fill(self, order: Order, r: dict) -> None:
        cfg, t, book = self.cfg, self.today, self.book
        leg, qty, price = r["leg"], r["qty"], r["price"]
        fee = fills.option_fee_cents(qty, cfg)
        fill_id = book.next_id("fill")
        self.flow("option_premium", -qty * 100 * price, fill_id)
        self.flow("option_fee", -fee, fill_id)
        position = book.positions[order.position_id]
        position.fills_cents += -qty * 100 * price - fee
        if not order.reduce_only:
            position.premium_cents += -qty * 100 * price
        leg.filled += qty
        quote = r["quote"]
        if r["source"] == "quote":
            mid, half = (r["bid_c"] + r["ask_c"]) / 200, (r["ask_c"] - r["bid_c"]) / 200
            k_half = float(cfg.k) * half if not (r["bid_c"] == 0) else None
        else:
            mid, half = r["model_mid"], r["h"]
            k_half = float(cfg.surface_half_spread_mult) * half
        self.ledger.append("fills", {
            "fill_id": fill_id, "order_id": order.order_id, "leg_no": leg.leg_no, "fill_date": t["t"],
            "instrument": "option", "osi_symbol": leg.osi_symbol, "qty": qty, "price_cents": price,
            "price": price / 100, "bid": quote.bid if quote else None, "ask": quote.ask if quote else None,
            "mid": mid, "half_spread": half, "k_half_spread": k_half, "fees_cents": fee, "fees": fee / 100,
            "fill_source": r["source"], "cap_contracts": r["cap"], "cap_type": r["cap_type"],
            "cap_volume": leg.cap_volume, "cap_volume_date": leg.cap_volume_date, "volume_reliable": r["reliable"],
            "fill_flags": r["flags"] if r["source"] == "surface" else 0})
        lot = book.lot_for(order.position_id, leg.osi_symbol)
        if order.reduce_only:
            lot.qty += qty
            if lot.qty == 0:
                self.close_lot(lot, order.exit_reason or "signal")
            return
        if lot is None:
            expiry, strike, right = self.contract(leg.osi_symbol)
            lot = Lot(book.next_id("lot"), order.position_id, leg.osi_symbol, expiry, strike, right, 0, t["t"],
                      settlement.settle_date(expiry, self.session_set, self.calendar[-1]))
            book.lots[lot.lot_id] = lot
        lot.avg_open_price = (lot.avg_open_price * lot.opened_qty + price / 100 * qty) / (lot.opened_qty + qty)
        lot.opened_qty += qty
        lot.qty += qty
        if position.status == "pending":
            position.status, position.opened_date = "open", t["t"]

    def fill_pass(self, orders: list[Order]) -> None:
        """Resolve option orders against today's snapshot (step 3 and pass 9b)."""
        options = [o for o in orders if o.legs and o.legs[0].instrument == "option"]
        if not options or not self.today["has_snapshot"]:
            return                    # no snapshot: option orders wait (ADR-0002 §1)
        if self.cfg.execution_mode == "surface" and (self.today["surface"] is None or not self.today["surface"].usable):
            return
        quotes = self.quotes_for([leg.osi_symbol for o in options for leg in o.legs])
        for order in options:
            if order.status == "pending":
                self.fill_option_order(order, quotes)

    def step_03_fill(self, t: date) -> None:
        if self.next_open_hedge is not None:
            self.execute_hedge(self.next_open_hedge, price=self.today["open"])
            self.next_open_hedge = None
        waiting = [o for o in self.book.pending() if o.created_date < t]
        for order in waiting:
            if order.legs and order.legs[0].instrument == "share":
                self.fill_share_order(order)          # D15: share orders do not wait for an option snapshot
        self.fill_pass([o for o in waiting if o.status == "pending"])

    def step_04_settle(self, t: date) -> None:
        book, s_cents = self.book, self.today["spot_cents"]
        removed, delivered = set(), 0
        for lot in book.open_lots():
            if lot.settle_date != t:
                continue
            event = settlement.settle_lot(lot, s_cents, fills.to_cents(lot.strike), self.cfg.pin_band_cents)
            event_id = book.next_id("event")
            book.shares += event["shares_delivered"]
            delivered += event["shares_delivered"]
            self.flow("settlement", event["cash_cents"], event_id)
            book.positions[lot.position_id].settled_usd += positions.delivery_value(
                event["shares_delivered"], event["cash_cents"], self.today["spot"])
            self.ledger.append("expiry_events", {
                "event_id": event_id, "session_date": t, "effective_date": t, "lot_id": lot.lot_id,
                "osi_symbol": lot.osi_symbol, "event_type": event["event_type"], "contracts": event["contracts"],
                "shares_delivered": event["shares_delivered"], "strike": lot.strike, "settlement_price": s_cents / 100,
                "dividend_ex_date": None, "dividend_amount": None, "decision_method": None, "decision_iv": None,
                "threshold_value": None, "pin_flag": event["pin_flag"]})
            self.today["settled"].append((lot, lot.qty))
            removed.add(lot.lot_id)
            self.close_lot(lot, "expiry")
        self.cancel_on_lots(removed)
        if delivered != 0 and self.cfg.hedge_mode == "never":
            # ADR-0003 §3: an unhedged book liquidates the delivered shares at the t+1 close.
            self.new_order(None, "share_liquidation", True, None, [("share", None, -delivered)], 1, None)

    def step_05_mark(self, t: date) -> None:
        cfg, book, today = self.cfg, self.book, self.today
        lots = book.open_lots()
        quotes = self.quotes_for([lot.osi_symbol for lot in lots])
        previous = self.prev["marks"] if self.prev else {}
        atm = today["surface"].atm_iv_30d() if today["surface"] is not None and today["surface"].usable else None
        atm_change = (atm - self.prev["atm"]) if (self.prev and atm is not None and self.prev["atm"] is not None) else None
        spot_change = (today["spot"] / self.prev["spot"] - 1) if self.prev else None
        rows = [marks.intrinsic_row(lot, qty, t, today["spot_cents"] / 100, today["spot"]) for lot, qty in today["settled"]]
        rows += marks.mark_lots(lots, t, today["spot"], today["rate"], quotes, today["surface"], cfg,
                                today["has_snapshot"], previous, atm_change, spot_change)
        today["atm_change"], today["spot_change"] = atm_change, spot_change
        self.counters["lattice_marks"] += sum(r["mark_source"] in ("SURFACE_MODEL", "STALE_SURFACE") for r in rows)
        today["marks"], today["atm"] = rows, atm

    def execute_hedge(self, plan: dict, price: float) -> None:
        shares = plan["shares"]
        price_cents = fills.to_cents(price)
        commission, slippage = fills.stock_cost_cents(shares, self.cfg)
        self.book.shares += shares
        self.flow("hedge_trade", -shares * price_cents)
        self.flow("hedge_commission", -commission)
        self.flow("hedge_slippage", -slippage)
        self.ledger.append("hedges", {
            "session_date": plan["session_date"], "executed_date": self.today["t"], "trigger": plan["trigger"],
            "timing": self.cfg.hedge_timing, "delta_before_shares": plan["delta_before"], "shares_traded": shares,
            "price": price_cents / 100, "price_cents": price_cents, "commission": commission / 100,
            "slippage": slippage / 100, "commission_cents": commission, "slippage_cents": slippage,
            "shares_after": self.book.shares, "delta_after_shares": plan["delta_before"] + shares})

    def net_delta(self) -> float:
        deltas = np.asarray([r["delta_shares"] for r in self.today["marks"] if r["in_nav"]], dtype=float)
        return float(np.sum(deltas)) + self.book.shares if deltas.size else float(self.book.shares)

    def step_06_hedge(self, t: date, index: int) -> None:
        today = self.today
        net = self.net_delta()
        nav_now = marks.nav(self.book.cash_cents, self.book.shares, today["spot"],
                            [r["value_mid_usd"] for r in today["marks"] if r["in_nav"]])
        due, trigger = hedge.hedge_due(self.cfg, index, net, today["spot"], nav_now)
        today["delta_after"] = net
        if not due or not np.isfinite(net):
            return
        plan = {"session_date": t, "trigger": trigger, "delta_before": net, "shares": hedge.hedge_shares(net)}
        if self.cfg.hedge_timing == "next_open":
            # Executed at the next session's open (step 3). The last session's plan has no next open in the run, so
            # it is dropped and writes no hedges row (documented, not booked: M3 round-2 review).
            self.next_open_hedge = plan
            return
        self.execute_hedge(plan, today["spot"])
        today["delta_after"] = net + plan["shares"]

    def step_07_snapshot(self, t: date) -> None:
        cfg, book, today = self.cfg, self.book, self.today
        rows = [r for r in today["marks"] if r["in_nav"]]
        values = [r["value_mid_usd"] for r in rows]
        liq = [r["value_liq_usd"] for r in rows]
        nav_mid = marks.nav(book.cash_cents, book.shares, today["spot"], values)
        nav_liq = marks.nav(book.cash_cents, book.shares, today["spot"], liq)
        gross, model, share = marks.model_share(rows)
        flows = today["flows"]
        fee_kinds = ("option_fee", "share_commission", "share_slippage", "hedge_commission", "hedge_slippage")
        prev = self.prev
        days = (t - prev["t"]).days if prev else 0
        today["nav_mid"] = nav_mid
        self.ledger.rows["daily_pnl"] = [r for r in self.ledger.rows["daily_pnl"] if r["session_date"] != t]
        self.ledger.append("daily_pnl", {
            "session_date": t, "has_snapshot": today["has_snapshot"], "spot": today["spot"], "nav_mid": nav_mid,
            "nav_liq": nav_liq, "cash": book.cash_cents / 100, "cash_cents": book.cash_cents, "shares": book.shares,
            "share_value": book.shares * today["spot"],
            "option_value_mid": float(np.sum(np.asarray(values, dtype=float))) if values else 0.0,
            "option_value_liq": float(np.sum(np.asarray(liq, dtype=float))) if liq else 0.0,
            "option_value_gross": gross, "model_marked_value_gross": model, "n_open_lots": len(rows),
            "pnl_total": nav_mid - prev["nav_mid"] if prev else None, "pnl_delta": None, "pnl_gamma": None,
            "pnl_vega": None, "pnl_theta": None, "pnl_fees": sum(flows.get(k, 0) for k in fee_kinds) / 100,
            "pnl_interest": flows.get("interest", 0) / 100, "pnl_dividends": flows.get("dividend", 0) / 100,
            "pnl_borrow": flows.get("borrow_fee", 0) / 100, "pnl_residual": None,
            "daily_return": nav_mid / prev["nav_mid"] - 1 if prev and prev["nav_mid"] > 0 else None,
            "rf_return": math.expm1(prev["rate"] * days / DAYS_PER_YEAR) if prev else None, "rate": today["rate"],
            "margin_req_gross_usd": None, "short_option_mv_usd": None, "margin_req_net_usd": None,
            "excess_liquidity_usd": None, "share_nav_model_marked": share,
            "mark_quality": marks.mark_quality(gross, model, cfg), "delta_after_hedge_shares": today.get("delta_after")})
        self.position_rows(t, rows)

    def position_rows(self, t: date, rows: list[dict]) -> None:
        """Each open position's hedged P&L at t's close (volbt.engine.positions), and a position closed today: its
        position_daily row, held in `today` until step 11 commits it (step 7 runs again after pass 9b)."""
        book, today, prev = self.book, self.today, self.prev
        held = [p for p in book.positions.values()
                if p.status == "open" or (p.status == "closed" and p.closed_date == t)]
        today["position_rows"] = out = []
        if not held:
            return
        by_lot = {r["lot_id"]: r for r in rows}
        dividend = self.dividend_today()
        hedged = self.cfg.hedge_mode != "never"
        computed = positions.computed(self.cfg)     # else the book's hedge lags the positions' delta: P&L is NaN
        for position in held:
            lots = book.position_lots(position.position_id)
            marked = [by_lot[lot.lot_id] for lot in lots if lot.lot_id in by_lot]
            for row in marked:
                book.lots[row["lot_id"]].mark_price = row["mark_price"]
            open_usd, delta = positions.open_value(marked)
            if not np.isfinite(delta):
                # A lot with no sigma has no delta, so the book did not hedge today (step 6): the hedge the book
                # holds is the one set at the last close, and so is the position's share of it.
                delta = position.delta_shares
            h = position.hedge_usd if computed else float("nan")
            if hedged and prev is not None:
                h += positions.hedge_increment(position.delta_shares, prev["spot"], today["spot"], dividend)
            pnl = positions.position_pnl(position.fills_cents, open_usd, position.settled_usd, h)
            position.pnl_usd = pnl
            out.append({"session_date": t, "position_id": position.position_id, "status": position.status,
                        "n_open_lots": len(marked), "premium_usd": position.premium_cents / 100,
                        "fills_usd": position.fills_cents / 100, "open_value_usd": open_usd,
                        "settled_usd": position.settled_usd, "hedge_usd": h, "pnl_usd": pnl, "delta_shares": delta})

    def step_08_eod_risk(self, t: date) -> bool:
        """Margin and budgets are M5. Ruin (ADR-0007 §5): NAV_mid <= 0 stops the run. True to stop."""
        if self.today["nav_mid"] > 0:
            return False
        self.status = "ruin"
        self.ledger.append("risk_events", {"event_id": self.book.next_id("risk"), "session_date": t, "kind": "ruin",
                                           "greek": None, "value": self.today["nav_mid"], "limit_value": 0.0,
                                           "order_id": None, "action": "stop"})
        for position in self.book.positions.values():
            if position.status == "open":
                position.exit_reason = "ruin"
        return True

    def new_order(self, position_id, intent, reduce_only, structure, legs, packages, exit_reason, volumes=None) -> Order:
        t = self.today["t"]
        order = Order(self.book.next_id("order"), position_id, t, self.next_session(t), intent, reduce_only, structure,
                      packages, exit_reason=exit_reason)
        for leg_no, (instrument, symbol, ratio) in enumerate(legs, start=1):
            volume = (volumes or {}).get(symbol)
            order.legs.append(OrderLeg(leg_no, instrument, symbol, int(ratio),
                                       None if volume is None else int(volume), t if instrument == "option" else None))
        self.book.orders[order.order_id] = order
        self.today["new_orders"].append(order)
        return order

    def check_intent(self, intent, quotes: dict) -> None:
        book = self.book
        if intent.intent not in INTENTS:
            raise EngineError(f"unknown intent {intent.intent!r}")
        if not intent.legs or int(intent.packages) < 1 or any(int(leg.ratio) == 0 for leg in intent.legs):
            raise EngineError(f"an order needs legs, packages >= 1 and no zero ratio: {intent}")
        if len({leg.osi_symbol for leg in intent.legs}) != len(intent.legs):
            raise EngineError(f"a symbol appears twice in one order: {intent}")
        if intent.intent == "open":
            if intent.position_id is not None:
                raise EngineError("an opening order creates its position: position_id must be None")
            if intent.exit_reason is not None:
                # M3 round-3 review: an open carrying "ruin" was booked with it as the order's exit_reason.
                raise EngineError(f"an opening order has no exit_reason, not {intent.exit_reason!r}")
            missing = [leg.osi_symbol for leg in intent.legs if leg.osi_symbol not in quotes]
            if missing:
                raise EngineError(f"{self.today['t']}: an opening order names contracts not in the snapshot: {missing}")
            for leg in intent.legs:
                expiry = self.contract(leg.osi_symbol)[0]
                if (expiry - self.today["t"]).days > MAX_EXPIRY_DAYS:
                    # The 180-day constraint (strategies.expiry, ADR-0008 amendment 8) binds every strategy, not only
                    # those that pick expiries with nearest_monthly (M3 round-2 review: a scripted 363-DTE straddle filled).
                    raise EngineError(f"{self.today['t']}: {leg.osi_symbol} expires {expiry}, more than "
                                      f"{MAX_EXPIRY_DAYS} days after the session")
                settlement.settle_date(expiry, self.session_set, self.calendar[-1])
            return
        if intent.entry_signal is not None:
            raise EngineError(f"a reduce-only order carries no entry_signal, not {intent.entry_signal!r}")
        position = book.positions.get(intent.position_id)
        if position is None or position.status != "open":
            raise EngineError(f"a reduce-only order must name an open position, not {intent.position_id}")
        if intent.exit_reason not in EXIT_REASONS:
            raise EngineError(f"a reduce-only order must give one of {EXIT_REASONS} as its exit_reason, not "
                              f"{intent.exit_reason!r} (the engine's own are {ENGINE_EXIT_REASONS})")
        if any(o.position_id == intent.position_id for o in book.pending()):
            raise EngineError(f"position {intent.position_id} already has a pending order (one per position, D22)")
        for leg in intent.legs:
            lot = book.lot_for(intent.position_id, leg.osi_symbol)
            want = int(intent.packages) * int(leg.ratio)
            if lot is None or lot.qty == 0 or lot.qty * want > 0 or abs(want) > abs(lot.qty):
                raise EngineError(f"a reduce-only leg must reduce |qty| of a lot of the position: {leg} on {lot}")

    def update_signals(self, t: date) -> MappingProxyType:
        """Step 9, first: each of the strategy's signals updated once, through t's view, and its `signals` row. The
        strategy reads the values in ctx.signals, a read-only mapping by name."""
        values = {}
        n_window = self.n_window(t)
        for signal in self.signals:
            value = signal.update(self.today["view"], n_window)
            if type(value) is not SignalValue:
                raise EngineError(f"signal {signal.name!r} returned {type(value).__name__}, not a SignalValue")
            self.ledger.append("signals", {
                "session_date": t, "signal_name": signal.name, "iv30": value.iv30, "iv30_flags": value.iv30_flags,
                "rv_forecast": value.rv_forecast, "rv_model": value.rv_model, "model_fit_date": value.model_fit_date,
                "vrp_spread": value.vrp_spread, "zscore": None, "vix_bucket": value.vix_bucket,
                "vol_regime": value.vol_regime, "log_var_ratio": value.value, "n_window": value.n_window,
                "flags": value.flags})
            values[signal.name] = value
        return MappingProxyType(values)

    def step_09_decide(self, t: date) -> bool:
        """The strategy's orders for t+1; with same_close, pass 9b. True when 9b ends in ruin (the run stops)."""
        today = self.today
        ctx = SessionContext(t, self.next_session(t), today["has_snapshot"], self.cfg.data_source,
                             self.cfg.execution_mode, self.session_set, self.update_signals(t), today["nav_mid"])
        intents = [intake(intent) for intent in self.strategy.decide(today["view"], self.book.state(t), ctx) or []]
        symbols = [leg.osi_symbol for intent in intents for leg in intent.legs]
        quotes = self.quotes_for(symbols)
        seen = set()
        for intent in intents:
            if intent.position_id is not None and intent.position_id in seen:
                raise EngineError(f"two orders for position {intent.position_id} in one session (one per position)")
            seen.add(intent.position_id)
            self.check_intent(intent, quotes)
            volumes = {leg.osi_symbol: quotes[leg.osi_symbol].volume if leg.osi_symbol in quotes else None
                       for leg in intent.legs}
            position_id = intent.position_id
            if intent.intent == "open":
                position_id = self.book.next_id("position")
                self.book.positions[position_id] = Position(position_id, self.strategy.name, intent.structure, t,
                                                            tuple((leg.osi_symbol, int(leg.ratio)) for leg in intent.legs),
                                                            entry_signal=intent.entry_signal)
            self.new_order(position_id, intent.intent, intent.intent in REDUCE_ONLY_INTENTS, intent.structure,
                           [("option", leg.osi_symbol, leg.ratio) for leg in intent.legs], int(intent.packages),
                           intent.exit_reason, volumes)
        if self.cfg.fill_timing == "same_close" and today["new_orders"]:
            # Pass 9b (D17): the diagnostic fills today's orders at today's snapshot, stamped today. The new lots
            # are marked today and hedged from the next session.
            created = [o for o in today["new_orders"] if o.legs[0].instrument == "option"]
            self.fill_pass(created)
            if any(o.status in ("filled", "partial") for o in created):
                # Pass 9b changed the book, so every open lot is marked again: a lot 9b closed leaves NAV, a new one
                # gets its first mark. (M3 review: the closed lots' step-5 marks stayed in NAV, counting them twice:
                # nav_mid was off by -8,740.00 on the fixture's 2023-02-09.) Then the day's row and ruin again.
                lots = self.book.open_lots()
                quotes = self.quotes_for([lot.osi_symbol for lot in lots])
                today["marks"] = [r for r in today["marks"] if not r["in_nav"]] + marks.mark_lots(
                    lots, t, today["spot"], today["rate"], quotes, today["surface"], self.cfg, today["has_snapshot"],
                    self.prev["marks"] if self.prev else {}, today["atm_change"], today["spot_change"])
                self.step_07_snapshot(t)
                return self.step_08_eod_risk(t)
        return False

    def step_10_early(self, t: date) -> None:
        t_next = self.next_session(t)
        surface = self.today["surface"]
        if t_next is None or surface is None or not surface.usable:
            return
        delivered = 0
        for lot in self.book.open_lots():
            if lot.settle_date <= t:
                continue
            forward, _ = surface.forward(lot.expiry)
            sigma = float(surface.iv(lot.expiry, math.log(lot.strike / forward))[0][0])
            decision = early.decide_lot(lot, t, t_next, self.today["spot"], self.today["rate"], sigma,
                                        self.today["paid"], self.calendar, self.cfg)
            if decision is None:
                continue
            if decision["method"] == "crr":
                self.counters["early_lattice"] += 1
            if not decision["exercise"]:
                continue
            event_id = self.book.next_id("event")
            self.ledger.append("expiry_events", {
                "event_id": event_id, "session_date": t, "effective_date": t_next, "lot_id": lot.lot_id,
                "osi_symbol": lot.osi_symbol, "event_type": early.event_type(lot.qty), "contracts": lot.qty,
                "shares_delivered": settlement.delivered_shares(lot.right, lot.qty), "strike": lot.strike,
                "settlement_price": None, "dividend_ex_date": decision["ex_date"],
                "dividend_amount": decision["dividend"], "decision_method": decision["method"],
                "decision_iv": decision["sigma"], "threshold_value": decision["threshold"], "pin_flag": False})
            self.early_pending.append({"lot_id": lot.lot_id, "event_id": event_id})
            delivered += settlement.delivered_shares(lot.right, lot.qty)
        if delivered != 0 and self.cfg.hedge_mode == "never":
            # ADR-0003 §5, "hedges or liquidation follow the rules in point 3": an unhedged book liquidates the
            # shares an early event delivers. Decided tonight, booked before t+1 opens (step 2), sold at t+1's
            # close (step 3), as for an expiry-day delivery. (Found by an xfail in tests/test_engine_early.py.)
            self.new_order(None, "share_liquidation", True, None, [("share", None, -delivered)], 1, None)

    def step_11_write(self, t: date, on_session_end) -> None:
        for row in self.today["marks"]:
            self.ledger.append("position_marks", row)
        today = self.today
        for row in today.get("position_rows", []):
            # Commit each position's H and delta: the next session's hedge term starts from them.
            position = self.book.positions[row["position_id"]]
            position.hedge_usd, position.delta_shares = row["hedge_usd"], row["delta_shares"]
            self.ledger.append("position_daily", row)
        self.prev = {"t": t, "spot": today["spot"], "spot_cents": today["spot_cents"], "rate": today["rate"],
                     "cash_cents": self.book.cash_cents, "shares": self.book.shares, "nav_mid": today["nav_mid"],
                     "surface": (today["surface"] if today["has_snapshot"] and today["surface"] is not None
                                 and today["surface"].usable else (self.prev["surface"] if self.prev else None)),
                     "marks": {r["lot_id"]: r["mark_price"] for r in today["marks"] if r["in_nav"]},
                     "atm": today.get("atm")}
        self.counters["sessions"] += 1
        if on_session_end is not None:
            on_session_end(t, self.book)

    def session(self, t: date, index: int, on_session_end) -> bool:
        """One session's eleven steps. True when the run must stop (ruin)."""
        self.step_01_load(t)
        self.step_02_start_of_day(t)
        self.step_03_fill(t)
        self.step_04_settle(t)
        self.step_05_mark(t)
        self.step_06_hedge(t, index)
        self.step_07_snapshot(t)
        stop = self.step_08_eod_risk(t)
        if not stop:
            stop = self.step_09_decide(t)
        if not stop:
            self.step_10_early(t)
        self.step_11_write(t, on_session_end)
        return stop

    # --- the ledger's slowly changing tables ---------------------------------------------------------

    def final_rows(self, run_row: dict) -> None:
        book, ledger = self.book, self.ledger
        ledger.append("runs", run_row)
        for p in book.positions.values():
            ledger.append("positions", {"position_id": p.position_id, "strategy_id": p.strategy_id,
                                        "structure": p.structure, "created_date": p.created_date,
                                        "opened_date": p.opened_date, "closed_date": p.closed_date,
                                        "status": p.status, "entry_signal": p.entry_signal,
                                        "exit_reason": p.exit_reason})
        for o in book.orders.values():
            ledger.append("orders", {"order_id": o.order_id, "position_id": o.position_id, "created_date": o.created_date,
                                     "target_fill_date": o.target_fill_date, "resolved_date": o.resolved_date,
                                     "intent": o.intent, "reduce_only": o.reduce_only, "structure": o.structure,
                                     "packages_requested": o.packages_requested,
                                     "packages_after_risk": o.packages_requested, "packages_filled": o.packages_filled,
                                     "risk_action": "none", "status": o.status, "cancel_reason": o.cancel_reason,
                                     "exit_reason": o.exit_reason})
            for leg in o.legs:
                ledger.append("order_legs", {"order_id": o.order_id, "leg_no": leg.leg_no, "instrument": leg.instrument,
                                             "osi_symbol": leg.osi_symbol, "ratio": leg.ratio,
                                             "cap_volume": leg.cap_volume, "cap_volume_date": leg.cap_volume_date,
                                             "filled": leg.filled, "cancel_reason": leg.cancel_reason})
        for lot in book.lots.values():
            ledger.append("lots", {"lot_id": lot.lot_id, "position_id": lot.position_id, "osi_symbol": lot.osi_symbol,
                                   "expiry": lot.expiry, "settle_date": lot.settle_date, "strike": lot.strike,
                                   "option_right": lot.right, "qty_open": lot.qty, "qty_opened": lot.opened_qty,
                                   "avg_open_price": lot.avg_open_price, "opened_date": lot.opened_date,
                                   "closed_date": lot.closed_date})


def run_backtest(cfg: RunConfig, strategy, store: Store | None = None, runs_root: Path | None = None,
                 stop_after: date | None = None, on_session_end=None, source_commit: str = "uncommitted",
                 store_check=None, run_gate=None, rerun_of: str | None = None,
                 rerun_reason: str | None = None) -> RunResult:
    """Run the daily loop over cfg's sample (or up to stop_after) and write the ledger. See the module docstring.

    store_check(store) runs before and after the run and must raise if the store is not current
    (tools/run_backtest.py passes volbt.build.require_current, which the engine may not import).
    run_gate(cfg, strategy, trial_hash) runs once, before anything is read, and must raise to refuse the run
    (milestone 4: the pre-registration's gate, tools/prereg.py, which the engine may not import either). It may
    return a recorder, record(run_id, config_hash), called once the run's folder is in place. A run that ends after
    the development split (2019-12-31) needs a gate: without one it is refused, whatever its purpose (fails closed;
    fix pass after the M4 part A review).
    The trust boundary (review B's B5; fix pass 3, item D6): the engine checks only that a gate is there. It cannot
    tell the pre-registration's gate from one that refuses nothing (the tests' made-up gate is one), so whatever
    limits a run past 2019 (spent windows, the holdout once, the validation re-runs, a diagnostic's kind) is the
    caller's gate. tools/run_backtest.py and tools/smoke_m4.py pass prereg.make_run_gate (tested in
    tests/test_smoke_m4.py); a caller that passes another gate is outside these checks.
    rerun_of and rerun_reason go to the runs row as given (ADR-0010 §1: a re-run logs the run it repeats and why;
    fix pass 2, review B N3): a non-blank string or None.
    """
    for name, value in (("rerun_of", rerun_of), ("rerun_reason", rerun_reason)):
        if value is not None and (type(value) is not str or not value.strip()):
            raise EngineError(f"{name} must be a non-blank string or None, not {value!r}")
    started = time.perf_counter()
    if run_gate is None and cfg.sample_end > SPLIT_DATES["development"][1]:
        raise EngineError(f"a run that ends after {SPLIT_DATES['development'][1]} needs a run_gate "
                          "(tools/prereg.py make_run_gate): without one it is refused")
    store = store or Store()
    runs_root = Path(runs_root) if runs_root is not None else config.work_dir() / "runs"
    record = run_gate(cfg, strategy, trial_hash(cfg, strategy)) if run_gate is not None else None
    if store_check is not None:
        store_check(store)
    files = run_inputs(store, cfg.data_source, cfg.sample_start.year, cfg.sample_end.year)
    fingerprint = data_fingerprint(files, store.root)
    calendar = session_calendar(store)
    last = min(cfg.sample_end, stop_after) if stop_after is not None else cfg.sample_end
    sessions = [d for d in calendar if cfg.sample_start <= d <= last]
    if not sessions:
        raise EngineError(f"no SPY session in [{cfg.sample_start}, {last}]")
    run = Run(cfg, strategy, store, calendar, sessions)
    checked = time.perf_counter()
    last_session = None
    for index, t in enumerate(sessions):
        last_session = t
        if run.session(t, index, on_session_end):
            break
    looped = time.perf_counter()
    # A run stopped early is a run over a shorter sample: its config says so, so it can never take the full run's id
    # and folder (M3 review: a run stopped at 2023-02-15 replaced the full run's folder and said sample_end 04-28).
    # Its sample_end is the last session it ran, so a stop on a weekend or holiday names the same run as a stop on the
    # session before it (round-2 review: Friday 2023-02-17 and Saturday 02-18 gave two ids).
    full_last = max(d for d in calendar if cfg.sample_start <= d <= cfg.sample_end)
    effective = cfg if sessions[-1] == full_last else replace(cfg, sample_end=sessions[-1])
    chash = config_hash(effective, strategy)
    code = code_fingerprint()
    run_id = make_run_id(chash, fingerprint, source_commit, code)
    run.final_rows({"source_commit": source_commit, "code_fingerprint": code, "config_hash": chash,
                    "config_json": json.dumps(config_json(effective, strategy), sort_keys=True),
                    "data_fingerprint": fingerprint, "data_source": cfg.data_source,
                    "execution_mode": cfg.execution_mode, "fill_timing": cfg.fill_timing, "cap_mode": cfg.cap_mode,
                    "chain_mask": cfg.chain_mask, "split": cfg.split, "run_purpose": cfg.run_purpose,
                    "trial_group": cfg.trial_group, "strategy": strategy.name, "rerun_of": rerun_of,
                    "rerun_reason": rerun_reason,
                    "sample_start": cfg.sample_start, "sample_end": effective.sample_end, "last_session": last_session,
                    "status": run.status})
    final = runs_root / f"run_id={run_id}"
    staging = runs_root / f"run_id={run_id}.tmp"
    if staging.exists():
        shutil.rmtree(staging)
    written = run.ledger.write(staging)
    # The reader checks after it read (ADR-0001 amendment 4): the same store, still current, or no ledger.
    if store_check is not None:
        store_check(store)
    after = data_fingerprint(run_inputs(store, cfg.data_source, cfg.sample_start.year, cfg.sample_end.year), store.root)
    if after != fingerprint:
        shutil.rmtree(staging)
        raise StoreChanged(f"the run's input files changed while it ran (data_fingerprint {fingerprint[:12]} before, "
                           f"{after[:12]} after): one writer at a time (ADR-0001); run again")
    finished = time.perf_counter()
    timings = {"check_and_fingerprint_s": round(checked - started, 3), "loop_s": round(looped - checked, 3),
               "write_and_recheck_s": round(finished - looped, 3), "total_s": round(finished - started, 3)}
    write_json({"run_id": run_id, "files": written, "timings": timings, "counters": run.counters,
                "sessions": run.counters["sessions"]}, staging / "run_meta.json")
    if final.exists():
        shutil.rmtree(final)
    staging.rename(final)
    if record is not None:
        record(run_id, chash)
    return RunResult(run_id, final, run.status, chash, fingerprint, source_commit, run.counters["sessions"],
                     last_session, run.book.digest(), written, timings)
