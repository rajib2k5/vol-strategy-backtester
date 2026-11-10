/**
 * The Strategies page: strategy_positions.json drawn as the file gives it. The banner comes first, as written. Per run, the
 * strategy, its params (as text, never interpreted), its trial group, and a timeline of its positions coloured by exit reason.
 * There is no count of positions per exit reason on the page: that count is a result, and no P&L, because the file has none.
 */
import type { AppDataState } from '../data/useAppData'
import { EXIT_REASONS, STRATEGY_POSITIONS_UNIT_KEYS, type StrategyPosition, type StrategyPositions, type StrategyRun } from '../lib/contract'
import { fmt } from '../lib/format'
import { EXIT_REASON_COLOR, EXIT_REASON_TEXT, OPEN_POSITION_COLOR } from '../content/engineRun'
import { NO_STRATEGY_POSITIONS, STRATEGIES_PAGE_INTRO } from '../content/strategies'
import { DataProblem } from './DataProblem'
import { Timeline } from './PositionsPage'
import { RunMeta } from './RunProvenance'
import { useRowLimit } from './rowLimit'
import { ShowMore } from './ShowMore'

const NONE = '—'

/** A signed whole number: "+1" long, "-1" short. */
function signed(n: number): string {
  return n > 0 ? `+${fmt(n, 0)}` : fmt(n, 0)
}

/** A param value as text: a string as it is, anything else as JSON. */
const paramText = (v: unknown): string => (typeof v === 'string' ? v : JSON.stringify(v))

/** Which exit reasons the run's positions have (in EXIT_REASONS order), each once, and whether any position is open: a legend, not a count. */
function Legend({ run }: { run: StrategyRun }) {
  const used = EXIT_REASONS.filter((r) => run.positions.some((p) => p.exit_reason === r))
  const open = run.positions.some((p) => p.closed === null)
  return (
    <ul className="legend" aria-label={`Exit reasons of ${run.strategy}`}>
      {used.map((reason) => (
        <li key={reason}>
          <span className="swatch" style={{ background: EXIT_REASON_COLOR[reason] }} aria-hidden="true" />
          <span>
            <strong>{reason}</strong>: {EXIT_REASON_TEXT[reason]}
          </span>
        </li>
      ))}
      {open && (
        <li>
          <span className="swatch open" style={{ borderColor: OPEN_POSITION_COLOR }} aria-hidden="true" />
          <span>
            <strong>open</strong>: no close date, drawn to the end of the sample
          </span>
        </li>
      )}
    </ul>
  )
}

function PositionsTable({ run }: { run: StrategyRun }) {
  const [limit, more] = useRowLimit()
  const rows: StrategyPosition[] = run.positions
  return (
    <>
      <div className="scroll-x">
        <table className="dq" aria-label={`Positions of ${run.strategy}`}>
          <thead>
            <tr>
              <th>Position</th>
              <th>Structure</th>
              <th>Opened</th>
              <th>Closed</th>
              <th>Exit reason</th>
              <th>Entry signal</th>
              <th>Legs</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, limit).map((p) => (
              <tr key={p.position_id}>
                <th scope="row">{p.position_id}</th>
                <td>{p.structure}</td>
                <td>{p.opened}</td>
                <td>{p.closed ?? 'open'}</td>
                <td>{p.exit_reason ?? NONE}</td>
                <td>{p.entry_signal === null ? NONE : fmt(p.entry_signal, 4)}</td>
                <td>
                  <ul className="legs">
                    {p.legs.map((leg, i) => (
                      <li key={i} className="osi">
                        {leg.osi_symbol} × {signed(leg.ratio)}
                      </li>
                    ))}
                  </ul>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ShowMore shown={Math.min(limit, rows.length)} total={rows.length} more={more} />
    </>
  )
}

function RunCard({ run, file }: { run: StrategyRun; file: StrategyPositions }) {
  return (
    <div className="card" aria-label={`Run of ${run.strategy}`} role="region">
      <h3>{run.strategy}</h3>
      <dl className="meta">
        <dt>Trial group</dt>
        <dd>{run.trial_group}</dd>
        <dt>Trials in the group</dt>
        <dd>{fmt(run.n_trials_group, 0)}</dd>
        {Object.entries(run.params).map(([key, value]) => (
          <div key={key} className="unit-row">
            <dt>{key}</dt>
            <dd>{paramText(value)}</dd>
          </div>
        ))}
      </dl>
      {run.positions.length === 0 ? (
        <p>{NO_STRATEGY_POSITIONS}</p>
      ) : (
        <>
          <Legend run={run} />
          <Timeline file={run} title={`When each position of ${run.strategy} was open`} />
          <PositionsTable run={run} />
        </>
      )}
      <h4>Where these numbers come from</h4>
      <RunMeta run={run.run} schemaVersion={file.schema_version} />
    </div>
  )
}

function Runs({ file }: { file: StrategyPositions }) {
  return (
    <>
      {file.runs.map((run) => (
        <RunCard key={run.run.run_id} run={run} file={file} />
      ))}
      <div className="card">
        <h3>Units and source</h3>
        <p className="sub">{file.label}</p>
        <dl className="meta units">
          {STRATEGY_POSITIONS_UNIT_KEYS.map((key) => (
            <div key={key} className="unit-row">
              <dt>{key}</dt>
              <dd>{file.units[key]}</dd>
            </div>
          ))}
        </dl>
      </div>
    </>
  )
}

export function StrategiesPage({ state }: { state: AppDataState }) {
  const file = state.status === 'ready' ? (state.data.strategyPositions ?? null) : null
  return (
    <section className="strategies-page">
      <h2>Strategies</h2>
      {file !== null && (
        <section className="notice" aria-label="Trial count">
          <strong>{file.banner}</strong>
        </section>
      )}
      <p className="sub">{STRATEGIES_PAGE_INTRO}</p>
      {state.status === 'loading' && <p>Loading the exported strategies…</p>}
      {state.status === 'error' && <DataProblem error={state.error} />}
      {file !== null && <Runs file={file} />}
    </section>
  )
}
