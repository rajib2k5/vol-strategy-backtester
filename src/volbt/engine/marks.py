"""One mark per lot per session (ADR-0004), its greeks, and the two NAVs.

The rule table, the first that applies (ADR-0004 Decision; D4, D11 and M2's amendments):

    0  INTRINSIC      the contract settled today: a row at max(S_set - K, 0) or max(K - S_set, 0), kept
                      OUT of NAV (the delivered shares and the cash are in it; decision D11, for M6's bridge)
    1  QUOTE_MID      0 < bid <= ask, not STALE, not CROSSED: (bid + ask) / 2
    2  ZERO_BID_MID   bid = 0 < ask: ask / 2, still the mid
    3  SURFACE_MODEL  crossed, one-sided, stale or missing, on a session with a surface; and EVERY lot in
                      surface mode (decision D4: the S run of ADR-0009 §4 then measures model-marking alone)
    4  STALE_SURFACE  no snapshot today: the previous surface's IV at the same log-moneyness, re-priced at
                      today's spot and forward

A model mark (rules 3 and 4) is the CRR AMERICAN price at the surface IV, N = 500, at every |k|
(ADR-0004 rule 3 and ADR-0008 §8 as amended in M2, decision E8): the surface is European-equivalent, so
Black-76 at a surface IV would leave out the early-exercise premium (ADR-0008 test 9: 6.9574, not 6.8162).
Never a carried last mid.

Greeks are our own Black-76 at the mark IV, never the vendor's (ADR-0004; M2 amendment 1 as fixed in round
2): an in_smile quote uses its own IV; an ITM quote and any quote not in the smile use surface_iv at its
log-moneyness (GREEKS_OTM_IV), and an OTM quote whose IV could not be solved keeps its mid as the mark and
takes the surface IV for its greeks (IV_FAIL). Model marks use the IV they were priced at.

NAV_mid = cash + shares S + sum qty 100 mark. NAV_liq values longs at the bid and shorts at the ask, and a
lot with no valid side at its model price -/+ h_model (ADR-0004 test 2: a zero-bid long counts 0, a short
its ask). share_nav_model_marked is the share of GROSS option value marked by rules 3 or 4; a share above
20% makes the day DEGRADED.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from volbt.data import flags as quality
from volbt.engine import fills, surface as surf
from volbt.pricing import black76, lattice

DAYS_PER_YEAR = 365
MULTIPLIER = 100


@dataclass
class Quote:
    bid: float | None
    ask: float | None
    flags: int | None
    volume: float | None
    log_moneyness: float | None
    is_otm: bool | None
    in_smile: bool | None
    iv: float | None
    iv_flags: int | None


def model_prices(rows: list[dict], spot: float, rate: float, steps: int) -> np.ndarray:
    """CRR American prices at each row's sigma, all in one lattice call (rows: strike, tau, sigma, right, divs)."""
    if not rows:
        return np.zeros(0)
    width = max((len(r["div_times"]) for r in rows), default=0)
    times = np.zeros((len(rows), width))
    amounts = np.zeros((len(rows), width))
    for i, row in enumerate(rows):
        times[i, :len(row["div_times"])] = row["div_times"]
        amounts[i, :len(row["div_amounts"])] = row["div_amounts"]
    result = lattice.crr(spot, np.array([r["strike"] for r in rows]), np.array([r["tau"] for r in rows]), rate,
                         np.array([r["sigma"] for r in rows]), np.array([r["right"] == "C" for r in rows]),
                         times if width else None, amounts if width else None, steps)
    return result["price"]


def mark_lots(lots, session, spot: float, rate: float, quotes: dict, surface, cfg, has_snapshot: bool,
              previous: dict, atm_change: float | None, spot_change: float | None) -> list[dict]:
    """Rows of position_marks for every open lot (rules 1-4), in lot_id order. `previous`: lot_id -> mark."""
    model_mode = cfg.execution_mode == "surface"
    rows = []
    model_rows = []
    for lot in lots:
        tau = (lot.expiry - session).days / DAYS_PER_YEAR
        quote = quotes.get(lot.osi_symbol) if has_snapshot else None
        bid_c, ask_c = (fills.to_cents(quote.bid), fills.to_cents(quote.ask)) if quote else (None, None)
        state = fills.quote_state(bid_c, ask_c, quote.flags if quote else None)
        row = {"lot": lot, "tau": tau, "quote": quote, "state": state, "bid_c": bid_c, "ask_c": ask_c,
               "mark_flags": 0, "strike": lot.strike, "right": lot.right}
        if surface is not None:
            forward, forward_flags = surface.forward(lot.expiry)
        else:
            forward, forward_flags = float("nan"), 0
        row["forward"] = forward
        row["mark_flags"] |= forward_flags
        k = float(np.log(lot.strike / forward)) if np.isfinite(forward) else float("nan")
        row["k"] = k
        if not has_snapshot:
            source = "STALE_SURFACE"
        elif model_mode or state == fills.NO_QUOTE:
            source = "SURFACE_MODEL"
        elif state == fills.ZERO_BID:
            source = "ZERO_BID_MID"
        else:
            source = "QUOTE_MID"
        row["mark_source"] = source
        if source in ("SURFACE_MODEL", "STALE_SURFACE"):
            if surface is None or not surface.usable:
                raise ValueError(f"{session}: lot {lot.lot_id} ({lot.osi_symbol}) needs a model mark and there is "
                                 "no usable surface (no smile with 5+ nodes on this or an earlier snapshot)")
            sigma, bits = surface.iv(lot.expiry, k)
            row["sigma"] = float(sigma[0])
            row["mark_flags"] |= int(bits[0])
            times, amounts = surface.schedule(lot.expiry)
            row["div_times"], row["div_amounts"] = times, amounts
            model_rows.append(row)
        else:
            row["mark"] = (bid_c + ask_c) / 200 if source == "QUOTE_MID" else ask_c / 200
            if quote.in_smile and quote.iv is not None and np.isfinite(quote.iv):
                row["sigma"] = float(quote.iv)
            else:
                if surface is None or not surface.usable:
                    row["sigma"] = float("nan")
                else:
                    sigma, bits = surface.iv(lot.expiry, quote.log_moneyness if quote.log_moneyness is not None else k)
                    row["sigma"] = float(sigma[0])
                    row["mark_flags"] |= int(bits[0])
                row["mark_flags"] |= surf.GREEKS_OTM_IV
                if quote.is_otm and quote.iv_flags is not None and quote.iv_flags & quality.IV_FAIL:
                    row["mark_flags"] |= surf.IV_FAIL
        rows.append(row)
    prices = model_prices(model_rows, spot, rate, cfg.exercise_tree_steps)
    for row, price in zip(model_rows, prices):
        row["mark"] = float(price)
    out = []
    for row in rows:
        lot = row["lot"]
        sigma, mark = row["sigma"], row["mark"]
        if np.isfinite(sigma) and np.isfinite(row["forward"]):
            g = black76.greeks_usd(lot.qty, spot, row["forward"], lot.strike, row["tau"], rate, sigma, lot.right == "C")
            greeks = {name: float(g[name]) for name in ("delta_shares", "gamma_1pct_usd", "vega_1vol_usd", "theta_1d_usd")}
        else:
            greeks = {name: float("nan") for name in ("delta_shares", "gamma_1pct_usd", "vega_1vol_usd", "theta_1d_usd")}
        value_mid = lot.qty * MULTIPLIER * mark
        model = row["mark_source"] in ("SURFACE_MODEL", "STALE_SURFACE")
        h = None
        if model:
            h, _ = surface.h_model(lot.expiry, row["k"], cfg.h_model_band)
            side_price = mark - (h or 0.0) if lot.qty > 0 else mark + (h or 0.0)
            side_price = max(side_price, 0.0)
        else:
            side_price = row["bid_c"] / 100 if lot.qty > 0 else row["ask_c"] / 100
        prev = previous.get(lot.lot_id)
        if (prev is not None and prev > 0 and abs(mark / prev - 1) > cfg.mark_jump_move and spot_change is not None
                and abs(spot_change) < cfg.mark_jump_spot and atm_change is not None
                and abs(atm_change) < cfg.mark_jump_atm_vol):
            row["mark_flags"] |= surf.MARK_JUMP
        quote = row["quote"]
        out.append({"session_date": session, "lot_id": lot.lot_id, "qty": lot.qty, "mark_price": mark,
                    "mark_iv": sigma if np.isfinite(sigma) else None, "mark_source": row["mark_source"],
                    "quality_flags": quote.flags if quote else None,
                    "bid": quote.bid if quote else None, "ask": quote.ask if quote else None,
                    "value_mid_usd": value_mid, "value_liq_usd": lot.qty * MULTIPLIER * side_price,
                    "in_nav": True, "h_model": h, "spot": spot, "forward": row["forward"], "tau_years": row["tau"],
                    "log_moneyness": row["k"], **greeks, "pnl_residual_usd": None, "mark_flags": row["mark_flags"]})
    return out


def intrinsic_row(lot, qty: int, session, settle_price: float, spot: float) -> dict:
    """Rule 0: the settled lot's INTRINSIC row, out of NAV (D11)."""
    value = max(settle_price - lot.strike, 0.0) if lot.right == "C" else max(lot.strike - settle_price, 0.0)
    nan = float("nan")
    return {"session_date": session, "lot_id": lot.lot_id, "qty": qty, "mark_price": value, "mark_iv": None,
            "mark_source": "INTRINSIC", "quality_flags": None, "bid": None, "ask": None,
            "value_mid_usd": qty * MULTIPLIER * value, "value_liq_usd": qty * MULTIPLIER * value, "in_nav": False,
            "h_model": None, "spot": spot, "forward": settle_price, "tau_years": 0.0,
            "log_moneyness": nan, "delta_shares": nan, "gamma_1pct_usd": nan, "vega_1vol_usd": nan,
            "theta_1d_usd": nan, "pnl_residual_usd": None, "mark_flags": 0}


def nav(cash_cents: int, shares: int, spot: float, values) -> float:
    """cash + shares S + the sum of the lots' values, the sum taken in lot_id order by NumPy (ADR-0001 §7)."""
    total = float(np.sum(np.asarray(values, dtype=float))) if len(values) else 0.0
    return cash_cents / 100 + shares * spot + total


def model_share(rows: list[dict]) -> tuple[float, float, float]:
    """(gross option value, gross model-marked value, share) over the rows in NAV (rules 3 and 4 / all)."""
    gross = np.asarray([abs(r["value_mid_usd"]) for r in rows if r["in_nav"]], dtype=float)
    model = np.asarray([abs(r["value_mid_usd"]) for r in rows
                        if r["in_nav"] and r["mark_source"] in ("SURFACE_MODEL", "STALE_SURFACE")], dtype=float)
    g, m = float(gross.sum()) if gross.size else 0.0, float(model.sum()) if model.size else 0.0
    return g, m, (m / g if g > 0 else 0.0)


def mark_quality(gross: float, model: float, cfg) -> str:
    """DEGRADED when the model-marked share of gross option value is ABOVE degraded_share (20%): compared as
    model x den > num x gross, so exactly 20% is OK (in floats 0.2 > Fraction(1, 5) is True: 0.2 is 0.2000...0111)."""
    share = cfg.degraded_share
    return "DEGRADED" if model * share.denominator > share.numerator * gross else "OK"
