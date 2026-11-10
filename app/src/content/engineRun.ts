/**
 * Static copy the Blotter and Positions pages share: what the run behind them is, and what it is not. Plain
 * strings so the wording can be revised without touching any component. Numbers are never written here: every
 * figure on either page comes from blotter.json or positions_timeline.json.
 */
import type { EngineRunBlock, ExitReason } from '../lib/contract'

/** The sentence every variant of the notice ends on: the files hold no result, so the page shows none. */
const NO_RESULT = 'It carries no P&L, NAV, return or Sharpe ratio, and nothing on this page should be read as one.'

/**
 * The notice at the top of the Blotter and Positions pages, worded for the run the file says it is. A diagnostic run
 * is the one this milestone commits (on the development split): it was made to exercise the engine, so it says nothing
 * about a strategy. A file that says otherwise gets its own words rather than that claim. Without a file (loading, or a
 * load error) the page says what it expects to draw.
 */
export function engineRunNotice(run: Pick<EngineRunBlock, 'run_purpose' | 'split' | 'strategy'> | null): { headline: string; body: string } {
  if (run === null || run.run_purpose === 'diagnostic') {
    const strategy = run === null ? 'the milestone-3 reference strategy' : `the milestone-3 reference strategy (${run.strategy})`
    return {
      headline: 'A diagnostic run, not a strategy result.',
      body: `This is a diagnostic run of ${strategy} on the ${run === null ? 'development' : run.split} split, made to exercise the engine. It shows what the engine did, fill by fill, and not how well a strategy does. ${NO_RESULT}`,
    }
  }
  return {
    headline: 'Records of an engine run, not a strategy result.',
    body: `This file marks the run as a ${run.run_purpose} run of ${run.strategy} on the ${run.split} split, not as a diagnostic one. The page draws what the engine did. ${NO_RESULT}`,
  }
}

/** The exit reasons of a position, as the legend and the table explain them (EXIT_REASONS, src/lib/contract.ts). */
export const EXIT_REASON_TEXT: Record<ExitReason, string> = {
  dte: 'closed by the days-to-expiry rule',
  expiry: 'held to expiry',
  assignment: 'assigned',
  exercise: 'exercised',
  signal: 'exit signal',
  profit_target: 'profit target',
  stop: 'stop loss',
  risk: 'risk limit',
  margin: 'margin liquidation',
  ruin: 'ruin',
}

/** The colour of each exit reason in the timeline: theme variables (src/index.css), so a bar and its legend entry stay readable in both themes. */
export const EXIT_REASON_COLOR: Record<ExitReason, string> = {
  dte: 'var(--teal)',
  expiry: 'var(--blue)',
  assignment: 'var(--accent)',
  exercise: 'var(--exit-purple)',
  signal: 'var(--exit-sky)',
  profit_target: 'var(--up)',
  stop: 'var(--exit-pink)',
  risk: 'var(--exit-orange)',
  margin: 'var(--down)',
  ruin: 'var(--ink)',
}

/** The colour of a position with no close date and no exit reason: still open at the end of the sample. */
export const OPEN_POSITION_COLOR = 'var(--muted)'
