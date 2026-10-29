"""The MarketView protocol: what a strategy or a signal is allowed to see on day t.

This module holds only the PROTOCOL and its two errors. The concrete view lives in
volbt.data.store, because only `data` may touch the store (ADR-0001 §4). Strategies and
signals import this module, never `data`, so the only way they can read market data is
through a view the engine hands them.

    LookAheadError  any read of data dated after the view's as_of date
    SplitError      creating a view whose as_of lies after the end of the run's split

The splits are ADR-0010 §1. A view may look back before its split starts (signals need
history to warm up), but never forward past the split's last date.

THE GUARD IS NOT HERE. This is the one volbt module strategies and signals may import, so any
function or table the guard read through it is something a strategy could rebind (M1 review,
round 2: `volbt.view.exact_date = <a day later>` moved a Tuesday view to Wednesday). The store
(volbt.data.store) therefore checks every date with its own code and its own copy of SPLITS,
and calls nothing in this module. What is here is published for callers:

    SPLITS      read-only (a mapping proxy of tuples): `SPLITS[name] = ...` raises TypeError
    exact_date  the date rule the store applies: only a plain datetime.date passes, rebuilt
                from its year, month and day, so an object with its own comparison operators
                cannot slip past. Rebinding it changes no view.

Standard library only (ADR-0001 table).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from types import MappingProxyType
from typing import Any, Protocol

# ADR-0010 §1: (first date, last date) of each split, both inclusive. A mapping proxy cannot be
# written through, and its values are tuples, so nothing can change a split in place.
# volbt.data.store keeps its own copy (a test requires the two to be equal).
SPLITS: Mapping[str, tuple[date, date]] = MappingProxyType({
    "development": (date(2010, 1, 4), date(2019, 12, 31)),
    "validation": (date(2020, 1, 2), date(2023, 12, 29)),
    "holdout": (date(2024, 1, 2), date(2026, 10, 26)),
})


class LookAheadError(Exception):
    """A read asked for data dated after the view's as_of date."""


class SplitError(Exception):
    """A view was requested for a date after the end of the run's split."""


def exact_date(value: object, what: str) -> date:
    """`value` rebuilt as a plain datetime.date; TypeError for anything else.

    Only an object whose type IS datetime.date is accepted. A subclass could answer `>` with
    whatever it likes (a `__gt__` that always says False would pass the look-ahead check), so
    it is refused, and the accepted value is rebuilt from its year, month and day: the date
    that is checked is the date that reaches the SQL. datetime and pandas.Timestamp (both
    subclasses of date) are refused too, rather than truncated: a time of day, or a time zone,
    would decide which calendar day the truncation lands on. Pass `.date()` explicitly.

    The store applies the same rule with its own copy (volbt.data.store.plain_date).
    """
    if type(value) is not date:
        raise TypeError(f"{what} must be a datetime.date, not {type(value).__module__}.{type(value).__qualname__}"
                        " (pass a plain date: .date() of a datetime or Timestamp)")
    return date(value.year, value.month, value.day)


class MarketView(Protocol):
    """Everything known at the close of `as_of`, and nothing later.

    Every method reads only rows dated on or before `as_of`. A method that takes a date
    raises LookAheadError when that date is after `as_of`. The return values are tables
    (pandas DataFrames in the concrete view); they are typed `Any` here so this module
    stays free of third-party imports.
    """

    @property
    def as_of(self) -> date: ...

    @property
    def split(self) -> str: ...

    def sessions(self) -> list[date]:
        """SPY sessions up to and including as_of."""
        ...

    def chain(self, quote_date: date, source: str = "optionsdx") -> Any:
        """The cleaned option_quotes rows of one source on one session."""
        ...

    def spy_bars(self) -> Any:
        """SPY daily bars (unadjusted) up to and including as_of: date, open, high, low, close, volume.

        No adjusted close: a dividend-adjusted price on day t is scaled by every dividend
        paid AFTER t, so its level would leak the future.
        """
        ...

    def dividends(self) -> Any:
        """SPY dividends with an ex-date on or before as_of: ex_date, amount."""
        ...

    def rates(self) -> Any:
        """FRED DGS3MO and its continuous rate, up to and including as_of."""
        ...

    def vix(self) -> Any:
        """Cboe VIX daily history up to and including as_of."""
        ...
