# Milestone 0: round-2 adversarial review — evidence-gated validation ledger

**Reviewer:** `adversarial-reviewer` (Opus), `evidence-gated-validation` skill, Tier 2 on numerics,
finance maths, statistics and version-sensitive APIs; Tier 1 elsewhere. Single-context fallback
mode: Channel A read primary sources (library source in `node_modules`, the Cboe Margin Manual,
finra.org Interpretation 4210(f)(2)(E)/02, the ADRs' own tests); Channel B ran the reviewer's own
probes (its own CRR/BAW pricers, a Crank–Nicolson PDE, DuckDB on OptionsDX, a SELECT-only export
of DoltHub's SPY rows, a DSR null simulation, mutants applied to a scratch copy and restored).

**Recorded by the orchestrator** (the reviewer's rules forbid writing report files). Before acting,
the orchestrator re-checked the three most severe refutations: `git update-index
--assume-unchanged` plus an edit made `git_state` return `(sha, False)`; ADR-0009 line 109 does say
the 2020–23 and 2024–26 DoltHub structure is "the same"; and `src/volbt/` holds only `config`,
`contract` and `illustrative`, so no `view`/`build` module or AST import test exists yet.

**Scope:** the fixes made after round 1 (`00-code-ledger.md`, `00-design-research-ledger.md`).

## Verdicts

> **Data notice.** The counts, dates and summaries of DoltHub rows in the tables below are derived from the DoltHub database `post-no-preference/options` (<https://www.dolthub.com/repositories/post-no-preference/options>), licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), and are shared under the same licence. The rest of this repository is MIT. See [DATA.md](../../DATA.md).

| # | Claim (the fix) | Verdict | Key evidence |
|---|---|---|---|
| 1 | `git_state` fails closed | PARTIALLY REFUTED | Corrupt index, `showUntrackedFiles=no`, ignored submodules and hung git → dirty; every old-behaviour mutant killed. Still reads clean under `--assume-unchanged`, `--skip-worktree`, `.git/info/exclude` and a global `core.excludesFile`. A timeout kills git but orphans its children. |
| 2 | SSVI calendar/butterfly checks | SURVIVES | 18 of 18 mutants killed without the notebook sync test; exporter refuses an inverted term structure. Note: G&J's calendar condition is at fixed forward log-moneyness. |
| 3 | Notebook builder | SURVIVES (minor) | 12 of 12 mutants killed. Minor: comments directly above a `def` are dropped; `X = 1; import os` makes an empty cell; `.gitattributes` does not pin `*.svg`. |
| 4 | `<Canvas flat>` and 3D wiring | SURVIVES (new survivors) | R3F source sets ACES unless `flat`; probe confirms toneMapping 4 → 0. All round-1 mutants killed. New survivors: removing `LabelProjector` (all axis labels stay hidden), flipping its y sign, camera position, `polygonOffset`, wire colour. |
| 5 | `contract.ts` validators, e2e test | SURVIVES (minor) | Impossible dates, hour 24, SemVer leading zeros, 6/65-hex commits rejected; 7/40/64-hex accepted. Untested: the explicit offset check at `contract.ts:115` (V8 already rejects those offsets). |
| 6 | ADR-0003 put lattice rule | SURVIVES (one premise contradicted) | Boundaries reproduce (old rule 421.70; lattice 409.02/408.78/408.66 by N; tolerance boundary 409.75; BAW 411.12); call closed form matches the lattice. "Only a European price exists in surface mode" (ADR-0003:90, :115) contradicts ADR-0008's lattice marks inside \|k\| ≤ 0.15. |
| 7 | ADR-0002 volume cap on order-date volume | PARTIALLY REFUTED | `V_t` is knowable at the *t+1* fill (volume change correlates 0.292 with same-day \|return\|, −0.017 next day). But the round-1 bias figures came from selecting contracts on the fill day. With order-date selection: clipped 50.9% (fill-day volume) vs 51.9% (order-day), flips 25.4%, corr −0.062, monthly clip 3.8%, weekly 57.2% vs 58.4%. "`V_t` is a little conservative (57.8% vs 49.7%)" is false; the flip rate stands. |
| 8 | ADR-0008 de-Americanisation | SURVIVES (caveats) | Forward error ≤ 0.07 bp in every case. Max IV error 0.0075–0.010 at 60 DTE (ADR says ≤ 0.007). Test 8 must pin the truth lattice N (N = 200 truth fails its own 0.01 bound at 0.029). The \|k\| ≤ 0.15 band edge fails the 0.02 gate at ≥ 60 DTE (0.023–0.127). |
| 9 | ADR-0007 net margin | SURVIVES | Cboe Margin Manual p. 30 ($4,110 requirement, $4,100 call, proceeds applied); FINRA 4210(f)(2)(E)/02 row confirmed; ADR tests recomputed. Unverified caveat: long options count at full value in NAV. |
| 10 | ADR-0006 stress budget | SURVIVES | Own full revaluation: 10%-OTM strangle capped at 65 by the worst cell; ATM straddles stay vega-bound (24; core cell allows 44); test 7 scales to 5. Minor: ADR-0002:116 "the hard cap can bind" for wings is false at the defaults. |
| 11 | ADR-0009/0004 surface-gap estimate | PARTIALLY REFUTED | The error numbers reproduce (7-DTE along k/√τ median 1.21; 19-strike grid flat 6.5–7.6 → Lee-clipped 1.14–1.21). "DoltHub 2020–23 structure matches 2024–26" is false on expiry churn: median listing share 0.286 (2020–22) vs 0.50–0.54 (2023 on); 111 expiries a year vs 36–44. |
| 12 | ADR-0010 protocol | SURVIVES (labelling) | PSR 0.9433, DSR 0.6319 reproduce. Null simulation: `dsr_eff` alone has up to a 35.7% false-positive rate with correlated variants; the headline min() is protected by `dsr_raw`, but ADR-0010:80 labels N_eff as `n_trials`. |
| 13 | ADR-0001 table, modules, causality | PARTIALLY REFUTED (docs) | The table is acyclic and keeps `strategies`/`signals` away from `data`. But the docs say `volbt.view`/`volbt.build` exist and an AST test "enforces" the rule; neither exists in M0. Design gaps: `sys.modules`/`getattr` bypasses; test 6 omits rates and dividends; the engine allow-list omits `config`. |
| 14 | Corrected data facts | SURVIVES | 44,926 rows on 12 closure dates; 9,775–58,087; 3,507 of 3,508 dates at 16:00:00; 84–97%; DoltHub 76–266 rows/date (2024), gap 07-30 → 08-09, 2 of 14 sessions, 11 missing weekdays. |
| 15 | PR/FAQ, §1.6, citations, `architecture.ts` | PARTIALLY REFUTED | 171 explicit citations resolve; ~60 content-checked, all correct. Wrong: PR/FAQ says PSR/DSR "correct for every configuration tried"; PR/FAQ gives "no open interest" as the reason against a volume cap; §1.6 habit 1 says the fill-day spread was harmful (it survived review); §1.6 calls the 7.0 vol-pt figure "DoltHub's real sampling" (it was a DoltHub-like grid; real mask: 8.9 all k, 0.52 within \|k\| ≤ 0.15). |
| 16 | Gates | SURVIVES | `pytest` 162 passed; notebooks up to date; `npm run verify` 22 files, 335 tests, build OK; `npm audit` 0. |

## Refutations, most severe first

1. ADR-0009: the 2020–23 DoltHub structure is not the same as 2024–26 on expiry churn, so the
   masked-run estimate mostly measures a different regime.
2. ADR-0002/0010 and §1.6: the volume-cap bias figures were a fill-day selection artefact.
3. `git_state` still reads clean under assume-unchanged, skip-worktree and exclude files.
4. The docs present `volbt.view`, `volbt.build` and the AST import test as existing.
5. `LabelProjector` wiring is untested.
6. PR/FAQ and §1.6 overstatements.
7. `dsr_eff` is labelled `n_trials` although it alone is anti-conservative.
8. ADR-0003's "only a European price" premise contradicts ADR-0008.
9. ADR-0008 accuracy caveats at 60+ DTE and an unpinned truth N in test 8.
10. Minor items in rows 3, 5, 10 and 13.

**Reviewer's verdict:** not publishable as-is; publishable after a short documentation pass and
the `git_state` fix. No redesign needed.

## Resolution

See the milestone-0 commit message, which lists each refuted claim and its fix.
