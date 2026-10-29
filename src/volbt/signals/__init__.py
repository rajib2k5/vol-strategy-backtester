"""volbt.signals: realised-vol estimators, HAR/GARCH forecasts, IV30 and the signal definitions.
EMPTY until milestone 4 (strategies and the VRP signal).

Every signal is causal: computed inside the daily loop from a MarketView(as_of = t), refitted
monthly on data up to t only (ADR-0001 §2). Signals never see the store.
May import (volbt): pricing, view. The import test also bans sys.modules, getattr/setattr with
a name, vars(), globals() and private-attribute reads here: each is a way round the allow-list.
"""
