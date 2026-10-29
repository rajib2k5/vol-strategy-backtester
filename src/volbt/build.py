"""volbt.build: the derived-table build. A skeleton in M1; the pricing build itself is M2.

Why a separate module (ADR-0001 §3). `pricing` must stay pure (no files, no store), yet someone
has to read option_quotes, run the pricing functions and store what they return. That is this
module, and it does all of its I/O THROUGH volbt.data: it never opens a file itself.

A build is a list of steps. Each step names the tables it reads (with the order to read them
in, so the input is deterministic), a pure function from those tables to one new table, and the
table it writes. M2 adds the three real steps (`expiry_forwards`, `quote_iv`, `smile_fits`),
whose functions will come from volbt.pricing. Until then they raise NotImplementedError.

May import (volbt): config, data, pricing.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from volbt.data.store import Store


@dataclass(frozen=True)
class Step:
    output: str                                 # the table this step writes
    inputs: tuple[tuple[str, str], ...]         # (table, ORDER BY clause) for each table it reads
    compute: Callable                           # dict[name, DataFrame] -> DataFrame, no I/O
    sort_by: tuple[str, ...]                    # the key the output is sorted by on disk
    partition_by: tuple[str, ...] = ()


def _not_yet(name: str) -> Callable:
    def compute(tables):
        raise NotImplementedError(f"{name} is built in milestone 2 (the pricing core)")
    return compute


# The M2 pricing build, declared so the shape is visible. Not run in M1.
M2_STEPS = (
    Step("expiry_forwards", (("option_quotes", "source, quote_date, osi_symbol"), ("rates", "date"),
                             ("dividends", "ex_date")),
         _not_yet("expiry_forwards"), sort_by=("source", "quote_date", "expiry")),
    Step("quote_iv", (("option_quotes", "source, quote_date, osi_symbol"), ("expiry_forwards", "source, quote_date, expiry")),
         _not_yet("quote_iv"), sort_by=("source", "quote_date", "osi_symbol")),
    Step("smile_fits", (("quote_iv", "source, quote_date, osi_symbol"),),
         _not_yet("smile_fits"), sort_by=("source", "quote_date", "expiry")),
)


def run(steps: tuple[Step, ...], store: Store | None = None) -> dict[str, int]:
    """Run the steps in order. Each reads through the store and writes through the store.

    A later step may read what an earlier one wrote. Returns {table written: rows}.
    """
    target = store or Store()
    written = {}
    for step in steps:
        tables = {name: target.read_table(name, order_by=order) for name, order in step.inputs}
        result = step.compute(tables)
        target.write_table(step.output, result, sort_by=step.sort_by, partition_by=step.partition_by)
        written[step.output] = len(result)
    return written
