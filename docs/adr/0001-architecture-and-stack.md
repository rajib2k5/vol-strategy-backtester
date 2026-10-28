# ADR-0001: Architecture and stack

**Status:** Accepted, milestone 0.
- Module skeleton: M1. Daily engine: M3. JSON datasets: the milestone that produces each one (table below).
- Revisit at M3 if a 14-year, single-strategy run takes longer than 60 s.

## Revised after M0 review (2026-10-28)

The adversarial review (`docs/validation/00-design-research-ledger.md`, claim 14) refuted four things here. Each was re-checked before this revision.

1. **The import test was weaker than the table.** "Fails if a module imports one not on its left" allowed 33 edges the "May import" column forbids, including `strategies → data`, which bypasses `MarketView`. Re-run of the reviewer's probe: 33 edges. **Changed:** the test is specified to enforce each row's explicit allow-list, with `strategies → data` as one of its required mutants. It does not exist in M0; it is implemented and enforced from M1.
2. **Signals leaked the future.** "Column operations over the full history, then shifted" moves the index but not the fitted parameters. Re-run: changing only data after t₀ moved a full-sample HAR forecast at t₀ from 2.985e-03 to 2.992e-03. **Changed:** signals are computed causally inside the daily loop from the `MarketView`, with refits on a schedule. A perturb-the-future test is specified (test 6) and implemented from M1.
3. **The engine could not call signals.** The sequence diagram has the engine call signals, but `signals` was not in the engine's allow-list. **Changed:** it now is. The diagram and the table agree.
4. **Pricing both had "no I/O" and wrote the derived tables.** **Changed:** the design adds a `volbt.build` module, specified here and implemented from M1 (the pricing build itself in M2). It reads and writes through `data` and calls the pure functions in `pricing`.

Also fixed: an early assignment decided at *t* could collide with a close order for the same lot (ledger, "Unspecified collision"). Such orders are now cancelled at the start of *t+1* (step 2).

Knock-on changes from other ADRs: the JSON `run` block gains `cap_mode` (ADR-0002) and `chain_mask` (ADR-0009), and `metrics` gains `n_trials_eff`, `dsr_raw` and `dsr_eff` (ADR-0010). All three are additive, so they are a MINOR bump.

Round 2 (`docs/validation/00-round2-ledger.md`, claim 13): the table is acyclic and keeps `strategies` and `signals` away from `data`, but the text above and elsewhere said `volbt.view`, `volbt.build` and the AST import test exist. In M0 only `config`, `contract` and `illustrative` exist; the rest is specified here and implemented and enforced from M1. Design gaps closed: the AST rule also bans `sys.modules`, string `getattr` and private-attribute access in `strategies` and `signals`, and the view keeps no public store reference (test 1, test 2); test 6 perturbs FRED rates and dividends too; the engine's allow-list includes `config`. `metrics` field names change with ADR-0010: `n_trials` is N_raw and N_eff is `n_trials_eff`.

## Context

We backtest SPY option strategies on end-of-day (EOD) chain snapshots. There is one snapshot a day, and no intraday data.

The P&L is **path-dependent**. Each position's state decides what happens next:
- whether the profit target or stop was hit, measured on that position's own P&L;
- the DTE (days to expiry) at which it must be closed;
- whether it expired in the money and delivered shares;
- whether an early assignment happened before an ex-dividend date;
- how many contracts the volume cap let through yesterday;
- the current portfolio delta that the hedge must offset;
- whether the margin requirement now exceeds NAV (net asset value).

The data volumes are small enough for one machine. Measured on 2026-10-28 from the local copy of Kaggle `dudesurfin/spy-options-eod-volatility-surface-2010-2023`:
- 14 yearly parquet files, 596,256,111 bytes (569 MiB). The brief's "~509 MB" is wrong.
- 9,468,584 rows over 3,508 snapshot dates, from 2010-01-04 to 2023-12-29.
- Rows per date grew from about 1,052 (2010) to 5,070 (2021).
- Nine full-scan DuckDB aggregate queries over all 14 files ran in 0.21–0.24 s wall-clock, including `uv run` start-up, warm cache (re-measured by the verifier on 2026-10-28; the first draft's 1.3 s came from a script that was not kept).

## Decision

1. **The engine is event-driven with a daily step.** It loops over exchange sessions. Each session runs a fixed sequence of steps, in this order (see `docs/architecture/engine-daily-loop.sequence.mmd`):
   1. **Load the snapshot for session *t*:** the cleaned chain, forwards and smiles, the SPY close, the rate and that day's dividends.
   2. **Start-of-day events:** first the early assignments decided at *t−1*, then dividends with ex-date *t*, then cash interest from *t−1* to *t*.
      - Any pending order with a leg on a lot that these events removed is then cancelled with `cancel_reason = LOT_REMOVED`. A real trader learns of an assignment before the market opens; the order would otherwise fill against a contract no longer held.
   3. **Fill the orders created at *t−1*** against the *t* quotes (ADR-0002). Fills come before marking so that every new lot gets its first mark today.
   4. **Settle the contracts that expire at *t*** (ADR-0003).
   5. **Mark every lot and compute greeks** (ADR-0004).
   6. **Delta-hedge at the *t* SPY close** (ADR-0005).
   7. **Take the portfolio greeks snapshot and the P&L attribution.**
   8. **Check end-of-day greek and stress budgets and the net margin requirement** (ADR-0006, ADR-0007). Any reductions they require become orders for *t+1*.
   9. **Compute signals from the `MarketView`, then let the strategies decide.** This produces exits and entries, passes them through the pre-trade risk check, and queues them as orders for *t+1*.
   10. **Decide early exercise and assignment** for *t+1*.
   11. **Write the ledger.**

   This order differs from the brief's (load → mark → expiries → greeks → signals → orders → risk → fills → hedge → ledger) for one reason. Fills from *yesterday's* orders happen at today's close, so they must come before today's marks. *Today's* orders fill tomorrow (ADR-0002).

2. **Signals are causal by construction.** At step 9 the engine calls `volbt.signals` with that session's `MarketView(as_of = t)`, so a signal can read nothing dated after *t*.
   - **Fitted models** (HAR, GARCH, GJR) are refitted on a fixed schedule: monthly, on an expanding window of data dated on or before the refit date (ADR-0010 §1). The value at *t* uses the parameters of the last refit on or before *t*. Each `signals` row records that `model_fit_date`.
   - **Vectorised code is allowed inside one computation,** for example a rolling RV over the history up to *t*. It is never run over a span that extends past *t*.
   - **"Compute over the full history, then shift" is forbidden.** Shifting fixes the index, but parameters fitted on the full sample still carry later data.
   - **The `MarketView` guard covers reads, not state** such as a cached fit. Test 6 covers state: it changes the future and requires the past to stay identical.
   - The portfolio simulation is never vectorised.

3. **Storage is a chain store of parquet files queried in-process by DuckDB.**
   - **Raw vendor files are never modified.** They stay outside the repo at `$VOL_DATA_DIR`, as in `src/volbt/config.py`.
   - **Cleaned data and derived tables** (quotes with quality flags, implied vols, forwards, smiles) are parquet files partitioned by `source/year`.
     - `volbt.data` writes the cleaned tables.
     - `volbt.build` writes the derived ones. It reads `option_quotes` and reference data through `data`, calls the pure functions in `pricing`, and writes through `data`.
     - `pricing` itself does no I/O.
   - **Each run writes its own ledger tables** to parquet under `runs/<run_id>/`. The table list is in `docs/architecture/data-model.erd.yaml`.
   - DuckDB is a library, not a server. It reads parquet directly and runs SQL with predicate pushdown.

4. **Module boundaries inside `volbt`.** Each module may import **exactly** the `volbt` modules in its "May import" column, and no others. The column is an allow-list, not "anything above it". The graph is acyclic.

   | Module | Owns | May import (`volbt`) | Third-party limit |
   |---|---|---|---|
   | `config` | paths (M0, implemented) | none | stdlib only |
   | `contract` | the JSON envelope (M0, implemented) | none | stdlib only |
   | `illustrative` | the M0 illustrative SSVI surface (implemented) | none | numpy |
   | `view` | the `MarketView` protocol, `LookAheadError`, `SplitError` | none | stdlib only |
   | `data` | loaders (OptionsDX, DoltHub, yfinance, FRED, Cboe), cleaning, quality flags, trading calendar, store readers and writers, and the concrete `MarketView` | config, view | |
   | `pricing` | Black-76 prices and greeks, IV solver, parity forward, CRR lattice (de-Americanisation, ADR-0008; early exercise, ADR-0003), smile build and interpolation, spot × vol shock revaluation | none | numpy, scipy only (pure functions, no I/O) |
   | `build` | the M2 pricing build: `expiry_forwards`, `quote_iv`, `smile_fits` | config, data, pricing | |
   | `signals` | realised-vol estimators, HAR/GARCH forecasts, IV30, signal definitions, all causal | pricing, view | |
   | `strategies` | building structures (straddle, strangle, calendar, vol-arb); entry/exit rules that emit order intents | pricing, signals, view | |
   | `risk` | greek and stress budgets, vega-notional sizing, pre-trade and end-of-day checks, margin model | pricing | |
   | `engine` | the daily loop, fill model, marks, expiry, settlement and early exercise, hedging, ledger | config, data, pricing, signals, strategies, risk, view | |
   | `analytics` | metrics, attribution, regimes, stress grid, PSR/DSR | config, pricing; reads ledger tables only | |
   | `export` | JSON writers and JSON Schemas for the app | analytics, contract | |

   In M0 only `config`, `contract` and `illustrative` exist. Every other row is specified here and implemented from M1, and the import test in "How we will test it" does not exist yet.

   **Strategies and signals never see the store.** Neither may import `data`, and neither can reach it through its allowed imports: `view` holds only the protocol. The engine creates the concrete view with `data.store.view(as_of = t, split = run.split)` and passes it in.
   - Any read of data dated after *t* raises `LookAheadError`.
   - Creating a view whose `as_of` lies after the run's split end raises `SplitError`, which enforces ADR-0010's split guard on every read.

   This is our main structural guard against look-ahead.

5. **Python→app JSON contract.**
   - **The M0 envelope stays exactly as built:** `schema_version`, `generated_at`, `source_commit`. It is written by `src/volbt/contract.py` and checked by `app/src/lib/contract.ts`.
   - **`manifest.json` lists each dataset** as `{name, path, schema_version, description}`.
   - **Versioning is MAJOR.MINOR.PATCH.** The app accepts a file only if its MAJOR equals `SUPPORTED_MAJOR` and ignores keys it does not know. A change that only adds fields therefore bumps MINOR.

   Every **results** dataset adds these three blocks after the envelope:
   - `run`: `{run_id, config_hash, data_fingerprint, data_source, execution_mode, fill_timing, cap_mode, chain_mask, sample_start, sample_end}`.
   - `units`: maps each numeric field to its unit string, for example `"vega_1vol_usd": "USD per 1 vol point"`. The app never guesses a unit.
   - `illustrative`: `false`. Only M0's illustrative surface sets it to `true`.

   Time series are stored **column-wise**, as `dates[]` plus one array per series, not as an array of row objects. Each file must stay under 10 MB uncompressed.

   | Dataset | Milestone | Shape (after the envelope and `run`) |
   |---|---|---|
   | `manifest` | M0 ✔ | `datasets[]` |
   | `illustrative_surface` | M0 ✔ | `illustrative, label, moneyness[], dte[], iv[dte][k], params` |
   | `surface_frames` | M2 | `grid_moneyness[], grid_dte[]`, `frames[{date, spot, atm_iv_30d, iv[dte][k], quoted_share}]`, weekly; `run` names the pricing build |
   | `blotter` | M3 | `fills[{fill_id, date, osi_symbol, qty, price, mid, half_spread, fees, fill_source, intent}]` |
   | `positions_timeline` | M3 | `positions[{position_id, structure, opened, closed, legs[], exit_reason}]`, `dates[]`, `open_count[]` |
   | `greeks_timeline` | M5 | `dates[], delta_usd[], gamma_1pct_usd[], vega_1vol_usd[], theta_1d_usd[], budgets{}` |
   | `pnl_attribution` | M6 | `dates[], nav_mid[], nav_liq[], pnl_delta[], pnl_gamma[], pnl_vega[], pnl_theta[], pnl_fees[], pnl_interest[], pnl_residual[]` |
   | `stress_grid` | M6 | `as_of, spot_shocks_pct[], vol_shocks_pts[], pnl_usd[vol][spot]` |
   | `metrics` | M6 | `overall{}, by_regime[], by_stress_window[], n_trials, n_trials_eff, psr, dsr, dsr_raw, dsr_eff` (ADR-0010 §2) |

6. **The app never computes results.**
   - It may format numbers, convert units for display, sort, filter, and build render-only geometry (mesh vertices, colour ramps).
   - It may not aggregate, re-price, annualise, or derive any number a reader would quote. Every displayed number exists in a JSON file.

7. **Determinism.** The same input files, config and commit must give byte-identical ledger parquet and JSON, except for `generated_at`. To achieve that:
   - The engine never reads the wall clock.
   - Every random draw (bootstrap, PSR/DSR simulation) takes its seed from the config.
   - All iteration is over sorted keys: `lot_id`s are assigned in creation order, and every DuckDB query has an explicit `ORDER BY`.
   - Floats are rounded per unit at export (prices to 4 dp, IV to 6 dp, USD to 2 dp).
   - Dependencies are pinned in `uv.lock`.
   - `data_fingerprint` is the SHA-256 over the sorted (path, size, SHA-256) list of input files.

## Alternatives considered

- **A fully vectorised backtest** (signal → position matrix → P&L via `cumsum`). Rejected because it cannot express state that depends on the path:
  - partial fills under a volume cap change tomorrow's position;
  - a stop depends on the position's own marked P&L;
  - expiry delivers shares;
  - the hedge depends on the whole book's delta;
  - forced liquidation depends on the NAV path.

  It would win only for single-option, hold-to-expiry studies with no caps, hedging or margin.
- **Intraday event-driven.** Rejected: we have no intraday quotes, and pretending we do invites fake precision.
- **An off-the-shelf framework** (backtrader, zipline, vectorbt, QuantConnect LEAN). Rejected:
  - The Python ones are equity-bar oriented, with no native option chains, expiry, assignment or greeks.
  - LEAN is C#, tied to its own data formats, and hides the fill and expiry logic that this repo exists to teach and defend.

  It would win if the goal were production trading rather than learning.
- **Postgres/TimescaleDB**: a server to run for a single-user, read-mostly workload. **SQLite**: a row store, slow for column scans over 9.5 M rows. **CSV**: untyped and about 10× larger. All rejected.

  A server database would win if several writers needed concurrent access.
- **QuantLib for pricing.** Rejected for the core: European Black-76 is about 50 lines that the owner must be able to derive in an interview. QuantLib stays acceptable as an independent cross-check in tests.
- **Letting the app compute metrics** (for example Sharpe in TypeScript). Rejected:
  - two implementations would drift apart;
  - the Python one is the tested one;
  - a reviewer could no longer trust that the chart shows the backtest's own number.

## Consequences

- **Speed.** The daily loop runs in Python, about 3,500 sessions × (fills + marks + hedge). Per-day chain slices are loaded a year at a time (≤ 1.3 M rows, a few hundred MB).
- **No intraday information**, so no intraday stops or hedges. This is **optimistic** for short-gamma books on gap days: a real book might have been stopped out intraday at a worse price. It is partly offset by the *t+1* fill rule (ADR-0002).
- **The `MarketView` guard** costs one indirection per data access. In return, a look-ahead *read* is a crash rather than a silent bias. Look-ahead through *state*, such as a model fitted once on everything, is caught by test 6 instead.
- **Causal signals cost more compute** than one vectorised pass: a monthly refit is about 170 fits over 14 years per model. That is small next to the daily loop.
- **Column-wise JSON** keeps files small but makes them harder to read by eye. The `units` block compensates.

## How we will test it

1. **Import boundaries.** An AST test parses every file under `src/volbt/`. It resolves absolute imports, `from volbt import x` and relative imports to the top-level `volbt` module. It fails if:
   - a module imports a `volbt` module that is not in that module's "May import" set;
   - a module breaks its third-party limit: `pricing` imports anything but numpy, scipy or stdlib, or `config`, `contract` or `view` import any third-party package;
   - a file under `src/volbt/` belongs to no row of the table;
   - `importlib` or `__import__` is used anywhere in `volbt`;
   - `sys.modules` is referenced, `getattr`, `setattr`, `vars` or `globals` is called with a string name, or a private attribute (a name starting with `_`) is read on an imported object, anywhere in `strategies` or `signals`. Each is a way round the import allow-list;
   - the table itself has a cycle (checked with `graphlib`).

   **Required mutants.** Each of these, on its own, must make the test fail:
   - `import volbt.data` in `strategies` (the `MarketView` bypass);
   - `import volbt.strategies` in `risk`;
   - `import volbt.engine` in `pricing`;
   - `from ..data import store` in `signals`;
   - `import duckdb` in `pricing`;
   - `sys.modules["volbt.data"]` in `strategies`;
   - `getattr(view, "_store")` in `signals`.
2. **Look-ahead guard.**
   - On a fixture with sessions 2023-03-14 and 2023-03-15, a strategy holding a `MarketView(as_of=2023-03-14)` that requests the 2023-03-15 chain raises `LookAheadError`.
   - For a run tagged `development`, creating a view with `as_of = 2020-01-02` raises `SplitError`.
   - The concrete `MarketView` keeps no public reference to the store: a walk over its public attributes reaches no object from `volbt.data`.
3. **Determinism.** Run the M3 fixture backtest twice. The SHA-256 of every ledger parquet and of every JSON file, with `generated_at` removed, must be identical.
   - Then change one seed: the bootstrap output must change and the ledger must not.
4. **Contract.** Each exported file validates against its JSON Schema in `volbt.export`.
   - A metrics fixture with `sharpe = 1.234567` must appear in the app as `1.23`. The app renders the file's value and does not recompute it.
5. **Step order.** On a fixture day with a pending buy and an expiring ITM short put, the ledger events must be ordered `fill → expiry → mark → hedge`. The new lot must have a mark row on its fill day.
6. **Signals are causal (metamorphic test).**
   - On a fixture of at least 1,500 sessions, run the daily loop to *t₀* and record every signal value.
   - Then change every input dated after *t₀*: SPY bars, VIX, FRED rates, dividends, quotes and derived tables. Multiply by 3 and permute the dates.
   - Re-run. Every signal value dated on or before *t₀*, and its `model_fit_date`, must be bit-identical.
   - **Proving the test can fail.** A mutant HAR that is fitted once on the whole fixture series must fail it, as the reviewer's probe did (2.985e-03 → 2.992e-03).
7. **Start-of-day cancel.**
   - A short put lot is early-assigned by a decision at *t*, and the strategy also queued a buy-to-close order for it at *t*.
   - At *t+1* the assignment is booked first. The order is then cancelled with `LOT_REMOVED`, and no fill row exists for it.
