"""Reference series: parsing the downloaded files, and how the fetchers call the outside world.

No test here touches the network: the fetchers are given a fake urlopen or a fake yfinance.
The files in tests/fixtures/reference/ are SYNTHETIC (tools/make_fixtures.py): the real download's
header, date format and column types, with made-up values.
"""

import sys
import types
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from volbt import config
from volbt.data import reference

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "reference"


def test_spy_closes_are_unadjusted_cents_and_the_dividend_is_on_its_ex_date():
    bars, dividends = reference.parse_spy_csv(FIXTURES / "yfinance" / "SPY_daily.csv")
    close = dict(zip(bars["date"], bars["close"]))
    # 349.3800048828125 in the file: the float32 rounding of 349.38 (a made-up close).
    assert close[date(2022, 6, 17)] == 349.38
    assert list(dividends.itertuples(index=False, name=None)) == [(date(2022, 6, 17), 1.249)]
    assert (bars["adj_close"] < bars["close"]).all()   # adjusted for later dividends, kept apart


def test_a_file_fetched_with_auto_adjust_is_refused(tmp_path):
    adjusted = tmp_path / "adj.csv"
    adjusted.write_text("Date,Open,High,Low,Close,Volume,Dividends,Stock Splits\n"
                        "2022-06-17 00:00:00-04:00,1,1,1,331.27,1,1.249,0\n")
    with pytest.raises(ValueError, match="auto_adjust=False"):
        reference.parse_spy_csv(adjusted)


@pytest.mark.parametrize("yield_pct, r_cc", [(5.25, 0.0521594), (0.05, 0.000500)])
def test_dgs3mo_to_a_continuous_rate(yield_pct, r_cc):
    # ADR-0008 test 1 (and ADR-0007): r_cc = (365/91) ln(1 + y/100 * 91/365).
    assert float(reference.r_cc_from_dgs3mo(yield_pct)) == pytest.approx(r_cc, abs=5e-8)


def test_fred_parses_and_drops_holidays(tmp_path):
    rates = reference.parse_fred_csv(FIXTURES / "fred" / "DGS3MO.csv")
    assert len(rates) == 19 and rates["date"].iloc[0] == date(2022, 1, 3)
    holiday = tmp_path / "f.csv"
    holiday.write_text("observation_date,DGS3MO\n2022-01-17,\n2022-01-18,0.10\n")
    assert list(reference.parse_fred_csv(holiday)["date"]) == [date(2022, 1, 18)]


def test_cboe_dates_are_us_format():
    vix = reference.parse_cboe_csv(FIXTURES / "cboe" / "VIX_History.csv")
    vix3m = reference.parse_cboe_csv(FIXTURES / "cboe" / "VIX3M_History.csv")
    assert vix["date"].iloc[0] == date(2022, 1, 3) and len(vix) == len(vix3m) == 19
    assert (vix3m["close"] > 0).all()


def test_dividend_present_value_counts_only_ex_dates_after_today_and_by_expiry():
    pv = reference.spy_dividends_pv([date(2022, 6, 17), date(2022, 9, 16)], [1.249, 1.318],
                                    date(2022, 6, 16), date(2022, 7, 15), 0.01)
    assert pv == pytest.approx(1.249 * np.exp(-0.01 / 365))
    assert reference.spy_dividends_pv([date(2022, 6, 17)], [1.249], date(2022, 6, 17), date(2022, 7, 15), 0.01) == 0


def test_download_keeps_the_bytes_and_records_them(monkeypatch, tmp_path):
    class Response:
        def __init__(self, body):
            self.body = body

        def read(self):
            return self.body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        return Response(b"observation_date,DGS3MO\n2022-01-03,0.17\n")

    monkeypatch.setattr(reference.urllib.request, "urlopen", fake_urlopen)
    meta = reference.fetch_fred_dgs3mo(tmp_path)
    assert seen["url"] == reference.FRED_DGS3MO_URL
    assert (tmp_path / "fred" / "DGS3MO.csv").read_bytes() == b"observation_date,DGS3MO\n2022-01-03,0.17\n"
    assert meta["bytes"] == 40 and len(meta["sha256"]) == 64
    assert (tmp_path / "fred" / "DGS3MO.csv.meta.json").exists()


def test_fetch_spy_asks_for_unadjusted_prices_and_keeps_its_cache_in_the_work_dir(monkeypatch, tmp_path):
    calls = {}
    raw_csv = (FIXTURES / "yfinance" / "SPY_daily.csv").read_text()

    class Ticker:
        def __init__(self, symbol):
            calls["symbol"] = symbol

        def history(self, **kwargs):
            calls["history"] = kwargs
            frame = pd.read_csv(pd.io.common.StringIO(raw_csv)).set_index("Date")
            return frame

    fake = types.SimpleNamespace(Ticker=Ticker, set_tz_cache_location=lambda path: calls.setdefault("cache", path))
    monkeypatch.setitem(sys.modules, "yfinance", fake)
    monkeypatch.setenv("VOLBT_WORK_DIR", str(tmp_path / "work"))
    reference.fetch_spy(tmp_path / "raw", end=date(2022, 12, 31))
    assert calls["symbol"] == "SPY"
    assert calls["history"]["auto_adjust"] is False and calls["history"]["actions"] is True
    assert calls["history"]["start"] == "2000-01-01" and calls["history"]["end"] == "2022-12-31"
    assert Path(calls["cache"]).is_relative_to(config.work_dir())
    bars, _ = reference.parse_spy_csv(tmp_path / "raw" / "yfinance" / "SPY_daily.csv")
    assert len(bars) == 19
