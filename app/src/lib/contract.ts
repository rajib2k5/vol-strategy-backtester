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

/** Sanity ceiling on IV: 5.0 = 500%. Catches an exporter that wrote percent (18) instead of decimal (0.18). In
 * surface_frames.json it bounds every cell except the ones ivCeiling names (parseFrame). */
export const MAX_IV = 5
/**
 * The ceiling of a surface_frames.json cell that ivCeiling lets read above MAX_IV. It is not a bound of the method:
 * a wing grows with Lee's slope, up to 2 per unit of |k|, from the smile's outermost node, and that node can sit far
 * from the grid, so a wing can read any IV (a 7-day put-only smile with nodes at k in [-1, -0.8] reads above 10 on
 * its own row; round-3 review, X1). The exporter refuses a frame with a cell above its ceiling
 * (tools/export_app_data.py check_frame_ivs), so a file here above 10 is not one the exporter wrote, or it holds
 * percent written for a decimal (18 for 0.18).
 */
export const MAX_EXTRAPOLATED_IV = 10

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

// ---------------------------------------------------------------- surface frames (milestone 2)

/** The dataset the Surface page reads: real SPY implied-vol surfaces on a fixed grid, for a few labelled dates. */
export const SURFACE_FRAMES_DATASET = 'surface_frames'

/**
 * The bits of a grid cell's `cell_flags`, in bit order (src/volbt/pricing/smile.py SURFACE_FLAG_NAMES,
 * ADR-0004): 1 = read beyond the quoted strikes, 2 = between two listed expiries, 4 = outside the
 * listed tenors, 8 = the calendar adjustment (no falling total variance with tenor) moved the value,
 * up or down. A file with other names is refused: the page explains these four.
 */
export const SURFACE_CELL_FLAG_NAMES = ['SURFACE_EXTRAP_STRIKE', 'SURFACE_CROSS_EXPIRY', 'SURFACE_EXTRAP_TENOR', 'SURFACE_CALENDAR_ADJUSTED'] as const

/** The bits that make a cell an extrapolation (strike or tenor); between-expiry interpolation and the calendar adjustment are not one. */
export const EXTRAPOLATED_BITS = 1 | 4

const FLAG_EXTRAP_STRIKE = 1
const FLAG_CROSS_EXPIRY = 2
const FLAG_EXTRAP_TENOR = 4
const FLAG_CALENDAR_ADJUSTED = 8

/** The highest cell_flags value: all four bits set. */
const MAX_CELL_FLAGS = 15

/** The pricing grid must be able to answer "what is the 30-day at-the-money vol?": the frame's atm_iv_30d is that cell. */
const ATM_DTE = 30
const ATM_MONEYNESS = 0

/** The first schema_version that has a surface_frames file; an older file cannot be one. */
export const SURFACE_FRAMES_MIN_VERSION = '0.3.0'

/*
 * Plausible ranges for a frame's SPY close (USD) and VIX close (index points): every close since 2010 sits well
 * inside, and a unit slip (cents, a VIX written as a decimal) or a wrong column falls outside. Measured in the store
 * on 2026-10-29: SPY closed between 102.20 (2010-07-02) and 779.09 (2026-10-06) from 2010 on; VIX between 9.14
 * (2017-11-03) and 82.69 (2020-03-16) from 1990 on. The margins: 50 is under half of 102.20 and 2000 over 2.5 times
 * 779.09; 5 is under 0.55 of 9.14 and 150 over 1.8 times 82.69.
 */
export const MIN_SPY_CLOSE = 50
export const MAX_SPY_CLOSE = 2000
export const MIN_VIX_CLOSE = 5
export const MAX_VIX_CLOSE = 150

/**
 * Relative slack of the calendar check (checkCalendar), for float noise only. The exporter rounds each IV to 6
 * decimals and then raises a cell by 1e-6 until iv * iv * dte / 365, computed in the order totalVariance computes
 * it, does not fall from one tenor row to the next (src/volbt/build.py surface_frame), so its files hold exact
 * non-decrease, checked row by row in the same float operations. 1e-12 of the variance only absorbs a last-bit
 * difference; a hand-made file can fall by less than that and pass (6.7e-14 relative with 6-decimal IVs, round-2 review).
 */
const CALENDAR_SLACK = 1e-12

/** The vendors a surface file may name in run.data_source, with the name the Surface page shows for each. */
export const DATA_SOURCE_NAMES = { optionsdx: 'OptionsDX', dolthub: 'DoltHub' } as const
export type DataSource = keyof typeof DATA_SOURCE_NAMES

/** Own keys only: "constructor" and "toString" are on every object and are not vendors. */
function isDataSource(v: string): v is DataSource {
  return Object.hasOwn(DATA_SOURCE_NAMES, v)
}

/** The name the Surface page shows for a data_source the parser has accepted. */
export function dataSourceName(source: string): string {
  if (!isDataSource(source)) fail('data_source', `"${source}" is not a known data source`)
  return DATA_SOURCE_NAMES[source]
}

/** A SHA-256 as hex: config_hash and data_fingerprint are each one. */
const SHA256_HEX = /^[0-9a-f]{64}$/

/**
 * A pricing build names its run after its code: "pricing-" and the first 12 hex digits of config_hash
 * (tools/export_app_data.py surface_frames_body). A run_id naming another hash says another build made the file.
 */
const RUN_ID_PREFIX = 'pricing-'
const RUN_ID_HASH_DIGITS = 12

/** ADR-0001 §5: the `run` block every results dataset carries, in this order (data_last_date is the pricing build's addition). */
export const RUN_KEYS = [
  'run_id',
  'config_hash',
  'data_fingerprint',
  'data_source',
  'data_last_date',
  'execution_mode',
  'fill_timing',
  'cap_mode',
  'chain_mask',
  'sample_start',
  'sample_end',
] as const

/** The run keys that belong to a backtest; a pricing build writes them as null. */
const RUN_NULLABLE: readonly string[] = ['execution_mode', 'fill_timing', 'cap_mode']

/** The number fields the Surface page shows: each needs a unit in `units`, so the page never guesses one. */
export const SURFACE_UNIT_KEYS = [
  'grid_moneyness',
  'grid_dte',
  'iv',
  'atm_iv_30d',
  'spot',
  'vix_close',
  'quoted_share',
  'cell_flags',
  'expiries_used',
] as const

/**
 * The unit of each of those fields, exactly as tools/export_app_data.py SURFACE_UNITS writes it. The page prints the
 * file's unit beside the number, so a unit that is not the exporter's (percent beside decimal IVs) would put a wrong
 * unit beside a right number: any other string is refused.
 */
export const SURFACE_UNITS: Record<(typeof SURFACE_UNIT_KEYS)[number], string> = {
  grid_moneyness: 'log-moneyness ln(K/F), F the de-Americanised parity forward of each tenor',
  grid_dte: 'calendar days to expiry',
  iv: 'implied volatility, decimal (0.20 = 20%)',
  atm_iv_30d: 'implied volatility at k = 0 and 30 days, decimal',
  spot: 'USD, the SPY close',
  vix_close: 'index points, the Cboe VIX close',
  quoted_share: 'fraction of grid cells read without strike or tenor extrapolation',
  cell_flags: 'bitmask of SURFACE_EXTRAP_STRIKE (1), SURFACE_CROSS_EXPIRY (2), SURFACE_EXTRAP_TENOR (4), SURFACE_CALENDAR_ADJUSTED (8)',
  expiries_used: 'listed expiries with a usable smile (5 or more valid OTM quotes)',
}

export type RunBlock = Record<(typeof RUN_KEYS)[number], string | null>

export interface SurfaceFrame {
  /** YYYY-MM-DD, the quote date: a weekday. */
  date: string
  /** The exporter's hand-written description of the date; not derived from any number of the frame. */
  label: string
  /** The SPY close, USD. */
  spot: number
  vix_close: number
  /** Listed expiries with a usable smile (5 or more valid OTM quotes). */
  expiries_used: number
  /** Implied vol as a decimal, iv[i_dte][j_moneyness]. */
  iv: number[][]
  /** SURFACE_CELL_FLAG_NAMES bits per cell, same shape as iv. */
  cell_flags: number[][]
  /** 0 to 1, computed by Python: the share of cells with no EXTRAPOLATED_BITS. */
  quoted_share: number
  atm_iv_30d: number
}

export interface SurfaceFrames {
  schema_version: string
  generated_at: string
  source_commit: string
  run: RunBlock
  units: Record<(typeof SURFACE_UNIT_KEYS)[number], string>
  illustrative: false
  label: string
  /** Log-moneyness ln(K/F), strictly increasing. */
  grid_moneyness: number[]
  /** Calendar days to expiry, whole and strictly increasing. */
  grid_dte: number[]
  cell_flag_names: string[]
  /** At least one, in strictly increasing date order. */
  frames: SurfaceFrame[]
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

// ---------------------------------------------------------------- surface frames

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

/** True for a YYYY-MM-DD date that exists (2023-02-30 does not: it would print back as 03-02). */
function isRealDate(v: string): boolean {
  if (!ISO_DATE.test(v)) return false
  const d = new Date(`${v}T00:00:00Z`)
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === v
}

function needDate(obj: Record<string, unknown>, key: string, path: string): string {
  const v = needString(obj, key, path)
  if (!isRealDate(v)) fail(`${path}.${key}`, `"${v}" is not a calendar date YYYY-MM-DD`)
  return v
}

/** A finite number in (0, max]. */
function needPositive(obj: Record<string, unknown>, key: string, path: string, max: number): number {
  const v = need(obj, key, path)
  const at = `${path}.${key}`
  if (typeof v !== 'number' || !Number.isFinite(v)) fail(at, `expected a finite number, got ${String(v)}`)
  if (v <= 0 || v > max) fail(at, `${v} is outside (0, ${max}]`)
  return v
}

/** A finite number in [min, max], the plausible range of `what`. */
function needInRange(obj: Record<string, unknown>, key: string, path: string, min: number, max: number, what: string): number {
  const v = need(obj, key, path)
  const at = `${path}.${key}`
  if (typeof v !== 'number' || !Number.isFinite(v)) fail(at, `expected a finite number, got ${String(v)}`)
  if (v < min || v > max) fail(at, `${v} is outside [${min}, ${max}], the plausible range of ${what}`)
  return v
}

/** The eleven run keys of a pricing build (ADR-0001 §5 plus data_last_date). Unknown extra keys are dropped, as everywhere in this contract. */
function parseRun(o: Record<string, unknown>, path: string): RunBlock {
  const at = `${path}.run`
  const raw = asRecord(need(o, 'run', path), at)
  const run = {} as RunBlock
  for (const key of RUN_KEYS) {
    const v = need(raw, key, at)
    if (v === null && RUN_NULLABLE.includes(key)) {
      run[key] = null
      continue
    }
    if (typeof v !== 'string' || v.trim() === '') {
      fail(`${at}.${key}`, RUN_NULLABLE.includes(key) ? 'expected a non-empty string or null' : 'expected a non-empty string')
    }
    run[key] = v
  }
  // The page prints both as "the code" and "the inputs" of the run: anything but a SHA-256 is not a fingerprint of either.
  for (const key of ['config_hash', 'data_fingerprint'] as const) {
    if (!SHA256_HEX.test(run[key] as string)) fail(`${at}.${key}`, `"${run[key]}" is not a SHA-256 (64 lowercase hex digits)`)
  }
  const runId = `${RUN_ID_PREFIX}${(run.config_hash as string).slice(0, RUN_ID_HASH_DIGITS)}`
  if (run.run_id !== runId) {
    fail(`${at}.run_id`, `"${run.run_id}" is not "${runId}", the pricing build's name for config_hash ${run.config_hash} ("${RUN_ID_PREFIX}" and its first ${RUN_ID_HASH_DIGITS} hex digits)`)
  }
  if (!isDataSource(run.data_source as string)) {
    fail(`${at}.data_source`, `"${run.data_source}" is not a known data source (${Object.keys(DATA_SOURCE_NAMES).join(', ')})`)
  }
  for (const key of ['sample_start', 'sample_end', 'data_last_date'] as const) needDate(raw, key, at)
  if ((run.sample_start as string) > (run.sample_end as string)) {
    fail(`${at}.sample_end`, `${run.sample_end} is before sample_start ${run.sample_start}`)
  }
  // The sample cannot run past the last quote date the source has.
  if ((run.sample_end as string) > (run.data_last_date as string)) {
    fail(`${at}.sample_end`, `${run.sample_end} is after data_last_date ${run.data_last_date}, the last quote date the source has`)
  }
  return run
}

function parseUnits(o: Record<string, unknown>, path: string): SurfaceFrames['units'] {
  const at = `${path}.units`
  const raw = asRecord(need(o, 'units', path), at)
  const units = {} as SurfaceFrames['units']
  for (const key of SURFACE_UNIT_KEYS) {
    const unit = needString(raw, key, at)
    if (unit !== SURFACE_UNITS[key]) fail(`${at}.${key}`, `"${unit}" is not the exporter's unit for ${key}, "${SURFACE_UNITS[key]}"`)
    units[key] = unit
  }
  return units
}

/** rows x cols of numbers, each passing `check` (which fails with its own message). */
function needGrid(
  obj: Record<string, unknown>,
  key: string,
  path: string,
  rows: number,
  cols: number,
  check: (x: number, at: string) => void,
): number[][] {
  const at = `${path}.${key}`
  const grid = needArray(obj, key, path)
  if (grid.length !== rows) fail(at, `has ${grid.length} rows but grid_dte has ${rows} values`)
  return grid.map((row, i): number[] => {
    const rowAt = `${at}[${i}]`
    if (!Array.isArray(row)) fail(rowAt, 'expected an array of numbers')
    if (row.length !== cols) fail(rowAt, `has ${row.length} values but grid_moneyness has ${cols} (ragged grid)`)
    row.forEach((x, j) => {
      if (typeof x !== 'number' || !Number.isFinite(x)) fail(`${rowAt}[${j}]`, `expected a finite number, got ${String(x)}`)
      check(x, `${rowAt}[${j}]`)
    })
    return row as number[]
  })
}

/** Total variance, in the order the exporter computes it (the order matters to the last bit of a float). */
function totalVariance(iv: number, dte: number): number {
  return (iv * iv * dte) / 365
}

/** SURFACE_CROSS_EXPIRY interpolates between two listed expiries, so a frame that used fewer than 2 cannot carry it. */
function checkCrossExpiryNeedsTwo(cell_flags: number[][], expiries_used: number, at: string): void {
  const crossing = cell_flags.flat().filter((x) => (x & FLAG_CROSS_EXPIRY) !== 0).length
  if (crossing > 0 && expiries_used < 2) {
    fail(`${at}.expiries_used`, `is ${expiries_used} but ${crossing} cell(s) carry SURFACE_CROSS_EXPIRY, which needs at least 2 listed expiries`)
  }
}

/** Where a grid tenor sits among the frame's listed expiries, as its row's tenor bits say. */
type TenorPlace = 'outside' | 'between' | 'on'

/**
 * A row's tenor bits say where its tenor sits among the listed expiries (src/volbt/pricing/smile.py surface_iv):
 * before the front expiry or past the back one, SURFACE_EXTRAP_TENOR; strictly between two, SURFACE_CROSS_EXPIRY; on
 * a listed expiry (tau equal to dte / 365), neither. That is a property of the tenor, not of the cell, so within a
 * grid_dte row every cell carries each of the two bits or none does. Returns each row's place.
 */
function tenorPlaces(cell_flags: number[][], dte: number[], at: string): TenorPlace[] {
  const bits = [
    [FLAG_EXTRAP_TENOR, 'SURFACE_EXTRAP_TENOR'],
    [FLAG_CROSS_EXPIRY, 'SURFACE_CROSS_EXPIRY'],
  ] as const
  return cell_flags.map((row, i): TenorPlace => {
    for (const [bit, name] of bits) {
      const n = row.filter((x) => (x & bit) !== 0).length
      if (n !== 0 && n !== row.length) {
        fail(`${at}.cell_flags[${i}]`, `${n} of ${row.length} cells of the ${dte[i]}-day row carry ${name}; the flag is for a whole row or none`)
      }
    }
    if ((row[0] & FLAG_EXTRAP_TENOR) !== 0) return 'outside'
    return (row[0] & FLAG_CROSS_EXPIRY) !== 0 ? 'between' : 'on'
  })
}

/** What the rows' tenor bits show about the listed expiries (rowLayout). */
interface RowLayout {
  /** True when no row is inside the listed expiries: the outside rows then lead and close the grid, split where the file does not show. */
  allOutside: boolean
  /** The rows before the front expiry, in tenor order: the outside rows ahead of the first inside row. */
  beforeFront: number[]
  /** The rows past the back expiry, in tenor order: the outside rows after the last inside row. */
  pastBack: number[]
  /** The row on the front expiry, when the file proves which one it is (rowLayout); -1 otherwise. */
  frontRow: number
  /** The row on the back expiry, likewise; -1 otherwise. */
  backRow: number
}

/** i, i + 1, ..., end - 1. */
function range(start: number, end: number): number[] {
  return Array.from({ length: Math.max(0, end - start) }, (_, n) => start + n)
}

/**
 * The rows' places must fit one ordered list of expiries, expiries_used of them:
 * - the rows outside the listed expiries are those before the front one and those past the back one, so they lead
 *   and close the grid; an outside row between two rows inside the listed range contradicts its neighbours;
 * - the frame used at least as many expiries as its rows need: one per row on an expiry (the grid tenors differ, so
 *   each is a different expiry), plus one below the first inside row if that row is between two (that expiry is
 *   below every inside row, so it is none of theirs), plus one above the last inside row likewise. A frame of 1
 *   expiry so has at most one row on it and none between two.
 * When expiries_used is exactly what the rows need, those are all the listed expiries. Then a first inside row on an
 * expiry sits on the front one (no listed expiry is shorter), and a last inside row on an expiry sits on the back one.
 * With more expiries than that, a shorter one can sit between the rows: a 7-day row before a 10-day front and a 14-day
 * row on the second expiry show the same flags as a 14-day front (round 3, P1 and P6), so no row is named the front.
 * Returns the layout the later checks read.
 */
function rowLayout(places: TenorPlace[], dte: number[], expiries_used: number, at: string): RowLayout {
  const inside = places.flatMap((place, i) => (place === 'outside' ? [] : [i]))
  if (inside.length === 0) return { allOutside: true, beforeFront: [], pastBack: [], frontRow: -1, backRow: -1 }
  const first = inside[0]
  const last = inside[inside.length - 1]
  for (let i = first + 1; i < last; i++) {
    if (places[i] === 'outside') {
      fail(
        `${at}.cell_flags[${i}]`,
        `the ${dte[i]}-day row carries SURFACE_EXTRAP_TENOR between the ${dte[first]}-day and ${dte[last]}-day rows, which are inside the listed expiries; a tenor is outside them only before the front expiry or past the back one`,
      )
    }
  }
  const on = inside.filter((i) => places[i] === 'on').length
  const below = places[first] === 'between' ? 1 : 0
  const above = places[last] === 'between' ? 1 : 0
  if (on + below + above > expiries_used) {
    fail(
      `${at}.expiries_used`,
      `is ${expiries_used} but the rows need at least ${on + below + above} listed expiries: ${on} row(s) on an expiry (neither SURFACE_CROSS_EXPIRY nor SURFACE_EXTRAP_TENOR), a different one each, ${below} below the first inside row and ${above} above the last (a row between two expiries has one on each side)`,
    )
  }
  const exact = on + below + above === expiries_used
  return {
    allOutside: false,
    beforeFront: range(0, first),
    pastBack: range(last + 1, places.length),
    frontRow: exact && places[first] === 'on' ? first : -1,
    backRow: exact && places[last] === 'on' ? last : -1,
  }
}

/**
 * The highest IV the exporter can write in a cell, by its flags and row (src/volbt/pricing/smile.py surface_iv; the
 * exporter refuses a frame above it, tools/export_app_data.py iv_ceilings, which reads the same rule):
 * - beyond a smile's quoted strikes (SURFACE_EXTRAP_STRIKE) the wing grows with Lee's slope, which the solver does not
 *   bound: MAX_EXTRAPOLATED_IV (a 7-day wing at k = -0.30 read 5.07 in the round-2 review);
 * - past the back expiry, where the calendar adjustment moved the value (SURFACE_EXTRAP_TENOR with
 *   SURFACE_CALENDAR_ADJUSTED): the value is the running maximum of the back smile read along k sqrt(t_back / tau')
 *   and never below the back's own w at k, and both can come from beyond the back's last node while the cell's own
 *   reading x = k sqrt(t_back / tau) is inside it, so the cell carries no strike bit (smile.py sets that bit from x
 *   alone). MAX_EXTRAPOLATED_IV: on 60,000 random surfaces through the exporter (round 3, T1), 3,248 such cells read
 *   above 5, 81 of them above 10 (frames the exporter refuses). When no row is inside the listed expiries, any outside
 *   row may be past the back;
 * - anywhere else the value is read inside some smile's quoted strikes: on an expiry and between two, w is at most a
 *   quoted w (the calendar raises a quote only to another quote); before the front, the running minimum only lowers
 *   the value read off the front at x. So a solved IV bounds it: MAX_IV (0 such cells above 5 on those surfaces, but
 *   for the exporter's rounding raise of a solved 5 to 5.000001, whose frame the exporter refuses).
 * Bit 4 alone, past the back, is the unmoved reading at x: MAX_IV too.
 */
function ivCeiling(flags: number, row: number, layout: RowLayout): number {
  if ((flags & FLAG_EXTRAP_STRIKE) !== 0) return MAX_EXTRAPOLATED_IV
  const pastBack = layout.allOutside || layout.pastBack.includes(row)
  return pastBack && (flags & FLAG_CALENDAR_ADJUSTED) !== 0 ? MAX_EXTRAPOLATED_IV : MAX_IV
}

function checkIvCeilings(iv: number[][], cell_flags: number[][], layout: RowLayout, dte: number[], moneyness: number[], at: string): void {
  iv.forEach((row, i) => row.forEach((x, j) => {
    const ceiling = ivCeiling(cell_flags[i][j], i, layout)
    if (x > ceiling) {
      fail(
        `${at}.iv[${i}][${j}]`,
        `implied vol ${x} is outside (0, ${ceiling}], the ceiling of a cell flagged ${cell_flags[i][j]} at k = ${moneyness[j]} on the ${dte[i]}-day row: only a cell beyond the quoted strikes, or one past the back expiry that the calendar adjustment moved, reads above a solved IV (${MAX_IV}); it must be a decimal (0.18 = 18%)`,
      )
    }
  }))
}

/**
 * SURFACE_EXTRAP_STRIKE marks a cell read beyond a smile's quoted strikes. A smile's nodes span one interval of k, so
 * in a row the flagged cells are those left of it and those right of it: a run from each edge of the grid. A row
 * between two expiries carries either expiry's flag (two runs from the same edge make one), and a row outside the
 * listed tenors reads the near expiry along k sqrt(tau_near / tau), which keeps the order of k. A flagged cell with an
 * unflagged one on each side contradicts that.
 */
function checkStrikeFlagAtEdges(cell_flags: number[][], dte: number[], moneyness: number[], at: string): void {
  cell_flags.forEach((row, i) => {
    const beyond = row.map((x) => (x & FLAG_EXTRAP_STRIKE) !== 0)
    let lo = 0
    while (lo < beyond.length && beyond[lo]) lo++
    let hi = beyond.length
    while (hi > lo && beyond[hi - 1]) hi--
    const j = beyond.indexOf(true, lo)
    if (j !== -1 && j < hi) {
      fail(
        `${at}.cell_flags[${i}][${j}]`,
        `carries SURFACE_EXTRAP_STRIKE at k = ${moneyness[j]} in the ${dte[i]}-day row, with cells read inside the quoted strikes on both sides; beyond the strikes is a run from an edge of the grid, never a gap inside it`,
      )
    }
  })
}

/**
 * The rows read off one expiry keep the order of that reading (src/volbt/pricing/smile.py step 5). The rows before the
 * front read the front smile at x = k s, s = sqrt(t_front / tau) above 1 and falling as tau grows, and the front's own
 * row reads it at s = 1; the back's own row reads the back smile at s = 1 and the rows past it at s below 1, falling
 * as tau grows. So in each group, in tenor order, s falls. A cell is beyond the quoted strikes where k s is outside
 * the expiry's node interval [k_lo, k_hi], so:
 * - at k = 0, x = 0 on every row of a group: the strike bit is the same on all of them;
 * - in a row with a cell inside the strikes, its left-edge run is the cells with k s < k_lo. At k <= 0, an earlier
 *   row (s' > s) reads k s' <= k s, so it is beyond the strikes there too; likewise the right-edge run at k >= 0.
 * What it cannot say (round 3, P6): a cell at k < 0 in the RIGHT run (k s > k_hi, a smile left of the cell) or at k > 0
 * in the left run can be inside the strikes on an earlier row, whose k s' is further out. A 14-day front with nodes at
 * k in [-0.6, -0.29] is beyond its right edge at k = -0.28 while the 7-day row before it reads x = -0.40, inside. A row
 * beyond the strikes everywhere does not show which side a cell is on, so it constrains nothing but k = 0. The front's
 * and the back's own rows join their groups only when the file proves which rows they are (rowLayout).
 */
function checkStrikeFlagAlongTenor(cell_flags: number[][], layout: RowLayout, dte: number[], moneyness: number[], at: string): void {
  const k0 = moneyness.indexOf(ATM_MONEYNESS)
  const beyond = (i: number, j: number) => (cell_flags[i][j] & FLAG_EXTRAP_STRIKE) !== 0
  const groups: [string, number[]][] = [
    ['front', [...layout.beforeFront, ...(layout.frontRow >= 0 ? [layout.frontRow] : [])]],
    ['back', [...(layout.backRow >= 0 ? [layout.backRow] : []), ...layout.pastBack]],
  ]
  for (const [expiry, group] of groups) {
    group.forEach((r, n) => {
      if (n > 0 && beyond(r, k0) !== beyond(group[0], k0)) {
        fail(
          `${at}.cell_flags[${r}][${k0}]`,
          `${beyond(r, k0) ? 'carries' : 'carries no'} SURFACE_EXTRAP_STRIKE at k = 0 on the ${dte[r]}-day row but the ${dte[group[0]]}-day row ${beyond(group[0], k0) ? 'does' : 'does not'}: both read the ${expiry} expiry's smile at x = 0, so both are beyond its strikes there or neither is`,
        )
      }
      const row = cell_flags[r]
      if (row.every((_, j) => beyond(r, j))) return
      let lo = 0
      while (beyond(r, lo)) lo++
      let hi = row.length
      while (beyond(r, hi - 1)) hi--
      row.forEach((_, j) => {
        const side = j < lo && moneyness[j] <= 0 ? 'left' : j >= hi && moneyness[j] >= 0 ? 'right' : null
        if (side === null) return
        const earlier = group.slice(0, n).find((e) => !beyond(e, j))
        if (earlier !== undefined) {
          fail(
            `${at}.cell_flags[${earlier}][${j}]`,
            `carries no SURFACE_EXTRAP_STRIKE at k = ${moneyness[j]} on the ${dte[earlier]}-day row, while the ${dte[r]}-day row is beyond the ${expiry} expiry's ${side} strike there; both read that smile along k sqrt(t / tau), the ${dte[earlier]}-day row further ${side}, so it is beyond it too`,
          )
        }
      })
    })
  }
}

/**
 * Where SURFACE_CALENDAR_ADJUSTED cannot be. The adjustment moves a value only against another expiry's (the calendar
 * rule of src/volbt/pricing/smile.py), so:
 * - with 1 listed expiry, the row on it is that expiry's own smile, with no other expiry to adjust it against;
 * - before the front expiry, at k = 0, the tenor extrapolation holds the front's at-the-money vol, so total variance
 *   rises linearly in tau up to the front's own value: its running minimum is itself, and the cap at the front's
 *   value does not bind. That needs the front's k = 0 value to be quoted, never moved: k = 0 inside its strikes, which
 *   the row's k = 0 cell shows by carrying no SURFACE_EXTRAP_STRIKE (along k / sqrt(tau), k = 0 reads the front at
 *   k = 0), and the front has no shorter expiry to be raised to. The rows before the front are the outside rows ahead
 *   of the first inside row; when every row is outside, which ones lead is unknown and nothing is checked;
 * - on the front expiry's own row, when the file proves which row that is (rowLayout), inside the strikes: a quoted
 *   value of the front has no shorter quote to be raised to (calendar_variance's running maximum starts at it), so
 *   only a cell beyond the strikes there can move (lowered to the next quoted value). When the file does not prove it,
 *   the first inside row may sit on a later expiry, raised to a shorter one between the rows (round 3, P1).
 * Anywhere else bit 8 may be right: the file holds only the moved value, so whether a value moved cannot be read back.
 */
function checkCalendarFlag(
  cell_flags: number[][],
  places: TenorPlace[],
  layout: RowLayout,
  dte: number[],
  moneyness: number[],
  expiries_used: number,
  at: string,
): void {
  const k0 = moneyness.indexOf(ATM_MONEYNESS)
  const firstInside = places.findIndex((place) => place !== 'outside')
  cell_flags.forEach((row, i) => {
    const j = row.findIndex((x) => (x & FLAG_CALENDAR_ADJUSTED) !== 0)
    if (expiries_used === 1 && places[i] === 'on' && j !== -1) {
      fail(
        `${at}.cell_flags[${i}][${j}]`,
        `carries SURFACE_CALENDAR_ADJUSTED on the ${dte[i]}-day row, which sits on the frame's only expiry: with no other expiry, nothing can adjust that expiry's own smile`,
      )
    }
    if (i < firstInside && (row[k0] & FLAG_CALENDAR_ADJUSTED) !== 0 && (row[k0] & FLAG_EXTRAP_STRIKE) === 0) {
      fail(
        `${at}.cell_flags[${i}][${k0}]`,
        `carries SURFACE_CALENDAR_ADJUSTED at k = 0 on the ${dte[i]}-day row, before the front expiry and inside its strikes: there total variance rises linearly to the front's quoted value, so the adjustment cannot move it`,
      )
    }
    const quotedMoved = row.findIndex((x) => (x & FLAG_CALENDAR_ADJUSTED) !== 0 && (x & FLAG_EXTRAP_STRIKE) === 0)
    if (i === layout.frontRow && quotedMoved !== -1) {
      fail(
        `${at}.cell_flags[${i}][${quotedMoved}]`,
        `carries SURFACE_CALENDAR_ADJUSTED inside the quoted strikes on the ${dte[i]}-day row, which sits on the front expiry (expiries_used ${expiries_used} is exactly the expiries the rows need, so none is shorter): a quote of the front has no shorter quote to be raised to`,
      )
    }
  })
}

/**
 * Total variance never falls with tenor at a fixed log-moneyness (no calendar arbitrage). The surface is built so
 * (the calendar adjustment moves values until it holds) and the exporter keeps it through its rounding, so a fall
 * beyond CALENDAR_SLACK is refused whatever the cell's flags say: bit 8 says a value was moved, never that it may fall.
 * Equal is allowed: that is what a value raised to the one above looks like.
 */
function checkCalendar(iv: number[][], dte: number[], moneyness: number[], at: string): void {
  for (let i = 1; i < iv.length; i++) {
    for (let j = 0; j < moneyness.length; j++) {
      const w = totalVariance(iv[i][j], dte[i])
      const above = totalVariance(iv[i - 1][j], dte[i - 1])
      if (w < above * (1 - CALENDAR_SLACK)) {
        fail(
          `${at}.iv[${i}][${j}]`,
          `total variance ${w.toPrecision(6)} at ${dte[i]} days is below ${above.toPrecision(6)} at ${dte[i - 1]} days (k = ${moneyness[j]}); it never falls with tenor, whatever the cell's flags`,
        )
      }
    }
  }
}

function parseFrame(raw: unknown, at: string, dte: number[], moneyness: number[]): SurfaceFrame {
  const rows = dte.length
  const cols = moneyness.length
  const f = asRecord(raw, at)
  const date = needDate(f, 'date', at)
  // A frame is one trading session's quotes. The app has no exchange calendar, so a weekday is the proxy it checks:
  // a Saturday or a Sunday is never an SPY session (an exchange holiday on a weekday is not caught here).
  const weekday = new Date(`${date}T00:00:00Z`).getUTCDay()
  if (weekday === 0 || weekday === 6) {
    fail(`${at}.date`, `${date} is a ${weekday === 0 ? 'Sunday' : 'Saturday'}: a frame is one session's quotes, and SPY does not trade at weekends`)
  }
  // The label is the exporter's own text, written by hand beside each date (tools/export_app_data.py
  // SURFACE_FRAME_DATES), not derived from vix_close or any other number of the frame. So what it says cannot be
  // checked here ("calm" beside a VIX close of 82.69 is accepted); only its shape is: a non-empty string.
  const label = needString(f, 'label', at)
  const spot = needInRange(f, 'spot', at, MIN_SPY_CLOSE, MAX_SPY_CLOSE, 'a SPY close in USD')
  const vix_close = needInRange(f, 'vix_close', at, MIN_VIX_CLOSE, MAX_VIX_CLOSE, 'a VIX close in index points')
  const expiries_used = needWholeCount(f, 'expiries_used', at)
  if (expiries_used < 1) fail(`${at}.expiries_used`, 'a surface needs at least 1 usable expiry, got 0')
  // Every cell must be in (0, MAX_EXTRAPOLATED_IV], which refuses percent written for a decimal. Its own ceiling,
  // MAX_IV unless its flags and row say the exporter can read above a solved IV there, needs the flags and the rows'
  // layout, so it is checked below (checkIvCeilings); an IV of 4.99 passes both, and the frame is then accepted only
  // where it keeps total variance from falling to the next tenor row (checkCalendar).
  const iv = needGrid(f, 'iv', at, rows, cols, (x, cell) => {
    if (x <= 0 || x > MAX_EXTRAPOLATED_IV) {
      fail(cell, `implied vol ${x} is outside (0, ${MAX_IV}] (or (0, ${MAX_EXTRAPOLATED_IV}] where extrapolated); it must be a decimal (0.18 = 18%)`)
    }
  })
  const cell_flags = needGrid(f, 'cell_flags', at, rows, cols, (x, cell) => {
    if (!Number.isInteger(x) || x < 0 || x > MAX_CELL_FLAGS) fail(cell, `expected a bitmask from 0 to ${MAX_CELL_FLAGS}, got ${x}`)
    if ((x & FLAG_CROSS_EXPIRY) !== 0 && (x & FLAG_EXTRAP_TENOR) !== 0) {
      fail(cell, `flags ${x} set SURFACE_CROSS_EXPIRY and SURFACE_EXTRAP_TENOR together; a cell cannot be both between two listed expiries and outside them`)
    }
  })
  const quoted_share = need(f, 'quoted_share', at)
  checkCell(quoted_share, 'share', `${at}.quoted_share`)
  // The page shows the file's share and never counts cells, so a share that is not the flags' own would be shown as fact.
  const cells = cell_flags.flat()
  const expected = cells.filter((x) => (x & EXTRAPOLATED_BITS) === 0).length / cells.length
  if (Math.abs((quoted_share as number) - expected) > SHARE_ROUNDING) {
    fail(`${at}.quoted_share`, `is ${String(quoted_share)} but ${expected.toFixed(6)} of the cells carry no extrapolation flag`)
  }
  checkCrossExpiryNeedsTwo(cell_flags, expiries_used, at)
  const places = tenorPlaces(cell_flags, dte, at)
  const layout = rowLayout(places, dte, expiries_used, at)
  checkIvCeilings(iv, cell_flags, layout, dte, moneyness, at)
  checkStrikeFlagAtEdges(cell_flags, dte, moneyness, at)
  checkStrikeFlagAlongTenor(cell_flags, layout, dte, moneyness, at)
  checkCalendarFlag(cell_flags, places, layout, dte, moneyness, expiries_used, at)
  checkCalendar(iv, dte, moneyness, at)
  // The exporter copies the 30-day, k = 0 cell; the grid has both (parseSurfaceFrames checked). So its ceiling is that
  // cell's (round 3, X2: an extrapolated 30-day ATM cell can read 5.04, and atm_iv_30d with it), and it is that cell
  // exactly: a copy has no rounding.
  const [atmRow, atmCol] = [dte.indexOf(ATM_DTE), moneyness.indexOf(ATM_MONEYNESS)]
  const atm_iv_30d = needPositive(f, 'atm_iv_30d', at, ivCeiling(cell_flags[atmRow][atmCol], atmRow, layout))
  const atmCell = iv[atmRow][atmCol]
  if (atm_iv_30d !== atmCell) {
    fail(`${at}.atm_iv_30d`, `is ${atm_iv_30d} but the grid's ${ATM_DTE}-day, k = ${ATM_MONEYNESS} cell is ${atmCell}`)
  }
  return { date, label, spot, vix_close, expiries_used, iv, cell_flags, quoted_share: quoted_share as number, atm_iv_30d }
}

/** True if MAJOR.MINOR.PATCH `version` is below `min`, comparing the three parts as numbers ("0.10.0" is above "0.3.0"). */
function isOlderThan(version: string, min: string): boolean {
  const a = (SEMVER.exec(version) as RegExpExecArray).slice(1).map(Number)
  const b = (SEMVER.exec(min) as RegExpExecArray).slice(1).map(Number)
  for (let i = 0; i < 3; i++) {
    if (a[i] !== b[i]) return a[i] < b[i]
  }
  return false
}

export function parseSurfaceFrames(raw: unknown): SurfaceFrames {
  const P = SURFACE_FRAMES_DATASET
  const o = asRecord(raw, P)
  const schema_version = needSchemaVersion(o, P)
  if (isOlderThan(schema_version, SURFACE_FRAMES_MIN_VERSION)) {
    fail(`${P}.schema_version`, `"${schema_version}" is older than ${SURFACE_FRAMES_MIN_VERSION}, the version that introduced this file`)
  }
  const generated_at = needTimestamp(o, P)
  const source_commit = needSourceCommit(o, P)
  const run = parseRun(o, P)
  // The source's last quote date cannot be after the day the file was written, the date as generated_at writes it
  // (the exporter writes UTC; end-of-day quotes exist only once their session has closed). The frames are at or
  // before data_last_date (checked below), so none is after the file either.
  const written = generated_at.slice(0, 10)
  if ((run.data_last_date as string) > written) {
    fail(`${P}.run.data_last_date`, `${run.data_last_date} is after ${written}, the date of generated_at: a file cannot hold quotes from after it was written`)
  }
  const units = parseUnits(o, P)
  if (need(o, 'illustrative', P) !== false) {
    fail(`${P}.illustrative`, 'must be false: the Surface page presents these as real surfaces, so a file flagged illustrative is refused')
  }
  const label = needString(o, 'label', P)
  // The page badge names the run's vendor; a label that names another one (or none) describes some other file.
  const vendor = dataSourceName(run.data_source as string)
  if (!label.includes(vendor)) {
    fail(`${P}.label`, `does not name ${vendor}, the vendor of run.data_source "${run.data_source}"`)
  }
  const grid_moneyness = needFiniteArray(o, 'grid_moneyness', P)
  assertStrictlyIncreasing(grid_moneyness, `${P}.grid_moneyness`)
  const grid_dte = needFiniteArray(o, 'grid_dte', P)
  grid_dte.forEach((d, i) => {
    if (!Number.isInteger(d) || d <= 0) fail(`${P}.grid_dte[${i}]`, `expected a whole number of days above 0, got ${d}`)
  })
  assertStrictlyIncreasing(grid_dte, `${P}.grid_dte`)
  // atm_iv_30d is read off the grid, so the grid must have the row and the column it is read from.
  if (!grid_dte.includes(ATM_DTE)) fail(`${P}.grid_dte`, `has no ${ATM_DTE}-day row, which atm_iv_30d is read from`)
  if (!grid_moneyness.includes(ATM_MONEYNESS)) fail(`${P}.grid_moneyness`, `has no k = ${ATM_MONEYNESS} column, which atm_iv_30d is read from`)
  const cell_flag_names = needStrings(o, 'cell_flag_names', P)
  if (
    cell_flag_names.length !== SURFACE_CELL_FLAG_NAMES.length ||
    cell_flag_names.some((name, i) => name !== SURFACE_CELL_FLAG_NAMES[i])
  ) {
    fail(`${P}.cell_flag_names`, `expected ${SURFACE_CELL_FLAG_NAMES.join(', ')} in bit order, got ${cell_flag_names.join(', ')}`)
  }
  const list = needArray(o, 'frames', P)
  if (list.length === 0) fail(`${P}.frames`, 'needs at least 1 frame')
  const frames = list.map((item, i) => parseFrame(item, `${P}.frames[${i}]`, grid_dte, grid_moneyness))
  frames.forEach((frame, i) => {
    if (i > 0 && !(frame.date > frames[i - 1].date)) {
      fail(`${P}.frames[${i}].date`, `frames must be in strictly increasing date order, but ${frame.date} follows ${frames[i - 1].date}`)
    }
    if (frame.date > (run.data_last_date as string)) {
      fail(`${P}.frames[${i}].date`, `${frame.date} is after run.data_last_date ${run.data_last_date}, the last quote date the source has`)
    }
  })
  // The run's sample is the span of its frames: a run that names other dates describes another file.
  if (run.sample_start !== frames[0].date || run.sample_end !== frames[frames.length - 1].date) {
    fail(`${P}.run`, `samples ${run.sample_start} to ${run.sample_end} but the frames run from ${frames[0].date} to ${frames[frames.length - 1].date}`)
  }
  return { schema_version, generated_at, source_commit, run, units, illustrative: false, label, grid_moneyness, grid_dte, cell_flag_names, frames }
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
