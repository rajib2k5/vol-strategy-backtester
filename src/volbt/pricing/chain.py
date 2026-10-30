"""One snapshot's chain, priced: forwards, de-Americanised IVs, IV flags and smiles (ADR-0008).

This is the pricing of ONE (source, quote date): every expiry listed that day, every quote. It
works on plain numpy arrays so it stays pure (volbt.build reads the store and hands them over),
and it batches every lattice of the date into one call, because one call on 5,000 options costs
about what one call on 50 does per step (the work is in the 200 backward steps, not in the width).

The order, per ADR-0008 as amended after the M2 review (§3a, default taken 2026-10-29):

1. tau, DF and the carry forward of every expiry (forward.py). On the expiry date tau = 0: no
   forward is needed, and no IV is solved (the contract is worth its intrinsic value).
2. The raw parity forward forward_raw from the raw mids (forward.parity_forward): K*, the
   median of F_K over the 5 strikes nearest it. Fewer than 3 valid pairs: the dividend fallback.
3. De-Americanisation (deam.py), in one pass: every quote that needs a premium gets its own
   American IV on the lattice, A(sigma_A) = mid, and its premium A - E at sigma_A. Those quotes are
   the 10 strikes nearest K*, call and put, and every out-of-the-money quote with a mid. Where a
   quote's American IV is not identified (deam.py step 4: A flat in sigma, deep in the money), its
   premium is priced at its partner's (same expiry and strike, other type) identified American IV
   instead (`premium_from_partner`; iv_american stays NaN), the partner's IV solved then if no
   earlier step had attempted it (round 3, F3); with no such partner the quote keeps
   FAIL_AMERICAN_UNIDENTIFIED and has no premium, so it is out of the forward (M2 round 2, E3).
4. The forward F from parity on the European-equivalent mids (mid - premium) of those 10 strikes.
   A pair counts only when both of its quotes were de-Americanised. With fewer than 3 such pairs
   the forward cannot be de-Americanised: F = forward_raw and `method` says so
   ("parity_median5_raw"), never silently.
5. Every OTM quote with a mid (puts K < F, calls K >= F, §7): its IV is the Black-76 IV of its
   European-equivalent mid on F. No American IV, or no Black-76 IV: IV_FAIL, with the reason.
   There is no |k| band: every OTM quote is corrected. `iv_raw`, the Black-76 IV of the raw mid on
   F, is kept only to measure the correction.
6. Every strike whose European-equivalent F_K is more than 0.5% from F: PARITY_OUTLIER, on both
   of its quotes. The OTM side is its own European-equivalent mid; the ITM side loses the premium
   priced at its partner's OTM IV (`eep_partner`, used for nothing else).
7. The smile of each expiry: the quotes `in_smile` (valid, OTM, with an IV, and `smile_ok`: the
   build passes False for a WIDE quote, ask - bid > mid) as nodes (k, w = sigma^2 tau), smile.py.
   A WIDE quote keeps its quote_iv row and its IV, and may still enter the forward's near-K* pairs:
   in the round-2 build a WIDE pair was among the 5 median strikes of 16 of the 93,857 expiries
   priced by parity, and leaving WIDE pairs out would have moved those forwards by at most 2.38 bp
   (median 0.05 bp; round-3 measurement). It is not a node, because a stub quote (bid 0.03,
   ask 4.84) gave IVs of 0.80-0.87 between tight neighbours at 0.33-0.38 and, through the calendar
   constraint, lifted 13 later expiries (round 3, code finding N-1; decision F2).

Two premiums, two columns (M2 review, design claim 6): `eep` is a quote's OWN premium at its OWN
American IV (every OTM quote with a mid, and the quotes of the strikes nearest K* that set the
forward), or, where that IV is not identified, at its partner's (step 3; iv_american is then
null); `eep_partner` is an ITM quote's premium at its partner's OTM IV, for step 6 only.

The IV flags (quote_iv.iv_flags) use the three bits M1 reserved for them (volbt/data/flags.py;
a test requires the two lists to be equal).
"""

from __future__ import annotations

import numpy as np

from volbt.pricing import forward as fw
from volbt.pricing.deam import american_iv
from volbt.pricing.iv import FAIL_AMERICAN_UNIDENTIFIED, FAIL_NONE, implied_vol
from volbt.pricing.lattice import DEAM_TREE_STEPS, early_exercise_premium
from volbt.pricing.smile import (MIN_NODES, SMILE_ATM_OUTSIDE, SMILE_FORWARD_FALLBACK, SMILE_FORWARD_RAW, SMILE_THIN,
                                 smile_iv, smile_nodes)

IV_FAIL = 1 << 0              # no IV: no American IV on the lattice, or the European-equivalent mid has no Black-76 IV
PARITY_OUTLIER = 1 << 1       # the strike's European-equivalent F_K is more than 0.5% from the expiry's F
FORWARD_FALLBACK = 1 << 2     # the expiry's F is the dividend fallback: fewer than 3 valid pairs
IV_FLAG_NAMES = ("IV_FAIL", "PARITY_OUTLIER", "FORWARD_FALLBACK")

METHOD_PARITY, METHOD_FALLBACK, METHOD_EXPIRY_DAY, METHOD_PARITY_RAW = 0, 1, 2, 3
METHOD_NAMES = ("parity_median5_deam", "dividend_fallback", "expiry_day", "parity_median5_raw")


def _pairs(strike, is_call, valid, expiry_quotes):
    """(strikes, call indices, put indices) of the strikes of one expiry with a valid call AND put."""
    calls = {strike[i]: i for i in expiry_quotes if is_call[i] and valid[i]}
    puts = {strike[i]: i for i in expiry_quotes if not is_call[i] and valid[i]}
    both = sorted(set(calls) & set(puts))
    return (np.array(both, dtype=float), np.array([calls[k] for k in both], dtype=int),
            np.array([puts[k] for k in both], dtype=int))


def _otm(strike, is_call, forward):
    """Puts below the forward, calls at or above it (ADR-0008 §7)."""
    return np.where(is_call, strike >= forward, strike < forward)


def price_chain(spot: float, rate: float, tau, div_times, div_amounts, expiry, strike, is_call, mid,
                valid, deamericanise: bool = True, steps: int = DEAM_TREE_STEPS, smile_ok=None) -> dict:
    """Price one snapshot. Per expiry e: tau[e], and its dividends div_times[e], div_amounts[e]
    (an (E, m) pair of arrays, zero-padded). Per quote i: expiry[i] (an index into tau),
    strike[i], is_call[i], mid[i] (NaN when the quote has no two-sided mid), valid[i] (the
    quote may enter the parity forward and the smile) and smile_ok[i] (default: all True; the
    quote may be a smile node: the build passes False for a WIDE quote, round 3, decision F2).

    `deamericanise=False` skips steps 3 and 4's correction: the European identity on raw mids,
    kept for the ADR-0008 test-8 mutant check; its forwards say so (`parity_median5_raw`).

    Returns {"expiries": {...}, "quotes": {...}, "smiles": [...]}: arrays per expiry, arrays per
    quote, and one dict per expiry with its nodes.
    """
    tau = np.asarray(tau, dtype=float)
    div_times, div_amounts = np.asarray(div_times, dtype=float), np.asarray(div_amounts, dtype=float)
    expiry, strike = np.asarray(expiry, dtype=int), np.asarray(strike, dtype=float)
    is_call, mid, valid = np.asarray(is_call, dtype=bool), np.asarray(mid, dtype=float), np.asarray(valid, dtype=bool)
    valid = valid & np.isfinite(mid)
    n_exp, n = tau.size, strike.size
    df = fw.discount_factor(rate, tau)
    members = [np.flatnonzero(expiry == e) for e in range(n_exp)]
    tau_q = tau[expiry] if n else np.zeros(0)

    out_e = {name: np.full(n_exp, np.nan) for name in (
        "forward", "forward_raw", "forward_carry", "k_star", "fk_slope_per_strike", "forward_mad_rel")}
    out_e.update({name: np.zeros(n_exp, dtype=np.int32) for name in (
        "n_pairs_valid", "n_pairs_used", "n_deamericanised", "method", "flags")})
    iv_flags = np.zeros(n, dtype=np.int32)

    # 1-2. Carry forward everywhere; raw parity forward where there are pairs.
    pairs = {}
    for e in range(n_exp):
        if tau[e] <= 0:
            out_e["forward"][e] = out_e["forward_carry"][e] = spot
            out_e["method"][e] = METHOD_EXPIRY_DAY
            continue
        out_e["forward_carry"][e] = fw.carry_forward(spot, rate, tau[e], div_times[e], div_amounts[e])
        strikes_e, calls_e, puts_e = _pairs(strike, is_call, valid, members[e])
        out_e["n_pairs_valid"][e] = strikes_e.size
        raw = fw.parity_forward(strikes_e, mid[calls_e], mid[puts_e], df[e])
        if raw is None:
            out_e["forward"][e] = out_e["forward_carry"][e]
            out_e["method"][e] = METHOD_FALLBACK
            out_e["flags"][e] = FORWARD_FALLBACK
            iv_flags[members[e]] |= FORWARD_FALLBACK
            continue
        out_e["forward"][e] = out_e["forward_raw"][e] = raw["forward"]
        near = np.sort(fw.nearest(strikes_e, raw["k_star"], fw.DEAM_STRIKES))
        raw_fk = fw.strike_forwards(strikes_e, mid[calls_e], mid[puts_e], df[e])
        out_e["fk_slope_per_strike"][e] = fw.slope_per_strike(strikes_e[near], raw_fk[near])
        out_e["k_star"][e], out_e["n_pairs_used"][e], out_e["forward_mad_rel"][e] = (
            raw["k_star"], raw["used"].size, raw["mad_rel"])
        pairs[e] = (strikes_e, calls_e, puts_e, near)

    # 3. One American IV solve for every quote that needs a premium: the near-K* pairs, and every
    # quote with a mid that is OTM on the forward known so far (forward_raw, or the fallback).
    am_iv, eep = np.full(n, np.nan), np.full(n, np.nan)
    am_fail = np.zeros(n, dtype=np.int8)
    attempted = np.zeros(n, dtype=bool)
    rescued = np.zeros(n, dtype=bool)            # premium priced at the partner's American IV
    near_quotes = (np.concatenate([np.concatenate([c[nr], p[nr]]) for _, c, p, nr in pairs.values()])
                   if pairs else np.array([], dtype=int))

    # The partner of a quote: same expiry and strike, the other type (-1 if it is not listed).
    slot = {(int(expiry[i]), float(strike[i]), bool(is_call[i])): i for i in range(n)}
    partner_of = np.array([slot.get((int(expiry[i]), float(strike[i]), not bool(is_call[i])), -1) for i in range(n)],
                          dtype=int)

    def american(quotes):
        """Each quote's own American IV and its premium there; marks them attempted."""
        e = expiry[quotes]
        got = american_iv(mid[quotes], spot, strike[quotes], tau[e], rate, is_call[quotes], div_times[e],
                          div_amounts[e], steps)
        am_iv[quotes], eep[quotes], am_fail[quotes] = got["iv"], got["premium"], got["fail"]
        attempted[quotes] = True

    def solve(quotes):
        quotes = quotes[~attempted[quotes]]
        if not deamericanise or quotes.size == 0:
            return
        american(quotes)
        # A quote whose own American IV is not identified (A flat in sigma: deep in the money, where
        # exercising at once is optimal) is priced at its partner's identified American IV; with no
        # such partner it stays unidentified and out of the forward (M2 round 2, decision E3). The
        # partner is solved here when no earlier batch attempted it (round 3, decision F3): an OTM
        # put between S and F at a high rate is flat in sigma while its partner call, ITM on the
        # forward and not near K*, was never attempted, so the put had no IV (r 8%, 700 days,
        # sigma 0.12: 2 IV_FAIL and 4 PARITY_OUTLIER on a clean chain).
        flat = quotes[am_fail[quotes] == FAIL_AMERICAN_UNIDENTIFIED]
        partner = partner_of[flat]
        needed = np.unique(partner[partner >= 0])
        needed = needed[~attempted[needed]]
        if needed.size:
            american(needed)
        usable = (partner >= 0) & np.isfinite(am_iv[np.maximum(partner, 0)])
        flat, partner = flat[usable], partner[usable]
        if flat.size:
            ef = expiry[flat]
            eep[flat] = early_exercise_premium(spot, strike[flat], tau[ef], rate, am_iv[partner], is_call[flat],
                                               div_times[ef], div_amounts[ef], steps)
            am_fail[flat] = FAIL_NONE
            rescued[flat] = True

    has_mid = np.isfinite(mid) & (tau_q > 0)
    first_otm = _otm(strike, is_call, out_e["forward"][expiry]) if n else np.zeros(0, bool)
    solve(np.union1d(near_quotes, np.flatnonzero(has_mid & first_otm)).astype(int))

    # 4. The de-Americanised forward, from the near-K* pairs both of whose quotes were solved.
    european = np.where(np.isfinite(eep), mid - eep, mid)
    if deamericanise:
        for e, (strikes_e, calls_e, puts_e, near) in pairs.items():
            both = near[np.isfinite(eep[calls_e[near]]) & np.isfinite(eep[puts_e[near]])]
            out_e["n_deamericanised"][e] = int(np.isfinite(eep[calls_e[near]]).sum() + np.isfinite(eep[puts_e[near]]).sum())
            final = fw.parity_forward(strikes_e[both], european[calls_e[both]], european[puts_e[both]], df[e])
            if final is None:
                out_e["method"][e] = METHOD_PARITY_RAW        # step 4: F stays forward_raw, and says so
                continue
            out_e["forward"][e] = final["forward"]
            out_e["k_star"][e], out_e["n_pairs_used"][e], out_e["forward_mad_rel"][e] = (
                final["k_star"], final["used"].size, final["mad_rel"])
    else:
        for e in pairs:                                       # raw parity, and the label says so
            out_e["method"][e] = METHOD_PARITY_RAW

    # 5. Every OTM quote with a mid on the final F: its premium (solved now if F moved it across), then
    # the Black-76 IV of mid - premium on F.
    forward_q = out_e["forward"][expiry] if n else np.zeros(0)
    with np.errstate(divide="ignore", invalid="ignore"):
        log_m = np.log(strike / forward_q)
    is_otm = _otm(strike, is_call, forward_q)
    solve_now = np.flatnonzero(is_otm & has_mid)
    solve(solve_now)
    out_q = {"log_moneyness": log_m, "is_otm": is_otm, "iv": np.full(n, np.nan), "iv_raw": np.full(n, np.nan),
             "iv_american": np.full(n, np.nan), "eep": np.full(n, np.nan), "eep_partner": np.full(n, np.nan),
             "solver": np.zeros(n, dtype=np.int8), "iterations": np.full(n, -1, dtype=np.int16),
             "fail": np.zeros(n, dtype=np.int8), "premium_from_partner": rescued}
    # eep and iv_american are kept where they were used: OTM quotes, and the near-K* quotes.
    kept = np.zeros(n, dtype=bool)
    kept[solve_now] = True
    kept[near_quotes] = True
    kept &= attempted
    out_q["iv_american"][kept], out_q["eep"][kept] = am_iv[kept], eep[kept]
    if solve_now.size:
        premium = eep[solve_now] if deamericanise else np.zeros(solve_now.size)
        american_failed = (am_fail[solve_now] != FAIL_NONE) if deamericanise else np.zeros(solve_now.size, bool)
        args = (forward_q[solve_now], strike[solve_now], tau_q[solve_now], rate, is_call[solve_now])
        second = implied_vol(np.where(american_failed, np.nan, mid[solve_now] - premium), *args)
        raw_iv = implied_vol(mid[solve_now], *args)
        failed = american_failed | (second["fail"] != FAIL_NONE)
        out_q["iv_raw"][solve_now] = raw_iv["iv"]
        if not deamericanise:
            out_q["eep"][solve_now] = np.where(failed, np.nan, 0.0)
        out_q["iv"][solve_now] = np.where(failed, np.nan, second["iv"])
        out_q["solver"][solve_now] = np.where(failed, 0, second["solver"])
        out_q["iterations"][solve_now] = np.where(failed, -1, second["iterations"])
        out_q["fail"][solve_now] = np.where(american_failed, am_fail[solve_now], second["fail"])
        iv_flags[solve_now[failed]] |= IV_FAIL

    # 6. Parity outliers, on European-equivalent mids (§3a: the steps of §3 run on them, not on
    # raw mids; on raw mids every deep-ITM put at a 5% rate would trip the 0.5% test through its
    # own premium). The OTM side of each pair is its own European-equivalent mid (step 5). The ITM
    # side loses its premium priced at its partner's OTM IV, kept in eep_partner. A pair whose OTM
    # side has no IV is tested raw.
    solved = np.isfinite(out_q["iv"]) & np.isfinite(out_q["eep"])
    european = mid.copy()
    european[solved] = mid[solved] - out_q["eep"][solved]
    itm, partner = [], []
    for e, (strikes_e, calls_e, puts_e, _) in pairs.items():
        for call, put in zip(calls_e, puts_e):
            inside, outside = (put, call) if is_otm[call] else (call, put)
            if deamericanise and solved[outside]:
                itm.append(inside)
                partner.append(outside)
    if itm:
        itm, partner = np.array(itm), np.array(partner)
        e_itm = expiry[itm]
        premium = early_exercise_premium(spot, strike[itm], tau[e_itm], rate, out_q["iv"][partner], is_call[itm],
                                         div_times[e_itm], div_amounts[e_itm], steps)
        european[itm] = mid[itm] - premium
        out_q["eep_partner"][itm] = premium
    for e, (strikes_e, calls_e, puts_e, _) in pairs.items():
        both = solved[np.where(is_otm[calls_e], calls_e, puts_e)] if deamericanise else np.ones(calls_e.size, bool)
        call_mid = np.where(both, european[calls_e], mid[calls_e])
        put_mid = np.where(both, european[puts_e], mid[puts_e])
        fk = fw.strike_forwards(strikes_e, call_mid, put_mid, df[e])
        outlier = np.abs(fk - out_e["forward"][e]) / out_e["forward"][e] > fw.OUTLIER_REL
        iv_flags[calls_e[outlier]] |= PARITY_OUTLIER
        iv_flags[puts_e[outlier]] |= PARITY_OUTLIER
    out_q["iv_flags"] = iv_flags
    # 7. The quotes that are the smile's nodes: valid (bid above 0, not stale), smile_ok (not WIDE,
    # round 3, F2), OTM, with an IV.
    smile_ok = np.ones(n, dtype=bool) if smile_ok is None else np.asarray(smile_ok, dtype=bool)
    out_q["in_smile"] = valid & smile_ok & is_otm & np.isfinite(out_q["iv"]) & (tau_q > 0)

    smiles = []
    for e in range(n_exp):
        node_quotes = members[e][out_q["in_smile"][members[e]]]
        k_nodes, w_nodes = (smile_nodes(log_m[node_quotes], out_q["iv"][node_quotes], tau[e])
                            if tau[e] > 0 else (np.array([]), np.array([])))
        flags = 0
        if k_nodes.size < MIN_NODES:
            flags |= SMILE_THIN
        if out_e["method"][e] == METHOD_FALLBACK:
            flags |= SMILE_FORWARD_FALLBACK
        if out_e["method"][e] == METHOD_PARITY_RAW:
            flags |= SMILE_FORWARD_RAW
        atm = float("nan")
        if k_nodes.size >= 2:
            atm = float(smile_iv(0.0, tau[e], k_nodes, w_nodes)[0])
            if not (k_nodes[0] <= 0.0 <= k_nodes[-1]):
                flags |= SMILE_ATM_OUTSIDE
        smiles.append({"k_nodes": k_nodes, "w_nodes": w_nodes, "n_points": int(k_nodes.size),
                       "atm_iv": atm, "fit_flags": flags})
    return {"expiries": out_e, "quotes": out_q, "smiles": smiles}
