"""How many packages an opening order asks for (milestone 4, plan section 5).

    Sizer            the interface: packages(view, book, ctx, legs) -> int >= 1, and params() for the config_hash
    FixedPackages(n) n packages whatever the market: 10 in M4, inside ADR-0002's 7-12 straddles at the default
                     capital, until M5's risk rules size by vega (VegaNotional)

May import (volbt): pricing, signals, view (ADR-0001 §4).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Protocol

PACKAGES = 10


class Sizer(Protocol):
    name: str

    def packages(self, view: Any, book: Any, ctx: Any, legs: tuple) -> int: ...

    def params(self) -> dict: ...


@dataclass(frozen=True)
class FixedPackages:
    n: int = PACKAGES
    name: ClassVar[str] = "FixedPackages"

    def __post_init__(self) -> None:
        if type(self.n) is not int or self.n < 1:
            raise ValueError(f"FixedPackages.n must be an int >= 1, not {self.n!r}")

    def packages(self, view: Any, book: Any, ctx: Any, legs: tuple) -> int:
        return self.n

    def params(self) -> dict:
        return {"name": self.name, "n": self.n}
