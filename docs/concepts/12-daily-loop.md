# The daily loop: why fills come before marks

## First principles

A backtest is a loop over sessions. What matters is the order of the steps inside one session, because each step changes what the next one sees. A wrong order does not crash. It books a trade a day early, or values a lot that has already gone, and the books still add up.

Terms:
- **Session**: a day SPY trades. **Snapshot**: the option chain of one session, taken at the close. A session can have a SPY bar and no snapshot.
- **Order created at *t***: a decision taken after snapshot *t*. It fills at *t+1* against *t+1*'s quotes ([concept 13](13-integer-cent-fills-and-t-plus-1.md)).
- **Lot**: one contract held inside a position. **Book**: cash in integer cents, SPY shares, lots and orders. **Ledger**: the tables the run writes.
- **NAV_mid** = cash + shares × S + the sum of qty × 100 × mark over the open lots ([concept 15](15-nav-mid-nav-liq-and-model-marks.md)).

**Why fills come before marks.** An order created at *t−1* fills at the *t* close. Its new lot exists at the *t* close, and the cash for it has already left the book. If the mark ran first, the lot would carry no value on its first day, and NAV would move by the whole premium that changed hands. So the fill runs first and the lot gets its first mark the same day. The same argument puts settlement before marks (a lot that expires today gets a settled value, not a quote) and the hedge after both (it needs the marks' greeks and the shares that settlement delivered).

## The maths

There is no model here, only an accounting identity that every step must keep true: NAV_mid = cash + shares × S + Σ qty × 100 × mark. Steps 2 to 4 move cash, shares and lots. Step 5 values what is left. The identity is checked on every session of every run (`tools/report_m3.py`, "NAV identity max error").

The eleven steps (ADR-0001 §1, `src/volbt/engine/loop.py:1-37`):

| Step | What it does | Why here |
|---|---|---|
| 1 load | the session's view, surface, S_t, rate dated before t, dividends paid by t | everything after reads it |
| 2 start of day | early events decided at *t−1*, dividends, interest, borrow fee; cancel orders on removed lots | a real trader learns of an assignment before the open |
| 3 fill | orders created before *t* fill against snapshot *t* | the lot needs a mark today |
| 4 settle | contracts that expire at *t* | before the marks and the hedge |
| 5 mark | one mark per lot, NAV_mid, NAV_liq, DEGRADED | needs the lots as steps 3 and 4 left them |
| 6 hedge | trade −round(net delta) at the *t* close | needs the marks' greeks and the delivered shares |
| 7-8 snapshot, risk | the `daily_pnl` row; ruin stops the run | after the hedge |
| 9 decide | the strategy sees the book at the close; its orders fill tomorrow | after everything it must see |
| 10 early | early exercise and assignment for *t+1* | needs σ and S at the *t* close |
| 11 write | append the rows; `on_session_end` | last |

**Worked example**, ADR-0001 test 5 (`tests/test_engine_loop.py:45`, on the made-up store; `uv run pytest -q tests/test_engine_loop.py`). Five long 2023-03-17 400 calls were ordered on 2023-02-16. Ten short 2023-02-17 405 puts expire on 2023-02-17, and SPY closes at 402.79, so the puts are in the money by 2.21. On 2023-02-17 the ledger shows, in the order the flows were booked:
- **fill**: the 5 calls (an `option_premium` and an `option_fee` flow);
- **expiry**: the puts are assigned, +1,000 shares at 405 (a `settlement` flow);
- **mark**: the new calls have a `QUOTE_MID` mark that day; the settled puts have only an `INTRINSIC` row, with `in_nav` false;
- **hedge**: the net delta counts the 1,000 delivered shares and the new calls' delta (three `hedge_*` flows).

**The same order on real data**, from `tools/report_m3.py`, block "trace" (2026-10-30): the order for SPY 2015-04-17 205 straddles was created on Friday 2015-03-13, filled on Monday 2015-03-16, marked that day (`QUOTE_MID` 5.225 and 2.525), and hedged that day (delta before −242.97, bought 243 shares, delta after 0.03).

**Proof that the order matters.** The loop test agent swapped pairs of steps in a scratch copy: fills after settlement failed 1 test, the hedge before the marks failed 3, the marks before settlement failed 3 (scratchpad `m3/tests/lld/mutants_run2.log`, L1 to L3).

## Assumptions

- **One snapshot a day, at the close.** No intraday information, so no intraday stops or hedges (ADR-0001, Consequences).
- **Today's orders fill tomorrow.** The one exception is the hedge: it trades at the close that produced its delta (ADR-0005 §3). The `same_close` fill timing is a diagnostic that fills at *t*, after the decision (pass 9b).
- **A decision sees only the book at the close.** The strategy gets a frozen copy of the book, not the engine's own object.

## Where it breaks

- **A session with no snapshot.** Nothing can fill against it. Option orders wait for the next snapshot. Share orders do not wait, because they fill at the close (decision D15). Lots are marked from the previous surface (rule 4).
- **An order on a lot that is gone.** An assignment decided at *t* is booked at the start of *t+1*, and a close order queued at *t* would then fill against nothing. Step 2 cancels the whole package with `LOT_REMOVED`. Step 4 does the same for a lot that settles today (decision D12).
- **Ruin.** If NAV_mid is zero or below after the hedge, the run stops (ADR-0007 §5). Steps 9 and 10 do not run on that session.

## In this project

- `src/volbt/engine/loop.py:717` `session`: the eleven steps in order. The step functions start at `:257` (`step_01_load`) and end at `:703` (`step_11_write`).
- `src/volbt/engine/loop.py:283` `step_02_start_of_day`, `:443` `step_03_fill`, `:453` `step_04_settle`, `:478` `step_05_mark`, `:512` `step_06_hedge`, `:626` `step_09_decide`, `:668` `step_10_early`.
- `src/volbt/engine/loop.py:237` `cancel_on_lots`: the `LOT_REMOVED` cancel.
- `tests/test_engine_loop.py:45` ADR-0001 test 5; `:89` ADR-0001 test 7; `:229` one mark per lot per session; `:250` the NAV identity on every session.
