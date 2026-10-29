import type { AppDataState } from '../data/useAppData'
import type { AppData } from '../data/loadAppData'
import { commitState } from '../lib/contract'
import {
  DATA_SOURCES,
  DATA_SOURCES_NOTE,
  DISCLAIMER_BODY,
  DISCLAIMER_HEADLINE,
  DOES,
  DOES_NOT,
  PITCH,
  STATUS,
} from '../content/about'
import { DataProblem } from './DataProblem'
import { SurfaceHero } from './SurfaceHero'

function ContractInfo({ data }: { data: AppData }) {
  const { manifest } = data
  const state = commitState(manifest.source_commit)
  return (
    <>
      <dl className="meta">
        <dt>Schema version</dt>
        <dd>{manifest.schema_version}</dd>
        <dt>Generated at</dt>
        <dd>{manifest.generated_at}</dd>
        <dt>Source commit</dt>
        <dd>
          <code>{manifest.source_commit}</code>
          {state !== 'clean' && (
            <span className="badge err-badge">{state === 'dirty' ? 'exported from a dirty working tree' : 'no commit yet'}</span>
          )}
        </dd>
      </dl>
      <div className="scroll-x">
        <table>
          <thead>
            <tr>
              <th>Dataset</th>
              <th>Schema</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            {manifest.datasets.map((d) => (
              <tr key={d.name}>
                <td className="num">{d.name}</td>
                <td className="num">{d.schema_version}</td>
                <td>{d.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

export function AboutPage({ state }: { state: AppDataState }) {
  return (
    <section className="about">
      <h2>About</h2>
      <p className="sub">{PITCH}</p>
      <div className="notice" role="note">
        <strong>{DISCLAIMER_HEADLINE}</strong> {DISCLAIMER_BODY}
      </div>
      <p className="sub">{STATUS}</p>

      <h2>Volatility surface</h2>
      <div className="card">
        {state.status === 'loading' && <p>Loading the exported surface…</p>}
        {state.status === 'error' && <DataProblem error={state.error} />}
        {state.status === 'ready' && <SurfaceHero surface={state.data.surface} />}
      </div>

      <div className="grid">
        <div className="card">
          <h3>What it does</h3>
          <ul>
            {DOES.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </div>
        <div className="card">
          <h3>What it does not do</h3>
          <ul>
            {DOES_NOT.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </div>
      </div>

      <h2>Data sources</h2>
      <div className="card">
        <ul>
          {DATA_SOURCES.map((s) => (
            <li key={s.name}>
              <strong>{s.name}</strong>: {s.role}
            </li>
          ))}
        </ul>
        <p className="sub">{DATA_SOURCES_NOTE}</p>
      </div>

      <h2>Exported data</h2>
      <div className="card">
        {state.status === 'ready' ? (
          <ContractInfo data={state.data} />
        ) : (
          <p className="sub">{state.status === 'loading' ? 'Loading manifest.json…' : 'No manifest loaded: see the message above.'}</p>
        )}
      </div>
    </section>
  )
}
