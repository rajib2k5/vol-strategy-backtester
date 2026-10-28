/* eslint-disable react-refresh/only-export-components -- chart math helpers are exported beside components deliberately; this is a leaf library file, not a hot-reload boundary */
import type { CSSProperties } from 'react'
/**
 * Analytics chart primitives (dependency-free SVG, theme-aware): Histogram and Heatmap.
 * Pure binning/scaling helpers are exported for oracle-backed testing.
 * Bars grow in with a stagger and heat cells fade in; both replay when data changes
 * and collapse to final states under prefers-reduced-motion.
 */
const CHART_STYLE = `
@keyframes vsbBarGrow { from { transform: scaleY(0); } }
.vsb-bar-grow { transform-origin: bottom; transform-box: fill-box; animation: vsbBarGrow .5s ease both; animation-delay: var(--d, 0s); }
@keyframes vsbCellIn { from { opacity: 0; } }
.vsb-cell-in { animation: vsbCellIn .4s ease both; animation-delay: var(--d, 0s); }
@media (prefers-reduced-motion: reduce) { .vsb-bar-grow, .vsb-cell-in { animation: none; } }
`

export function binValues(values: number[], bins: number): { counts: number[]; min: number; max: number } {
  const clean = values.filter(Number.isFinite)
  if (clean.length === 0 || bins < 1) return { counts: [], min: NaN, max: NaN }
  const min = Math.min(...clean)
  const max = Math.max(...clean)
  const counts = new Array<number>(bins).fill(0)
  const span = max - min
  for (const v of clean) {
    // top edge inclusive so max lands in the last bin
    const i = span === 0 ? 0 : Math.min(Math.floor(((v - min) / span) * bins), bins - 1)
    counts[i]++
  }
  return { counts, min, max }
}

export function Histogram({ values, bins = 20, color, yLabel }: { values: number[]; bins?: number; color?: string; yLabel?: string }) {
  const { counts, min, max } = binValues(values, bins)
  if (counts.length === 0) return <p className="sub">No data to bin.</p>
  const W = 720
  const H = 200
  const pad = { l: 40, r: 10, t: 10, b: 26 }
  const peak = Math.max(...counts, 1)
  const bw = (W - pad.l - pad.r) / counts.length
  const sig = `${counts.length}:${min}:${max}:${peak}`
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Histogram" style={{ width: '100%', height: 'auto' }}>
      <style>{CHART_STYLE}</style>
      <g key={sig}>
      {counts.map((c, i) => {
        const h = (c / peak) * (H - pad.t - pad.b)
        return (
          <rect
            key={i}
            className="vsb-bar-grow"
            data-testid="vsb-hist-bar"
            style={{ '--d': `${i * 0.02}s` } as CSSProperties}
            x={pad.l + i * bw + 1}
            y={H - pad.b - h}
            width={Math.max(bw - 2, 1)}
            height={h}
            fill={color ?? 'var(--accent, #888)'}
            opacity={0.85}
          />
        )
      })}
      </g>
      <line x1={pad.l} y1={H - pad.b} x2={W - pad.r} y2={H - pad.b} stroke="var(--line, #555)" />
      <text x={pad.l} y={H - 8} fontSize="10" fill="var(--muted, #888)" fontFamily="var(--mono, monospace)">
        {min.toPrecision(4)}
      </text>
      <text x={W - pad.r} y={H - 8} fontSize="10" textAnchor="end" fill="var(--muted, #888)" fontFamily="var(--mono, monospace)">
        {max.toPrecision(4)}
      </text>
      <text x={6} y={pad.t + 8} fontSize="10" fill="var(--muted, #888)" fontFamily="var(--mono, monospace)">
        {yLabel ?? `peak ${peak}`}
      </text>
    </svg>
  )
}

/** Normalize a matrix to [0,1] cell intensities; NaN cells map to null. */
export function normalizeMatrix(rows: number[][]): (number | null)[][] {
  const flat = rows.flat().filter(Number.isFinite)
  if (flat.length === 0) return rows.map((r) => r.map(() => null))
  const min = Math.min(...flat)
  const max = Math.max(...flat)
  const span = max - min || 1
  return rows.map((r) => r.map((v) => (Number.isFinite(v) ? (v - min) / span : null)))
}

export function Heatmap({
  rows,
  xLabels,
  yLabels,
  color,
}: {
  rows: number[][]
  xLabels?: string[]
  yLabels?: string[]
  color?: string
}) {
  const norm = normalizeMatrix(rows)
  const nRows = rows.length
  const nCols = rows[0]?.length ?? 0
  if (nRows === 0 || nCols === 0) return <p className="sub">No data.</p>
  const W = 720
  const pad = { l: 86, t: 8, r: 10, b: 24 }
  const cw = (W - pad.l - pad.r) / nCols
  const ch = 30
  const H = pad.t + nRows * ch + pad.b
  const sig = `${nRows}x${nCols}:${rows[0]?.[0] ?? 0}:${rows[nRows - 1]?.[nCols - 1] ?? 0}`
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Heatmap" style={{ width: '100%', height: 'auto' }}>
      <style>{CHART_STYLE}</style>
      <g key={sig}>
      {norm.map((r, i) =>
        r.map((v, j) => (
          <rect
            key={`${i}-${j}`}
            className="vsb-cell-in"
            data-testid="vsb-heat-cell"
            style={{ '--d': `${(i + j) * 0.015}s` } as CSSProperties}
            x={pad.l + j * cw}
            y={pad.t + i * ch}
            width={cw - 1}
            height={ch - 1}
            fill={v === null ? 'var(--surface2, #333)' : (color ?? 'var(--accent, #888)')}
            opacity={v === null ? 0.4 : 0.15 + 0.85 * v}
          />
        )),
      )}
      </g>
      {yLabels?.slice(0, nRows).map((l, i) => (
        <text key={l} x={pad.l - 6} y={pad.t + i * ch + ch / 2 + 3} fontSize="10" textAnchor="end" fill="var(--muted, #888)" fontFamily="var(--mono, monospace)">
          {l}
        </text>
      ))}
      {xLabels?.slice(0, nCols).map((l, j) => (
        <text key={l} x={pad.l + j * cw + cw / 2} y={H - 8} fontSize="10" textAnchor="middle" fill="var(--muted, #888)" fontFamily="var(--mono, monospace)">
          {l}
        </text>
      ))}
    </svg>
  )
}
