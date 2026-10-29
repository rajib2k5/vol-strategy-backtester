"""volbt.pricing: pure pricing functions. EMPTY until milestone 2 (the pricing core).

M2 fills it with: Black-76 prices and greeks on a parity forward, the IV solver (Newton, then
bisection), the parity forward itself, the CRR lattice (de-Americanisation, ADR-0008; early
exercise, ADR-0003), smile build and interpolation, and the spot x vol shock revaluation.

Pure functions only: no files, no store, no clock (ADR-0001 §3). volbt.build does the I/O.
May import (volbt): nothing. Third-party: numpy and scipy only (the import test enforces it).
"""
