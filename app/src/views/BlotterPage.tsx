/**
 * The Blotter page: every fill and every expiry event of blotter.json, the file of one engine run.
 *
 * Every number shown is the file's own, formatted (ADR-0001 §6): the page filters, sorts nothing it was not given, and
 * adds nothing up. There is no P&L here because the file has none.
 */
import { useId, useState } from 'react'
import type { AppDataState } from '../data/useAppData'
import {
  BLOTTER_UNIT_KEYS,
  FILL_INTENTS,
  OPTION_FILL_SOURCES,
  SHARE_FILL_SOURCE,
  type Blotter,
  type DataSource,
  type ExpiryEvent,
  type Fill,
  type FillIntent,
  type FillSource,
} from '../lib/contract'
import { fmt } from '../lib/format'
import {
  BLOTTER_CLOSES_NOTICE,
  BLOTTER_DOLTHUB_CHANGES,
  BLOTTER_PAGE_INTRO,
  BLOTTER_VENDOR_NOTICE,
  EVENTS_NOTE,
  FILLS_NOTE,
  NO_EVENTS_MATCH,
  NO_FILLS_MATCH,
} from '../content/blotter'
import { DataNotice, DoltHubAttribution } from './DataNotice'
import { DataProblem } from './DataProblem'
import { EngineRunNotice } from './EngineRunNotice'
import { RunProvenance } from './RunProvenance'
import { useRowLimit } from './rowLimit'
import { ShowMore } from './ShowMore'

/** Shown where a value does not apply (a share fill has no contract, no mid and no half-spread; an early event has no settlement price). */
const NONE = '—'

/** A signed whole number: "+10" bought, "-10" sold. */
function signed(n: number): string {
  return n > 0 ? `+${fmt(n, 0)}` : fmt(n, 0)
}

/** Per-share prices are written at 4 decimals in the file (fees at 2), so that is how they are shown. */
const price = (n: number | null): string => (n === null ? NONE : fmt(n, 4))

function FillsTable({ fills }: { fills: Fill[] }) {
  const [limit, more] = useRowLimit()
  if (fills.length === 0) return <p>{NO_FILLS_MATCH}</p>
  return (
    <>
      <div className="scroll-x">
        <table className="dq" aria-label="Fills">
          <thead>
            <tr>
              <th>Fill</th>
              <th>Date</th>
              <th>Instrument</th>
              <th>Contract</th>
              <th className="num">Qty</th>
              <th className="num">Price</th>
              <th className="num">Mid</th>
              <th className="num">Half-spread</th>
              <th className="num">Fees</th>
              <th>Source</th>
              <th>Intent</th>
            </tr>
          </thead>
          <tbody>
            {fills.slice(0, limit).map((f) => (
              <tr key={f.fill_id}>
                <th scope="row">{f.fill_id}</th>
                <td>{f.date}</td>
                <td>{f.instrument}</td>
                <td className="osi">{f.osi_symbol ?? NONE}</td>
                <td className="num">{signed(f.qty)}</td>
                <td className="num">{price(f.price)}</td>
                <td className="num">{price(f.mid)}</td>
                <td className="num">{price(f.half_spread)}</td>
                <td className="num">{fmt(f.fees, 2)}</td>
                <td>{f.fill_source}</td>
                <td>{f.intent}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ShowMore shown={Math.min(limit, fills.length)} total={fills.length} more={more} />
    </>
  )
}

function EventsTable({ events }: { events: ExpiryEvent[] }) {
  const [limit, more] = useRowLimit()
  if (events.length === 0) return <p>{NO_EVENTS_MATCH}</p>
  return (
    <>
      <div className="scroll-x">
        <table className="dq" aria-label="Expiry events">
          <thead>
            <tr>
              <th>Event</th>
              <th>Date</th>
              <th>Books on</th>
              <th>Contract</th>
              <th>Type</th>
              <th className="num">Contracts</th>
              <th className="num">Shares delivered</th>
              <th className="num">Strike</th>
              <th className="num">Settlement price</th>
              <th>Pin</th>
            </tr>
          </thead>
          <tbody>
            {events.slice(0, limit).map((e) => (
              <tr key={e.event_id}>
                <th scope="row">{e.event_id}</th>
                <td>{e.date}</td>
                <td>{e.effective_date}</td>
                <td className="osi">{e.osi_symbol}</td>
                <td>{e.event_type}</td>
                <td className="num">{signed(e.contracts)}</td>
                <td className="num">{signed(e.shares_delivered)}</td>
                <td className="num">{price(e.strike)}</td>
                <td className="num">{price(e.settlement_price)}</td>
                <td>{e.pin_flag ? 'yes' : 'no'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ShowMore shown={Math.min(limit, events.length)} total={events.length} more={more} />
    </>
  )
}

/** What each unit key of the file means, as the file says it: the table headers name the fields, this names their units. */
function Units({ file }: { file: Blotter }) {
  return (
    <dl className="meta units">
      {BLOTTER_UNIT_KEYS.map((key) => (
        <div key={key} className="unit-row">
          <dt>{key}</dt>
          <dd>{file.units[key]}</dd>
        </div>
      ))}
    </dl>
  )
}

type Choice<T extends string> = T | 'all'

function Tables({ file }: { file: Blotter }) {
  const id = useId()
  const [intent, setIntent] = useState<Choice<FillIntent>>('all')
  const [source, setSource] = useState<Choice<FillSource>>('all')
  // '' = no bound. An ISO date compares as text, so the filters need no date arithmetic.
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  // Only the values the file has: a choice the file cannot satisfy would only show an empty table.
  const intents = FILL_INTENTS.filter((i) => file.fills.some((f) => f.intent === i))
  const sources = [...OPTION_FILL_SOURCES, SHARE_FILL_SOURCE].filter((s) => file.fills.some((f) => f.fill_source === s))
  const inRange = (date: string): boolean => (from === '' || date >= from) && (to === '' || date <= to)
  const fills = file.fills.filter((f) => (intent === 'all' || f.intent === intent) && (source === 'all' || f.fill_source === source) && inRange(f.date))
  const events = file.events.filter((e) => inRange(e.date))
  const filtered = intent !== 'all' || source !== 'all' || from !== '' || to !== ''
  const reset = (): void => {
    setIntent('all')
    setSource('all')
    setFrom('')
    setTo('')
  }
  return (
    <>
      <h3>Fills</h3>
      <div className="controls" role="group" aria-label="Filters">
        <label htmlFor={`${id}-intent`}>Intent</label>
        <select id={`${id}-intent`} value={intent} onChange={(e) => setIntent(e.target.value as Choice<FillIntent>)}>
          <option value="all">all intents</option>
          {intents.map((i) => (
            <option key={i} value={i}>
              {i}
            </option>
          ))}
        </select>
        <label htmlFor={`${id}-source`}>Fill source</label>
        <select id={`${id}-source`} value={source} onChange={(e) => setSource(e.target.value as Choice<FillSource>)}>
          <option value="all">all sources</option>
          {sources.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <label htmlFor={`${id}-from`}>From</label>
        <input id={`${id}-from`} type="date" min={file.run.sample_start} max={file.run.sample_end} value={from} onChange={(e) => setFrom(e.target.value)} />
        <label htmlFor={`${id}-to`}>To</label>
        <input id={`${id}-to`} type="date" min={file.run.sample_start} max={file.run.sample_end} value={to} onChange={(e) => setTo(e.target.value)} />
        <button type="button" onClick={reset} disabled={!filtered}>
          Clear filters
        </button>
      </div>
      <p className="sub" role="status">
        Showing {fmt(fills.length, 0)} of {fmt(file.fills.length, 0)} fills and {fmt(events.length, 0)} of {fmt(file.events.length, 0)} events.
      </p>
      <div className="card">
        {/* key: a new filter starts the table again from its first rows */}
        <FillsTable key={`${intent}|${source}|${from}|${to}`} fills={fills} />
        <p className="sub">{FILLS_NOTE}</p>
      </div>
      <h3>Expiry events</h3>
      <div className="card">
        <EventsTable key={`${from}|${to}`} events={events} />
        <p className="sub">{EVENTS_NOTE}</p>
      </div>
      <div className="card">
        <h3>Units</h3>
        <Units file={file} />
      </div>
      <div className="card">
        <RunProvenance file={file} />
      </div>
    </>
  )
}

/**
 * The data notice follows the file's run.data_source: its vendor's paragraph, the CC BY-SA attribution for DoltHub, and
 * where the SPY prices come from. Without a file (loading, or a load error) no number is on the page and no vendor is named.
 */
function BlotterNotice({ source }: { source: DataSource | null }) {
  return (
    <DataNotice>
      {source !== null && (
        <>
          <p className="sub">{BLOTTER_VENDOR_NOTICE[source]}</p>
          {source === 'dolthub' && <DoltHubAttribution changes={BLOTTER_DOLTHUB_CHANGES} />}
          <p className="sub">{BLOTTER_CLOSES_NOTICE}</p>
        </>
      )}
    </DataNotice>
  )
}

export function BlotterPage({ state }: { state: AppDataState }) {
  const file = state.status === 'ready' ? state.data.blotter : null
  return (
    <section className="blotter-page">
      <h2>Blotter</h2>
      <p className="sub">{BLOTTER_PAGE_INTRO}</p>
      <EngineRunNotice run={file?.run ?? null} />
      {state.status === 'loading' && <p>Loading the exported blotter…</p>}
      {state.status === 'error' && <DataProblem error={state.error} />}
      {file !== null && <Tables file={file} />}
      <BlotterNotice source={file?.run.data_source ?? null} />
    </section>
  )
}
