"""volbt.engine: the daily loop (ADR-0001 §1), fill model (ADR-0002), marks (ADR-0004), expiry,
settlement and early exercise (ADR-0003), hedging (ADR-0005) and the ledger. EMPTY until
milestone 3.

The engine creates the concrete view with volbt.data.store.view(as_of = t, split = run.split)
and passes it to signals and strategies.
May import (volbt): config, data, pricing, signals, strategies, risk, view.
"""
