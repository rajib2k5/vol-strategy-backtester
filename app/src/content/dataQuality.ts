/**
 * Static copy for the Data quality page. Plain strings so the wording can be revised without
 * touching any component. Numbers are never written here: every figure on the page comes from
 * data_quality.json.
 */

export const DATA_QUALITY_INTRO =
  'Every option quote is kept and flagged: a quote can carry several of 13 quality flags, and each part of the engine picks the flags it cares about (ADR-0009). This page shows how many quotes carry each flag, what the calendar fixed, how closely the two vendors agree, and whether the build passed its quality gate.'

export const GATE_NOTE =
  'The limits were set after looking at the data, each above the worst value seen with some headroom. The gate is a tripwire for a broken download or loader. It is not a statement that the data is good.'

export const SOURCES_NOTE = 'A quote is one contract on one snapshot date, calls and puts counted separately.'

/** The calendar actions, as the prose above the calendar table explains them. The contract accepts exactly these two (CALENDAR_ACTION_NAMES). */
export const CALENDAR_ACTIONS: { action: string; meaning: string }[] = [
  { action: 'session', meaning: 'the vendor date is a day SPY traded; its quotes are kept as dated.' },
  {
    action: 'drop',
    meaning:
      'the vendor date is not a day SPY traded, in either source. Its quotes are removed, and a date is never moved to a neighbouring session; these are the only quotes the build deletes.',
  },
]

export const FLAGS_NOTE =
  'The chart follows four flags that mark a broken feed (the gate limits each of them): one line per flag, one point per year, oldest year on the left. The table lists all 13 flags.'

export const CROSSVENDOR_NOTE =
  'Where both vendors list the same contract on the same day, how far apart are their numbers? There is no verdict here. The thresholds below were chosen after looking at these same dates, so a pass or fail on them could not fail; each row reports the share of dates inside its threshold, and the table by year shows where that share is lower. A few dates carry a broken vendor IV column, which gives the IV gap a long tail.'

export const BY_YEAR_NOTE =
  'The pooled shares hide that the years differ. Each parity spot is the European identity on raw mids, so an American put’s early-exercise premium is not removed, and a spot that drifts below the close as rates rise is expected rather than a fault in either vendor.'

/**
 * The flags the chart follows, in the order of its legend, each with its own theme colour (a CSS
 * variable, so the line and its legend entry stay readable in both themes). A flag the file does
 * not carry is left out.
 */
export const CHART_FLAGS: { flag: string; color: string }[] = [
  { flag: 'BID_NULL', color: 'var(--accent)' },
  { flag: 'CROSSED', color: 'var(--teal)' },
  { flag: 'VENDOR_IV_INVALID', color: 'var(--down)' },
  { flag: 'UNDERLYING_MISMATCH', color: 'var(--blue)' },
]
