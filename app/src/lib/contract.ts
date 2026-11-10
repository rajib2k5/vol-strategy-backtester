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

/** The `units` block of a results dataset: every key of `keys`, each exactly the string `expected` gives. Unknown extra keys are dropped. */
function needUnits<K extends string>(o: Record<string, unknown>, path: string, keys: readonly K[], expected: Record<K, string>): Record<K, string> {
  const at = `${path}.units`
  const raw = asRecord(need(o, 'units', path), at)
  const units = {} as Record<K, string>
  for (const key of keys) {
    const unit = needString(raw, key, at)
    if (unit !== expected[key]) fail(`${at}.${key}`, `"${unit}" is not the exporter's unit for ${key}, "${expected[key]}"`)
    units[key] = unit
  }
  return units
}

function parseUnits(o: Record<string, unknown>, path: string): SurfaceFrames['units'] {
  return needUnits(o, path, SURFACE_UNIT_KEYS, SURFACE_UNITS)
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

// ---------------------------------------------------------------- engine datasets (milestone 3)

/*
 * blotter.json and positions_timeline.json are two views of one engine run's ledger: every fill and expiry event,
 * and when each position was open. They carry what the engine did, never how well it did: no P&L, NAV, return or
 * Sharpe is in either file, and the app computes none (ADR-0001 §6). The checks below are the dataset spec's, one
 * for one; where the spec is silent the parser is silent too, except where its own sentence needs a value to exist.
 */

/** The dataset the Blotter page reads: every fill and every expiry or exercise event of one engine run. */
export const BLOTTER_DATASET = 'blotter'

/** The dataset the Positions page reads: when each position was open, and how many were open at each close. */
export const POSITIONS_TIMELINE_DATASET = 'positions_timeline'

/** The first schema_version that has a blotter or positions_timeline file; an older file cannot be one. */
export const ENGINE_DATASETS_MIN_VERSION = '0.4.0'

/** The run block of an engine run, in the order the exporter writes it (ADR-0001 §5; the engine's run record, not the pricing build's RUN_KEYS). */
export const ENGINE_RUN_KEYS = [
  'run_id',
  'config_hash',
  'data_fingerprint',
  'engine_commit',
  'data_source',
  'execution_mode',
  'fill_timing',
  'cap_mode',
  'chain_mask',
  'split',
  'run_purpose',
  'strategy',
  'status',
  'sample_start',
  'sample_end',
] as const

export const EXECUTION_MODES = ['quote', 'surface'] as const
export const FILL_TIMINGS = ['next_close', 'same_close'] as const
export const CAP_MODES = ['hard_only', 'volume'] as const
/** The only chain mask a run can name so far. */
export const CHAIN_MASKS = ['none'] as const
export const SPLITS = ['development', 'validation', 'holdout'] as const
export const RUN_PURPOSES = ['trial', 'diagnostic'] as const
export const RUN_STATUSES = ['ok', 'ruin'] as const

export const FILL_INSTRUMENTS = ['option', 'share'] as const
/** Where an option fill's price came from; a share fill is always the SPY `close`. */
export const OPTION_FILL_SOURCES = ['quote', 'surface'] as const
export const SHARE_FILL_SOURCE = 'close'
export const FILL_INTENTS = ['open', 'close', 'reduce_risk', 'margin_liquidation', 'share_liquidation'] as const
/** The one intent a share fill has, and the one an option fill never has. */
export const SHARE_FILL_INTENT = 'share_liquidation'

export const EVENT_TYPES = ['expired_worthless', 'exercised', 'assigned', 'early_exercised', 'early_assigned'] as const
/** The events that book on the next session and settle at the strike, so they have no settlement price. */
export const EARLY_EVENT_TYPES: readonly string[] = ['early_exercised', 'early_assigned']
/** ADR-0003: a settlement within this many cents of the strike is a pin. */
const PIN_BAND_CENTS = 50
/** Shares in one option contract. */
export const SHARES_PER_CONTRACT = 100

// One array literal on one line: a Python contract test parses it and compares it, as a set, with the engine's exit reasons.
export const EXIT_REASONS = ['dte', 'expiry', 'assignment', 'exercise', 'signal', 'profit_target', 'stop', 'risk', 'margin', 'ruin'] as const

// Mirrors volbt.engine.settlement.NON_SESSION_EXPIRIES (a contract test keeps them equal; ADR-0003 D16): an expiry that was not
// a session settles at the close of the session before it. One object literal, which that test parses.
export const NON_SESSION_EXPIRIES: Readonly<Record<string, string>> = { '2015-12-19': '2015-12-18', '2018-12-05': '2018-12-04' }

export type ExecutionMode = (typeof EXECUTION_MODES)[number]
export type FillTiming = (typeof FILL_TIMINGS)[number]
export type CapMode = (typeof CAP_MODES)[number]
export type Split = (typeof SPLITS)[number]
export type RunPurpose = (typeof RUN_PURPOSES)[number]
export type RunStatus = (typeof RUN_STATUSES)[number]
export type FillInstrument = (typeof FILL_INSTRUMENTS)[number]
export type FillSource = (typeof OPTION_FILL_SOURCES)[number] | typeof SHARE_FILL_SOURCE
export type FillIntent = (typeof FILL_INTENTS)[number]
export type EventType = (typeof EVENT_TYPES)[number]
export type ExitReason = (typeof EXIT_REASONS)[number]

/** The number fields of blotter.json, each with a unit in `units` so the page never guesses one. */
export const BLOTTER_UNIT_KEYS = ['qty', 'price', 'mid', 'half_spread', 'fees', 'strike', 'settlement_price', 'shares_delivered'] as const

/** The unit of each, exactly as tools/export_app_data.py writes it: any other string is refused, as SURFACE_UNITS does. */
export const BLOTTER_UNITS: Record<(typeof BLOTTER_UNIT_KEYS)[number], string> = {
  qty: 'contracts (options) or shares (SPY), signed: + bought, - sold',
  price: 'USD per share',
  mid: 'USD per share',
  half_spread: 'USD per share',
  fees: 'USD',
  strike: 'USD per share',
  settlement_price: 'USD per share',
  shares_delivered: 'shares, signed: + received, - delivered',
}

/** The number fields of positions_timeline.json. */
export const POSITIONS_TIMELINE_UNIT_KEYS = ['open_count', 'ratio'] as const

export const POSITIONS_TIMELINE_UNITS: Record<(typeof POSITIONS_TIMELINE_UNIT_KEYS)[number], string> = {
  open_count: "positions open at the session's close",
  ratio: 'contracts per package, signed: + long, - short',
}

export interface EngineRunBlock {
  /** SHA-256 hex of config_hash, data_fingerprint and engine_commit. */
  run_id: string
  /** SHA-256, 64 lowercase hex digits. */
  config_hash: string
  /** SHA-256, 64 lowercase hex digits. */
  data_fingerprint: string
  /** 40 hex digits of the commit the run was made from, then "-dirty" if the tree had uncommitted changes. */
  engine_commit: string
  data_source: DataSource
  execution_mode: ExecutionMode
  fill_timing: FillTiming
  cap_mode: CapMode
  chain_mask: (typeof CHAIN_MASKS)[number]
  split: Split
  run_purpose: RunPurpose
  strategy: string
  status: RunStatus
  /** YYYY-MM-DD. */
  sample_start: string
  /** YYYY-MM-DD, not before sample_start. */
  sample_end: string
}

export interface Fill {
  /** From 1, strictly increasing along the file. */
  fill_id: number
  /** The session the fill was booked on: a weekday inside the run's sample, not before the fill above, and on or before the contract's expiry (option). */
  date: string
  instrument: FillInstrument
  /** The 21-character OSI symbol of an option fill; null for a share fill. */
  osi_symbol: string | null
  /** Contracts (option) or shares (SPY), signed: + bought, - sold. Never 0. */
  qty: number
  /** USD per share, 4 decimals; an option fill's is a whole number of cents (ADR-0002 §2). */
  price: number
  /** USD per share; null for a share fill. */
  mid: number | null
  /** USD per share; null for a share fill. */
  half_spread: number | null
  /** USD, 2 decimals. */
  fees: number
  fill_source: FillSource
  intent: FillIntent
}

export interface ExpiryEvent {
  /** From 1, strictly increasing along the file. */
  event_id: number
  /** The session the event was decided or settled on: on or before the contract's expiry; a settlement event is on the contract's settle date. */
  date: string
  /** The session it books on: `date`, or the next session for an early event. Never after the contract's expiry. */
  effective_date: string
  osi_symbol: string
  event_type: EventType
  /** Signed lot quantity: + long, - short. Never 0. */
  contracts: number
  /** Signed: + received, - delivered. 0 for expired_worthless, else 100 per contract. */
  shares_delivered: number
  /** The OSI symbol's strike. */
  strike: number
  /** null for an early event: it settles at the strike, not a close. Otherwise the event type agrees with it: ITM by a cent or more exactly when not expired_worthless (ADR-0003). */
  settlement_price: number | null
  /** True only for a short lot settled within the pin band (50 cents) of the strike (ADR-0003). */
  pin_flag: boolean
}

export interface Blotter {
  schema_version: string
  generated_at: string
  source_commit: string
  run: EngineRunBlock
  units: Record<(typeof BLOTTER_UNIT_KEYS)[number], string>
  illustrative: false
  label: string
  fills: Fill[]
  events: ExpiryEvent[]
}

export interface PositionLeg {
  osi_symbol: string
  /** Contracts per package, signed: + long, - short. Never 0. */
  ratio: number
}

export interface Position {
  /** From 1, strictly increasing along the file. */
  position_id: number
  /** E.g. "short_straddle". */
  structure: string
  opened: string
  /** Not before `opened`; null while the position is open at sample_end, or when the run ended in ruin. */
  closed: string | null
  legs: PositionLeg[]
  /** null exactly while closed is null in a run that did not end in ruin. "expiry" only for a position closed on or after its earliest settle date. */
  exit_reason: ExitReason | null
}

export interface PositionsTimeline {
  schema_version: string
  generated_at: string
  source_commit: string
  run: EngineRunBlock
  units: Record<(typeof POSITIONS_TIMELINE_UNIT_KEYS)[number], string>
  illustrative: false
  label: string
  positions: Position[]
  /** The run's sessions (weekdays), strictly increasing. */
  dates: string[]
  /** Positions open at each session's close (opened on or before it, not yet closed); same length as `dates`, and checked against `positions`. */
  open_count: number[]
}

/** The commit the run was made from: a full SHA-1 in hex, then "-dirty" if the working tree had changes. */
const ENGINE_COMMIT = /^[0-9a-f]{40}(?:-dirty)?$/

/** A 21-character OSI option symbol: the root padded to 6 characters, YYMMDD, C or P, and the strike times 1000 as 8 digits. */
const OSI_SYMBOL = /^[A-Z0-9 ]{6}\d{6}[CP]\d{8}$/

function quotedList(allowed: readonly string[]): string {
  return allowed.map((a) => `"${a}"`).join(', ')
}

/** `v` as one of `allowed`, or a failure at `at` that lists them. */
function checkOneOf<T extends string>(v: unknown, at: string, allowed: readonly T[]): T {
  if (typeof v !== 'string' || !(allowed as readonly string[]).includes(v)) fail(at, `expected one of ${quotedList(allowed)}, got ${JSON.stringify(v)}`)
  return v as T
}

function needOneOf<T extends string>(obj: Record<string, unknown>, key: string, path: string, allowed: readonly T[]): T {
  return checkOneOf(need(obj, key, path), `${path}.${key}`, allowed)
}

/** A whole number of at least `min`. */
function checkInteger(v: unknown, at: string, min: number): number {
  if (typeof v !== 'number' || !Number.isInteger(v) || v < min) fail(at, `expected a whole number of at least ${min}, got ${String(v)}`)
  return v
}

function needInteger(obj: Record<string, unknown>, key: string, path: string, min: number): number {
  return checkInteger(need(obj, key, path), `${path}.${key}`, min)
}

/** A whole number other than 0: a quantity or a ratio has a sign and a size. */
function needNonZeroInteger(obj: Record<string, unknown>, key: string, path: string): number {
  const v = need(obj, key, path)
  if (typeof v !== 'number' || !Number.isInteger(v) || v === 0) fail(`${path}.${key}`, `expected a whole number other than 0, got ${String(v)}`)
  return v
}

/** A finite number above 0. */
function needPositiveNumber(obj: Record<string, unknown>, key: string, path: string): number {
  const v = need(obj, key, path)
  if (typeof v !== 'number' || !Number.isFinite(v) || v <= 0) fail(`${path}.${key}`, `expected a number above 0, got ${String(v)}`)
  return v
}

/** A finite number of at least 0. */
function checkNonNegative(v: unknown, at: string): number {
  if (typeof v !== 'number' || !Number.isFinite(v) || v < 0) fail(at, `expected a number of at least 0, got ${String(v)}`)
  return v
}

function needNonNegativeNumber(obj: Record<string, unknown>, key: string, path: string): number {
  return checkNonNegative(need(obj, key, path), `${path}.${key}`)
}

/** An option fill carries the number; a share fill, which has no quote, carries null. */
function needNumberForOptionOnly(f: Record<string, unknown>, key: string, at: string, isOption: boolean): number | null {
  const v = need(f, key, at)
  if (isOption) return checkNonNegative(v, `${at}.${key}`)
  if (v !== null) fail(`${at}.${key}`, `a share fill has no quote, so this must be null, got ${String(v)}`)
  return null
}

function needOsiSymbol(obj: Record<string, unknown>, key: string, path: string): string {
  const v = need(obj, key, path)
  if (typeof v !== 'string' || !OSI_SYMBOL.test(v)) {
    fail(`${path}.${key}`, `${JSON.stringify(v)} is not a 21-character OSI symbol (root padded to 6, YYMMDD, C or P, strike x 1000 as 8 digits)`)
  }
  return v
}

/** The expiry date of an OSI symbol: its YYMMDD, in the 2000s. */
function osiExpiry(osi: string): string {
  return `20${osi.slice(6, 8)}-${osi.slice(8, 10)}-${osi.slice(10, 12)}`
}

/** The session a contract settles on: its expiry, or the session before when the expiry was not one (ADR-0003 D16). */
function osiSettleDate(osi: string): string {
  const expiry = osiExpiry(osi)
  return NON_SESSION_EXPIRIES[expiry] ?? expiry
}

/** The strike an OSI symbol names: the last 8 digits over 1000. */
function osiStrike(osi: string): number {
  return Number(osi.slice(13, 21)) / 1000
}

/** `date` must not be after the contract's expiry. */
function assertNotAfterExpiry(date: string, osi: string, at: string, what: string): void {
  const expiry = osiExpiry(osi)
  if (date > expiry) fail(at, `${date} is after the expiry ${expiry} of ${JSON.stringify(osi)}: ${what}`)
}

function assertWeekday(date: string, at: string): void {
  const weekday = new Date(`${date}T00:00:00Z`).getUTCDay()
  if (weekday === 0 || weekday === 6) fail(at, `${date} is a ${weekday === 0 ? 'Sunday' : 'Saturday'}: a session is a weekday`)
}

/** A YYYY-MM-DD date that exists and is a weekday: the app has no exchange calendar, so a weekday is the proxy for a session (a holiday on a weekday is not caught). */
function needSession(obj: Record<string, unknown>, key: string, path: string): string {
  const v = needDate(obj, key, path)
  assertWeekday(v, `${path}.${key}`)
  return v
}

/** A session inside the run's sample (both ends included). */
function needSessionInSample(obj: Record<string, unknown>, key: string, path: string, run: EngineRunBlock): string {
  const v = needSession(obj, key, path)
  if (v < run.sample_start || v > run.sample_end) fail(`${path}.${key}`, `${v} is outside the run's sample ${run.sample_start} to ${run.sample_end}`)
  return v
}

function needHex(obj: Record<string, unknown>, key: string, path: string): string {
  const v = needString(obj, key, path)
  if (!SHA256_HEX.test(v)) fail(`${path}.${key}`, `"${v}" is not a SHA-256 (64 lowercase hex digits)`)
  return v
}

/** How each run key is read: the same set of keys as ENGINE_RUN_KEYS, so a key added to the list without a reader does not compile. */
const ENGINE_RUN_READERS: Record<(typeof ENGINE_RUN_KEYS)[number], (obj: Record<string, unknown>, key: string, at: string) => string> = {
  run_id: needHex,
  config_hash: needHex,
  data_fingerprint: needHex,
  engine_commit: (obj, key, at) => {
    const v = needString(obj, key, at)
    if (!ENGINE_COMMIT.test(v)) fail(`${at}.${key}`, `"${v}" is not 40 lowercase hex digits, optionally followed by -dirty`)
    return v
  },
  data_source: (obj, key, at) => {
    const v = needString(obj, key, at)
    if (!isDataSource(v)) fail(`${at}.${key}`, `"${v}" is not a known data source (${Object.keys(DATA_SOURCE_NAMES).join(', ')})`)
    return v
  },
  execution_mode: (obj, key, at) => needOneOf(obj, key, at, EXECUTION_MODES),
  fill_timing: (obj, key, at) => needOneOf(obj, key, at, FILL_TIMINGS),
  cap_mode: (obj, key, at) => needOneOf(obj, key, at, CAP_MODES),
  chain_mask: (obj, key, at) => needOneOf(obj, key, at, CHAIN_MASKS),
  split: (obj, key, at) => needOneOf(obj, key, at, SPLITS),
  run_purpose: (obj, key, at) => needOneOf(obj, key, at, RUN_PURPOSES),
  strategy: needString,
  status: (obj, key, at) => needOneOf(obj, key, at, RUN_STATUSES),
  sample_start: needDate,
  sample_end: needDate,
}

/** The fifteen run keys of an engine run, in ENGINE_RUN_KEYS order. Unknown extra keys are dropped, as everywhere in this contract. */
function parseEngineRun(o: Record<string, unknown>, path: string): EngineRunBlock {
  const at = `${path}.run`
  const raw = asRecord(need(o, 'run', path), at)
  const run: Record<string, string> = {}
  for (const key of ENGINE_RUN_KEYS) run[key] = ENGINE_RUN_READERS[key](raw, key, at)
  if (run.sample_end < run.sample_start) fail(`${at}.sample_end`, `${run.sample_end} is before sample_start ${run.sample_start}`)
  return run as unknown as EngineRunBlock
}

/** The blocks both engine datasets open with, after the envelope: run, units, illustrative and label. */
function parseEngineHeader<K extends string>(
  o: Record<string, unknown>,
  P: string,
  unitKeys: readonly K[],
  unitTable: Record<K, string>,
): { schema_version: string; generated_at: string; source_commit: string; run: EngineRunBlock; units: Record<K, string>; label: string } {
  const schema_version = needSchemaVersion(o, P)
  if (isOlderThan(schema_version, ENGINE_DATASETS_MIN_VERSION)) {
    fail(`${P}.schema_version`, `"${schema_version}" is older than ${ENGINE_DATASETS_MIN_VERSION}, the version that introduced this file`)
  }
  const generated_at = needTimestamp(o, P)
  const source_commit = needSourceCommit(o, P)
  const run = parseEngineRun(o, P)
  const units = needUnits(o, P, unitKeys, unitTable)
  if (need(o, 'illustrative', P) !== false) {
    fail(`${P}.illustrative`, 'must be false: these are the records of an engine run, so a file flagged illustrative is refused')
  }
  const label = needString(o, 'label', P)
  return { schema_version, generated_at, source_commit, run, units, label }
}

function parseFill(raw: unknown, at: string, run: EngineRunBlock): Fill {
  const f = asRecord(raw, at)
  const fill_id = needInteger(f, 'fill_id', at, 1)
  const date = needSessionInSample(f, 'date', at, run)
  const instrument = needOneOf(f, 'instrument', at, FILL_INSTRUMENTS)
  const isOption = instrument === 'option'
  let osi_symbol: string | null = null
  if (isOption) {
    osi_symbol = needOsiSymbol(f, 'osi_symbol', at)
  } else if (need(f, 'osi_symbol', at) !== null) {
    fail(`${at}.osi_symbol`, 'a share fill has no OSI symbol, so this must be null')
  }
  const qty = needNonZeroInteger(f, 'qty', at)
  const price = needPositiveNumber(f, 'price', at)
  // ADR-0002 §2: the engine rounds an option fill to whole cents.
  if (isOption && Math.abs(price * 100 - Math.round(price * 100)) > 1e-9) {
    fail(`${at}.price`, `${price} is not a whole number of cents (ADR-0002 §2)`)
  }
  const mid = needNumberForOptionOnly(f, 'mid', at, isOption)
  const half_spread = needNumberForOptionOnly(f, 'half_spread', at, isOption)
  const fees = needNonNegativeNumber(f, 'fees', at)
  const fill_source = isOption ? needOneOf(f, 'fill_source', at, OPTION_FILL_SOURCES) : needOneOf(f, 'fill_source', at, [SHARE_FILL_SOURCE] as const)
  const intent = needOneOf(f, 'intent', at, FILL_INTENTS)
  if (isOption && intent === SHARE_FILL_INTENT) {
    fail(`${at}.intent`, `an option fill never has the intent "${SHARE_FILL_INTENT}"`)
  }
  if (!isOption && intent !== SHARE_FILL_INTENT) {
    fail(`${at}.intent`, `a share fill has the intent "${SHARE_FILL_INTENT}", got "${intent}"`)
  }
  if (osi_symbol !== null) assertNotAfterExpiry(date, osi_symbol, `${at}.date`, 'a contract is not traded after it expires')
  return { fill_id, date, instrument, osi_symbol, qty, price, mid, half_spread, fees, fill_source, intent }
}

function parseEvent(raw: unknown, at: string, run: EngineRunBlock): ExpiryEvent {
  const e = asRecord(raw, at)
  const event_id = needInteger(e, 'event_id', at, 1)
  const date = needSessionInSample(e, 'date', at, run)
  // An early event books on the next session, so the effective date is after the decision, never before it; it may fall past the sample's end.
  const effective_date = needSession(e, 'effective_date', at)
  if (effective_date < date) fail(`${at}.effective_date`, `${effective_date} is before date ${date}`)
  const osi_symbol = needOsiSymbol(e, 'osi_symbol', at)
  const event_type = needOneOf(e, 'event_type', at, EVENT_TYPES)
  const contracts = needNonZeroInteger(e, 'contracts', at)
  const shares_delivered = need(e, 'shares_delivered', at)
  if (typeof shares_delivered !== 'number' || !Number.isInteger(shares_delivered)) {
    fail(`${at}.shares_delivered`, `expected a whole number, got ${String(shares_delivered)}`)
  }
  // ADR-0003's delivery table, checked, not computed for display: we exercise longs and are assigned on shorts, and a
  // call delivers +100 shares a contract held (a put -100), so the sign follows the right and the side. (M3 review: a
  // long lot "assigned", or a delivery of the wrong sign, was accepted.)
  if ((event_type === 'assigned' || event_type === 'early_assigned') && contracts > 0) {
    fail(`${at}.contracts`, `is ${contracts} but only a short lot (contracts < 0) is assigned`)
  }
  if ((event_type === 'exercised' || event_type === 'early_exercised') && contracts < 0) {
    fail(`${at}.contracts`, `is ${contracts} but only a long lot (contracts > 0) is exercised`)
  }
  if (event_type === 'expired_worthless') {
    if (shares_delivered !== 0) fail(`${at}.shares_delivered`, `is ${shares_delivered} but an option that expired worthless delivers no shares`)
  } else {
    const perContract = osi_symbol.charAt(12) === 'C' ? SHARES_PER_CONTRACT : -SHARES_PER_CONTRACT
    if (shares_delivered !== perContract * contracts) {
      fail(`${at}.shares_delivered`, `is ${shares_delivered} but ${contracts} contract(s) of a ${osi_symbol.charAt(12) === 'C' ? 'call' : 'put'} deliver ${perContract * contracts} shares (ADR-0003's delivery table)`)
    }
  }
  assertNotAfterExpiry(date, osi_symbol, `${at}.date`, 'an event is not decided after the contract expires')
  assertNotAfterExpiry(effective_date, osi_symbol, `${at}.effective_date`, 'an event does not book after the contract expires')
  const strike = needPositiveNumber(e, 'strike', at)
  // Whole cents, the test the fill price uses, before any comparison in cents: Math.round and Python's round part
  // ways on a half cent (M3 round-3 review: K = 450.125 against S = 450.13).
  if (Math.abs(strike * 100 - Math.round(strike * 100)) > 1e-9) {
    fail(`${at}.strike`, `${strike} is not a whole number of cents`)
  }
  if (Math.abs(strike - osiStrike(osi_symbol)) > 1e-9) {
    fail(`${at}.strike`, `is ${strike} but the OSI symbol ${JSON.stringify(osi_symbol)} names the strike ${osiStrike(osi_symbol)}`)
  }
  const settlement = need(e, 'settlement_price', at)
  let settlement_price: number | null = null
  if (EARLY_EVENT_TYPES.includes(event_type)) {
    if (settlement !== null) fail(`${at}.settlement_price`, `an early event settles at the strike, not a close, so this must be null, got ${String(settlement)}`)
  } else {
    settlement_price = needPositiveNumber(e, 'settlement_price', at)
    if (Math.abs(settlement_price * 100 - Math.round(settlement_price * 100)) > 1e-9) {
      fail(`${at}.settlement_price`, `${settlement_price} is not a whole number of cents (S_set is the unadjusted close)`)
    }
  }
  if (!EARLY_EVENT_TYPES.includes(event_type)) {
    const settleDate = osiSettleDate(osi_symbol)
    if (date !== settleDate) fail(`${at}.date`, `is ${date} but a settlement event is on the contract's settle date ${settleDate}`)
    if (effective_date !== date) fail(`${at}.effective_date`, `is ${effective_date} but a settlement event books on its own date ${date}`)
  }
  const pin_flag = needBoolean(e, 'pin_flag', at)
  // ADR-0003: whether the contract finished in the money, in whole cents, and the one-cent rule; and the pin band.
  if (settlement_price !== null) {
    const settleCents = Math.round(settlement_price * 100)
    const strikeCents = Math.round(strike * 100)
    const isCall = osi_symbol.charAt(12) === 'C'
    const itm = isCall ? settleCents - strikeCents >= 1 : strikeCents - settleCents >= 1
    if (itm !== (event_type !== 'expired_worthless')) {
      fail(
        `${at}.event_type`,
        `is "${event_type}" but the ${isCall ? 'call' : 'put'} struck at ${strike} settled at ${settlement_price}, which is ${itm ? 'in' : 'not in'} the money by a cent or more (ADR-0003)`,
      )
    }
    // The engine's rule, both ways (settlement.settle_lot): a short lot settling within the band is pinned, and
    // nothing else is. (M3 round-3 review: a short lot inside the band with pin_flag false was accepted.)
    const pinned = contracts < 0 && Math.abs(settleCents - strikeCents) <= PIN_BAND_CENTS
    if (pin_flag !== pinned) {
      fail(
        `${at}.pin_flag`,
        `is ${pin_flag} but the ${contracts < 0 ? 'short' : 'long'} lot (contracts ${contracts}) settled at ${settlement_price}, ${Math.abs(settleCents - strikeCents)} cents from the strike ${strike}: only a short lot within ${PIN_BAND_CENTS} cents is pinned (ADR-0003's pin band)`,
      )
    }
  }
  if (pin_flag && settlement_price === null) fail(`${at}.pin_flag`, 'is true but an early event has no settlement price to pin to')
  return { event_id, date, effective_date, osi_symbol, event_type, contracts, shares_delivered, strike, settlement_price, pin_flag }
}

/** Entries of `list` with `id` strictly increasing (and, where `dateOf` is given, the date not before the one above it). */
function assertOrdered<T>(list: T[], at: string, idKey: string, idOf: (x: T) => number, dateOf?: (x: T) => string): void {
  list.forEach((item, i) => {
    if (i === 0) return
    const before = list[i - 1]
    if (!(idOf(item) > idOf(before))) fail(`${at}[${i}].${idKey}`, `must be strictly increasing, but ${idOf(item)} follows ${idOf(before)}`)
    if (dateOf !== undefined && dateOf(item) < dateOf(before)) {
      fail(`${at}[${i}].date`, `must not go back in time, but ${dateOf(item)} follows ${dateOf(before)}`)
    }
  })
}

/**
 * Every intent but `open` (and the share fills' `share_liquidation`) only reduces a position. Walking the option fills in
 * file order, a reduce-only fill may not close more long (or short) contracts of a symbol than the earlier `open` fills
 * bought (or sold). Events are ignored: they only remove contracts, so ignoring them never refuses a valid file.
 */
function assertReduceOnlyFillsHaveSomethingToReduce(fills: Fill[], at: string): void {
  const book = new Map<string, { openedLong: number; openedShort: number; closedLong: number; closedShort: number }>()
  fills.forEach((fill, i) => {
    if (fill.osi_symbol === null) return
    let row = book.get(fill.osi_symbol)
    if (row === undefined) {
      row = { openedLong: 0, openedShort: 0, closedLong: 0, closedShort: 0 }
      book.set(fill.osi_symbol, row)
    }
    if (fill.intent === 'open') {
      if (fill.qty > 0) row.openedLong += fill.qty
      else row.openedShort -= fill.qty
      return
    }
    // Reduce-only: a sale reduces a long, a purchase reduces a short.
    if (fill.qty < 0) row.closedLong -= fill.qty
    else row.closedShort += fill.qty
    if (row.closedLong > row.openedLong || row.closedShort > row.openedShort) {
      fail(
        `${at}[${i}].intent`,
        `is "${fill.intent}" (reduce-only) but ${fill.qty} of ${JSON.stringify(fill.osi_symbol)} reduces more ${fill.qty < 0 ? 'long' : 'short'} contracts than the fills before it opened`,
      )
    }
  })
}

export function parseBlotter(raw: unknown): Blotter {
  const P = BLOTTER_DATASET
  const o = asRecord(raw, P)
  const { schema_version, generated_at, source_commit, run, units, label } = parseEngineHeader(o, P, BLOTTER_UNIT_KEYS, BLOTTER_UNITS)
  const fills = needArray(o, 'fills', P).map((item, i) => parseFill(item, `${P}.fills[${i}]`, run))
  assertOrdered(fills, `${P}.fills`, 'fill_id', (x) => x.fill_id, (x) => x.date)
  assertReduceOnlyFillsHaveSomethingToReduce(fills, `${P}.fills`)
  const events = needArray(o, 'events', P).map((item, i) => parseEvent(item, `${P}.events[${i}]`, run))
  assertOrdered(events, `${P}.events`, 'event_id', (x) => x.event_id, (x) => x.date)
  return { schema_version, generated_at, source_commit, run, units, illustrative: false, label, fills, events }
}

function parsePosition(raw: unknown, at: string, run: EngineRunBlock): Position {
  const p = asRecord(raw, at)
  const position_id = needInteger(p, 'position_id', at, 1)
  const structure = needString(p, 'structure', at)
  const opened = needSessionInSample(p, 'opened', at, run)
  let closed: string | null = null
  if (need(p, 'closed', at) !== null) {
    closed = needSessionInSample(p, 'closed', at, run)
    if (closed < opened) fail(`${at}.closed`, `${closed} is before opened ${opened}`)
  }
  const legList = needArray(p, 'legs', at)
  if (legList.length === 0) fail(`${at}.legs`, 'needs at least 1 leg')
  const legs = legList.map((item, i): PositionLeg => {
    const legAt = `${at}.legs[${i}]`
    const leg = asRecord(item, legAt)
    return { osi_symbol: needOsiSymbol(leg, 'osi_symbol', legAt), ratio: needNonZeroInteger(leg, 'ratio', legAt) }
  })
  // A reason exists once the position is closed, or the run ended in ruin; before that the position is simply still open.
  const reason = need(p, 'exit_reason', at)
  let exit_reason: ExitReason | null = null
  if (closed !== null || run.status === 'ruin') {
    exit_reason = checkOneOf(reason, `${at}.exit_reason`, EXIT_REASONS)
  } else if (reason !== null) {
    fail(`${at}.exit_reason`, `is ${JSON.stringify(reason)} but the position is still open in a run that did not end in ruin, so this must be null`)
  }
  if (exit_reason === 'expiry') {
    const earliest = legs.map((l) => osiSettleDate(l.osi_symbol)).reduce((a, b) => (a < b ? a : b))
    if (closed === null) fail(`${at}.exit_reason`, 'is "expiry" but the position has no close date')
    if (closed < earliest) fail(`${at}.exit_reason`, `is "expiry" but the position closed on ${closed}, before its earliest settle date ${earliest}`)
  }
  return { position_id, structure, opened, closed, legs, exit_reason }
}

export function parsePositionsTimeline(raw: unknown): PositionsTimeline {
  const P = POSITIONS_TIMELINE_DATASET
  const o = asRecord(raw, P)
  const { schema_version, generated_at, source_commit, run, units, label } = parseEngineHeader(
    o,
    P,
    POSITIONS_TIMELINE_UNIT_KEYS,
    POSITIONS_TIMELINE_UNITS,
  )
  const positions = needArray(o, 'positions', P).map((item, i) => parsePosition(item, `${P}.positions[${i}]`, run))
  assertOrdered(positions, `${P}.positions`, 'position_id', (x) => x.position_id)
  const rawDates = needArray(o, 'dates', P)
  // The first session is the one the chart starts on, so the list cannot be empty.
  if (rawDates.length === 0) fail(`${P}.dates`, 'needs at least 1 session')
  const dates = rawDates.map((x, i) => {
    const at = `${P}.dates[${i}]`
    if (typeof x !== 'string' || !isRealDate(x)) fail(at, `${JSON.stringify(x)} is not a calendar date YYYY-MM-DD`)
    assertWeekday(x, at)
    return x
  })
  dates.forEach((x, i) => {
    if (i > 0 && !(x > dates[i - 1])) fail(`${P}.dates[${i}]`, `must be strictly increasing, but ${x} follows ${dates[i - 1]}`)
  })
  if (dates[0] < run.sample_start) fail(`${P}.dates[0]`, `${dates[0]} is before the run's sample_start ${run.sample_start}`)
  if (dates[dates.length - 1] > run.sample_end) {
    fail(`${P}.dates[${dates.length - 1}]`, `${dates[dates.length - 1]} is after the run's sample_end ${run.sample_end}`)
  }
  const rawCounts = needArray(o, 'open_count', P)
  if (rawCounts.length !== dates.length) fail(`${P}.open_count`, `has ${rawCounts.length} values but dates has ${dates.length}`)
  const open_count = rawCounts.map((x, i) => checkInteger(x, `${P}.open_count[${i}]`, 0))
  // The engine counts a position as open at a close when it opened on or before that session and has not closed by it.
  open_count.forEach((n, i) => {
    const expected = positions.filter((p) => p.opened <= dates[i] && (p.closed === null || p.closed > dates[i])).length
    if (n !== expected) fail(`${P}.open_count[${i}]`, `is ${n} but ${expected} position(s) are open at the close of ${dates[i]}`)
  })
  return { schema_version, generated_at, source_commit, run, units, illustrative: false, label, positions, dates, open_count }
}

// ---------------------------------------------------------------- strategy datasets (milestone 4)

/*
 * signals_timeline.json and strategy_positions.json (schema 0.5.0) carry the volatility signal of the development split and
 * the positions the strategies opened on it. Neither holds a result: no P&L, return or Sharpe, and no count of positions
 * per exit reason (that count is a result), and the app computes none (ADR-0001 §6). Nothing after 2019 may be shown
 * (decision D19): a file with a date after it, or of another split, is refused.
 */

/** The dataset the Signal page reads: the daily IV30, the HAR forecast of volatility, the log variance ratio and the forecast test. */
export const SIGNALS_TIMELINE_DATASET = 'signals_timeline'

/** The dataset the Strategies page reads: the positions of each strategy run, with the trial count of its group. */
export const STRATEGY_POSITIONS_DATASET = 'strategy_positions'

/** The first schema_version that has a signals_timeline or strategy_positions file; an older file cannot be one. */
export const M4_DATASETS_MIN_VERSION = '0.5.0'

/** The last day of the development split (decision D19): no date of either file, and no run's sample, may be after it. */
export const DEVELOPMENT_LAST_DATE = '2019-12-31'

/** The number fields of signals_timeline.json. */
export const SIGNALS_TIMELINE_UNIT_KEYS = ['iv30', 'rv_forecast', 'rv_realised', 'log_var_ratio', 'n_window', 'coef'] as const

export const SIGNALS_TIMELINE_UNITS: Record<(typeof SIGNALS_TIMELINE_UNIT_KEYS)[number], string> = {
  iv30: 'annualised implied vol, decimal (0.20 = 20%)',
  rv_forecast: 'annualised forecast vol over the next 30 calendar days, decimal',
  rv_realised: 'annualised realised vol over the next 30 calendar days, ex post, decimal',
  log_var_ratio: 'ln(IV30^2 / RV^2), dimensionless',
  n_window: 'sessions in (t, t + 30 calendar days]',
  coef: 'HAR coefficients [constant, daily, weekly, monthly] on daily squared log returns',
}

/** The number fields of strategy_positions.json. */
export const STRATEGY_POSITIONS_UNIT_KEYS = ['ratio', 'entry_signal'] as const

export const STRATEGY_POSITIONS_UNITS: Record<(typeof STRATEGY_POSITIONS_UNIT_KEYS)[number], string> = {
  ratio: 'contracts per package, signed: + long, - short',
  entry_signal: 'ln(IV30^2 / RV^2) at the entry decision, dimensionless',
}

export const RV_MODELS = ['har', 'naive'] as const
export type RvModel = (typeof RV_MODELS)[number]

/** The bits of a signals_timeline `flags` value, bit 0 first. */
export const SIGNAL_FLAG_NAMES = ['RV_FALLBACK', 'RV_MISSING', 'IV30_MISSING', 'WINDOW_EMPTY'] as const

/** The signal's fixed parameters, as the exporter writes them (the file names them; a file with others is not this signal). */
export const SIGNAL_PARAMS = { window_days: 30, horizon: 21, min_pairs: 504 } as const

/** The entry and exit levels of the log variance ratio, as the exporter writes them. The page draws them; it derives only theta - exit_band for a line's position. */
export const SIGNAL_THRESHOLDS = { short_entry: [0, 0.4], long_entry: 0, exit_band: 0.4 } as const

/** The structures a strategy position can have. */
export const STRATEGY_STRUCTURES = ['short_straddle', 'long_straddle', 'short_strangle', 'straddle_calendar'] as const
export type StrategyStructure = (typeof STRATEGY_STRUCTURES)[number]

/** The forecast test's shortest honest label: the test is a proxy for how the signal would have done, not a result. */
const FORECAST_LABEL_PREFIX = 'proxy'

export interface SignalSpec {
  name: string
  rv_model: RvModel
  window_days: 30
  horizon: 21
  min_pairs: 504
}

export interface HarFit {
  fit_date: string
  /** [constant, daily, weekly, monthly]. */
  coef: number[]
  /** At least 504. */
  n_pairs: number
}

export interface ForecastTest {
  prereg_id: string
  /** SHA-256, 64 lowercase hex digits. */
  prereg_sha256: string
  window: string
  k: 1
  n: number
  q: number
  block: number
  draws: number
  mean_d: number
  ewc_t: number
  se: number
  p: number
  p_holm: number
  ci: [number, number]
  alpha: number
  /** The registered decision threshold: the test chooses the forecast model when p is below it. Equal to alpha. */
  threshold: number
  worst_simulated_size: number
  /** Simulated sizes of the test: the ABC-weighted size per seed and the worst matched size per seed, each in [0, 1]. Each ABC-weighted size is at most the worst matched size of its seed. */
  effective_size: {
    /** The threshold the sizes were simulated at, in (0, 1); equal to the test's threshold. */
    threshold: number
    abc_size_battery_seed: number
    abc_size_second_seed: number
    worst_matched_battery_seed: { rate: number; null_side: string }
    worst_matched_second_seed: { rate: number; null_side: string }
  }
  /** The pre-registered fragile band [lo, hi) of p, two numbers in (0, 1) with lo < hi. */
  fragile_band: [number, number]
  /** True exactly when lo <= p < hi: the decision then rests on modelling choices. */
  fragile: boolean
  decision: RvModel
  /** Starts with "proxy". */
  label: string
}

export interface SignalsTimeline {
  schema_version: string
  generated_at: string
  source_commit: string
  run: EngineRunBlock
  units: Record<(typeof SIGNALS_TIMELINE_UNIT_KEYS)[number], string>
  illustrative: false
  label: string
  signal: SignalSpec
  thresholds: { short_entry: [number, number]; long_entry: number; exit_band: number }
  /** Strictly increasing, inside the run's sample, none after 2019-12-31. */
  dates: string[]
  /** Each of the four series has one entry per date; null where the value is missing. */
  iv30: (number | null)[]
  rv_forecast: (number | null)[]
  /** Ex post: null where the 30-day window ends after 2019-12-31. */
  rv_realised: (number | null)[]
  log_var_ratio: (number | null)[]
  /** The fit (a fits[].fit_date) behind each date's forecast; null for the naive model or where there is no forecast. */
  model_fit_date: (string | null)[]
  n_window: number[]
  flags: number[]
  flag_names: string[]
  fits: HarFit[]
  /** null while the test has not been scored. */
  forecast_test: ForecastTest | null
}

export interface StrategyPosition extends Position {
  structure: StrategyStructure
  /** ln(IV30^2 / RV^2) at the entry decision; null when there was none. */
  entry_signal: number | null
}

export interface StrategyRun {
  run: EngineRunBlock
  strategy: string
  /** Shown as key/value text, never interpreted. */
  params: Record<string, unknown>
  trial_group: string
  n_trials_group: number
  positions: StrategyPosition[]
}

export interface StrategyPositions {
  schema_version: string
  generated_at: string
  source_commit: string
  units: Record<(typeof STRATEGY_POSITIONS_UNIT_KEYS)[number], string>
  illustrative: false
  label: string
  /** Shown as written, first on the Strategies page. */
  banner: string
  runs: StrategyRun[]
}

/** The envelope both M4 datasets open with: a version that has the file, a timestamp and a source commit. */
function parseM4Envelope(o: Record<string, unknown>, P: string): { schema_version: string; generated_at: string; source_commit: string } {
  const schema_version = needSchemaVersion(o, P)
  if (isOlderThan(schema_version, M4_DATASETS_MIN_VERSION)) {
    fail(`${P}.schema_version`, `"${schema_version}" is older than ${M4_DATASETS_MIN_VERSION}, the version that introduced this file`)
  }
  return { schema_version, generated_at: needTimestamp(o, P), source_commit: needSourceCommit(o, P) }
}

/** An engine run block of the development split (decision D19): another split, or a sample ending after 2019, is refused. */
function parseDevelopmentRun(o: Record<string, unknown>, path: string): EngineRunBlock {
  const run = parseEngineRun(o, path)
  if (run.split !== 'development') fail(`${path}.run.split`, `is "${run.split}" but this file shows the development split only (decision D19)`)
  if (run.sample_end > DEVELOPMENT_LAST_DATE) {
    fail(`${path}.run.sample_end`, `${run.sample_end} is after ${DEVELOPMENT_LAST_DATE}, the end of the development split (decision D19)`)
  }
  return run
}

/** The two blocks after the units that both M4 datasets carry: `illustrative` false and a non-empty label. */
function needNotIllustrativeWithLabel(o: Record<string, unknown>, P: string): string {
  if (need(o, 'illustrative', P) !== false) {
    fail(`${P}.illustrative`, 'must be false: these are records of the engine, so a file flagged illustrative is refused')
  }
  return needString(o, 'label', P)
}

/** `date` plus `days` calendar days, as YYYY-MM-DD. */
function addCalendarDays(date: string, days: number): string {
  const d = new Date(`${date}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

/** A key that must be exactly the number `expected`. */
function needExactly(obj: Record<string, unknown>, key: string, path: string, expected: number): void {
  const v = need(obj, key, path)
  if (v !== expected) fail(`${path}.${key}`, `expected ${expected}, got ${JSON.stringify(v)}`)
}

/** A finite number of any sign. */
function needFiniteNumber(obj: Record<string, unknown>, key: string, path: string): number {
  return checkFinite(need(obj, key, path), `${path}.${key}`)
}

function checkFinite(v: unknown, at: string): number {
  if (typeof v !== 'number' || !Number.isFinite(v)) fail(at, `expected a finite number, got ${String(v)}`)
  return v
}

/** A finite number strictly between 0 and 1. */
function needOpenUnitInterval(obj: Record<string, unknown>, key: string, path: string): number {
  const v = needFiniteNumber(obj, key, path)
  if (v <= 0 || v >= 1) fail(`${path}.${key}`, `${v} is outside (0, 1)`)
  return v
}

function parseSignalSpec(o: Record<string, unknown>, P: string): SignalSpec {
  const at = `${P}.signal`
  const s = asRecord(need(o, 'signal', P), at)
  const name = needString(s, 'name', at)
  const rv_model = needOneOf(s, 'rv_model', at, RV_MODELS)
  for (const key of ['window_days', 'horizon', 'min_pairs'] as const) needExactly(s, key, at, SIGNAL_PARAMS[key])
  return { name, rv_model, ...SIGNAL_PARAMS }
}

function parseThresholds(o: Record<string, unknown>, P: string): SignalsTimeline['thresholds'] {
  const at = `${P}.thresholds`
  const t = asRecord(need(o, 'thresholds', P), at)
  const shortEntry = needArray(t, 'short_entry', at)
  const want = SIGNAL_THRESHOLDS.short_entry
  if (shortEntry.length !== want.length || shortEntry.some((x, i) => x !== want[i])) {
    fail(`${at}.short_entry`, `expected [${want.join(', ')}], got ${JSON.stringify(shortEntry)}`)
  }
  needExactly(t, 'long_entry', at, SIGNAL_THRESHOLDS.long_entry)
  needExactly(t, 'exit_band', at, SIGNAL_THRESHOLDS.exit_band)
  return { short_entry: [want[0], want[1]], long_entry: SIGNAL_THRESHOLDS.long_entry, exit_band: SIGNAL_THRESHOLDS.exit_band }
}

/** A series of one entry per date, each a finite number or null; `positive` also requires a number to be above 0. */
function needNullableSeries(o: Record<string, unknown>, key: string, P: string, length: number, positive: boolean): (number | null)[] {
  const raw = needArray(o, key, P)
  if (raw.length !== length) fail(`${P}.${key}`, `has ${raw.length} values but dates has ${length}`)
  return raw.map((x, i) => {
    if (x === null) return null
    const at = `${P}.${key}[${i}]`
    const v = checkFinite(x, at)
    if (positive && v <= 0) fail(at, `expected a number above 0 or null, got ${v}`)
    return v
  })
}

function parseHarFit(raw: unknown, at: string): HarFit {
  const f = asRecord(raw, at)
  const fit_date = needDate(f, 'fit_date', at)
  if (fit_date > DEVELOPMENT_LAST_DATE) fail(`${at}.fit_date`, `${fit_date} is after ${DEVELOPMENT_LAST_DATE}, the end of the development split (decision D19)`)
  const coefRaw = needArray(f, 'coef', at)
  if (coefRaw.length !== 4) fail(`${at}.coef`, `expected 4 coefficients [constant, daily, weekly, monthly], got ${coefRaw.length}`)
  const coef = coefRaw.map((x, i) => checkFinite(x, `${at}.coef[${i}]`))
  const n_pairs = needInteger(f, 'n_pairs', at, SIGNAL_PARAMS.min_pairs)
  return { fit_date, coef, n_pairs }
}

function parseEffectiveSize(raw: unknown, at: string): ForecastTest['effective_size'] {
  const e = asRecord(raw, at)
  const worst = (key: 'worst_matched_battery_seed' | 'worst_matched_second_seed') => {
    const w = asRecord(need(e, key, at), `${at}.${key}`)
    return { rate: needInRange(w, 'rate', `${at}.${key}`, 0, 1, 'a size'), null_side: needString(w, 'null_side', `${at}.${key}`) }
  }
  const threshold = needOpenUnitInterval(e, 'threshold', at)
  const abc_size_battery_seed = needInRange(e, 'abc_size_battery_seed', at, 0, 1, 'a size')
  const abc_size_second_seed = needInRange(e, 'abc_size_second_seed', at, 0, 1, 'a size')
  const worst_matched_battery_seed = worst('worst_matched_battery_seed')
  const worst_matched_second_seed = worst('worst_matched_second_seed')
  if (abc_size_battery_seed > worst_matched_battery_seed.rate) {
    fail(`${at}.abc_size_battery_seed`, `${abc_size_battery_seed} is above the worst matched size ${worst_matched_battery_seed.rate} of its seed`)
  }
  if (abc_size_second_seed > worst_matched_second_seed.rate) {
    fail(`${at}.abc_size_second_seed`, `${abc_size_second_seed} is above the worst matched size ${worst_matched_second_seed.rate} of its seed`)
  }
  return { threshold, abc_size_battery_seed, abc_size_second_seed, worst_matched_battery_seed, worst_matched_second_seed }
}

function parseFragileBand(raw: unknown, at: string): [number, number] {
  if (!Array.isArray(raw) || raw.length !== 2) fail(at, `expected [lo, hi], got ${JSON.stringify(raw)}`)
  const edge = (x: unknown, i: number): number => {
    const v = checkFinite(x, `${at}[${i}]`)
    if (v <= 0 || v >= 1) fail(`${at}[${i}]`, `${v} is outside (0, 1)`)
    return v
  }
  const lo = edge(raw[0], 0)
  const hi = edge(raw[1], 1)
  if (lo >= hi) fail(at, `lo ${lo} is not below hi ${hi}`)
  return [lo, hi]
}

function parseForecastTest(raw: unknown, at: string): ForecastTest {
  const f = asRecord(raw, at)
  const prereg_id = needString(f, 'prereg_id', at)
  const prereg_sha256 = needHex(f, 'prereg_sha256', at)
  const window = needString(f, 'window', at)
  needExactly(f, 'k', at, 1)
  const n = needInteger(f, 'n', at, 1)
  const q = needInteger(f, 'q', at, 1)
  const block = needInteger(f, 'block', at, 1)
  const draws = needInteger(f, 'draws', at, 1)
  const mean_d = needFiniteNumber(f, 'mean_d', at)
  const ewc_t = needFiniteNumber(f, 'ewc_t', at)
  const se = needNonNegativeNumber(f, 'se', at)
  const p = needPositive(f, 'p', at, 1)
  const p_holm = needPositive(f, 'p_holm', at, 1)
  if (p_holm !== p) fail(`${at}.p_holm`, `${p_holm} differs from p ${p}: with k = 1 the Holm p is p`)
  const ciRaw = needArray(f, 'ci', at)
  if (ciRaw.length !== 2) fail(`${at}.ci`, `expected [lo, hi], got ${ciRaw.length} value(s)`)
  const ci: [number, number] = [checkFinite(ciRaw[0], `${at}.ci[0]`), checkFinite(ciRaw[1], `${at}.ci[1]`)]
  if (ci[0] > ci[1]) fail(`${at}.ci`, `lo ${ci[0]} is above hi ${ci[1]}`)
  const alpha = needOpenUnitInterval(f, 'alpha', at)
  const threshold = needOpenUnitInterval(f, 'threshold', at)
  if (threshold !== alpha) fail(`${at}.threshold`, `${threshold} differs from alpha ${alpha}`)
  const worst_simulated_size = needInRange(f, 'worst_simulated_size', at, 0, 1, 'a size')
  const effective_size = parseEffectiveSize(need(f, 'effective_size', at), `${at}.effective_size`)
  if (effective_size.threshold !== threshold) fail(`${at}.effective_size.threshold`, `${effective_size.threshold} differs from threshold ${threshold}`)
  if (worst_simulated_size < effective_size.worst_matched_battery_seed.rate) {
    fail(`${at}.worst_simulated_size`, `${worst_simulated_size} is below the worst matched battery-seed size ${effective_size.worst_matched_battery_seed.rate}`)
  }
  const decision = needOneOf(f, 'decision', at, RV_MODELS)
  const expected: RvModel = p < threshold ? 'har' : 'naive'
  if (decision !== expected) fail(`${at}.decision`, `is "${decision}" but p ${p} against threshold ${threshold} decides "${expected}"`)
  const fragile_band = parseFragileBand(need(f, 'fragile_band', at), `${at}.fragile_band`)
  const fragile = needBoolean(f, 'fragile', at)
  const inBand = fragile_band[0] <= p && p < fragile_band[1]
  if (fragile !== inBand) fail(`${at}.fragile`, `is ${fragile} but p ${p} against the band [${fragile_band[0]}, ${fragile_band[1]}) makes it ${inBand}`)
  const label = needString(f, 'label', at)
  if (!label.startsWith(FORECAST_LABEL_PREFIX)) fail(`${at}.label`, `${JSON.stringify(label)} does not start with "${FORECAST_LABEL_PREFIX}": the test is a proxy, and says so`)
  return { prereg_id, prereg_sha256, window, k: 1, n, q, block, draws, mean_d, ewc_t, se, p, p_holm, ci, alpha, threshold, worst_simulated_size, effective_size, fragile_band, fragile, decision, label }
}

export function parseSignalsTimeline(raw: unknown): SignalsTimeline {
  const P = SIGNALS_TIMELINE_DATASET
  const o = asRecord(raw, P)
  const { schema_version, generated_at, source_commit } = parseM4Envelope(o, P)
  const run = parseDevelopmentRun(o, P)
  const units = needUnits(o, P, SIGNALS_TIMELINE_UNIT_KEYS, SIGNALS_TIMELINE_UNITS)
  const label = needNotIllustrativeWithLabel(o, P)
  const signal = parseSignalSpec(o, P)
  const thresholds = parseThresholds(o, P)
  const rawDates = needArray(o, 'dates', P)
  if (rawDates.length === 0) fail(`${P}.dates`, 'needs at least 1 date')
  const dates = rawDates.map((x, i) => {
    const at = `${P}.dates[${i}]`
    if (typeof x !== 'string' || !isRealDate(x)) fail(at, `${JSON.stringify(x)} is not a calendar date YYYY-MM-DD`)
    // The run's sample ends on or before DEVELOPMENT_LAST_DATE (parseDevelopmentRun), so a date inside it is never after it.
    if (x < run.sample_start || x > run.sample_end) fail(at, `${x} is outside the run's sample ${run.sample_start} to ${run.sample_end}, which ends on or before ${DEVELOPMENT_LAST_DATE} (decision D19)`)
    return x
  })
  dates.forEach((x, i) => {
    if (i > 0 && !(x > dates[i - 1])) fail(`${P}.dates[${i}]`, `must be strictly increasing, but ${x} follows ${dates[i - 1]}`)
  })
  const iv30 = needNullableSeries(o, 'iv30', P, dates.length, true)
  const rv_forecast = needNullableSeries(o, 'rv_forecast', P, dates.length, true)
  const rv_realised = needNullableSeries(o, 'rv_realised', P, dates.length, true)
  const log_var_ratio = needNullableSeries(o, 'log_var_ratio', P, dates.length, false)
  dates.forEach((date, i) => {
    if (log_var_ratio[i] !== null && (iv30[i] === null || rv_forecast[i] === null)) {
      fail(`${P}.log_var_ratio[${i}]`, `is ${log_var_ratio[i]} but ${iv30[i] === null ? 'iv30' : 'rv_forecast'}[${i}] is null on ${date}: the ratio needs both`)
    }
    // The realised vol looks 30 calendar days ahead; a window that ends after the development split is not ours to show.
    if (rv_realised[i] !== null && addCalendarDays(date, 30) > DEVELOPMENT_LAST_DATE) {
      fail(`${P}.rv_realised[${i}]`, `is ${rv_realised[i]} but the 30-day window from ${date} ends after ${DEVELOPMENT_LAST_DATE}, so this must be null (decision D19)`)
    }
  })
  const fitList = needArray(o, 'fits', P)
  const fits = fitList.map((item, i) => parseHarFit(item, `${P}.fits[${i}]`))
  fits.forEach((f, i) => {
    if (i > 0 && !(f.fit_date > fits[i - 1].fit_date)) fail(`${P}.fits[${i}].fit_date`, `must be strictly increasing, but ${f.fit_date} follows ${fits[i - 1].fit_date}`)
  })
  if (signal.rv_model === 'naive' && fits.length > 0) fail(`${P}.fits`, 'must be empty for the naive model, which is not fitted')
  const rawFitDates = needArray(o, 'model_fit_date', P)
  if (rawFitDates.length !== dates.length) fail(`${P}.model_fit_date`, `has ${rawFitDates.length} values but dates has ${dates.length}`)
  const model_fit_date = rawFitDates.map((x, i) => {
    if (x === null) return null
    const at = `${P}.model_fit_date[${i}]`
    if (typeof x !== 'string' || !isRealDate(x)) fail(at, `${JSON.stringify(x)} is not a calendar date YYYY-MM-DD or null`)
    if (signal.rv_model === 'naive') fail(at, `is ${x} but the naive model has no fit, so this must be null`)
    if (x > dates[i]) fail(at, `${x} is after the date ${dates[i]} it forecasts for`)
    if (!fits.some((f) => f.fit_date === x)) fail(at, `${x} is not the fit_date of any entry of fits`)
    return x
  })
  const n_window = needArray(o, 'n_window', P).map((x, i) => checkInteger(x, `${P}.n_window[${i}]`, 0))
  if (n_window.length !== dates.length) fail(`${P}.n_window`, `has ${n_window.length} values but dates has ${dates.length}`)
  const flagCeiling = 2 ** SIGNAL_FLAG_NAMES.length - 1
  const flags = needArray(o, 'flags', P).map((x, i) => {
    const v = checkInteger(x, `${P}.flags[${i}]`, 0)
    if (v > flagCeiling) fail(`${P}.flags[${i}]`, `${v} is above ${flagCeiling}, the value with all ${SIGNAL_FLAG_NAMES.length} flag bits set`)
    return v
  })
  if (flags.length !== dates.length) fail(`${P}.flags`, `has ${flags.length} values but dates has ${dates.length}`)
  const flag_names = needStrings(o, 'flag_names', P)
  if (flag_names.length !== SIGNAL_FLAG_NAMES.length || flag_names.some((x, i) => x !== SIGNAL_FLAG_NAMES[i])) {
    fail(`${P}.flag_names`, `expected [${SIGNAL_FLAG_NAMES.join(', ')}] (bit 0 first), got ${JSON.stringify(flag_names)}`)
  }
  const test = need(o, 'forecast_test', P)
  const forecast_test = test === null ? null : parseForecastTest(test, `${P}.forecast_test`)
  if (forecast_test !== null && signal.rv_model !== forecast_test.decision) {
    fail(`${P}.signal.rv_model`, `is "${signal.rv_model}" but the forecast test chose "${forecast_test.decision}": the timeline shows the model the test chose`)
  }
  return {
    schema_version, generated_at, source_commit, run, units, illustrative: false, label, signal, thresholds, dates,
    iv30, rv_forecast, rv_realised, log_var_ratio, model_fit_date, n_window, flags, flag_names, fits, forecast_test,
  }
}

/** A date of a position that must lie inside the run's sample (any calendar day: the file names no sessions). */
function needDateInSample(obj: Record<string, unknown>, key: string, path: string, run: EngineRunBlock): string {
  const v = needDate(obj, key, path)
  if (v < run.sample_start || v > run.sample_end) fail(`${path}.${key}`, `${v} is outside the run's sample ${run.sample_start} to ${run.sample_end}`)
  return v
}

const isCall = (osi: string): boolean => osi.charAt(12) === 'C'

/** The legs of a structure, by the rules of that structure (the file carries every value checked here). */
function checkStructureLegs(structure: StrategyStructure, legs: PositionLeg[], at: string): void {
  const expected = structure === 'straddle_calendar' ? 4 : 2
  if (legs.length !== expected) fail(`${at}.legs`, `a ${structure} has ${expected} legs, got ${legs.length}`)
  const calls = legs.filter((l) => isCall(l.osi_symbol))
  if (structure !== 'straddle_calendar' && (calls.length !== 1 || legs.length - calls.length !== 1)) {
    fail(`${at}.legs`, `a ${structure} has one call and one put, got ${calls.length} call(s) and ${legs.length - calls.length} put(s)`)
  }
  const expiries = [...new Set(legs.map((l) => osiExpiry(l.osi_symbol)))].sort()
  const strikes = new Set(legs.map((l) => osiStrike(l.osi_symbol)))
  if (structure === 'short_straddle' || structure === 'long_straddle') {
    const ratio = structure === 'short_straddle' ? -1 : 1
    if (expiries.length !== 1) fail(`${at}.legs`, `a ${structure} has one expiry, got ${expiries.length}`)
    if (strikes.size !== 1) fail(`${at}.legs`, `a ${structure} has one strike, got ${strikes.size}`)
    legs.forEach((l, i) => {
      if (l.ratio !== ratio) fail(`${at}.legs[${i}].ratio`, `is ${l.ratio} but every leg of a ${structure} has ratio ${ratio}`)
    })
  } else if (structure === 'short_strangle') {
    if (expiries.length !== 1) fail(`${at}.legs`, `a short_strangle has one expiry, got ${expiries.length}`)
    legs.forEach((l, i) => {
      if (l.ratio !== -1) fail(`${at}.legs[${i}].ratio`, `is ${l.ratio} but every leg of a short_strangle has ratio -1`)
    })
    const put = legs.find((l) => !isCall(l.osi_symbol)) as PositionLeg
    if (!(osiStrike(calls[0].osi_symbol) > osiStrike(put.osi_symbol))) {
      fail(`${at}.legs`, `the call strike ${osiStrike(calls[0].osi_symbol)} is not above the put strike ${osiStrike(put.osi_symbol)}, which a short_strangle needs`)
    }
  } else {
    if (strikes.size !== 1) fail(`${at}.legs`, `a straddle_calendar has one strike, got ${strikes.size}`)
    if (expiries.length !== 2) fail(`${at}.legs`, `a straddle_calendar has two expiries, got ${expiries.length}`)
    for (const expiry of expiries) {
      const same = legs.filter((l) => osiExpiry(l.osi_symbol) === expiry)
      if (same.length !== 2 || same.filter((l) => isCall(l.osi_symbol)).length !== 1) {
        fail(`${at}.legs`, `a straddle_calendar has a call and a put on each expiry, but ${expiry} has ${same.length} leg(s)`)
      }
    }
    legs.forEach((l, i) => {
      const ratio = osiExpiry(l.osi_symbol) === expiries[0] ? -1 : 1
      if (l.ratio !== ratio) fail(`${at}.legs[${i}].ratio`, `is ${l.ratio} but the ${ratio === -1 ? 'nearer' : 'farther'} expiry's legs of a straddle_calendar have ratio ${ratio}`)
    })
  }
}

function parseStrategyPosition(raw: unknown, at: string, run: EngineRunBlock): StrategyPosition {
  const p = asRecord(raw, at)
  const position_id = needInteger(p, 'position_id', at, 1)
  const structure = needOneOf(p, 'structure', at, STRATEGY_STRUCTURES)
  const opened = needDateInSample(p, 'opened', at, run)
  let closed: string | null = null
  if (need(p, 'closed', at) !== null) {
    closed = needDateInSample(p, 'closed', at, run)
    if (closed < opened) fail(`${at}.closed`, `${closed} is before opened ${opened}`)
  }
  const legList = needArray(p, 'legs', at)
  const legs = legList.map((item, i): PositionLeg => {
    const legAt = `${at}.legs[${i}]`
    const leg = asRecord(item, legAt)
    const osi_symbol = needOsiSymbol(leg, 'osi_symbol', legAt)
    const ratio = need(leg, 'ratio', legAt)
    if (ratio !== 1 && ratio !== -1) fail(`${legAt}.ratio`, `expected 1 or -1, got ${JSON.stringify(ratio)}`)
    if (opened >= osiExpiry(osi_symbol)) fail(`${at}.opened`, `${opened} is not before the expiry ${osiExpiry(osi_symbol)} of ${JSON.stringify(osi_symbol)}`)
    return { osi_symbol, ratio }
  })
  checkStructureLegs(structure, legs, at)
  const entry = need(p, 'entry_signal', at)
  const entry_signal = entry === null ? null : checkFinite(entry, `${at}.entry_signal`)
  const reason = need(p, 'exit_reason', at)
  let exit_reason: ExitReason | null = null
  if (closed === null) {
    if (reason !== null) fail(`${at}.exit_reason`, `is ${JSON.stringify(reason)} but the position is open (closed is null), so this must be null`)
  } else {
    if (reason === null) fail(`${at}.exit_reason`, `is null but the position closed on ${closed}, so it has an exit reason`)
    exit_reason = checkOneOf(reason, `${at}.exit_reason`, EXIT_REASONS)
  }
  return { position_id, structure, opened, closed, legs, entry_signal, exit_reason }
}

function parseStrategyRun(raw: unknown, at: string): StrategyRun {
  const r = asRecord(raw, at)
  const run = parseDevelopmentRun(r, at)
  const strategy = needString(r, 'strategy', at)
  if (strategy !== run.strategy) fail(`${at}.strategy`, `is "${strategy}" but run.strategy is "${run.strategy}"`)
  const params = asRecord(need(r, 'params', at), `${at}.params`)
  const trial_group = needString(r, 'trial_group', at)
  const n_trials_group = needInteger(r, 'n_trials_group', at, 1)
  const positions = needArray(r, 'positions', at).map((item, i) => parseStrategyPosition(item, `${at}.positions[${i}]`, run))
  assertOrdered(positions, `${at}.positions`, 'position_id', (x) => x.position_id)
  return { run, strategy, params, trial_group, n_trials_group, positions }
}

export function parseStrategyPositions(raw: unknown): StrategyPositions {
  const P = STRATEGY_POSITIONS_DATASET
  const o = asRecord(raw, P)
  const { schema_version, generated_at, source_commit } = parseM4Envelope(o, P)
  const units = needUnits(o, P, STRATEGY_POSITIONS_UNIT_KEYS, STRATEGY_POSITIONS_UNITS)
  const label = needNotIllustrativeWithLabel(o, P)
  const banner = needString(o, 'banner', P)
  const runList = needArray(o, 'runs', P)
  if (runList.length === 0) fail(`${P}.runs`, 'needs at least 1 run')
  const runs = runList.map((item, i) => parseStrategyRun(item, `${P}.runs[${i}]`))
  return { schema_version, generated_at, source_commit, units, illustrative: false, label, banner, runs }
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
