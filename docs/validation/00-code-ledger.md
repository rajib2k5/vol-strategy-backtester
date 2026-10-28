# Milestone 0: code adversarial review — evidence-gated validation ledger

**Reviewer:** `adversarial-reviewer` (Opus), following the `evidence-gated-validation` skill.
Tier 2 (documentation channel + runtime channel) on numerics, JSON/date semantics, nbformat,
uv/npm and three.js/R3F behaviour. Tier 1 elsewhere.

**Recorded by the orchestrator.** The reviewer's rules forbid it from writing report files, so it
returned the ledger as text. This file reproduces its verdicts. The orchestrator independently
re-checked the three most severe refutations before acting:
1. `git_state` on a throwaway repo with a truncated index and a modified file returned
   `('78023e0…', False)`, i.e. clean.
2. `no_arbitrage_checks` computes θ only from `dte` and fixed constants, so its calendar test only
   checks that `dte` is sorted.
3. `<Canvas>` in `SurfaceHero.tsx` has no `flat` prop.

```
target: vol-strategy-backtester working tree (no commits yet)
env:    Python 3.12.13, uv 0.11.25, numpy 2.5.4, nbformat 5.11.1, node 22.23.1 (V8 12.4),
        npm 10.9.8, vite 7.3.6, vitest 4.1.11, @react-three/fiber 9.8.2, three 0.186.1,
        git 2.43.0, Blender not installed
mode:   Channel A = separate documentation subagent; Channel B = runtime probes in the reviewer's
        context. Channel A's report was visible before most Channel B probes ran, so
        "dual-confirmed" is fallback-strength, not independent.
result: FAIL — 18 ledger rows rejected, 2 unresolved (bpy at runtime; notebook --check on
        Windows).
```

## Ledger

| ID | Claim | Tier | Channel A (docs) | Channel B (runtime) | Gate |
|---|---|---|---|---|---|
| G1 | pytest 79 passed | 1 | n/a | `79 passed`, rc 0 | ACCEPTED |
| G2 | notebook `--check` in sync | 1 | n/a | rc 0 | ACCEPTED |
| G3 | `npm run verify`: 271 tests, thresholds, build | 1 | n/a | 271/271, 99.44% lines on `src/lib/**`, built | ACCEPTED |
| T1 | Python suite kills targeted mutants | 1 | n/a | Butterfly strictness, calendar-from-θ and φ×1.0001 mutants survive once the notebook sync test is excluded. Byte-vs-JSON drift, trailing newline and `sys.path` mutants survive the full suite | REJECTED |
| T2 | App suite kills targeted mutants | 1 | n/a | 5 `SurfaceHero.tsx` mutants survive (buffers swapped, wrong index, axis moved, `FitCamera` removed, controls target) because the fiber mock never renders children | REJECTED |
| T3 | No source-grep tests | 1 | n/a | The notebook sync test pins source text (kills a comment-only edit) | REJECTED (scoped) |
| S1 | SSVI formula = Gatheral & Jacquier eq. 4.1 | 2 | eq. (4.1), arXiv:1204.0646v4 | Independent implementation, max rel. error 1.08e-13; falsifier 0.103 | ACCEPTED |
| S2 | Butterfly conditions are sufficient (Thm 4.2) | 2 | Thm 4.2; Lemma 4.2 | 0 of 13,000 admissible points with g(k) < 0; loosened falsifier finds 17 | ACCEPTED |
| S3 | Code checks only θ monotone | 2 | Thm 4.1 is iff | confirmed | ACCEPTED |
| S4 | Calendar check can fail for ascending DTE | 1 | n/a | 0 failures in 200,000 random inputs | REJECTED |
| S5 | `01-ssvi-surface.md` [run] numbers reproduce | 1 | n/a | all reproduce | ACCEPTED |
| S6 | G&J theorem/lemma numbering | docs | confirmed; Lemma 2.2 wording imprecise | n/a | ACCEPTED |
| S7 | `uv run python -c` cannot import volbt | 1 | n/a | imports fine, rc 0 | REJECTED (doc stale) |
| J1 | Real exported files pass the real TS validator | 1 | n/a | accepted; falsifier rejected | ACCEPTED |
| J2 | NaN/Infinity tokens rejected | 2 | ECMA-262 ParseJSON, RFC 8259 §6 | `SyntaxError` → `DataLoadError` | ACCEPTED |
| J3 | `1e999` rejected | 2 | parses to +Infinity | `ContractError` | ACCEPTED |
| J4 | Impossible dates rejected | 2 | spec silent; V8 rolls over | 2026-02-30, 2026-04-31, 2025-02-29, `T24:00` all accepted | REJECTED |
| J5 | Major-version handling | 1 | n/a | major OK; SemVer leading zeros accepted | ACCEPTED (minor) |
| J6 | Ragged/transposed grids rejected | 1 | n/a | confirmed | ACCEPTED |
| J7 | No dataset path escapes `./data/` | 1 | n/a | 0 escapes in 99,942 accepted fuzz paths | ACCEPTED |
| J8 | Python `allow_nan=False` / `1e999` semantics | 2 | confirmed | confirmed; test helper lets `1e999` through | ACCEPTED |
| J9 | An end-to-end Python→TS contract test exists | 1 | n/a | none | REJECTED |
| D1 | `-dirty` whenever code changed | 1 | `--porcelain` honours `showUntrackedFiles` | corrupt index, unreadable index and `showUntrackedFiles=no` all read clean | REJECTED |
| D2 | Exclude pathspec does not hide siblings | 2 | git `dir.c` | confirmed | ACCEPTED |
| N1 | Notebook byte-deterministic across processes | 1 | n/a | identical sha256 under 4 hash seeds | ACCEPTED |
| N2 | `--check` catches any byte drift | 1+2 | `write_text` writes CRLF on Windows | confirmed on Linux | UNRESOLVED (Windows) |
| N3 | Faithful when an assignment follows a function | 1 | n/a | duplicated `def`s | REJECTED |
| N4 | Keeps decorators / classes / `try` | 1 | n/a | silently dropped | REJECTED |
| N5 | nbformat id semantics | 2 | `validate` repairs duplicate ids randomly | a function named `constants` → non-deterministic hash | ACCEPTED (finding) |
| N6 | Function edit caught by `--check` | 1 | n/a | rc 1 | ACCEPTED |
| V1 | `iv[i][j]` → vertex `i*nK+j` at (k, iv, dte) | 1 | n/a | max error 2.9e-08; falsifier 0.887 | ACCEPTED |
| V2 | Winding faces +y; grid edges unique | 1 | n/a | 950/950 triangles, 994 unique edges | ACCEPTED |
| V3 | Tick labels at the ends of their axes | 1 | n/a | confirmed | ACCEPTED |
| V4 | On-screen colours equal the ramp anchors | 2 | R3F sets ACESFilmic unless `flat`; materials `toneMapped=true` | ACES shifts every anchor; stated contrast 2.11 → 1.88:1 | REJECTED |
| V5 | Blender reads the grid like the app | 1 | n/a | confirmed to ~3e-08 | ACCEPTED |
| V6 | 3D wiring is tested | 1 | n/a | 5 surviving mutants | REJECTED |
| H1 | Exact pins | 1 | n/a | confirmed; Node version unpinned | ACCEPTED |
| H2 | `uv sync --locked` reproduces | 2 | confirmed | rc 0 | ACCEPTED |
| H3 | `npm ci` reproduces | 2 | confirmed | identical tree | ACCEPTED |
| H4 | `uv_build==0.11.25` is real | 2 | on PyPI | builds; falsifier unsatisfiable | ACCEPTED |
| H5 | No private references | 1 | n/a | none found | ACCEPTED |
| H6 | No secrets | 1 | n/a | none found | ACCEPTED |
| H7 | `.gitignore` behaviour | 1 | n/a | confirmed | ACCEPTED |
| H8 | `npm audit` | 1 | n/a | 6 dev-only (3 moderate, 3 high); `--omit=dev` finds 0 | reported |
| W1 | ≥ 30 walkthrough citations correct | 1 | n/a | ~120 checked, all correct (one off-by-one) | ACCEPTED |
| W2 | Walkthrough numbers reproduce | 1 | n/a | confirmed, incl. DuckDB spot checks | ACCEPTED |
| W3 | Walkthrough explanations correct | 1 | n/a | 6 items wrong or overstated | REJECTED |
| W4 | Predict block precedes findings; questions unanswered | 1 | n/a | confirmed | ACCEPTED |
| B1 | Blender pure maths | 1 | n/a | confirmed | ACCEPTED |
| B2 | bpy calls valid for Blender 4.x | docs | confirmed against 4.0/4.2/4.5 API pages | no Blender | UNRESOLVED (runtime) |
| B3 | Caption inside camera clip range | 1 | n/a | confirmed | ACCEPTED |
| M1 | Renderer exits non-zero on a bad diagram | 1 | docs silent | rc 1; control rc 0 | ACCEPTED |
| M2 | Renderer fully pinned | 2 | CLI declares `mermaid ^11.14.0`, peer puppeteer range | resolved mermaid 11.17.2 | REJECTED |
| X1 | SHA-256 `source_commit` accepted by the app | 1 | n/a | regex `{7,40}` rejects it | REJECTED |
| X2 | Script-path test can fail | 1 | n/a | `sys.path` mutants survive | REJECTED |
| X3 | Notebook cell ids always unique | 1 | `validate` repairs | two different hashes | REJECTED |
| X4 | pytest sync test ≡ `--check` | 1 | n/a | CRLF passes pytest, fails `--check` | REJECTED |

## Refutations, most severe first

1. `git_state` fails open, so a modified tree can be stamped as a clean commit (D1).
2. The Python no-arbitrage tests are partly vacuous: boundary and calendar mutants survive without
   the notebook sync test (T1).
3. The calendar check cannot fail for any input the exporter can pass (S4).
4. On-screen colours are tone-mapped away from the ramp; the legend and contrast claims are wrong
   (V4).
5. The 3D wiring in `SurfaceHero` is untested (V6, T2).
6. Impossible dates are accepted by `contract.ts` (J4).
7. Notebook builder fragility: duplicated defs, dropped nodes, non-deterministic ids, CRLF
   (N3, N4, X3, X4).
8. Mermaid renderer not fully pinned (M2).
9. Walkthrough inaccuracies and stale "volbt is not installed" claims (W3, S7).
10. SHA-256 `source_commit` rejected; dev-only npm advisories; Node unpinned; BSM wording; M1/M2
    inconsistency; duplicated `__version__` (X1, H8, H1, known issues).

## Escalated, unresolved

- **B2:** needs Blender 4.2+ to run the render path. Risk: the render crashes, or picks EEVEE over
  Cycles.
- **N2 on Windows:** needs a Windows checkout to run build then `--check`.

## Not validated

A real WebGL pixel read-back (V4 rests on R3F configuration plus the shader formula); a real Blender
render; external regulatory and paper citations in the walkthrough.

## Resolution

Fixes and their before/after test evidence are recorded in the milestone-0 commit message and in
[`00-code-fixes.md`](00-code-fixes.md) once the fix pass completes.
