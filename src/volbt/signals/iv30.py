"""IV30: the ATM-forward implied vol at 30 calendar days (milestone 4, plan section 4).

    usable_smiles(frame)      the session's smile_fits rows the surface reads: tau > 0 and at least
                              smile.MIN_NODES nodes, as (tau, k_nodes, w_nodes), sorted by tau
    iv30(view, t, source)     (sigma, SURFACE_* flags) = smile.surface_iv([0], 30/365, usable smiles)

It is the same call as the engine's DaySurface.atm_iv_30d() and M2's exported `atm_iv_30d`, and returns the same
number wherever iv30 is a number: k = 0 is the log-moneyness at the expiry's own parity forward, so the read is
ATM-forward. NaN when the session has no snapshot (no smile rows), no usable smile, or the read needs
SURFACE_EXTRAP_TENOR (30 days is not bracketed by two expiries: early in some Januaries the front expiry is past 30
days). The flags of the read are returned with the NaN (0x4 for SURFACE_EXTRAP_TENOR; 0 with no snapshot or no usable
smile, where the VRP signal's own IV30_MISSING says why). Not equal on SURFACE_EXTRAP_TENOR: there atm_iv_30d has no
NaN branch and returns the tenor-extrapolated value, while iv30 is NaN. On the development sessions that happens on 5
(2010-01-15, 01-19, 04-16, 04-19 and 04-20; review C24), and 27 more have no usable smile (C25: all 32 carry the VRP's
IV30_MISSING, measured 2026-11-09).

Unlike DaySurface.from_view, it does not read the session's forwards: the 30-day read needs only the smiles (a
session with smiles and no forwards does not occur in the store; default taken 2026-11-09, owner can override).

May import (volbt): pricing, view. numpy only.
"""

from __future__ import annotations

from datetime import date

import numpy as np

from volbt.pricing import smile

DAYS = 30
DAYS_PER_YEAR = 365


def usable_smiles(frame) -> list[tuple[float, np.ndarray, np.ndarray]]:
    """The rows of a view.smiles() frame the surface uses, as smile.surface_iv takes them."""
    rows = zip(frame["tau_years"], frame["k_nodes"], frame["total_var_nodes"], frame["n_points"])
    return sorted(((float(tau), np.asarray(k, dtype=float), np.asarray(w, dtype=float))
                   for tau, k, w, n in rows if tau > 0 and n >= smile.MIN_NODES), key=lambda s: s[0])


def iv30(view, t: date, source: str = "optionsdx") -> tuple[float, int]:
    """(IV30 at t, the SURFACE_* flags of the read); NaN as the module docstring says."""
    smiles = usable_smiles(view.smiles(t, source=source))
    if not smiles:
        return float("nan"), 0
    sigma, flags = smile.surface_iv(np.zeros(1), DAYS / DAYS_PER_YEAR, smiles)
    flags = int(flags[0])
    if flags & smile.SURFACE_EXTRAP_TENOR:
        return float("nan"), flags
    return float(sigma[0]), flags
