"""volbt.strategies: structures (straddle, strangle, calendar, vol-arb) and the entry and exit
rules that emit order intents. EMPTY until milestone 4.

A strategy sees the market only through the MarketView the engine hands it.
May import (volbt): pricing, signals, view. Never data: that would bypass the view's look-ahead
guard (ADR-0001 §4). The import test bans the same back doors as in signals.
"""
