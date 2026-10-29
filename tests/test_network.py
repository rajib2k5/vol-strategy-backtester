"""What the outside services really return. Not in the default run: uv run pytest -m network"""

from datetime import date

import pytest

from volbt import config
from volbt.data import reference

pytestmark = pytest.mark.network


def test_yfinance_adjusts_by_default_and_not_with_auto_adjust_false(tmp_path):
    import yfinance as yf

    # The close the build downloaded for that date, read at run time (run build_data.py --fetch first).
    spy_file = config.raw_dir() / "yfinance" / "SPY_daily.csv"
    if not spy_file.exists():
        pytest.skip(f"{spy_file} is not downloaded: run uv run python tools/build_data.py --fetch --no-build")
    bars, _ = reference.parse_spy_csv(spy_file)
    downloaded_close = dict(zip(bars["date"], bars["close"]))

    yf.set_tz_cache_location(str(tmp_path))
    ticker = yf.Ticker("SPY")
    window = dict(start="2022-06-13", end="2022-06-24", actions=True)
    raw = ticker.history(auto_adjust=False, **window)
    adjusted = ticker.history(auto_adjust=True, **window)
    default = ticker.history(**window)
    day = [d.date() for d in raw.index].index(date(2022, 6, 17))
    assert round(float(raw["Close"].iloc[day]), 2) == downloaded_close[date(2022, 6, 17)]   # the price that traded
    assert float(adjusted["Close"].iloc[day]) < float(raw["Close"].iloc[day])   # rescaled for later dividends
    assert default.equals(adjusted)                                     # the default adjusts
    assert (adjusted["Close"] - raw["Adj Close"]).abs().max() < 1e-9    # Adj Close is the adjusted close
    assert float(raw["Dividends"].iloc[day]) > 0                        # 06-17 was an ex-dividend date


def test_cboe_vix3m_is_published(tmp_path):
    reference.fetch_cboe("VIX3M", tmp_path)
    vix3m = reference.parse_cboe_csv(tmp_path / "cboe" / "VIX3M_History.csv")
    assert vix3m["date"].iloc[0] == date(2009, 9, 18) and len(vix3m) > 4000
