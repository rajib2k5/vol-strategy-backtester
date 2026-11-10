/**
 * Static copy for the Positions page. Plain strings so the wording can be revised without touching any component.
 * Numbers are never written here: every figure on the page comes from positions_timeline.json.
 */
import type { DataSource } from '../lib/contract'

export const POSITIONS_PAGE_INTRO =
  'When each position of one engine run was open. A bar runs from the session a position was opened to the session it was closed and is coloured by why it was closed; a position with no close date runs to the end of the sample and is marked. Below it, how many positions were open at each close.'

export const COUNT_NOTE = 'One point per session of the run, oldest on the left. Each point is the number of positions open at that session’s close.'

export const NO_POSITIONS = 'The file holds no positions.'

/**
 * The data notice of the Positions page names the vendor of the file's run.data_source. The page shows contracts and
 * dates, never a quote or a price; a DoltHub file also carries the CC BY-SA 4.0 attribution (DOLTHUB_ATTRIBUTION in
 * content/dataNotice.ts), closed by POSITIONS_DOLTHUB_CHANGES.
 */
export const POSITIONS_VENDOR_NOTICE: Record<DataSource, string> = {
  optionsdx:
    "The contracts on this page are named from OptionsDX end-of-day option quotes, obtained through the Kaggle dataset dudesurfin/spy-options-eod-volatility-surface-2010-2023. Kaggle lists that dataset under the MIT licence, but the numbers are OptionsDX's, so we treat them as vendor data; the page shows no quote and no price.",
  dolthub: 'The contracts on this page are named from the SPY option quotes of the DoltHub database post-no-preference/options.',
}

/** What the page did to DoltHub's data: the close of the attribution on a DoltHub timeline. */
export const POSITIONS_DOLTHUB_CHANGES =
  '. Changes: the contracts and dates of the quotes were used to name each position; no quote row and no price is reproduced. The DoltHub-derived figures on this page are shared under the same licence.'
