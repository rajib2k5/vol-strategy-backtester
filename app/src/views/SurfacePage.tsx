/**
 * The Surface page: the real SPY implied-vol surfaces of surface_frames.json, one date at a time, in
 * the same 3D view as the About page's illustrative hero.
 *
 * Every number shown is the file's own, formatted (ADR-0001 §6): the page picks a frame and draws it,
 * and computes nothing a reader would quote. The grid and the IVs go to SurfaceHero unchanged.
 */
import { useMemo, useState } from 'react'
import type { AppDataState } from '../data/useAppData'
import { dataSourceName, type DataSource, type SurfaceFrame, type SurfaceFrames } from '../lib/contract'
import { fmt, pct } from '../lib/format'
import {
  EXTRAPOLATION_NOTE,
  FRAME_STATS,
  PROVENANCE_NOTE,
  SURFACE_CLOSES_NOTICE,
  SURFACE_DOLTHUB_CHANGES,
  SURFACE_PAGE_INTRO,
  SURFACE_VENDOR_NOTICE,
  realSurfaceBadge,
} from '../content/surface'
import { DataNotice, DoltHubAttribution } from './DataNotice'
import { DataProblem } from './DataProblem'
import { SurfaceHero, type SurfaceGrid } from './SurfaceHero'

/** A tile's value, formatted for its field: IVs and shares as percentages, prices to the cent, counts whole. */
function statValue(frame: SurfaceFrame, field: (typeof FRAME_STATS)[number]['field']): string {
  switch (field) {
    case 'spot':
      return `$${fmt(frame.spot, 2)}`
    case 'vix_close':
      return fmt(frame.vix_close, 2)
    case 'atm_iv_30d':
      return pct(frame.atm_iv_30d, 1)
    case 'quoted_share':
      return pct(frame.quoted_share, 1)
    case 'expiries_used':
      return fmt(frame.expiries_used, 0)
  }
}

function FramePicker({ frames, chosen, choose }: { frames: SurfaceFrame[]; chosen: number; choose: (i: number) => void }) {
  return (
    <div className="frame-picker" role="group" aria-label="Surface date">
      {frames.map((frame, i) => (
        <button key={frame.date} type="button" aria-pressed={i === chosen} className={i === chosen ? 'primary' : ''} onClick={() => choose(i)}>
          {frame.date}
        </button>
      ))}
    </div>
  )
}

function Frame({ file, frame }: { file: SurfaceFrames; frame: SurfaceFrame }) {
  // The hero draws any IV grid; this frame's is the file's grid with this date's IVs.
  const grid: SurfaceGrid = useMemo(() => ({ moneyness: file.grid_moneyness, dte: file.grid_dte, iv: frame.iv }), [file, frame])
  return (
    <>
      <div className="card">
        {/* key: a new date mounts a fresh scene rather than patching the old one's buffers */}
        <SurfaceHero key={frame.date} surface={grid} label={realSurfaceBadge(frame.date, dataSourceName(file.run.data_source as string))} />
      </div>
      <p className="frame-label">
        <strong>{frame.date}</strong>: {frame.label}
      </p>
      <div className="grid">
        {FRAME_STATS.map(({ field, title }) => (
          <div className="stat" key={field}>
            <div className="k">{title}</div>
            <div className="v">{statValue(frame, field)}</div>
            <div className="k unit">{file.units[field]}</div>
          </div>
        ))}
      </div>
      <p className="sub">{EXTRAPOLATION_NOTE}</p>
    </>
  )
}

function Provenance({ file }: { file: SurfaceFrames }) {
  const { run } = file
  return (
    <>
      <h3>Where these numbers come from</h3>
      <p className="sub">{file.label}</p>
      <p className="sub">{PROVENANCE_NOTE}</p>
      <dl className="meta">
        <dt>Run</dt>
        <dd>
          <code>{run.run_id}</code>
        </dd>
        <dt>Data source</dt>
        <dd>{run.data_source}</dd>
        <dt>Chain mask</dt>
        <dd>{run.chain_mask}</dd>
        <dt>Dates</dt>
        <dd>
          {run.sample_start} to {run.sample_end}
        </dd>
        <dt>Pricing code</dt>
        <dd>
          <code>{run.config_hash}</code>
        </dd>
        <dt>Inputs</dt>
        <dd>
          <code>{run.data_fingerprint}</code>
        </dd>
        <dt>Schema version</dt>
        <dd>{file.schema_version}</dd>
      </dl>
    </>
  )
}

function Surfaces({ file }: { file: SurfaceFrames }) {
  const [chosen, setChosen] = useState(0)
  const frame = file.frames[chosen]
  return (
    <>
      <FramePicker frames={file.frames} chosen={chosen} choose={setChosen} />
      <Frame file={file} frame={frame} />
      <div className="card">
        <Provenance file={file} />
      </div>
    </>
  )
}

/**
 * The data notice follows the file's run.data_source: its vendor's paragraph, the CC BY-SA attribution for DoltHub,
 * and where the closes come from. Without a file (loading, or a load error) no number is on the page and no vendor is named.
 */
function SurfaceNotice({ source }: { source: DataSource | null }) {
  return (
    <DataNotice>
      {source !== null && (
        <>
          <p className="sub">{SURFACE_VENDOR_NOTICE[source]}</p>
          {source === 'dolthub' && <DoltHubAttribution changes={SURFACE_DOLTHUB_CHANGES} />}
          <p className="sub">{SURFACE_CLOSES_NOTICE}</p>
        </>
      )}
    </DataNotice>
  )
}

export function SurfacePage({ state }: { state: AppDataState }) {
  return (
    <section className="surface-page">
      <h2>Surface</h2>
      <p className="sub">{SURFACE_PAGE_INTRO}</p>
      {state.status === 'loading' && <p>Loading the exported surfaces…</p>}
      {state.status === 'error' && <DataProblem error={state.error} />}
      {state.status === 'ready' && <Surfaces file={state.data.surfaceFrames} />}
      {/* parseSurfaceFrames accepted run.data_source as a known vendor, so the cast names one */}
      <SurfaceNotice source={state.status === 'ready' ? (state.data.surfaceFrames.run.data_source as DataSource) : null} />
    </section>
  )
}
