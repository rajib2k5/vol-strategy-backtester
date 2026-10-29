"""volbt.data: loading, cleaning, flagging and storing market data (milestone 1).

Only this package touches files and the store (ADR-0001 §4). Its modules, in the order data
flows through them:

    schema      the pinned vendor schemas, and the checks that refuse anything else
    optionsdx   the OptionsDX (Kaggle) parquet files: schema check, wide -> long rows
    dolthub     DoltHub, queried in our private mirror of the shared clone, never the clone itself
    reference   SPY bars and dividends (yfinance), DGS3MO (FRED), VIX and VIX3M (Cboe)
    calendar    sessions from SPY bars; rows dated on a non-session are dropped
    osi         the OSI option symbol, e.g. "SPY   240315C00450000"
    flags       the 13-bit quality_flags mask
    quotes      the clean long table option_quotes, with its flags
    quality     the quality report and the quality gate
    mask        the DoltHub sampling mask (chain_mask = dolthub / dolthub_daily)
    crossvendor the OptionsDX-vs-DoltHub check: 30-day ATM IV and parity-implied spot
    store       parquet + DuckDB, and the concrete MarketView
    pipeline    the M1 job that runs all of the above

May import (volbt): config, view. Nothing else.
"""
