"""The M2 pricing build on the REAL store. Not in the default run.

Run after `uv run python tools/build_data.py` and `uv run python tools/build_pricing.py`:

    uv run pytest -m real_data tests/test_real_pricing.py
"""

from datetime import timedelta

import pytest

from volbt import build, config
from volbt.data.store import Store
from volbt.pricing import dividends

pytestmark = pytest.mark.real_data


@pytest.fixture(scope="module")
def store():
    built = Store(config.store_dir())
    if not all(built.has(name) for name in ("option_quotes", *build.PRICING_TABLES)):
        pytest.skip("no priced store: run tools/build_data.py, then tools/build_pricing.py")
    return built


def test_every_real_ex_date_since_2009_is_where_the_rule_puts_it(store):
    # dividends.py projects SPY's ex-dates from the third-Friday rule; check it on every one SPY paid.
    paid = store.read_table("dividends", order_by="ex_date")
    sessions = [d.date() for d in store.read_table("spy_bars", order_by="date")["date"]]
    actual = [d.date() for d in paid["ex_date"] if d.year >= 2009]
    assert len(actual) == 71
    for day in actual:
        assert dividends.projected_ex_dates(day - timedelta(days=40), day, sessions)[-1] == day


def test_quote_iv_has_one_row_per_quote_and_the_forwards_one_per_expiry(store):
    counts = store.query("""
        SELECT (SELECT count(*) FROM option_quotes) AS quotes, (SELECT count(*) FROM quote_iv) AS ivs,
               (SELECT count(DISTINCT (source, quote_date, expiry)) FROM option_quotes) AS expiries,
               (SELECT count(*) FROM expiry_forwards) AS forwards, (SELECT count(*) FROM smile_fits) AS smiles""")
    row = counts.iloc[0]
    assert row["quotes"] == row["ivs"] == 19_022_008
    assert row["expiries"] == row["forwards"] == row["smiles"]
    missing = store.query("""SELECT count(*) AS n FROM option_quotes o
                             ANTI JOIN quote_iv q USING (source, year, quote_date, osi_symbol)""")
    assert missing["n"][0] == 0


def test_almost_every_otm_quote_with_a_mid_has_an_iv(store):
    solve = store.query(f"""SELECT count(*) FILTER (q.iv IS NOT NULL) AS solved, count(*) AS attempted
                            FROM quote_iv q JOIN option_quotes o USING (source, year, quote_date, osi_symbol)
                            WHERE q.is_otm AND q.expiry > q.quote_date AND (o.quality_flags & {build.NO_MID}) = 0
                                  AND o.ask > 0""")
    assert solve["solved"][0] / solve["attempted"][0] > 0.999


def test_an_iv_is_never_solved_for_an_itm_or_expiry_day_quote(store):
    bad = store.query("""SELECT count(*) AS n FROM quote_iv
                         WHERE iv IS NOT NULL AND (NOT is_otm OR expiry = quote_date)""")
    assert bad["n"][0] == 0


def test_the_summary_on_disk_is_the_summary_of_the_tables_on_disk(store):
    import json

    written = json.loads((store.root / build.SUMMARY_FILE).read_text(encoding="utf-8"))
    assert written == build.pricing_summary(store)


def test_every_otm_quote_in_the_smile_has_its_own_premium_and_american_iv(store):
    # D1/D6: an IV is solved only from mid - eep, so every IV has a premium, never NaN (D2). The
    # premium is at the quote's own American IV, except where that IV is not identified (round 2,
    # E3: A flat in sigma), where it is at the partner's and iv_american is null: 3 OptionsDX
    # quotes in the whole build (measured 2026-10-29), each with its premium.
    bad = store.query("""SELECT count(*) AS n FROM quote_iv WHERE iv IS NOT NULL AND (eep IS NULL OR isnan(eep))""")
    assert bad["n"][0] == 0
    partner = store.query("SELECT source, count(*) AS n FROM quote_iv WHERE iv IS NOT NULL AND iv_american IS NULL "
                          "GROUP BY source ORDER BY source")
    assert dict(zip(partner["source"], partner["n"])) == {"optionsdx": 3}
    smile = store.query("SELECT count(*) AS n FROM quote_iv WHERE in_smile AND (iv IS NULL OR NOT is_otm)")
    assert smile["n"][0] == 0


def test_the_solve_rate_over_valid_otm_quotes(store):
    # D6: over the quotes that may enter the smile (valid: bid > 0, not STALE; since round 3, F2, not
    # WIDE either) as well as over every OTM quote with a mid. No WIDE quote is a node.
    rate = store.query(f"""
        SELECT count(*) FILTER (q.in_smile) AS in_smile,
               count(*) FILTER ((o.quality_flags & {build.NOT_SMILE}) = 0 AND o.ask > 0) AS smile_ok,
               count(*) FILTER (q.in_smile AND (o.quality_flags & {build.NOT_SMILE}) <> 0) AS in_smile_not_ok
        FROM quote_iv q JOIN option_quotes o USING (source, year, quote_date, osi_symbol)
        WHERE q.is_otm AND q.expiry > q.quote_date""")
    assert rate["in_smile"][0] / rate["smile_ok"][0] > 0.9999 and rate["in_smile_not_ok"][0] == 0


def test_the_dividend_rule_is_the_best_of_the_four_in_a_no_look_ahead_backtest(store):
    # D4: over SPY's 71 ex-dates since 2009, the projected amount (the same quarter a year earlier
    # times trailing-year growth) has the lowest mean absolute error of the four rules.
    import numpy as np

    paid = store.read_table("dividends", order_by="ex_date")
    days = [d.date() for d in paid["ex_date"]]
    amount = paid["amount"].to_numpy(float)
    errors = {"last": [], "year_ago": [], "trailing_mean": [], "rule": []}
    for i, day in enumerate(days):
        if day.year < 2009:
            continue
        errors["last"].append(abs(amount[i - 1] / amount[i] - 1))
        errors["year_ago"].append(abs(amount[i - 4] / amount[i] - 1))
        errors["trailing_mean"].append(abs(amount[i - 4:i].mean() / amount[i] - 1))
        projected = dividends.projected_amount(days, list(amount), day - timedelta(days=1), day)
        errors["rule"].append(abs(projected / amount[i] - 1))
    mean = {name: float(np.mean(values)) for name, values in errors.items()}
    assert len(errors["rule"]) == 71
    assert mean["rule"] == min(mean.values())
    assert mean["rule"] < 0.07 < mean["trailing_mean"] < mean["year_ago"] < mean["last"]


# The two real snapshots on which the M2 review found that one de-Americanisation pass was not
# equivalent to two (code claim 12: 3.41 bp in a 0-60-day forward on 2019-03-14, 16 flag flips on
# 2023-06-15). The procedure is now one pass by construction: each premium is A - E at the quote's
# own American IV, which does not depend on F. Pinned on the rebuilt store, 2026-10-29
# (uv run python tools/report_m2.py, block "the real snapshots of code claim 12").
SNAPSHOTS = {
    "2019-03-14": {"0-60": (2788, 1323, 0), "61-180": (988, 484, 0), "181+": (2726, 1361, 74)},
    "2023-06-15": {"0-60": (3464, 1728, 0), "61-180": (1260, 630, 0), "181+": (2694, 1347, 0)},
}


@pytest.mark.parametrize("day", sorted(SNAPSHOTS))
def test_the_review_s_real_snapshots(store, day):
    import numpy as np
    import pandas as pd
    from datetime import date as date_type

    from volbt.pricing import lattice

    counts = store.query(f"""SELECT {build.TENOR} AS tenor, count(*) AS quotes, count(iv) AS ivs,
                                    count(*) FILTER (iv_flags & 2 <> 0) AS outliers
                             FROM quote_iv WHERE source = 'optionsdx' AND quote_date = ? AND expiry > quote_date
                             GROUP BY ALL""", [day])
    assert {r.tenor: (r.quotes, r.ivs, r.outliers) for r in counts.itertuples(index=False)} == SNAPSHOTS[day]
    # A fresh pricing of the snapshot is the stored one, bit for bit.
    quote_day = date_type.fromisoformat(day)
    quotes = store.query(f"SELECT {build.QUOTE_COLUMNS} FROM option_quotes WHERE source = 'optionsdx' AND year = ? "
                         "AND quote_date = ? ORDER BY quote_date, osi_symbol", [day[:4], quote_day])
    quotes["quote_date"] = pd.to_datetime(quotes["quote_date"]).dt.date
    quotes["expiry"] = pd.to_datetime(quotes["expiry"]).dt.date
    reference = build.reference_inputs(store)
    fresh = build.price_snapshot(quotes, quote_day, reference)
    stored = store.query("SELECT osi_symbol, iv, eep, iv_american, iv_flags FROM quote_iv WHERE source = 'optionsdx' "
                         "AND quote_date = ? ORDER BY osi_symbol", [quote_day])
    for column in ("iv", "eep", "iv_american"):
        assert np.array_equal(np.asarray(fresh["quote_iv"][column], float), stored[column].to_numpy(float), equal_nan=True)
    assert np.array_equal(np.asarray(fresh["quote_iv"]["iv_flags"]), stored["iv_flags"].to_numpy())
    # Self-consistent: at its stored American IV each OTM quote's lattice American price is its mid,
    # and its stored premium is the lattice's A - E there. No second pass could change either.
    q = pd.DataFrame(fresh["quote_iv"]).assign(strike=quotes["strike"].to_numpy(float),
                                              is_call=(quotes["call_put"] == "C").to_numpy(),
                                              mid=((quotes["bid"] + quotes["ask"]) / 2).to_numpy(float))
    short = q[q["is_otm"] & np.isfinite(q["iv"]) & (pd.to_datetime(q["expiry"]) - pd.Timestamp(quote_day)).dt.days.le(60)]
    expiry = [e for e in short["expiry"]]
    tau = np.array([(e - quote_day).days / 365 for e in expiry])
    schedules = [build.dividends.schedule(reference["ex_dates"], reference["amounts"], quote_day, e, reference["sessions"])
                 for e in expiry]
    width = max(len(t) for t, _ in schedules)
    times, amounts = np.zeros((len(expiry), width)), np.zeros((len(expiry), width))
    for row, (t, a) in enumerate(schedules):
        times[row, :len(t)], amounts[row, :len(a)] = t, a
    spot, rate = float(quotes["spy_close"].iloc[0]), build.rate_on(reference, quote_day)
    sigma = short["iv_american"].to_numpy(float)
    american = lattice.crr(spot, short["strike"].to_numpy(), tau, rate, sigma, short["is_call"].to_numpy(), times, amounts)["price"]
    european = lattice.crr_european(spot, short["strike"].to_numpy(), tau, rate, sigma, short["is_call"].to_numpy(), times, amounts)
    mid = short["mid"].to_numpy()
    assert np.all(np.abs(american - mid) <= np.maximum(1e-8, 1e-7 * mid) + 1e-12)
    assert np.allclose(short["eep"].to_numpy(float), np.maximum(american - european, 0), rtol=0, atol=1e-12)
