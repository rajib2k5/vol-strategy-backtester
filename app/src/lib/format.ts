/** Shared numeric formatting for consistent tabular display. */
export function fmt(n: number, dp = 2): string {
  if (!Number.isFinite(n)) return '—'
  return n.toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp })
}

export function pct(n: number, dp = 2): string {
  if (!Number.isFinite(n)) return '—'
  return `${(n * 100).toFixed(dp)}%`
}

export function bps(n: number, dp = 1): string {
  if (!Number.isFinite(n)) return '—'
  return `${(n * 10_000).toFixed(dp)} bps`
}
