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
