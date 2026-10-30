# Milestone 1: the option-chain data layer and quality filters

> **Data notice.** The DoltHub figures in this document (counts, dates, quantiles and summaries, in its text and in its tables) are derived from the DoltHub database `post-no-preference/options` (<https://www.dolthub.com/repositories/post-no-preference/options>), licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), and are shared under the same licence. Changes: we aggregated it into counts, shares and quantiles, compared it with OptionsDX and ran our pricing build on it; no quote row is reproduced. The rest of this repository is MIT. See [DATA.md](../../DATA.md).

Status: built and reviewed. Reviewed by: `adversarial-reviewer` (Opus) and `verifier` (Sonnet) on 2026-10-29 (`docs/validation/01-ledger.md`), then a second round that attacked the fixes. Every refutation of both rounds was fixed ("After the review", below), the store was rebuilt after round 2, and the numbers here were re-measured on that rebuild.

Every number below was measured on 2026-10-29 and names the command that produced it. Two commands produce most of them:

- **[build]** `uv run python tools/build_data.py`: builds `data/store/` and writes `data/store/build_summary.json`.
- **[report]** `uv run python tools/report_m1.py`: prints the numbers this document quotes, read from the built store, one labelled block each.

> ### Guess first (ungraded)
>
> Write your guesses down *before* you read on. They are not graded. The point is to find out where your picture of option data is wrong.
>
> 1. **What share of the 2010-2012 OptionsDX chain survives a zero-bid filter?** (One row per contract, calls and puts.)
> 2. OptionsDX has 12 snapshot dates on days the market was shut. **Its `UNDERLYING_LAST` on those dates: whose close is it, and how many cents off?**
> 3. **On a normal day, how far is OptionsDX's `UNDERLYING_LAST` from the official SPY close?** Give a typical gap and a worst gap.
> 4. DoltHub records no snapshot time. You compute SPY's price from put-call parity on its quotes. **Will it match the close or the open better, and by how much?**
> 5. DoltHub's 2019 SPY rows are dated on Saturdays. **What do you think they are?**
> 6. **What share of the OptionsDX 2020-23 chain survives DoltHub's sampling mask?**
> 7. You run `dolt status` on a database. **Does it write to the database folder?**
>
> Answers are in "Measured results".

---

## What we built and why

M1 turns two vendors' option chains into one clean table, `option_quotes`, with one row per (`source`, `quote_date`, `osi_symbol`). Every quote problem is a bit in a 13-bit `quality_flags` mask; no quote is deleted, except rows the calendar drops. The calendar comes from SPY's own daily bars, so a vendor cannot invent a trading day. A quality gate stops the build if the report looks broken. A sampling mask replays DoltHub's thin listings on the dense OptionsDX chain, and a cross-vendor check measures how far the two vendors agree. The store is parquet read with DuckDB, written byte-deterministically. The later layers exist as empty modules with a `MarketView` that refuses to look ahead, and an import test that keeps strategies and signals away from the store.

What a user can now do: run `tools/build_data.py`, get 19,022,008 flagged quotes for 2010-2026 [report, "rows per source"], and know for every row what is wrong with it.

## Why this design

| Choice | Alternatives | Why this one | What it costs |
|---|---|---|---|
| Run every dolt call in a private mirror, a `cp -a` copy of the shared clone; never in the clone | Run `dolt sql` on the clone; an `unshare` overlay of the clone (M1's first choice, replaced on 2026-10-29) | Even `dolt status` writes to the database it runs in (10 files reopened, `.dolt/tmp/` created), and two projects querying one clone contend for those files. The copy takes all of dolt's writes. The project-wide rule of 2026-10-29 | 8.3 GiB of disk per copy, and the mirror goes stale if the shared clone is updated |
| Export DoltHub's SPY rows once to parquet | Query dolt on every build | The SELECT scans the whole 8.3 GiB database; the export from the mirror, checks included, took 166.8 s (107.6 s through the overlay). The build then reads about 2.6 MiB of parquet | A second copy of 185,910 rows, under `data/raw/` |
| Calendar = SPY bars (yfinance) | The chain's own dates; a hand-made holiday list | The chain has 12 closure dates and misses 26 sessions | One more download, and its own adjustment trap (`auto_adjust`) |
| Flag, do not drop | Delete bad quotes | A held contract with a zero bid still needs a mark (ADR-0009) | Every consumer must apply its own rule to the bits |
| Flags in numpy on whole cents; joins and LAG in DuckDB | All in SQL; all in pandas | SQL moves 19 M rows fast; the rules read like the ADR in numpy; cents make every boundary exact | Two languages in one step. Peak memory 18.7 GiB (20.0 GB) |
| Drop every non-session row, both vendors (round 2 of the review; default taken 2026-10-29, the owner can override it) | ADR-0009's relabel rule (move a closure snapshot to an empty previous session when its underlying matches that close; the first M1 build); a parity test for DoltHub | The one date the rule moved, OptionsDX 2022-06-20, had 06-17's prices and 06-20's contract list: none of the 516 contracts expiring 06-17, and 1,142 that 06-16 did not list. A relabel leaks contracts first listed on 06-20 into 06-17 and hides that day's expiries | 2022-06-17 has no OptionsDX snapshot; 11 DoltHub closure dates in 2020-24 whose previous session has no DoltHub row stay empty |
| Gate thresholds beyond the worst year seen, and every source required over its expected years, with a minimum per year by sampling regime | Fixed textbook thresholds; limits only; one minimum per source | Set after looking at the report, so today's data passes and a broken file fails. Limits alone passed an empty report (M1 review, R2). One DoltHub minimum, set on its Mon/Wed/Fri years, let a daily year lose half its dates (round 2) | A tripwire, not a statement that the data is good. The spans and regimes (OptionsDX 2010-23; DoltHub 2020-23, 2024, 2025, 2026 to date) are edited by hand when the data grows |
| Cross-vendor thresholds published as measurements: the share of dates inside each, pooled and by year | A pass/fail tolerance on a share of dates; a maximum per date | The thresholds were chosen on the same overlap dates they would judge (573 then, 572 after round 2), so a pass/fail could not fail (M1 review, R7). Four DoltHub dates in Nov-2021 have a broken vendor IV column, so a maximum would fail for ever | Nothing raises an alarm if a later build agrees less; a reader has to look |
| Byte-deterministic parquet (sorted, metadata stripped, fixed options) | Whatever the writer does | A build can be checked with a hash (ADR-0001 §7) | A full sort of 19 M rows on every write (part of the 15.3 s write step) |

## Code walkthrough

Read in this order. Each step names one file and line.

1. `src/volbt/config.py:118-130`. `work_dir()`: everything M1 writes goes under the repo's git-ignored `data/` folder, or `$VOLBT_WORK_DIR`, which may not resolve inside a shared DoltHub clone. Vendor sources stay at `data_dir()` (`:58-65`) and are only read; the one exception is this project's dolt mirror, `dolthub_mirror_dir()` (`:83-90`), under `project_cache_dir()` (`:78-80`). `shared_clones()` (`:93-109`) is every path that counts as the shared clone: the one `VOL_DATA_DIR` names and the default one, whatever the environment says. `raw_dir()` and `store_dir()` (`:133-140`) hang off `work_dir()`.
2. `src/volbt/data/schema.py:14-66`. The two pinned schemas: 33 OptionsDX columns with pyarrow types, 13 DoltHub columns with SQL types. `check_columns` (`:73-82`) compares position by position, so the error names the first column that differs.
3. `src/volbt/data/optionsdx.py:38-71`. The wide-to-long reshape, as SQL DuckDB runs on the parquet files. `long_rows_sql` checks every file's schema first (`:67-68`). `[C_SIZE]` "305 x 270" splits into a bid size and an ask size (`:52-54`).
4. `src/volbt/data/dolthub.py:104-119`. `mirror_dir`: dolt's target is the private mirror. A path that resolves inside a shared clone (directly, through `..` or through a symlink) is refused, and so is one that does not resolve under the project's cache folder (`MirrorPathError`). The clone test is `config.inside_shared_clone` (`src/volbt/config.py:112-115`), which resolves the path first.
5. `src/volbt/data/dolthub.py:135-156`. `run_dolt`: checks the target and the work folder before anything runs, refuses to run without dolt on PATH, then runs a plain `dolt` process with the mirror as its working folder and `DOLT_ROOT_PATH` inside the repo.
6. `src/volbt/data/dolthub.py:90-101`. `assert_read_only_sql`: only SELECT/SHOW/DESCRIBE, one statement, none of `INSERT`, `UPDATE`, `DELETE`, `CALL DOLT_`, `COMMIT`, `DOLT_`, `INTO`.
7. `src/volbt/data/dolthub.py:216-241`. `export_spy_rows`: `dolt status` on the mirror must be clean before anything is read (`:224-225`); then the schema check, one SELECT, and `dolt status` again, which must be clean before the parquet is written (`:239-240`).
8. `src/volbt/data/reference.py:86-106`. `fetch_spy`: `auto_adjust=False` (`:97-98`), and yfinance's cache pointed inside `work_dir` before the first request (`:91-94`). `parse_spy_csv` (`:109-132`) rounds prices to cents and refuses a file without `Adj Close`, the sign of an adjusted download.
9. `src/volbt/data/calendar.py:43-75`. `build_date_map`: per (source, vendor date), keep it as a session or drop it; nothing is moved (the module docstring says why the relabel rule was removed). `bisect_left(...) - 1` finds the previous session (`:67`), kept with its close as a diagnostic. `quality.non_session_check` (`src/volbt/data/quality.py:103-122`) compares each dropped date's underlying with that close.
10. `src/volbt/data/quotes.py:72-112`. `clean`: the date map joins the raw rows (`:79-87`); a window LAG fetches each contract's previous snapshot (`:88-95`); a duplicate key stops the build (`:96-101`); numpy then adds the OSI symbol and the flags (`:107-108`).
11. `src/volbt/data/flags.py:80-128`. `mid_flags` (bits 0-5) and `quote_flags` (all 13; bit 8, `RELABELLED`, is reserved and never set). Every price test is in cents: STALE is `200·|S − S_prev| ≥ S_prev` (`:108`), UNDERLYING_MISMATCH is `1000·|u − S| > S` (`:120`). VENDOR_IV_INVALID is a null or non-positive vendor IV (`:122-126`).
12. `src/volbt/data/osi.py:46-82`. `osi_symbol`, `parse_osi`, and `osi_symbols` for millions of rows.
13. `src/volbt/data/quality.py:34-72`. The gate thresholds, each with the worst value measured beside it, and the sources, spans and regimes every build must cover (`GATE_DATES_PER_YEAR`, `:49-63`). `gate` (`:146-194`) lists every failure, not just the first.
14. `src/volbt/data/mask.py:52-77`. `build_mask`: DoltHub's pairs on its dates; for `dolthub_daily`, Tue/Thu sessions DoltHub lacks take the last listing before them, minus expired expiries (`:71-72`).
15. `src/volbt/data/crossvendor.py:74-131`. `atm_iv30` (drops a point with an invalid vendor IV at either vendor, `:81-83`; total-variance interpolation between the two expiries around 30 days, `:100-104`) and `parity_spot` (median F_K over the 5 strikes nearest K\*, `:124-128`). `within_thresholds` and `by_year` (`:235-270`) report shares, with no verdict. `previous_session_test` (`:185-220`) is the labelled 2019 test.
16. `src/volbt/data/store.py:42-51` and `:111-142`. `write_parquet` strips metadata and uses fixed options; `write_table` sorts, then writes one file per hive partition.
17. `src/volbt/data/store.py:164-306`. The guard is the store's own code (`:164-217`): `plain_date` accepts only a plain `datetime.date` and rebuilds it, and `check_split` and `check_not_after` use it and return the rebuilt date, against the store's own `SPLITS` (`:176-180`). None of it calls `volbt.view`, the one module a strategy may import and rebind (round 2); `volbt.view` keeps the protocol, a read-only `SPLITS` and the published `exact_date` (`src/volbt/view.py:38-68`). `VIEW_SQL` (`:224-236`) is every query a view can run, each bounded by the view's own as_of, with no `adj_close`. `StoreView` keeps only private slots (`:252`); `view()` checks the split before it builds the view (`:295`), and its reader refuses any other query (`:298-304`).
18. `src/volbt/build.py:50-62`. `run`: read each input through the store, call a pure function, write through the store. M2 adds the real steps (`:39-47`).
19. `src/volbt/data/pipeline.py:156-225`. `build`: reference tables, clean, report, gate (`:195-199`), quotes, masks, cross-vendor, summary.
20. `tests/test_import_boundaries.py:163-414`. The AST checker: `binds`, `exempting` and `exempt_methods` decide when a method's first parameter is exempt; `with_aliases` follows `S = sys` and `m = vv`; `guarded_import_problems` is the allow-list of strategies and signals (`:281-310`); `violations` (`:313-367`) and `guarded_problems` (`:370-414`) apply every rule. ADR-0001's seven required mutants are `:466-472`; the M1 reviewer's 15 probes are `:501-520` and 17 variants `:522-543`; round 2's 23 probes are `:581-625`, and 31 tests of the new rules `:636-678`.

## Data flow

One OptionsDX quote, followed from the vendor file to the store. The 2022-06-20 rows (Juneteenth, a closure) are the interesting case: they stop at step 4.

1. **Vendor file** `$VOL_DATA_DIR/kaggle/spy-eod-2010-2023/spy_eod_2022.parquet`. One wide row per (date, expiry, strike), 33 columns. Its footer is checked against the pin (`optionsdx.check_file`).
2. **Raw long rows** (DuckDB view `raw_quotes`). The wide row becomes two rows, a call and a put, with the 18 `RAW_COLUMNS`. DoltHub's exported parquet joins by `UNION ALL`, with NULL for what it lacks.
3. **Snapshot summary**: one row per (source, vendor date) with its single `UNDERLYING_LAST` and row count. 2022-06-20 has 9,742 long rows and one `UNDERLYING_LAST`, equal to the 06-17 SPY close to the cent.
4. **Date map** (`calendar.build_date_map`, pandas, about 4,800 rows): 2022-06-20 is not a SPY session. Action `drop`, flags 128 (`NON_SESSION_DATE`), with `prev_session` 2022-06-17 and its close kept as a diagnostic: the quality report's `quality_non_session_dates` gives 0 cents, and that 06-17 has no snapshot of its own. Until round 2 this row was relabelled to 06-17, although its contract list is 06-20's; now 2022-06-17 is a session without an OptionsDX snapshot, and the 06-20 rows go no further. A quote on a session goes on:
5. **Clean stage** (DuckDB temp table, 19.0 M rows): joined to the date map and the SPY close, with each contract's previous bid, ask and close from a LAG.
6. **Flags and OSI** (pandas/numpy): `osi_symbol` and the 13-bit `quality_flags`. `vendor_quote_date` keeps the date the vendor wrote; with no relabel it equals `quote_date` on every row.
7. **Report and gate** (`quality.report`, `quality.gate`): counts per flag per source-year, calendar actions, rows per date, underlying gaps, and the non-session check. Pass, or stop here.
8. **Store** `data/store/option_quotes/source=optionsdx/year=2022/part-0.parquet`, sorted by (quote_date, osi_symbol). DuckDB reads it back with `hive_partitioning`.
9. **Views** for later milestones: `view(as_of=t, split=...)` reads it with `quote_date ≤ t`; `chain_mask` selects the DoltHub-sampled subset.

## Pitfalls met and how each is guarded

| Pitfall | How it showed up | Guard (`file:line`) |
|---|---|---|
| A "read-only" dolt command writes to the shared clone | In an overlay, `dolt status` rewrote 10 files in `.dolt/` with the same bytes and created `.dolt/tmp/`; a read-only bind mount made dolt refuse to start (`fslock ... read-only file system`) | `src/volbt/data/dolthub.py:104-156` runs dolt only in the private mirror and refuses a target inside the clone; `tests/test_dolthub_readonly.py` runs a real dolt on a throwaway clone's `cp -a` copy and checks the clone's listing is unchanged |
| A path that only looks private | A symlink, a `..` path or a `VOLBT_WORK_DIR` could point into the shared clone (M1 review). With `VOL_DATA_DIR` pointed elsewhere, the real clone passed as a mirror and as a work folder (round 2) | `src/volbt/config.py:93-130` resolves every path before comparing, against the default clone too, whatever the environment says; `src/volbt/data/dolthub.py:104-119` also requires the mirror to lie under the project's cache; `tests/test_config.py`, `tests/test_dolthub_readonly.py` |
| dolt writes outside the repo | dolt keeps its config and telemetry in `~/.dolt` | `src/volbt/data/dolthub.py:122-132` sets `DOLT_ROOT_PATH` inside `data/` with metrics off |
| A SELECT that writes | `SELECT DOLT_COMMIT('-am', 'x')` is a SELECT, and the `_` hides COMMIT from a word-boundary match | `src/volbt/data/dolthub.py:49` bans `DOLT_` and `INTO`; `tests/test_dolthub_readonly.py` tests each word alone. Found by the mutation run (below) |
| A second statement with no banned word | `SELECT 1; DROP TABLE option_chain` passes every word test | `src/volbt/data/dolthub.py:100-101`, one statement per call; a test whose only banned feature is the second statement (M1 review, R4) |
| yfinance adjusts prices by default | `Ticker.history()` and `yf.download()` default to `auto_adjust=True`: the 2022-06-17 close prints about $20 below the price that traded | `src/volbt/data/reference.py:97-98` passes `auto_adjust=False`; `parse_spy_csv` refuses a file without `Adj Close` (`:116`, which calls `check_yfinance_frame`); `tests/test_reference.py` spies on the call |
| yfinance writes a cache under `~/.cache` | By default it keeps `cookies.db` and `tkr-tz.db` in `~/.cache/py-yfinance` (`yfinance/cache.py:54` in the installed 1.7.0) | `src/volbt/data/reference.py:91-94` points the cache into `data/cache/` before the first request |
| Float boundaries | 420.42/420 − 1 is `0.001000000000000112` in floats, so a 0.10% gap would count as a mismatch | `src/volbt/data/flags.py:71-73` works in cents; `tests/test_flags.py` pins 420.42 as no mismatch |
| `WIDE` firing on a zero bid | 0.00/0.05 is "200% wide" | `src/volbt/data/flags.py:89` needs bid > 0; ADR-0009 test 3 row pins `[2]` |
| A closure snapshot that looks like the session before | 2022-06-20 carries the 06-17 close to the cent and 06-17 has no snapshot, so the relabel rule moved it; but it lists 06-20's contracts: 0 of the 516 expiring 06-17, and 1,142 that 06-16 did not list (round 2) | `src/volbt/data/calendar.py:43-75` drops every non-session row; `src/volbt/data/quality.py:103-122` reports the match as a diagnostic only; `tests/test_calendar.py`, `tests/test_pipeline.py` |
| A duplicate key after the calendar step | Would silently double a contract on one date | `src/volbt/data/quotes.py:96-101` stops the build |
| A strategy reads the store | `import volbt.data`, `sys.modules`, `getattr(view, "_store")`, `view._read`; after the review also `exec`, `eval`, `def peek(self): return self._read` in a plain function, `inspect`, `gc`, `pickle`, `pkgutil`, `pydoc`, `runpy`, `operator.attrgetter`, `builtins.__import__`; in round 2 `os.sys.modules`, `typing.sys.modules`, `S = sys`, `type(__loader__)(...).load_module()`, `typing.get_type_hints` on a string annotation, `timeit`, `subprocess`, `ctypes`, and the control cases | `tests/test_import_boundaries.py:163-414`, an allow-list in strategies and signals since round 2, with 23 mutants, the first round's 15 probes plus 17 variants, round 2's 23 probes and 31 rule tests, all reported. ADR-0001 test 1 states the threat model (a tripwire, not a sandbox) and lists what is still open |
| A strategy reads the future | `view.chain(t + 1)` | `src/volbt/data/store.py:216` raises `LookAheadError` (called from `chain`, `:273`); `tests/test_view.py` |
| A date that lies about its order | A `date` subclass whose `__gt__` returns False got the next day's chain (M1 review, R1) | `src/volbt/data/store.py:183-194` accepts only a plain `datetime.date` and rebuilds it; the rebuilt date is what reaches the SQL |
| A guard that reads names a strategy can rebind | `volbt.view.exact_date = <a day later>` moved a Tuesday view to Wednesday, with its bars, dividends and VIX; `SPLITS` was a plain dict (round 2) | `src/volbt/data/store.py:164-217` checks with its own code and its own `SPLITS`, calling nothing in `volbt.view`; `volbt.view.SPLITS` is read-only; `tests/test_view.py` rebinds `volbt.view` after the store is imported and, in a fresh interpreter, before |
| A price that encodes later dividends | `adj_close` on 2015-01-02 is 0.8239668 × close; the 47 later dividend factors multiply to 0.8239670 (M1 review, R1) | `src/volbt/data/store.py:224-236` serves no `adj_close` and no dividend after as_of; `tests/test_view.py` changes only the future, `adj_close` of every date included, and requires every view read to stay identical |
| A view reaches the store through a public attribute | A public `store` field would leak it | `__slots__` of private names only (`src/volbt/data/store.py:252`); `tests/test_view.py` walks the public attributes |
| The same rows give different bytes | Row order, pandas metadata | `src/volbt/data/store.py:42-51`, `:123-125`; `tests/test_pipeline.py` builds twice, once with input rows reversed. Two builds in one environment carry the same metadata, so that test passed with the metadata kept; `tests/test_store.py` now writes the same rows from pandas and from arrow and requires equal bytes (M1 review, R4) |
| A broken report is paired with old quotes | A failing gate after an earlier good build | `src/volbt/data/pipeline.py:195-199` deletes the old `option_quotes`; `tests/test_pipeline.py` |
| A gate that cannot fail | An empty report, a report with no DoltHub rows, and OptionsDX cut to 2022 all passed (M1 review, R2). In round 2, a total exactly at its minimum was never tested (the `<=` mutant survived), and a daily DoltHub year could lose half its dates | `src/volbt/data/quality.py:49-63`, `:151-153` (both sources present) and `:169-180` (dates in all, and per year by sampling regime); `tests/test_quality.py` tests every limit from both sides, each total exactly at its minimum |
| A test reads its expectation from the code it tests | My first banned-word test iterated over `dolthub.BANNED_SQL`, so removing a word shrank the test with it; that mutant survived | The test now lists the words itself (`tests/test_dolthub_readonly.py`) |

## Measured results

All on 2026-10-29. [build] and [report] are defined at the top. "Block" names the [report] block.

### The guesses, answered

| # | What | Command | Result |
|---|---|---|---|
| 1 | 2010-12 OptionsDX rows surviving a zero-bid filter | [report], block "guess 1" | **89.84%** (180,096 of 1,772,674 rows have `ZERO_BID`). Dropping any of BID_NULL/ASK_NULL/ZERO_BID/CROSSED keeps 88.81% |
| 2 | `UNDERLYING_LAST` on the 12 closure dates minus the previous session's SPY close | [report], block "calendar: OptionsDX" | **0 cents on all 12**. Every closure-dated snapshot carries the previous session's official close exactly |
| 3 | `UNDERLYING_LAST` minus the SPY close on normal dates | [report], block "UNDERLYING_LAST minus the SPY close" | Median \|gap\| **3 cents**, p95 12, p99 24, worst **162 cents** (2020-03-13). Exactly 0 on 476 of 3,496 dates; 37 dates beyond 0.10%; 7 of the 9 worst are in Mar-2020 |
| 4 | DoltHub's parity-implied spot against the close and the open, 2020-23 | [report], block "cross-vendor" | Against the close: median **+1.3 bp**, 5-95% −18.1 to +21.1 bp. Against the open: mean \|miss\| **69.8 bp**. So the snapshot is near the close |
| 5 | DoltHub's weekend-dated rows (2019-02-09 → 2020-01-04) | [report], block "labelled hypothesis test" | **Previous session's close**: the parity spot is closer to it than to the next session's close on 39 of 45 testable dates; median +4.3 bp from it, against a mean \|miss\| of 51.3 bp from the next close |
| 6 | OptionsDX 2020-23 rows kept by `chain_mask = dolthub` | [report], block "chain_mask" | **0.88%** (79,792 of 9,029,124) |
| 7 | Does `dolt status` write to `.dolt/`? | an overlay probe (see "The DoltHub clone") | **Yes**: 10 files reopened for writing (same bytes, new times) and a new `.dolt/tmp/`. The data hub saw the same with a plain `select` on 2026-10-29 |

### Rows, flags and the calendar

| What | Command | Result |
|---|---|---|
| Rows in `option_quotes` | [report], "rows per source" | OptionsDX **18,847,316** on 3,496 dates; DoltHub **174,692** on 1,196 dates (before round 2: OptionsDX 18,857,058 on 3,497) |
| OptionsDX long rows before cleaning | 2 × 9,468,584 wide rows (ADR-0009) | 18,937,168; minus 89,852 dropped = 18,847,316 |
| Closure-dated OptionsDX snapshots | [report], "calendar: OptionsDX" | **12 dates, 44,926 wide rows** (89,852 long). ADR-0009's count reproduces |
| Dropped | same | **All 12 dates**, 44,926 wide rows: 2012-10-29, 2012-10-30, 2018-12-05 and nine 2022 holidays, 2022-06-20 included. The first M1 build relabelled 2022-06-20 → 06-17 (4,871 wide rows); round 2 removed the rule |
| The non-session check (a diagnostic) | same, and `build_summary.json` `non_session_dates` | All 12 carry the previous session's close to the cent. 11 previous sessions have their own snapshot; 2022-06-20's, 06-17, has none |
| The 2022-06-20 check | same; the contract counts by DuckDB on the first M1 store | Its `UNDERLYING_LAST` equals yfinance's unadjusted 2022-06-17 close to the cent, and OptionsDX has no 06-17 snapshot. **But its contract list is 06-20's**: 9,742 long rows, first expiry 2022-06-21, none of the 516 contracts expiring 06-17 that 06-16 listed, and 1,142 (symbol, expiry) pairs 06-16 did not list, including two expiries first seen on 06-21's chain (2022-07-25 and 07-27). So it is dropped, and 06-17 is served as missing |
| Sessions without an OptionsDX snapshot, 2010-01-04 → 2023-12-29 | [report], "OptionsDX sessions without a snapshot" | 3,522 sessions; **26** missing against the vendor's dates (ADR-0009's count reproduces), and 26 after the calendar step: nothing fills 2022-06-17 (25 while the relabel did) |
| DoltHub vendor dates dropped | [report], "calendar: DoltHub" | **103 dates, 11,218 rows**: 47 Saturdays and 1 Sunday (2019-02-09 → 2020-01-04), and 55 market closures in 2020-26. ADR-0009 listed 3 closures; there are 55 |
| Flag totals, OptionsDX | [report], "flag totals" | ZERO_BID 1,373,457; VENDOR_IV_INVALID 1,277,951; STALE 459,728; EXPIRY_DAY 352,844; LOCKED 294,971; UNDERLYING_MISMATCH 187,588; WIDE 145,556; CROSSED 33,473; BID_NULL 19,842; ASK_NULL 19,842; NON_SESSION_DATE 0; RELABELLED 0 (reserved, never set); VOLUME_UNRELIABLE 13,503,828. Before round 2: 1,373,946; 1,278,142; 459,837; 145,706; 19,952; 9,742 each for bits 7 and 8; 13,506,087 |
| Flag totals, DoltHub | same | VOLUME_UNRELIABLE 174,692 (all rows, by rule); ZERO_BID 5,709; STALE 1,925; LOCKED 1,234; WIDE 74; VENDOR_IV_INVALID 70; CROSSED 27; every other bit 0 |
| What VENDOR_IV_INVALID counts | [report], "vendor IV" | OptionsDX: 1,055,303 null, 5,983 exactly 0, 216,665 negative (−0.0005 to −0.00001); before round 2 dropped the 2022-06-20 rows, 1,055,458, 5,984 and 216,700. DoltHub: 70 at 0, all on bid = ask = 0 quotes. Before the review the bit was `VENDOR_IV_NULL` and counted only the nulls |
| Tiny positive vendor IVs (not flagged) | same, the "tiny positive" line | OptionsDX **321,212** rows with 0 < IV ≤ 0.0005 and **482,104** with 0 < IV < 0.01, none flagged (321,252 and 482,144 on the first M1 store; the dropped 2022-06-20 file held 40 of each). DoltHub none: its smallest positive `vol` is 0.0203. Bit 11 is left as it is, null or ≤ 0: M2 recomputes IV from the quotes, so no vendor IV is used for pricing |
| Vendor IV above 5 (not flagged) | same | OptionsDX **16,262** rows (largest 55.77); DoltHub 0 (largest 4.296) |
| Most common masks | [report], "the most common flag masks" | OptionsDX: 512 (VOLUME_UNRELIABLE only) on 10,748,580 rows; 0 (clean) on 4,610,901; 2560 (VOLUME_UNRELIABLE, VENDOR_IV_INVALID) on 977,583 |
| Worst source-year shares (the gate's inputs) | [report], "worst source-year share" | OptionsDX BID_NULL 3.02% (2010), CROSSED 0.38% (2017), VENDOR_IV_INVALID 8.42% (2016), UNDERLYING_MISMATCH 3.99% (2013); DoltHub CROSSED 0.07% (2026), VENDOR_IV_INVALID 0.17% (2021), BID_NULL/ASK_NULL 0 |
| Snapshot dates per source and year (the gate's coverage inputs) | [report], "snapshot dates per source and year" | OptionsDX 245-252 a year, fewest 245 (2011), 3,496 in all (2022: 247). DoltHub, by sampling regime: Mon/Wed/Fri 2020-23, 143-145 a year (fewest 143, 2021); 2024, 173 (97 Mon/Wed/Fri dates to 09-09, none 07-30 → 08-09, then 76 of the 78 sessions from 09-11); 2025 daily, 248 of 250 sessions; 2026 to 10-26, 198 of 205. 1,196 in all, one of them in 2019 |
| Quality gate | [build], `quality_gate` | **Passed**, no failures |

**The quality gate thresholds, set after looking** (`src/volbt/data/quality.py:34-72`). Each sits beyond the worst source-year above, with headroom: OptionsDX BID_NULL and ASK_NULL ≤ 5%, CROSSED ≤ 1%, VENDOR_IV_INVALID ≤ 12%, UNDERLYING_MISMATCH ≤ 8%; DoltHub BID_NULL, ASK_NULL, CROSSED, VENDOR_IV_INVALID ≤ 1%; both sources present; at least 230 OptionsDX dates in every year 2010-2023 (fewest measured 245) and 3,300 in all (3,496). DoltHub's minimum per year follows its sampling regime, at about 80% of the fewest measured (round 2: one minimum of 120, set on the Mon/Wed/Fri years, let a daily year lose half its dates): 120 in each Mon/Wed/Fri year 2020-2023 (143), 140 in 2024 (173), 200 in 2025 (248) and 160 in 2026 to date (198); and 1,000 in all (1,196). At least 1,000 rows on every OptionsDX date (min measured 1,790) and 40 on every DoltHub date from 2020-01-06 (min 60); at most 15 OptionsDX and 130 DoltHub dropped dates (12 and 103); p99 \|UNDERLYING_LAST − close\| ≤ 50 cents (24). Market-describing flags (ZERO_BID, LOCKED, WIDE, STALE, VOLUME_UNRELIABLE, EXPIRY_DAY) have no limit.

### The cross-vendor check, 2020-01-06 → 2023-12-29

Vendor IVs (each vendor's own IV column), raw-mid parity, no de-Americanisation. Both vendors are measured on the (expiry, strike, side) points both list that day. For IV30, a point whose vendor IV is invalid (`VENDOR_IV_INVALID`: null, zero or negative) at either vendor is left out for both (`src/volbt/data/crossvendor.py:81-83`). Before the exclusion `atm_iv30` read the IV column only, so a zero or negative IV could have entered it. Running `overlap_table` on the rebuilt store with and without the exclusion, **0 of the 572 dates change** their IV30, for either vendor. **That 0 is vacuous, not evidence that the exclusion works** (round 2 of the review): on the overlap dates, 570 common points with an IV at both vendors carry the bit, and none of them lies within 1% of spot at 1-90 DTE (the nearest is 3.8% away), while IV30 reads only the strike nearest the close. On this data the exclusion has nothing near the money to exclude; `tests/test_crossvendor.py` shows it bites on rows built to need it. (Measured with a one-off script on 2026-10-29: `crossvendor.common_points` per overlap date, then `overlap_table` twice, the second time with the bit set to 0.)

| What | Command | Result |
|---|---|---|
| Overlap dates | [report], "cross-vendor" | **572** (DoltHub has 576 clean dates in the window; on 4 OptionsDX has no snapshot, 2022-06-17 among them since round 2; 573 before) |
| 30-day ATM IV, DoltHub minus OptionsDX | same | Median **+0.19 vol pts**, IQR +0.10 to +0.33, 5-95% −0.03 to +0.68 (n = 570). 97.4% of dates within 1.0 |
| Bad DoltHub vendor IV | same, the worst six | **2021-11-12, 11-17, 11-19, 11-22**: DoltHub IV30 0.67-0.73 against OptionsDX 0.12-0.15 (+52 to +60 vol pts). On 2021-11-12 an at-the-money 14-day call has DoltHub `vol` near 0.9 and `delta` near 0.13, while its quotes (about $4.1) are normal. The vendor's IV and greeks are wrong; the quotes are fine |
| DoltHub parity spot vs the SPY close | same | Median **+1.3 bp**, IQR −4.7 to +7.3, 5-95% −18.2 to +21.2, mean \|miss\| 9.2 bp |
| OptionsDX parity spot vs the close (the yardstick, stamped 16:00) | same | Median **−0.6 bp**, IQR −3.6 to +2.1, 5-95% −10.3 to +12.7, mean \|miss\| 5.1 bp |
| Both vs the SPY open | same | Mean \|miss\| 69.9 bp (DoltHub), 69.5 bp (OptionsDX) |
| Shares inside the bands | [report], the three share lines | IV: 88.4% within 0.5 vol pts, **97.4%** within 1.0. Spot: DoltHub 69.8% within 10 bp, **93.0%** within 25 bp; OptionsDX 87.1% and 97.7% |

**Thresholds chosen, and reported as measurements** (`src/volbt/data/crossvendor.py:51-59`). After the table above, two thresholds were picked: 1.0 vol point for the IV30 difference and 25 bp for DoltHub's parity spot against the close. They were chosen on these same dates (573 then; 572 after round 2), so a pass/fail on them could not fail (M1 review, R7). There is no verdict: the build reports the share of dates inside each, **97.4%** (of 570 dates with both IVs) and **93.0%** (of 572), in `build_summary.json` and in `data_quality.json`.

**The pooled shares hide the years** [report], "cross-vendor", the per-year lines:

| Year | Dates | IV30 within 1.0 pt | DoltHub spot within 25 bp | DoltHub spot vs close, median | OptionsDX spot vs close, median | Mean DGS3MO |
|---|---|---|---|---|---|---|
| 2020 | 144 | 94.4% | **85.4%** | +3.38 bp | **+1.08 bp** | 0.35% |
| 2021 | 143 | 95.8% | 95.1% | +2.22 bp | +0.05 bp | 0.04% |
| 2022 | 141 | 99.3% | 91.5% | −1.05 bp | −2.37 bp | 2.09% |
| 2023 | 144 | 100.0% | 100.0% | +0.12 bp | **−2.49 bp** | 5.28% |

- **2020 alone has 85.4% of dates within 25 bp,** well under the pooled 93.0%. A 90% tolerance on the pooled share would have passed while one year in four missed it.
- **OptionsDX's parity spot drifts from +1.1 bp (2020) to −2.5 bp (2023) as rates rise.** That is the American put premium: an American put is worth more than the European one, so C − P is smaller and the implied forward and spot come out low, more so at higher rates. The formula here is the European identity, labelled as such ("raw-mid parity, no de-Americanisation"); M2 removes the premium.

**What it says about DoltHub's snapshot time.** Its implied spot tracks the close, not the open, at about twice OptionsDX's scatter. That fits a snapshot at or near the close with noisier quotes. It cannot tell 15:45 from 16:00: we have no intraday prices.

### The labelled 2019 test (hypothesis, not overlap)

DoltHub's 48 weekend-dated rows run from 2019-02-09 to 2020-01-04. **Hypothesis:** they are the previous session's close. Test: compare each with the session before and the session after.

| What | Command | Result |
|---|---|---|
| Testable dates | [report], "labelled hypothesis test" | 45 of 48. On the other 3 the previous session (2019-03-01, 05-24, 06-07) is one of OptionsDX's 26 missing sessions |
| Parity spot vs the previous close | same | median +4.3 bp, mean \|miss\| 9.1 bp |
| Parity spot vs the next close | same | median −4.2 bp, mean \|miss\| 51.3 bp |
| Closer to the previous close | same | **39 of 45** |
| IV30 vs OptionsDX on the previous / next session | same | median +0.17 / −0.22 vol pts; mean \|diff\| 0.18 / 0.84 |

The same test on DoltHub's 55 closure-dated rows from 2020 finds 26 of 27 testable dates closer to the previous close (27 of 28 before round 2: 2022-06-17, now without an OptionsDX snapshot, was one of the testable previous sessions). **Conclusion:** DoltHub's non-session rows behave like the previous session's close. M1 drops them, as it drops every non-session date. 11 of those closure dates (2020-04-10 to 2024-06-19) follow a session with no DoltHub row of its own, so a parity-based relabel would fill them. Round 2's finding cuts against it: a parity test, like the $0.02 test, checks prices, and the OptionsDX case had the right prices and the wrong day's contract list. That is a decision for the owner (see "Decisions taken in M1").

### The DoltHub clone

| What | Command | Result |
|---|---|---|
| SPY rows exported from the mirror | `uv run python tools/build_data.py --export-dolthub --no-build`, then `data/raw/dolthub/option_chain_spy.export.json` | **185,910** rows on 1,299 dates, 2019-02-09 → 2026-10-26, in **166.8 s** (`ran_in`: the private mirror) |
| The parquet against the overlay-era export | `sha256sum data/raw/dolthub/option_chain_spy.parquet`, before and after | **identical** (`b12c4699…e293de`), so the build's input fingerprint did not move |
| `dolt status` on the mirror, before and after | same evidence file | `nothing to commit, working tree clean`, both times |
| Shared clone listing (path, size, mtime, ctime), 63 entries | `find ~/data/vol-projects/dolthub/options -printf '%P\t%s\t%T@\t%C@\n'`, before and after the export | **identical**. The mirror's `noms/manifest` moved to 2026-10-29 09:31, as dolt's housekeeping may |
| What dolt opened for writing, per call (in the M1 overlay, before the mirror) | the overlay-era evidence file, `overlay_writes_select` | 10 files, all rewritten with the same bytes: `noms/LOCK`, `noms/journal.idx`, `noms/manifest`, `noms/oldgen/LOCK`, the journal, and the same five under `stats/` |
| `dolt status` on an overlay (first probe, before the mirror rule; do not re-run it on the shared clone) | `unshare -rm sh -c "mount -t overlay ... && dolt status"`, then a listing of the upper layer | the same files plus a new empty `.dolt/tmp/` |
| A read-only bind mount instead (the same: a probe from before the mirror rule) | `unshare -rm sh -c "mount --bind ...; mount -o remount,ro,bind ...; dolt status"` | dolt refuses: `fslock new .../noms/LOCK: ... read-only file system` |

### Reference data, the store and the build

| What | Command | Result |
|---|---|---|
| yfinance adjustment | `uv run pytest -m network` (`tests/test_network.py`) | `history()` default equals `auto_adjust=True`. On 2022-06-17: the unadjusted Close equals the downloaded SPY file's close for that date to the cent, the adjusted Close is about $20 lower, and a dividend was booked that day; `yf.download()` also adjusts. Passed, 2 tests |
| SPY bars | [build], table `spy_bars` | 6,746 sessions, 2000-01-03 → 2026-10-28; 108 dividends |
| VIX3M | [report], "VIX3M" | **Available**: `cdn-api.cboe.com/.../VIX3M_History.csv`, 4,304 rows, 2009-09-18 → 2026-10-28 |
| DGS3MO | [build], table `rates` | 11,288 values, last 2026-10-27 (FRED lags a day) |
| Store size | `du -s --block-size=1 data/store` | 499,154,944 bytes: 476.0 MiB (499.2 MB) in 36 parquet files (the 36th is round 2's `quality_non_session_dates`) |
| Build wall time, full data | `/usr/bin/time -f "WALL %e s, MAXRSS %M KB" uv run python tools/build_data.py`, the rebuild after round 2 | **126.0 s** wall, `MAXRSS 19563276 KB`: peak 18.7 GiB (20.0 GB) RSS. Steps (`data/store/build_timings.json`): clean 51.9 s, cross-vendor 57.2 s, write quotes 15.3 s |
| Byte-determinism, full data | a second `pipeline.build()` into `data/store_check/`, then SHA-256 of every parquet file and `build_summary.json` in both stores | **37 of 37 files identical**, re-run after round 2. The second build and the hashing took 151.0 s (`MAXRSS 19755944 KB`, 18.8 GiB) |
| Tests, default run | `uv run pytest -q`, at the commit (2026-10-29) | `666 passed, 26 deselected`. The 26 deselected are marked: `uv run pytest -q -m real_data` gives `24 passed` (it needs the built store, the mirror and dolt, and runs `dolt status` and `DESCRIBE` in the mirror); the 2 `-m network` tests were not re-run after the review. The app: `npm run verify` gives 619 tests in 24 files. (Earlier figures in this doc's history, 412, 553 and 633, were stale counts from before later fixes.) |


### Mutation runs

Each mutant was written into the real source, its tests run, and the file restored (SHA-256 of every source file equal before and after). The 33 mutants: WIDE without `bid > 0`; STALE with `>` instead of `≥`; STALE at 1%; MISMATCH with `≥`; LOCKED without `> 0`; the volume era a day late; DoltHub volume treated as reliable; EXPIRY_DAY never set; the LAG ignoring the side; the relabel ignoring the session's own snapshot; a 3-cent tolerance; the next session instead of the previous; the relabel clash allowed; OSI strike × 100; the OSI root not padded; the schema checking names only; the guard missing COMMIT; the guard allowing any statement; dolt run without `unshare` and the export ignoring a changed clone (both tested the overlay code the mirror replaced); the store not sorting; the view exposing its store; `chain()` without the look-ahead check; `view()` without the split check; the gate limit `≥`; the pipeline ignoring the gate; the mask carrying every weekday; the mask carrying expired pairs; parity forgetting dividends; IV30 linear in vol; yfinance adjusted; `work_dir` following `VOL_DATA_DIR`; the build writing nothing. The first run killed 30. After closing the three gaps it found, the second run killed all 33. Four of the 33 (the relabel ignoring the session's own snapshot, the 3-cent tolerance, the next session instead of the previous, the relabel clash allowed) tested the relabel rule, which round 2 removed, so their sites are gone. The three:

- **"Two dates moving onto one session are both dropped"** had no test at all. Added `test_two_dates_that_would_move_onto_one_empty_session_are_both_dropped`. (That rule and its test went with the relabel in round 2; `test_two_closure_dates_in_a_row_are_both_dropped` keeps the Sandy dates.)
- **"Only Tue/Thu are carried"** was tested vacuously: the Monday in the test had no earlier listing, so nothing could be carried anyway. The test now has a Friday listing before it.
- **Removing `COMMIT` from the guard** survived twice. First because the other guards also stop a bare `COMMIT`, then because my new test read its list from the module. The search turned up a real hole: `SELECT DOLT_COMMIT(...)`. Fixed in the code and in the test.

The import-boundary test carries its own 23 mutants (ADR-0001's seven required ones, including `strategies → data`, and 16 more) and, since the review, the reviewer's 15 probes plus 17 variants, and since round 2 that round's 23 probes and 31 tests of the allow-list's rules; each is reported.

**The review's mutants (2026-10-29).** The reviewer found six mutants the suite did not kill: the SQL guard without its one-statement check, the LAG window without the expiry, IV30 on the outermost expiries, parity on 1 strike, the DoltHub minimum rows at 0, and pandas metadata kept in the parquet. Each now has a test that fails on it. Then every fix of the review was reverted on its own in the real source and its tests run: 33 reverts, all 33 killed, and every source file was restored byte for byte (SHA-256 of 61 files equal before and after). The list: the view serving `adj_close`; dividends not bounded by as_of; the guard trusting the argument's own `>`; `view()` trusting a lying as_of; the private reader running any SQL; the chain SQL without its own as_of bound; the gate without the presence check, without dates per year, without dates in all, and with DoltHub's minimum rows at 0; an empty underlying table passing; the AST rule exempting any name `self`/`cls`, allowing `exec`/`eval`/`compile`, allowing the reflection modules, catching `__import__` only as a bare name, and checking `sys.modules` only in strategies and signals; the other five of the six above, with parity also at 3 and 7 strikes; `VENDOR_IV_INVALID` back to null only; a `passed` key back in the cross-vendor JSON; the per-year median as a mean; and seven dolt-mirror reverts (a mirror inside the clone, the path check without `resolve()`, `VOLBT_WORK_DIR` inside the clone, a work folder passed to `run_dolt` unchecked, the export reading a dirty mirror, the export writing after a dirty status, dolt run in the shared clone). A control run showed why the metadata test was needed: with the metadata kept, the three old determinism tests still pass.

## After the review (2026-10-29)

The adversarial review (`docs/validation/01-ledger.md`) refuted five claims and found the shared clone's mtimes and a `VOLBT_WORK_DIR` hole. What changed, each with a test that fails without it:

| # | Refuted | Fix |
|---|---|---|
| R1 | `MarketView` blocks later data | The view serves no `adj_close` and no dividend after as_of; a date must be a plain `datetime.date`, rebuilt before the query; the private reader runs only fixed queries bounded by its own as_of (`src/volbt/data/store.py:164-306`; the date rule was in `src/volbt/view.py` until round 2 moved it). A metamorphic test changes only the future and requires every read to stay identical |
| R2 | The quality gate is sound | Both sources must be present, with minimum dates per year and in all; an empty underlying check fails (`src/volbt/data/quality.py:49-63`, `:146-194`). Every limit is tested from both sides |
| R3 | The AST test enforces the allow-list | `exec`/`eval`/`compile` and the reflection modules are banned in strategies and signals; `__import__` and `sys.modules` everywhere; `self` is exempt only as a method's first parameter (`tests/test_import_boundaries.py:163-414`; round 2 replaced the module ban list with an allow-list) |
| R4 | The mutants are killed | Six new tests, above |
| R5 | The 13 flags match ADR-0009 | `VENDOR_IV_NULL` became `VENDOR_IV_INVALID`, null or ≤ 0, same bit (`src/volbt/data/flags.py:122-126`) |
| R7 | The cross-vendor verdict | No verdict: shares inside the thresholds, pooled and by year |
| also | `atm_iv30` ignored `VENDOR_IV_INVALID` | A point invalid at either vendor is left out of IV30 for both (`src/volbt/data/crossvendor.py:81-83`). It moves no number on this data (0 of 572 dates on the rebuilt store; vacuous, see the cross-vendor section). Three tests fail with the exclusion reverted |
| also | The clone was left unmodified | Corrected in ADR-0009: its mtimes are from M0's direct dolt runs. dolt now runs only in a private mirror, and a `VOLBT_WORK_DIR` inside the clone is refused |

### Round 2 (2026-10-29)

The review of those fixes refuted three claims again and found more in the docs. Each fix has a test that fails without it: every fix was reverted on its own, or its rule removed, and its tests run (counts below are failing tests).

| # | Refuted | Fix | Proven failing |
|---|---|---|---|
| R1 | The view guard holds | It depended on `volbt.view`'s names: rebinding `exact_date` to add a day moved a Tuesday view to Wednesday. The store now checks with its own code and its own `SPLITS` (`src/volbt/data/store.py:164-217`), and `volbt.view.SPLITS` is read-only | old `view.py` + `store.py`: 4 tests; `SPLITS` a dict: 2; the store's checks calling `volbt.view` again: 2 |
| R3 | The AST rule enforces the allow-list | A ban list cannot: 20 of 23 new probes passed. Strategies and signals now have an allow-list of imports, with bans on attribute names, file readers, writes through an imported name and quoted annotations; every module refuses a computed `getattr` name (ADR-0001 test 1, which now states the threat model and the open paths) | the old checker: 51 of 119 tests; each new rule removed alone: 1 to 28 |
| 8 | The mirror guards hold | The protected path followed `VOL_DATA_DIR`. The default clone is refused whatever the environment says, and dolt runs only under the project's cache (`src/volbt/config.py:93-130`, `src/volbt/data/dolthub.py:104-119`) | old `config.py` + `dolthub.py`: 8 tests; the env clone only: 7; without the account's home: 1; without the cache check: 1 |
| also | The 2022-06-20 relabel | Its contract list is 06-20's. All 12 closure dates are dropped; the underlying check stays as a diagnostic (`quality_non_session_dates`); `RELABELLED` is reserved | old `calendar.py` + `flags.py`: 8 tests |
| R2 | The gate (minor) | The `<=` totals mutant survived, and DoltHub's daily years could lose half their dates. Totals tested exactly at their minimum; a minimum per year by sampling regime | `<=`: 2 tests; `< minimum - 1`: 2; 2024-26 back at 120: 4; the last year of a span skipped: 7 |
| R5 | `VENDOR_IV_INVALID` (caveat) | Unchanged on purpose (M2 recomputes IV); the tiny positive IVs are now reported, and the "0 of 573" is labelled vacuous | (a measurement) |
| 10 | The docs | Stale test count, citations and diagram links, ADR-0009's "nothing goes to `$VOL_DATA_DIR`", the docstrings naming `data-flow.mmd` | (docs) |

The reviewer's probes, re-run after the fixes: `ast3.py` reports all 23 cases caught (3 before); `mirror_guard.py` refuses every path into the real clone, with `VOL_DATA_DIR` pointed elsewhere too, and only the default mirror would run; `runtime_bypass.py` shows a view built for Tuesday staying at Tuesday with `volbt.view.exact_date` rebound. Its last three sections still reach the Store at run time (`os.sys.modules`, `__loader__`, `typing.get_type_hints`): Python allows that, and the allow-list is what stops a strategy from writing it. `mutants.py` kills every mutant whose site still exists, except two that cannot be killed: rebuilding a plain date from its year, month and day, and passing the argument rather than the rebuilt date, are both no-ops once the type is exactly `datetime.date`.

R6 (the app's `parseDataQuality` accepts contradictory files) is the app's, and is fixed with the app: it now refuses a gate marked passed with a row whose worst is beyond its limit, a share that is not counts / rows (to the 6 decimals Python writes), and flag names that are not the 13 of ADR-0009 §3 in bit order (`app/src/lib/contract.ts`). Each branch was removed in turn and the tests that name it failed (3, 4, 3 and 2 tests for the gate, the shares, the name count and the name order).

## Decisions taken in M1 that the ADRs did not fix

1. **DoltHub is read only in a private mirror** (a `cp -a` copy of the shared clone), and the loader refuses a target or work folder inside the clone. The ADR said "a read-only SQL session"; there is none that does not touch the files. M1 first used an `unshare` overlay of the clone; it was replaced on 2026-10-29 because two projects querying one clone contend for its files.
2. **Every non-session row is dropped, in both vendors** (round 2 of the review; default taken 2026-10-29, the owner can override it). ADR-0009's relabel rule moved one date, OptionsDX 2022-06-20, whose contract list is 06-20's; 2022-06-17 is served as missing. For DoltHub the 2019 test suggests a parity-based relabel; round 2 says a price test cannot see the contract list. Owner's call.
3. **"The previous session"**, kept for the diagnostic, is the session immediately before the vendor date.
4. **STALE's S is the SPY close** on the two snapshot dates (both vendors), and "previous snapshot" is the contract's own last quote, however many sessions back.
5. **`UNDERLYING_MISMATCH` cannot fire on DoltHub** (no underlying), and **`WIDE` needs a bid above zero** (ADR-0009's own test 3 requires it).
6. **"IV-related flags arrive in M2"** is read as ADR-0009's `iv_flags` (IV_FAIL, PARITY_OUTLIER, FORWARD_FALLBACK), a separate column of M2's `quote_iv`. Their bits are reserved in `flags.py:49-52` and never set. `VENDOR_IV_INVALID` (bit 11, null or ≤ 0) is one of the 13 quality bits and reads only the vendor's column, so M1 sets it. An IV above 5 is not flagged; it is counted.
7. **Prices are rounded to cents**: yfinance OHLC (float32 noise), and all flag tests.
8. **The cross-vendor ATM strike** is the listed strike nearest the SPY close, common to both vendors; the parity expiry is the nearest one at least 7 days out with 3 or more valid pairs.
9. **The gate thresholds** as above, set after looking, with DoltHub's minimum dates a year set per sampling regime, and **the cross-vendor thresholds published as measurements**, with no verdict.
12. **The view takes only a plain `datetime.date`.** A `datetime` or a `pandas.Timestamp` is refused with `TypeError`, not truncated: its time of day, or its time zone, would decide which calendar day the truncation lands on.
10. **The fixture parquet is tracked in git** through a `.gitignore` exception (`!/tests/fixtures/*.parquet`); every other parquet stays ignored.
11. **The later layers are packages** (`pricing/`, `signals/`, ...), so ADR-0001's relative-import mutant `from ..data import store` in `signals` means what it says.

## Not done in M1

- The engine, pricing and every later layer: stubs only, as planned.
- The `MarketView` exposes the OptionsDX and DoltHub chains, bars, rates and VIX; it does not yet serve `chain_mask`-filtered chains (M3 needs that).
- The perturb-the-future test (ADR-0001 test 6) needs signals (M4).
- The AST import rule is a tripwire, not a sandbox: it catches accidental and casual misuse in our own strategy code, and deliberate subversion of Python cannot be stopped statically. The behavioural guard is the perturb-the-future test, which strategies get in M4. ADR-0001 test 1 lists the paths still open, each checked on 2026-10-29: a method reached through an expression rather than a class name (`type(obj).peek(view)`), a module written through a container (`[vv][0].x = ...`), attributes of allowed modules the lists do not name (`np.f2py`, `dataclasses.copy`), a stdlib name rebound before the store is first imported, and run-time reflection if the rule is bypassed. The Store itself is still reachable at run time through the reader's closure and any store function's `__globals__`; only the AST rule stops a strategy from writing that.
- The app (`app/`) still reads the old `data_quality.json` shape; it is updated in a later step.

## Concepts used

- [Quality flags as a bitmask](../concepts/02-quality-flags-bitmask.md)
- [Put-call parity: the implied forward and the implied spot](../concepts/03-put-call-parity-forward-and-spot.md)
- [The OSI option symbol](../concepts/04-osi-symbol.md)
- [The sampling mask](../concepts/05-sampling-mask.md)
- [Querying a shared database without touching it: the private mirror](../concepts/06-private-dolt-mirror.md)
- From milestone 0: [background](../concepts/00-background.md) (why spreads and volume matter)

## Explain it back

Answer aloud first, then check against the code and the ADRs. They get harder as they go.

1. **The calendar, and why we drop the relabel.** Why does the calendar come from SPY bars and not from the chain's own dates? The 2022-06-20 snapshot carries the 06-17 close to the cent, and 06-17 has no snapshot of its own: why is it still dropped? What in its contract list shows it is not 06-17's chain, and what would a strategy have seen on 06-17 if it had been relabelled? What can a matching underlying tell you, and what can it not? Why does the underlying check survive as a diagnostic, and why is `RELABELLED` kept as a reserved bit instead of being removed?
2. **Flags, not deletions.** A short put you hold has a zero bid today. Trace what each consumer (marks, fills, the smile) should do with that row, and why deleting it in cleaning would change the result. Why does `WIDE` need a bid above zero, and why are all the price tests done in cents?
3. **STALE.** Define it precisely: which S, which "previous snapshot", which threshold, which comparison. Why is the LAG partitioned by (source, side, expiry, strike) and not by (source, strike)? What does a STALE flag on a deep out-of-the-money 0.00/0.01 quote mean?
4. **The shared clone.** Why is "only send SELECT" not enough to keep a dolt database unchanged? Why does a private `cp -a` mirror fix it, what does it cost, and when does it go stale? Why does the path check resolve symlinks and `..` before it compares, and why must the protected path not follow `VOL_DATA_DIR`? Why is "dolt runs only under the project's cache" safer than "never in the clone"? What does the before-and-after listing of the shared clone compare, and why include ctime?
5. **The cross-vendor check.** Derive `S = F·DF + PV(dividends)` from put-call parity. Why compare both vendors on the same (expiry, strike, side) points? What does "DoltHub's implied spot misses the close by a median +1.3 bp and the open by about 70 bp" tell you about its snapshot time, and what can it not tell you? Why are the thresholds published as measurements and not as a pass/fail, and what does the 2020 row show that the pooled share hides?
6. **The sampling mask.** What question does `chain_mask = dolthub` answer that a run on the full chain cannot? Why must the mask use DoltHub's clean dates, and why is a mask result an estimate and not a bound on the holdout distortion?
7. **Look-ahead by construction.** Name four ways a strategy could read the store despite the allow-list, and say which line of the AST test catches each. Name one it cannot catch. Why is the rule for strategies an allow-list, and what is its threat model? Why does the store's guard call nothing in `volbt.view`, and what did rebinding `volbt.view.exact_date` do before it was changed? Why does the concrete view keep its store in a private closure, why do its fixed queries carry their own as_of bound, and what does the public-attribute walk prove? Why is `adj_close` a look-ahead even though every row is dated on or before as_of?
8. **Determinism.** List what had to be fixed so that two builds give identical parquet bytes. Why does `build_summary.json` hold no clock time, and where did the wall times go?
