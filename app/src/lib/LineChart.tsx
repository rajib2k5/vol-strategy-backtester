import type { CSSProperties } from 'react'
/** Dependency-free SVG line chart.
 * Lines draw in on mount and re-draw whenever the data signature changes;
 * prefers-reduced-motion renders the final state immediately. */
const LINE_STYLE = `
@keyframes vsbLineDraw { to { stroke-dashoffset: 0; } }
.vsb-line-draw { stroke-dasharray: 100 100; stroke-dashoffset: 100; animation: vsbLineDraw .9s ease forwards; animation-delay: var(--d, 0s); }
@media (prefers-reduced-motion: reduce) { .vsb-line-draw { animation: none; stroke-dashoffset: 0; } }
`
interface Series {
  name: string
  values: number[]
  color?: string
}

const pad0 = { l: 56, r: 12, t: 12, b: 24 }
const GLYPH_W = 6
const LEGEND_GAP = 24
const LEGEND_ROW = 14
const LABEL_BAND = 28

function layoutLegend(names: string[], left: number, right: number) {
  const out: { x: number; row: number }[] = []
  let x = left
  let row = 0
  for (const name of names) {
    const w = (name.length + 3) * GLYPH_W
    if (x > left && x + w > right) {
      x = left
      row++
    }
    out.push({ x, row })
    x += w + LEGEND_GAP
  }
  return out
}

export function LineChart({
  series,
  height = 220,
  yLabel,
}: {
  series: Series[]
  height?: number
  yLabel?: string
}) {
  const width = 720
  // Legend entries are laid out by text width (10px monospace, ~6px a glyph) and wrap onto
  // extra rows, so long series names never run into each other.
  const legend = series.length > 1 ? layoutLegend(series.map((s) => s.name), pad0.l + 8, width - pad0.r) : []
  const legendRows = legend.length ? legend[legend.length - 1].row + 1 : 1
  // The y-axis label sits above the plot, so the plot starts below it; otherwise the label
  // collides with the top tick value, which is drawn at the plot's top edge.
  const pad = { ...pad0, t: yLabel ? LABEL_BAND : pad0.t, b: pad0.b + (legendRows - 1) * LEGEND_ROW }
  const all = series.flatMap((s) => s.values).filter(Number.isFinite)
  if (all.length === 0) return <p>No data</p>
  const yMin = Math.min(...all)
  const yMax = Math.max(...all)
  const span = yMax - yMin || 1
  const n = Math.max(...series.map((s) => s.values.length))
  const x = (i: number) => pad.l + (i / Math.max(n - 1, 1)) * (width - pad.l - pad.r)
  const y = (v: number) => pad.t + (1 - (v - yMin) / span) * (height - pad.t - pad.b)
  const ticks = [yMin, yMin + span / 2, yMax]
  const palette = ['#e0a458', '#4fb8a8', '#c25450', '#7d9bd1', '#a58fd1']
  // signature keys the animated group so a data change replays the draw
  const sig = series.map((s) => `${s.name}:${s.values.length}:${s.values[0] ?? 0}:${s.values[s.values.length - 1] ?? 0}`).join('|')
  return (
    <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', height: 'auto' }} role="img">
      <style>{LINE_STYLE}</style>
      {ticks.map((t, i) => (
        <g key={i}>
          <line x1={pad.l} x2={width - pad.r} y1={y(t)} y2={y(t)} stroke="var(--line, #2c3547)" strokeWidth="1" />
          <text x={pad.l - 6} y={y(t) + 4} textAnchor="end" fontSize="10" fill="var(--muted, #929db0)" fontFamily="monospace">
            {t.toPrecision(4)}
          </text>
        </g>
      ))}
      {yLabel && (
        <text x={4} y={12} fontSize="10" fill="var(--muted, #929db0)" fontFamily="monospace">
          {yLabel}
        </text>
      )}
      <g key={sig}>
        {series.map((s, si) => (
          <polyline
            key={s.name}
            className="vsb-line-draw"
            pathLength={100}
            style={{ '--d': `${si * 0.18}s` } as CSSProperties}
            fill="none"
            stroke={s.color ?? palette[si % palette.length]}
            strokeWidth="1.6"
            points={s.values.map((v, i) => `${x(i)},${y(v)}`).join(' ')}
          />
        ))}
      </g>
      {series.length > 1 &&
        series.map((s, si) => (
          <text key={s.name} x={legend[si].x} y={height - 6 - (legendRows - 1 - legend[si].row) * LEGEND_ROW} fontSize="10" fontFamily="monospace" fill={s.color ?? palette[si % palette.length]}>
            ── {s.name}
          </text>
        ))}
    </svg>
  )
}
