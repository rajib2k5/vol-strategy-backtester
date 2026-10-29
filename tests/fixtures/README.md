# Test fixtures

These files are **synthetic**. No vendor data is committed to this repo, and a 20-row excerpt counts. So `tools/make_fixtures.py` writes made-up values. Run it by hand when a fixture must change: `uv run python tools/make_fixtures.py`.

The values are invented. The shape is not. Each file has:

- the vendor's exact column names, in the vendor's order, with the vendor's types (the schema pin in `src/volbt/data/schema.py`);
- the nulls the tests need: a null bid, a null vendor IV, a null volume;
- quote dates on real SPY sessions, plus three closure dates (2022-01-17, 2022-06-20, 2022-07-04) for the calendar tests;
- bids at or below asks, except two crossed legs and the zero-bid legs the flag tests need;
- OSI symbols that read back to the same contract;
- the vendor's text format: `01/03/2022` for Cboe, `2022-01-03 00:00:00-05:00` and float32 noise for yfinance, dolt's CSV layout for DoltHub.

| File | Shape copied from |
|---|---|
| `optionsdx_20rows.parquet` | OptionsDX via Kaggle: 33 columns, one wide row per (date, expiry, strike) |
| `dolthub_describe.csv` | `DESCRIBE option_chain` on DoltHub `post-no-preference/options`, in dolt's CSV layout |
| `dolthub_spy_20rows.csv` | 20 SPY rows from the same table, in dolt's CSV layout |
| `reference/yfinance/SPY_daily.csv` | `yfinance Ticker('SPY').history(auto_adjust=False, actions=True)` |
| `reference/fred/DGS3MO.csv` | FRED `DGS3MO` |
| `reference/cboe/VIX_History.csv`, `VIX3M_History.csv` | Cboe's index history files |

## How the schema pin is tested

- The generator spells the columns out again. It does not import the pin.
- `tests/test_fixtures.py` checks that a fresh run equals the committed files, and that the generated files pass the pin through the real loaders. Rename a column in the generator and that test fails.
- The **real** vendor files are checked against the same pin only by the tests marked `real_data` (`uv run pytest -m real_data`). They also check that no fixture row copies a real vendor row.

The parquet file is committed through a `.gitignore` exception (`!/tests/fixtures/*.parquet`). Every other parquet file stays ignored.
