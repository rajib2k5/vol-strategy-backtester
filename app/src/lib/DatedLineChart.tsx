/**
 * Dependency-free SVG line chart on a calendar-date axis, for series that have gaps (a null leaves the line broken, it is
 * never joined across or read as 0), with horizontal reference lines and vertical date markers. It only places the file's
 * own numbers and dates on a scale (ADR-0001 §6).
 */
export interface DatedSeries {
  name: string
  /** One value per date; null where the file has none. */
  values: (number | null)[]
  color: string
}

export interface LevelLine {
  y: number
  /** What the level is; shown as the line's tooltip and read by a screen reader. */
  label: string
}

export interface DateMark {
  date: string
  label: string
}

const WIDTH = 720
const PAD = { l: 56, r: 40, t: 14, b: 38 }
const MS_PER_DAY = 86_400_000
const day = (date: string): number => Date.parse(`${date}T00:00:00Z`) / MS_PER_DAY
const GLYPH_W = 6

/** Runs of consecutive non-null values, as [index, value] pairs. */
function runs(values: (number | null)[]): [number, number][][] {
  const out: [number, number][][] = []
  let current: [number, number][] = []
  values.forEach((v, i) => {
    if (v === null) {
      if (current.length > 0) out.push(current)
      current = []
    } else current.push([i, v])
  })
  if (current.length > 0) out.push(current)
  return out
}

export function DatedLineChart({
  dates,
  series,
  levels = [],
  marks = [],
  height = 220,
  yLabel,
}: {
  dates: string[]
  series: DatedSeries[]
  levels?: LevelLine[]
  marks?: DateMark[]
  height?: number
  yLabel?: string
}) {
  const present = series.flatMap((s) => s.values).filter((v): v is number => v !== null)
  if (present.length === 0) return <p>No data</p>
  const everyY = [...present, ...levels.map((l) => l.y)]
  const yMin = Math.min(...everyY)
  const yMax = Math.max(...everyY)
  const span = yMax - yMin || 1
  const t0 = day(dates[0])
  const tSpan = Math.max(day(dates[dates.length - 1]) - t0, 1)
  const x = (date: string): number => PAD.l + ((day(date) - t0) / tSpan) * (WIDTH - PAD.l - PAD.r)
  const y = (v: number): number => PAD.t + (1 - (v - yMin) / span) * (height - PAD.t - PAD.b)
  const ticks = [yMin, yMin + span / 2, yMax]
  let legendX = PAD.l + 8
  const legend = series.map((s) => {
    const at = legendX
    legendX += (s.name.length + 3) * GLYPH_W + 24
    return at
  })
  return (
    <svg viewBox={`0 0 ${WIDTH} ${height}`} style={{ width: '100%', height: 'auto' }} role="img">
      {ticks.map((t, i) => (
        <g key={i}>
          <line x1={PAD.l} x2={WIDTH - PAD.r} y1={y(t)} y2={y(t)} stroke="var(--line, #2c3547)" strokeWidth="1" />
          <text x={PAD.l - 6} y={y(t) + 4} textAnchor="end" fontSize="10" fill="var(--muted, #929db0)" fontFamily="monospace">
            {t.toPrecision(4)}
          </text>
        </g>
      ))}
      {yLabel && (
        <text x={4} y={10} fontSize="10" fill="var(--muted, #929db0)" fontFamily="monospace">
          {yLabel}
        </text>
      )}
      {marks
        .filter((m) => m.date >= dates[0] && m.date <= dates[dates.length - 1])
        .map((m) => (
          <line key={m.date} data-mark={m.date} x1={x(m.date)} x2={x(m.date)} y1={PAD.t} y2={height - PAD.b} stroke="var(--muted, #929db0)" strokeWidth="1" strokeDasharray="2 3">
            <title>{m.label}</title>
          </line>
        ))}
      {levels.map((l) => (
        <g key={l.y}>
          <line data-level={l.y} x1={PAD.l} x2={WIDTH - PAD.r} y1={y(l.y)} y2={y(l.y)} stroke="var(--accent, #e0a458)" strokeWidth="1" strokeDasharray="5 3">
            <title>{l.label}</title>
          </line>
          <text x={WIDTH - PAD.r + 4} y={y(l.y) + 3} fontSize="9" fill="var(--accent, #e0a458)" fontFamily="monospace">
            {l.y}
          </text>
        </g>
      ))}
      {series.map((s) =>
        runs(s.values).map((run) =>
          run.length === 1 ? (
            <circle key={`${s.name}:${run[0][0]}`} data-series={s.name} cx={x(dates[run[0][0]])} cy={y(run[0][1])} r="1.6" fill={s.color} />
          ) : (
            <polyline
              key={`${s.name}:${run[0][0]}`}
              data-series={s.name}
              fill="none"
              stroke={s.color}
              strokeWidth="1.6"
              points={run.map(([i, v]) => `${x(dates[i])},${y(v)}`).join(' ')}
            />
          ),
        ),
      )}
      <text x={PAD.l} y={height - PAD.b + 14} fontSize="10" fill="var(--muted, #929db0)" fontFamily="monospace">
        {dates[0]}
      </text>
      <text x={WIDTH - PAD.r} y={height - PAD.b + 14} textAnchor="end" fontSize="10" fill="var(--muted, #929db0)" fontFamily="monospace">
        {dates[dates.length - 1]}
      </text>
      {series.length > 1 &&
        series.map((s, i) => (
          <text key={s.name} x={legend[i]} y={height - 6} fontSize="10" fontFamily="monospace" fill={s.color}>
            ── {s.name}
          </text>
        ))}
    </svg>
  )
}
