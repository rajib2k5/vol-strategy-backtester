import { useState } from 'react'
import type { AppDataState } from '../data/useAppData'
import { commitState, type CrossVendor, type DataQuality } from '../lib/contract'
import { compact, fmt, pct } from '../lib/format'
import { LineChart } from '../lib/LineChart'
import {
  BY_YEAR_NOTE,
  CALENDAR_ACTIONS,
  CHART_FLAGS,
  CROSSVENDOR_NOTE,
  DATA_QUALITY_INTRO,
  DATA_QUALITY_NOTICE,
  DOLTHUB_CHANGES,
  FLAGS_NOTE,
  GATE_NOTE,
  SOURCES_NOTE,
} from '../content/dataQuality'
import { DataNotice, DoltHubAttribution } from './DataNotice'
import { DataProblem } from './DataProblem'

/** A number with its unit as the file gives it: "fraction" is a share, anything else a plain unit ("quotes", "bp"). */
function amount(value: number, unit: string): string {
  if (unit === 'fraction') return pct(value)
  return `${fmt(value, Number.isInteger(value) ? 0 : 2)} ${unit}`
}

function Verdict({ ok, yes, no }: { ok: boolean; yes: string; no: string }) {
  return <span className={ok ? 'badge ok-badge' : 'badge err-badge'}>{ok ? yes : no}</span>
}

function Failures({ failures }: { failures: string[] }) {
  if (failures.length === 0) return null
  return (
    <ul role="alert" className="failures">
      {failures.map((f, i) => (
        <li key={i}>{f}</li>
      ))}
    </ul>
  )
}

function GateSection({ dq }: { dq: DataQuality }) {
  const { gate } = dq
  const t = gate.thresholds
  return (
    <>
      <h2>Quality gate</h2>
      <div className="card">
        <p className="verdict">
          <Verdict ok={gate.passed} yes="Passed" no="Failed" />
          {gate.passed ? 'The build stayed inside every limit below.' : 'The build broke at least one limit below.'}
        </p>
        <Failures failures={gate.failures} />
        <div className="scroll-x">
          <table className="dq" aria-label="Quality-gate limits">
            <thead>
              <tr>
                <th>Source</th>
                <th>Check</th>
                <th className="num">Limit</th>
                <th className="num">Worst seen</th>
              </tr>
            </thead>
            <tbody>
              {t.rule.map((_, i) => (
                <tr key={i}>
                  <td>{t.source[i]}</td>
                  <td>{t.what[i]}</td>
                  <td className="num">{`${t.bound[i] === 'max' ? '≤' : '≥'} ${amount(t.limit[i], t.unit[i])}`}</td>
                  <td className="num">{amount(t.worst[i], t.unit[i])}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="sub">{GATE_NOTE}</p>
      </div>
    </>
  )
}

function SourcesSection({ dq }: { dq: DataQuality }) {
  const s = dq.sources
  return (
    <>
      <h2>Rows per source</h2>
      <div className="grid">
        {s.source.map((source, i) => (
          <div className="stat" key={source}>
            <div className="k">{source}</div>
            <div className="v">{fmt(s.rows[i], 0)}</div>
            <div className="k">quotes on {fmt(s.dates[i], 0)} snapshot dates</div>
          </div>
        ))}
      </div>
      <p className="sub">{SOURCES_NOTE}</p>
    </>
  )
}

function CalendarSection({ dq }: { dq: DataQuality }) {
  const c = dq.calendar
  return (
    <>
      <h2>Calendar fixes</h2>
      <div className="card">
        <p>
          A vendor can date a snapshot on a day the market was shut. The calendar comes from SPY’s own daily bars, and each vendor date gets
          one of two actions:
        </p>
        <ul>
          {CALENDAR_ACTIONS.map((a) => (
            <li key={a.action}>
              <strong>{a.action}</strong>: {a.meaning}
            </li>
          ))}
        </ul>
        <div className="scroll-x">
          <table className="dq" aria-label="Calendar fixes">
            <thead>
              <tr>
                <th>Source</th>
                <th>Action</th>
                <th className="num">Vendor dates</th>
                <th className="num">Quotes</th>
              </tr>
            </thead>
            <tbody>
              {c.source.map((source, i) => (
                <tr key={i}>
                  <td>{source}</td>
                  <td>{c.action[i]}</td>
                  <td className="num">{fmt(c.dates[i], 0)}</td>
                  <td className="num">{fmt(c.rows[i], 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}

type FlagMode = 'shares' | 'counts'

/** One source's years: the chart of the gated flags and the table of all flags. */
function FlagsOfSource({ dq, source, mode }: { dq: DataQuality; source: string; mode: FlagMode }) {
  const f = dq.flags_by_year
  const rows = f.source.flatMap((s, i) => (s === source ? [i] : []))
  const years = rows.map((i) => f.year[i])
  // The file's shares are fractions; the chart shows them as percentages, a change of unit for display only.
  const series = CHART_FLAGS.filter(({ flag }) => dq.flag_names.includes(flag)).map(({ flag, color }) => ({
    name: flag,
    color,
    values: rows.map((i) => f.shares[flag][i] * 100),
  }))
  return (
    <div className="card">
      <h3>{source}</h3>
      {rows.length >= 2 && (
        <>
          <LineChart series={series} yLabel="% of the year’s quotes" />
          <p className="sub">
            Years {years[0]} to {years[years.length - 1]}, left to right.
          </p>
        </>
      )}
      <div className="scroll-x">
        <table className="dq dense" aria-label={`Quality flags by year, ${source}`}>
          <thead>
            <tr>
              <th>Flag</th>
              {years.map((year, k) => (
                <th key={k} className="num">
                  {year}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">quotes</th>
              {rows.map((i, k) => (
                // Shortened in the share view so a table of 14 years fits the page; the exact number is the tooltip.
                <td key={k} className="num" title={fmt(f.rows[i], 0)}>
                  {mode === 'shares' ? compact(f.rows[i]) : fmt(f.rows[i], 0)}
                </td>
              ))}
            </tr>
            {dq.flag_names.map((name, j) => (
              <tr key={name}>
                <th scope="row" title={dq.flag_descriptions[j]}>
                  {name}
                  <span className="flag-note">{dq.flag_descriptions[j]}</span>
                </th>
                {rows.map((i, k) => (
                  <td key={k} className="num">
                    {mode === 'shares' ? pct(f.shares[name][i]) : fmt(f.counts[name][i], 0)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function FlagsSection({ dq }: { dq: DataQuality }) {
  const [mode, setMode] = useState<FlagMode>('shares')
  const sources = [...new Set(dq.flags_by_year.source)]
  return (
    <>
      <h2>Quality flags by year</h2>
      <p className="sub">{FLAGS_NOTE}</p>
      <div className="controls">
        <label htmlFor="dq-flag-mode">Tables show</label>
        <select id="dq-flag-mode" value={mode} onChange={(e) => setMode(e.target.value as FlagMode)}>
          <option value="shares">the share of the year’s quotes</option>
          <option value="counts">the number of quotes</option>
        </select>
      </div>
      {sources.map((source) => (
        <FlagsOfSource key={source} dq={dq} source={source} mode={mode} />
      ))}
    </>
  )
}

/** "≤ 1 vol pts" for the row of `within_thresholds` with this key, as the file gives it; empty if the file has no such row. */
function thresholdText(v: CrossVendor, key: string): string {
  const w = v.within_thresholds
  const i = w.key.indexOf(key)
  return i < 0 ? '' : `≤ ${amount(w.threshold[i], w.unit[i])}`
}

function CrossVendorSection({ dq }: { dq: DataQuality }) {
  const v = dq.cross_vendor
  const d = v.distributions
  const w = v.within_thresholds
  const y = v.by_year
  const iv = thresholdText(v, 'iv30')
  const spot = thresholdText(v, 'spot')
  return (
    <>
      <h2>Cross-vendor agreement</h2>
      <p className="sub">{CROSSVENDOR_NOTE}</p>
      <div className="card">
        <p>
          {v.label}; {fmt(v.overlap_dates, 0)} dates in both.
        </p>
        <p className="sub">{v.basis}</p>
        <h3>Dates inside each threshold</h3>
        <div className="scroll-x">
          <table className="dq" aria-label="Cross-vendor dates inside a threshold">
            <thead>
              <tr>
                <th>Gap</th>
                <th className="num">Threshold</th>
                <th className="num">Dates</th>
                <th className="num">Share within</th>
              </tr>
            </thead>
            <tbody>
              {w.key.map((key, i) => (
                <tr key={key}>
                  <td>{w.label[i]}</td>
                  <td className="num">{`≤ ${amount(w.threshold[i], w.unit[i])}`}</td>
                  <td className="num">{fmt(w.dates[i], 0)}</td>
                  <td className="num">{pct(w.share_within[i], 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="card">
        <h3>By calendar year</h3>
        <div className="scroll-x">
          <table className="dq" aria-label="Cross-vendor agreement by year">
            <thead>
              <tr>
                <th>Year</th>
                <th className="num">Dates</th>
                <th className="num">{`30-day IV gap ${iv}`.trim()}</th>
                <th className="num">{`DoltHub spot miss ${spot}`.trim()}</th>
                <th className="num">DoltHub spot, median miss of the close (bp)</th>
                <th className="num">OptionsDX spot, median miss of the close (bp)</th>
              </tr>
            </thead>
            <tbody>
              {y.year.map((year, i) => (
                <tr key={year}>
                  <td>{year}</td>
                  <td className="num">{fmt(y.dates[i], 0)}</td>
                  <td className="num">{pct(y.iv30_share_within[i], 1)}</td>
                  <td className="num">{pct(y.spot_dolthub_share_within[i], 1)}</td>
                  <td className="num">{fmt(y.spot_dolthub_vs_close_median_bp[i])}</td>
                  <td className="num">{fmt(y.spot_optionsdx_vs_close_median_bp[i])}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="sub">{BY_YEAR_NOTE}</p>
      </div>
      <div className="card">
        <h3>How far apart the vendors are</h3>
        <div className="scroll-x">
          <table className="dq" aria-label="Cross-vendor differences">
            <thead>
              <tr>
                <th>Difference</th>
                <th>Unit</th>
                <th className="num">Dates</th>
                <th className="num">P5</th>
                <th className="num">P25</th>
                <th className="num">Median</th>
                <th className="num">P75</th>
                <th className="num">P95</th>
                <th className="num">Mean |gap|</th>
              </tr>
            </thead>
            <tbody>
              {d.key.map((key, i) => (
                <tr key={key}>
                  <td>{d.label[i]}</td>
                  <td>{d.unit[i]}</td>
                  <td className="num">{fmt(d.n[i], 0)}</td>
                  <td className="num">{fmt(d.p05[i])}</td>
                  <td className="num">{fmt(d.p25[i])}</td>
                  <td className="num">{fmt(d.median[i])}</td>
                  <td className="num">{fmt(d.p75[i])}</td>
                  <td className="num">{fmt(d.p95[i])}</td>
                  <td className="num">{fmt(d.mean_abs[i])}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}

function Provenance({ dq }: { dq: DataQuality }) {
  const state = commitState(dq.source_commit)
  return (
    <>
      <h2>Where these numbers come from</h2>
      <div className="card">
        <p className="sub">{dq.label}</p>
        <dl className="meta">
          <dt>Schema version</dt>
          <dd>{dq.schema_version}</dd>
          <dt>Generated at</dt>
          <dd>{dq.generated_at}</dd>
          <dt>Source commit</dt>
          <dd>
            <code>{dq.source_commit}</code>
            {state !== 'clean' && (
              <span className="badge err-badge">{state === 'dirty' ? 'exported from a dirty working tree' : 'no commit yet'}</span>
            )}
          </dd>
        </dl>
      </div>
    </>
  )
}

function Notice() {
  return (
    <DataNotice>
      <p className="sub">{DATA_QUALITY_NOTICE}</p>
      <DoltHubAttribution changes={DOLTHUB_CHANGES} />
    </DataNotice>
  )
}

export function DataQualityPage({ state }: { state: AppDataState }) {
  return (
    <section className="data-quality">
      <h2>Data quality</h2>
      <p className="sub">{DATA_QUALITY_INTRO}</p>
      {state.status === 'loading' && (
        <div className="card">
          <p>Loading the exported data-quality file…</p>
        </div>
      )}
      {state.status === 'error' && (
        <div className="card">
          <DataProblem error={state.error} />
        </div>
      )}
      {state.status === 'ready' && (
        <>
          <GateSection dq={state.data.dataQuality} />
          <SourcesSection dq={state.data.dataQuality} />
          <CalendarSection dq={state.data.dataQuality} />
          <FlagsSection dq={state.data.dataQuality} />
          <CrossVendorSection dq={state.data.dataQuality} />
          <Provenance dq={state.data.dataQuality} />
        </>
      )}
      <Notice />
    </section>
  )
}
