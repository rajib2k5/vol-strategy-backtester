/**
 * Static copy for the Blotter page. Plain strings so the wording can be revised without touching any component.
 * Numbers are never written here: every figure on the page comes from blotter.json.
 */
import type { DataSource } from '../lib/contract'

export const BLOTTER_PAGE_INTRO =
  'Every fill the engine booked in one run, one row each, and every expiry or exercise event that settled an option. Narrow the fills by intent, by where the price came from and by date. Prices are USD per share; a quantity is signed, + bought and - sold.'

export const FILLS_NOTE =
  'An option fill names where its price came from (a quote, or the fitted surface) and carries the mid and the half-spread beside the price. A share fill is SPY at the close and has the intent share_liquidation. The date range narrows the events table as well.'

export const EVENTS_NOTE =
  'An option that expires worthless, or is exercised or assigned at expiry, settles against the close of its expiry session. An early exercise or assignment settles at the strike, not at a close, and books on the next session. The pin column is the engine’s own pin_flag, shown as the file gives it.'

/** What the filters do when nothing is left. */
export const NO_FILLS_MATCH = 'No fill matches these filters.'
export const NO_EVENTS_MATCH = 'No event falls in this date range.'

/**
 * The data notice of the Blotter page names the vendor of the file's run.data_source: whose quotes the option fills are
 * priced from. A DoltHub file also carries the CC BY-SA 4.0 attribution (DOLTHUB_ATTRIBUTION in content/dataNotice.ts),
 * closed by BLOTTER_DOLTHUB_CHANGES.
 */
export const BLOTTER_VENDOR_NOTICE: Record<DataSource, string> = {
  optionsdx:
    "The option fills on this page were priced from OptionsDX end-of-day option quotes, obtained through the Kaggle dataset dudesurfin/spy-options-eod-volatility-surface-2010-2023. Kaggle lists that dataset under the MIT licence, but the numbers are OptionsDX's, so we treat them as vendor data and publish only values derived from them: a fill's price, mid and half-spread, never a quote row.",
  dolthub: 'The option fills on this page were priced from the SPY option quotes of the DoltHub database post-no-preference/options.',
}

/** What the engine did to DoltHub's quotes: the close of the attribution on a DoltHub blotter. */
export const BLOTTER_DOLTHUB_CHANGES =
  ". Changes: each fill's price, mid and half-spread were read from one quote of the database; no quote row is reproduced. The DoltHub-derived figures on this page are shared under the same licence."

/** Where the SPY prices of the page come from. Their terms are not restated here: DATA.md, linked in the notice, gives them. */
export const BLOTTER_CLOSES_NOTICE =
  'The price of a share fill and the settlement price of an event are SPY closes from Yahoo Finance, downloaded with yfinance. DATA.md, linked below, gives the terms.'
