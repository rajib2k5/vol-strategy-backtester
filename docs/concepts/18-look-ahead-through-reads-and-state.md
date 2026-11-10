# Look-ahead through reads, and through state

## First principles

**Look-ahead** is a decision that uses information from after the decision. A backtest that does it reports a result no trader could have had. The leak has two routes.

- **Through a read.** The code asks the data for a row dated after *t*. This is the easy case: put a wall at the reader. In this project every market read goes through a `StoreView` built for one session. The view carries its own `as_of`, and a read of a later date raises `LookAheadError` (ADR-0001 §4).
- **Through state.** The code keeps a value that was computed with later data: a model fitted once on the whole sample, a cached table of a whole year, a variable set by an earlier run. No read of a later date is ever made, so the wall sees nothing. This is the hard case, and the only test that finds it is a *behavioural* one: change the future and see whether the past moves.

Terms:
- **`as_of`**: the last date a view may serve.
- **Year cache**: the engine reads a year of quotes into memory at once, because a read per day costs too much ([walkthrough](../milestones/03-daily-engine.md), decision D1). The cache holds data from after *t*, so it is state.
- **Prefix property**: a run stopped at *t₀* writes the same rows as the full run does up to *t₀*.

## The maths

There is no model. There is a test, and its logic is a proof by contradiction. Take store A and build store B from it:
- every value dated after *t₀* is multiplied by 3 and permuted across the future dates (bars, VIX, rates, dividends, quotes, volumes);
- the set of session dates is kept, because the calendar is a legitimate input (decision D3);
- the derived tables are rebuilt with the M2 pricing build.

A and B are identical up to *t₀* and different after it (a test checks both halves). Now run the engine on both, stopped at *t₀*. If any step of the run read a value dated after *t₀*, directly or through the cache, the two ledgers would differ. They must be byte-identical, and the books must have the same `Book.digest` (`tests/test_engine_lookahead.py:139`; `uv run pytest -q tests/test_engine_lookahead.py`).

**The test must be able to fail.** Stopped one session later, the two runs do differ (`:167`). So the equality above is not an empty check.

**Worked example.** *t₀* = 2023-03-16, the eve of an ex-date that is also a monthly expiry. The reference strategy holds a short 2023-03-17 400 straddle, and the call is in the money. The call rule assigns it early, on the *projected* dividend of 1.818 (the last paid amount, because fewer than eight are known). The dividend booked on 2023-03-17 is 1.616, and in store B it is 3 × 1.616 = 4.848. A rule that read the real next dividend would put 1.616 in the event on A and 4.848 on B, and the ledgers would differ. They do not: the event's `dividend_amount` is 1.818 on both. A second *t₀*, 2023-04-03 (the −8% gap), covers an early put assignment whose σ comes from a later expiry's surface: a σ read from *t₀*+1 shows only at this *t₀*.

**The prefix property** (`:251`). The full run's rows dated up to *t₀* equal the rows of the run stopped at *t₀*, for eight (strategy, *t₀*) cases. A decision column must match exactly. An outcome column (an order's status, a lot's close date) is compared only where the date that settles it is on or before *t₀*; otherwise it must still be null in the stopped run.

**The cache is checked on its own.** Changing every cached row after `as_of` changes nothing a cached view serves (`:330`), and no public attribute of a view reaches `volbt.data` or the cache, which itself has no public read method (`:377`).

## Assumptions

- **The calendar is allowed.** The engine reads the list of future session dates (dates only, no price). Exchange holidays are published in advance, so this is not look-ahead. It does leak an *unscheduled* closure a day early: 2012-10-29 and 10-30, 2018-12-05 and 2025-01-09 are absent from `spy_bars` (decision D3).
- **The perturbation reaches every input.** Bars, VIX, rates, dividends, quotes and volumes all change. A path from a table the test does not change would not be tested.
- **The AST import rule is a tripwire, not a sandbox.** It stops casual misuse in strategy code; the behavioural test is the proof (ADR-0001, test 1).

## Where it breaks

- **Strategies and signals are tested in M4, not here.** ADR-0001 test 6 perturbs the future for signals and needs fitted models. M3 tests the engine's own reads and state with a reference strategy.
- **A leak that the made-up store cannot show.** The test sees only the paths the fixture exercises. The eight prefix cases and the two *t₀* values were chosen to cover a missing snapshot, a settlement, an early call assignment, an early put assignment, a close order and a waiting order.
- **Some leaks are caught by an exception, not by the equality.** With the mutant in which the cache returns every row of the year (mutant 30), the checker's run, stopped at the first failure, ended in a `ValueError` from the smile surface (two smiles at one τ). The loop test agent's run of the same mutant failed 5 tests, among them the direct equality of `:330`, and raised errors in 8 more. It is killed either way.

## In this project

- `src/volbt/data/store.py:622` `view`: the closure applies `check_not_after` to the one date it slices. `:547` `YearCache._slice`, `:570` `_upto`, `:492` the class and its docstring. `:610` `session_calendar`.
- `src/volbt/data/store.py:475-489` the view's `quotes`, `quote_ivs`, `forwards` and `smiles`; `src/volbt/view.py:117-129` the protocol.
- `src/volbt/engine/loop.py:257` `step_01_load`: builds the view of session *t* for the whole session.
- `tests/test_engine_lookahead.py`: `:115` the premise (A equals B up to *t₀*), `:139` (a), `:167` the control, `:251` (b), `:330` and `:377` the cache.
- `tests/test_engine_provenance.py:51`: the cached private reader serves nothing after `as_of` (it covers mutant 38).
