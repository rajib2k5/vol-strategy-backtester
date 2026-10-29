# Data and licences

The code in this repository is MIT-licensed (see [LICENSE](LICENSE)). **The data is not covered by this repository's MIT licence.** Each source below has its own terms. They are summarised here from the project's records (README, ADR-0009) and each provider's public page, as of 2026-10-29. This is not legal advice: the provider's own page governs, so check it before you redistribute anything.

| Source | Used for | Terms (one line) | Link |
|---|---|---|---|
| OptionsDX, via Kaggle | SPY end-of-day option chains, 2010-2023 (in-sample) | The Kaggle dataset `dudesurfin/spy-options-eod-volatility-surface-2010-2023` is listed there under the MIT licence (ADR-0009), but the numbers are OptionsDX's own, so we treat the files as vendor data: never committed, only our aggregates are. | [Kaggle dataset](https://www.kaggle.com/datasets/dudesurfin/spy-options-eod-volatility-surface-2010-2023), [OptionsDX](https://www.optionsdx.com/) |
| DoltHub `post-no-preference/options` | SPY option chains, 2019-2026 (out-of-sample) | CC BY-SA 4.0: credit the source, say what changed, and share what you derive from it under the same licence. | [DoltHub repository](https://www.dolthub.com/repositories/post-no-preference/options), [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) |
| Yahoo Finance, through yfinance | SPY daily bars and dividends | Yahoo's terms of use govern the data; yfinance is an unofficial open-source client intended for research and education. | [yfinance](https://github.com/ranaroussi/yfinance), [Yahoo terms](https://policies.yahoo.com/us/en/yahoo/terms/product-atos/apiforydn/index.htm) |
| FRED `DGS3MO` | 3-month Treasury constant-maturity rate (risk-free rate) | Public domain as published by the Federal Reserve Board (H.15); FRED asks for a citation. | [FRED series](https://fred.stlouisfed.org/series/DGS3MO) |
| Cboe VIX and VIX3M | Index history, for regimes | Cboe's terms: personal, non-commercial use. | [Cboe VIX historical data](https://www.cboe.com/tradable_products/vix/vix_historical_data/) |

## What is committed, and what is never

Owner's decision, 2026-10-29 (recorded in `docs/validation/01-ledger.md`): the data the app and the docs need lives in the repository, small and derived. That means the JSON under `app/public/data/`, small tables of counts, shares and quantiles, and real values quoted in the docs.

Never committed: the downloaded vendor files themselves. That covers the raw CSV downloads (`data/raw/`), the OptionsDX/Kaggle Parquet chains, the DoltHub clone and its exports, DuckDB stores and caches. A committed data file stays under about 10 MB and never goes over 50 MB. `tools/licensing/check_tracked_data.py` (run by `tests/test_tracked_data.py`) fails when git would take a raw vendor file or an oversized data file.

## DoltHub-derived tables (CC BY-SA 4.0)

Contains information derived from the DoltHub database `post-no-preference/options` (<https://www.dolthub.com/repositories/post-no-preference/options>), which is licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Changes: we aggregated it into counts, shares and quantiles, and we compared it with OptionsDX. No quote row is reproduced.

These tables are shared under the same licence, CC BY-SA 4.0, and carry a notice next to them:

- `app/public/data/data_quality.json`, see [`app/public/data/LICENSE-DATA.md`](app/public/data/LICENSE-DATA.md) for the fields;
- the measured-results tables of `docs/milestones/01-data-layer.md`, the data-fact tables of `docs/validation/00-design-research-ledger.md`, and the tables of `docs/validation/00-round2-ledger.md` and `docs/validation/01-ledger.md` that report DoltHub counts, dates and summaries.

The share-alike condition covers those tables, not the code. Everything else in the repository stays MIT. In `data_quality.json`, the OptionsDX-derived numbers are aggregate counts, shares and quantile summaries only: our own measurements, with no OptionsDX quote, price or chain row.

`app/public/data/illustrative_surface.json` is a made-up SSVI surface, not market data, and is MIT like the code.
