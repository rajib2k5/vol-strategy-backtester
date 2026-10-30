/**
 * Static copy for the Surface page. Plain strings so the wording can be revised without touching
 * any component. Numbers are never written here: every figure on the page comes from
 * surface_frames.json.
 */
import type { DataSource } from '../lib/contract'

export const SURFACE_PAGE_INTRO =
  'Real SPY implied-volatility surfaces from the milestone-2 pricing build. Each out-of-the-money quote of the file’s source (named over the view) has its American early-exercise premium removed on a binomial lattice, its implied vol is solved with Black-76 on a forward implied from put-call parity, and each expiry’s smile is read on one fixed grid of log-moneyness and days to expiry. Pick a date to compare a calm market with a crash.'

/** The badge over the 3D view: says the surface is market data, not the illustrative one of the About page. `vendor` is the display name of the file's run.data_source. */
export const realSurfaceBadge = (date: string, vendor: string): string => `SPY implied-vol surface, ${date}: market data (${vendor})`

export const EXTRAPOLATION_NOTE =
  'Not every grid cell is a quote. Between two listed expiries the surface is interpolated, linear in total variance at fixed log-moneyness. Beyond the quoted strikes it is extended with a slope clipped to Lee’s moment bound, and outside the listed tenors the vol is held along log-moneyness over the square root of time (ADR-0004). Those two are extrapolations, not quotes; the quoted share is the share of grid cells read without either. Where two smiles cross, total variance is moved, up or down, so that it never falls with tenor at a fixed log-moneyness, a quoted value taking precedence over an extrapolated one (the calendar adjustment, flagged per cell).'

export const PROVENANCE_NOTE =
  'The run below names what made these surfaces: the pricing build’s code fingerprint (its code, library versions and store settings), and the fingerprint of the input files the frames depend on (each frame year’s option quotes, the rates, dividends, SPY bars and VIX tables). The backtest fields are empty because no strategy ran.'

/** The stat tiles under the surface, in order: [file field, title]. Each tile shows the file's unit for its field. */
export const FRAME_STATS: { field: 'spot' | 'vix_close' | 'atm_iv_30d' | 'quoted_share' | 'expiries_used'; title: string }[] = [
  { field: 'spot', title: 'SPY close' },
  { field: 'vix_close', title: 'VIX close' },
  { field: 'atm_iv_30d', title: '30-day ATM implied vol' },
  { field: 'quoted_share', title: 'Quoted share of the grid' },
  { field: 'expiries_used', title: 'Expiries used' },
]

/**
 * The data notice of the Surface page names the vendor of the file's run.data_source: whose quotes these surfaces are
 * computed from. A DoltHub file also carries the CC BY-SA 4.0 attribution (DOLTHUB_ATTRIBUTION in
 * content/dataNotice.ts), closed by SURFACE_DOLTHUB_CHANGES.
 */
export const SURFACE_VENDOR_NOTICE: Record<DataSource, string> = {
  optionsdx:
    "These surfaces are computed from OptionsDX end-of-day option quotes, obtained through the Kaggle dataset dudesurfin/spy-options-eod-volatility-surface-2010-2023. Kaggle lists that dataset under the MIT licence, but the numbers are OptionsDX's, so we treat them as vendor data and publish only values derived from them.",
  dolthub: 'These surfaces are computed from the SPY option quotes of the DoltHub database post-no-preference/options.',
}

/** What the pricing build did to DoltHub's quotes: the close of the attribution on a DoltHub surface. */
export const SURFACE_DOLTHUB_CHANGES =
  '. Changes: each out-of-the-money quote had its early-exercise premium removed and its implied vol solved, and the smiles were read on a fixed grid of log-moneyness and days to expiry; no quote row is reproduced. The DoltHub-derived surfaces on this page are shared under the same licence.'

/** Where the SPY and VIX closes of every frame come from. Their terms are not restated here: DATA.md, linked in the notice, gives them. */
export const SURFACE_CLOSES_NOTICE =
  'SPY closes come from Yahoo Finance, downloaded with yfinance, and VIX closes from Cboe’s VIX historical data. DATA.md, linked below, gives the terms of each.'
