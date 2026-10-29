# Milestone 1: adversarial review and verifier pass — evidence-gated validation ledger

**Reviewer:** `adversarial-reviewer` (Opus), `evidence-gated-validation` skill. Tier 2 on numerics,
finance maths, statistics and version-sensitive APIs (yfinance, dolt, `unshare`/overlayfs,
DuckDB/pyarrow determinism); Tier 1 elsewhere. Single-context fallback (Mode 2): Channel A read the
installed library source and the ADR text; Channel B ran the reviewer's own probes against the
built store (read-only) and mutants in a scratch copy with its own venv.

**Verifier:** `verifier` (Sonnet) re-measured every number in `docs/milestones/01-data-layer.md`,
concept notes 02–06, the ADR-0009 M1 notes and `app/public/data/data_quality.json`, with its own
DuckDB and pandas queries.

**Recorded by the orchestrator** (the reviewer's rules forbid writing report files). Before acting,
the orchestrator re-ran the reviewer's probes for the three most severe refutations and saw the
same results:
- `gate.py`: `GateResult(passed=True, failures=[])` for the real report, for no DoltHub rows, for
  OptionsDX cut to 2022, and for an empty report;
- `adj.py`: adj/close at 2015-01-02 = 0.8239668, against the product of the 47 later dividend
  factors, 0.8239670;
- `ast_bypass.py`: 13 bypasses missed, including `exec`, `eval`, `self._read` and
  `builtins.__import__`.

**Scope:** the uncommitted milestone-1 tree against 046fd8f.

## Verdicts

> **Data notice.** The counts, dates and summaries of DoltHub rows in the tables below are derived from the DoltHub database `post-no-preference/options` (<https://www.dolthub.com/repositories/post-no-preference/options>), licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), and are shared under the same licence. The rest of this repository is MIT. See [DATA.md](../../DATA.md).

| # | Claim | Verdict | Key evidence |
|---|---|---|---|
| 1 | The DoltHub clone is never written. | SURVIVES | 25 guard candidates were tried; those that pass do not write in dolt 2.6.1. The listings before and after (size, mtime, ctime) are identical. |
| 2 | The calendar relabel rule: 1 relabelled, 11 dropped. | SURVIVES (wording) | On all 12 dates the underlying equals the previous close to the cent. The clash rule never fires on real data. |
| 3 | The 13-bit flags match ADR-0009. | PARTIALLY REFUTED | STALE, WIDE and the tick boundaries are exact. `VENDOR_IV_NULL` misses IV ≤ 0 (R5). |
| 4 | `option_quotes` is unique on its key, with 18,857,058 / 174,692 rows. | SURVIVES | Key-distinct. Every kept wide row gives one C and one P row. |
| 5 | The OSI symbol round-trips. | SURVIVES | 465,438 contracts, 0 mismatches, including 242 x.5 strikes. |
| 6 | The DoltHub mask equals DoltHub's listed pairs. | SURVIVES | 40,234 pairs both ways on 576 dates. |
| 7 | The cross-vendor distributions. | SURVIVES (caveats) | Medians reproduce. The tolerances were fitted to the same dates, so they cannot fail (R7). 2020 alone has 85.4% within 25 bp. |
| 8 | yfinance defaults to `auto_adjust=True`; the loader gets unadjusted closes. | SURVIVES (both channels) | Installed source and `inspect.signature` agree; the raw 2022-06-17 close is the price that traded, not the rescaled one. |
| 9 | `MarketView` blocks later data. | **REFUTED** | R1. |
| 10 | The AST import test enforces the allow-list. | **REFUTED** | R3. |
| 11 | The build is byte-deterministic. | SURVIVES | 36 of 36 files identical. The "keep pandas metadata" mutant survives (R4). |
| 12 | The quality gate is sound. | **REFUTED** | R2. |
| 13 | The fixtures hold no vendor data, and the schema pins bite. | SURVIVES | No real row shares the 6 quote and IV columns with a fixture row. |
| 14 | `data_quality.json` holds aggregates only, and 0.2.0 is right. | PARTIALLY REFUTED | The validator accepts contradictory files (R6). |
| 15 | The diagrams match the build. | PARTIALLY REFUTED | The ledger and JSON ERDs carry no "planned" marks, and `architecture` still says raw data lives under `VOL_DATA_DIR`. |
| 16 | Every `file:line` and explanation in the docs is right. | SURVIVES | 98 to 99 citations resolve; the concept arithmetic reproduces. |
| 17 | 460 tests pass, and the mutants are killed. | SURVIVES (counts) | 8 of the 33 claimed mutants were re-run; all were killed. 6 of the reviewer's own 15 survive (R4). |
| 18 | No vendor data is tracked or staged. | SURVIVES | Only the 7 synthetic fixtures are untracked and data-like. |

## Refutations, most severe first

- **R1.** `MarketView.spy_bars()` serves `adj_close`, whose level encodes every later dividend, holdout years included. A `date` subclass with a lying `__gt__` gets the next day's chain. The store is reachable through `inspect.getclosurevars`.
- **R2.** `quality.gate` passes an empty report, a report with no DoltHub rows, and a report with OptionsDX cut to 2022.
- **R3.** The import checker misses:
  - `self._read`, `exec`, `eval`, `pkgutil`, `pydoc`, `pickle`, `runpy`, `operator.attrgetter`, `inspect` and `gc` in strategies and signals;
  - `builtins.__import__` in any module.
- **R4.** Six mutants survive:
  - the SQL guard without its one-statement check;
  - the LAG window without expiry;
  - IV30 on the outermost expiries;
  - parity on 1 strike;
  - DoltHub minimum rows at 0;
  - pandas metadata kept in the parquet.
- **R5.** `VENDOR_IV_NULL` does not flag IV ≤ 0: 216,700 negative and 5,984 zero OptionsDX rows, and 70 zero DoltHub rows.
- **R6.** `parseDataQuality` accepts contradictory verdicts, worst values beyond their limits, shares that do not equal counts/rows, and unknown flag names.
- **R7.** The cross-vendor `passed` verdict cannot fail, because its tolerances were set on the same 573 dates. Publish them as measurements instead.
- **Also found:**
  - ADR-0009's "both stores were left unmodified" is false. The clone's mtimes are from 2026-10-28 14:11, from direct `dolt` runs in M0; the bytes are unchanged.
  - `VOLBT_WORK_DIR` could point inside the clone.

## Verifier: DISAGREE rows

| Where | Claimed | Measured |
|---|---|---|
| `01-data-layer.md:195` | 412 passed, 8 deselected | 460 passed, 25 deselected |
| `01-data-layer.md:40, :193` | peak 18.9 GB | `MAXRSS 18893112 KB` = 18.0 GiB (19.3 GB) |
| concept 05:8 | Mon/Wed/Fri only before Oct-2024 | also 6 Thursday and 5 Tuesday dates |
| `01-data-layer.md:219` | the fixture "is committed" | nothing from M1 was committed yet |
| `01-data-layer.md:58, :242` | three conditions | four |
| `01-data-layer.md:36, :37, :192` | 8.3 GB / 2.6 MB / 477 MB | binary units (GiB/MiB) |

The verifier found no stale `file:line` among the 99 citations it resolved.

## A rule change during the review (2026-10-29)

The hub reproduced that on dolt 2.6.1 even a plain `select` rewrites files in a clone, so two projects querying one clone contend for its files. The project now queries a private copy (`cp -a`) at `$VOL_DATA_DIR/vol-strategy-backtester/cache/dolt_mirror/options`. The `unshare` overlay that M1 first used is replaced.

## Resolution

See the milestone-1 commit message, which lists each refuted claim and its fix.

## Round 2: review of the round-1 fixes (2026-10-29)

**Reviewer:** `adversarial-reviewer` (Opus), `evidence-gated-validation`, Mode 2. Probes in the session
scratchpad (`egv/round2/probes/`). It never ran dolt, and it did not modify the repo.
**Orchestrator re-checks before acting:**
- `runtime_bypass.py` showed a monkeypatched `volbt.view.exact_date` moving a Tuesday view to Wednesday. It also showed `os.sys.modules`, `__loader__` and `typing.get_type_hints` reaching the Store.
- A DuckDB query showed the relabelled 2022-06-17 chain: 9,742 rows, minimum expiry 2022-06-21, and 0 contracts expiring 06-17, while 06-16 listed 516.

| # | Claim | Verdict | Key evidence |
|---|---|---|---|
| 1 | R1 closed: the view guard | **REFUTED** | The type guard holds for 9 argument types, pickling and deepcopy. But rebinding `volbt.view.exact_date` from a strategy moves the bound. |
| 2 | R2 closed: the gate | SURVIVES (minor) | 6 of 7 gate mutants killed. The totals-boundary mutant survives. DoltHub's 120 dates a year is loose for the daily years. |
| 3 | R3 closed: the AST rule | **REFUTED** | 20 of 23 new bypasses were missed, among them `os.sys.modules`, `__loader__`, `get_type_hints`, `subprocess` and `ctypes`. |
| 4 | R4: the six new tests kill their mutants | SURVIVES | All 6 killed, plus parity at 3 strikes. |
| 5 | R5: `VENDOR_IV_INVALID` | SURVIVES (caveat) | 1,278,142 = 1,055,458 null + 216,700 negative + 5,984 zero. 321,252 rows with 0 < IV ≤ 0.0005 are not flagged. "0 of 573 changed" is vacuous. |
| 6 | R6: `parseDataQuality` | SURVIVES as listed | 14 further contradictions are accepted: cross-sums, the pinned rule set, calendar actions. |
| 7 | R7: no cross-vendor verdict | SURVIVES | The 2020 share is 0.854. The OptionsDX median by year is +1.08, +0.05, −2.31 and −2.49 bp. |
| 8 | The dolt mirror guards | PARTIALLY REFUTED | With `VOL_DATA_DIR` elsewhere, the real clone passes as a mirror and as a work dir. |
| 9 | No vendor values | SURVIVES (scope); gaps | The scanner misses other date formats and values 4 or more lines from their date. The two real values it missed in prose, ADR-0010:107 and concept 00:362, were already present at 046fd8f. |
| 10 | The docs | **REFUTED** | Stale count and citation; links to deleted `.mmd` files; ADR-0009:121. |
| 11 | The gates | SURVIVES | 557 passed + 1 dolt test deselected; real_data 23 without dolt; vitest 566. |

**Also found:** the relabelled 2022-06-17 chain is the 06-20 vendor file (its contract list is 06-20's, its
prices are 06-17's). The rule is changed to drop all 12 closure dates (default taken 2026-10-29).

## Owner's data-policy decision (2026-10-29)

The owner decided: "Keep the strict rule: no real vendor values or data files … in any new commit,
made-up values in tests, and leave public history as it is." For this repo:
- the 17 dated vendor values quoted in prose in the pushed commit 046fd8f stay in history; there is no rewrite and no force-push;
- every real value in the milestone-1 tree is replaced with a made-up or coarse value;
- `tools/licensing/scan_real_rows.py` must print 0 hits before every push.

**One exception (owner, 2026-10-29):** "Allow small derived DoltHub tables (CC BY-SA, with the
attribution and licence notice) in the repos … The strict rule still covers Yahoo, Cboe, FRED and
OptionsDX/Kaggle data." So:
- a small table derived from DoltHub `post-no-preference/options`, such as a per-date summary, may be committed if a DoltHub attribution and a CC BY-SA 4.0 notice sit next to it, separate from the repo's MIT licence;
- raw `option_chain` rows are never committed.

**Replaced the same day (owner, 2026-10-29).** "This project is meant to show my technical
portfolio. Let's keep the data … Keep all the real data the apps and docs need in the repos,
including results and series built from the OptionsDX/Kaggle option chains, plus real values in
docs. No bulk raw files (GB-size dumps)." This replaces the strict rule above, so:
- the app JSON, small derived series and result tables are committed, and docs may quote real values;
- the downloaded vendor files are never tracked: raw CSVs, the Kaggle parquet chains, dolt clones, caches;
- a committed data file stays under about 10 MB and never over 50 MB;
- the made-up values in tests stay;
- `DATA.md` gives each source's terms. DoltHub-derived tables keep their CC BY-SA 4.0 notice;
- the push gate is now `tools/licensing/check_tracked_data.py`: no raw vendor file is tracked, and no data file is over the size limit. The real-value scanner is no longer a gate.

Public history stays as it is.
