/**
 * The JSON contract between the Python exporter (tools/export_app_data.py) and this app.
 *
 * The app never computes results: it fetches `manifest.json` plus the datasets the manifest
 * lists, and renders them. Everything fetched is untrusted until it has passed through a
 * parser below. Each parser takes `unknown` (what `response.json()` gives you) and either
 * returns a typed value or throws a ContractError naming the exact field that is wrong.
 *
 * Pure: no I/O, no DOM, no clock. The fetching lives in src/data/loadAppData.ts.
 *
 * Versioning rule: `schema_version` is "MAJOR.MINOR.PATCH". This app accepts any file whose MAJOR
 * equals SUPPORTED_MAJOR. Unknown extra keys are ignored, so a MINOR/PATCH bump that only adds
 * fields does not break old viewers.
 */

export const SUPPORTED_MAJOR = 0

export class ContractError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ContractError'
  }
}

export interface DatasetEntry {
  name: string
  path: string
  schema_version: string
  description: string
}

export interface Manifest {
  schema_version: string
  generated_at: string
  /** `<sha>`, `<sha>-dirty` (uncommitted changes in the tree) or `uncommitted` (no commit yet). */
  source_commit: string
  datasets: DatasetEntry[]
}

export interface IllustrativeSurface {
  schema_version: string
  generated_at: string
  source_commit: string
  illustrative: true
  label: string
  /** Log-moneyness grid, strictly increasing. */
  moneyness: number[]
  /** Days to expiry grid, strictly increasing, positive. */
  dte: number[]
  /** Implied vol as a decimal (0.18 = 18%), indexed iv[i_dte][j_moneyness]. */
  iv: number[][]
  params: Record<string, unknown>
}

/** The only dataset the milestone-0 app consumes. */
export const SURFACE_DATASET = 'illustrative_surface'

/** Sanity ceiling on IV: 5.0 = 500%. Catches an exporter that wrote percent (18) instead of decimal (0.18). */
export const MAX_IV = 5

/** The dataset the Data quality page reads. */
export const DATA_QUALITY_DATASET = 'data_quality'

/*
 * data_quality.json holds aggregates of the built option-chain store: counts, shares and quantiles,
 * never a quote. Every table is column-wise (one array per column, all the same length), and every
 * number the page shows, shares included, is in the file: the app divides nothing.
 */

/**
 * The 13 quality flags in bit order (ADR-0009 §3; src/volbt/data/flags.py FLAG_NAMES). A file whose
 * flag_names differ is refused: this app reads these 13 and nothing else.
 */
export const FLAG_NAMES = [
  'BID_NULL',
  'ASK_NULL',
  'ZERO_BID',
  'CROSSED',
  'LOCKED',
  'WIDE',
  'STALE',
  'NON_SESSION_DATE',
  'RELABELLED',
  'VOLUME_UNRELIABLE',
  'UNDERLYING_MISMATCH',
  'VENDOR_IV_INVALID',
  'EXPIRY_DAY',
] as const

/**
 * How far a share may sit from counts / rows. Python writes a share rounded to 6 decimals (an error
 * of at most 5e-7); one unit in the last place is allowed.
 */
export const SHARE_ROUNDING = 1e-6

/**
 * The calendar's actions (src/volbt/data/calendar.py build_date_map): a vendor date is a session,
 * kept as dated, or it is dropped. Nothing is moved to another date, so a file with another action
 * ("relabel" from before the M1 review, or one nobody defined) is refused.
 */
export const CALENDAR_ACTION_NAMES = ['session', 'drop'] as const

/**
 * The flags the gate limits the share of, per source, as tools/export_app_data.py writes them
 * (src/volbt/data/quality.py GATE_MAX_SHARE). A `max_share` row names its flag in `what`.
 */
export const GATE_SHARE_FLAGS: Record<string, readonly string[]> = {
  optionsdx: ['BID_NULL', 'ASK_NULL', 'CROSSED', 'VENDOR_IV_INVALID', 'UNDERLYING_MISMATCH'],
  dolthub: ['BID_NULL', 'ASK_NULL', 'CROSSED', 'VENDOR_IV_INVALID'],
}

/**
 * The rule set of the quality gate, as tools/export_app_data.py thresholds_table writes it: each
 * rule with the side it bounds and how many rows each source has. A file whose gate has another
 * rule, a bound turned round, or a row missing or added is refused: the page would show a gate
 * that is not the one the build ran. The limits themselves are not pinned; they are the build's to change.
 */
export const GATE_RULES: Record<string, { bound: GateBound; rows: Record<string, number> }> = {
  max_share: { bound: 'max', rows: { optionsdx: 5, dolthub: 4 } },
  // One row per sampling regime of the source (quality.py GATE_DATES_PER_YEAR).
  min_dates_per_year: { bound: 'min', rows: { optionsdx: 1, dolthub: 4 } },
  min_dates: { bound: 'min', rows: { optionsdx: 1, dolthub: 1 } },
  min_rows_per_date: { bound: 'min', rows: { optionsdx: 1, dolthub: 1 } },
  max_dropped_dates: { bound: 'max', rows: { optionsdx: 1, dolthub: 1 } },
  max_underlying_p99_cents: { bound: 'max', rows: { optionsdx: 1 } },
}

/** The cross-vendor `within_thresholds` rows that a by-year column also reports, by key. */
const POOLED_BY_YEAR_COLUMN = { iv30: 'iv30_share_within', spot: 'spot_dolthub_share_within' } as const

/** The keys an earlier cross_vendor carried for a verdict. The check reports measurements, so a file that carries one contradicts itself. */
const CROSS_VENDOR_VERDICT_KEYS = ['passed', 'failures'] as const

/** One row per (source, year). Row i of `counts[flag]` is the quotes of that row carrying the flag. */
export interface FlagsByYear {
  source: string[]
  year: number[]
  /** Quotes in the source-year. */
  rows: number[]
  counts: Record<string, number[]>
  /** counts / rows, 0 to 1, computed by Python. */
  shares: Record<string, number[]>
}

export interface SourceRows {
  source: string[]
  /** Quotes in the store. */
  rows: number[]
  /** Distinct snapshot dates. */
  dates: number[]
}

/** One row per (source, action); the action is session (kept as dated) or drop. */
export interface CalendarCounts {
  source: string[]
  action: string[]
  dates: number[]
  rows: number[]
}

/** One row per cross-vendor difference; `unit` says what the quantiles are in ("vol pts", "bp"). */
export interface Distributions {
  key: string[]
  label: string[]
  unit: string[]
  n: number[]
  mean: number[]
  mean_abs: number[]
  p05: number[]
  p25: number[]
  median: number[]
  p75: number[]
  p95: number[]
}

/**
 * The share of overlap dates inside each threshold. A measurement: the thresholds were chosen after
 * looking at these same dates, so nothing here passes or fails. `dates` counts the dates with a value.
 */
export interface WithinThresholds {
  /** "iv30" or "spot": the app looks a row up by this key. */
  key: string[]
  label: string[]
  threshold: number[]
  /** "vol pts" or "bp". */
  unit: string[]
  dates: number[]
  /** 0 to 1, computed by Python: the share of `dates` with |gap| at or below `threshold`. */
  share_within: number[]
}

/** One row per calendar year of the overlap. The shares use the thresholds of `within_thresholds`. */
export interface ByYear {
  year: number[]
  dates: number[]
  iv30_share_within: number[]
  spot_dolthub_share_within: number[]
  /** Median of the parity spot against the SPY close, in bp (signed). */
  spot_dolthub_vs_close_median_bp: number[]
  spot_optionsdx_vs_close_median_bp: number[]
}

export interface CrossVendor {
  label: string
  overlap_dates: number
  /** Why the thresholds are measurements and not a test. Said once, here, by the exporter. */
  basis: string
  distributions: Distributions
  within_thresholds: WithinThresholds
  by_year: ByYear
}

/** "max": `worst` must stay at or below `limit`; "min": at or above it. */
export type GateBound = 'max' | 'min'

/** One row per quality-gate limit. `unit` is "fraction" (a share, 0 to 1) or a plain unit such as "quotes". */
export interface Thresholds {
  rule: string[]
  source: string[]
  what: string[]
  bound: GateBound[]
  limit: number[]
  worst: number[]
  unit: string[]
}

export interface Gate {
  passed: boolean
  failures: string[]
  thresholds: Thresholds
}

export interface DataQuality {
  schema_version: string
  generated_at: string
  source_commit: string
  label: string
  /** The 13 flags in bit order; `flag_descriptions[i]` explains `flag_names[i]`. */
  flag_names: string[]
  flag_descriptions: string[]
  flags_by_year: FlagsByYear
  sources: SourceRows
  calendar: CalendarCounts
  cross_vendor: CrossVendor
  gate: Gate
}

// ---------------------------------------------------------------- helpers

function fail(path: string, problem: string): never {
  throw new ContractError(`${path}: ${problem}`)
}

function asRecord(v: unknown, path: string): Record<string, unknown> {
  if (typeof v !== 'object' || v === null || Array.isArray(v)) fail(path, 'expected an object')
  return v as Record<string, unknown>
}

function need(obj: Record<string, unknown>, key: string, path: string): unknown {
  if (!(key in obj)) fail(path, `missing required key "${key}"`)
  return obj[key]
}

function needString(obj: Record<string, unknown>, key: string, path: string): string {
  const v = need(obj, key, path)
  if (typeof v !== 'string' || v.trim() === '') fail(`${path}.${key}`, 'expected a non-empty string')
  return v
}

// Each part is 0 or a number without leading zeros, as SemVer requires: "01.0.0" or "0.1.00" would
// otherwise be read as a different string for the same version.
const SEMVER = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/

function needSchemaVersion(obj: Record<string, unknown>, path: string): string {
  const v = needString(obj, 'schema_version', path)
  const m = SEMVER.exec(v)
  if (!m) fail(`${path}.schema_version`, `"${v}" is not MAJOR.MINOR.PATCH`)
  const major = Number(m[1])
  if (major !== SUPPORTED_MAJOR) {
    fail(`${path}.schema_version`, `unsupported major version ${major} ("${v}"); this app reads ${SUPPORTED_MAJOR}.x`)
  }
  return v
}

// 2026-10-27T23:30:00Z, with optional fractional seconds and either Z or a +hh:mm offset.
// Captures: 1 = the wall-clock part (no fraction, no offset), 4 and 5 = offset hours and minutes.
const ISO_TIMESTAMP = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?(Z|[+-](\d{2}):(\d{2}))$/

/**
 * True if the date and time exist. Date.parse alone is not enough: V8 rolls an impossible date
 * forward ("2026-02-30" becomes 2 March) and reads hour 24 as midnight of the next day. So we also
 * build the wall-clock time as a UTC Date and require that printing it gives back the same
 * characters; a rolled-over date prints differently.
 */
function isRealTimestamp(v: string): boolean {
  const m = ISO_TIMESTAMP.exec(v)
  if (!m || Number.isNaN(Date.parse(v))) return false
  const wallClock = m[1]
  const roundTrip = new Date(`${wallClock}Z`)
  if (Number.isNaN(roundTrip.getTime()) || roundTrip.toISOString().slice(0, 19) !== wallClock) return false
  // Offsets are checked here rather than left to Date.parse, which is engine-specific.
  return m[4] === undefined || (Number(m[4]) <= 23 && Number(m[5]) <= 59)
}

function needTimestamp(obj: Record<string, unknown>, path: string): string {
  const v = needString(obj, 'generated_at', path)
  if (!isRealTimestamp(v)) {
    fail(`${path}.generated_at`, `"${v}" is not an ISO-8601 timestamp such as 2026-10-27T23:30:00Z`)
  }
  return v
}

// 7 to 64 hex digits: a short SHA-1 prefix up to a full SHA-256 hash (git can create SHA-256
// repositories, whose commit ids are 64 digits; SHA-1 ones are 40).
const SOURCE_COMMIT = /^(?:[0-9a-f]{7,64}(?:-dirty)?|uncommitted)$/

function needSourceCommit(obj: Record<string, unknown>, path: string): string {
  const v = needString(obj, 'source_commit', path)
  if (!SOURCE_COMMIT.test(v)) {
    fail(`${path}.source_commit`, `"${v}" is not <sha>, <sha>-dirty or uncommitted`)
  }
  return v
}

/** Plain relative path made of safe segments: no leading "/", no "..", no scheme, no backslash, no query. */
const SAFE_RELATIVE_PATH = /^[A-Za-z0-9_][A-Za-z0-9_.-]*(?:\/[A-Za-z0-9_][A-Za-z0-9_.-]*)*$/

function needFiniteArray(obj: Record<string, unknown>, key: string, path: string): number[] {
  const v = need(obj, key, path)
  const at = `${path}.${key}`
  if (!Array.isArray(v)) fail(at, 'expected an array of numbers')
  if (v.length < 2) fail(at, `needs at least 2 values to form a surface, got ${v.length}`)
  v.forEach((x, i) => {
    if (typeof x !== 'number' || !Number.isFinite(x)) fail(`${at}[${i}]`, `expected a finite number, got ${String(x)}`)
  })
  return v as number[]
}

function assertStrictlyIncreasing(xs: number[], at: string): void {
  for (let i = 1; i < xs.length; i++) {
    if (!(xs[i] > xs[i - 1])) fail(`${at}[${i}]`, `grid must be strictly increasing, but ${xs[i]} follows ${xs[i - 1]}`)
  }
}

// ---------------------------------------------------------------- parsers

export function parseManifest(raw: unknown): Manifest {
  const P = 'manifest'
  const o = asRecord(raw, P)
  const schema_version = needSchemaVersion(o, P)
  const generated_at = needTimestamp(o, P)
  const source_commit = needSourceCommit(o, P)
  const list = need(o, 'datasets', P)
  if (!Array.isArray(list)) fail(`${P}.datasets`, 'expected an array')
  const seen = new Set<string>()
  const datasets = list.map((item, i): DatasetEntry => {
    const at = `${P}.datasets[${i}]`
    const d = asRecord(item, at)
    const name = needString(d, 'name', at)
    if (seen.has(name)) fail(`${at}.name`, `duplicate dataset name "${name}"`)
    seen.add(name)
    const path = needString(d, 'path', at)
    if (!SAFE_RELATIVE_PATH.test(path)) fail(`${at}.path`, `"${path}" must be a plain relative path inside the data folder`)
    return { name, path, schema_version: needSchemaVersion(d, at), description: needString(d, 'description', at) }
  })
  return { schema_version, generated_at, source_commit, datasets }
}

export function parseIllustrativeSurface(raw: unknown): IllustrativeSurface {
  const P = SURFACE_DATASET
  const o = asRecord(raw, P)
  const schema_version = needSchemaVersion(o, P)
  const generated_at = needTimestamp(o, P)
  const source_commit = needSourceCommit(o, P)
  if (need(o, 'illustrative', P) !== true) {
    fail(`${P}.illustrative`, 'must be true: this app labels the surface "not market data", so a dataset that is not flagged illustrative is refused')
  }
  const label = needString(o, 'label', P)
  const moneyness = needFiniteArray(o, 'moneyness', P)
  assertStrictlyIncreasing(moneyness, `${P}.moneyness`)
  const dte = needFiniteArray(o, 'dte', P)
  assertStrictlyIncreasing(dte, `${P}.dte`)
  if (dte[0] <= 0) fail(`${P}.dte[0]`, `days to expiry must be positive, got ${dte[0]}`)

  const rows = need(o, 'iv', P)
  if (!Array.isArray(rows)) fail(`${P}.iv`, 'expected an array of rows (one per dte)')
  if (rows.length !== dte.length) fail(`${P}.iv`, `has ${rows.length} rows but dte has ${dte.length} values`)
  const iv = rows.map((row, i): number[] => {
    const at = `${P}.iv[${i}]`
    if (!Array.isArray(row)) fail(at, 'expected an array of numbers')
    if (row.length !== moneyness.length) fail(at, `has ${row.length} values but moneyness has ${moneyness.length} (ragged grid)`)
    row.forEach((x, j) => {
      if (typeof x !== 'number' || !Number.isFinite(x)) fail(`${at}[${j}]`, `expected a finite number, got ${String(x)}`)
      if (x <= 0 || x > MAX_IV) fail(`${at}[${j}]`, `implied vol ${x} is outside (0, ${MAX_IV}]; it must be a decimal (0.18 = 18%)`)
    })
    return row as number[]
  })

  const params = asRecord(need(o, 'params', P), `${P}.params`)
  return { schema_version, generated_at, source_commit, illustrative: true, label, moneyness, dte, iv, params }
}

// ---------------------------------------------------------------- data quality

type ColumnKind = 'text' | 'count' | 'year' | 'share' | 'number' | 'flag'
type CellOf<K extends ColumnKind> = K extends 'text' ? string : K extends 'flag' ? boolean : number
type TableOf<S extends Record<string, ColumnKind>> = { [C in keyof S]: CellOf<S[C]>[] }

/** The calendar years a quote can belong to. Wide on purpose: it only catches a column that is not years at all. */
const MIN_YEAR = 1900
const MAX_YEAR = 2200

function checkCell(x: unknown, kind: ColumnKind, at: string): void {
  if (kind === 'text') {
    if (typeof x !== 'string' || x.trim() === '') fail(at, 'expected a non-empty string')
    return
  }
  if (kind === 'flag') {
    if (typeof x !== 'boolean') fail(at, `expected true or false, got ${String(x)}`)
    return
  }
  if (typeof x !== 'number' || !Number.isFinite(x)) fail(at, `expected a finite number, got ${String(x)}`)
  if (kind === 'count' && (!Number.isInteger(x) || x < 0)) fail(at, `expected a whole number of at least 0, got ${x}`)
  if (kind === 'year' && (!Number.isInteger(x) || x < MIN_YEAR || x > MAX_YEAR)) fail(at, `expected a calendar year, got ${x}`)
  if (kind === 'share' && (x < 0 || x > 1)) fail(at, `expected a share between 0 and 1, got ${x}`)
}

function needArray(obj: Record<string, unknown>, key: string, path: string): unknown[] {
  const v = need(obj, key, path)
  if (!Array.isArray(v)) fail(`${path}.${key}`, 'expected an array')
  return v
}

/**
 * Reads `obj[key]` as a column-wise table: an object with one array per column in `spec`, every
 * array the same length (at least one row), every cell of the column's kind. Columns the spec does
 * not name are dropped.
 */
function needTable<S extends Record<string, ColumnKind>>(
  obj: Record<string, unknown>,
  key: string,
  path: string,
  spec: S,
): TableOf<S> {
  const at = `${path}.${key}`
  const table = asRecord(need(obj, key, path), at)
  const out: Record<string, unknown[]> = {}
  let first: string | undefined
  for (const [column, kind] of Object.entries(spec)) {
    const values = needArray(table, column, at)
    if (first === undefined) {
      first = column
      if (values.length === 0) fail(`${at}.${column}`, 'needs at least 1 row')
    } else if (values.length !== out[first].length) {
      fail(`${at}.${column}`, `has ${values.length} values but "${first}" has ${out[first].length}`)
    }
    values.forEach((x, i) => checkCell(x, kind, `${at}.${column}[${i}]`))
    out[column] = values
  }
  return out as TableOf<S>
}

/** Fails on the first key that an earlier row already had: a table keyed by (source, year) or (source, action) must not repeat a key. */
function assertNoRepeat(keys: string[], at: string, noun: string): void {
  keys.forEach((key, i) => {
    if (keys.indexOf(key) !== i) fail(`${at}[${i}]`, `duplicate ${noun} ${key} (first at row ${keys.indexOf(key)})`)
  })
}

/** A (possibly empty) array of non-empty strings. */
function needStrings(obj: Record<string, unknown>, key: string, path: string): string[] {
  const values = needArray(obj, key, path)
  values.forEach((x, i) => checkCell(x, 'text', `${path}.${key}[${i}]`))
  return values as string[]
}

function needBoolean(obj: Record<string, unknown>, key: string, path: string): boolean {
  const v = need(obj, key, path)
  checkCell(v, 'flag', `${path}.${key}`)
  return v as boolean
}

function needWholeCount(obj: Record<string, unknown>, key: string, path: string): number {
  const v = need(obj, key, path)
  checkCell(v, 'count', `${path}.${key}`)
  return v as number
}

/** `passed` plus the reasons for a failure. The two must agree: a verdict of "passed" that lists failures is contradictory. */
function needVerdict(obj: Record<string, unknown>, path: string): { passed: boolean; failures: string[] } {
  const passed = needBoolean(obj, 'passed', path)
  const failures = needStrings(obj, 'failures', path)
  if (passed && failures.length > 0) fail(`${path}.passed`, `is true but ${failures.length} failure(s) are listed`)
  if (!passed && failures.length === 0) fail(`${path}.passed`, 'is false but no failure is listed')
  return { passed, failures }
}

/** The flag names: the 13 of FLAG_NAMES, in bit order. A repeated name is reported as such before the order is checked. */
function needFlagNames(obj: Record<string, unknown>, path: string): string[] {
  const names = needStrings(obj, 'flag_names', path)
  names.forEach((name, i) => {
    if (names.indexOf(name) !== i) fail(`${path}.flag_names[${i}]`, `duplicate flag name "${name}"`)
  })
  if (names.length !== FLAG_NAMES.length) {
    fail(`${path}.flag_names`, `has ${names.length} names but this app reads the ${FLAG_NAMES.length} flags of ADR-0009 §3`)
  }
  names.forEach((name, i) => {
    if (name !== FLAG_NAMES[i]) fail(`${path}.flag_names[${i}]`, `expected "${FLAG_NAMES[i]}" (flag ${i} in bit order), got "${name}"`)
  })
  return names
}

/** `counts` or `shares`: one array per flag in `flagNames`, one value per table row. */
function needFlagColumns(
  table: Record<string, unknown>,
  key: 'counts' | 'shares',
  path: string,
  flagNames: string[],
  rowCount: number,
): Record<string, number[]> {
  const at = `${path}.${key}`
  const block = asRecord(need(table, key, path), at)
  const out: Record<string, number[]> = {}
  for (const name of flagNames) {
    const values = needArray(block, name, at)
    if (values.length !== rowCount) fail(`${at}.${name}`, `has ${values.length} values but the table has ${rowCount} rows`)
    values.forEach((x, i) => checkCell(x, key === 'counts' ? 'count' : 'share', `${at}.${name}[${i}]`))
    out[name] = values as number[]
  }
  return out
}

function parseFlagsByYear(o: Record<string, unknown>, flagNames: string[]): FlagsByYear {
  const P = DATA_QUALITY_DATASET
  const at = `${P}.flags_by_year`
  const base = needTable(o, 'flags_by_year', P, { source: 'text', year: 'year', rows: 'count' })
  assertNoRepeat(base.source.map((source, i) => `${source} ${base.year[i]}`), `${at}.year`, 'row for')
  const raw = asRecord(o.flags_by_year, at)
  const counts = needFlagColumns(raw, 'counts', at, flagNames, base.rows.length)
  const shares = needFlagColumns(raw, 'shares', at, flagNames, base.rows.length)
  for (const name of flagNames) {
    counts[name].forEach((n, i) => {
      if (n > base.rows[i]) fail(`${at}.counts.${name}[${i}]`, `${n} quotes carry the flag but the row has only ${base.rows[i]}`)
    })
    // The page shows the file's shares and never divides, so a share that is not counts / rows would be shown as fact.
    shares[name].forEach((share, i) => {
      const expected = base.rows[i] === 0 ? 0 : counts[name][i] / base.rows[i]
      if (Math.abs(share - expected) > SHARE_ROUNDING) {
        fail(`${at}.shares.${name}[${i}]`, `is ${share} but ${counts[name][i]} of ${base.rows[i]} quotes is ${expected.toFixed(6)}`)
      }
    })
  }
  return { ...base, counts, shares }
}

function parseCrossVendor(o: Record<string, unknown>): CrossVendor {
  const P = DATA_QUALITY_DATASET
  const at = `${P}.cross_vendor`
  const raw = asRecord(need(o, 'cross_vendor', P), at)
  const distributions = needTable(raw, 'distributions', at, {
    key: 'text',
    label: 'text',
    unit: 'text',
    n: 'count',
    mean: 'number',
    mean_abs: 'number',
    p05: 'number',
    p25: 'number',
    median: 'number',
    p75: 'number',
    p95: 'number',
  })
  distributions.key.forEach((key, i) => {
    const q = [distributions.p05[i], distributions.p25[i], distributions.median[i], distributions.p75[i], distributions.p95[i]]
    if (q.some((v, j) => j > 0 && v < q[j - 1])) {
      fail(`${at}.distributions`, `row ${i} ("${key}") has quantiles out of order: ${q.join(', ')} (p05, p25, median, p75, p95)`)
    }
  })
  const within_thresholds = needTable(raw, 'within_thresholds', at, {
    key: 'text',
    label: 'text',
    threshold: 'number',
    unit: 'text',
    dates: 'count',
    share_within: 'share',
  })
  const by_year = needTable(raw, 'by_year', at, {
    year: 'year',
    dates: 'count',
    iv30_share_within: 'share',
    spot_dolthub_share_within: 'share',
    spot_dolthub_vs_close_median_bp: 'number',
    spot_optionsdx_vs_close_median_bp: 'number',
  })
  const label = needString(raw, 'label', at)
  const overlap_dates = needWholeCount(raw, 'overlap_dates', at)
  const basis = needString(raw, 'basis', at)
  checkCrossVendor(raw, at, overlap_dates, distributions, within_thresholds, by_year)
  return { label, overlap_dates, basis, distributions, within_thresholds, by_year }
}

/**
 * The cross-vendor numbers must agree with each other: the page shows them side by side as facts, so
 * a table that contradicts another is refused. Each rule below is arithmetic on numbers the file
 * already holds, within the rounding the exporter applies (SHARE_ROUNDING for a share, none for a count).
 */
function checkCrossVendor(
  raw: Record<string, unknown>,
  at: string,
  overlap: number,
  d: Distributions,
  w: WithinThresholds,
  y: ByYear,
): void {
  // The check reports measurements, never a verdict: a pass or fail beside them would be shown as one.
  for (const key of CROSS_VENDOR_VERDICT_KEYS) {
    if (key in raw) fail(`${at}.${key}`, 'is a verdict, but the cross-vendor check reports measurements and has none')
  }
  d.key.forEach((key, i) => {
    if (d.n[i] > overlap) fail(`${at}.distributions.n[${i}]`, `${d.n[i]} dates for "${key}" but the vendors overlap on only ${overlap}`)
    // The mean of |x| is at least |mean of x| (rounding keeps the order), so a smaller one is not a mean of the same values.
    if (d.mean_abs[i] < Math.abs(d.mean[i])) {
      fail(`${at}.distributions.mean_abs[${i}]`, `is ${d.mean_abs[i]} for "${key}", below |mean| ${Math.abs(d.mean[i])}`)
    }
  })
  w.key.forEach((key, i) => {
    // The gap is an absolute value compared with the threshold, so a negative threshold admits no date at all.
    if (w.threshold[i] < 0) fail(`${at}.within_thresholds.threshold[${i}]`, `is ${w.threshold[i]} for "${key}", but a threshold on |gap| cannot be negative`)
    if (w.dates[i] > overlap) fail(`${at}.within_thresholds.dates[${i}]`, `${w.dates[i]} dates for "${key}" but the vendors overlap on only ${overlap}`)
  })
  const yearDates = y.dates.reduce((sum, n) => sum + n, 0)
  if (yearDates !== overlap) fail(`${at}.by_year.dates`, `sum to ${yearDates} but the vendors overlap on ${overlap} dates`)
  w.key.forEach((key, i) => {
    const column = key === 'iv30' || key === 'spot' ? POOLED_BY_YEAR_COLUMN[key] : undefined
    if (column === undefined) return
    const range = pooledShareRange(y.dates, y[column], overlap - w.dates[i])
    if (range === undefined) return
    if (w.share_within[i] < range[0] - SHARE_ROUNDING || w.share_within[i] > range[1] + SHARE_ROUNDING) {
      const said = range[0] === range[1] ? range[0].toFixed(6) : `${range[0].toFixed(6)} to ${range[1].toFixed(6)}`
      fail(
        `${at}.within_thresholds.share_within[${i}]`,
        `is ${w.share_within[i]} for "${key}" but by_year.${column}, weighted by the dates of each year, gives ${said}`,
      )
    }
  })
}

/**
 * The pooled share that the years' shares allow, as [lowest, highest]; undefined when no date has a value.
 *
 * Pooled = sum(dates with a value in year * share of year) / (all dates with a value). `yearDates`
 * counts every overlap date of a year, but a date with no value (`missing` of them in all, so
 * `within_thresholds.dates` is smaller than the overlap) counts for no year in the pooled share, and
 * the file does not say which year lost it. So the weights are not known: the lowest pooled share
 * takes the missing dates from the highest-share years, the highest takes them from the lowest. With
 * nothing missing the two coincide and the pooled share is the date-weighted mean of the years.
 */
function pooledShareRange(yearDates: number[], yearShares: number[], missing: number): [number, number] | undefined {
  const valued = yearDates.reduce((sum, n) => sum + n, 0) - missing
  if (valued <= 0) return undefined
  const total = yearDates.reduce((sum, n, i) => sum + n * yearShares[i], 0)
  const without = (order: number[]): number => {
    let left = missing
    let sum = total
    for (const i of order) {
      const take = Math.min(left, yearDates[i])
      sum -= take * yearShares[i]
      left -= take
    }
    return sum / valued
  }
  const byShare = yearShares.map((_, i) => i).sort((a, b) => yearShares[b] - yearShares[a])
  return [without(byShare), without([...byShare].reverse())]
}

/** `max_share` rows say which flag they limit in `what`: "BID_NULL share of a year's quotes". */
const SHARE_WHAT = /^([A-Z_]+) share of a year's quotes$/

/** The flag a `max_share` row limits, or undefined when its `what` does not name one. */
function shareFlagOf(what: string): string | undefined {
  return SHARE_WHAT.exec(what)?.[1]
}

/**
 * The gate rows must be the build's rule set (GATE_RULES): every row a known rule, bounding the side
 * the rule bounds, for a source that has that rule, and each rule with the number of rows each
 * source has. A `max_share` row must name one of the flags GATE_SHARE_FLAGS lists for its source, once.
 */
function checkGateRules(t: { rule: string[]; source: string[]; what: string[]; bound: string[] }, at: string): void {
  const flagsSeen = new Set<string>()
  t.rule.forEach((rule, i) => {
    if (!Object.hasOwn(GATE_RULES, rule)) {
      fail(`${at}.rule[${i}]`, `"${rule}" is not a rule of the quality gate (the gate has ${Object.keys(GATE_RULES).join(', ')})`)
    }
    const spec = GATE_RULES[rule]
    if (t.bound[i] !== spec.bound) fail(`${at}.bound[${i}]`, `${rule} is a "${spec.bound}" limit, got "${t.bound[i]}"`)
    if (!Object.hasOwn(spec.rows, t.source[i])) fail(`${at}.source[${i}]`, `${rule} has no limit for source "${t.source[i]}"`)
    if (rule !== 'max_share') return
    const flag = shareFlagOf(t.what[i])
    if (flag === undefined || !GATE_SHARE_FLAGS[t.source[i]].includes(flag)) {
      fail(
        `${at}.what[${i}]`,
        `"${t.what[i]}" is not a share limit of ${t.source[i]} (it limits ${GATE_SHARE_FLAGS[t.source[i]].join(', ')})`,
      )
    }
    const key = `${t.source[i]} ${flag}`
    if (flagsSeen.has(key)) fail(`${at}.what[${i}]`, `${t.source[i]} has two share limits for ${flag}`)
    flagsSeen.add(key)
  })
  for (const [rule, spec] of Object.entries(GATE_RULES)) {
    for (const [source, expected] of Object.entries(spec.rows)) {
      const found = t.rule.filter((r, i) => r === rule && t.source[i] === source).length
      if (found !== expected) fail(`${at}.rule`, `has ${found} ${rule} row(s) for ${source} but the gate has ${expected}`)
    }
  }
}

/**
 * Each gate row's `worst` is a number the other tables also hold, so it must equal it: a gate that
 * says "worst 3.02%" over a table with a 30% year is not describing this store. Rows whose worst the
 * file cannot rebuild (a thinnest year, a thinnest date, the p99 of the underlying) are left alone.
 *   max_share          the highest share of that flag in flags_by_year over the source's years
 *   min_dates          sources.dates of the source
 *   max_dropped_dates  the dates the calendar drops for the source
 */
function checkGateWorst(t: Thresholds, flags: FlagsByYear, sources: SourceRows, calendar: CalendarCounts): void {
  const at = `${DATA_QUALITY_DATASET}.gate.thresholds.worst`
  t.rule.forEach((rule, i) => {
    const source = t.source[i]
    let expected: number
    if (rule === 'max_share') {
      const flag = shareFlagOf(t.what[i]) as string // checkGateRules has named it
      const shares = flags.shares[flag].filter((_, j) => flags.source[j] === source)
      if (shares.length === 0) fail(`${at}[${i}]`, `flags_by_year has no rows for ${source}, so ${flag} has no share to compare`)
      expected = Math.max(...shares)
      if (Math.abs(t.worst[i] - expected) > SHARE_ROUNDING) {
        fail(`${at}[${i}]`, `is ${t.worst[i]} for ${source} ${flag}, but its highest share in flags_by_year is ${expected}`)
      }
      return
    }
    if (rule === 'min_dates') {
      // A source that sources does not list gives undefined here, which no worst equals: refused below.
      expected = sources.dates[sources.source.indexOf(source)]
    } else if (rule === 'max_dropped_dates') {
      expected = calendar.dates.reduce((sum, n, j) => (calendar.source[j] === source && calendar.action[j] === 'drop' ? sum + n : sum), 0)
    } else {
      return
    }
    if (t.worst[i] !== expected) fail(`${at}[${i}]`, `is ${t.worst[i]} for ${source} ${rule}, but the other tables give ${expected}`)
  })
}

function parseGate(o: Record<string, unknown>): Gate {
  const P = DATA_QUALITY_DATASET
  const at = `${P}.gate`
  const raw = asRecord(need(o, 'gate', P), at)
  const table = needTable(raw, 'thresholds', at, {
    rule: 'text',
    source: 'text',
    what: 'text',
    bound: 'text',
    limit: 'number',
    worst: 'number',
    unit: 'text',
  })
  table.bound.forEach((b, i) => {
    if (b !== 'max' && b !== 'min') fail(`${at}.thresholds.bound[${i}]`, `expected "max" or "min", got "${b}"`)
  })
  checkGateRules(table, `${at}.thresholds`)
  const verdict = needVerdict(raw, at)
  // A passed gate stayed inside every limit (at the limit is inside: "max" is <=, "min" is >=).
  if (verdict.passed) {
    table.rule.forEach((rule, i) => {
      const beyond = table.bound[i] === 'max' ? table.worst[i] > table.limit[i] : table.worst[i] < table.limit[i]
      if (beyond) {
        fail(
          `${at}.passed`,
          `is true but thresholds row ${i} (${table.source[i]} ${rule}: "${table.what[i]}") has worst ${table.worst[i]} beyond its ${table.bound[i]} limit ${table.limit[i]}`,
        )
      }
    })
  }
  return { ...verdict, thresholds: { ...table, bound: table.bound as GateBound[] } }
}

function parseCalendar(o: Record<string, unknown>): CalendarCounts {
  const P = DATA_QUALITY_DATASET
  const at = `${P}.calendar`
  const calendar = needTable(o, 'calendar', P, { source: 'text', action: 'text', dates: 'count', rows: 'count' })
  calendar.action.forEach((action, i) => {
    if (!(CALENDAR_ACTION_NAMES as readonly string[]).includes(action)) {
      fail(`${at}.action[${i}]`, `expected ${CALENDAR_ACTION_NAMES.map((a) => `"${a}"`).join(' or ')}, got "${action}"`)
    }
  })
  assertNoRepeat(calendar.source.map((source, i) => `${source} ${calendar.action[i]}`), `${at}.action`, 'row for')
  return calendar
}

/** `sources` is the per-source total of `flags_by_year`: the same quotes counted two ways must agree. */
function checkSources(flags: FlagsByYear, sources: SourceRows): void {
  const at = `${DATA_QUALITY_DATASET}.sources`
  assertNoRepeat(sources.source, `${at}.source`, 'row for')
  flags.source.forEach((source, j) => {
    if (!sources.source.includes(source)) fail(`${DATA_QUALITY_DATASET}.flags_by_year.source[${j}]`, `"${source}" has no row in sources`)
  })
  sources.source.forEach((source, i) => {
    const total = flags.rows.reduce((sum, n, j) => (flags.source[j] === source ? sum + n : sum), 0)
    if (sources.rows[i] !== total) fail(`${at}.rows[${i}]`, `is ${sources.rows[i]} for ${source} but flags_by_year has ${total} quotes of it`)
  })
}

export function parseDataQuality(raw: unknown): DataQuality {
  const P = DATA_QUALITY_DATASET
  const o = asRecord(raw, P)
  const schema_version = needSchemaVersion(o, P)
  const generated_at = needTimestamp(o, P)
  const source_commit = needSourceCommit(o, P)
  const label = needString(o, 'label', P)
  const flag_names = needFlagNames(o, P)
  const flag_descriptions = needStrings(o, 'flag_descriptions', P)
  if (flag_descriptions.length !== flag_names.length) {
    fail(`${P}.flag_descriptions`, `has ${flag_descriptions.length} entries but flag_names has ${flag_names.length}`)
  }
  // Each table is read for its own shape first, in file order; only then are they held against each other.
  const flags_by_year = parseFlagsByYear(o, flag_names)
  const sources = needTable(o, 'sources', P, { source: 'text', rows: 'count', dates: 'count' })
  const calendar = parseCalendar(o)
  const cross_vendor = parseCrossVendor(o)
  const gate = parseGate(o)
  checkSources(flags_by_year, sources)
  checkGateWorst(gate.thresholds, flags_by_year, sources, calendar)
  return { schema_version, generated_at, source_commit, label, flag_names, flag_descriptions, flags_by_year, sources, calendar, cross_vendor, gate }
}

// ---------------------------------------------------------------- small pure helpers

export function findDataset(manifest: Manifest, name: string): DatasetEntry | undefined {
  return manifest.datasets.find((d) => d.name === name)
}

/**
 * The manifest says which schema_version each dataset file has; the file says it again about
 * itself. They are written by the same exporter run, so they must agree. A mismatch means the
 * manifest and the file come from different runs (or one was edited by hand), and the app cannot
 * tell which of the two to believe.
 */
export function assertDatasetMatchesEntry(entry: DatasetEntry, dataset: { schema_version: string }): void {
  if (dataset.schema_version !== entry.schema_version) {
    fail(
      entry.name,
      `the manifest lists schema_version "${entry.schema_version}" but ${entry.path} says "${dataset.schema_version}"`,
    )
  }
}

export type CommitState = 'clean' | 'dirty' | 'uncommitted'

/** Whether results were exported from a clean commit (reproducible) or not. */
export function commitState(sourceCommit: string): CommitState {
  if (sourceCommit === 'uncommitted') return 'uncommitted'
  return sourceCommit.endsWith('-dirty') ? 'dirty' : 'clean'
}
