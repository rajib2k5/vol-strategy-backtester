/**
 * Wording the Surface page and the Data quality page share in their data notice: where the full
 * list of sources and terms lives, that the data is not under the repository's licence, and the
 * DoltHub attribution. The sources each page names are in content/surface.ts and content/dataQuality.ts.
 */

/** Every data source of the project and its terms, at the root of the repository. */
export const DATA_MD_URL = 'https://github.com/rajib2k5/vol-strategy-backtester/blob/main/DATA.md'

/** The notice served next to the data files (app/public/data/LICENSE-DATA.md); relative, like the dataset fetches. */
export const DATA_NOTICE_URL = './data/LICENSE-DATA.md'

export const DATA_NOTICE_TITLE = 'Data sources and terms'

export const NOT_MIT_NOTE = "The data is not covered by this repository's MIT licence."

/**
 * The CC BY-SA 4.0 attribution a page with DoltHub-derived figures carries, as the text around its two links:
 * <lead>, the database link, <licenceLead>, the licence link, then the page's own "Changes: ..." sentence
 * (content/dataQuality.ts, content/surface.ts). Said in full it reads "Contains information derived from the DoltHub
 * database post-no-preference/options, licensed under CC BY-SA 4.0. Changes: ...".
 */
export const DOLTHUB_ATTRIBUTION = {
  lead: 'Contains information derived from the DoltHub database ',
  database: 'post-no-preference/options',
  databaseUrl: 'https://www.dolthub.com/repositories/post-no-preference/options',
  licenceLead: ', licensed under ',
  licence: 'CC BY-SA 4.0',
  licenceUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
} as const

/** The closing line, as the text between and around its two links: <dataMd>, <middle>, <notice>, then a full stop. */
export const DATA_NOTICE_LINKS = {
  dataMd: 'DATA.md',
  middle: ' lists every data source and its terms. The notice served next to the data files is ',
  notice: 'data/LICENSE-DATA.md',
} as const
