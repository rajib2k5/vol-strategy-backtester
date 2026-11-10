/**
 * The Signal page: signals_timeline.json drawn as the file gives it. The series are placed on a date scale, the
 * threshold lines are the file's thresholds (an exit level is the entry level minus the exit band, which is where the
 * line sits and nothing more), and the forecast-test card shows the file's own numbers (ADR-0001 §6).
 */
import { useId } from 'react'
import type { AppDataState } from '../data/useAppData'
import { SIGNALS_TIMELINE_UNIT_KEYS, type ForecastTest, type SignalsTimeline } from '../lib/contract'
import { DatedLineChart, type LevelLine } from '../lib/DatedLineChart'
import { fmt } from '../lib/format'
import { FORECAST_NOT_SCORED, FORECAST_TEST_NOTE, fragileNotice, LEVELS_NOTE, NO_FITS, SIGNAL_IN_SAMPLE_NOTE, SIGNAL_PAGE_INTRO } from '../content/signal'
import { DataProblem } from './DataProblem'
import { RunProvenance } from './RunProvenance'

/** The entry and exit levels of the file's thresholds, one per distinct level, each with the names of what sits on it. */
function thresholdLevels(file: SignalsTimeline): LevelLine[] {
  const { short_entry, long_entry, exit_band } = file.thresholds
  const named: [number, string][] = [
    [short_entry[0], 'short entry'],
    [short_entry[1], 'short entry'],
    [long_entry, 'long entry'],
    [short_entry[0] - exit_band, 'short exit'],
    [short_entry[1] - exit_band, 'short exit'],
    [long_entry + exit_band, 'long exit'],
  ]
  const byLevel = new Map<number, string[]>()
  for (const [y, name] of named) byLevel.set(y, [...(byLevel.get(y) ?? []), name])
  return [...byLevel].map(([y, names]) => ({ y, label: `${y}: ${names.join(', ')}` }))
}

function PriceChart({ file }: { file: SignalsTimeline }) {
  const id = useId()
  const first = file.dates[0]
  const last = file.dates[file.dates.length - 1]
  return (
    <figure className="chart" aria-labelledby={`${id}-title`} aria-describedby={`${id}-desc`}>
      <h3 id={`${id}-title`}>IV30, forecast vol and ex-post realised vol</h3>
      <DatedLineChart
        dates={file.dates}
        series={[
          { name: 'IV30', values: file.iv30, color: 'var(--accent)' },
          { name: 'RV forecast', values: file.rv_forecast, color: 'var(--teal)' },
          { name: 'RV realised (ex post)', values: file.rv_realised, color: 'var(--blue)' },
        ]}
        marks={file.fits.map((f) => ({ date: f.fit_date, label: `HAR refit ${f.fit_date}` }))}
        yLabel="annualised vol, decimal"
      />
      <figcaption id={`${id}-desc`} className="sub">
        {fmt(file.dates.length, 0)} dates, {first} to {last}, left to right. A gap in a line is a date the file has no value for. Dotted vertical lines mark the refits of the forecast model that fall in this range.
      </figcaption>
    </figure>
  )
}

function RatioChart({ file }: { file: SignalsTimeline }) {
  const id = useId()
  const levels = thresholdLevels(file)
  return (
    <figure className="chart" aria-labelledby={`${id}-title`} aria-describedby={`${id}-desc`}>
      <h3 id={`${id}-title`}>Log variance ratio</h3>
      <DatedLineChart
        dates={file.dates}
        series={[{ name: 'log variance ratio', values: file.log_var_ratio, color: 'var(--exit-purple)' }]}
        levels={levels}
        marks={file.fits.map((f) => ({ date: f.fit_date, label: `HAR refit ${f.fit_date}` }))}
        yLabel={file.units.log_var_ratio}
      />
      <figcaption id={`${id}-desc`} className="sub">
        {LEVELS_NOTE}
      </figcaption>
      <ul className="legend" aria-label="Threshold levels">
        {levels.map((l) => (
          <li key={l.y}>{l.label}</li>
        ))}
      </ul>
    </figure>
  )
}

function ForecastTestCard({ test }: { test: ForecastTest | null }) {
  return (
    <div className="card">
      <h3>Forecast test</h3>
      {test === null ? (
        <p>{FORECAST_NOT_SCORED}</p>
      ) : (
        <>
          <p className="sub">{FORECAST_TEST_NOTE}</p>
          {test.fragile && (
            <section className="notice" aria-label="Fragile decision">
              {fragileNotice(test.fragile_band)}
            </section>
          )}
          <dl className="meta">
            <dt>Decision</dt>
            <dd>{test.decision}</dd>
            <dt>p</dt>
            <dd>{fmt(test.p, 4)}</dd>
            <dt>p (Holm)</dt>
            <dd>{fmt(test.p_holm, 4)}</dd>
            <dt>Threshold (p &lt;)</dt>
            <dd>{fmt(test.threshold, 3)}</dd>
            <dt>Fragile band</dt>
            <dd>{`[${test.fragile_band[0]}, ${test.fragile_band[1]})`}</dd>
            <dt>Effective size (ABC-weighted, battery / second seed)</dt>
            <dd>
              {fmt(test.effective_size.abc_size_battery_seed, 4)} / {fmt(test.effective_size.abc_size_second_seed, 4)}
            </dd>
            <dt>Worst matched size (battery / second seed)</dt>
            <dd>
              {fmt(test.effective_size.worst_matched_battery_seed.rate, 4)} / {fmt(test.effective_size.worst_matched_second_seed.rate, 4)}
              <br />
              <span className="sub">
                {test.effective_size.worst_matched_battery_seed.null_side}; {test.effective_size.worst_matched_second_seed.null_side}
              </span>
            </dd>
            <dt>EWC t</dt>
            <dd>{fmt(test.ewc_t, 2)}</dd>
            <dt>Confidence interval</dt>
            <dd>
              [{fmt(test.ci[0], 4)}, {fmt(test.ci[1], 4)}]
            </dd>
            <dt>Block</dt>
            <dd>{fmt(test.block, 0)}</dd>
            <dt>q</dt>
            <dd>{fmt(test.q, 0)}</dd>
            <dt>n</dt>
            <dd>{fmt(test.n, 0)}</dd>
            <dt>Window</dt>
            <dd>{test.window}</dd>
            <dt>Label</dt>
            <dd>{test.label}</dd>
            <dt>Pre-registration</dt>
            <dd>
              <code>{test.prereg_id}</code>
            </dd>
            <dt>SHA-256</dt>
            <dd>
              <code>{test.prereg_sha256}</code>
            </dd>
          </dl>
        </>
      )}
    </div>
  )
}

function Charts({ file }: { file: SignalsTimeline }) {
  return (
    <>
      <div className="card">
        <PriceChart file={file} />
      </div>
      <div className="card">
        <RatioChart file={file} />
      </div>
      <ForecastTestCard test={file.forecast_test} />
      <div className="card">
        <h3>The forecast model</h3>
        <p className="sub">
          {file.signal.name}: {file.signal.rv_model} forecast, {file.signal.window_days}-day window, {file.signal.horizon}-session horizon, at least {file.signal.min_pairs} pairs to fit.
        </p>
        {file.fits.length === 0 ? (
          <p>{NO_FITS}</p>
        ) : (
          <p>
            Refit dates: <span className="osi">{file.fits.map((f) => f.fit_date).join(', ')}</span>
          </p>
        )}
        <dl className="meta units">
          {SIGNALS_TIMELINE_UNIT_KEYS.map((key) => (
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

export function SignalPage({ state }: { state: AppDataState }) {
  const file = state.status === 'ready' ? (state.data.signalsTimeline ?? null) : null
  return (
    <section className="signal-page">
      <h2>Signal</h2>
      <p className="sub">{SIGNAL_PAGE_INTRO}</p>
      <section className="notice" aria-label="What this series is">
        {SIGNAL_IN_SAMPLE_NOTE}
      </section>
      {state.status === 'loading' && <p>Loading the exported signal…</p>}
      {state.status === 'error' && <DataProblem error={state.error} />}
      {file !== null && <Charts file={file} />}
    </section>
  )
}
