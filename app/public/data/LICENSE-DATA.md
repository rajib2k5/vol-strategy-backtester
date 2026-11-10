# Licence of the data in this folder

The full list of data sources, their terms and what is committed is in [`DATA.md`](../../../DATA.md) at the root of the repository. This page is the notice that sits next to the data.

## `data_quality.json`: partly DoltHub-derived, CC BY-SA 4.0

Attribution: contains information derived from the DoltHub database `post-no-preference/options` (<https://www.dolthub.com/repositories/post-no-preference/options>), licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Changes: we aggregated it into counts, shares and quantiles and compared it with another vendor's chains. No quote row is reproduced.

These fields are DoltHub-derived, and are shared under CC BY-SA 4.0:

- `flags_by_year`: the rows where `source` is `dolthub` (their `rows`, `counts` and `shares`);
- `sources`: the `dolthub` row;
- `calendar`: the rows where `source` is `dolthub`;
- `gate.thresholds`: the rows where `source` is `dolthub` (the `worst` values);
- `cross_vendor`: all of it, because it compares DoltHub with OptionsDX (`distributions`, `within_thresholds`, `by_year`).

The OptionsDX-derived numbers in the file (the rows where `source` is `optionsdx`, and the OptionsDX side of `cross_vendor`) are aggregate counts, shares and quantile summaries only: our own measurements, with no OptionsDX quote, price or chain row.

The rest of the file (the flag names and descriptions, the labels, the gate limits and the envelope) is our own text and is MIT.

## `surface_frames.json`: OptionsDX-derived, with Yahoo Finance and Cboe values

- **The implied vols** (`iv`, `atm_iv_30d`, `quoted_share`, `cell_flags`, `expiries_used`) were computed by our pricing build from OptionsDX end-of-day SPY option quotes, obtained through the Kaggle dataset `dudesurfin/spy-options-eod-volatility-surface-2010-2023` (<https://www.kaggle.com/datasets/dudesurfin/spy-options-eod-volatility-surface-2010-2023>). Kaggle lists that dataset under the MIT licence. We know of no OptionsDX terms: <https://www.optionsdx.com/terms-of-service/> returned HTTP 404 when checked on 2026-10-29. The numbers are OptionsDX's own, so we treat the quotes as vendor data as a precaution: the file reproduces no quote, price or chain row, only values derived from them on our grid. We cannot name the terms these derived values are shared on (DATA.md, the OptionsDX row).
- **`spot`** is the SPY close of each date: a Yahoo Finance value, obtained through yfinance and covered by Yahoo's terms of use (<https://policies.yahoo.com/us/en/yahoo/terms/product-atos/apiforydn/index.htm>). The yfinance README says the Yahoo! finance API is "intended for personal use only" (<https://github.com/ranaroussi/yfinance>). It is not our measurement.
- **`vix_close`** is the Cboe VIX close of each date: a Cboe value (<https://www.cboe.com/tradable_products/vix/vix_historical_data/>). It is not our measurement. Cboe's website terms (<https://www.cboe.com/terms/>, last updated 2022-11-16) allow you to view, print and download one copy of the materials for personal non-commercial use, and bar copying, storing in a retrieval system, creating a derivative work, publishing or distributing them without Cboe's prior written consent. This file publishes these closes. The owner has not decided what to do about that: see "For owner review: Cboe data" in [`DATA.md`](../../../DATA.md), which sets out the clause and lists every file that carries VIX values or figures computed from Cboe's index files.
- It holds no DoltHub data.

The data is not covered by this repository's MIT licence.

## `blotter.json` and `positions_timeline.json`: OptionsDX-derived

Both files hold the trades of one diagnostic run of the milestone-3 reference strategy on the development split (OptionsDX SPY option chains, 2010-01-04 to 2019-12-31). They exercise the engine and are not a strategy result. They hold no P&L, NAV, return or Sharpe ratio.

- **`blotter.json`** has 477 fills and 1 expiry event. Each fill carries the contract (OSI symbol), the signed quantity, the fill `price`, the `mid` and `half_spread` of that contract's quote on the fill date, the fees, the fill source and the intent. At the default k = 1 a fill is at the bid (a sale) or the ask (a purchase), so for a quote fill `price`, `mid` and `half_spread` read back that contract's OptionsDX bid and ask on that date. That is 469 contract-day quotes, to 4 decimals. The other 8 fills are surface fills, whose `mid` and `half_spread` are our model's. They were produced by our engine from OptionsDX end-of-day quotes obtained through the Kaggle dataset `dudesurfin/spy-options-eod-volatility-surface-2010-2023`. Kaggle lists that dataset under the MIT licence. We know of no OptionsDX terms (<https://www.optionsdx.com/terms-of-service/> returned HTTP 404 when checked on 2026-10-29), so we treat the quotes as vendor data as a precaution and publish only these few, which the app's Blotter page needs (DATA.md, the OptionsDX row, and the entry for these two files).
- **`positions_timeline.json`** has the 120 positions (structure, opened and closed dates, legs with OSI symbol and ratio, exit reason) and the count of open positions on each of the run's 2,516 session dates. The positions and counts are our own engine output. The OSI symbols name contracts, which are public terms, and no price appears in this file.
- Neither file holds a SPY close, a VIX value or any DoltHub data.
- **The test fixtures are made up.** The files of the same names under `app/src/test/fixtures/` describe an invented run of 4 straddles and are labelled so.

The data is not covered by this repository's MIT licence.

The owner's decision of 2026-10-29 keeps the real data the app and docs need in the repository, results and series built from the OptionsDX/Kaggle option chains included (DATA.md, "What is committed, and what is never").

## The other files here

- `illustrative_surface.json`: a made-up SSVI surface, not market data. MIT, like the rest of the repository.
- `manifest.json`: lists the datasets above. MIT.

The rest of the repository is MIT, see [`LICENSE`](../../../LICENSE).
