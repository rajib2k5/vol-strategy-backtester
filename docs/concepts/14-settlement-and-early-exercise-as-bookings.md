# Settlement and early exercise are bookings, not marks

## First principles

An option does not pay out. When it expires, or when its holder exercises it, a *transaction* happens: shares change hands at the strike, cash moves, and the contract disappears. The engine books exactly that. It does not add a payoff to a P&L line.

Why this matters: a booking moves the book into a new shape, and the next steps (the marks, the hedge, the decision) must see the new shape. A payoff added to P&L would leave the shares out, and the hedge would trade for them a second time.

Terms:
- **S_set**: the SPY official close on the expiry date, **unadjusted** (`spy_bars.close`). It is never the option's own quote and never the dividend-adjusted close.
- **Ex-by-Ex**: exercise by exception. A contract in the money by at least one cent is exercised; any other expires. No contrary instructions.
- **Assignment**: the short side of an exercise. **Early** means before the expiry date.
- **Delivery**: shares at the strike *K*, 100 per contract. Long call +100, short call −100, long put −100, short put +100; cash moves by ∓100 × K.
- **Pin**: a short contract with |S_set − K| ≤ $0.50. It is settled by the rule as usual and flagged `pin_flag`.

## The maths

**Value is conserved at settlement.** Take two long 440 calls and S_set = 450.00 (ADR-0003 test 2; `uv run pytest -q tests/test_engine_settlement.py`). The book receives +200 shares and pays 200 × 440 = $88,000. The shares are worth 200 × 450 = $90,000. The settlement therefore adds $2,000, which is the calls' intrinsic value, 2 × 100 × 10. NAV is conserved at the intrinsic value: the lot's `INTRINSIC` row (the same $2,000) is kept out of NAV because the shares and the cash already carry it (decision D11).

**The one-cent rule in integers** (`src/volbt/engine/settlement.py:73`): a call is exercised iff S_set − K ≥ 1 cent. At 450.00 a 450 call and a 450 put both expire. At S_set = 450.00 a 449.99 call and a 450.01 put are each one cent in the money and exercised.

**Hedged and unhedged books.** A hedged book's step 6 runs after settlement, so it sees the delivered shares in place of the expiring options' terminal delta (±1 or 0 per share). The two net out and the hedge trades 0 shares on the expiry day. An unhedged book gets a share-liquidation order for the delivered shares, filled at the next close.

**Early exercise is decided at step 10 of day *t* and booked at step 2 of *t+1*.** The order inside the booking matters (ADR-0003 test 5, `tests/test_engine_early.py:186`). A short 440 call, S = 450, a dividend of $1.80 going ex on *t+1*, r = 5%:
- the closed form says exercise iff D > P_E(K) + K(1 − e^(−rτ)); τ from the ex-date to expiry is 0, so the right side is 0 and 1.80 > 0: the call is assigned;
- at the start of *t+1* the book gets −100 shares and **+$44,000** (100 × 440);
- then the dividend with ex-date *t+1* is paid on the shares held *after* the booking: **−$180** (100 short shares × $1.80).

With the two steps in the other order the dividend would be paid on the shares held before the assignment, and the book would be $180 wrong. Test 6 shows the other side: with 30 days left after the ex-date the right side is 4.80 (a $3.00 put plus 1.8045 of interest on K), which beats 1.80, so the call is not assigned.

**Puts have no closed form.** ADR-0003 test 7 (K = 450, 30 days, σ = 0.20, N = 500, tolerance $0.005) gives the margin continuation − intrinsic: **0.5201** at S = 420 and r = 5% (not assigned, though the old inequality would assign), **−0.0037** at S = 400 (assigned), **1.0986** at S = 395 with a $1.70 dividend in 10 days (waiting for it dominates), **0.0167** at r = 0.25% and S = 390 (not assigned).

## Assumptions

- **Shorts are assigned on every qualifying contract.** If exercise is optimal, the whole short lot goes. Longs are exercised by us.
- **σ is the surface IV at the lot's strike at *t*,** never a market mid and never *t+1*'s. The rate is the last value dated before *t*.
- **The dividend is projected, not read.** The amount that goes ex at *t+1* is projected from the dividends paid by *t* (ADR-0008 amendment 4). On the made-up store the call rule uses 1.818 (the last paid, fewer than eight being known) while 1.616 is booked on the ex-date (`tests/test_engine_early.py:247`).
- **A non-session expiry settles on a mapped session or stops the run** (decision D16): 2015-12-19 (a Saturday) settles at the 2015-12-18 close, and 2018-12-05 (the day of mourning for President George H.W. Bush) at the 2018-12-04 close. 2018-12-23 and 12-25 are unmapped, and a run holding one raises `UnmappedExpiry`. An expiry after the calendar's last SPY bar is not called a non-session: it settles on its own date (the M3 review found holdout runs into late 2026 stopping).

## Where it breaks

- **After 4:00 pm.** With end-of-day data there is no information about what happens after the close, so no pin outcome is simulated.
- **Unhedged early delivery.** The engine first left shares delivered by an *early* assignment in the book for the rest of the run, because only expiry-day delivery created a liquidation order. A test that asserted ADR-0003 §5 failed, was kept as a strict xfail, and the engine was fixed (`src/volbt/engine/loop.py:701`). The test that passes now is `test_an_unhedged_book_liquidates_early_assigned_shares`, `tests/test_engine_early.py:211`.
- **A known inconsistency, not changed.** For a call with two ex-dates before expiry the lattice branch runs from *t*, while the closed form measures τ from the ex-date. On test 6's inputs the boundaries are 462.60 (closed form), 464.21 (the lattice from *t*) and 462.61 (the lattice at the closed form's τ). It applies only to calls beyond about 90 days, which the reference strategy never holds.
- **The 2018-12-05 entry needed a primary source that names SPY.** A Cboe notice moves ETP Wednesday weeklies to the Tuesday close but does not name SPY, so the first M3 review had the entry removed. OCC Information Memo #44125, read through the Wayback Machine in the round-2 review, lists SPY options at Tuesday closing prices, so the entry is back. The sources are in `settlement.py` and ADR-0003 amendment 1.

## In this project

- `src/volbt/engine/settlement.py:61` `settle_date` (the D16 map, `:50`), `:73` `is_exercised`, `:78` `delivered_shares`, `:83` `settle_lot`.
- `src/volbt/engine/early.py:42` `decide_lot`: the closed form for calls, the lattice for puts. `:32` `call_threshold`.
- `src/volbt/engine/loop.py:453` `step_04_settle`, `:283` `step_02_start_of_day` (the early bookings, then the dividend), `:668` `step_10_early`.
- `tests/test_engine_settlement.py:53` ADR-0003 test 1; `:72` test 2; `:279` hedged netting trades nothing; `:294` unhedged shares are liquidated; `tests/test_engine_early.py:125` the put table; `:267` the early shares arrive before the dividend.
