"""The M3 round-2 code reviewer's look-ahead attack (not a test file: tests/test_engine_round2.py runs it as a script).

A strategy holds its view and numpy. It takes the last smile row of its own session and reads `n` values past
that row's end with np.lib.stride_tricks.as_strided; an auditor then looks for every smile row of the next 30
sessions with at least one node, verbatim, in what it read (an empty row, on its expiry day, matches anything). When every frame was a zero-copy view into the cached year, the attack found
72 future rows at 2015-03-02 (the last dated 2015-04-10). It also counts the symbols held in the Arrow buffers
behind the day's osi_symbol column (1,970,573 behind 3,476 rows then).

    python tests/leak_probe.py <store root> <source> <as_of YYYY-MM-DD> <split> <n>

prints one JSON line. It runs in a fresh interpreter, because memory freed by other code in the same process could
hold future rows by chance and be read past the end of a row that owns its memory.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pyarrow as pa

from volbt.data import store as store_module
from volbt.data.store import Store, YearCache


def main(root: str, source: str, as_of: str, split: str, n: str) -> None:
    store, t0, n = Store(Path(root)), date.fromisoformat(as_of), int(n)
    cache = YearCache(store, source)
    view = store_module.view(t0, split, store, cache)
    # the strategy's side: before anything dated after t0 is read in this process
    row = view.smiles(t0, source=source)["total_var_nodes"].iloc[-1]
    tail = np.array(np.lib.stride_tricks.as_strided(row, shape=(row.size + n,), strides=row.strides)[row.size:])
    symbols = view.quotes(t0, source=source)["osi_symbol"].array.__arrow_array__()
    held = sum(chunk.buffers()[1].size // (8 if pa.types.is_large_string(chunk.type) else 4) - 1
               for chunk in symbols.chunks)
    # the auditor's side
    last = min(date(t0.year, 12, 31), store_module.SPLITS[split][1])
    days = [d for d in store_module.view(last, split, store, cache).sessions() if d > t0][:30]
    hits = []
    for day in days:
        for nodes in store_module.view(day, split, store, cache).smiles(day, source=source)["total_var_nodes"]:
            nodes = np.asarray(nodes)
            if nodes.size and any(np.array_equal(tail[i:i + nodes.size], nodes) for i in range(tail.size - nodes.size + 1)):
                hits.append(day.isoformat())
    print(json.dumps({"future_rows": len(hits), "last": max(hits) if hits else None, "sessions_checked": len(days),
                      "frame_rows": len(symbols), "symbols_in_buffers": held}))


if __name__ == "__main__":
    main(*sys.argv[1:])
