/**
 * The data notice at the foot of the Surface and Data quality pages: which sources the numbers on
 * the page come from and under what terms, with links to the full list (DATA.md) and to the notice
 * served next to the data files. Each page passes its own paragraphs; the wording shared by both
 * is in content/dataNotice.ts, and so is the DoltHub attribution either page may carry.
 */
import type { ReactNode } from 'react'
import { DATA_MD_URL, DATA_NOTICE_LINKS, DATA_NOTICE_TITLE, DATA_NOTICE_URL, DOLTHUB_ATTRIBUTION, NOT_MIT_NOTE } from '../content/dataNotice'

export function DataNotice({ children }: { children: ReactNode }) {
  return (
    <section className="card data-notice" aria-label={DATA_NOTICE_TITLE}>
      <h3>{DATA_NOTICE_TITLE}</h3>
      {children}
      <p className="sub">{NOT_MIT_NOTE}</p>
      <p className="sub">
        <a href={DATA_MD_URL}>{DATA_NOTICE_LINKS.dataMd}</a>
        {DATA_NOTICE_LINKS.middle}
        <a href={DATA_NOTICE_URL}>{DATA_NOTICE_LINKS.notice}</a>.
      </p>
    </section>
  )
}

/** The CC BY-SA 4.0 attribution of DoltHub-derived figures, linking the database and the licence; `changes` says what the page did to the data. */
export function DoltHubAttribution({ changes }: { changes: string }) {
  const a = DOLTHUB_ATTRIBUTION
  return (
    <p className="sub">
      {a.lead}
      <a href={a.databaseUrl}>{a.database}</a>
      {a.licenceLead}
      <a href={a.licenceUrl}>{a.licence}</a>
      {changes}
    </p>
  )
}
