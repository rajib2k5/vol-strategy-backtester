/**
 * Content for the Architecture page: plain typed data, no React. It mirrors the decision records
 * in docs/adr/ (ADR-0001 for the module boundaries and the daily order, ADR-0002 for fills,
 * ADR-0006 for the stress budget, ADR-0008 for pricing, ADR-0010 for the evaluation protocol) and
 * the diagrams in docs/architecture/. It was brought in line with the ADRs as revised after the
 * M0 adversarial review (2026-10-28).
 * Revise it here (and only here) when a decision changes. The structural tests in
 * architecture.test.tsx fail if an edit leaves a dangling reference or a label too long to draw.
 *
 * Box labels are drawn as single-line SVG text with no wrapping, so keep them short (roughly
 * <= 16 characters when a layer has 5 boxes, <= 21 with 4, <= 28 with 3, <= 43 with 2). Put the
 * longer explanation in `detail`, which the page prints beside the diagram. With eleven actors the
 * sequence headers are 50 units wide, so actor names stay at 7 characters or fewer.
 */
import type { ActEdge, ActNode, ArchLayer, SeqStep } from '../lib/diagrams'

export interface ArchitectureLayer extends ArchLayer {
  /** A few sentences shown under the diagram. */
  detail: string
}

/**
 * Listed in data-flow order: the first layer is drawn at the TOP and each arrow points down to
 * the layer that consumes its output, so the picture reads Sources -> ... -> App. The picture is
 * data flow, not an import rule: each module may import exactly the modules in its "May import"
 * allow-list (ADR-0001 section 4), which an AST test will enforce (specified; implemented and
 * enforced from M1), and "anything above it" is not that list.
 */
export const LAYERS: ArchitectureLayer[] = [
  {
    label: 'Sources',
    boxes: ['Kaggle OptionsDX', 'DoltHub clone', 'yfinance SPY', 'FRED DGS3MO', 'CBOE VIX'],
    detail:
      'In-sample option chains are OptionsDX SPY end-of-day files from Kaggle (2010–2023); the held-out years 2024–2026 come from the DoltHub post-no-preference/options clone. SPY prices and dividends come from yfinance, the 3-month yield DGS3MO from FRED and the VIX from CBOE. Raw vendor files are never modified and stay outside the repository.',
  },
  {
    label: 'Chain store',
    boxes: ['Loaders + SPY calendar', 'Quality flags, not drops', 'Parquet + DuckDB'],
    detail:
      'volbt.data loads the vendor files, takes the trading calendar from SPY’s own bars and writes one long table of quotes per source. A bad quote sets a bit in a 13-flag quality mask instead of being deleted, so a held contract with a zero bid can still be marked. Cleaned and derived tables are parquet files, queried in-process by DuckDB.',
  },
  {
    label: 'Pricing core',
    boxes: ['CRR lattice', 'Parity forward', 'Black-76, greeks', 'IV solver', 'Smile, total var'],
    detail:
      'Pure functions with no I/O, importing numpy and scipy only and no other volbt module. Options are priced with European Black-76 on a forward implied from put-call parity, so dividends never enter as a yield, not plain Black-Scholes-Merton. SPY options are American, so a CRR lattice first removes the early-exercise premium from the near-the-money quotes (de-Americanisation); left in, it biased the forward 4–7 bp low at 5% rates. Implied vol is then solved from out-of-the-money mids by Newton with a bisection fallback, and smiles are interpolated in total variance. The same lattice adds the premium back to model marks near the money and decides early exercise of puts.',
  },
  {
    label: 'Pricing build',
    boxes: ['expiry_forwards', 'quote_iv', 'smile_fits'],
    detail:
      'volbt.build (specified; implemented from M1, with the pricing build in M2) runs the pricing over the store. It reads option_quotes and the reference data through volbt.data, calls the pure functions in pricing, and writes the derived tables (forwards, implied vols, smiles) back through data. That split is how pricing stays free of I/O while the derived tables still get built.',
  },
  {
    label: 'Signals',
    boxes: ['IV30', 'Realised vol', 'HAR / GARCH', 'Monthly refit', 'IV30 − forecast'],
    detail:
      'Signals are causal. The engine calls volbt.signals each session with the MarketView at as_of = t, so a signal can read nothing dated after t, and signals may import only pricing and the view, never the store. HAR and GARCH are refitted monthly on an expanding window ending at the refit date, and every signal row records its model_fit_date. Computing over the full history and then shifting is forbidden: shifting fixes the index but not the fitted parameters, and a perturb-the-future test checks the state a view guard cannot see. IV30 is interpolated from the two expiries around 30 days; realised vol is close-to-close with the overnight gap, forecast over the same horizon. The gap between the two is the volatility-premium signal.',
  },
  {
    label: 'Strategies',
    boxes: ['MarketView', 'Straddle', 'Strangle', 'Calendar', 'Entry/exit rules'],
    detail:
      'Strategies build structures (straddle, strangle, calendar, vol-arb) on standard monthly expiries by default and turn entry and exit rules into order intents. They never touch the store: neither they nor signals may import volbt.data. The engine hands them a MarketView fixed at as_of = t, specified in volbt.view (implemented from M1), which imports nothing and keeps no public reference to the store. The import test, once built, also bans sys.modules, string getattr and private-attribute access in strategies and signals. Any read dated after t raises LookAheadError, and a view whose as_of lies past the run’s split end raises SplitError, so look-ahead is a crash rather than a silent bias.',
  },
  {
    label: 'Risk',
    boxes: ['Greek budgets', 'Stress budget', 'Vega sizing', 'Scale or reject', 'Net margin call'],
    detail:
      'Budgets are fractions of NAV: vega 0.25%, gamma 20% and theta 0.10%, with each position held to 40% of each. A binding stress budget revalues the book in full on the spot × vol grid: loss at most 15% of NAV at (−10%, +20 vol points) and at most 35% at the worst of 63 cells, checked before each trade and again at the end of the day. Entries are sized by vega, then scaled to fit or rejected before they become orders. An end-of-day breach beyond 110% is cut back to 100%, gamma first and the stress budget last. A margin call compares the net requirement (the rule’s gross figure minus the short options’ market value, which NAV already subtracts) with NAV and liquidates down to 80% at t+1; entries are capped at 50% of NAV net, and hedge shares are charged 50% Reg T initial margin pre-trade and 25% long or 30% short maintenance in the call test.',
  },
  {
    label: 'Engine',
    boxes: ['Fills (t+1)', 'Settle + assign', 'Marks + greeks', 'Delta hedge', 'Ledger'],
    detail:
      'The daily event loop over exchange sessions, in the order of ADR-0001: start-of-day events (assignments, dividends, interest) with a LOT_REMOVED cancel of any pending order on a lot they removed, then fill yesterday’s orders at today’s quotes, settle expiries, mark every lot, hedge, check greek and stress budgets and net margin, then compute signals from the view and let the strategies decide. The engine may import signals as well as config, data, pricing, strategies, risk and view. Orders created at t fill at the t+1 close at mid ± k·half-spread, computed in integer cents (k = 1 by default); the hedge is the one exception and trades at the same close. Each line is capped at 100 contracts a day in every split; a 10% cap on V_t, the contract’s volume on the order date, is only a 2021–23 diagnostic that reports a capacity haircut. Early exercise is decided each day for t+1: calls by a closed form before an ex-date, puts on a CRR lattice (exercise when continuation value − intrinsic ≤ $0.005). The portfolio simulation is never vectorised. See the sequence below.',
  },
  {
    label: 'Analytics',
    boxes: ['Sharpe, PSR + lower DSR', 'Greek P&L attribution', 'Regimes + stress grid'],
    detail:
      'Reads the ledger tables only. Returns are NAV-based on a fixed $1M capital base; constant leverage leaves the Sharpe ratio of excess returns unchanged, and what leverage changes is the path (margin calls, ruin). The Deflated Sharpe Ratio counts independent trials: N_eff, from clustering the trials’ returns at a fixed correlation of 0.5, and N_raw, which adds the logged design choices, and the headline is the lower of the two DSRs. A frozen configuration may be re-run on validation at most twice, each re-run a trial, and the holdout is run once and labelled semi-blind, because the background notes on Aug-2024 and Apr-2025 were written before any strategy ran. P&L is split into delta, gamma, vega, theta, fees and a residual, and results are cut by VIX regime, by five named stress windows (Aug-2024 is NO_DATA: DoltHub has no SPY dates from 2024-07-30 to 2024-08-09) and by a full-revaluation spot × vol grid.',
  },
  {
    label: 'Export',
    boxes: ['Versioned JSON: manifest + column-wise datasets'],
    detail:
      'tools/export_app_data.py writes manifest.json and one JSON file per dataset into app/public/data. Every file starts with an envelope (schema_version, generated_at, source_commit); results files add run (including the cap mode and chain mask), units and illustrative blocks. Series are stored column-wise and each file stays under 10 MB. Milestone 0 ships the envelope, the manifest and the illustrative surface; the results datasets arrive with M2–M6.',
  },
  {
    label: 'App',
    boxes: ['This UI: React + three.js, renders JSON only'],
    detail:
      'Validates each file against the contract (same major version, rectangular grids, finite numbers), then draws it. The app never computes results: it may format, sort, filter and build render-only geometry, but every number it shows exists in a JSON file.',
  },
]

/**
 * Drawn as boxes in this order, left to right. Indices are used by STEPS below. Marks, hedging
 * and fills live inside the engine module (ADR-0001) but are separate roles in the day's story.
 * `Signals` is its own module that the engine calls and that reads the View; `Strat` is the
 * strategies module, shortened to fit its header box.
 */
export const ACTORS: string[] = ['Engine', 'Store', 'View', 'Fills', 'Expiry', 'Marker', 'Hedger', 'Risk', 'Signals', 'Strat', 'Ledger']

const [ENGINE, STORE, VIEW, FILLS, EXPIRY, MARKER, HEDGER, RISK, SIGNALS, STRAT, LEDGER] = ACTORS.map((_, i) => i)

/** One message of the day, tagged with the ADR-0001 step (1 to 11) it belongs to. */
export interface DayStep extends SeqStep {
  adr: number
}

/**
 * One trading session t, top to bottom, in the order of ADR-0001 (docs/architecture/
 * engine-daily-loop.sequence.mmd). Fills of yesterday's orders come before marking, so every new
 * lot is marked on the day it is filled; today's orders fill tomorrow.
 */
export const STEPS: DayStep[] = [
  // 1. Load the snapshot for session t
  { adr: 1, from: ENGINE, to: STORE, label: 'load snapshot t' },
  { adr: 1, from: ENGINE, to: VIEW, label: 'open view: as_of t, run split' },
  { adr: 1, from: VIEW, to: VIEW, label: 'read after t: LookAheadError, past the split: SplitError' },
  // 2. Start-of-day events; a pending order on a lot they removed is cancelled before any fill
  { adr: 2, from: ENGINE, to: EXPIRY, label: 'book assignments decided at t-1' },
  { adr: 2, from: ENGINE, to: ENGINE, label: 'cancel orders on removed lots: LOT_REMOVED' },
  { adr: 2, from: ENGINE, to: ENGINE, label: 'ex-date dividends, then cash interest' },
  // 3. Fill the orders created at t-1 against the t quotes
  { adr: 3, from: ENGINE, to: FILLS, label: 'fill orders from t-1' },
  { adr: 3, from: FILLS, to: ENGINE, label: 'mid ± k·half-spread in cents, fees' },
  { adr: 3, from: FILLS, to: ENGINE, label: 'hard cap 100/line; V_t (order date) is diagnostic' },
  // 4. Settle the contracts that expire at t
  { adr: 4, from: ENGINE, to: EXPIRY, label: 'settle contracts expiring at t' },
  // 5. Mark every lot and compute greeks
  { adr: 5, from: ENGINE, to: MARKER, label: 'mark every lot, new fills too' },
  { adr: 5, from: MARKER, to: ENGINE, label: 'mark + Black-76 greeks' },
  // 6. Delta-hedge at the t close
  { adr: 6, from: ENGINE, to: HEDGER, label: 'delta-hedge at the t close' },
  // 7. Portfolio greeks snapshot and P&L attribution
  { adr: 7, from: ENGINE, to: LEDGER, label: 'greeks snapshot, P&L attribution' },
  // 8. End-of-day greek and stress budgets and the net margin requirement
  { adr: 8, from: ENGINE, to: RISK, label: 'greek + stress budgets, net margin' },
  { adr: 8, from: RISK, to: ENGINE, label: 'reduce-only orders for t+1' },
  // 9. Signals from the view, then the strategies decide; pre-trade risk check; orders for t+1
  { adr: 9, from: ENGINE, to: SIGNALS, label: 'compute signals, refit monthly' },
  { adr: 9, from: SIGNALS, to: VIEW, label: 'read bars, VIX, surface up to t' },
  { adr: 9, from: SIGNALS, to: ENGINE, label: 'IV30, forecast, model_fit_date' },
  { adr: 9, from: ENGINE, to: STRAT, label: 'view + signals, then decide' },
  { adr: 9, from: STRAT, to: ENGINE, label: 'exit + entry intents' },
  { adr: 9, from: ENGINE, to: RISK, label: 'pre-trade: greeks, stress, net margin' },
  { adr: 9, from: RISK, to: ENGINE, label: 'scaled orders queued for t+1' },
  // 10. Decide early exercise and assignment for t+1
  { adr: 10, from: ENGINE, to: EXPIRY, label: 'early-exercise test for t+1: puts on CRR lattice' },
  // 11. Write the ledger
  { adr: 11, from: ENGINE, to: LEDGER, label: 'write the ledger rows for t' },
]

/**
 * The research process from hypothesis to publication (docs/architecture/process.mmd, split
 * dates from ADR-0010). Decision nodes are the gates and reviews; a failed gate or a refuted
 * review loops back, and nothing else branches.
 */
export const NODES: ActNode[] = [
  { id: 'question', label: 'Research question', type: 'start' },
  { id: 'hypothesis', label: 'Hypothesis + config grid' },
  { id: 'ingest', label: 'Ingest + quality flags' },
  { id: 'qualityGate', label: 'Quality gate', type: 'decision' },
  { id: 'pricing', label: 'Forwards, IV, smiles' },
  { id: 'pricingGate', label: 'Pricing gate', type: 'decision' },
  { id: 'development', label: 'Development runs 2010-19' },
  { id: 'attributionGate', label: 'Attribution gate', type: 'decision' },
  { id: 'methodReview', label: 'Method review', type: 'decision' },
  { id: 'freeze', label: 'Freeze config' },
  { id: 'validation', label: 'Validation run 2020-23' },
  { id: 'holdout', label: 'Holdout run 2024-26, once' },
  { id: 'report', label: 'Metrics, lower DSR, stress' },
  { id: 'resultsReview', label: 'Results review', type: 'decision' },
  { id: 'export', label: 'Export validated JSON' },
  { id: 'app', label: 'App renders results', type: 'end' },
]

export const EDGES: ActEdge[] = [
  { from: 'question', to: 'hypothesis' },
  { from: 'hypothesis', to: 'ingest', label: 'ADR committed' },
  { from: 'ingest', to: 'qualityGate', label: 'quality report' },
  { from: 'qualityGate', to: 'pricing', label: 'pass' },
  { from: 'qualityGate', to: 'ingest', label: 'fail: fix loader' },
  { from: 'pricing', to: 'pricingGate', label: 'pricing report' },
  { from: 'pricingGate', to: 'development', label: 'pass' },
  { from: 'pricingGate', to: 'pricing', label: 'fail' },
  { from: 'development', to: 'attributionGate', label: 'trial logged' },
  { from: 'attributionGate', to: 'methodReview', label: 'pass' },
  { from: 'attributionGate', to: 'development', label: 'fail: bad marks' },
  { from: 'methodReview', to: 'freeze', label: 'survives' },
  { from: 'methodReview', to: 'hypothesis', label: 'refuted: revise' },
  { from: 'freeze', to: 'validation', label: 'frozen config_hash' },
  { from: 'validation', to: 'holdout', label: 'validation recorded' },
  { from: 'holdout', to: 'report', label: 'semi-blind holdout ledger' },
  { from: 'report', to: 'resultsReview', label: 'report + claims' },
  { from: 'resultsReview', to: 'export', label: 'survives' },
  { from: 'resultsReview', to: 'report', label: 'refuted: re-measure' },
  { from: 'export', to: 'app', label: 'JSON' },
]
