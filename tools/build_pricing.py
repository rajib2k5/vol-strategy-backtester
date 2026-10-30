"""Run the M2 pricing build on the built store: expiry_forwards, quote_iv and smile_fits.

Run:  uv run python tools/build_pricing.py [--store DIR] [--source S ...] [--year Y ...] [--workers N] [--force]

Needs the M1 store (uv run python tools/build_data.py). Each (source, year) partition of
option_quotes is priced on its own, in parallel processes, and written as that partition of the
three tables. A partition whose quotes, reference tables and pricing code have not changed since
its last build is skipped, so a second run costs only the summary; --force re-prices everything.

Writes, next to the tables: pricing_summary.json (the headline numbers, read back from the stored
tables; no clock time, so the same tables always give the same bytes), pricing_inputs.json (each
partition's input fingerprint) and pricing_timings.json (wall times). pricing_timings.json is
overwritten by the next build, so a copy named by its finish time is also kept in the logs folder
beside the store (data/logs/pricing_timings_<UTC time>.json for the default store): every build's
timings stay reproducible from a file.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from volbt import build
from volbt.data.store import Store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", type=Path, default=None, help="the store to read and write (default: work_dir()/store)")
    parser.add_argument("--source", action="append", default=None, help="price only this source (repeatable)")
    parser.add_argument("--year", action="append", default=None, help="price only this year (repeatable)")
    parser.add_argument("--workers", type=int, default=max(1, min(10, (os.cpu_count() or 2) // 2)),
                        help="parallel processes, one partition each (default: half the CPUs, at most 10)")
    parser.add_argument("--force", action="store_true", help="re-price partitions whose inputs have not changed")
    args = parser.parse_args(argv)
    store = Store(args.store)
    if not store.has("option_quotes"):
        print(f"error: {store.root} has no option_quotes; build the store first: uv run python tools/build_data.py",
              file=sys.stderr)
        return 1
    build.build_pricing(store, sources=args.source, years=args.year, workers=args.workers, force=args.force)
    for name in (build.SUMMARY_FILE, build.INPUTS_FILE, build.TIMINGS_FILE):
        print("wrote", store.root / name)
    timings = store.root / build.TIMINGS_FILE
    finished = json.loads(timings.read_text(encoding="utf-8"))["finished_at"].replace(":", "")
    kept = store.root.parent / "logs" / f"pricing_timings_{finished}.json"
    kept.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(timings, kept)
    print("kept", kept)
    return 0


if __name__ == "__main__":
    sys.exit(main())
