"""Reference series: SPY bars and dividends, the DGS3MO rate, and the VIX and VIX3M indices.

Each source has two halves:

    fetch_*   network. Downloads into work_dir()/raw/<source>/, kept as received, with a
              small .meta.json beside it (URL, time, size, SHA-256). Run by the M1 job only.
    parse_*   no network. Reads a downloaded file into a typed table. Tests use these.

What we found about yfinance 1.7.0 (measured 2026-10-29, docs/milestones/01-data-layer.md):
- `Ticker.history()` and `yf.download()` both default to auto_adjust=True, which rescales
  Open/High/Low/Close for dividends. On 2022-06-17 that prints a SPY close about $20 below
  the price that traded. So we always pass auto_adjust=False, and keep Adj Close only as
  a separate column.
- Prices arrive as float32-rounded values (349.3800048828125 for a made-up 349.38), so we round
  Open/High/Low/Close to cents. Yahoo's Close is split-adjusted; SPY has never split.
- yfinance keeps a cache under ~/.cache by default. We point it inside work_dir() before
  the first request, so nothing is written outside the repo.
"""

from __future__ import annotations

import hashlib
import math
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from volbt import config
from volbt.data.schema import check_cboe_frame, check_fred_frame, check_yfinance_frame
from volbt.data.store import write_json

SPY_TICKER = "SPY"
# ADR-0010 §1: realised-vol models warm up on SPY bars from 2000-01-03.
SPY_START = "2000-01-01"
FRED_DGS3MO_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS3MO"
# The old cdn.cboe.com address answers with a 307 redirect to this one (checked 2026-10-29).
CBOE_URL = "https://cdn-api.cboe.com/api/global/us_indices/daily_prices/{index}_History.csv"
USER_AGENT = "vol-strategy-backtester (learning project)"

# DGS3MO is a 3-month (91-day) bill yield, in percent, on the investment (bond-equivalent)
# basis. ADR-0007 converts it once to a continuous rate.
DGS3MO_DAYS = 91


def r_cc_from_dgs3mo(yield_pct):
    """ADR-0007: r_cc = (365/91) * ln(1 + y/100 * 91/365). DGS3MO = 5.25 gives 0.0521594."""
    y = np.asarray(yield_pct, dtype=float)
    return (365 / DGS3MO_DAYS) * np.log1p(y / 100 * DGS3MO_DAYS / 365)


def _meta_path(path: Path) -> Path:
    return path.with_name(path.name + ".meta.json")


def _record(path: Path, url: str, data: bytes) -> dict:
    meta = {"url": url, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    write_json(meta, _meta_path(path))
    return meta


def download(url: str, dest: Path, timeout: float = 60.0) -> dict:
    """Fetch `url` to `dest` byte for byte (no parsing), and record where it came from."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # follows redirects
        data = response.read()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return _record(dest, url, data)


def fetch_fred_dgs3mo(raw: Path | None = None) -> dict:
    dest = (raw or config.raw_dir()) / "fred" / "DGS3MO.csv"
    return download(FRED_DGS3MO_URL, dest)


def fetch_cboe(index: str, raw: Path | None = None) -> dict:
    """index is "VIX" or "VIX3M" (VIX3M from the same Cboe family is available: see the milestone doc)."""
    dest = (raw or config.raw_dir()) / "cboe" / f"{index}_History.csv"
    return download(CBOE_URL.format(index=index), dest)


def fetch_spy(raw: Path | None = None, end: date | None = None) -> dict:
    """SPY daily bars and dividends from yfinance, UNADJUSTED, saved as CSV."""
    import yfinance as yf  # imported here: only the fetch step needs it

    root = raw or config.raw_dir()
    # Before the first request: keep yfinance's cookie and timezone caches inside the repo.
    cache = config.work_dir() / "cache" / "yfinance"
    cache.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(cache))
    # end is exclusive in yfinance, so the default asks for everything up to yesterday.
    stop = (end or datetime.now(timezone.utc).date()).isoformat()
    history = yf.Ticker(SPY_TICKER).history(start=SPY_START, end=stop, interval="1d",
                                            auto_adjust=False, actions=True, repair=False)
    if history.empty:
        raise RuntimeError("yfinance returned no SPY rows")
    dest = root / "yfinance" / "SPY_daily.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    text = history.to_csv(lineterminator="\n")
    dest.write_text(text, encoding="utf-8", newline="\n")
    return _record(dest, f"yfinance Ticker('SPY').history(start={SPY_START}, end={stop}, "
                         "auto_adjust=False, actions=True)", text.encode("utf-8"))


def parse_spy_csv(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(bars, dividends) from the yfinance CSV.

    bars: date, open, high, low, close (cents, unadjusted), adj_close, volume.
    dividends: ex_date, amount (yfinance books a dividend on its ex-date).
    """
    frame = pd.read_csv(path)
    check_yfinance_frame(frame, str(path))
    # "2022-06-17 00:00:00-04:00": the first 10 characters are the New York trading date.
    dates = pd.to_datetime(frame["Date"].str[:10], format="%Y-%m-%d").dt.date
    bars = pd.DataFrame({
        "date": dates,
        "open": frame["Open"].round(2),
        "high": frame["High"].round(2),
        "low": frame["Low"].round(2),
        "close": frame["Close"].round(2),
        "adj_close": frame["Adj Close"].round(6),
        "volume": frame["Volume"].astype("int64"),
    })
    if bars["date"].duplicated().any():
        raise ValueError(f"{path}: duplicate dates")
    paid = frame["Dividends"] > 0
    dividends = pd.DataFrame({"ex_date": dates[paid], "amount": frame.loc[paid, "Dividends"].round(6)})
    return bars.reset_index(drop=True), dividends.reset_index(drop=True)


def parse_fred_csv(path: Path) -> pd.DataFrame:
    """date, dgs3mo_pct, r_cc. FRED leaves the value empty on bond-market holidays: dropped."""
    frame = pd.read_csv(path, na_values=["", "."])
    check_fred_frame(frame, str(path))
    frame = frame.dropna(subset=["DGS3MO"])
    return pd.DataFrame({
        "date": pd.to_datetime(frame["observation_date"], format="%Y-%m-%d").dt.date,
        "dgs3mo_pct": frame["DGS3MO"].astype(float),
        "r_cc": r_cc_from_dgs3mo(frame["DGS3MO"].astype(float)),
    }).reset_index(drop=True)


def parse_cboe_csv(path: Path) -> pd.DataFrame:
    """date, open, high, low, close from a Cboe index history (MM/DD/YYYY dates)."""
    frame = pd.read_csv(path)
    check_cboe_frame(frame, str(path))
    return pd.DataFrame({
        "date": pd.to_datetime(frame["DATE"], format="%m/%d/%Y").dt.date,
        "open": frame["OPEN"].astype(float),
        "high": frame["HIGH"].astype(float),
        "low": frame["LOW"].astype(float),
        "close": frame["CLOSE"].astype(float),
    }).reset_index(drop=True)


def spy_dividends_pv(ex_dates, amounts, quote_date: date, expiry: date, r_cc: float) -> float:
    """Present value at quote_date of the dividends with ex-date in (quote_date, expiry].

    tau in calendar days / 365 (ADR-0008 §5). Used only by the cross-vendor diagnostic.
    """
    total = 0.0
    for ex_date, amount in zip(ex_dates, amounts):
        if quote_date < ex_date <= expiry:
            total += amount * math.exp(-r_cc * (ex_date - quote_date).days / 365)
    return total
