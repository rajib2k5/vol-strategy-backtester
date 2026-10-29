# Architecture: index

This folder holds the design diagrams for the volatility backtester. The decisions behind them are in `docs/adr/`.

- Every diagram is generated from a YAML spec in `specs/`. The specs use the shared diagram kit's schema, documented in the kit's [SCHEMA.md](https://github.com/rajib2k5/vol-diagram-kit/blob/7493b4b/SCHEMA.md). The kit is vendored in `tools/diagrams/` (see `tools/diagrams/README.md`), but its `SCHEMA.md` is not. Edit the YAML, then rebuild.
- `out/` is the generated set: for each spec a `.mmd`, `.svg`, `.png`, `.drawio` and `.lucid.xml` (the sequence diagram has `.mmd`, `.svg` and `.png` only), plus `.diagram-kit-manifest.json`. Do not edit these files; rebuild instead.
- The earlier hand-kept `*.mmd` files that sat in this folder, and `rendered/`, were **superseded by `out/`** and removed on 2026-10-29 (see "Removed files" below).

## Diagrams

| Spec | Output | What it shows |
|---|---|---|
| `specs/architecture.yaml` | `out/architecture.svg`, `.mmd` | The components from end to end: vendor sources, chain store, `volbt` modules, run ledger, JSON export and the app. Vendor sources in `$VOL_DATA_DIR` (read only; DoltHub through a private mirror) are shown apart from the downloads and built tables in the repo's git-ignored `data/`. |
| `specs/data_flow.yaml` | `out/data_flow.svg`, `.mmd` | How data moves: vendor tables → `option_quotes` → de-Americanised forwards, IV and smiles → `MarketView` → signals and the daily loop → ledger tables → analytics → JSON → app. The M1 lane is what the build does today (quality report, gate, `option_quotes`, `calendar_actions`, `chain_mask`, the cross-vendor check, `build_summary.json`, the `data_quality.json` export); lanes labelled planned are not built. |
| `specs/process.yaml` | `out/process.svg`, `.mmd` | The research and backtest process: quality, pricing and attribution gates, the two adversarial reviews, the frozen config, validation, a single holdout run, and the publish gate. |
| `specs/data_model_reference_erd.yaml` | `out/data_model_reference_erd.svg`, `.mmd` | Data model, part 1 of 3: the raw vendor tables, reference data (calendar, bars, rates, dividends, VIX), the clean `option_quotes` chain, the quality report and the cross-vendor tables, as M1 builds them (14 tables, columns from `DESCRIBE`), and the pricing build (`expiry_forwards`, `quote_iv`, `smile_fits`), labelled `(planned, M2)` because it is not built. 19 entities. |
| `specs/data_model_ledger_erd.yaml` | `out/data_model_ledger_erd.svg`, `.mmd` | Data model, part 2 of 3: the per-run ledger, `runs` and the 12 tables hanging off it. 13 tables, plus 5 `(partial)` copies. Nothing in it is built: each table is labelled `(planned, M3)`, `(planned, M4)` or `(planned, M5)`. |
| `specs/data_model_json_erd.yaml` | `out/data_model_json_erd.svg`, `.mmd` | Data model, part 3 of 3: the Python→app JSON contract entities (`json_*`) and how they come from the tables. 12 entities, plus 11 `(partial)` copies. Implemented: `json_manifest`, `json_manifest_dataset`, `json_illustrative_surface` (M0) and `json_data_quality` (M1). Every other entity is labelled `(planned, Mn)`. |
| `specs/engine_daily_loop_sequence.yaml` | `out/engine_daily_loop_sequence.svg`, `.mmd` | One trading session of the engine, in the step order fixed by ADR-0001. Converted from the hand-written Mermaid sequence diagram it replaced. |

**Why the data model is three diagrams.** The kit draws an ERD left to right only: it has no `direction` key, and a spec with `direction: TB` is rejected at validation (exit 2). One 35-entity spec built to a 6084 x 11828 px PNG (2,307,408 bytes) with relation lines crossing the whole page. Split in three, the PNGs are 3112 x 5202 (670,234 bytes), 4300 x 5986 (1,045,643 bytes) and 2842 x 6072 (648,667 bytes). A table another spec owns appears in a diagram as `name (partial)`, showing only the columns joined there, so every relation stays drawn. The earlier ERD PNG, rendered by `mmdc`, was 2,005,745 bytes.

## Build, check and verify

Run from the repo root. Details and the one-time setup for the render gate are in `tools/diagrams/README.md`.

```bash
# build: writes out/ (the kit refuses to overwrite files it did not write, so out/ must be fresh or the kit's own)
uv run --group diagrams python tools/diagrams/build.py docs/architecture/specs --out docs/architecture/out

# check: exit 1 and a list of files when out/ is stale; tests/test_diagrams.py runs this with --no-png
uv run --group diagrams python tools/diagrams/build.py docs/architecture/specs --out docs/architecture/out --check --no-png

# verify: render every .mmd with Mermaid 12.2.0 (GitHub's) and compare text; run before every commit that changes a spec
export DIAGRAM_KIT_MERMAID_JS=~/.cache/diagram-kit/node_modules/mermaid/dist/mermaid.min.js
export DIAGRAM_KIT_CHROMIUM=$HOME/.cache/ms-playwright/chromium-1234/chrome-linux/chrome
uv run --group diagrams --with playwright==1.64.1 python tools/diagrams/build.py docs/architecture/specs --verify-mermaid
```

Drop `--no-png` to compare the PNGs too; PNG bytes are verified on aarch64 only, so use `--no-png` on x86_64 runners.

## Known limits

From the kit's "Known limitations"; none of these was measured on these specs.

- **Long edge labels can sit over other edges.** A label pill wider than its card cannot be kept clear of the card's other edges. Several edge labels here are long (up to 58 characters in `process.yaml`). The kit's advice is to keep them short.
- **Edges closer than 12 px, in one case.** One of the kit's 150 fuzzed flows has three pairs of edges closer than 12 px. ERD relations are not separated at all: ports are fixed to column rows, so the 12 px rule is enforced for flows only.
- **No text wrapping.** Labels are one line, so long labels make wide cards. ERDs are left to right only.
- **Lucid, Figma and FigJam imports are untested.** `.drawio` was checked in draw.io's viewer only, not opened in the editor; `.lucid.xml` has not been opened in Lucid; FigJam's documented imports do not include SVG.
- **PNG bytes are verified on aarch64 only.**

## Removed files

On 2026-10-29 the earlier set was removed, because `out/` replaced it and the old files had fallen behind (the old ERD still named bit 11 `VENDOR_IV_NULL`; it is `VENDOR_IV_INVALID` since the M1 review):

- `architecture.mmd`, `data-flow.mmd`, `data-model.erd.mmd`, `engine-daily-loop.sequence.mmd` and `process.mmd` in this folder, and `rendered/` (their SVG and PNG copies);
- `tools/diagrams/render_mermaid.sh` and the toolchain it installed, `tools/diagrams/package.json` and `package-lock.json` (`@mermaid-js/mermaid-cli`, `mermaid` and `puppeteer`). Nothing else in the repo used them.

Every link to them was repointed to the matching file in `out/`: the root `README.md`, `docs/milestones/00-foundations.md` (its diagram table and the `data-flow.mmd:N` citations, whose line numbers were re-resolved in `out/data_flow.mmd`), `docs/adr/0001-architecture-and-stack.md`, `docs/validation/00-design-research-ledger.md`, `app/src/content/architecture.ts` (two comments), `tests/test_notebooks.py` (the `.gitattributes` checks now read `out/architecture.svg`, `out/architecture.mmd` and `out/architecture.png`) and one sublabel in `specs/data_flow.yaml`, which meant rebuilding `out/data_flow.*`. The removed files are in the history of the M0 commit (`9cd2f19`). The data model, which was one ERD, is now the three `data_model_*_erd` diagrams: there is no single replacement file.

## How the specs differ from the interim schema

The first specs used an interim schema; the kit's schema replaced it. What changed, so that a diff of the specs makes sense:

- **File names** must be identifiers, because the name is used for every output: `data-flow` is now `data_flow`, `data-model.erd` is three `data_model_*_erd` specs, and `engine-daily-loop.sequence` is `engine_daily_loop_sequence`.
- **Flow nodes:** `note` is now `sublabel`; `artifact` is now `output`; `decision` is now `process` (the kit has no diamond, so the five gates are no longer drawn as one; each is marked `# was type: decision` in the YAML, and the labels still name them: four end in "gate", the fifth in a question mark). The top-level `id` key is gone, and `direction: TB` is set.
- **ERD notes:** the kit has no field for an entity description or a column note. They are kept as comments in the YAML and no longer appear in the images; the earlier Mermaid ERD showed column notes. Vendor columns written `[QUOTE_DATE]` lose the brackets, `array<T>` is written `T[]`, and `DECIMAL(7,2)` is `DECIMAL_7_2` because a type cannot contain a comma.
- **ERD relations** are drawn from the referencing column to the referenced column, not between tables. 22 of the 54 earlier relations joined tables with no foreign key; each is drawn on a representative column and marked in the YAML. The kit has no many-to-many, so the 7 `N:M` relations are drawn as zero-or-many with `(N:M)` added to the label; `1:1` is `1..1`, as before. A foreign-key column with no relation of its own gets an unlabelled line (7 of them), so a composite key draws one line per key column.
- **Sequence diagram:** the two `Note over` lines became the note on the message that follows, and the shaded `rect` block around the start-of-day steps is dropped (the kit has `loop`, `opt` and `alt` only); its heading is the note on the first of its messages.

## Refresh after M1 (2026-10-29)

The M1 data layer was built after these specs were written, so `data_model_reference_erd.yaml` and `data_flow.yaml` were compared with `src/volbt/data/` and the built `data/store/` (a `DESCRIBE` of every table) and rewritten to match; `data_quality.json` was added to `data_model_json_erd.yaml`.

- **Built tables carry the built names and columns.** `spy_bars` replaces `underlying_bars`, `vix` and `vix3m` replace `vix_daily`, and there is no `trading_calendar`: a session is a `spy_bars` row, and `calendar_actions` records what happened to each vendor date. `option_quotes` has no `mid` and no `dte_days`, and adds `spy_close`, `vendor_quote_date` and the `source`/`year` partition columns. `chain_mask`, the four `quality_*` tables and the two `cross_vendor_*` tables are new. The two raw vendor entities were checked against the pinned schemas in `src/volbt/data/schema.py`: 33 and 13 columns, same names, order and types.
- **Unbuilt tables are marked.** `expiry_forwards`, `quote_iv` and `smile_fits` are labelled `(planned, M2)`; the flow's lanes after M1 are labelled planned. The `MarketView` is built (`StoreView`) but does not serve `chain_mask` yet, and the flow says so.
- **Consequential edits in two other specs.** The ledger spec's partial copies were renamed to `spy_bars` and `vix`, its `trading_calendar` copy was dropped, and its quote-mark relation now joins `option_quotes.bid`; `architecture.yaml`'s clean-store node lists the built tables.
- **Measured on the refreshed specs** (counted with `yaml.safe_load`): reference ERD 19 entities, 197 columns, 15 relations; ledger ERD 18 entities (13 + 5 partial), 188 columns, 22 relations; JSON ERD 23 entities (12 + 11 partial), 122 columns, 29 relations; data flow 6 lanes, 32 nodes, 48 edges. PNGs: reference 3532 x 10336 (1,059,913 bytes), ledger 4300 x 6010 (1,039,722), JSON 2944 x 7032 (794,160), data flow 5670 x 7548 (944,767). `--check` exits 0 and the Mermaid 12.2.0 render gate exits 0 on all 7 specs.

PNG sizes in the last bullet are as of this refresh; the next section gives them after the label edits. The counts in the section after it are those of the conversion, before this refresh.

## Planned labels, data locations and the graph (2026-10-29)

A review found that only this README said which tables are planned, and that two specs put the raw data in the wrong place.

- **Planned entities are marked in the diagram.** Every entity that is not built carries `(planned, Mn)` in its label, as the reference ERD's three do: the 13 ledger tables, `json_run` and the 7 future JSON datasets, and the `(partial)` copies of unbuilt tables (`smile_fits`, `runs`, `fills`, `positions`, `greeks_snapshots`, `daily_pnl`, `position_marks`). The JSON milestones are the ones in ADR-0001's dataset table. That table lists JSON datasets only, so a ledger table takes the milestone of the daily engine that writes it: M3 (ADR-0001), except `signals` (M4, `docs/milestones/00-foundations.md`) and `greeks_snapshots` (M5, the `greeks_timeline` row). `json_run` takes M2, the first results dataset that carries it. Built: `manifest.json`, `illustrative_surface.json`, `data_quality.json` and every reference-ERD table not labelled planned.
- **Where the data lives.** Vendor sources are only read, from `$VOL_DATA_DIR`; DoltHub is queried through a private mirror at `$VOL_DATA_DIR/vol-strategy-backtester/cache/dolt_mirror/options`, never the shared clone. Downloads and built tables are written to the repo's git-ignored `data/` (`volbt.config.work_dir()`): `data/raw/`, `data/store/`. `architecture.yaml` now has one node for each (`st_vendor`, `st_raw`); `data_flow.yaml` names the mirror, `data/raw/` and `data/store/` in the nodes and edges that read or write them.
- **Measured after the edits** (`yaml.safe_load`): architecture 6 lanes, 22 nodes, 26 edges; data flow 6 lanes, 32 nodes, 48 edges; the three ERDs have the same entities, columns and relations as before (19, 18 and 23 entities). PNGs: architecture 5318 x 6424 (700,388 bytes), data flow 6448 x 7548 (983,296), ledger ERD 4300 x 6054 (1,090,850), JSON ERD 3252 x 7076 (849,467); the reference ERD is unchanged (3532 x 10336, 1,059,913).
- **`graph/graph.svg` is regenerated.** `graphify export svg` needs matplotlib, which is not a project dependency, and scipy (networkx's spring layout). Neither goes into `pyproject.toml`; run it from a scratch folder with the pins on the command line, then copy the SVG here:

  ```bash
  cp docs/architecture/graph/graph.json "$TMP/graph.json" && cp graphify-out/.graphify_labels.json "$TMP/labels.json"
  (cd "$TMP" && uv tool run --from graphifyy==0.9.93 --with matplotlib==3.11.2 --with scipy==1.18.1 \
     graphify export svg --graph graph.json --labels labels.json)   # writes $TMP/graph.svg
  ```

  The export writes `graph.svg` next to the `--graph` file, hence the copy. The current SVG has 2,571 text elements, the 2,524 node labels of `graph.json` and 47 legend entries; the one before had 1,330. It is dense (9.8 MB); `graph.html` is the view to read.

## Validation of the generated set (`out/`, 2026-10-29)

Measured on aarch64 with the kit at `7493b4b`.

1. **Nothing was lost in the conversion.** Each interim spec was compared with its converted spec through the kit's own loader: every lane, node (id, label, note as sublabel, type, lane), edge, entity, column (name, type, pk, fk, nullable), relation (parent, child, label, cardinality) and sequence message (sender, receiver, label, kind, order) matched, with 0 mismatches. The counts:

   | Diagram | Interim specs | Converted specs |
   |---|---|---|
   | Architecture | 6 lanes, 21 nodes, 24 edges | 6 lanes, 21 nodes, 24 edges |
   | Data flow | 6 lanes, 27 nodes, 39 edges | 6 lanes, 27 nodes, 39 edges |
   | Process | 4 lanes, 19 nodes, 25 edges | 4 lanes, 19 nodes, 25 edges |
   | Data model | 35 entities, 420 columns, 58 pk, 86 nullable, 39 fk, 54 relations | 35 entities, 420 columns, 58 pk, 86 nullable, 39 fk, 61 relations (the 54, plus 7 drawn for fk columns that had none), plus 13 `(partial)` entities with 14 repeated columns |
   | Sequence (from the `.mmd`) | 11 participants, 37 messages, 2 notes, 2 `alt`, 1 `rect` | 11 participants, 37 messages, 2 notes, 2 `alt` |

2. **`--check`** exits 0 with and without `--no-png`: `ok: 7 spec(s) up to date in docs/architecture/out`.
3. **`--verify-mermaid`** (Mermaid 12.2.0) exits 0: `mermaid 12.2.0: 7 spec(s) checked: every title, label, sublabel, column, note and block label is drawn once in its own element (participants twice), and the drawn text, whitespace collapsed, reads as the spec text`.
4. **`tests/test_diagrams.py`** runs the `--check --no-png` line through `uv run --group diagrams`. Editing one file in `out/` (`process.svg`), or one label in a spec without rebuilding, made it fail with the file listed as `differs`.

## The earlier hand-kept Mermaid files (validated 2026-10-28, removed 2026-10-29)

The five `.mmd` files that this folder held before `out/` were validated on 2026-10-28, after the M0 review revision: the four YAML specs behind them passed a schema check that was itself tested with four injected errors (an unknown edge endpoint, a bad node type, a broken `fk`, an orphan node; all four reported, exit 1), and all five files rendered with `@mermaid-js/mermaid-cli` 11.17.0 with exit code 0 (21, 27 and 19 nodes in the three flow diagrams, 35 entities and 420 columns in the ERD, 37 messages in the sequence diagram). They were removed on 2026-10-29, see "Removed files". `out/` is validated in the section above.

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

## Diagram spec schema

The specs follow the diagram kit's schema (`kind: flow`, `erd` or `sequence`): [SCHEMA.md](https://github.com/rajib2k5/vol-diagram-kit/blob/7493b4b/SCHEMA.md) in the kit repo, at the vendored commit. It is not copied into this repo; the vendored code is in `tools/diagrams/`. The interim schema this section used to describe is gone, and "How the specs differ from the interim schema" above lists what changed.
