"""Write the tiny SYNTHETIC test fixtures in tests/fixtures/. Run by hand, only when a fixture must change.

Run:  uv run python tools/make_fixtures.py

THE RULE: no vendor data is ever committed or pushed. That covers Kaggle/OptionsDX, Cboe, DoltHub
and Yahoo, and a 20-row excerpt counts. So every number below is made up. The files copy the
vendors' SHAPE and nothing else:

    - the same column names, in the same order, with the same types (the schema pin, which the
      loaders check: src/volbt/data/schema.py);
    - the same null patterns, where a test needs a null (a null bid, a null vendor IV, a null volume);
    - quote dates on real SPY sessions, plus the three closure dates the calendar tests need;
    - the same text formats: OptionsDX strings, dolt's CSV, "01/03/2022" for Cboe, yfinance's
      "2022-01-03 00:00:00-05:00" and its float32 noise.

Bids sit at or below asks, except where a test needs a crossed row (two OptionsDX legs) or a
zero bid. The output is deterministic: hand-written rows and closed-form arithmetic, no random
numbers, so a run always writes the same values.

This file does NOT import the pin. It spells the columns out again, so a change to the pin or
to this file shows up as a failing test (tests/test_fixtures.py), not as a silent re-sync. The
real vendor files are checked against the pin only by the tests marked real_data.

    optionsdx_20rows.parquet   20 wide rows, each one case the flags or the calendar look for
    dolthub_describe.csv       `DESCRIBE option_chain`, in dolt's CSV layout
    dolthub_spy_20rows.csv     20 SPY rows of 2022-06-15 in dolt's CSV layout
    reference/...              19 dates of 2022: SPY bars (yfinance layout), DGS3MO, VIX, VIX3M
"""

from __future__ import annotations

import math
import struct
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"

# --- The sessions every file hangs on -----------------------------------------------------------
# (date, SPY close in cents, VIX close, DGS3MO percent). All invented. The dates are real SPY
# sessions of 2022; the three closure dates below are not sessions, on purpose.
SESSIONS = [
    ("2022-01-03", 43127, 18.91, 0.14), ("2022-01-04", 43392, 18.56, 0.13),
    ("2022-01-05", 42815, 20.44, 0.14), ("2022-01-06", 42948, 19.99, 0.18),
    ("2022-01-14", 42163, 23.52, 0.35), ("2022-01-18", 41809, 23.45, 0.22),
    ("2022-03-11", 39674, 28.32, 0.44), ("2022-03-14", 39358, 31.08, 0.53),
    ("2022-03-15", 39921, 27.52, 0.56), ("2022-06-13", 35246, 32.17, 1.68),
    ("2022-06-14", 35083, 30.94, 1.78), ("2022-06-15", 35612, 27.87, 1.64),
    ("2022-06-16", 34795, 31.58, 1.54), ("2022-06-17", 34938, 29.51, 1.68),
    ("2022-06-21", 35564, 28.10, 1.66), ("2022-07-01", 36027, 25.38, 1.75),
    ("2022-07-05", 36109, 25.88, 1.79), ("2022-12-29", 39452, 23.06, 4.37),
    ("2022-12-30", 39386, 22.46, 4.39),
]
CLOSE_CENTS = {day: cents for day, cents, _, _ in SESSIONS}

# Chain rows the vendor dated on a closure carry the previous session's close, as the real ones
# do (the calendar drops them; its diagnostic reports the match). The other dates differ from the close by a few cents.
UNDERLYING_CENTS = {
    "2022-01-03": CLOSE_CENTS["2022-01-03"] + 4, "2022-01-04": CLOSE_CENTS["2022-01-04"] + 1,
    "2022-01-06": CLOSE_CENTS["2022-01-06"] - 2,
    "2022-01-17": CLOSE_CENTS["2022-01-14"],      # MLK Day, a closure: the 01-14 close
    "2022-03-14": CLOSE_CENTS["2022-03-14"] + 3, "2022-06-15": CLOSE_CENTS["2022-06-15"] - 5,
    "2022-06-16": CLOSE_CENTS["2022-06-16"] + 4,
    "2022-06-20": CLOSE_CENTS["2022-06-17"],      # Juneteenth, a closure: the 06-17 close
    "2022-06-21": CLOSE_CENTS["2022-06-21"] - 1,
    "2022-07-04": CLOSE_CENTS["2022-07-01"],      # Independence Day, a closure: the 07-01 close
    "2022-12-30": CLOSE_CENTS["2022-12-30"] + 2,
}
EX_DIVIDEND_DATE = "2022-06-17"
DIVIDEND = 1.249


def ny_offset_hours(day: date) -> int:
    """Hours New York is behind UTC on `day`. Daylight time ran 2022-03-13 to 2022-11-05."""
    return 4 if date(2022, 3, 13) <= day < date(2022, 11, 6) else 5


def sixteen_hundred_unix(day: date) -> int:
    """Unix seconds of 16:00 New York time on `day` (what OptionsDX stamps every row with)."""
    midnight_utc = (day - date(1970, 1, 1)).days * 86400
    return midnight_utc + (16 + ny_offset_hours(day)) * 3600


# --- Black-Scholes, only to make plausible prices and greeks --------------------------------------
def _cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def black_scholes(spot: float, strike: float, years: float, vol: float, rate: float, side: str):
    """(price, delta, gamma, vega per vol point, theta per day, rho per 1%) of a European option."""
    root_t = math.sqrt(years)
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * years) / (vol * root_t)
    d2 = d1 - vol * root_t
    discount = math.exp(-rate * years)
    pdf = math.exp(-0.5 * d1 * d1) / math.sqrt(2.0 * math.pi)
    gamma = pdf / (spot * vol * root_t)
    vega = spot * pdf * root_t / 100
    decay = -spot * pdf * vol / (2 * root_t)
    if side == "C":
        price = spot * _cdf(d1) - strike * discount * _cdf(d2)
        return (price, _cdf(d1), gamma, vega,
                (decay - rate * strike * discount * _cdf(d2)) / 365, strike * years * discount * _cdf(d2) / 100)
    price = strike * discount * _cdf(-d2) - spot * _cdf(-d1)
    return (price, _cdf(d1) - 1, gamma, vega,
            (decay + rate * strike * discount * _cdf(-d2)) / 365, -strike * years * discount * _cdf(-d2) / 100)


# --- OptionsDX: 20 wide rows -----------------------------------------------------------------------
# Own copy of the 33 column names and types, in file order.
OPTIONSDX_SCHEMA = pa.schema([
    ("[QUOTE_UNIXTIME]", pa.int64()), ("[QUOTE_READTIME]", pa.string()), ("[QUOTE_DATE]", pa.string()),
    ("[QUOTE_TIME_HOURS]", pa.float64()), ("[UNDERLYING_LAST]", pa.float64()), ("[EXPIRE_DATE]", pa.string()),
    ("[EXPIRE_UNIX]", pa.int64()), ("[DTE]", pa.float64()),
    ("[C_DELTA]", pa.float64()), ("[C_GAMMA]", pa.float64()), ("[C_VEGA]", pa.float64()),
    ("[C_THETA]", pa.float64()), ("[C_RHO]", pa.float64()), ("[C_IV]", pa.float64()),
    ("[C_VOLUME]", pa.float64()), ("[C_LAST]", pa.float64()), ("[C_SIZE]", pa.string()),
    ("[C_BID]", pa.float64()), ("[C_ASK]", pa.float64()), ("[STRIKE]", pa.float64()),
    ("[P_BID]", pa.float64()), ("[P_ASK]", pa.float64()), ("[P_SIZE]", pa.string()),
    ("[P_LAST]", pa.float64()), ("[P_DELTA]", pa.float64()), ("[P_GAMMA]", pa.float64()),
    ("[P_VEGA]", pa.float64()), ("[P_THETA]", pa.float64()), ("[P_RHO]", pa.float64()),
    ("[P_IV]", pa.float64()), ("[P_VOLUME]", pa.float64()),
    ("[STRIKE_DISTANCE]", pa.float64()), ("[STRIKE_DISTANCE_PCT]", pa.float64()),
])


def leg(bid, ask, last, size, volume, iv) -> dict:
    return {"bid": bid, "ask": ask, "last": last, "size": size, "volume": volume, "iv": iv}


# One entry per wide row: vendor date, expiry, strike, the call leg, the put leg. A leg is
# (bid, ask, last, "bid size x ask size", volume, vendor IV); None is a null in the file.
# The comment says which case the row is for; the flag it must set is in tests/test_flags.py.
OPTIONSDX_ROWS = [
    # 0-4: expiry-day deep in-the-money calls (null IV and volume) with zero-bid puts whose vendor IV is absurd
    ("2022-01-03", "2022-01-03", 390.0, leg(41.22, 42.38, 41.70, "2 x 1", None, None),
     leg(0.00, 0.01, 0.01, "0 x 2471", 0.0, 4.31288)),
    ("2022-01-03", "2022-01-03", 395.0, leg(36.19, 37.40, 36.80, "1 x 1", None, None),
     leg(0.00, 0.01, 0.01, "0 x 2337", 0.0, 4.20877)),
    ("2022-01-03", "2022-01-03", 400.0, leg(31.17, 32.41, 31.20, "1 x 1", None, None),
     leg(0.00, 0.01, 0.01, "0 x 2327", 0.0, 4.05562)),
    ("2022-01-03", "2022-01-03", 405.0, leg(26.14, 27.33, 26.50, "1 x 1", None, None),
     leg(0.00, 0.01, 0.01, "0 x 2327", 0.0, 3.91340)),
    ("2022-01-03", "2022-01-03", 410.0, leg(21.08, 22.36, 21.60, "1 x 1", None, None),
     leg(0.00, 0.01, 0.01, "0 x 2301", 0.0, 3.78215)),
    # 5: a row with every value present; a zero-bid call on the expiry day
    ("2022-01-03", "2022-01-03", 432.0, leg(0.00, 0.01, 0.01, "0 x 1655", 27310.0, 0.02870),
     leg(0.98, 1.66, 1.21, "300 x 300", 1520.0, 0.00420)),
    # 6: a locked call (bid = ask > 0)
    ("2022-01-03", "2022-01-10", 451.0, leg(0.02, 0.02, 0.02, "412 x 655", 188.0, 0.09170),
     leg(19.71, 20.07, 19.85, "50 x 50", 0.0, 0.09540)),
    # 7: a wide call (0.03 / 0.10); a null put volume
    ("2022-01-03", "2022-06-17", 590.0, leg(0.03, 0.10, 0.08, "711 x 1248", 0.0, 0.14310),
     leg(158.77, 161.20, 0.0, "60 x 56", None, 0.20910)),
    # 8: a crossed call (bid above ask); every value present
    ("2022-01-04", "2022-01-05", 434.0, leg(1.20, 1.15, 1.18, "53 x 19", 52418.0, 0.10210),
     leg(1.04, 1.07, 1.05, "39 x 67", 55906.0, 0.08930)),
    # 9: a crossed put; every value present
    ("2022-01-06", "2022-01-07", 430.0, leg(1.02, 1.05, 1.03, "1 x 122", 47318.0, 0.12040),
     leg(1.55, 1.52, 1.54, "18 x 1", 46077.0, 0.11880)),
    # 10: dated on MLK Day (a closure, dropped by the calendar); null bids, asks, last prices and volumes
    ("2022-01-17", "2022-02-14", 380.0, leg(None, None, None, "0 x 0", None, None),
     leg(None, None, None, "0 x 0", None, 0.28740)),
    # 11-14: more expiry-day and next-day deep in-the-money calls with zero-bid puts
    ("2022-03-14", "2022-03-14", 170.0, leg(223.58, 224.69, 0.0, "1 x 1", None, None),
     leg(0.00, 0.01, 0.00, "0 x 1820", None, 4.50210)),
    ("2022-06-15", "2022-06-15", 130.0, leg(226.04, 227.31, 226.80, "1 x 1", 1.0, None),
     leg(0.00, 0.01, 0.01, "0 x 1366", 0.0, 5.34870)),
    ("2022-06-15", "2022-06-15", 131.0, leg(225.07, 226.29, 225.50, "1 x 1", 1.0, None),
     leg(0.00, 0.01, 0.01, "0 x 673", 0.0, 5.30125)),
    ("2022-06-16", "2022-06-17", 90.0, leg(257.95, 261.02, 259.10, "10 x 10", 8.0, None),
     leg(0.00, 0.01, 0.01, "0 x 4510", 1.0, 5.26480)),
    # 15-16: dated on Juneteenth (dropped; 06-17 has no snapshot of its own and stays missing)
    ("2022-06-20", "2022-06-21", 250.0, leg(99.07, 99.74, 0.0, "0 x 0", None, None),
     leg(0.00, 0.01, 0.01, "0 x 0", 0.0, 1.41230)),
    ("2022-06-20", "2022-06-21", 255.0, leg(94.10, 94.79, 0.0, "0 x 0", None, None),
     leg(0.00, 0.01, 0.02, "0 x 0", 0.0, 1.33880)),
    # 17: the same contract as row 15 on the next session: its put quote is unchanged while SPY moved (STALE)
    ("2022-06-21", "2022-06-21", 250.0, leg(105.58, 106.77, 0.0, "300 x 1", None, None),
     leg(0.00, 0.01, 0.01, "0 x 1482", 2.0, 2.16640)),
    # 18: dated on Independence Day (dropped)
    ("2022-07-04", "2022-07-05", 240.0, leg(120.14, 120.81, 0.0, "300 x 300", None, None),
     leg(0.00, 0.01, 0.03, "0 x 3500", 3.0, 1.82750)),
    # 19: the last session of the year, expiry day
    ("2022-12-30", "2022-12-30", 165.0, leg(228.79, 228.93, 229.10, "2 x 2", 1.0, None),
     leg(0.00, 0.01, 0.01, "0 x 6559", 0.0, 6.04430)),
]
GREEK_RATE = 0.01


def optionsdx_row(vendor_date: str, expiry: str, strike: float, call: dict, put: dict) -> dict:
    quote_day, expiry_day = date.fromisoformat(vendor_date), date.fromisoformat(expiry)
    spot = UNDERLYING_CENTS[vendor_date] / 100
    dte = (expiry_day - quote_day).days
    row = {
        "[QUOTE_UNIXTIME]": sixteen_hundred_unix(quote_day), "[QUOTE_READTIME]": f"{vendor_date} 16:00",
        "[QUOTE_DATE]": vendor_date, "[QUOTE_TIME_HOURS]": 16.0, "[UNDERLYING_LAST]": spot,
        "[EXPIRE_DATE]": expiry, "[EXPIRE_UNIX]": sixteen_hundred_unix(expiry_day), "[DTE]": float(dte),
        "[STRIKE]": strike, "[STRIKE_DISTANCE]": round(abs(strike - spot), 1),
        "[STRIKE_DISTANCE_PCT]": round(abs(strike - spot) / spot, 3),
    }
    for side, quote in (("C", call), ("P", put)):
        iv = quote["iv"]
        # Greeks need a sane vol: an absurd vendor IV (4.3) or a missing one gets a plain 20%.
        vol = iv if iv is not None and 0.02 <= iv <= 2.0 else 0.20
        _, delta, gamma, vega, theta, rho = black_scholes(spot, strike, max(dte, 0.1) / 365, vol, GREEK_RATE, side)
        row.update({
            f"[{side}_DELTA]": round(delta, 5), f"[{side}_GAMMA]": round(gamma, 5),
            f"[{side}_VEGA]": round(vega, 5), f"[{side}_THETA]": round(theta, 5), f"[{side}_RHO]": round(rho, 5),
            f"[{side}_IV]": iv, f"[{side}_VOLUME]": quote["volume"], f"[{side}_LAST]": quote["last"],
            f"[{side}_SIZE]": quote["size"], f"[{side}_BID]": quote["bid"], f"[{side}_ASK]": quote["ask"],
        })
    return row


def optionsdx_table() -> pa.Table:
    rows = [optionsdx_row(*spec) for spec in OPTIONSDX_ROWS]
    columns = {field.name: pa.array([row[field.name] for row in rows], type=field.type) for field in OPTIONSDX_SCHEMA}
    return pa.table(columns, schema=OPTIONSDX_SCHEMA)


# --- DoltHub: DESCRIBE and 20 SPY rows of 2022-06-15 -------------------------------------------------
# Own copy of `DESCRIBE option_chain`: (Field, Type, Null, Key).
DOLTHUB_DESCRIBE = [
    ("date", "date", "NO", "PRI"), ("act_symbol", "varchar(64)", "NO", "PRI"),
    ("expiration", "date", "NO", "PRI"), ("strike", "decimal(7,2)", "NO", "PRI"),
    ("call_put", "varchar(64)", "NO", "PRI"), ("bid", "decimal(7,2)", "YES", ""),
    ("ask", "decimal(7,2)", "YES", ""), ("vol", "decimal(5,4)", "YES", ""),
    ("delta", "decimal(5,4)", "YES", ""), ("gamma", "decimal(5,4)", "YES", ""),
    ("theta", "decimal(5,4)", "YES", ""), ("vega", "decimal(5,4)", "YES", ""),
    ("rho", "decimal(5,4)", "YES", ""),
]
DOLTHUB_DATE, DOLTHUB_EXPIRY = "2022-06-15", "2022-06-29"
DOLTHUB_STRIKES = [290, 300, 312, 322, 330, 340, 350, 358, 368, 378]
DOLTHUB_RATE = 0.0175


def dolthub_describe_text() -> str:
    """dolt's CSV layout: a type with a comma is quoted, an empty Key is "", Default is empty, Extra is "".

    Dolt prints the Key of a column outside the primary key as "" (two quotes), and a NULL Default as nothing.
    """
    lines = ["Field,Type,Null,Key,Default,Extra"]
    for name, sql_type, nullable, key in DOLTHUB_DESCRIBE:
        quoted = f'"{sql_type}"' if "," in sql_type else sql_type
        lines.append(f'{name},{quoted},{nullable},{key or chr(34) * 2},,""')
    return "\n".join(lines) + "\n"


def _text(value: float, places: int) -> str:
    """Fixed decimals; adding 0.0 turns a rounded -0.0 into 0.0, so no "-0.0000" appears."""
    return f"{round(value, places) + 0.0:.{places}f}"


def dolthub_rows_text() -> str:
    spot = CLOSE_CENTS[DOLTHUB_DATE] / 100
    years = (date.fromisoformat(DOLTHUB_EXPIRY) - date.fromisoformat(DOLTHUB_DATE)).days / 365
    lines = ["date,act_symbol,expiration,strike,call_put,bid,ask,vol,delta,gamma,theta,vega,rho"]
    for strike in DOLTHUB_STRIKES:
        moneyness = math.log(strike / spot)
        vol = round(0.30 + 1.1 * moneyness**2 - 0.25 * moneyness, 4)     # a smile with a mild skew
        for side, name in (("C", "Call"), ("P", "Put")):
            price, delta, gamma, vega, theta, rho = black_scholes(spot, strike, years, vol, DOLTHUB_RATE, side)
            spread = max(0.01, round(0.012 * price, 2))
            bid = round(price - spread / 2, 2)
            ask = round(bid + spread, 2)
            assert 0 < bid <= ask, (strike, side, bid, ask)
            lines.append(",".join([DOLTHUB_DATE, "SPY", DOLTHUB_EXPIRY, _text(strike, 2), name, _text(bid, 2),
                                   _text(ask, 2), _text(vol, 4), _text(delta, 4), _text(gamma, 4),
                                   _text(theta, 4), _text(vega, 4), _text(rho, 4)]))
    return "\n".join(lines) + "\n"


# --- Reference series (the same 19 dates in every file) ------------------------------------------------
def float32(value: float) -> float:
    """What yfinance prints: a float32 widened to float64, so 349.38 reads 349.3800048828125."""
    return struct.unpack("f", struct.pack("f", value))[0]


def spy_text() -> str:
    lines = ["Date,Open,High,Low,Close,Adj Close,Volume,Dividends,Stock Splits,Capital Gains"]
    for i, (day, close, _, _) in enumerate(SESSIONS):
        opened = close + (-1) ** i * (60 + 23 * (i % 4))
        high = max(opened, close) + 55 + 17 * (i % 3)
        low = min(opened, close) - 48 - 19 * (i % 5)
        # Adjusted for the dividends after the day, so the factor rises towards the present
        # and steps up once the 06-17 ex-date is behind us.
        factor = (0.9420 if day >= EX_DIVIDEND_DATE else 0.9350) + 0.0004 * i
        stamp = f"{day} 00:00:00-0{ny_offset_hours(date.fromisoformat(day))}:00"
        volume = 61_000_000 + 7_300_000 * (i % 6) + 1_137_000 * i
        dividend = DIVIDEND if day == EX_DIVIDEND_DATE else 0.0
        prices = [float32(cents / 100) for cents in (opened, high, low, close)]
        lines.append(",".join([stamp, *(repr(p) for p in prices), repr(float32(close * factor / 100)),
                               str(volume), repr(dividend), "0.0", "0.0"]))
    return "\n".join(lines) + "\n"


def fred_text() -> str:
    lines = ["observation_date,DGS3MO"]
    lines += [f"{day},{percent:.2f}" for day, _, _, percent in SESSIONS]
    return "\n".join(lines) + "\n"


def cboe_text(level: float, slope: float) -> str:
    """A Cboe history: US-style dates and six decimals. VIX3M is the VIX pulled towards a flatter level."""
    lines = ["DATE,OPEN,HIGH,LOW,CLOSE"]
    for i, (day, _, vix, _) in enumerate(SESSIONS):
        close = round(vix * slope + level, 2)
        opened = round(close + (-1) ** i * (0.35 + 0.11 * (i % 4)), 2)
        high = round(max(opened, close) + 0.62 + 0.09 * (i % 5), 2)
        low = round(min(opened, close) - 0.58 - 0.07 * (i % 3), 2)
        year, month, dom = day.split("-")
        lines.append(f"{month}/{dom}/{year},{opened:.6f},{high:.6f},{low:.6f},{close:.6f}")
    return "\n".join(lines) + "\n"


# --- Writing -----------------------------------------------------------------------------------------------
def write_all(folder: Path) -> list[Path]:
    """Write every fixture under `folder`. Returns the paths written, relative to it."""
    texts = {
        "dolthub_describe.csv": dolthub_describe_text(),
        "dolthub_spy_20rows.csv": dolthub_rows_text(),
        "reference/yfinance/SPY_daily.csv": spy_text(),
        "reference/fred/DGS3MO.csv": fred_text(),
        "reference/cboe/VIX_History.csv": cboe_text(level=0.0, slope=1.0),
        "reference/cboe/VIX3M_History.csv": cboe_text(level=7.29, slope=0.79),
    }
    for relative, text in texts.items():
        target = folder / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    pq.write_table(optionsdx_table(), folder / "optionsdx_20rows.parquet")
    return [Path("optionsdx_20rows.parquet"), *(Path(relative) for relative in texts)]


if __name__ == "__main__":
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for written in write_all(FIXTURES):
        print("wrote", written)
