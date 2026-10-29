/** Shared numeric formatting for consistent tabular display. */
export function fmt(n: number, dp = 2): string {
  if (!Number.isFinite(n)) return '—'
  return n.toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp })
}

export function pct(n: number, dp = 2): string {
  if (!Number.isFinite(n)) return '—'
  return `${(n * 100).toFixed(dp)}%`
}

/** A short form for a cramped cell: 1,088,170 gives "1.1M", 525,956 gives "526K", 66 gives "66". */
export function compact(n: number): string {
  if (!Number.isFinite(n)) return '—'
  return n.toLocaleString('en-US', { notation: 'compact', maximumFractionDigits: 1 })
}

export function bps(n: number, dp = 1): string {
  if (!Number.isFinite(n)) return '—'
  return `${(n * 10_000).toFixed(dp)} bps`
}
