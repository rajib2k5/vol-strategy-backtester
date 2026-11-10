/**
 * Static copy for the Signal page. Plain strings so the wording can be revised without touching any component.
 * Numbers are never written here: every figure on the page comes from signals_timeline.json.
 */

export const SIGNAL_PAGE_INTRO =
  'The volatility signal the strategies trade on: the 30-day implied vol (IV30), the forecast of the vol over the next 30 calendar days, and the vol that was realised over that window, ex post. The log variance ratio compares the first two, and the dashed lines mark the levels at which a strategy enters and exits.'

export const SIGNAL_IN_SAMPLE_NOTE =
  'This series is in-sample development data. Every date is on or before 2019-12-31, the end of the development split, and the ex-post vol is left empty wherever its 30-day window would end after it. Nothing on this page is a trading result.'

export const FORECAST_NOT_SCORED = 'Forecast test: not scored yet'

export const FORECAST_TEST_NOTE =
  'The forecast test compares the forecast model with the naive one. It is a proxy for how the signal would trade, not a result of trading it, and the timeline shows the model the test chose. The threshold is the level the p value must fall below to choose the forecast model. The effective size is how often the test chooses it when it should not.'

export const LEVELS_NOTE = 'The dashed lines are drawn at the levels in the file’s thresholds. An exit level is the entry level minus the exit band.'

export const NO_FITS = 'The naive model is not fitted, so there are no refits.'

/** The notice for a p inside the fragile band; the band is the file's. */
export const fragileNotice = (band: [number, number]): string => `p in [${band[0]}, ${band[1]}): decided by modelling choices`
