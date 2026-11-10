"""An independent audit of one run's ledger (not a test file: pytest does not collect it).

It recomputes, from the STORE's parquet files and the ADRs' formulas, and importing nothing from volbt:
every session's cash against the initial cash plus its flows; each option fill's premium, its fee (70 cents a
contract, opening and closing, ADR-0002 §3) and, for a quote fill, its integer-cent price at k (ADR-0002 §2); each
share fill's trade, commission and slippage (Decimal, ROUND_HALF_UP, ADR-0002 §4); each hedge's price (the close,
or the next session's OPEN for hedge_timing next_open) and costs; each expiry and early event's delivery, cash,
date and pin flag (ADR-0003); interest on the prior-close balance at the rate dated strictly before the previous
session, the borrow fee and the dividends (ADR-0007, decisions D8 and D9); the share count; the set of lots in
NAV; each quote mark, liquidation value and model liquidation value (ADR-0004); NAV_mid and NAV_liq.

The cash identity test (tests/test_engine_cash.py) proves only that cash moves through Run.flow; this audit
checks the amounts. It began as the M3 round-2 code reviewer's probe. audit(run_dir, store_root) returns
(problems, info); no problems is a pass.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pyarrow.dataset as ds
import pyarrow.parquet as pq


def T(run_dir, name):
    return pq.read_table(Path(run_dir) / name / "part-0.parquet").to_pylist()


def d(x):
    return None if x is None else date(x.year, x.month, x.day)


def half_up(dollars: Decimal) -> int:
    return int((dollars * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def audit(run_dir, store_root, initial=100_000_000, fee=70, k_n=4, borrow=Decimal("0.0025"), neg=Decimal("0.005")):
    run_dir, store_root = Path(run_dir), Path(store_root)
    probs = []
    P = lambda *a: probs.append(" ".join(str(x) for x in a))
    run = T(run_dir, "runs")[0]
    source = run["data_source"]
    flows, dp, fills, hedges = T(run_dir, "cash_flows"), T(run_dir, "daily_pnl"), T(run_dir, "fills"), T(run_dir, "hedges")
    events, marks, lots, orders = T(run_dir, "expiry_events"), T(run_dir, "position_marks"), T(run_dir, "lots"), T(run_dir, "orders")
    lot_by = {l["lot_id"]: l for l in lots}
    order_by = {o["order_id"]: o for o in orders}
    bars = pq.read_table(store_root / "spy_bars" / "part-0.parquet").to_pylist()
    close = {d(b["date"]): b["close"] for b in bars}
    opn = {d(b["date"]): b["open"] for b in bars}
    rates = sorted((d(r["date"]), r["r_cc"]) for r in pq.read_table(store_root / "rates" / "part-0.parquet").to_pylist()
                   if r["r_cc"] is not None and not math.isnan(r["r_cc"]))
    divs = [(d(r["ex_date"]), r["amount"]) for r in pq.read_table(store_root / "dividends" / "part-0.parquet").to_pylist()]
    rate_before = lambda t: [r for day, r in rates if day < t][-1]
    sessions = [d(r["session_date"]) for r in dp]
    syms = sorted({l["osi_symbol"] for l in lots})
    qds = ds.dataset(store_root / "option_quotes", partitioning="hive")
    qt = qds.to_table(filter=(ds.field("source") == source) & ds.field("osi_symbol").isin(syms),
                      columns=["quote_date", "osi_symbol", "bid", "ask"]).to_pylist()
    quote = {(d(q["quote_date"]), q["osi_symbol"]): q for q in qt}
    snap_days = set(d(x) for x in qds.to_table(filter=(ds.field("source") == source),
                                               columns=["quote_date"]).column("quote_date").unique().to_pylist())
    cents = lambda x: int(round(x * 100))
    by_kind_day, by_ref, flow_by_day = defaultdict(int), defaultdict(list), defaultdict(int)
    for f in flows:
        by_kind_day[(f["kind"], d(f["session_date"]))] += f["amount_cents"]
        flow_by_day[d(f["session_date"])] += f["amount_cents"]
        if f["ref_id"] is not None:
            by_ref[(f["kind"], f["ref_id"])].append(f["amount_cents"])
    run_cash = initial
    for r in dp:                                                    # 1. cash identity, every session
        run_cash += flow_by_day[d(r["session_date"])]
        if r["cash_cents"] != run_cash:
            P("cash identity", d(r["session_date"]), r["cash_cents"], run_cash)
    for f in fills:                                                 # 2. fills
        t, o = d(f["fill_date"]), order_by[f["order_id"]]
        if f["instrument"] == "option":
            if by_ref[("option_premium", f["fill_id"])] != [-f["qty"] * 100 * f["price_cents"]]:
                P("premium", f["fill_id"])
            if by_ref[("option_fee", f["fill_id"])] != [-fee * abs(f["qty"])]:
                P("fee", f["fill_id"], by_ref[("option_fee", f["fill_id"])])
            if f["fill_source"] == "quote":
                q = quote[(t, f["osi_symbol"])]
                b, a, side = cents(q["bid"]), cents(q["ask"]), 1 if f["qty"] > 0 else -1
                want = a if (b == 0 and side > 0) else (-(-(4 * (b + a) + k_n * (a - b)) // 8) if side > 0
                                                         else (4 * (b + a) - k_n * (a - b)) // 8)
                if want != f["price_cents"]:
                    P("fill price", f["fill_id"], t, b, a, f["price_cents"], want)
            ct = d(o["created_date"])
            if run["fill_timing"] == "next_close":
                if not t > ct or [s for s in sessions if ct < s < t and s in snap_days]:
                    P("next-close fill date", f["fill_id"], ct, t)
            elif t != ct and o["intent"] != "share_liquidation":
                P("same-close fill not on its creation date", f["fill_id"], ct, t)
        else:
            if by_ref[("share_trade", f["fill_id"])] != [-f["qty"] * cents(close[t])]:
                P("share trade", f["fill_id"])
            n = Decimal(abs(f["qty"]))
            if (by_ref[("share_commission", f["fill_id"])], by_ref[("share_slippage", f["fill_id"])]) != (
                    [-half_up(max(n * Decimal("0.005"), Decimal("1.00")))], [-half_up(n * Decimal("0.005"))]):
                P("share costs", f["fill_id"])
    hedge_day = defaultdict(lambda: [0, 0, 0, 0])                   # 3. hedges
    for h in hedges:
        t = d(h["executed_date"])
        px = opn[t] if h["timing"] == "next_open" else close[t]
        if h["price_cents"] != cents(px):
            P("hedge price", t, h["price_cents"], px)
        if h["timing"] == "next_open":
            nxt = [s for s in sessions if s > d(h["session_date"])]
            if not nxt or nxt[0] != t:
                P("next_open hedge date", h["session_date"], t)
        n = Decimal(abs(h["shares_traded"]))
        com = half_up(max(n * Decimal("0.005"), Decimal("1.00"))) if n else 0
        sl = half_up(n * Decimal("0.005")) if n else 0
        if (h["commission_cents"], h["slippage_cents"]) != (com, sl):
            P("hedge costs", t)
        e = hedge_day[t]
        e[0] += -h["shares_traded"] * cents(px); e[1] -= com; e[2] -= sl; e[3] += h["shares_traded"]
    for t, (tr, com, sl, _) in hedge_day.items():
        if (by_kind_day[("hedge_trade", t)], by_kind_day[("hedge_commission", t)], by_kind_day[("hedge_slippage", t)]) != (tr, com, sl):
            P("hedge flows", t)
    deliveries = defaultdict(int)                                   # 4. settlement and early events
    for e in events:
        lot = lot_by[e["lot_id"]]
        K = cents(lot["strike"])
        if e["decision_method"] is None:
            t = d(e["session_date"])
            S = cents(close[t])
            if e["settlement_price"] is None or cents(e["settlement_price"]) != S:
                P("settle price", e["event_id"])
            itm = (S - K >= 1) if lot["option_right"] == "C" else (K - S >= 1)
            sh = (100 * e["contracts"] if lot["option_right"] == "C" else -100 * e["contracts"]) if itm else 0
            if e["shares_delivered"] != sh:
                P("delivery", e["event_id"], e["shares_delivered"], sh)
            if by_ref[("settlement", e["event_id"])] != ([-sh * K] if sh else []):
                P("settlement cash", e["event_id"])
            if t != d(lot["settle_date"]):
                P("settled on the wrong date", e["event_id"])
            if e["pin_flag"] != (e["contracts"] < 0 and abs(S - K) <= 50):
                P("pin flag", e["event_id"])
            deliveries[t] += sh
        else:
            t = d(e["effective_date"])
            sh = 100 * e["contracts"] if lot["option_right"] == "C" else -100 * e["contracts"]
            if e["shares_delivered"] != sh or by_ref[("early_settlement", e["event_id"])] != [-sh * K]:
                P("early event", e["event_id"])
            if t != [s for s in sessions if s > d(e["session_date"])][0]:
                P("early event not effective the next session", e["event_id"])
            deliveries[("early", t)] += sh
    marks_by_day, share_fill_day = defaultdict(list), defaultdict(int)
    for m in marks:
        marks_by_day[d(m["session_date"])].append(m)
    for f in fills:
        if f["instrument"] == "share":
            share_fill_day[d(f["fill_date"])] += f["qty"]
    lot_of = {(l["position_id"], l["osi_symbol"]): l["lot_id"] for l in lots}
    lot_changes = defaultdict(list)
    for f in fills:
        if f["instrument"] == "option":
            lot_changes[lot_of[(order_by[f["order_id"]]["position_id"], f["osi_symbol"])]].append((d(f["fill_date"]), f["qty"]))
    for e in events:
        lot_changes[e["lot_id"]].append((d(e["effective_date"]) if e["decision_method"] else d(e["session_date"]), -e["contracts"]))
    prev = None
    for r in dp:                                                    # 5. day by day
        t = d(r["session_date"])
        if prev is not None:
            pt, days, bal = d(prev["session_date"]), (t - d(prev["session_date"])).days, prev["cash_cents"]
            rr = rate_before(pt) + (float(neg) if bal < 0 else 0.0)
            want = half_up(Decimal(bal) / 100 * Decimal(math.expm1(rr * days / 365))) if bal else 0
            if by_kind_day[("interest", t)] != want:
                P("interest", t, by_kind_day[("interest", t)], want)
            wb = -half_up(Decimal(-prev["shares"]) * Decimal(cents(prev["spot"])) / 100
                          * Decimal(math.expm1(float(borrow) * days / 365))) if prev["shares"] < 0 else 0
            if by_kind_day[("borrow_fee", t)] != wb:
                P("borrow", t, by_kind_day[("borrow_fee", t)], wb)
            start = prev["shares"] + deliveries[("early", t)]
            wd = sum(half_up(Decimal(start) * Decimal(repr(a))) for ex, a in divs if ex == t) if start else 0
            if by_kind_day[("dividend", t)] != wd:
                P("dividend", t, by_kind_day[("dividend", t)], wd)
            if r["shares"] != start + deliveries[t] + hedge_day[t][3] + share_fill_day[t]:
                P("shares", t)
            if r["rate"] != rate_before(t):
                P("rate", t)
        open_at_close = {}
        for lid, ch in lot_changes.items():
            q = sum(dq for day, dq in ch if day <= t)
            if q:
                open_at_close[lid] = q
        in_nav = [m for m in marks_by_day[t] if m["in_nav"]]
        if {m["lot_id"]: m["qty"] for m in in_nav} != open_at_close:
            P("in-NAV lots", t)
        tm = tl = 0.0
        for m in in_nav:
            if m["mark_source"] in ("QUOTE_MID", "ZERO_BID_MID"):
                q = quote[(t, lot_by[m["lot_id"]]["osi_symbol"])]
                b, a = cents(q["bid"]), cents(q["ask"])
                if abs(m["mark_price"] - ((b + a) / 200 if m["mark_source"] == "QUOTE_MID" else a / 200)) > 1e-12:
                    P("quote mark", t, m["lot_id"])
                if abs(m["value_liq_usd"] - m["qty"] * (b if m["qty"] > 0 else a)) > 1e-6:
                    P("liq value", t, m["lot_id"])
            else:
                h = m["h_model"] or 0.0
                side = max(m["mark_price"] - h, 0) if m["qty"] > 0 else m["mark_price"] + h
                if abs(m["value_liq_usd"] - m["qty"] * 100 * side) > 1e-6:
                    P("model liq", t, m["lot_id"])
                if (m["mark_source"] == "STALE_SURFACE") == (t in snap_days):
                    P("stale mark rule", t)
            if abs(m["value_mid_usd"] - m["qty"] * 100 * m["mark_price"]) > 1e-6:
                P("value_mid", t)
            tm += m["value_mid_usd"]; tl += m["value_liq_usd"]
        if abs(r["cash_cents"] / 100 + r["shares"] * close[t] + tm - r["nav_mid"]) > 1e-6:
            P("nav_mid", t, r["cash_cents"] / 100 + r["shares"] * close[t] + tm - r["nav_mid"])
        if abs(r["cash_cents"] / 100 + r["shares"] * close[t] + tl - r["nav_liq"]) > 1e-6:
            P("nav_liq", t)
        if r["n_open_lots"] != len(open_at_close) or r["spot"] != close[t]:
            P("n_open_lots/spot", t)
        prev = r
    return probs, {"flows": len(flows), "sessions": len(dp), "fills": len(fills), "events": len(events),
                   "hedges": len(hedges), "kinds": sorted({f["kind"] for f in flows})}
