# Graph Report - vol-strategy-backtester  (2026-10-29)

> **Data notice.** This report, `graph.html`, `graph.json` and `graph.svg` index the repository's documents and quote DoltHub-derived figures from them (counts, dates, quantiles and summaries). They are derived from the DoltHub database `post-no-preference/options` (<https://www.dolthub.com/repositories/post-no-preference/options>), licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), and are shared under the same licence. Changes: we aggregated it into counts, shares and quantiles, compared it with OptionsDX and ran our pricing build on it; no quote row is reproduced. Only this file carries the notice in text: `graph.html`, `graph.json` and `graph.svg` hold none in-file, and are listed in [DATA.md](../../../DATA.md). `graphify` writes this report: a regeneration drops the notice, so add it again. The rest of this repository is MIT.

## Corpus Check
- 181 files · ~883,867 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 40 file(s) not represented in the graph (top: .mmd 12, (none) 6, .drawio 6)

## Summary
- 2524 nodes · 5454 edges · 128 communities (105 shown, 23 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 381 edges (avg confidence: 0.9)
- Token cost: 0 for this update (`graphify update`: code re-extracted by AST, no LLM). The first build, 2026-10-28, cost ~626,980 tokens across 3 semantic-extraction subagents (docs only); doc nodes of files that did not change are kept; docs written or edited since (for example docs/milestones/01-data-layer.md) were not re-read. `graph.svg` was regenerated from this `graph.json` on 2026-10-29 with `uv tool run --with matplotlib==3.11.2 --with scipy==1.18.1` (see `docs/architecture/README.md`).

## Graph Freshness
- Built from commit: `046fd8fe`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Chart & Surface Rendering
- Blender Hero Render Script
- Verdict FAIL: 13 material claims rejected, 2 unresolved
- Illustrative Surface Tests
- Architecture Diagram Content
- App Frontend Conventions
- Contract Envelope Tests
- Diagram Tooling & Validation
- Notebook Builder Tests
- build_notebooks.py
- SurfaceHero.test.tsx
- ADR-0001: Architecture and stack
- App Shell & Routing
- Communities (66 total, 10 thin omitted)
- About Page & Content
- M0 Foundations Walkthrough
- App Data Loader
- Fill Model & Evaluation Process
- contract.ts
- Fills, Fees & Expiry Rules
- Raw Data Sources & README
- App tsconfig Settings
- Config & Test Fixtures
- test_export.py
- App Package & ESLint
- volbt.engine: daily loop, fills, marks, expiry, hedge
- Event Loop & Early Exercise
- Delta Hedging & Greeks Inputs
- Vol Premium Background Research
- App Dev Dependencies
- volbt.build: pricing build
- Illustrative SSVI Module
- tsconfig.node Settings
- volbt.risk: greek and stress budgets, sizing, margin
- spec.py
- App JSON Contract & Metrics
- Variance Risk Premium Literature
- Diagram Tool Dependencies
- build_payloads
- Look-Ahead Guards & Calendar
- PR/FAQ Core Questions
- shutil
- Mark Cascade & Sparse Quotes
- Fill Timing Validation
- Data Sources & Calendar Gaps
- export_app_data.py
- Milestone 0: foundations walkthrough
- Margin & Liquidation Rules
- Greek Limit Enforcement
- Code walkthrough
- App npm Scripts
- dolthub.py
- Package Module Layout
- Deflated Sharpe Evaluation
- Blender Script Tests
- App Runtime Dependencies
- Mermaid Render Script
- Store
- quality_body
- tsconfig Root References
- Vite Build Config
- Node Engine Requirement
- Test Setup & jest-dom
- Quality Flags & Attribution
- Project Package Root
- cli.py
- mermaid_check.py
- store.py
- capture.mjs
- sequence.py
- test_export_data_quality.py
- reference.py
- test_fixtures.py
- make_fixtures.py
- DataQualityPage.tsx
- test_schema.py
- crossvendor.py
- pipeline.py
- LEARNING_LOG.md (milestone table and checkpoints)
- test_dolthub_readonly.py
- Svg
- mxgraph.py
- DataQualityPage.test.tsx
- schema.py
- layout
- erd.py
- pytest
- The SSVI implied-vol surface
- math
- test_flags.py
- MermaidRenderer
- osi.py
- pandas
- quotes.py
- MarketView
- test_calendar.py
- test_reference.py
- React 19 + TypeScript + Vite results viewer
- quality.py
- _number
- flags.py
- contract.test.ts
- Graph Report - vol-strategy-backtester  (2026-10-28)
- mask.py
- test_quality.py
- StoreView
- view
- Measured results
- build_date_map
- re
- test_mask.py
- colorRamp.ts
- SpecError
- Milestone 1: the option-chain data layer and quality filters
- volbt/build.py
- reachable_data_objects
- _marker
- conftest.py
- tools/screenshots
- Test fixtures

## God Nodes (most connected - your core abstractions)
1. `Communities (66 total, 10 thin omitted)` - 57 edges
2. `Store` - 36 edges
3. `Milestone 0: foundations walkthrough` - 33 edges
4. `docs/architecture/README.md (diagram index, validation, ADR summary)` - 32 edges
5. `Svg` - 30 edges
6. `Code walkthrough` - 29 edges
7. `build()` - 26 edges
8. `read_json()` - 26 edges
9. `vitest` - 25 edges
10. `layout()` - 24 edges

## Surprising Connections (you probably didn't know these)
- `God Nodes (most connected - your core abstractions)` --references--> `parseIllustrativeSurface()`  [INFERRED]
  docs/architecture/graph/GRAPH_REPORT.md → app/src/lib/contract.ts
- `Explain it back` --references--> `build_date_map()`  [INFERRED]
  docs/milestones/01-data-layer.md → src/volbt/data/calendar.py
- `Not done in M1` --references--> `MarketView`  [INFERRED]
  docs/milestones/01-data-layer.md → src/volbt/view.py
- `Page title and description meta: volatility-mispricing backtester, educational, not financial advice` --semantically_similar_to--> `Vol Strategy Backtester`  [INFERRED] [semantically similar]
  app/index.html → README.md
- `Code walkthrough` --references--> `run()`  [INFERRED]
  docs/milestones/01-data-layer.md → src/volbt/build.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Engine daily loop pipeline (fill, settle, mark, hedge, risk, early exercise)** — docs_adr_0001_architecture_and_stack_daily_engine_loop, docs_adr_0002_fill_model_next_close_fill_timing, docs_adr_0003_expiry_settlement_early_exercise_expiry_settlement, docs_adr_0004_mark_to_market_mark_rule_cascade, docs_adr_0005_delta_hedge_frequency_default_daily_hedge, docs_adr_0006_greeks_limit_enforcement_eod_breach_hysteresis, docs_adr_0007_capital_base_and_returns_margin_call_liquidation, docs_adr_0003_expiry_settlement_early_exercise_early_assignment_step [EXTRACTED 1.00]
- **Look-ahead defence stack** — docs_milestones_00_foundations_marketview_lookahead_guard, docs_milestones_00_foundations_import_allowlist_ast_test, docs_milestones_00_foundations_causal_signals_monthly_refit, docs_milestones_00_foundations_same_close_fill_bias [EXTRACTED 1.00]
- **M0 adversarial review artifacts** — docs_milestones_00_foundations_m0_adversarial_reviews, docs_validation_00_code_ledger, docs_validation_00_design_research_ledger [EXTRACTED 1.00]
- **Layered risk limits (greek, stress, margin, liquidation)** — docs_adr_0006_greeks_limit_enforcement_greek_budgets, docs_adr_0006_greeks_limit_enforcement_stress_loss_budget, docs_adr_0006_greeks_limit_enforcement_pretrade_check, docs_adr_0007_capital_base_and_returns_pretrade_margin_cap, docs_adr_0007_capital_base_and_returns_margin_call_liquidation, docs_adr_0006_greeks_limit_enforcement_eod_breach_hysteresis [EXTRACTED 1.00]
- **Quality, pricing, attribution and publish gates in the research process** — docs_architecture_specs_process_g_quality, docs_architecture_specs_process_g_pricing, docs_architecture_specs_process_g_attr, docs_architecture_specs_process_g_publish [EXTRACTED 1.00]
- **Surface IV construction chain for model marks** — docs_adr_0004_mark_to_market_surface_iv_construction, docs_adr_0004_mark_to_market_strike_extrapolation, docs_adr_0004_mark_to_market_tenor_extrapolation, docs_adr_0004_mark_to_market_cross_expiry_interp, docs_adr_0008_pricing_inputs_deamericanisation [EXTRACTED 1.00]
- **VRP measurement chain (RV, model-free implied variance, VIX, VRP)** — docs_concepts_00_background_realised_variance, docs_concepts_00_background_model_free_implied_variance, docs_concepts_00_background_vix_construction, docs_concepts_00_background_variance_risk_premium [EXTRACTED 1.00]

## Communities (128 total, 23 thin omitted)

### Community 0 - "Chart & Surface Rendering"
Cohesion: 0.06
Nodes (43): BASE_FOV, fovForAspect(), MAX_FOV, REF_ASPECT, labelTransform(), Ndc, ndcToPixels(), StageSize (+35 more)

### Community 1 - "Blender Hero Render Script"
Cohesion: 0.05
Nodes (41): add_camera(), add_labels(), add_lights(), add_surface(), _add_text(), Annotation, axis_annotations(), box_corners() (+33 more)

### Community 2 - "Verdict FAIL: 13 material claims rejected, 2 unresolved"
Cohesion: 0.10
Nodes (19): Python-to-app JSON contract (envelope and manifest), Pinned reproducible Mermaid renderer, Scene wiring tests via pure functions and test-renderer, source_commit stamp that fails closed, Strict contract validation in the app, Surface geometry mapping iv[i][j] to vertex i*nK+j, S4: calendar check cannot fail for any exporter input, D1: git_state fails open (+11 more)

### Community 3 - "Illustrative Surface Tests"
Cohesion: 0.05
Nodes (3): test_no_arbitrage_checks_hands_the_real_w_table_to_the_calendar_check(), test_phi_condition_of_gatheral_jacquier_theorem_4_1_holds_for_phi_eta_over_sqrt_theta(), test_total_variance_at_the_money_equals_theta()

### Community 4 - "Architecture Diagram Content"
Cohesion: 0.13
Nodes (29): ACTORS, ArchitectureLayer, DayStep, EDGES, [ENGINE, STORE, VIEW, FILLS, EXPIRY, MARKER, HEDGER, RISK, SIGNALS, STRAT, LEDGER], LAYERS, NODES, STEPS (+21 more)

### Community 5 - "App Frontend Conventions"
Cohesion: 0.12
Nodes (14): Illustrative implied-vol surface drawn with three.js (@react-three/fiber), tools/: notebook builder, app-data exporter, blender render scripts, tools/blender/README.md (Blender render scripts), Axes: x = log-moneyness k, y = days to expiry, z = implied vol, scaled to a 4 x 4 x 1.8 box, Written against the Blender 4.x Python API (3.2+ needed for per-vertex colour attributes), CLI options: --data, --out, --samples (64), --resolution (1920x1080), Cycles tried first, EEVEE fallback with identifiers read from the running Blender, Three suns (key, fill, rim) and a fitted 3/4 camera (+6 more)

### Community 6 - "Contract Envelope Tests"
Cohesion: 0.08
Nodes (26): commit_a_file(), hang_status(), arm(), repo(), run_git(), _running(), test_a_hung_git_status_counts_as_dirty(), test_a_hung_rev_parse_gives_no_commit() (+18 more)

### Community 7 - "Diagram Tooling & Validation"
Cohesion: 0.12
Nodes (29): ADR-0010: Evaluation protocol, docs/architecture/README.md (diagram index, validation, ADR summary), architecture.mmd: end-to-end components diagram, data-flow.mmd: how data moves from vendor tables to the app, data-model.erd.mmd: every stored table plus Python-to-app JSON entities, engine-daily-loop.sequence.mmd: one trading session in ADR-0001 step order (hand-written), ERD column-name and type sanitising for Mermaid (brackets and punctuation become underscores, raw name kept in comment), Interim YAML diagram schema (kind flow and kind erd, unknown keys are errors) (+21 more)

### Community 8 - "Notebook Builder Tests"
Cohesion: 0.08
Nodes (21): test_a_comment_above_a_function_does_not_land_in_the_previous_cell_or_twice(), test_a_comment_separated_from_a_function_by_a_blank_line_is_not_carried(), test_a_function_named_like_a_fixed_cell_id_is_rejected(), test_a_module_with_different_content_still_builds_with_stable_ids(), test_a_module_without_assignments_is_fine(), test_a_redefined_function_is_rejected(), test_a_string_expression_after_the_first_statement_is_not_mistaken_for_the_docstring(), test_an_assignment_after_a_function_does_not_copy_the_function_twice() (+13 more)

### Community 9 - "build_notebooks.py"
Cohesion: 0.06
Nodes (29): imported_modules(), mutable_src(), mutate(), row_and_package(), test_a_cycle_in_the_table_is_detected(), test_each_mutant_is_caught(), test_every_row_has_a_module(), test_imports_inside_a_package_are_allowed() (+21 more)

### Community 10 - "SurfaceHero.test.tsx"
Cohesion: 0.12
Nodes (13): SURFACE_LABEL, binValues(), Heatmap(), Histogram(), normalizeMatrix(), layoutLegend(), LineChart(), pad0 (+5 more)

### Community 11 - "ADR-0001: Architecture and stack"
Cohesion: 0.13
Nodes (15): ADR-0001: Architecture and stack, app/public/data JSON: manifest + datasets, volbt.analytics: metrics, attribution, regimes, stress grid, volbt.export + tools/export_app_data.py, volbt.signals: RV, HAR/GARCH, IV30, VRP spread, volbt.strategies: structures, entry and exit rules, MarketView as_of t, Derived tables: quote_iv, expiry_forwards, smile_fits (+7 more)

### Community 12 - "App Shell & Routing"
Cohesion: 0.16
Nodes (16): AppShell(), readRoute(), ShellPage, PAGES, shell(), STORE, memMap, memoryFallback (+8 more)

### Community 13 - "Communities (66 total, 10 thin omitted)"
Cohesion: 0.04
Nodes (57): Communities (66 total, 10 thin omitted), Community 0 - "Chart & Surface Rendering", Community 10 - "App Data Fixtures & Tests", Community 11 - "Engine Module Architecture", Community 12 - "App Shell & Routing", Community 13 - "Data Layer & Quality Flags", Community 14 - "About Page & Content", Community 15 - "M0 Foundations Walkthrough" (+49 more)

### Community 14 - "About Page & Content"
Cohesion: 0.13
Nodes (20): App(), APP_SLUG, DATA_SOURCES, DATA_SOURCES_NOTE, DataSource, DISCLAIMER_BODY, DISCLAIMER_HEADLINE, DOES (+12 more)

### Community 15 - "M0 Foundations Walkthrough"
Cohesion: 0.24
Nodes (14): Where this goes next (M1 data layer, M2 real surfaces), ADR-0001 Architecture and stack, ADR-0006 Greeks and limit enforcement, Causal signals with monthly refits, Daily event-driven loop (11 steps), Planned data flow M1 to M6, Module import allow-list AST test with required mutants, Milestone 1: data layer and quality filters (+6 more)

### Community 16 - "App Data Loader"
Cohesion: 0.14
Nodes (22): AppData, asContractFailure(), DATA_DIR, DataLoadError, describeLoadFailure(), EXPORT_COMMAND, FetchLike, getJson() (+14 more)

### Community 17 - "Fill Model & Evaluation Process"
Cohesion: 0.16
Nodes (12): LEARNING_LOG.md entry, Attribution and mark-quality gate, Pricing gate, Publish gate, Freeze config, Development runs 2010-2019, Holdout run 2024-2026 DoltHub, once, Metrics, DSR, regimes, stress windows, grid (+4 more)

### Community 18 - "contract.ts"
Cohesion: 0.16
Nodes (38): asRecord(), assertStrictlyIncreasing(), CalendarCounts, CellOf, checkCell(), ColumnKind, CrossVendor, DatasetEntry (+30 more)

### Community 19 - "Fills, Fees & Expiry Rules"
Cohesion: 0.11
Nodes (13): Option fees $0.70 per contract per side, Whole-package fills with no carry-over or legging, same_close diagnostic mode and same-snapshot premium, SEC Rel. 34-105153 (expiring options trade until 4:15 pm ET), Volume unreliable before 2021-01-04, OCC Exercise-by-Exception (Rule 805, $0.01 threshold), Expiry settlement by Ex-by-Ex at the official close, Pin risk flag (pin_band $0.50) (+5 more)

### Community 20 - "Raw Data Sources & README"
Cohesion: 0.09
Nodes (25): app/README.md (React viewer), ADR-0009: Data sources, trading calendar, quality flags and out-of-sample execution mode, Cboe VIX history CSV, DoltHub option_chain SPY 2019-2026, FRED DGS3MO, Kaggle OptionsDX SPY EOD 2010-2023, yfinance SPY bars and dividends, Raw vendor files under VOL_DATA_DIR (+17 more)

### Community 21 - "App tsconfig Settings"
Cohesion: 0.09
Nodes (21): compilerOptions, allowImportingTsExtensions, jsx, lib, module, moduleDetection, moduleResolution, noEmit (+13 more)

### Community 23 - "test_export.py"
Cohesion: 0.10
Nodes (26): assert_matches_a_fresh_export(), committed_quality_body(), committed_quality_body(), test_the_file_is_the_envelope_then_the_body(), test_the_manifest_lists_data_quality_with_the_current_schema_version(), lookup_for(), parse_finite_float(), read_json() (+18 more)

### Community 24 - "App Package & ESLint"
Cohesion: 0.11
Nodes (19): description, name, private, type, version, eslint, @eslint/js, eslint-plugin-react-hooks (+11 more)

### Community 25 - "volbt.engine: daily loop, fills, marks, expiry, hedge"
Cohesion: 0.18
Nodes (5): ADR-0003: Expiry, settlement, pin risk and early exercise, ADR-0004: Mark-to-market, ADR-0005: Delta-hedge frequency, instrument and cost, volbt.engine: daily loop, fills, marks, expiry, hedge, Milestone 3: Event-driven engine: marks, fills, expiry, hedging

### Community 26 - "Event Loop & Early Exercise"
Cohesion: 0.16
Nodes (13): Start-of-day LOT_REMOVED order cancel, Early assignment and exercise decision (step 10), European put necessary-condition pre-filter, expiry_events table, SPY quarterly ex-dividend schedule, Surface IV construction (own-expiry, strike, cross-expiry, tenor steps), Dividend cash flow on hedge shares, Model marks add the early-exercise premium back (|k| <= 0.15) (+5 more)

### Community 27 - "Delta Hedging & Greeks Inputs"
Cohesion: 0.13
Nodes (18): SPY hedge share commission and slippage (Decimal ROUND_HALF_UP), Delivered shares: hedge netting or unhedged liquidation, Vendor IV and greeks unreliable, Discrete hedging residual scaling with sqrt(dt), Gamma rent P&L formula, Hedge frequency sweep (time-based and band-based), Hull-White (2017) minimum-variance delta (variant), Sticky-strike Black-76 spot delta (+10 more)

### Community 28 - "Vol Premium Background Research"
Cohesion: 0.18
Nodes (11): Apr-2025 tariff shock, Aug-2024 carry-trade unwind and VIX quote spike, Augustin, Cheng and Van den Bergen (2021) Volmageddon and short volatility products, BIS Bulletin 90 (2024) Carry trade unwind of August 2024, BIS Bulletin 95 (2024) Anatomy of the VIX spike in August 2024, Feb-2018 Volmageddon, Mar-2020 crash, SEC DERA working paper (2025) Demystify the surge in VIX (+3 more)

### Community 29 - "App Dev Dependencies"
Cohesion: 0.11
Nodes (19): devDependencies, eslint, @eslint/js, eslint-plugin-react-hooks, eslint-plugin-react-refresh, globals, jsdom, @react-three/test-renderer (+11 more)

### Community 30 - "volbt.build: pricing build"
Cohesion: 0.22
Nodes (11): volbt.build: pricing build, volbt.data: load, calendar, quality flags, volbt.pricing: Black-76, IV, parity forward, CRR lattice, smile, Clean parquet + DuckDB, Quality gate, ADR or config change committed, State hypothesis and pre-register config grid, M1 ingest and quality flags (+3 more)

### Community 31 - "Illustrative SSVI Module"
Cohesion: 0.20
Nodes (8): atm_total_variance(), butterfly_conditions(), calendar_condition(), iv_grid(), no_arbitrage_checks(), phi(), sigma_atm(), total_variance()

### Community 32 - "tsconfig.node Settings"
Cohesion: 0.11
Nodes (17): compilerOptions, allowImportingTsExtensions, lib, module, moduleDetection, moduleResolution, noEmit, noFallthroughCasesInSwitch (+9 more)

### Community 34 - "spec.py"
Cohesion: 0.07
Nodes (24): _among(), _closest(), _construct_unique_mapping(), Edge, Entity, _erd(), resolve(), _flow() (+16 more)

### Community 35 - "App JSON Contract & Metrics"
Cohesion: 0.15
Nodes (12): Exported JSON datasets by milestone, Python-to-app JSON contract, volbt.analytics, volbt.export, cap_mode: hard_only vs volume, Return and risk-metric definitions (Sharpe, Sortino, Calmar), Bailey & Lopez de Prado (2014) deflated Sharpe ratio, Deflated Sharpe Ratio (DSR) = min(dsr_raw, dsr_eff) (+4 more)

### Community 36 - "Variance Risk Premium Literature"
Cohesion: 0.09
Nodes (30): Background: volatility mispricing in SPY options, Bakshi and Kapadia (2003) Delta-hedged gains, Broadie, Chernov and Johannes (2009) Understanding index option returns, Capital base and leverage problem, Carr and Wu (2009) Variance risk premiums, Corsi (2009) A simple approximate long-memory model of realized volatility, Why paper returns disappear: costs, margin, tails, Coval and Shumway (2001) Expected option returns (+22 more)

### Community 37 - "Diagram Tool Dependencies"
Cohesion: 0.12
Nodes (16): mermaid, @mermaid-js/mermaid-cli, dependencies, mermaid, @mermaid-js/mermaid-cli, puppeteer, description, engines (+8 more)

### Community 38 - "build_payloads"
Cohesion: 0.25
Nodes (4): build_payloads(), manifest_payload(), surface_payload(), write_json()

### Community 39 - "Look-Ahead Guards & Calendar"
Cohesion: 0.16
Nodes (12): Import boundary AST test with required mutants, LookAheadError, MarketView look-ahead and split guard, Signals-are-causal metamorphic test (test 6), SplitError, Calendar-day time to expiry (not vendor DTE), Vendor DTE daylight-saving artefact, Cross-vendor check 2020-01-06 to 2023-12-29 (+4 more)

### Community 40 - "PR/FAQ Core Questions"
Cohesion: 0.23
Nodes (11): ADR-0007 Capital base and returns, Net margin requirement compared with NAV, PR/FAQ: Vol Strategy Backtester, Central question: do SPY vol trades beat T-bills after realistic costs, Event-driven daily engine (six-step day), Fill timing and price (t+1, mid +/- k*half-spread, $0.70 fees), What it will not tell you and what we will not do, Open questions for the author (+3 more)

### Community 41 - "shutil"
Cohesion: 0.10
Nodes (10): build_envelope(), _git(), git_state(), _kill_process_group(), source_commit(), _check(), test_check_flags_a_hand_edited_output(), test_committed_outputs_match_the_specs() (+2 more)

### Community 42 - "Mark Cascade & Sparse Quotes"
Cohesion: 0.19
Nodes (12): Quote states at fill time (ZERO_BID, NO_QUOTE, surface fill), Surface execution mode (model fills), Cross-expiry interpolation of total variance, DoltHub held contracts usually not quoted on later days, Mark rule cascade (rules 0-4, mark_source), STALE_SURFACE mark (sticky moneyness), quote_iv table (iv_flags, eep), DoltHub sparse sampling (re-centred strikes, 3-4 expiries, none under 10 DTE) (+4 more)

### Community 43 - "Fill Timing Validation"
Cohesion: 0.21
Nodes (13): SPY options trade to 4:15 pm while SPY closes at 4:00 pm, ADR-0002 Fill model, Fill price mid +/- k*half-spread in integer cents, Pitfalls this design guards against, Same-close fills book quote noise as edge, Hard cap of 100 contracts, 10% volume cap as diagnostic, Volume unreliable before 2021 (null means unknown), Liquidity: 100-contract hard cap, volume cap as diagnostic (+5 more)

### Community 44 - "Data Sources & Calendar Gaps"
Cohesion: 0.18
Nodes (17): ADR-0004 Mark-to-market, ADR-0008 Pricing inputs, ADR-0009 Data sources, calendar and quality flags, American early-exercise premium biases the parity forward, Aug-2024 DoltHub gap (no SPY dates 2024-07-30 to 08-09), Calendar anomalies: closure-dated snapshots and missing sessions, DoltHub options dataset (2019-2026, sparse), OptionsDX SPY EOD dataset (2010-2023) (+9 more)

### Community 45 - "export_app_data.py"
Cohesion: 0.14
Nodes (12): test_a_store_without_the_report_is_refused_and_says_how_to_build_it(), test_every_number_in_the_file_is_finite_and_has_at_most_six_decimals(), numbers(), test_the_committed_files_equal_a_fresh_export_from_the_real_store(), test_the_real_export_reports_the_numbers_the_milestone_document_quotes(), test_the_real_gate_verdict_agrees_with_the_exported_limits_and_worst_values(), test_the_script_exits_1_and_prints_the_reason_when_the_store_is_not_built(), test_whole_numbers_are_written_without_a_decimal_point() (+4 more)

### Community 46 - "Milestone 0: foundations walkthrough"
Cohesion: 0.18
Nodes (13): ADR-0002: Fill model and fill timing, ADR-0006: Greek units, budgets and limit enforcement, ADR-0007: Capital base, margin, forced liquidation and return definition, ADR-0008: Pricing inputs (rate, forward, dividends, day count, European approximation, IV solver), Milestone 0: foundations walkthrough, ADR-0003 Expiry, settlement and early exercise, Early assignment: closed-form calls, lattice puts, M0 adversarial reviews (code and design) (+5 more)

### Community 47 - "Margin & Liquidation Rules"
Cohesion: 0.20
Nodes (10): Muravyev & Pearson (2020) effective spreads, Reduce-only orders never volume-capped, Santa-Clara & Saretto (option strategy returns, margin and costs), NAV_mid and NAV_liq series, Cboe Margin Manual, FINRA Interpretation 4210(f)(2)(E)/02, Hedge-share margin rates (50% initial, 25%/30% maintenance), Margin call, forced liquidation and ruin stop (+2 more)

### Community 48 - "Greek Limit Enforcement"
Cohesion: 0.27
Nodes (7): End-of-day breach reduction with 1.10x hysteresis, Greek budgets as fractions of NAV_mid (vega, gamma, theta), Pre-trade check: scale else reject, with closed-form quantity, risk_events table, Vega-notional sizing of entries, Fixed allocated capital of $1,000,000, Pre-trade net margin cap at 50% of NAV

### Community 49 - "Code walkthrough"
Cohesion: 0.23
Nodes (7): Code walkthrough, data_dir(), dolthub_options_dir(), kaggle_dir(), raw_dir(), store_dir(), work_dir()

### Community 50 - "App npm Scripts"
Cohesion: 0.22
Nodes (9): scripts, build, coverage, dev, lint, preview, test, test:watch (+1 more)

### Community 51 - "dolthub.py"
Cohesion: 0.07
Nodes (24): Assumptions, First principles, In this project, Reading a database without writing to it: the overlay mount, The maths, Where it breaks, assert_read_only_sql(), clone_listing() (+16 more)

### Community 52 - "Package Module Layout"
Cohesion: 0.44
Nodes (8): volbt.build (M2 pricing build), volbt.data (loaders, store, concrete MarketView), volbt.engine, volbt.pricing (pure functions, no I/O), volbt.risk, volbt.signals, volbt.strategies, volbt.view (MarketView protocol)

### Community 53 - "Deflated Sharpe Evaluation"
Cohesion: 0.31
Nodes (9): Bailey and Lopez de Prado (2014) The Deflated Sharpe Ratio, Deflated Sharpe Ratio for multiple testing, ADR-0010 Evaluation protocol, Evaluation protocol: fixed splits, N_eff and N_raw DSR, semi-blind holdout, NO_DATA row for Aug-2024, Reported outputs (excess return, PSR/DSR, P&L attribution, regimes, shock grid), Success metrics for launch, Vol shock: VIX up 25% or 5 points (+1 more)

### Community 55 - "App Runtime Dependencies"
Cohesion: 0.33
Nodes (6): dependencies, react, react-dom, @react-three/drei, @react-three/fiber, three

### Community 56 - "Mermaid Render Script"
Cohesion: 0.67
Nodes (5): mmdc(), render_one(), render_png(), render_mermaid.sh script, svg_width()

### Community 57 - "Store"
Cohesion: 0.09
Nodes (22): Store, test_a_later_step_can_read_an_earlier_step_s_table(), test_a_step_reads_and_writes_through_the_store(), real_store(), hashes(), make_inputs(), permissive(), test_a_rebuild_of_the_same_folder_is_byte_identical() (+14 more)

### Community 58 - "quality_body"
Cohesion: 0.33
Nodes (3): committed_copy(), exported(), quality_body()

### Community 66 - "cli.py"
Cohesion: 0.10
Nodes (23): _blocked(), build(), build_command(), check_out_dir(), compare(), find_specs(), generate(), load_all() (+15 more)

### Community 67 - "mermaid_check.py"
Cohesion: 0.10
Nodes (30): parent_marker_of(), compare_texts(), expected_texts(), _fits(), map_texts(), walk(), mmd_of(), Place (+22 more)

### Community 68 - "store.py"
Cohesion: 0.08
Nodes (13): Pitfalls met and how each is guarded, _as_arrow(), check_not_after(), check_split(), LookAheadError, SplitError, test_the_m2_steps_are_declared_but_not_built_yet(), test_2022_06_20_is_relabelled_to_06_17_and_the_rest_are_dropped() (+5 more)

### Community 69 - "capture.mjs"
Cohesion: 0.07
Nodes (27): @jsquash/oxipng, analysePng(), APP_DIR, argValue(), CHROMIUM_ARGS, freePort(), HERE, main() (+19 more)

### Community 70 - "sequence.py"
Cohesion: 0.11
Nodes (17): BlockGeom, build_scene(), walk(), _iter_messages(), _message(), MsgGeom, _open_head(), participant_width() (+9 more)

### Community 71 - "test_export_data_quality.py"
Cohesion: 0.11
Nodes (15): calendar_frame(), flag_counts_frame(), make_store(), rows_per_date_frame(), body(), committed_text(), test_a_cross_vendor_difference_with_no_values_is_refused(), test_a_failing_gate_is_reported_with_its_failures() (+7 more)

### Community 72 - "reference.py"
Cohesion: 0.11
Nodes (15): In this project, fetch_reference(), load_reference(), download(), fetch_cboe(), fetch_fred_dgs3mo(), fetch_spy(), _meta_path() (+7 more)

### Community 73 - "test_fixtures.py"
Cohesion: 0.11
Nodes (19): committed_files(), generated(), long_rows(), spy_bars(), test_a_closure_dated_row_carries_the_previous_sessions_close(), test_a_fresh_run_equals_the_committed_fixtures(), test_one_underlying_per_optionsdx_date(), test_optionsdx_bids_sit_at_or_below_asks_except_two_crossed_legs() (+11 more)

### Community 74 - "make_fixtures.py"
Cohesion: 0.11
Nodes (14): black_scholes(), cboe_text(), _cdf(), dolthub_describe_text(), dolthub_rows_text(), float32(), fred_text(), ny_offset_hours() (+6 more)

### Community 75 - "DataQualityPage.tsx"
Cohesion: 0.17
Nodes (24): CALENDAR_ACTIONS, CHART_FLAGS, CROSSVENDOR_NOTE, DATA_QUALITY_INTRO, FLAGS_NOTE, GATE_NOTE, SOURCES_NOTE, commitState (+16 more)

### Community 76 - "test_schema.py"
Cohesion: 0.14
Nodes (16): check_dolthub_schema(), SchemaError, test_the_generated_files_pass_the_schema_pin(), test_the_real_dolthub_option_chain_matches_the_pin(), _fixture(), test_a_changed_type_fails(), test_a_dropped_column_fails(), test_a_reference_file_with_a_changed_header_fails() (+8 more)

### Community 77 - "crossvendor.py"
Cohesion: 0.16
Nodes (12): add_differences(), atm_iv30(), check_tolerances(), common_points(), compare_pair(), _one_vendor(), overlap_table(), parity_spot() (+4 more)

### Community 78 - "pipeline.py"
Cohesion: 0.10
Nodes (13): distribution(), build(), export_dolthub(), _flag_totals(), _no_nan(), QualityGateError, raw_dolthub_rows(), _summary() (+5 more)

### Community 79 - "LEARNING_LOG.md (milestone table and checkpoints)"
Cohesion: 0.10
Nodes (18): Assumptions, First principles, Quality flags as a bitmask, The maths, Where it breaks, Assumptions, First principles, Put-call parity: the implied forward and the implied spot (+10 more)

### Community 80 - "test_dolthub_readonly.py"
Cohesion: 0.10
Nodes (13): _fake_dolt(), fake(), test_a_real_overlay_leaves_a_real_dolt_repo_untouched(), test_dolt_sql_refuses_before_running_anything(), must_not_run(), test_every_banned_word_is_refused_on_its_own(), test_the_command_always_goes_through_the_overlay(), test_the_export_refuses_a_clone_that_changed() (+5 more)

### Community 81 - "Svg"
Cohesion: 0.31
Nodes (14): draw_entity(), draw_legend(), draw_relation(), erd_svg(), draw_card(), draw_edge(), draw_lane(), draw_legend() (+6 more)

### Community 82 - "mxgraph.py"
Cohesion: 0.17
Nodes (14): type_text(), FlowScene, _Doc, _erd_columns(), erd_drawio(), flow_drawio(), _label(), _label_position() (+6 more)

### Community 83 - "DataQualityPage.test.tsx"
Cohesion: 0.11
Nodes (14): FILES, serve(), STORE, DATA, fakeFetch(), datasets, generated_at, schema_version (+6 more)

### Community 84 - "schema.py"
Cohesion: 0.13
Nodes (10): Data flow, check_file(), files(), long_rows_sql(), _side_sql(), check_cboe_frame(), check_columns(), _check_frame() (+2 more)

### Community 85 - "layout"
Cohesion: 0.15
Nodes (16): LaneRect, layout(), end_cross(), fits(), gap_between(), pav(), pill_clear(), room() (+8 more)

### Community 86 - "erd.py"
Cohesion: 0.20
Nodes (13): badge_w(), build_scene(), entity_size(), EntityGeom, ErdScene, key_badges(), pill_size(), RelationGeom (+5 more)

### Community 87 - "pytest"
Cohesion: 0.13
Nodes (10): test_unknown_mask_names_are_refused(), test_yfinance_adjusts_by_default_and_not_with_auto_adjust_false(), test_bad_contracts_raise(), test_bad_symbols_raise(), test_round_trip(), test_strike_field(), test_the_vectorised_builder_agrees_with_the_scalar_one(), test_the_real_reference_downloads_match_their_pins() (+2 more)

### Community 88 - "The SSVI implied-vol surface"
Cohesion: 0.17
Nodes (17): The SSVI implied-vol surface, Butterfly no-arbitrage (convexity in strike, g(k) >= 0), Calendar no-arbitrage (w non-decreasing in T), eta and phi(theta)=eta/sqrt(theta): curvature and wings, Gatheral and Jacquier (2014) Arbitrage-free SVI volatility surfaces, Lee (2004) The moment formula for implied volatility at extreme strikes, Certification only up to a maximum expiry t*_0, no_arbitrage_checks (butterfly and calendar flags) (+9 more)

### Community 89 - "math"
Cohesion: 0.19
Nodes (14): build_scene(), card_size(), EdgeGeom, lane_label_width(), LaneGeom, NodeGeom, params_for(), pill_size() (+6 more)

### Community 90 - "test_flags.py"
Cohesion: 0.24
Nodes (16): flags_of(), row(), stale_pair(), test_a_dolthub_row_is_always_volume_unreliable_and_has_no_underlying_check(), test_not_stale_when_spot_moves_a_quarter_percent(), test_not_stale_when_the_quote_moved(), test_null_quotes_are_not_stale(), test_one_row_per_flag() (+8 more)

### Community 91 - "MermaidRenderer"
Cohesion: 0.14
Nodes (6): check(), GateUnavailable, MermaidRenderer, setup_problem(), Verdict, verify()

### Community 92 - "osi.py"
Cohesion: 0.15
Nodes (10): Assumptions, First principles, In this project, The maths, The OSI option symbol, Where it breaks, osi_symbol(), osi_symbols() (+2 more)

### Community 93 - "pandas"
Cohesion: 0.20
Nodes (15): overlap(), parity_chain(), test_expiries_under_a_week_are_skipped_for_parity(), test_iv30_interpolates_in_total_variance(), test_iv30_needs_an_expiry_on_each_side_of_30_days(), test_only_points_both_vendors_list_are_compared(), test_parity_adds_back_the_dividend(), test_parity_recovers_the_spot_without_dividends() (+7 more)

### Community 94 - "quotes.py"
Cohesion: 0.22
Nodes (6): _arrow_dates(), clean(), clean_quotes(), snapshot_summary(), to_pandas(), test_the_dolthub_rows_parse_with_the_pinned_types()

### Community 96 - "test_calendar.py"
Cohesion: 0.26
Nodes (14): bars(), one(), raw(), snapshots(), test_a_date_before_the_first_session_is_dropped(), test_a_row_without_an_underlying_cannot_be_checked_so_it_is_dropped(), test_each_source_is_judged_on_its_own_snapshots(), test_sessions_map_to_themselves_with_no_flags() (+6 more)

### Community 98 - "React 19 + TypeScript + Vite results viewer"
Cohesion: 0.16
Nodes (15): app/index.html (Vite HTML entry), Module entry script /src/main.tsx, Page title and description meta: volatility-mispricing backtester, educational, not financial advice, #root mount element, Load-time contract validation (schema version, required keys, grid shape, finite numbers), Coverage thresholds on src/lib: 85% lines and functions, 75% branches, Dependencies pinned to exact versions, src/content: typed copy for the About and Architecture pages (+7 more)

### Community 99 - "quality.py"
Cohesion: 0.23
Nodes (7): calendar_counts(), flag_counts(), gate(), GateResult, report(), rows_per_date(), underlying_check()

### Community 100 - "_number"
Cohesion: 0.14
Nodes (7): calendar_table(), distributions_table(), flags_by_year(), _number(), sources_table(), thresholds_table(), tolerances_table()

### Community 101 - "flags.py"
Cohesion: 0.23
Nodes (6): In this project, cents(), flag_names(), mid_flags(), quote_flags(), set_where()

### Community 102 - "contract.test.ts"
Cohesion: 0.18
Nodes (9): ContractError, findDataset(), MAX_IV, SUPPORTED_MAJOR, broken(), clone(), Cols, Doc (+1 more)

### Community 103 - "Graph Report - vol-strategy-backtester  (2026-10-28)"
Cohesion: 0.15
Nodes (12): Ambiguous Edges - Review These, Community Hubs (Navigation), Corpus Check, God Nodes (most connected - your core abstractions), Graph Report - vol-strategy-backtester  (2026-10-28), Hyperedges (group relationships), Import Cycles, Knowledge Gaps (+4 more)

### Community 104 - "mask.py"
Cohesion: 0.23
Nodes (5): In this project, apply_mask(), build_mask(), listed_pairs(), strike_milli()

### Community 105 - "test_quality.py"
Cohesion: 0.28
Nodes (11): clean(), tables(), test_a_clean_report_passes(), test_a_thin_date_fails(), test_a_wide_underlying_gap_fails(), test_crossed_above_one_percent_fails_and_says_why(), test_every_failure_is_listed(), test_exactly_at_the_limit_passes() (+3 more)

### Community 107 - "view"
Cohesion: 0.26
Nodes (8): view(), test_a_view_after_the_split_end_raises_split_error(), test_an_unknown_split_is_refused(), test_history_reads_stop_at_as_of(), test_nothing_can_be_attached_to_a_view(), test_reading_the_next_day_raises_look_ahead(), test_reading_today_returns_only_today(), test_the_concrete_view_satisfies_the_protocol()

### Community 108 - "Measured results"
Cohesion: 0.18
Nodes (10): Measured results, Mutation runs, Reference data, the store and the build, Rows, flags and the calendar, The cross-vendor check, 2020-01-06 → 2023-12-29, The DoltHub clone, The guesses, answered, The labelled 2019 test (hypothesis, not overlap) (+2 more)

### Community 109 - "build_date_map"
Cohesion: 0.31
Nodes (3): build_date_map(), missing_sessions(), sessions_from_bars()

### Community 110 - "re"
Cohesion: 0.40
Nodes (6): _cairosvg(), _playwright(), render_png(), RendererUnavailable, _resvg(), svg_size()

### Community 111 - "test_mask.py"
Cohesion: 0.36
Nodes (6): masked(), pair_set(), test_thursday_carries_wednesday_and_the_listed_days_are_unchanged(), test_tuesday_is_empty_under_dolthub(), test_tuesday_keeps_monday_s_pairs_under_dolthub_daily(), test_wednesday_keeps_exactly_the_pairs_both_vendors_have()

### Community 112 - "colorRamp.ts"
Cohesion: 0.44
Nodes (6): hexToSrgb(), RAMP_STOPS, rampLinear(), rampSrgb(), Rgb, srgbToLinear()

### Community 114 - "Milestone 1: the option-chain data layer and quality filters"
Cohesion: 0.29
Nodes (7): Concepts used, Decisions taken in M1 that the ADRs did not fix, Explain it back, Milestone 1: the option-chain data layer and quality filters, Not done in M1, What we built and why, Why this design

### Community 115 - "volbt/build.py"
Cohesion: 0.33
Nodes (3): _not_yet(), run(), Step

### Community 116 - "reachable_data_objects"
Cohesion: 0.33
Nodes (5): reachable_data_objects(), is_data(), walk(), test_no_public_attribute_reaches_the_store(), test_the_walk_would_see_a_public_store_reference()

### Community 117 - "_marker"
Cohesion: 0.52
Nodes (6): _marker(), at(), bar(), circle(), crow(), line()

### Community 119 - "tools/screenshots"
Cohesion: 0.33
Nodes (5): Checks (the script exits 1 if any fails), Command, How it works, Output (measured on the dev box, 2026-10-28), tools/screenshots

## Ambiguous Edges - Review These
- `Where this goes next (M1 data layer, M2 real surfaces)` → `Short-dated skew bound |d sigma/dk| <= |rho|/sqrt((1+|rho|)T)`  [AMBIGUOUS]
  docs/concepts/01-ssvi-surface.md · relation: conceptually_related_to

## Knowledge Gaps
- **86 isolated node(s):** `@types/react`, `@types/react-dom`, `@types/three`, `@vitest/coverage-v8`, `eslint` (+81 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 900 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **23 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Load-time contract validation (schema version, required keys, grid shape, finite numbers)` connect `React 19 + TypeScript + Vite results viewer` to `contract.ts`?**
  _High betweenness centrality (0.193) - this node is a cross-community bridge._
- **What connects `@types/react`, `@types/react-dom`, `@types/three` to the rest of the system?**
  _86 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Chart & Surface Rendering` be split into smaller, more focused modules?**
  _Cohesion score 0.062003968253968256 - nodes in this community are weakly interconnected._
- **Why does `app/public/data JSON: manifest.json plus datasets` connect `React 19 + TypeScript + Vite results viewer` to `export_app_data.py`?**
  _High betweenness centrality (0.168) - this node is a cross-community bridge._
- **Should `Blender Hero Render Script` be split into smaller, more focused modules?**
  _Cohesion score 0.05352112676056338 - nodes in this community are weakly interconnected._
- **Why does `Background: volatility mispricing in SPY options` connect `Variance Risk Premium Literature` to `Look-Ahead Guards & Calendar`, `Diagram Tooling & Validation`, `Milestone 0: foundations walkthrough`, `LEARNING_LOG.md (milestone table and checkpoints)`, `The SSVI implied-vol surface`, `volbt.engine: daily loop, fills, marks, expiry, hedge`, `Delta Hedging & Greeks Inputs`, `Vol Premium Background Research`?**
  _High betweenness centrality (0.129) - this node is a cross-community bridge._

### Low-confidence Hints
_AMBIGUOUS edges — the extractor was unsure. Verify before acting on these._

- **What is the exact relationship between `Where this goes next (M1 data layer, M2 real surfaces)` and `Short-dated skew bound |d sigma/dk| <= |rho|/sqrt((1+|rho|)T)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._