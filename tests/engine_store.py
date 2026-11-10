"""A made-up store for the engine tests (not a test file: pytest does not collect it).

Made-up values only. About 80 sessions from 2023-01-03 to 2023-04-28, SPY bars to 2023-06-30 (the
calendar the engine may read ahead, decision D3), DGS3MO rising from 4.40% to 5.00%, and:

    expiries   monthlies 2023-02-17, 03-17, 04-21, 05-19 and weeklies 03-10, 03-24 (15 strikes each,
               5 apart around 400), every quote Black-76 at a skewed smile on the true carry forward,
               with a 2-cent spread (bid = mid - 0.01, ask = mid + 0.01, in cents)
    dividends  2022-03-18 1.212, 06-17 1.313, 09-16 1.414, 12-16 1.818 and 2023-03-17 1.616: fewer than 8
               are paid by 2023-03-16, so the projection there is the last paid amount, 1.818, while 1.616 is
               booked on the ex-date (so a test can tell the projected amount from the actual one)
    scripted   no snapshot on MISSING_SNAPSHOT (a session with bars but no quotes); a -8% close-to-close
               gap on GAP_DATE; volumes of 1,000 except where `edits` say otherwise

`make_engine_store(root, edits=..., spot_moves=..., open_factor=...)` lets a test change single quotes (bid, ask,
quality_flags, volume) or spots before the store is written and priced, and give the bars opens that differ
from the closes (open = close x open_factor, to the cent; by default open = close); `built_store(root, ...)`
also runs the M2 pricing build on it, which is what the engine reads.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd

from volbt import build
from volbt.data import flags
from volbt.data.osi import osi_symbol
from volbt.data.store import Store
from volbt.pricing import black76

FIRST_BAR, LAST_BAR = date(2022, 12, 1), date(2023, 6, 30)
FIRST_SNAPSHOT, LAST_SNAPSHOT = date(2023, 1, 3), date(2023, 4, 28)
HOLIDAYS = {date(2022, 12, 26), date(2023, 1, 2), date(2023, 1, 16), date(2023, 2, 20), date(2023, 4, 7),
            date(2023, 5, 29), date(2023, 6, 19)}
MISSING_SNAPSHOT = date(2023, 2, 8)
GAP_DATE = date(2023, 4, 3)
GAP = 0.92
MONTHLIES = [date(2023, 2, 17), date(2023, 3, 17), date(2023, 4, 21), date(2023, 5, 19)]
WEEKLIES = [date(2023, 3, 10), date(2023, 3, 24)]
EXPIRIES = sorted(MONTHLIES + WEEKLIES)
STRIKES = np.arange(365.0, 436.0, 5.0)              # 15 strikes
DIVIDENDS = [(date(2022, 3, 18), 1.212), (date(2022, 6, 17), 1.313), (date(2022, 9, 16), 1.414),
             (date(2022, 12, 16), 1.818), (date(2023, 3, 17), 1.616)]
VOLUME = 1000.0


def sessions() -> list[date]:
    days, day = [], FIRST_BAR
    while day <= LAST_BAR:
        if day.weekday() < 5 and day not in HOLIDAYS:
            days.append(day)
        day += timedelta(days=1)
    return days


def snapshot_sessions() -> list[date]:
    return [d for d in sessions() if FIRST_SNAPSHOT <= d <= LAST_SNAPSHOT and d != MISSING_SNAPSHOT]


def spot_path(moves: dict | None = None) -> dict[date, float]:
    """A seeded close-to-close path from 400, the gap on GAP_DATE, whole cents. `moves`: date -> spot override."""
    rng = np.random.default_rng(2)
    spot, out = 400.0, {}
    for day in sessions():
        if day != FIRST_BAR:
            spot *= math.exp(rng.normal(0.0, 0.008))
            if day == GAP_DATE:
                spot *= GAP
        out[day] = round(spot, 2)
    for day, value in (moves or {}).items():
        out[day] = value
    return out


def rate_pct() -> dict[date, float]:
    days = sessions()
    return {day: round(4.40 + 0.60 * i / (len(days) - 1), 4) for i, day in enumerate(days)}


def r_cc(pct: float) -> float:
    return (365 / 91) * math.log1p(pct / 100 * 91 / 365)


def rate_before(day: date) -> float:
    pct = rate_pct()
    return r_cc([p for d, p in sorted(pct.items()) if d < day][-1])


def smile_sigma(k):
    return 0.18 - 0.25 * np.asarray(k)


def carry_forward(day: date, expiry: date, spot: float, rate: float) -> float:
    tau = (expiry - day).days / 365
    paid = [(d, a) for d, a in DIVIDENDS if day < d <= expiry]
    return spot * math.exp(rate * tau) - sum(a * math.exp(rate * (tau - (d - day).days / 365)) for d, a in paid)


def quotes_on(day: date, spot: float) -> list[dict]:
    rate = rate_before(day)
    rows = []
    for expiry in EXPIRIES:
        if expiry < day or (expiry - day).days > 200:
            continue
        tau = (expiry - day).days / 365
        forward = carry_forward(day, expiry, spot, rate) if tau > 0 else spot
        for right in ("C", "P"):
            if tau > 0:
                mids = black76.price(forward, STRIKES, tau, rate, smile_sigma(np.log(STRIKES / forward)), right == "C")
            else:
                mids = black76.intrinsic(spot, STRIKES, right == "C")
            for strike, mid in zip(STRIKES, mids):
                mid_c = int(round(float(mid) * 100))
                bid_c, ask_c = max(mid_c - 1, 0), max(mid_c + 1, 1)
                rows.append({"source": "optionsdx", "quote_date": day, "osi_symbol": osi_symbol("SPY", expiry, right, strike),
                             "expiry": expiry, "strike": float(strike), "call_put": right, "bid": bid_c / 100,
                             "ask": ask_c / 100, "volume": VOLUME, "spy_close": spot, "underlying_last": spot,
                             "year": day.year})
    return rows


def make_engine_store(root, edits: dict | None = None, spot_moves: dict | None = None,
                      open_factor: float | None = None) -> Store:
    """Write the store. `edits`: {(date, osi_symbol): {"bid": .., "ask": .., "quality_flags": .., "volume": ..,
    "drop": True}}; quality_flags given there are OR-ed into the computed ones."""
    store = Store(root)
    spots = spot_path(spot_moves)
    rows = [row for day in snapshot_sessions() for row in quotes_on(day, spots[day])]
    edits = edits or {}
    kept = []
    for row in rows:
        change = edits.get((row["quote_date"], row["osi_symbol"]), {})
        if change.get("drop"):
            continue
        row = {**row, **{k: v for k, v in change.items() if k in ("bid", "ask", "volume")}}
        bits = int(flags.mid_flags(flags.cents([row["bid"]]), flags.cents([row["ask"]]))[0])
        if row["expiry"] == row["quote_date"]:
            bits |= flags.EXPIRY_DAY
        bits |= int(change.get("quality_flags", 0))
        row["quality_flags"] = bits
        kept.append(row)
    quotes = pd.DataFrame(kept)
    quotes["volume"] = quotes["volume"].astype(float)
    store.write_table("option_quotes", quotes, sort_by=("quote_date", "osi_symbol"), partition_by=("source", "year"))
    days = sessions()
    closes = [spots[d] for d in days]
    opens = closes if open_factor is None else [round(close * open_factor, 2) for close in closes]
    store.write_table("spy_bars", pd.DataFrame({"date": days, "open": opens, "high": closes, "low": closes,
                                                "close": closes, "adj_close": closes, "volume": [1] * len(days)}),
                      sort_by=("date",))
    pct = rate_pct()
    store.write_table("rates", pd.DataFrame({"date": list(pct), "dgs3mo_pct": list(pct.values()),
                                             "r_cc": [r_cc(p) for p in pct.values()]}), sort_by=("date",))
    store.write_table("dividends", pd.DataFrame({"ex_date": [d for d, _ in DIVIDENDS],
                                                 "amount": [a for _, a in DIVIDENDS]}), sort_by=("ex_date",))
    store.write_table("vix", pd.DataFrame({"date": days, "open": [20.0] * len(days), "high": [21.0] * len(days),
                                           "low": [19.0] * len(days), "close": [20.0] * len(days)}), sort_by=("date",))
    return store


def built_store(root, edits: dict | None = None, spot_moves: dict | None = None,
                open_factor: float | None = None) -> Store:
    store = make_engine_store(root, edits, spot_moves, open_factor)
    build.build_pricing(store)
    return store


def symbol(expiry: date, right: str, strike: float) -> str:
    return osi_symbol("SPY", expiry, right, strike)
