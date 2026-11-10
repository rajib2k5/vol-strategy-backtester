/**
 * The Positions page: when each position of positions_timeline.json was open, and how many were open at each close.
 *
 * The timeline is drawn, not computed: a bar's ends are the file's own dates placed on a scale (ADR-0001 §6), and the
 * count line is the file's open_count. There is no P&L here because the file has none.
 */
import { useId } from 'react'
import type { AppDataState } from '../data/useAppData'
import { EXIT_REASONS, POSITIONS_TIMELINE_UNIT_KEYS, type DataSource, type ExitReason, type Position, type PositionsTimeline } from '../lib/contract'
import { fmt } from '../lib/format'
import { LineChart } from '../lib/LineChart'
import { EXIT_REASON_COLOR, EXIT_REASON_TEXT, OPEN_POSITION_COLOR } from '../content/engineRun'
import { COUNT_NOTE, NO_POSITIONS, POSITIONS_DOLTHUB_CHANGES, POSITIONS_PAGE_INTRO, POSITIONS_VENDOR_NOTICE } from '../content/positions'
import { DataNotice, DoltHubAttribution } from './DataNotice'
import { DataProblem } from './DataProblem'
import { EngineRunNotice } from './EngineRunNotice'
import { RunProvenance } from './RunProvenance'
import { useRowLimit } from './rowLimit'
import { ShowMore } from './ShowMore'

const NONE = '—'

/** A signed whole number: "+1" long, "-1" short. */
function signed(n: number): string {
  return n > 0 ? `+${fmt(n, 0)}` : fmt(n, 0)
}

// The timeline's geometry, in SVG units (the svg scales to the page's width). A right margin leaves room for the "open" mark.
const WIDTH = 720
const LEFT = 12
const RIGHT = 48
const TOP = 22
const ROW = 7
const BAR = 5
const BOTTOM = 16
const MIN_BAR_WIDTH = 1.5
const MS_PER_DAY = 86_400_000

/** The day a YYYY-MM-DD date falls on, as a count the scale can place; only ever differences of these are used. */
const day = (date: string): number => Date.parse(`${date}T00:00:00Z`) / MS_PER_DAY

/** How a position's bar is drawn: its colour, and whether it is the dashed bar of a position with no close date. */
function barStyle(p: Position): { color: string; open: boolean } {
  return { color: p.exit_reason === null ? OPEN_POSITION_COLOR : EXIT_REASON_COLOR[p.exit_reason], open: p.closed === null }
}

/** The text a position's bar carries for a screen reader and a hover: what it was, when, and how it ended. */
function barTitle(p: Position): string {
  const end = p.closed === null ? 'no close date (drawn to the end of the sample)' : `closed ${p.closed}`
  return `Position ${p.position_id}, ${p.structure}: opened ${p.opened}, ${end}, ${p.exit_reason === null ? 'open' : `exit reason ${p.exit_reason}`}`
}

/** The exit reasons the file uses, in EXIT_REASONS order, each with its positions. */
function reasonsUsed(positions: Position[]): { reason: ExitReason; count: number }[] {
  return EXIT_REASONS.map((reason) => ({ reason, count: positions.filter((p) => p.exit_reason === reason).length })).filter((r) => r.count > 0)
}

function Legend({ positions }: { positions: Position[] }) {
  const open = positions.filter((p) => p.exit_reason === null).length
  return (
    <ul className="legend" aria-label="Exit reasons">
      {reasonsUsed(positions).map(({ reason, count }) => (
        <li key={reason}>
          <span className="swatch" style={{ background: EXIT_REASON_COLOR[reason] }} aria-hidden="true" />
          <span>
            <strong>{reason}</strong>: {EXIT_REASON_TEXT[reason]} ({fmt(count, 0)})
          </span>
        </li>
      ))}
      {open > 0 && (
        <li>
          <span className="swatch open" style={{ borderColor: OPEN_POSITION_COLOR }} aria-hidden="true" />
          <span>
            <strong>open</strong>: no close date, drawn to the end of the sample ({fmt(open, 0)})
          </span>
        </li>
      )}
    </ul>
  )
}

/** The year ticks of the time axis: January 1st of each year inside the sample, thinned so that no more than about 8 are drawn. */
function yearTicks(start: string, end: string): number[] {
  const first = Number(start.slice(0, 4)) + 1
  const last = Number(end.slice(0, 4))
  const years = Array.from({ length: Math.max(0, last - first + 1) }, (_, n) => first + n)
  const every = Math.ceil(years.length / 8)
  return years.filter((_, n) => n % every === 0)
}

/** The timeline of a run's positions: PositionsTimeline's, and each run of strategy_positions.json (the Strategies page). */
export function Timeline({ file, title = 'When each position was open' }: { file: Pick<PositionsTimeline, 'positions' | 'run'>; title?: string }) {
  const id = useId()
  const { positions, run } = file
  const t0 = day(run.sample_start)
  const span = Math.max(day(run.sample_end) - t0, 1)
  const x = (date: string): number => LEFT + ((day(date) - t0) / span) * (WIDTH - LEFT - RIGHT)
  const height = TOP + positions.length * ROW + BOTTOM
  const open = positions.filter((p) => p.closed === null).length
  return (
    <svg viewBox={`0 0 ${WIDTH} ${height}`} style={{ width: '100%', height: 'auto' }} role="img" aria-labelledby={`${id}-title`} aria-describedby={`${id}-desc`}>
      <title id={`${id}-title`}>{title}</title>
      <desc id={`${id}-desc`}>
        {`${fmt(positions.length, 0)} positions from ${run.sample_start} to ${run.sample_end}, one bar each, in the order they were opened, top to bottom. A bar runs from the day the position was opened to the day it was closed and is coloured by its exit reason (the list above names them).${open > 0 ? ` ${fmt(open, 0)} of them have no close date and are drawn to ${run.sample_end}, dashed.` : ''}`}
      </desc>
      {/* the sample's first and last day under the bars, where no year tick label can run into them */}
      <text x={LEFT} y={height - 3} fontSize="10" fill="var(--muted, #929db0)" fontFamily="monospace">
        {run.sample_start}
      </text>
      <text x={WIDTH - RIGHT} y={height - 3} fontSize="10" textAnchor="end" fill="var(--muted, #929db0)" fontFamily="monospace">
        {run.sample_end}
      </text>
      {yearTicks(run.sample_start, run.sample_end).map((year) => (
        <g key={year}>
          <line x1={x(`${year}-01-01`)} x2={x(`${year}-01-01`)} y1={TOP - 6} y2={height - BOTTOM + 2} stroke="var(--line, #2c3547)" strokeWidth="1" />
          <text x={x(`${year}-01-01`) + 3} y={TOP - 9} fontSize="10" fill="var(--muted, #929db0)" fontFamily="monospace">
            {year}
          </text>
        </g>
      ))}
      {positions.map((p, i) => {
        const { color, open: noClose } = barStyle(p)
        const x1 = x(p.opened)
        const x2 = x(p.closed ?? run.sample_end)
        const y = TOP + i * ROW
        return (
          <g key={p.position_id}>
            <rect
              x={x1}
              y={y}
              width={Math.max(x2 - x1, MIN_BAR_WIDTH)}
              height={BAR}
              fill={color}
              fillOpacity={noClose ? 0.35 : 1}
              stroke={noClose ? color : 'none'}
              strokeDasharray={noClose ? '3 2' : undefined}
              data-position={p.position_id}
            >
              <title>{barTitle(p)}</title>
            </rect>
            {noClose && (
              <text x={x2 + 4} y={y + BAR} fontSize="9" fontFamily="monospace" fill={color}>
                {p.exit_reason ?? 'open'}
              </text>
            )}
          </g>
        )
      })}
    </svg>
  )
}

function CountChart({ file }: { file: PositionsTimeline }) {
  const id = useId()
  const first = file.dates[0]
  const last = file.dates[file.dates.length - 1]
  return (
    <figure className="chart" aria-labelledby={`${id}-title`} aria-describedby={`${id}-desc`}>
      <h3 id={`${id}-title`}>Positions open at each close</h3>
      <LineChart series={[{ name: 'positions open', values: file.open_count }]} yLabel={file.units.open_count} />
      <figcaption id={`${id}-desc`} className="sub">
        {fmt(file.dates.length, 0)} sessions, {first} to {last}, left to right. {COUNT_NOTE}
      </figcaption>
    </figure>
  )
}

function legText(osi: string, ratio: number): string {
  return `${osi} × ${signed(ratio)}`
}

function PositionsTable({ positions }: { positions: Position[] }) {
  const [limit, more] = useRowLimit()
  return (
    <>
      <div className="scroll-x">
        <table className="dq" aria-label="Positions">
          <thead>
            <tr>
              <th>Position</th>
              <th>Structure</th>
              <th>Opened</th>
              <th>Closed</th>
              <th>Exit reason</th>
              <th>Legs</th>
            </tr>
          </thead>
          <tbody>
            {positions.slice(0, limit).map((p) => (
              <tr key={p.position_id}>
                <th scope="row">{p.position_id}</th>
                <td>{p.structure}</td>
                <td>{p.opened}</td>
                <td>{p.closed ?? 'no close date'}</td>
                <td>{p.exit_reason ?? (p.closed === null ? 'open' : NONE)}</td>
                <td>
                  <ul className="legs">
                    {p.legs.map((leg, i) => (
                      <li key={i} className="osi">
                        {legText(leg.osi_symbol, leg.ratio)}
                      </li>
                    ))}
                  </ul>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ShowMore shown={Math.min(limit, positions.length)} total={positions.length} more={more} />
    </>
  )
}

function Charts({ file }: { file: PositionsTimeline }) {
  return (
    <>
      <div className="card">
        <h3>When each position was open</h3>
        {file.positions.length === 0 ? (
          <p>{NO_POSITIONS}</p>
        ) : (
          <>
            <Legend positions={file.positions} />
            <Timeline file={file} />
          </>
        )}
      </div>
      <div className="card">
        <CountChart file={file} />
      </div>
      <div className="card">
        <h3>The positions</h3>
        {file.positions.length === 0 ? <p>{NO_POSITIONS}</p> : <PositionsTable positions={file.positions} />}
        <dl className="meta units">
          {POSITIONS_TIMELINE_UNIT_KEYS.map((key) => (
            <div key={key} className="unit-row">
              <dt>{key}</dt>
              <dd>{file.units[key]}</dd>
            </div>
          ))}
        </dl>
      </div>
      <div className="card">
        <RunProvenance file={file} />
      </div>
    </>
  )
}

/**
 * The data notice follows the file's run.data_source: its vendor's paragraph and, for DoltHub, the CC BY-SA attribution.
 * Without a file (loading, or a load error) no vendor is named.
 */
function PositionsNotice({ source }: { source: DataSource | null }) {
  return (
    <DataNotice>
      {source !== null && (
        <>
          <p className="sub">{POSITIONS_VENDOR_NOTICE[source]}</p>
          {source === 'dolthub' && <DoltHubAttribution changes={POSITIONS_DOLTHUB_CHANGES} />}
        </>
      )}
    </DataNotice>
  )
}

export function PositionsPage({ state }: { state: AppDataState }) {
  const file = state.status === 'ready' ? state.data.positionsTimeline : null
  return (
    <section className="positions-page">
      <h2>Positions</h2>
      <p className="sub">{POSITIONS_PAGE_INTRO}</p>
      <EngineRunNotice run={file?.run ?? null} />
      {state.status === 'loading' && <p>Loading the exported positions…</p>}
      {state.status === 'error' && <DataProblem error={state.error} />}
      {file !== null && <Charts file={file} />}
      <PositionsNotice source={file?.run.data_source ?? null} />
    </section>
  )
}
