# Data and licences

The code in this repository is MIT-licensed (see [LICENSE](LICENSE)). **The data is not covered by this repository's MIT licence.** Each source below has its own terms. They are summarised here from the project's records (README, ADR-0009) and each provider's public page, as of 2026-10-29. This is not legal advice: the provider's own page governs, so check it before you redistribute anything.

| Source | Used for | Terms (one line) | Link |
|---|---|---|---|
| OptionsDX, via Kaggle | SPY end-of-day option chains, 2010-2023 (in-sample) | We know of no OptionsDX terms. The Kaggle dataset `dudesurfin/spy-options-eod-volatility-surface-2010-2023` lists `licenseName` MIT (ADR-0009). The OptionsDX terms page, <https://www.optionsdx.com/terms-of-service/>, returned HTTP 404 when checked twice on 2026-10-29 (by the round-3 reviewer and again when this text was fixed), so there is no OptionsDX terms text to quote. This repository commits no OptionsDX quote row, only aggregates and values we derived from the quotes. | [Kaggle dataset](https://www.kaggle.com/datasets/dudesurfin/spy-options-eod-volatility-surface-2010-2023), [OptionsDX](https://www.optionsdx.com/) |
| DoltHub `post-no-preference/options` | SPY option chains, 2019-05-10 to 2026-10-26; its 2024-01-02 to 2026-10-26 is the out-of-sample holdout ([ADR-0010](docs/adr/0010-evaluation-protocol.md)), and its earlier dates overlap OptionsDX's (the cross-vendor checks use 2020-01-06 to 2023-12-29) | CC BY-SA 4.0: credit the source, say what changed, and share what you derive from it under the same licence. | [DoltHub repository](https://www.dolthub.com/repositories/post-no-preference/options), [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) |
| Yahoo Finance, through yfinance | SPY daily bars and dividends | Yahoo's terms of use apply. The yfinance README says "the Yahoo! finance API is intended for personal use only" (<https://github.com/ranaroussi/yfinance>): it says this of the API, not of the data. yfinance is an unofficial open-source client, not affiliated with Yahoo, and intended for research and educational purposes (same README). | [yfinance](https://github.com/ranaroussi/yfinance), [Yahoo terms](https://policies.yahoo.com/us/en/yahoo/terms/product-atos/apiforydn/index.htm) |
| FRED `DGS3MO` | 3-month Treasury constant-maturity rate (risk-free rate) | Public domain as published by the Federal Reserve Board (H.15); FRED asks for a citation. | [FRED series](https://fred.stlouisfed.org/series/DGS3MO) |
| Cboe VIX and VIX3M; SPX and PUT index histories | Index history, for regimes and background statistics | Cboe's website terms (<https://www.cboe.com/terms/>, last updated 2022-11-16, section 2): you may view, print and download one copy of the materials for personal non-commercial use. You may not otherwise copy, store (also in a retrieval system), create a derivative work from, publish or distribute them without Cboe's prior written consent (the clause is set out under "For owner review: Cboe data" below). This repository publishes VIX closes and figures computed from Cboe's VIX, VIX3M, SPX and PUT files, in the files that section lists. | [Cboe VIX historical data](https://www.cboe.com/tradable_products/vix/vix_historical_data/), [Cboe terms](https://www.cboe.com/terms/) |

## What is committed, and what is never

Owner's decision, 2026-10-29 (recorded in `docs/validation/01-ledger.md`): the data the app and the docs need lives in the repository, small and derived. That means the JSON under `app/public/data/`, small tables of counts, shares and quantiles, and real values quoted in the docs.

Never committed: the downloaded vendor files themselves. That covers the raw CSV downloads (`data/raw/`), the OptionsDX/Kaggle Parquet chains, the DoltHub clone and its exports, DuckDB stores and caches. A committed data file stays under about 10 MB and never goes over 50 MB. `tools/licensing/check_tracked_data.py` (run by `tests/test_tracked_data.py`) fails when git would take a raw vendor file or an oversized data file.

## DoltHub-derived figures (CC BY-SA 4.0)

Contains information derived from the DoltHub database `post-no-preference/options` (<https://www.dolthub.com/repositories/post-no-preference/options>), which is licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Changes: we aggregated it into counts, shares and quantiles, and we compared it with OptionsDX. No quote row is reproduced.

**Short form.** A document that quotes DoltHub-derived figures, in its text or in its tables, carries this paragraph directly under its title (the path to this file changes with the document's folder). Its scope is the whole document, not one table:

> **Data notice.** The DoltHub figures in this document (counts, dates, quantiles and summaries, in its text and in its tables) are derived from the DoltHub database `post-no-preference/options` (<https://www.dolthub.com/repositories/post-no-preference/options>), licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), and are shared under the same licence. Changes: we aggregated it into counts, shares and quantiles, compared it with OptionsDX and ran our pricing build on it; no quote row is reproduced. The rest of this repository is MIT. See [DATA.md](DATA.md).

These figures are shared under the same licence, CC BY-SA 4.0. A document that quotes them must carry the notice above, or its short form, next to them. The files that quote DoltHub-derived figures are:

- `app/public/data/data_quality.json`, see [`app/public/data/LICENSE-DATA.md`](app/public/data/LICENSE-DATA.md) for the fields;
- the milestone walkthroughs `docs/milestones/00-foundations.md`, `01-data-layer.md` and `02-pricing-core.md`, each as a whole;
- the validation ledgers `docs/validation/00-design-research-ledger.md`, `00-round2-ledger.md`, `01-ledger.md` and `02-ledger.md`, each as a whole;
- the concept pages `docs/concepts/02-quality-flags-bitmask.md`, `03-put-call-parity-forward-and-spot.md`, `05-sampling-mask.md`, `06-private-dolt-mirror.md`, `09-implied-vol-solving.md`, `10-crr-lattice-and-de-americanisation.md` and `11-smile-in-total-variance.md`, each as a whole;
- the ADRs `docs/adr/0002-fill-model.md`, `0003-expiry-settlement-early-exercise.md`, `0004-mark-to-market.md`, `0008-pricing-inputs.md`, `0009-data-sources-calendar-quality-flags.md` and `0010-evaluation-protocol.md`, each as a whole;
- `docs/prfaq.md` and `LEARNING_LOG.md`, each as a whole;
- the knowledge graph in `docs/architecture/graph/`, which quotes the figures above in its node labels and rationales: `GRAPH_REPORT.md` carries the short form under its title (`graphify` writes that file, so a regenerated report needs the paragraph added again), and `graph.html`, `graph.json` and `graph.svg` are generated and carry no notice in the file, so this list is their notice.

The 23 documents in the list above, `GRAPH_REPORT.md` among them, each carry the short form. The share-alike condition covers those figures, not the code. Everything else in the repository stays MIT. In `data_quality.json`, the OptionsDX-derived numbers are aggregate counts, shares and quantile summaries only: our own measurements, with no OptionsDX quote, price or chain row.

`app/public/data/illustrative_surface.json` is a made-up SSVI surface, not market data, and is MIT like the code.

`app/public/data/surface_frames.json` (milestone 2) is OptionsDX-derived: for four dates it holds implied vols that our pricing build computed from OptionsDX quotes (via the Kaggle dataset above) and read off our smiles on a fixed grid of log-moneyness and tenor. We know of no OptionsDX terms (the OptionsDX row above), so we cannot name the terms these values are shared on; Kaggle lists the dataset under MIT. The file also holds the SPY close and the VIX close of each date. They are not our measurements. The SPY closes are Yahoo Finance values: Yahoo's terms of use apply, and the yfinance README says the Yahoo! finance API is "intended for personal use only" (the Yahoo row). The VIX closes are Cboe values: Cboe's website terms allow personal non-commercial use of one copy and need Cboe's prior written consent to publish or distribute (the Cboe row). See "For owner review: Cboe data" below. The file reproduces no quote, price or chain row, and holds no DoltHub data.

**What the app shows.** The Surface page shows a "Data sources and terms" notice that follows the file's `run.data_source`:

- an OptionsDX file shows the OptionsDX paragraph: the surfaces are computed from OptionsDX end-of-day quotes obtained through the Kaggle dataset, which Kaggle lists under MIT; the numbers are OptionsDX's, so we treat them as vendor data and publish only values derived from them;
- a DoltHub file shows the DoltHub paragraph, then the CC BY-SA 4.0 attribution (the database, the licence, the "Changes" sentence, and that the DoltHub-derived surfaces are shared under the same licence);
- either file then shows where the closes come from: SPY from Yahoo Finance through yfinance, VIX from Cboe's VIX historical data, with the terms of each in this file;
- while the file loads, or if it fails to load, the notice names no vendor.

The Data Quality page shows its own notice. It names the two vendors whose quotes its counts, shares and quantiles come from: OptionsDX (treated as vendor data, only aggregates published) and DoltHub. It then shows the same CC BY-SA 4.0 attribution with the page's own "Changes" sentence. It says nothing about SPY or VIX closes, because it shows none. Both notices end with the line that the data is not covered by this repository's MIT licence and with links to this file and to [`app/public/data/LICENSE-DATA.md`](app/public/data/LICENSE-DATA.md).

## For owner review: Cboe data

**The terms.** Cboe's website terms (<https://www.cboe.com/terms/>, "Last Updated: November 16, 2022", section 2, "Copyrights, Trademarks, Service Marks, And Proprietary Rights") govern the website's materials, which they define to include its text and databases. The clause says:

- you may view, print and download one copy of the materials for your "personal non-commercial use" in connection with Cboe's products and services, provided you keep every copyright, trademark and other notice on them;
- you may not otherwise copy, reproduce, alter, store (on paper or in an electronic retrieval system), license, transmit, display, broadcast, create a derivative work from (the terms give a financial product, service or index as the example), use to verify or correct other data, publish, rent, sublicense, distribute, or otherwise use the materials in whole or in part, without Cboe's prior written consent;
- the exception is a use that counts as fair use under the US Copyright Act of 1976, as amended;
- you ask for consent through Cboe's content-use request form.

This is a close paraphrase, not the clause itself (the page governs; read it at the link). It was read from the page on 2026-10-29, by the round-3 reviewer and again when this text was fixed. We have not established whether the downloadable index files (`VIX_History.csv` and the others) count as materials of the website.

**What this repository does.** It publishes VIX closes (the first table) and figures computed from Cboe's VIX, VIX3M, SPX and PUT daily files (the second table). The repository's records show no written consent from Cboe. A mean, share, correlation or drawdown computed from the closes may be a derivative work in the terms' sense; we have not decided that either way. The owner has not decided what to do about the closes or the computed figures, and nothing has been removed. The lists are the state on 2026-10-29. Together they name 14 files: the 13 of the first table, plus `docs/milestones/01-data-layer.md` from the second (the other four files of the second table are in the first as well).

### VIX closes

Found by searching the files git tracks and the new files git would add (`git ls-files`, and `git ls-files --others --exclude-standard`) for `vix_close` keys, VIX columns in CSV files, and VIX numbers in docs, code comments and tests. A "close" is one VIX level on one date. The count is of distinct values in the file, by the method in the last column.

| File | VIX values it holds | How counted |
|---|---|---|
| `app/public/data/surface_frames.json` | 4 closes: 9.14, 37.32, 82.69, 14.5 | `vix_close` of each of its 4 frames, read with a JSON parser |
| `app/src/test/fixtures/surface_frames.json` (test copy) | 2 closes: 12.47 (the file labels it made-up) and 82.69, the same number as the 2020-03-16 close above | `vix_close` of each of its 2 frames |
| `docs/milestones/02-pricing-core.md` (measured results) | 4 closes: the four above | the numbers on the "surface frames" line, `grep -o` |
| `docs/concepts/00-background.md` | 7 closes to the cent (82.69, 36.45, 23.39, 38.57, 27.71, 45.31, 52.33; 38.57 appears twice), 2 intraday highs (65.73, 60.13), 4 rounded levels ("passed 65 before the open" in Aug-2024 among them) ("about 17" and "about 37" for Feb-2018, "about 17" on 2020-02-21) and 1 range ("11–17" in the week before 5 Feb 2018) | each value searched with `grep -o`; rounded levels read from the lines |
| `docs/validation/00-design-research-ledger.md` | 4 closes to the cent (82.69, 36.45, 45.31, 52.33), 6 rounded levels ("about 23, 39, 28" for 2024-08-02, 08-05, 08-06; "about 17" and "about 37" for Feb-2018; "about 17" for 2020-02-21) | as above |
| `docs/adr/0010-evaluation-protocol.md` | 2 closes (23.39, 38.57), 2 rounded levels ("about 17", "about 37" for 2018-02-05) | as above |
| `docs/milestones/00-foundations.md` | 1 close (38.57) | as above |
| `docs/adr/0002-fill-model.md` | 1 rounded level ("pre-open VIX above 65" in Aug-2024) | read from the line |
| `docs/architecture/graph/graph.json` (the knowledge graph's copy of the docs' text) | the rounded "65" pre-open level of Aug-2024, as in ADR-0002 and `00-background.md` (added after the round-2 review of this list) | read from the line |
| `app/src/lib/contract.ts` (code comments) | 2 closes: 9.14 and 82.69, the minimum and maximum VIX close since 1990 (5 mentions) | `grep -o` |
| `app/src/lib/surfaceFrames.committed.test.ts` | 1 close: 82.69 (2 mentions); the test reads the committed `surface_frames.json` | `grep -o` |
| `app/src/views/SurfacePage.test.tsx` | 2 closes: 12.47 and 82.69, the test copy's values | `grep -o` |
| `tests/test_export_surface.py` | none quoted; it asserts that the `stress` frame's `vix_close` is above 80 and the `calm` frame's below 10 | read from the line |

### Figures computed from Cboe's index files

These are not Cboe closes. They are statistics, shares, correlations, returns and drawdowns that the one-off script `p10_vix.py` (design review, claim 10; the script is not in the repository) and the background doc's own calculations computed from the daily files of VIX, VIX3M, SPX and PUT downloaded on 2026-10-28. Found by searching the docs for the figures; a figure restated in a file the search missed is not listed.

| File | Computed figures it holds | Where |
|---|---|---|
| `docs/concepts/00-background.md` | The SPX/VIX correlation (-0.79); mean VIX 19.43 against realised vol 15.33, the share of days VIX beat realised vol (85.9%; 76.7% in 2020), the mean log premium; mean VIX² minus RV by year; VIX above VIX3M on 7.5% of days; CAGR, volatility and maximum drawdown of PUT (7.28%, 13.78%, -37.09%) and SPX (8.94%, 19.62%, -56.78%); the stress-episode table (SPX and PUT returns and drawdowns, the 2022 VIX mean and VIX/VIX3M count, one-day VIX changes); the Feb-2018, 2022, Aug-2024 and Apr-2025 follow-up figures | lines 53-94, 172-177, 253-289 and 352 |
| `docs/validation/00-design-research-ledger.md` | The same figures again, in the table of "Claim 10" that checks them; the vol-shock shares (1.7%, 2.1%, 1.5% of sessions; 50 of 123 and 29 shocks fire through one arm only) | lines 419-441 and 491-494 |
| `docs/adr/0010-evaluation-protocol.md` | SPX fell 8.49% from its peak (Aug-2024) | line 109 |
| `docs/milestones/01-data-layer.md` | The row count and date range of the VIX3M file (4,304 rows, 2009-09-18 to 2026-10-28) | line 215 |
| `docs/architecture/graph/graph.json` | The SPX/VIX correlation (-0.79), as a node's rationale | one line |

Not VIX closes, so not in the first table: the statistics we computed from the daily Cboe files (they are in the second table), a change in VIX points (ADR-0006), the example thresholds in ADR-0010 (19.99, 20.00, 30.0 to 33.0), and the mean 19.3 that Bondarenko reports, which is cited from the paper. No VIX3M level is quoted outside the invented test files.

Also in the repository, but invented, not Cboe values (`tests/fixtures/README.md`): `tests/fixtures/reference/cboe/VIX_History.csv` and `VIX3M_History.csv`, 19 rows each; the invented VIX tables in `tests/pricing_store.py` and `tests/test_view.py`; and the invented close 13.6 in `tests/test_pricing_build.py`.
