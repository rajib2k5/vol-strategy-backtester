"""OptionsDX SPY end-of-day chains (Kaggle `dudesurfin/spy-options-eod-volatility-surface-2010-2023`).

The files hold one WIDE row per (date, expiry, strike): the call and the put side by side,
33 columns whose names include the square brackets. We check every file's schema against
the pin (volbt.data.schema) before reading a single row, then reshape to LONG rows, one per
contract, with the column names every later step uses (quotes.RAW_COLUMNS).

The reshape is SQL that DuckDB runs straight off the parquet files, so the 9.5 million wide
rows never pass through Python one at a time.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow.parquet as pq

from volbt import config
from volbt.data.schema import check_optionsdx_schema

DATASET_DIR = "spy-eod-2010-2023"


def files(kaggle_dir: Path | None = None) -> list[Path]:
    """The yearly files spy_eod_2010.parquet ... spy_eod_2023.parquet, sorted."""
    folder = (kaggle_dir or config.kaggle_dir()) / DATASET_DIR
    found = sorted(folder.glob("spy_eod_*.parquet"))
    if not found:
        raise FileNotFoundError(f"no spy_eod_*.parquet files in {folder}")
    return found


def check_file(path: Path) -> None:
    """Raise SchemaError unless the file has exactly the 33 pinned columns. Reads only the footer."""
    check_optionsdx_schema(pq.read_schema(path), Path(path).name)


def _side_sql(side: str, sources: str) -> str:
    """One SELECT for the call side ("C") or the put side ("P") of the wide rows."""
    c = side  # the vendor's column prefix is the same letter: [C_BID], [P_BID]
    return f"""
    SELECT
        'optionsdx' AS source,
        CAST(trim("[QUOTE_DATE]") AS DATE) AS vendor_date,
        CAST(trim("[EXPIRE_DATE]") AS DATE) AS expiry,
        "[STRIKE]" AS strike,
        '{side}' AS call_put,
        "[{c}_BID]" AS bid,
        "[{c}_ASK]" AS ask,
        "[{c}_LAST]" AS last,
        "[{c}_VOLUME]" AS volume,
        -- "[C_SIZE]" reads "305 x 270": bid size, then ask size (parses on 100% of rows).
        CAST(split_part("[{c}_SIZE]", ' x ', 1) AS BIGINT) AS bid_size,
        CAST(split_part("[{c}_SIZE]", ' x ', 2) AS BIGINT) AS ask_size,
        "[{c}_IV]" AS vendor_iv,
        "[{c}_DELTA]" AS vendor_delta,
        "[{c}_GAMMA]" AS vendor_gamma,
        "[{c}_VEGA]" AS vendor_vega,
        "[{c}_THETA]" AS vendor_theta,
        "[{c}_RHO]" AS vendor_rho,
        "[UNDERLYING_LAST]" AS underlying_last
    FROM {sources}"""


def long_rows_sql(paths: list[Path]) -> str:
    """SQL for the long rows of every file in `paths`, after checking each file's schema."""
    for path in paths:
        check_file(path)
    listed = ", ".join(f"'{Path(p).as_posix()}'" for p in paths)
    sources = f"read_parquet([{listed}])"
    return f"{_side_sql('C', sources)}\n    UNION ALL\n{_side_sql('P', sources)}"
