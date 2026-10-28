# Architecture: index

This folder holds the design diagrams for the volatility backtester. The decisions behind them are in `docs/adr/`.

- Every diagram is plain Mermaid, so GitHub renders it in place.
- The four flow and ERD diagrams are **generated from the YAML specs** in `specs/`. Edit the YAML, then regenerate.
- The sequence diagram is written by hand.

## Diagrams

| File | What it shows |
|---|---|
| `architecture.mmd` | The components from end to end: vendor sources, chain store, `volbt` modules, run ledger, JSON export and the app. Generated from `specs/architecture.yaml`. |
| `data-flow.mmd` | How data moves: vendor tables → `option_quotes` → de-Americanised forwards, IV and smiles → `MarketView` → signals and the daily loop → ledger tables → analytics → JSON → app. It includes the M1 quality gate and the DoltHub sampling mask used by the surface-gap runs. Generated from `specs/data-flow.yaml`. |
| `process.mmd` | The research and backtest process: quality, pricing and attribution gates, the two adversarial reviews, the frozen config, validation, a single holdout run, and the publish gate. Generated from `specs/process.yaml`. |
| `data-model.erd.mmd` | Every stored table (raw vendor tables, reference data, clean chain, pricing build, per-run ledger) plus the Python→app JSON entities. Generated from `specs/data-model.erd.yaml`. |
| `engine-daily-loop.sequence.mmd` | One trading session of the engine, in the step order fixed by ADR-0001. Hand-written. |

### Validation of the Mermaid files (2026-10-28, re-run after the M0 review revision)

1. **YAML specs.** All four parse and pass a schema check:
   - every node and lane resolves, and no node is orphaned;
   - every `fk` names an existing `entity.column`;
   - every entity has at least one relation.

   To check that the checker itself catches errors, we injected an unknown edge endpoint, a bad node type, a broken `fk` and an orphan node. It reported all four and exited 1.
2. **Regeneration.** Before any spec was edited, the converter reproduced all four committed `.mmd` files byte-for-byte from their YAML. The four generated files were then regenerated from the revised specs. The ERD header now names the right spec file, `specs/data-model.erd.yaml`.
3. **Rendering.** All five `.mmd` files rendered with `@mermaid-js/mermaid-cli` 11.17.0 (`mmdc`) with exit code 0.
   - A malformed file exits with code 1. A `;` inside a sequence-diagram note did exactly that during this revision: Mermaid reads `;` as a statement separator.
4. **Rendered counts,** read from the SVGs: flowchart node groups, ERD entity and attribute elements, sequence numbers.

   | Diagram | Rendered |
   |---|---|
   | Architecture | 21 nodes |
   | Data flow | 27 nodes |
   | Process | 19 nodes |
   | ERD | 35 entities, 420 columns |
   | Sequence | 37 messages |

The YAML→Mermaid converter used for this is a throwaway script, rebuilt for this revision and kept outside the repo. The shared diagram toolkit will replace it. `rendered/` was regenerated from these revised `.mmd` files with `bash tools/diagrams/render_mermaid.sh`.

## Decision records (`docs/adr/`)

| ADR | One-line decision |
|---|---|
| [0001](../adr/0001-architecture-and-stack.md) | Daily event-driven engine over EOD snapshots. Parquet + DuckDB chain store. Each `volbt` module imports exactly its allow-list, to be enforced by an AST test with mutants. `volbt.build` is specified to own the pricing build, and `pricing` does no I/O. A `MarketView` look-ahead and split guard. Signals are causal, with a perturb-the-future test. In M0 only `config`, `contract` and `illustrative` exist; the rest, including the AST test, is specified and implemented from M1. Column-wise versioned JSON. The app never computes results. Runs are byte-deterministic. |
| [0002](../adr/0002-fill-model.md) | A signal from snapshot *t* fills at the *t+1* close. Fill price is mid ± k·half-spread, computed in integer cents, with k = 1 by default and a sweep over {0, 0.5, 1}. $0.70 per contract in fees. The hard cap of 100 contracts per line is the rule of record. A 10% volume cap, using the order date's volume `V_t`, is a 2021–23 diagnostic. Strategies trade standard monthly expiries. |
| [0003](../adr/0003-expiry-settlement-early-exercise.md) | Default exit at DTE ≤ 7. If held to expiry, exercise-by-exception applies at ≥ $0.01 ITM against the 4 pm close, with physical delivery. Early assignment happens exactly when exercise is optimal. Calls: `D > P_E + K(1−e^{−rτ})` before an ex-date. Puts: a CRR lattice, exercising when continuation − intrinsic ≤ $0.005, with the old inequality kept only as a pre-filter. |
| [0004](../adr/0004-mark-to-market.md) | Mark at mid when the quote is valid. Fallbacks: zero bid → ask/2; bad or missing quote → the day's surface (American lattice price near the money); no snapshot → the previous day's surface IV at the same moneyness. Wings use Lee-clipped linear total variance, and below the front expiry IV is held along k/√τ, all flagged. Never carry a price forward. Report NAV at mid and at liquidation value. Flag a day when more than 20% of NAV is model-marked. |
| [0005](../adr/0005-delta-hedge-frequency.md) | Hedge with SPY shares to zero delta at every close (sticky-strike Black-76 delta). Sweep 1, 2 or 5 sessions, or never, and bands of 0.5–5% of NAV. Cost is $0.01 per share per side. Book dividends on the hedge shares. |
| [0006](../adr/0006-greeks-limit-enforcement.md) | Units: gamma per 1%, vega per vol point, theta per calendar day, all in USD. Budgets: vega 0.25%, gamma 20%, theta 0.10% of NAV, with each position limited to 40% of each. A binding full-revaluation stress budget: loss ≤ 15% of NAV at (−10%, +20 vol) and ≤ 35% at the worst grid cell. Size by vega. Pre-trade orders are scaled to fit, or rejected. Breaches trigger at 110% and are cut back to 100%, gamma first, stress last. |
| [0007](../adr/0007-capital-base-and-returns.md) | $1M of fixed allocated capital; cash earns the DGS3MO rate. Margin is the Cboe strategy-based rule (15%, with 10% minimum; FINRA Interpretation 4210(f)(2)(E)/02), compared with NAV net of the short options' value. Hedge shares are charged 50% pre-trade and 25%/30% maintenance. Net requirement capped at 50% of NAV for entries. A margin call liquidates at *t+1* down to 80%. Returns are NAV-based, on a 252-session year. |
| [0008](../adr/0008-pricing-inputs.md) | European Black-76 on the forward implied by put-call parity (median of the 5 strikes nearest K\*), computed from quotes de-Americanised with a CRR lattice. Model marks add the premium back. r from DGS3MO. Dividends never enter as q. τ = calendar days / 365. Newton-then-bisection IV on de-Americanised OTM mids. |
| [0009](../adr/0009-data-sources-calendar-quality-flags.md) | The trading calendar comes from SPY bars. Bad quotes are flagged, not dropped, using a 13-bit flag. Out-of-sample DoltHub runs in surface mode. The distortion that mode causes is *estimated*, not bounded, by surface runs on OptionsDX masked by DoltHub's own 2020–23 sampling, reported separately for 2020–22 and 2023 (2023 is the closest analogue of the holdout). Cross-vendor checks run on the 2020-01-06 → 2023-12-29 Mon/Wed/Fri overlap. |
| [0010](../adr/0010-evaluation-protocol.md) | Splits: development 2010–2019, validation 2020–2023, holdout 2024–2026 (semi-blind). One cap rule of record (hard cap) in every split. At most two validation re-runs, each a trial. DSR headline = min over N_raw (trials plus logged design choices) and N_eff (return clusters at ρ\* = 0.5), with `n_trials` = N_raw. Regimes are defined by vol shock, not drawdown. Five named stress windows (Aug-2024 = `NO_DATA`). A full-revaluation spot × vol grid. |

## Interim YAML diagram schema

The specs follow this schema until the shared diagram toolkit takes it over. Unknown keys are errors.

```yaml
# flow
kind: flow
id: <string>
title: <string>
lanes: [{id: <string>, label: <string>}]
nodes: [{id: <string>, label: <string>,
         type: source|store|process|decision|artifact|ui|external,
         lane: <lane id>, note: <string, optional>}]
edges: [{from: <node id>, to: <node id>, label: <string>}]

# erd
kind: erd
id: <string>
title: <string>
entities: [{name: <string>, description: <string>,
            columns: [{name: <string>, type: <string>,
                       pk: true (optional), fk: "<entity>.<column>" (optional),
                       nullable: true (optional), note: <string, optional>}]}]
relations: [{from: <entity>, to: <entity>, cardinality: "1:1"|"1:N"|"N:M", label: <string>}]
```

How the converter maps the YAML to Mermaid:

| YAML | Mermaid |
|---|---|
| A lane | A `subgraph` |
| `source` | Stadium shape |
| `store` | Cylinder |
| `process` | Rectangle |
| `decision` | Rhombus |
| `artifact` | Parallelogram |
| `ui` | Rounded box |
| `external` | Subroutine box |

Mermaid will not accept some ERD characters, so the converter replaces them:
- **Column names** have their brackets and punctuation replaced with `_`. The raw name is kept in the attribute comment, for example `QUOTE_UNIXTIME "raw [QUOTE_UNIXTIME]"`.
- **Types** with brackets or parentheses get the same treatment. For example, `DECIMAL(7,2)` becomes `DECIMAL_7_2`.
