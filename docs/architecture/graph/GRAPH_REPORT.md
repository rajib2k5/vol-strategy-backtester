# Graph Report - vol-strategy-backtester  (2026-10-28)

## Corpus Check
- 101 files · ~109,711 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 12 file(s) not represented in the graph (top: (none) 6, .mmd 5, .css 1)

## Summary
- 1264 nodes · 2413 edges · 66 communities (56 shown, 10 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 137 edges (avg confidence: 0.87)
- Token cost: ~626,980 tokens total across 3 semantic-extraction subagents (docs only; code was AST-only at zero LLM cost). The input/output split was not reported by the harness.

## Community Hubs (Navigation)
- Chart & Surface Rendering
- Blender Hero Render Script
- SSVI Surface & No-Arbitrage
- Illustrative Surface Tests
- Architecture Diagram Content
- App Frontend Conventions
- Contract Envelope Tests
- Diagram Tooling & Validation
- Notebook Builder Tests
- Notebook Builder Script
- App Data Fixtures & Tests
- Engine Module Architecture
- App Shell & Routing
- Data Layer & Quality Flags
- About Page & Content
- M0 Foundations Walkthrough
- App Data Loader
- Fill Model & Evaluation Process
- App Contract Validation
- Fills, Fees & Expiry Rules
- Raw Data Sources & README
- App tsconfig Settings
- Config & Test Fixtures
- Export JSON Contract Tests
- App Package & ESLint
- Marking, Assignment & Stress
- Event Loop & Early Exercise
- Delta Hedging & Greeks Inputs
- Vol Premium Background Research
- App Dev Dependencies
- Pricing Build & IV Solver
- Illustrative SSVI Module
- tsconfig.node Settings
- Risk Limits & Capital Base
- Causal Signals & Import Boundaries
- App JSON Contract & Metrics
- Variance Risk Premium Literature
- Diagram Tool Dependencies
- Export App Data Script
- Look-Ahead Guards & Calendar
- PR/FAQ Core Questions
- Contract Envelope Module
- Mark Cascade & Sparse Quotes
- Fill Timing Validation
- Data Sources & Calendar Gaps
- Committed Export Tests
- Background & ADR Summaries
- Margin & Liquidation Rules
- Greek Limit Enforcement
- Data Directory Config
- App npm Scripts
- LineChart & React Entry
- Package Module Layout
- Deflated Sharpe Evaluation
- Blender Script Tests
- App Runtime Dependencies
- Mermaid Render Script
- Pricing Inputs Claims
- Export Test Fixtures
- tsconfig Root References
- Vite Build Config
- Node Engine Requirement
- Test Setup & jest-dom
- Quality Flags & Attribution
- Project Package Root

## God Nodes (most connected - your core abstractions)
1. `vitest` - 23 edges
2. `Vol Strategy Backtester` - 23 edges
3. `docs/architecture/README.md (diagram index, validation, ADR summary)` - 22 edges
4. `compilerOptions` - 20 edges
5. `runs, signals, orders, order_legs, fills, positions, lots, position_marks, hedges, expiry_events, risk_events, greeks_snapshots, daily_pnl` - 19 edges
6. `runs` - 19 edges
7. `Milestone 0: foundations walkthrough` - 19 edges
8. `parseIllustrativeSurface()` - 17 edges
9. `ADR-0001: Architecture and stack` - 17 edges
10. `compilerOptions` - 16 edges

## Surprising Connections (you probably didn't know these)
- `Page title and description meta: volatility-mispricing backtester, educational, not financial advice` --semantically_similar_to--> `Vol Strategy Backtester`  [INFERRED] [semantically similar]
  app/index.html → README.md
- `DoltHub post-no-preference/options SPY chains 2024-2026 (out-of-sample)` --semantically_similar_to--> `DoltHub option_chain SPY 2019-2026`  [INFERRED] [semantically similar]
  README.md → docs/architecture/specs/architecture.yaml
- `Vite + React 19 + three.js viewer` --semantically_similar_to--> `React 19 + TypeScript + Vite results viewer`  [INFERRED] [semantically similar]
  docs/architecture/specs/architecture.yaml → app/README.md
- `volbt.risk: greek and stress budgets, sizing, margin` --conceptually_related_to--> `Milestone 5: Risk: greek budgets and sizing`  [INFERRED]
  docs/architecture/specs/architecture.yaml → LEARNING_LOG.md
- `OptionsDX SPY EOD option chains 2010-2023 (re-hosted on Kaggle)` --semantically_similar_to--> `Kaggle OptionsDX SPY EOD 2010-2023`  [INFERRED] [semantically similar]
  README.md → docs/architecture/specs/architecture.yaml

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Engine daily loop pipeline (fill, settle, mark, hedge, risk, early exercise)** — docs_adr_0001_architecture_and_stack_daily_engine_loop, docs_adr_0002_fill_model_next_close_fill_timing, docs_adr_0003_expiry_settlement_early_exercise_expiry_settlement, docs_adr_0004_mark_to_market_mark_rule_cascade, docs_adr_0005_delta_hedge_frequency_default_daily_hedge, docs_adr_0006_greeks_limit_enforcement_eod_breach_hysteresis, docs_adr_0007_capital_base_and_returns_margin_call_liquidation, docs_adr_0003_expiry_settlement_early_exercise_early_assignment_step [EXTRACTED 1.00]
- **Surface IV construction chain for model marks** — docs_adr_0004_mark_to_market_surface_iv_construction, docs_adr_0004_mark_to_market_strike_extrapolation, docs_adr_0004_mark_to_market_tenor_extrapolation, docs_adr_0004_mark_to_market_cross_expiry_interp, docs_adr_0008_pricing_inputs_deamericanisation [EXTRACTED 1.00]
- **Layered risk limits (greek, stress, margin, liquidation)** — docs_adr_0006_greeks_limit_enforcement_greek_budgets, docs_adr_0006_greeks_limit_enforcement_stress_loss_budget, docs_adr_0006_greeks_limit_enforcement_pretrade_check, docs_adr_0007_capital_base_and_returns_pretrade_margin_cap, docs_adr_0007_capital_base_and_returns_margin_call_liquidation, docs_adr_0006_greeks_limit_enforcement_eod_breach_hysteresis [EXTRACTED 1.00]
- **json_run provenance block embedded in every results dataset** — docs_architecture_specs_data_model_erd_json_run, docs_architecture_specs_data_model_erd_json_surface_frames, docs_architecture_specs_data_model_erd_json_blotter, docs_architecture_specs_data_model_erd_json_positions_timeline, docs_architecture_specs_data_model_erd_json_greeks_timeline, docs_architecture_specs_data_model_erd_json_pnl_attribution, docs_architecture_specs_data_model_erd_json_stress_grid, docs_architecture_specs_data_model_erd_json_metrics [EXTRACTED 1.00]
- **Quality, pricing, attribution and publish gates in the research process** — docs_architecture_specs_process_g_quality, docs_architecture_specs_process_g_pricing, docs_architecture_specs_process_g_attr, docs_architecture_specs_process_g_publish [EXTRACTED 1.00]
- **Four YAML diagram specs following the interim schema** — docs_architecture_specs_architecture, docs_architecture_specs_data_flow, docs_architecture_specs_process, docs_architecture_specs_data_model_erd, docs_architecture_readme_interim_yaml_diagram_schema [EXTRACTED 1.00]
- **Look-ahead defence stack** — docs_milestones_00_foundations_marketview_lookahead_guard, docs_milestones_00_foundations_import_allowlist_ast_test, docs_milestones_00_foundations_causal_signals_monthly_refit, docs_milestones_00_foundations_same_close_fill_bias [EXTRACTED 1.00]
- **M0 adversarial review artifacts** — docs_milestones_00_foundations_m0_adversarial_reviews, docs_validation_00_code_ledger, docs_validation_00_design_research_ledger [EXTRACTED 1.00]
- **VRP measurement chain (RV, model-free implied variance, VIX, VRP)** — docs_concepts_00_background_realised_variance, docs_concepts_00_background_model_free_implied_variance, docs_concepts_00_background_vix_construction, docs_concepts_00_background_variance_risk_premium [EXTRACTED 1.00]

## Communities (66 total, 10 thin omitted)

### Community 0 - "Chart & Surface Rendering"
Cohesion: 0.06
Nodes (45): binValues(), Heatmap(), Histogram(), normalizeMatrix(), hexToSrgb(), RAMP_STOPS, rampLinear(), rampSrgb() (+37 more)

### Community 1 - "Blender Hero Render Script"
Cohesion: 0.06
Nodes (40): add_camera(), add_labels(), add_lights(), add_surface(), _add_text(), Annotation, axis_annotations(), box_corners() (+32 more)

### Community 2 - "SSVI Surface & No-Arbitrage"
Cohesion: 0.06
Nodes (38): The SSVI implied-vol surface, Butterfly no-arbitrage (convexity in strike, g(k) >= 0), Calendar no-arbitrage (w non-decreasing in T), eta and phi(theta)=eta/sqrt(theta): curvature and wings, Gatheral and Jacquier (2014) Arbitrage-free SVI volatility surfaces, Lee (2004) The moment formula for implied volatility at extreme strikes, Certification only up to a maximum expiry t*_0, no_arbitrage_checks (butterfly and calendar flags) (+30 more)

### Community 3 - "Illustrative Surface Tests"
Cohesion: 0.05
Nodes (3): test_no_arbitrage_checks_hands_the_real_w_table_to_the_calendar_check(), test_phi_condition_of_gatheral_jacquier_theorem_4_1_holds_for_phi_eta_over_sqrt_theta(), test_total_variance_at_the_money_equals_theta()

### Community 4 - "Architecture Diagram Content"
Cohesion: 0.13
Nodes (29): ACTORS, ArchitectureLayer, DayStep, EDGES, [ENGINE, STORE, VIEW, FILLS, EXPIRY, MARKER, HEDGER, RISK, SIGNALS, STRAT, LEDGER], LAYERS, NODES, STEPS (+21 more)

### Community 5 - "App Frontend Conventions"
Cohesion: 0.07
Nodes (30): app/index.html (Vite HTML entry), Module entry script /src/main.tsx, Page title and description meta: volatility-mispricing backtester, educational, not financial advice, #root mount element, Load-time contract validation (schema version, required keys, grid shape, finite numbers), Coverage thresholds on src/lib: 85% lines and functions, 75% branches, Dependencies pinned to exact versions, src/content: typed copy for the About and Architecture pages (+22 more)

### Community 6 - "Contract Envelope Tests"
Cohesion: 0.09
Nodes (15): commit_a_file(), repo(), run_git(), test_a_hung_git_status_counts_as_dirty(), test_a_hung_rev_parse_gives_no_commit(), test_every_git_call_has_a_timeout(), test_real_lookup_clean_repo(), test_real_lookup_corrupt_index_counts_as_dirty() (+7 more)

### Community 7 - "Diagram Tooling & Validation"
Cohesion: 0.14
Nodes (30): docs/architecture/README.md (diagram index, validation, ADR summary), architecture.mmd: end-to-end components diagram, data-flow.mmd: how data moves from vendor tables to the app, data-model.erd.mmd: every stored table plus Python-to-app JSON entities, engine-daily-loop.sequence.mmd: one trading session in ADR-0001 step order (hand-written), ERD column-name and type sanitising for Mermaid (brackets and punctuation become underscores, raw name kept in comment), Interim YAML diagram schema (kind flow and kind erd, unknown keys are errors), Validation of the Mermaid files (2026-10-28, after M0 review revision) (+22 more)

### Community 8 - "Notebook Builder Tests"
Cohesion: 0.09
Nodes (14): test_a_function_named_like_a_fixed_cell_id_is_rejected(), test_a_module_with_different_content_still_builds_with_stable_ids(), test_a_module_without_assignments_is_fine(), test_a_redefined_function_is_rejected(), test_a_string_expression_after_the_first_statement_is_not_mistaken_for_the_docstring(), test_an_assignment_after_a_function_does_not_copy_the_function_twice(), test_an_empty_module_gives_no_cells(), test_comments_above_constants_travel_with_them() (+6 more)

### Community 9 - "Notebook Builder Script"
Cohesion: 0.10
Nodes (14): assert_unique_cell_ids(), build_scaffold_tour(), code(), drifted_notebooks(), _is_docstring(), main(), markdown(), module_cells() (+6 more)

### Community 10 - "App Data Fixtures & Tests"
Cohesion: 0.10
Nodes (14): FILES, serve(), STORE, SURFACE_LABEL, DATA, fakeFetch(), datasets, generated_at (+6 more)

### Community 11 - "Engine Module Architecture"
Cohesion: 0.10
Nodes (22): ADR-0005: Delta-hedge frequency, instrument and cost, app/public/data JSON: manifest + datasets, volbt.analytics: metrics, attribution, regimes, stress grid, volbt.engine: daily loop, fills, marks, expiry, hedge, volbt.export + tools/export_app_data.py, Run ledger parquet under runs/run_id, Vite + React 19 + three.js viewer, manifest.json + dataset JSON files (+14 more)

### Community 12 - "App Shell & Routing"
Cohesion: 0.16
Nodes (16): AppShell(), readRoute(), ShellPage, PAGES, shell(), STORE, memMap, memoryFallback (+8 more)

### Community 13 - "Data Layer & Quality Flags"
Cohesion: 0.13
Nodes (24): volbt.data: load, calendar, quality flags, DoltHub option_chain SPY 2019-2026, Clean parquet + DuckDB, Quality report within tolerance?, Build trading_calendar from SPY bars, Reshape long, OSI symbol, quality_flags, Load chains + pin schema, Load reference series (+16 more)

### Community 14 - "About Page & Content"
Cohesion: 0.15
Nodes (20): App(), APP_SLUG, DATA_SOURCES, DATA_SOURCES_NOTE, DataSource, DISCLAIMER_BODY, DISCLAIMER_HEADLINE, DOES (+12 more)

### Community 15 - "M0 Foundations Walkthrough"
Cohesion: 0.15
Nodes (21): Where this goes next (M1 data layer, M2 real surfaces), Milestone 0: foundations walkthrough, ADR-0001 Architecture and stack, ADR-0003 Expiry, settlement and early exercise, ADR-0005 Delta-hedge frequency, ADR-0006 Greeks and limit enforcement, Causal signals with monthly refits, Daily event-driven loop (11 steps) (+13 more)

### Community 16 - "App Data Loader"
Cohesion: 0.16
Nodes (17): AppData, asContractFailure(), DATA_DIR, DataLoadError, EXPORT_COMMAND, FetchLike, getJson(), loadAppData() (+9 more)

### Community 17 - "Fill Model & Evaluation Process"
Cohesion: 0.18
Nodes (15): fills, json_run, orders, risk_events, runs, Attribution and mark-quality gate, Freeze config, Development runs 2010-2019 (+7 more)

### Community 18 - "App Contract Validation"
Cohesion: 0.23
Nodes (18): asRecord(), assertStrictlyIncreasing(), ContractError, DatasetEntry, fail(), findDataset(), isRealTimestamp(), MAX_IV (+10 more)

### Community 19 - "Fills, Fees & Expiry Rules"
Cohesion: 0.11
Nodes (13): Option fees $0.70 per contract per side, Whole-package fills with no carry-over or legging, same_close diagnostic mode and same-snapshot premium, SEC Rel. 34-105153 (expiring options trade until 4:15 pm ET), Volume unreliable before 2021-01-04, OCC Exercise-by-Exception (Rule 805, $0.01 threshold), Expiry settlement by Ex-by-Ex at the official close, Pin risk flag (pin_band $0.50) (+5 more)

### Community 20 - "Raw Data Sources & README"
Cohesion: 0.13
Nodes (22): app/README.md (React viewer), Cboe VIX history CSV, FRED DGS3MO, Kaggle OptionsDX SPY EOD 2010-2023, yfinance SPY bars and dividends, Raw vendor files under VOL_DATA_DIR, raw_optionsdx_eod, raw_optionsdx_eod (+14 more)

### Community 21 - "App tsconfig Settings"
Cohesion: 0.09
Nodes (21): compilerOptions, allowImportingTsExtensions, jsx, lib, module, moduleDetection, moduleResolution, noEmit (+13 more)

### Community 23 - "Export JSON Contract Tests"
Cohesion: 0.16
Nodes (17): parse_finite_float(), read_json(), reject_non_finite(), test_default_out_dir_comes_from_the_script_location_not_the_working_directory(), test_every_manifest_path_exists_next_to_the_manifest(), test_manifest_content(), test_no_head_gives_uncommitted(), test_script_runs_as_a_plain_script_from_another_directory() (+9 more)

### Community 24 - "App Package & ESLint"
Cohesion: 0.11
Nodes (19): description, name, private, type, version, eslint, @eslint/js, eslint-plugin-react-hooks (+11 more)

### Community 25 - "Marking, Assignment & Stress"
Cohesion: 0.15
Nodes (15): ADR-0004: Mark-to-market, Greek P&L attribution, Export + JSON Schema validation, Spot x vol stress grid, Metrics, PSR/DSR, regimes, stress windows, runs, signals, orders, order_legs, fills, positions, lots, position_marks, hedges, expiry_events, risk_events, greeks_snapshots, daily_pnl, dividends, expiry_events (+7 more)

### Community 26 - "Event Loop & Early Exercise"
Cohesion: 0.16
Nodes (13): Start-of-day LOT_REMOVED order cancel, Early assignment and exercise decision (step 10), European put necessary-condition pre-filter, expiry_events table, SPY quarterly ex-dividend schedule, Surface IV construction (own-expiry, strike, cross-expiry, tenor steps), Dividend cash flow on hedge shares, Model marks add the early-exercise premium back (|k| <= 0.15) (+5 more)

### Community 27 - "Delta Hedging & Greeks Inputs"
Cohesion: 0.13
Nodes (18): SPY hedge share commission and slippage (Decimal ROUND_HALF_UP), Delivered shares: hedge netting or unhedged liquidation, Vendor IV and greeks unreliable, Discrete hedging residual scaling with sqrt(dt), Gamma rent P&L formula, Hedge frequency sweep (time-based and band-based), Hull-White (2017) minimum-variance delta (variant), Sticky-strike Black-76 spot delta (+10 more)

### Community 28 - "Vol Premium Background Research"
Cohesion: 0.12
Nodes (19): Apr-2025 tariff shock, Aug-2024 carry-trade unwind and VIX quote spike, Augustin, Cheng and Van den Bergen (2021) Volmageddon and short volatility products, BIS Bulletin 90 (2024) Carry trade unwind of August 2024, BIS Bulletin 95 (2024) Anatomy of the VIX spike in August 2024, Capital base and leverage problem, Why paper returns disappear: costs, margin, tails, Dew-Becker, Giglio, Le and Rodriguez (2017) The price of variance risk (+11 more)

### Community 29 - "App Dev Dependencies"
Cohesion: 0.11
Nodes (19): devDependencies, eslint, @eslint/js, eslint-plugin-react-hooks, eslint-plugin-react-refresh, globals, jsdom, @react-three/test-renderer (+11 more)

### Community 30 - "Pricing Build & IV Solver"
Cohesion: 0.21
Nodes (15): ADR-0008: Pricing inputs (rate, forward, dividends, day count, European approximation, IV solver), volbt.build: pricing build, volbt.pricing: Black-76, IV, parity forward, CRR lattice, smile, Derived tables: quote_iv, expiry_forwards, smile_fits, Parity forward per expiry, de-Americanised, IV solve on de-Americanised OTM mids, Smile nodes in total variance, expiry_forwards, quote_iv, smile_fits (+7 more)

### Community 31 - "Illustrative SSVI Module"
Cohesion: 0.20
Nodes (8): atm_total_variance(), butterfly_conditions(), calendar_condition(), iv_grid(), no_arbitrage_checks(), phi(), sigma_atm(), total_variance()

### Community 32 - "tsconfig.node Settings"
Cohesion: 0.11
Nodes (17): compilerOptions, allowImportingTsExtensions, lib, module, moduleDetection, moduleResolution, noEmit, noFallthroughCasesInSwitch (+9 more)

### Community 33 - "Risk Limits & Capital Base"
Cohesion: 0.18
Nodes (9): volbt.risk: greek and stress budgets, sizing, margin, daily_pnl, greeks_snapshots, json_blotter, json_greeks_timeline, json_manifest_dataset, json_metrics, json_pnl_attribution (+1 more)

### Community 34 - "Causal Signals & Import Boundaries"
Cohesion: 0.19
Nodes (11): ADR-0001: Architecture and stack, volbt.signals: RV, HAR/GARCH, IV30, VRP spread, volbt.strategies: structures, entry and exit rules, MarketView as_of t, Daily loop: fills, expiry, marks, hedge, risk, orders, Signals from the view: RV, HAR/GARCH, IV30 minus RV forecast, MarketView as_of t, DoltHub sampling mask for surface-gap runs (+3 more)

### Community 35 - "App JSON Contract & Metrics"
Cohesion: 0.15
Nodes (12): Exported JSON datasets by milestone, Python-to-app JSON contract, volbt.analytics, volbt.export, cap_mode: hard_only vs volume, Return and risk-metric definitions (Sharpe, Sortino, Calmar), Bailey & Lopez de Prado (2014) deflated Sharpe ratio, Deflated Sharpe Ratio (DSR) = min(dsr_raw, dsr_eff) (+4 more)

### Community 36 - "Variance Risk Premium Literature"
Cohesion: 0.15
Nodes (17): Bakshi and Kapadia (2003) Delta-hedged gains, Broadie, Chernov and Johannes (2009) Understanding index option returns, Carr and Wu (2009) Variance risk premiums, Coval and Shumway (2001) Expected option returns, Demeterfi, Derman, Kamal and Zou (1999) A guide to volatility and variance swaps, Discrete hedging error scales as sqrt(dt), Delta-hedged P&L gamma-rent formula, Goyal and Saretto (2009) Cross-section of option returns and volatility (+9 more)

### Community 37 - "Diagram Tool Dependencies"
Cohesion: 0.12
Nodes (16): mermaid, @mermaid-js/mermaid-cli, puppeteer, dependencies, mermaid, @mermaid-js/mermaid-cli, puppeteer, description (+8 more)

### Community 38 - "Export App Data Script"
Cohesion: 0.17
Nodes (8): test_a_valid_custom_term_structure_is_exported_and_recorded(), test_files_are_written_with_lf_even_where_text_mode_would_write_crlf(), test_output_directory_is_created(), build_payloads(), main(), manifest_payload(), surface_payload(), write_json()

### Community 39 - "Look-Ahead Guards & Calendar"
Cohesion: 0.16
Nodes (12): Import boundary AST test with required mutants, LookAheadError, MarketView look-ahead and split guard, Signals-are-causal metamorphic test (test 6), SplitError, Calendar-day time to expiry (not vendor DTE), Vendor DTE daylight-saving artefact, Cross-vendor check 2020-01-06 to 2023-12-29 (+4 more)

### Community 40 - "PR/FAQ Core Questions"
Cohesion: 0.20
Nodes (13): ADR-0007 Capital base and returns, Net margin requirement compared with NAV, PR/FAQ: Vol Strategy Backtester, Central question: do SPY vol trades beat T-bills after realistic costs, Event-driven daily engine (six-step day), Fill timing and price (t+1, mid +/- k*half-spread, $0.70 fees), Holdout tested through a fitted surface, What it will not tell you and what we will not do (+5 more)

### Community 41 - "Contract Envelope Module"
Cohesion: 0.20
Nodes (4): build_envelope(), _git(), git_state(), source_commit()

### Community 42 - "Mark Cascade & Sparse Quotes"
Cohesion: 0.19
Nodes (12): Quote states at fill time (ZERO_BID, NO_QUOTE, surface fill), Surface execution mode (model fills), Cross-expiry interpolation of total variance, DoltHub held contracts usually not quoted on later days, Mark rule cascade (rules 0-4, mark_source), STALE_SURFACE mark (sticky moneyness), quote_iv table (iv_flags, eep), DoltHub sparse sampling (re-centred strikes, 3-4 expiries, none under 10 DTE) (+4 more)

### Community 43 - "Fill Timing Validation"
Cohesion: 0.21
Nodes (13): SPY options trade to 4:15 pm while SPY closes at 4:00 pm, ADR-0002 Fill model, Fill price mid +/- k*half-spread in integer cents, Pitfalls this design guards against, Same-close fills book quote noise as edge, Hard cap of 100 contracts, 10% volume cap as diagnostic, Volume unreliable before 2021 (null means unknown), Liquidity: 100-contract hard cap, volume cap as diagnostic (+5 more)

### Community 44 - "Data Sources & Calendar Gaps"
Cohesion: 0.26
Nodes (11): ADR-0004 Mark-to-market, ADR-0009 Data sources, calendar and quality flags, Aug-2024 DoltHub gap (no SPY dates 2024-07-30 to 08-09), Calendar anomalies: closure-dated snapshots and missing sessions, DoltHub options dataset (2019-2026, sparse), OptionsDX SPY EOD dataset (2010-2023), Data sources: OptionsDX, DoltHub, yfinance, FRED DGS3MO, Cboe VIX, Internal FAQ: measured data facts and gaps (+3 more)

### Community 45 - "Committed Export Tests"
Cohesion: 0.18
Nodes (9): assert_matches_a_fresh_export(), lookup_for(), test_committed_app_data_matches_a_fresh_export_byte_for_byte(), test_refuses_to_export_a_surface_that_fails_no_arbitrage(), test_refuses_to_export_an_inverted_term_structure(), test_the_drift_check_fails_on_a_one_digit_change(), test_the_drift_check_fails_on_crlf_line_endings(), test_the_drift_check_passes_on_an_untouched_copy() (+1 more)

### Community 46 - "Background & ADR Summaries"
Cohesion: 0.20
Nodes (11): ADR-0002: Fill model and fill timing, ADR-0003: Expiry, settlement, pin risk and early exercise, ADR-0006: Greek units, budgets and limit enforcement, ADR-0007: Capital base, margin, forced liquidation and return definition, ADR-0009: Data sources, trading calendar, quality flags and out-of-sample execution mode, ADR-0010: Evaluation protocol, Background: volatility mispricing in SPY options, Corsi (2009) A simple approximate long-memory model of realized volatility (+3 more)

### Community 47 - "Margin & Liquidation Rules"
Cohesion: 0.20
Nodes (10): Muravyev & Pearson (2020) effective spreads, Reduce-only orders never volume-capped, Santa-Clara & Saretto (option strategy returns, margin and costs), NAV_mid and NAV_liq series, Cboe Margin Manual, FINRA Interpretation 4210(f)(2)(E)/02, Hedge-share margin rates (50% initial, 25%/30% maintenance), Margin call, forced liquidation and ruin stop (+2 more)

### Community 48 - "Greek Limit Enforcement"
Cohesion: 0.27
Nodes (7): End-of-day breach reduction with 1.10x hysteresis, Greek budgets as fractions of NAV_mid (vega, gamma, theta), Pre-trade check: scale else reject, with closed-form quantity, risk_events table, Vega-notional sizing of entries, Fixed allocated capital of $1,000,000, Pre-trade net margin cap at 50% of NAV

### Community 49 - "Data Directory Config"
Cohesion: 0.29
Nodes (3): data_dir(), dolthub_options_dir(), kaggle_dir()

### Community 50 - "App npm Scripts"
Cohesion: 0.22
Nodes (9): scripts, build, coverage, dev, lint, preview, test, test:watch (+1 more)

### Community 51 - "LineChart & React Entry"
Cohesion: 0.25
Nodes (6): layoutLegend(), LineChart(), pad0, Series, react, react-dom

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

### Community 57 - "Pricing Inputs Claims"
Cohesion: 0.83
Nodes (4): ADR-0008 Pricing inputs, American early-exercise premium biases the parity forward, Vendor IV and greeks are inconsistent, Claim 8: ADR-0008 parity forward unbiased enough (PARTIALLY REFUTED)

## Ambiguous Edges - Review These
- `Short-dated skew bound |d sigma/dk| <= |rho|/sqrt((1+|rho|)T)` → `Where this goes next (M1 data layer, M2 real surfaces)`  [AMBIGUOUS]
  docs/concepts/01-ssvi-surface.md · relation: conceptually_related_to

## Knowledge Gaps
- **89 isolated node(s):** `@types/react`, `@types/react-dom`, `@types/three`, `@vitest/coverage-v8`, `eslint` (+84 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 406 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **10 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Load-time contract validation (schema version, required keys, grid shape, finite numbers)` connect `App Frontend Conventions` to `App Contract Validation`?**
  _High betweenness centrality (0.304) - this node is a cross-community bridge._
- **What connects `@types/react`, `@types/react-dom`, `@types/three` to the rest of the system?**
  _89 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Chart & Surface Rendering` be split into smaller, more focused modules?**
  _Cohesion score 0.062111801242236024 - nodes in this community are weakly interconnected._
- **Why does `Background: volatility mispricing in SPY options` connect `Background & ADR Summaries` to `SSVI Surface & No-Arbitrage`, `Variance Risk Premium Literature`, `Look-Ahead Guards & Calendar`, `Engine Module Architecture`, `Delta Hedging & Greeks Inputs`, `Vol Premium Background Research`?**
  _High betweenness centrality (0.269) - this node is a cross-community bridge._
- **Should `Blender Hero Render Script` be split into smaller, more focused modules?**
  _Cohesion score 0.05755693581780538 - nodes in this community are weakly interconnected._
- **Why does `React 19 + TypeScript + Vite results viewer` connect `App Frontend Conventions` to `Engine Module Architecture`, `Raw Data Sources & README`?**
  _High betweenness centrality (0.222) - this node is a cross-community bridge._

### Low-confidence Hints
_AMBIGUOUS edges — the extractor was unsure. Verify before acting on these._

- **What is the exact relationship between `Short-dated skew bound |d sigma/dk| <= |rho|/sqrt((1+|rho|)T)` and `Where this goes next (M1 data layer, M2 real surfaces)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._