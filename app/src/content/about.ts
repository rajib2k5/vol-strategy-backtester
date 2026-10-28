/**
 * Static copy for the About page. Plain strings so the wording can be revised without touching
 * any component.
 */

export const TITLE = 'Vol Strategy Backtester'

export const PITCH =
  'Backtests volatility-mispricing option strategies on SPY with realistic fills, greek risk limits and regime stress tests.'

/** Always shown on the 3D hero, whatever the dataset's own `label` says. */
export const SURFACE_LABEL = 'Illustrative SSVI surface — not market data'

export const DISCLAIMER_HEADLINE = 'Educational project — not financial advice.'

export const DISCLAIMER_BODY =
  'This is a learning project. Nothing here is a recommendation to buy or sell any security or option. Backtests are hypothetical, are built on historical data with simplified fill assumptions, and do not predict future results. Options can lose more than the premium paid.'

export const STATUS =
  'Status: early build. This version ships the app shell, the data contract and an illustrative surface; strategy results are not exported yet.'

export const DOES: string[] = [
  'Prices SPY options with Black-76 on a forward implied from put-call parity, after removing the American early-exercise premium from the quotes, and solves implied volatility from end-of-day quotes.',
  'Compares 30-day implied volatility with HAR and GARCH forecasts of realised volatility to find mispricing. The forecasts are refitted monthly and use only data up to each day.',
  'Backtests straddles, strangles and calendar spreads on standard monthly expiries, day by day, filling the next day at the far side of the spread and capping each line at 100 contracts a day.',
  'Limits vega, gamma, theta and full-revaluation stress loss, checks margin on the net requirement, delta-hedges with SPY, and attributes P&L to the greeks.',
  'Reports Sharpe, Sortino, Calmar, drawdowns, and results by volatility regime and stress scenario, with a Deflated Sharpe Ratio that counts independent trials.',
]

export const DOES_NOT: string[] = [
  'Compute anything in the browser. A Python engine produces the results; this app only draws the JSON it exports.',
  'Trade, connect to a broker or stream live quotes.',
  'Ship market data. Raw vendor files are never committed, and the surface above is synthetic.',
  'Give investment advice or claim a track record.',
]

export interface DataSource {
  name: string
  role: string
}

export const DATA_SOURCES: DataSource[] = [
  { name: 'OptionsDX SPY end-of-day option chains (via Kaggle)', role: 'In-sample option history, 2010–2023.' },
  { name: 'DoltHub post-no-preference/options (SPY)', role: 'Out-of-sample option history, 2024–2026, run once and reported as semi-blind.' },
  { name: 'yfinance', role: 'SPY underlying price history.' },
  { name: 'FRED series DGS3MO', role: '3-month Treasury yield, used as the risk-free rate.' },
  { name: 'CBOE VIX', role: 'Volatility index, used as a market-wide volatility reference.' },
]

export const DATA_SOURCES_NOTE =
  'Raw vendor data is never committed to this repository; only small derived JSON files for this app are.'
