# Exits on a hedged book

## First principles

A stop-loss asks "has this position lost too much?". On an unhedged position the answer is the position's own value change. On a delta-hedged one it is not. The hedge trades SPY shares for the whole book ([concept 16](16-hedged-gamma-rent.md)), and its gains and losses are part of what the position earns. A rule that reads only the options will stop a short straddle out on a move that its hedge already paid for.

So the exit rules read the **hedged position P&L**, and the engine computes it. A strategy that priced its own marks would be a second implementation of ADR-0004, which the plan rejected.

Terms:
- **Premium**: the cash the opening fills took in (credit, positive) or paid out (debit, negative): −Σ qty × 100 × price. The size of the position for the rules is |premium|.
- **Stop**, **profit target**: exits when the hedged P&L falls to −1.0 × |premium| or rises to +0.5 × |premium|.
- **Signal exit**: an exit when the signal s_t crosses back across a level ([concept 21](21-iv30-log-variance-ratio-and-calendar-time.md)).
- **DTE exit**: close before expiry, so the position never reaches the last two weeks.
- **Precedence**: when two exits hold on one session, the first in a fixed order wins.

## The maths

For one position at the close of session t (`engine/positions.py`):

pnl_t = fills_t + open_t + settled_t + H_t

- fills_t: the position's option fills so far, −qty × 100 × price less fees, in integer cents.
- open_t: its open lots at this close, Σ qty × 100 × mark.
- settled_t: what its settled lots delivered, valued at the session the delivery was booked.
- H_t = Σ_{u≤t} −Δ_{u−1} (S_u + D_u − S_{u−1}): the position's share of the daily hedge. Δ is the position's delta in shares at the previous close, S the SPY close and D the dividend with ex-date u.

It leaves out interest, the borrow fee and the hedge's commission and slippage, because those belong to the book. For a book that holds one position from flat, with the daily hedge at the close, pnl_t equals NAV_mid,t − NAV_mid,0 − interest − borrow fee − hedge costs, plus a residual of at most half a share times each day's move, because the hedge trades whole shares.

**When it exists.** H assumes the book holds −Δ shares at every close. That is true to half a share under a daily hedge at the close with fills at the next close, and trivially with no hedge. Under any other hedge the book's shares lag the positions' delta (the review measured up to 809 shares with a hedge every 5 sessions), so the engine writes no position P&L: `hedge_usd` and `pnl_usd` are null. A rule with a stop or a target refuses such a P&L with an error and does not silently never stop.

**The rules, in order** (`strategies/rules.py`, `PRECEDENCE`): stop, then profit target, then signal, then DTE. At each session's decision, for each open position with no order pending, the first that holds gives the close order's reason.
- **stop**: pnl ≤ −1.0 × |premium|.
- **profit_target**: pnl ≥ +0.5 × |premium|.
- **signal**: short vol, s ≤ θ − 0.4; long vol, s ≥ +0.4. It is a level, not a crossing: a gated entry starts on the other side of it (s ≥ θ > θ − 0.4), so reaching the level is the crossing. A NaN s holds nothing, and the other exits still apply.
- **dte**: the days from the *next* session to the settlement date of the position's earliest open lot are at most 14. The close fills at that next session, so a contract is closed at about 14 DTE.

One close order per position (decision D22), for every open lot, in the gcd of the lots' quantities.

**Why 14.** At 14 DTE a close fills against a listed expiry in a normal week. On DoltHub, the nearest listed expiry is exactly 14 DTE on 404 of 432 sessions in 2020-22 and on 120 of 144 in 2023, and a standard monthly's own expiry is listed on 31 of 31 and 11 of 11 sessions at exactly 14 DTE. The marks use the contract's own expiry, with a median error of 0.04 vol points (ADR-0004's masked measurement). At 15-21 DTE a monthly is never listed and always bracketed by two other expiries (98 of 98 and 31 of 31 pairs; ADR-0004's median error at 21 DTE is 0.24), and at 7 DTE it is always below the front expiry and needs tenor extrapolation (34 of 34 and 12 of 12; median error 1.21) (`tools/measure_listing.py`, 2026-11-17; ADR-0004's table). See the ADR-0003 amendment.

**Worked example, made-up arithmetic.** Ten short straddles taken in at $10.00 each have a premium of $10,000. The stop is at a hedged P&L of −$10,000 and the target at +$5,000. Now take ADR-0005's test 1 numbers (concept 16): 100 straddles, spot from 400 to 404. Short, the options lose $633.12 and the hedge, which holds 229 shares long against the short delta, gains 229 × $4 = $916. The hedged P&L is +$282.88. An option-only rule sees −$633.12 and moves toward the stop. The hedged rule sees a gain.

**Worked example on real data**, position 4 of development run `10d433dd…` (a short straddle, entry θ = 0, signal exit at −0.4, stop and target on): the signal exit fired on 2010-05-10, when s = −0.547 ≤ −0.4. On that session the stop and the target did not hold, because the precedence puts them first, so the reason would have been `stop` or `profit_target` if either had held. On the sessions from 2010-04-27 to 05-07 the lowest s was −0.358 (on 05-03), above the exit level of −0.4. No close order exists for the position before 05-10, so no exit held. The DTE exit was far off: the next session, 2010-05-11, was 38 days from the 06-18 expiry. The close order was created on 05-10 and filled on 05-11. No P&L figure of the position is quoted here (decision D19, extended to every date before M6).

## Assumptions

- **The hedge is the book's.** One position is attributed the hedge by its own delta. Rejected: allocating the book's shares pro rata by delta, because two positions with nearly opposite deltas make "shares per unit of delta" unbounded.
- **Marks are the engine's.** `open_t` uses the in-NAV marks of step 5, or of pass 9b for fills at the same close.
- **The thresholds are defaults, not tuned**: 1.0 and 0.5 of |premium|, the 0.4 signal band.

## Where it breaks

- **Gaps.** A −8% gap day cannot be hedged at the old delta. The stop sees the loss after the day, not during it, and fills at the next close.
- **Stale marks.** A stop reads the last mark; on a session with no snapshot, the marks come from a copied surface. A stop on a stale mark can fire late or early.
- **A signal exit waits for a snapshot.** With no snapshot, s is NaN and the signal exit does not hold.
- **Overlap.** Two open positions double the exposure; each has its own stop, and nothing limits the pair until M5.

## In this project

- `src/volbt/engine/positions.py:46` `computed` (when the engine writes a P&L), `:55` `hedge_increment`, `:74` `position_pnl`.
- `src/volbt/engine/loop.py:604` `position_rows` (writes `position_daily`).
- `src/volbt/strategies/rules.py:96` `exit_reason` (the precedence), `:68` `ExitRules`, `:46` `EntryRule`.
- `src/volbt/strategies/vol.py:116` `exit_order` (the DTE counted from the next session, the gcd close), `:90` `decide`.
- `tests/test_engine_positions.py` (the identity against NAV_mid across an ex-date, an early assignment and a partial close), `tests/test_strategy_rules.py`, `tests/test_strategy_causal.py:168` (a stop or a target refuses a P&L that is not computed).
