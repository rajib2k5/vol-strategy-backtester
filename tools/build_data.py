"""Run the milestone-1 data job.

    uv run python tools/build_data.py --fetch            download SPY, DGS3MO, VIX, VIX3M (network)
    uv run python tools/build_data.py --export-dolthub   export DoltHub's SPY rows, read-only
    uv run python tools/build_data.py                    build the store from what is downloaded

Everything is written under work_dir() (the repo's git-ignored data/ folder, or
$VOLBT_WORK_DIR). Vendor sources are only read, from $VOL_DATA_DIR.
"""

from __future__ import annotations

import argparse
import json
import sys

from volbt.data import pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fetch", action="store_true", help="download the reference series first")
    parser.add_argument("--export-dolthub", action="store_true", help="export DoltHub's SPY rows first")
    parser.add_argument("--no-build", action="store_true", help="only fetch or export")
    args = parser.parse_args(argv)
    if args.fetch:
        print(json.dumps(pipeline.fetch_reference(), indent=1))
    if args.export_dolthub:
        print(json.dumps(pipeline.export_dolthub(), indent=1))
    if not args.no_build:
        summary = pipeline.build()
        print(json.dumps({key: summary[key] for key in ("rows", "calendar", "quality_gate")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
