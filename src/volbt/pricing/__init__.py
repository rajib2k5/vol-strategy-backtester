"""volbt.pricing: pure pricing functions (milestone 2, the pricing core).

    black76    Black-76 prices and greeks on the forward, and ADR-0006's USD units
    iv         the IV solver: bounds, Newton, then bisection (ADR-0008 §7)
    lattice    the CRR lattice with escrowed discrete dividends; the early-exercise premium
    deam       de-Americanisation: each quote's American IV on the lattice, and its premium there
    dividends  the projected ex-dates and amounts, from dividends already paid (no look-ahead)
    forward    tau, DF, the parity forward of one expiry and its dividend fallback (ADR-0008 §3)
    exercise   ADR-0003's early exercise: the call closed form and the put lattice rule
    smile      the smile and the surface in total variance (ADR-0004's interpolation rules)
    chain      one snapshot priced: forwards, de-Americanised IVs, iv_flags, smiles

Pure functions only: no files, no store, no clock (ADR-0001 §3). volbt.build does the I/O.
May import (volbt): nothing. Third-party: numpy and scipy only (the import test enforces it).
The spot x vol shock revaluation ADR-0001 also lists here is built with the risk layer (M5).
"""
