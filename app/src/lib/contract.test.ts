import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  CALENDAR_ACTION_NAMES,
  ContractError,
  FLAG_NAMES,
  GATE_RULES,
  GATE_SHARE_FLAGS,
  MAX_IV,
  SUPPORTED_MAJOR,
  assertDatasetMatchesEntry,
  commitState,
  findDataset,
  parseDataQuality,
  parseIllustrativeSurface,
  parseManifest,
} from './contract'
import manifestFixture from '../test/fixtures/manifest.json'
import surfaceFixture from '../test/fixtures/illustrative_surface.json'
import dataQualityFixture from '../test/fixtures/data_quality.json'

// A fresh, mutable deep copy per test so one case cannot leak into the next.
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T
type Obj = Record<string, unknown>

/** Assert `parse(raw)` throws a ContractError whose message contains `fragment`. */
function rejects(parse: (raw: unknown) => unknown, raw: unknown, fragment: string): void {
  let err: unknown
  try {
    parse(raw)
  } catch (e) {
    err = e
  }
  expect(err, `expected a ContractError containing "${fragment}"`).toBeInstanceOf(ContractError)
  expect((err as Error).message).toContain(fragment)
}

describe('parseManifest: accepts', () => {
  it('returns the fixture unchanged (every field survives, in order)', () => {
    expect(parseManifest(manifestFixture)).toEqual(manifestFixture)
  })
  it('ignores unknown extra keys and accepts any minor/patch of the supported major', () => {
    const m = clone(manifestFixture) as Obj
    m.schema_version = `${SUPPORTED_MAJOR}.9.3`
    m.future_field = { anything: 1 }
    const parsed = parseManifest(m)
    expect(parsed.schema_version).toBe('0.9.3')
    expect(parsed).not.toHaveProperty('future_field')
  })
  it.each([
    'a1b2c3d',
    'a1b2c3d4e5f60718293a4b5c6d7e8f9012345678', // 40 hex: a full SHA-1 commit id
    'a1b2c3d4e5f60718293a4b5c6d7e8f9012345678a1b2c3d4e5f60718293a4b5c', // 64 hex: a full SHA-256 commit id
    'a1b2c3d4e5f60718293a4b5c6d7e8f9012345678a1b2c3d4e5f60718293a4b5c-dirty',
    'a1b2c3d-dirty',
    'uncommitted',
  ])(
    'accepts source_commit %s',
    (sha) => {
      const m = clone(manifestFixture) as Obj
      m.source_commit = sha
      expect(parseManifest(m).source_commit).toBe(sha)
    },
  )
  it.each([
    '2026-10-27T23:30:00Z',
    '2026-10-27T23:30:00.123456Z',
    '2026-10-27T23:30:00+00:00',
    '2026-10-27T19:30:00-04:00',
    '2024-02-29T12:00:00Z', // 2024 is a leap year
    '2026-12-31T23:59:59Z',
    '2026-01-01T00:00:00Z',
    '2026-10-27T10:00:00+23:59',
    '2026-10-27T10:00:00-12:00',
  ])(
    'accepts generated_at %s',
    (ts) => {
      const m = clone(manifestFixture) as Obj
      m.generated_at = ts
      expect(parseManifest(m).generated_at).toBe(ts)
    },
  )
  it('accepts an empty dataset list and a nested relative path', () => {
    const m = clone(manifestFixture) as Obj
    m.datasets = []
    expect(parseManifest(m).datasets).toEqual([])
    const n = clone(manifestFixture) as { datasets: Obj[] }
    n.datasets[0].path = 'surfaces/v1/illustrative_surface.json'
    expect(parseManifest(n).datasets[0].path).toBe('surfaces/v1/illustrative_surface.json')
  })
})

describe('parseManifest: rejects', () => {
  it.each([null, undefined, 3, 'text', [], true])('a non-object root (%j)', (bad) => {
    rejects(parseManifest, bad, 'manifest: expected an object')
  })
  it.each([
    ['1.0.0', 'unsupported major version 1'],
    ['2.1.0', 'unsupported major version 2'],
    ['10.0.0', 'unsupported major version 10'],
    ['0.1', 'not MAJOR.MINOR.PATCH'],
    ['v0.1.0', 'not MAJOR.MINOR.PATCH'],
    ['0.1.0-beta', 'not MAJOR.MINOR.PATCH'],
    ['00.1.0', 'not MAJOR.MINOR.PATCH'], // leading zeros are not SemVer
    ['0.01.0', 'not MAJOR.MINOR.PATCH'],
    ['0.1.00', 'not MAJOR.MINOR.PATCH'],
    ['01.0.0', 'not MAJOR.MINOR.PATCH'],
    ['', 'non-empty string'],
  ])('schema_version %j', (version, fragment) => {
    const m = clone(manifestFixture) as Obj
    m.schema_version = version
    rejects(parseManifest, m, fragment)
  })
  it.each(['0.0.0', '0.10.20', '0.1.0'])('accepts the zero-bearing but valid schema_version %s', (version) => {
    const m = clone(manifestFixture) as Obj
    m.schema_version = version
    expect(parseManifest(m).schema_version).toBe(version)
  })
  it('a numeric schema_version', () => {
    const m = clone(manifestFixture) as Obj
    m.schema_version = 0.1
    rejects(parseManifest, m, 'manifest.schema_version: expected a non-empty string')
  })
  it.each(['schema_version', 'generated_at', 'source_commit', 'datasets'])('a missing top-level key %s', (key) => {
    const m = clone(manifestFixture) as Obj
    delete m[key]
    rejects(parseManifest, m, `missing required key "${key}"`)
  })
  it.each([
    'yesterday',
    '2026-10-27',
    '2026-10-27 23:30:00',
    '2026-10-27T23:30:00',
    '2026-13-45T25:61:61Z',
    // Well-formed but not real. Date.parse alone lets the first ones through (it rolls them over).
    '2026-02-30T00:00:00Z', // February has no 30th
    '2025-02-29T00:00:00Z', // 2025 is not a leap year
    '2026-04-31T00:00:00Z', // April has 30 days
    '2026-00-10T00:00:00Z', // month 0
    '2026-10-00T00:00:00Z', // day 0
    '2026-10-27T24:00:00Z', // hour 24 is read as midnight of the next day
    '2026-10-27T24:00:00+00:00',
    '2026-10-27T23:59:60Z', // a leap second is not representable
    '2026-10-27T10:00:00+24:00', // offset hours go to 23
    '2026-10-27T10:00:00+05:60', // offset minutes go to 59
  ])(
    'generated_at %j',
    (ts) => {
      const m = clone(manifestFixture) as Obj
      m.generated_at = ts
      rejects(parseManifest, m, 'manifest.generated_at')
    },
  )
  // V8's Date.parse already returns NaN for an offset outside +-23:59, so on this engine the explicit
  // offset check in contract.ts is never reached by the cases above. The ECMAScript spec leaves a
  // string that is out of range for the ISO format to the engine, and others may read it. Make
  // Date.parse accept anything and check that the contract still refuses.
  describe('generated_at offsets when Date.parse is lenient', () => {
    afterEach(() => {
      vi.restoreAllMocks()
    })
    it.each(['+24:00', '-24:00', '+05:60', '-05:60', '+99:99'])('rejects offset %s', (offset) => {
      vi.spyOn(Date, 'parse').mockReturnValue(0)
      const m = clone(manifestFixture) as Obj
      m.generated_at = `2026-10-27T10:00:00${offset}`
      rejects(parseManifest, m, 'manifest.generated_at')
    })
    it.each(['+23:59', '-23:59', '+05:30', '+00:00', 'Z'])('still accepts offset %s', (offset) => {
      vi.spyOn(Date, 'parse').mockReturnValue(0)
      const m = clone(manifestFixture) as Obj
      m.generated_at = `2026-10-27T10:00:00${offset}`
      expect(parseManifest(m).generated_at).toBe(m.generated_at)
    })
  })
  it.each([
    'xyz',
    'A1B2C3D4',
    'a1b2c3',
    'a1b2c3d-clean',
    'uncommited',
    'g1b2c3d4',
    'a'.repeat(65), // longer than any git commit id
    `${'a'.repeat(65)}-dirty`,
  ])('source_commit %j', (sha) => {
    const m = clone(manifestFixture) as Obj
    m.source_commit = sha
    rejects(parseManifest, m, 'manifest.source_commit')
  })
  it('datasets that is not an array', () => {
    const m = clone(manifestFixture) as Obj
    m.datasets = { name: 'x' }
    rejects(parseManifest, m, 'manifest.datasets: expected an array')
  })
  it('a dataset entry that is not an object', () => {
    const m = clone(manifestFixture) as Obj
    m.datasets = ['illustrative_surface.json']
    rejects(parseManifest, m, 'manifest.datasets[0]: expected an object')
  })
  it.each(['name', 'path', 'schema_version', 'description'])('a dataset entry missing %s', (key) => {
    const m = clone(manifestFixture) as { datasets: Obj[] }
    delete m.datasets[0][key]
    rejects(parseManifest, m, `manifest.datasets[0]: missing required key "${key}"`)
  })
  it('a dataset entry with an unsupported major version', () => {
    const m = clone(manifestFixture) as { datasets: Obj[] }
    m.datasets[0].schema_version = '1.0.0'
    rejects(parseManifest, m, 'manifest.datasets[0].schema_version: unsupported major version 1')
  })
  it('duplicate dataset names, naming the second occurrence', () => {
    const m = clone(manifestFixture) as { datasets: Obj[] }
    m.datasets.push(clone(m.datasets[0]))
    rejects(parseManifest, m, 'manifest.datasets[2].name: duplicate dataset name "illustrative_surface"')
  })
  it.each([
    '../secrets.json',
    'data/../../etc/passwd',
    '/etc/passwd',
    'https://example.com/x.json',
    'C:\\x.json',
    'dir\\file.json',
    'file.json?x=1',
    'file.json#frag',
    '.hidden.json',
    'a//b.json',
    'trailing/',
    '',
  ])('unsafe or malformed path %j', (p) => {
    const m = clone(manifestFixture) as { datasets: Obj[] }
    m.datasets[0].path = p
    let err: unknown
    try {
      parseManifest(m)
    } catch (e) {
      err = e
    }
    expect(err).toBeInstanceOf(ContractError)
    expect((err as Error).message).toContain('manifest.datasets[0].path')
  })
})

describe('parseIllustrativeSurface: accepts', () => {
  it('returns the fixture unchanged', () => {
    expect(parseIllustrativeSurface(surfaceFixture)).toEqual(surfaceFixture)
  })
  it('accepts the smallest grid (2 x 2) and IV exactly at the ceiling', () => {
    const s = clone(surfaceFixture) as Obj
    s.moneyness = [-0.1, 0.1]
    s.dte = [7, 30]
    s.iv = [
      [MAX_IV, 0.2],
      [0.2, 0.01],
    ]
    expect(parseIllustrativeSurface(s).iv).toEqual([
      [5, 0.2],
      [0.2, 0.01],
    ])
  })
})

describe('parseIllustrativeSurface: rejects', () => {
  it.each([null, [], 'x', 7])('a non-object root (%j)', (bad) => {
    rejects(parseIllustrativeSurface, bad, 'illustrative_surface: expected an object')
  })
  it.each(['schema_version', 'generated_at', 'source_commit', 'illustrative', 'label', 'moneyness', 'dte', 'iv', 'params'])(
    'a missing key %s',
    (key) => {
      const s = clone(surfaceFixture) as Obj
      delete s[key]
      rejects(parseIllustrativeSurface, s, `illustrative_surface: missing required key "${key}"`)
    },
  )
  it('a wrong schema_version major', () => {
    const s = clone(surfaceFixture) as Obj
    s.schema_version = '1.0.0'
    rejects(parseIllustrativeSurface, s, 'unsupported major version 1')
  })
  it.each([false, 'true', 1, null])('illustrative = %j (must be literally true)', (flag) => {
    const s = clone(surfaceFixture) as Obj
    s.illustrative = flag
    rejects(parseIllustrativeSurface, s, 'illustrative_surface.illustrative: must be true')
  })
  it.each(['2026-02-30T00:00:00Z', '2026-10-27T24:00:00Z'])('an impossible generated_at (%s) in a dataset file too', (ts) => {
    const s = clone(surfaceFixture) as Obj
    s.generated_at = ts
    rejects(parseIllustrativeSurface, s, 'illustrative_surface.generated_at')
  })
  it('a source_commit that is not a hash', () => {
    const s = clone(surfaceFixture) as Obj
    s.source_commit = 'a'.repeat(65)
    rejects(parseIllustrativeSurface, s, 'illustrative_surface.source_commit')
  })
  it('an empty label', () => {
    const s = clone(surfaceFixture) as Obj
    s.label = '  '
    rejects(parseIllustrativeSurface, s, 'illustrative_surface.label')
  })

  describe('axes', () => {
    it.each(['moneyness', 'dte'])('%s that is not an array', (key) => {
      const s = clone(surfaceFixture) as Obj
      s[key] = '1,2,3'
      rejects(parseIllustrativeSurface, s, `illustrative_surface.${key}: expected an array of numbers`)
    })
    it.each(['moneyness', 'dte'])('%s with fewer than 2 values', (key) => {
      const s = clone(surfaceFixture) as Obj
      s[key] = [1]
      rejects(parseIllustrativeSurface, s, `illustrative_surface.${key}: needs at least 2 values`)
    })
    it.each([
      ['NaN', NaN],
      ['Infinity', Infinity],
      ['-Infinity', -Infinity],
      ['null', null],
      ['a numeric string', '0.1'],
    ])('a non-finite or non-number axis value (%s)', (_name, bad) => {
      const s = clone(surfaceFixture) as { moneyness: unknown[] }
      s.moneyness[2] = bad
      rejects(parseIllustrativeSurface, s, 'illustrative_surface.moneyness[2]: expected a finite number')
    })
    it('a descending moneyness grid', () => {
      const s = clone(surfaceFixture) as Obj
      s.moneyness = [0.1, 0.0, -0.1, -0.2]
      rejects(parseIllustrativeSurface, s, 'illustrative_surface.moneyness[1]: grid must be strictly increasing')
    })
    it('a repeated dte value (non-strict increase)', () => {
      const s = clone(surfaceFixture) as Obj
      s.dte = [7, 30, 30]
      rejects(parseIllustrativeSurface, s, 'illustrative_surface.dte[2]: grid must be strictly increasing')
    })
    it.each([0, -7])('a non-positive first dte (%d)', (first) => {
      const s = clone(surfaceFixture) as Obj
      s.dte = [first, 30, 90]
      rejects(parseIllustrativeSurface, s, 'illustrative_surface.dte[0]: days to expiry must be positive')
    })
  })

  describe('iv grid', () => {
    it('iv that is not an array', () => {
      const s = clone(surfaceFixture) as Obj
      s.iv = 'flat'
      rejects(parseIllustrativeSurface, s, 'illustrative_surface.iv: expected an array of rows')
    })
    it('too few rows for the dte axis', () => {
      const s = clone(surfaceFixture) as { iv: number[][] }
      s.iv.pop()
      rejects(parseIllustrativeSurface, s, 'illustrative_surface.iv: has 2 rows but dte has 3')
    })
    it('a ragged row (shorter than moneyness)', () => {
      const s = clone(surfaceFixture) as { iv: number[][] }
      s.iv[1] = [0.28, 0.23, 0.2]
      rejects(parseIllustrativeSurface, s, 'illustrative_surface.iv[1]: has 3 values but moneyness has 4 (ragged grid)')
    })
    it('a ragged row (longer than moneyness)', () => {
      const s = clone(surfaceFixture) as { iv: number[][] }
      s.iv[0].push(0.25)
      rejects(parseIllustrativeSurface, s, 'illustrative_surface.iv[0]: has 5 values but moneyness has 4 (ragged grid)')
    })
    it('a row that is not an array', () => {
      const s = clone(surfaceFixture) as { iv: unknown[] }
      s.iv[2] = 0.2
      rejects(parseIllustrativeSurface, s, 'illustrative_surface.iv[2]: expected an array of numbers')
    })
    it.each([
      ['NaN', NaN],
      ['Infinity', Infinity],
      ['null', null],
      ['a string', '0.2'],
    ])('a non-finite IV cell (%s), naming its row and column', (_name, bad) => {
      const s = clone(surfaceFixture) as { iv: unknown[][] }
      s.iv[2][3] = bad
      rejects(parseIllustrativeSurface, s, 'illustrative_surface.iv[2][3]: expected a finite number')
    })
    it.each([0, -0.2])('a non-positive IV (%d)', (bad) => {
      const s = clone(surfaceFixture) as { iv: number[][] }
      s.iv[0][0] = bad
      rejects(parseIllustrativeSurface, s, 'illustrative_surface.iv[0][0]: implied vol')
    })
    it('an IV just above the ceiling', () => {
      const s = clone(surfaceFixture) as { iv: number[][] }
      s.iv[1][1] = MAX_IV + 0.0001
      rejects(parseIllustrativeSurface, s, 'must be a decimal (0.18 = 18%)')
    })
    it('percent-scaled IVs (18 instead of 0.18)', () => {
      const s = clone(surfaceFixture) as { iv: number[][] }
      s.iv = s.iv.map((row) => row.map((v) => v * 100))
      rejects(parseIllustrativeSurface, s, 'must be a decimal (0.18 = 18%)')
    })
  })

  describe('params', () => {
    it.each([null, [], 'a=1', 3])('params = %j (must be an object)', (bad) => {
      const s = clone(surfaceFixture) as Obj
      s.params = bad
      rejects(parseIllustrativeSurface, s, 'illustrative_surface.params: expected an object')
    })
  })
})

// ---------------------------------------------------------------- data_quality

type Cols = Record<string, unknown[]>
interface Doc extends Obj {
  flag_names: unknown[]
  flag_descriptions: unknown[]
  flags_by_year: { source: unknown[]; year: unknown[]; rows: unknown[]; counts: Cols; shares: Cols } & Obj
  sources: Cols
  calendar: Cols
  cross_vendor: { distributions: Cols; within_thresholds: Cols; by_year: Cols; label: unknown; overlap_dates: unknown; basis: unknown } & Obj
  gate: { thresholds: Cols; passed: unknown; failures: unknown } & Obj
}

/** A deep copy of the data-quality fixture with `edit` applied. */
function broken(edit: (d: Doc) => void): Doc {
  const d = clone(dataQualityFixture) as unknown as Doc
  edit(d)
  return d
}

describe('parseDataQuality: accepts', () => {
  it('returns the fixture unchanged (every field survives, in order)', () => {
    expect(parseDataQuality(dataQualityFixture)).toEqual(dataQualityFixture)
  })
  it('accepts any minor/patch of the supported major, and drops unknown keys at every level', () => {
    const d = broken((x) => {
      x.schema_version = `${SUPPORTED_MAJOR}.9.3`
      x.future = 1
      x.flags_by_year.future = 1
      x.flags_by_year.counts.NOT_A_FLAG = [1, 1, 1, 1]
      x.sources.future = [1, 2]
      x.cross_vendor.future = 1
      x.cross_vendor.distributions.future = [1, 2]
      x.gate.future = 1
      x.gate.thresholds.future = [1, 2, 3]
    })
    const parsed = parseDataQuality(d) as unknown as Doc
    expect(parsed.schema_version).toBe('0.9.3')
    expect(parsed).not.toHaveProperty('future')
    expect(parsed.flags_by_year).not.toHaveProperty('future')
    expect(parsed.flags_by_year.counts).not.toHaveProperty('NOT_A_FLAG')
    expect(parsed.sources).not.toHaveProperty('future')
    expect(parsed.cross_vendor).not.toHaveProperty('future')
    expect(parsed.cross_vendor.distributions).not.toHaveProperty('future')
    expect(parsed.gate).not.toHaveProperty('future')
    expect(parsed.gate.thresholds).not.toHaveProperty('future')
  })
  it('accepts a failed gate when it lists its reasons, even for a failure that is not a row of the table', () => {
    const d = broken((x) => {
      x.gate.passed = false
      x.gate.failures = ['dolthub: no rows in the report']
    })
    const parsed = parseDataQuality(d)
    expect(parsed.gate.passed).toBe(false)
    expect(parsed.gate.failures).toHaveLength(1)
  })
  it('drops a tolerances key of an older file from the cross-vendor check, which has no verdict', () => {
    const d = broken((x) => {
      x.cross_vendor.tolerances = { check: ['iv30'] }
    })
    const parsed = parseDataQuality(d).cross_vendor
    expect(parsed).not.toHaveProperty('tolerances')
    expect(Object.keys(parsed).sort()).toEqual(['basis', 'by_year', 'distributions', 'label', 'overlap_dates', 'within_thresholds'])
  })
  it('accepts shares of exactly 0 and 1, a count equal to its row total, and quantiles that tie', () => {
    const d = broken((x) => {
      x.flags_by_year.shares.ZERO_BID = [0, 1, 1, 0] // a flag the gate does not limit
      x.flags_by_year.counts.ZERO_BID = [0, 1000, 2000, 0] // every quote of 2010 and 2011 carries the flag
      x.cross_vendor.distributions.p25 = [-0.25, -18] // equal to p05: a tie is in order
    })
    const parsed = parseDataQuality(d)
    expect(parsed.flags_by_year.counts.ZERO_BID).toEqual([0, 1000, 2000, 0])
    expect(parsed.cross_vendor.distributions.p25).toEqual([-0.25, -18])
  })
  it('accepts a share that differs from counts / rows by the rounding of its 6 decimals', () => {
    const d = broken((x) => (x.flags_by_year.shares.ZERO_BID[1] = 0.1000004)) // 100 / 1000 = 0.1, 4e-7 away
    expect(parseDataQuality(d).flags_by_year.shares.ZERO_BID[1]).toBe(0.1000004)
  })
  it('accepts a gate worst that differs from the highest share by the rounding of its 6 decimals', () => {
    const d = broken((x) => (x.gate.thresholds.worst[0] = 0.0300004)) // the highest BID_NULL share of optionsdx is 0.03
    expect(parseDataQuality(d).gate.thresholds.worst[0]).toBe(0.0300004)
  })
  it('accepts a source-year with no quotes when every share of it is 0', () => {
    const d = broken((x) => {
      x.flags_by_year.rows[2] = 0
      for (const name of FLAG_NAMES) {
        x.flags_by_year.counts[name][2] = 0
        x.flags_by_year.shares[name][2] = 0
      }
      x.sources.rows[1] = 5000 // 1000 + 0 + 4000: the source total follows the year
    })
    expect(parseDataQuality(d).flags_by_year.rows[2]).toBe(0)
  })
  it('accepts a gate bound of max and of min, with every row of the 21 in the fixture', () => {
    const { bound, rule } = parseDataQuality(dataQualityFixture).gate.thresholds
    expect(rule).toHaveLength(21)
    expect(new Set(bound)).toEqual(new Set(['max', 'min']))
  })
  it('has, in the fixture, the rows of the exporter\'s rule set and the calendar actions it defines', () => {
    const dq = parseDataQuality(dataQualityFixture)
    for (const [rule, spec] of Object.entries(GATE_RULES)) {
      for (const [source, rows] of Object.entries(spec.rows)) {
        expect(dq.gate.thresholds.rule.filter((r, i) => r === rule && dq.gate.thresholds.source[i] === source), `${rule} ${source}`).toHaveLength(rows)
      }
    }
    expect(Object.keys(GATE_SHARE_FLAGS)).toEqual(['optionsdx', 'dolthub'])
    expect([...CALENDAR_ACTION_NAMES]).toEqual(['session', 'drop'])
    expect(new Set(dq.calendar.action)).toEqual(new Set(CALENDAR_ACTION_NAMES))
  })
  it('accepts a passed gate whose "max" row sits exactly at its limit (the highest share is the limit)', () => {
    const d = broken((x) => {
      x.flags_by_year.counts.BID_NULL[1] = 50 // 50 / 1000 = 0.05, the limit of row 0
      x.flags_by_year.shares.BID_NULL[1] = 0.05
      x.gate.thresholds.worst[0] = 0.05
    })
    const { thresholds } = parseDataQuality(d).gate
    expect(thresholds.bound[0]).toBe('max')
    expect(thresholds.worst[0]).toBe(thresholds.limit[0])
  })
  it('accepts a passed gate whose "min" row sits exactly at its limit', () => {
    const d = broken((x) => (x.gate.thresholds.worst[9] = x.gate.thresholds.limit[9]))
    const { thresholds } = parseDataQuality(d).gate
    expect(thresholds.bound[9]).toBe('min')
    expect(thresholds.worst[9]).toBe(230)
  })
  it('accepts a pooled share anywhere the missing dates allow, and not only the exact date-weighted mean', () => {
    // iv30: 98 of the 100 overlap dates have a value, and the years (25 dates each) are at 0.92, 0.96, 1 and 1.
    // The 2 missing dates came from somewhere. If from the two best-scoring dates the pooled share is 95 / 98 =
    // 0.969388; if from the worst year, 95.16 / 98 = 0.971020. Both ends, and between, are possible.
    for (const share of [0.969388, 0.97, 0.97102]) {
      expect(parseDataQuality(broken((x) => (x.cross_vendor.within_thresholds.share_within[0] = share))).cross_vendor.within_thresholds.share_within[0]).toBe(share)
    }
  })
  it('accepts a threshold with no date that has a value, whatever its share (there is nothing to weigh)', () => {
    const d = broken((x) => {
      // unequal years: the sums of shares times dates are not exact in floating point, which a division by 0 would show
      x.cross_vendor.by_year.dates = [10, 20, 30, 40]
      x.cross_vendor.within_thresholds.share_within[1] = 0.956 // spot, weighted by those dates
      x.cross_vendor.within_thresholds.dates[0] = 0
      x.cross_vendor.within_thresholds.share_within[0] = 0
    })
    expect(parseDataQuality(d).cross_vendor.within_thresholds.dates[0]).toBe(0)
  })
  it('reads exactly the 13 flags of ADR-0009 §3, in bit order', () => {
    expect(parseDataQuality(dataQualityFixture).flag_names).toEqual([...FLAG_NAMES])
    expect(FLAG_NAMES).toHaveLength(13)
    expect(FLAG_NAMES[11]).toBe('VENDOR_IV_INVALID')
  })
})

describe('parseDataQuality: rejects', () => {
  it.each([null, undefined, 3, 'text', [], true])('a non-object root (%j)', (bad) => {
    rejects(parseDataQuality, bad, 'data_quality: expected an object')
  })
  it.each([
    'schema_version',
    'generated_at',
    'source_commit',
    'label',
    'flag_names',
    'flag_descriptions',
    'flags_by_year',
    'sources',
    'calendar',
    'cross_vendor',
    'gate',
  ])('a missing top-level key %s', (key) => {
    const d = broken((x) => {
      delete x[key]
    })
    rejects(parseDataQuality, d, `data_quality: missing required key "${key}"`)
  })
  it('an unsupported schema major', () => {
    rejects(parseDataQuality, broken((x) => (x.schema_version = '1.0.0')), 'data_quality.schema_version: unsupported major version 1')
  })
  it('an impossible generated_at', () => {
    rejects(parseDataQuality, broken((x) => (x.generated_at = '2026-02-30T00:00:00Z')), 'data_quality.generated_at')
  })
  it('a source_commit that is not a hash', () => {
    rejects(parseDataQuality, broken((x) => (x.source_commit = 'nope')), 'data_quality.source_commit')
  })
  it('an empty label', () => {
    rejects(parseDataQuality, broken((x) => (x.label = ' ')), 'data_quality.label: expected a non-empty string')
  })

  describe('flag names and descriptions', () => {
    it('flag_names that is not an array', () => {
      rejects(parseDataQuality, broken((x) => ((x as Obj).flag_names = 'BID_NULL')), 'data_quality.flag_names: expected an array')
    })
    it('no flag names at all', () => {
      rejects(parseDataQuality, broken((x) => (x.flag_names = [])), 'data_quality.flag_names: has 0 names but this app reads the 13 flags')
    })
    it('fewer flag names than the 13', () => {
      rejects(parseDataQuality, broken((x) => x.flag_names.pop()), 'data_quality.flag_names: has 12 names but this app reads the 13 flags')
    })
    it('more flag names than the 13', () => {
      rejects(parseDataQuality, broken((x) => x.flag_names.push('EXTRA')), 'data_quality.flag_names: has 14 names but this app reads the 13 flags')
    })
    it('the name bit 11 had before the M1 review (VENDOR_IV_NULL), naming the flag it should be', () => {
      rejects(
        parseDataQuality,
        broken((x) => (x.flag_names[11] = 'VENDOR_IV_NULL')),
        'data_quality.flag_names[11]: expected "VENDOR_IV_INVALID" (flag 11 in bit order), got "VENDOR_IV_NULL"',
      )
    })
    it('the 13 names in another order', () => {
      rejects(
        parseDataQuality,
        broken((x) => {
          ;[x.flag_names[0], x.flag_names[1]] = [x.flag_names[1], x.flag_names[0]]
        }),
        'data_quality.flag_names[0]: expected "BID_NULL" (flag 0 in bit order), got "ASK_NULL"',
      )
    })
    it.each([['an empty string', ''], ['a number', 7]])('a flag name that is %s', (_name, bad) => {
      rejects(
        parseDataQuality,
        broken((x) => (x.flag_names[1] = bad)),
        'data_quality.flag_names[1]: expected a non-empty string',
      )
    })
    it('a repeated flag name, naming the second occurrence', () => {
      rejects(
        parseDataQuality,
        broken((x) => (x.flag_names[2] = 'BID_NULL')),
        'data_quality.flag_names[2]: duplicate flag name "BID_NULL"',
      )
    })
    it('flag_descriptions that is not an array', () => {
      rejects(parseDataQuality, broken((x) => ((x as Obj).flag_descriptions = 'x')), 'data_quality.flag_descriptions: expected an array')
    })
    it('a description list of another length than the flag names', () => {
      rejects(
        parseDataQuality,
        broken((x) => x.flag_descriptions.pop()),
        'data_quality.flag_descriptions: has 12 entries but flag_names has 13',
      )
    })
    it('an empty description', () => {
      rejects(
        parseDataQuality,
        broken((x) => (x.flag_descriptions[3] = '')),
        'data_quality.flag_descriptions[3]: expected a non-empty string',
      )
    })
  })

  describe('column-wise tables', () => {
    it.each(['flags_by_year', 'sources', 'calendar'])('%s that is not an object', (key) => {
      rejects(parseDataQuality, broken((x) => (x[key] = [1, 2])), `data_quality.${key}: expected an object`)
    })
    it.each([
      ['sources', 'source'],
      ['sources', 'rows'],
      ['sources', 'dates'],
      ['calendar', 'action'],
      ['flags_by_year', 'year'],
      ['cross_vendor.distributions', 'p95'],
      ['cross_vendor.within_thresholds', 'share_within'],
      ['cross_vendor.by_year', 'spot_optionsdx_vs_close_median_bp'],
      ['gate.thresholds', 'worst'],
    ])('%s without its %s column', (table, column) => {
      const d = broken((x) => {
        delete tableOf(x, table)[column]
      })
      rejects(parseDataQuality, d, `data_quality.${table}: missing required key "${column}"`)
    })
    it('a column that is not an array', () => {
      rejects(parseDataQuality, broken((x) => ((x.sources as Obj).rows = 5)), 'data_quality.sources.rows: expected an array')
    })
    it('a table with no rows', () => {
      const d = broken((x) => {
        x.sources = { source: [], rows: [], dates: [] }
      })
      rejects(parseDataQuality, d, 'data_quality.sources.source: needs at least 1 row')
    })
    it('a ragged column, naming it and the first column', () => {
      rejects(
        parseDataQuality,
        broken((x) => x.sources.dates.push(9)),
        'data_quality.sources.dates: has 3 values but "source" has 2',
      )
    })
    it.each([
      ['an empty string', ''],
      ['a number', 4],
      ['null', null],
    ])('a text cell that is %s', (_name, bad) => {
      rejects(parseDataQuality, broken((x) => (x.sources.source[1] = bad)), 'data_quality.sources.source[1]: expected a non-empty string')
    })
    it.each([
      ['a negative number', -1],
      ['a fraction', 2.5],
      ['NaN', NaN],
      ['Infinity', Infinity],
      ['a string', '7'],
      ['null', null],
    ])('a count cell that is %s', (_name, bad) => {
      const d = broken((x) => (x.sources.rows[0] = bad))
      let err: unknown
      try {
        parseDataQuality(d)
      } catch (e) {
        err = e
      }
      expect(err).toBeInstanceOf(ContractError)
      expect((err as Error).message).toMatch(/^data_quality\.sources\.rows\[0\]: expected a (finite number|whole number of at least 0)/)
    })
    it('a count that is a fraction says it must be whole; one that is negative says at least 0', () => {
      rejects(parseDataQuality, broken((x) => (x.sources.rows[0] = 2.5)), 'expected a whole number of at least 0, got 2.5')
      rejects(parseDataQuality, broken((x) => (x.sources.rows[0] = -1)), 'expected a whole number of at least 0, got -1')
      rejects(parseDataQuality, broken((x) => (x.sources.rows[0] = NaN)), 'expected a finite number, got NaN')
    })
    it.each([1899, 2201, 2020.5, '2020'])('a year cell of %j', (bad) => {
      const d = broken((x) => (x.flags_by_year.year[2] = bad))
      let err: unknown
      try {
        parseDataQuality(d)
      } catch (e) {
        err = e
      }
      expect(err).toBeInstanceOf(ContractError)
      expect((err as Error).message).toMatch(/^data_quality\.flags_by_year\.year\[2\]: expected a (calendar year|finite number)/)
    })
    it('accepts the first and last calendar years', () => {
      const d = broken((x) => (x.flags_by_year.year = [1900, 2200, 2010, 2011]))
      expect(parseDataQuality(d).flags_by_year.year).toEqual([1900, 2200, 2010, 2011])
    })
    it.each([
      ['NaN', NaN],
      ['Infinity', Infinity],
      ['a string', '0.5'],
      ['null', null],
    ])('a number cell that is %s', (_name, bad) => {
      rejects(
        parseDataQuality,
        broken((x) => (x.cross_vendor.distributions.mean[0] = bad)),
        'data_quality.cross_vendor.distributions.mean[0]: expected a finite number',
      )
    })
    it.each([-0.01, 1.01])('a share cell of %d (must lie between 0 and 1)', (bad) => {
      rejects(
        parseDataQuality,
        broken((x) => (x.cross_vendor.within_thresholds.share_within[0] = bad)),
        `data_quality.cross_vendor.within_thresholds.share_within[0]: expected a share between 0 and 1, got ${bad}`,
      )
    })
  })

  describe('every column is checked for its own kind', () => {
    // [table, column, kind] for each column the contract names; one bad cell per column.
    const COLUMNS: [string, string, 'text' | 'count' | 'year' | 'share' | 'number' | 'flag'][] = [
      ['flags_by_year', 'source', 'text'],
      ['flags_by_year', 'year', 'year'],
      ['flags_by_year', 'rows', 'count'],
      ['sources', 'source', 'text'],
      ['sources', 'rows', 'count'],
      ['sources', 'dates', 'count'],
      ['calendar', 'source', 'text'],
      ['calendar', 'action', 'text'],
      ['calendar', 'dates', 'count'],
      ['calendar', 'rows', 'count'],
      ['cross_vendor.distributions', 'key', 'text'],
      ['cross_vendor.distributions', 'label', 'text'],
      ['cross_vendor.distributions', 'unit', 'text'],
      ['cross_vendor.distributions', 'n', 'count'],
      ...['mean', 'mean_abs', 'p05', 'p25', 'median', 'p75', 'p95'].map((c): [string, string, 'number'] => ['cross_vendor.distributions', c, 'number']),
      ['cross_vendor.within_thresholds', 'key', 'text'],
      ['cross_vendor.within_thresholds', 'label', 'text'],
      ['cross_vendor.within_thresholds', 'threshold', 'number'],
      ['cross_vendor.within_thresholds', 'unit', 'text'],
      ['cross_vendor.within_thresholds', 'dates', 'count'],
      ['cross_vendor.within_thresholds', 'share_within', 'share'],
      ['cross_vendor.by_year', 'year', 'year'],
      ['cross_vendor.by_year', 'dates', 'count'],
      ['cross_vendor.by_year', 'iv30_share_within', 'share'],
      ['cross_vendor.by_year', 'spot_dolthub_share_within', 'share'],
      ['cross_vendor.by_year', 'spot_dolthub_vs_close_median_bp', 'number'],
      ['cross_vendor.by_year', 'spot_optionsdx_vs_close_median_bp', 'number'],
      ['gate.thresholds', 'rule', 'text'],
      ['gate.thresholds', 'source', 'text'],
      ['gate.thresholds', 'what', 'text'],
      ['gate.thresholds', 'bound', 'text'],
      ['gate.thresholds', 'limit', 'number'],
      ['gate.thresholds', 'worst', 'number'],
      ['gate.thresholds', 'unit', 'text'],
    ]
    const BAD = { text: '', count: 1.5, year: 1850, share: 2, number: 'x', flag: 'yes' } as const
    const SAYS = {
      text: 'expected a non-empty string',
      count: 'expected a whole number of at least 0, got 1.5',
      year: 'expected a calendar year, got 1850',
      share: 'expected a share between 0 and 1, got 2',
      number: 'expected a finite number, got x',
      flag: 'expected true or false, got yes',
    } as const
    it.each(COLUMNS)('%s.%s refuses a bad %s cell', (table, column, kind) => {
      const d = broken((x) => {
        tableOf(x, table)[column][1] = BAD[kind]
      })
      rejects(parseDataQuality, d, `data_quality.${table}.${column}[1]: ${SAYS[kind]}`)
    })
  })

  describe('flags_by_year counts and shares', () => {
    it.each(['counts', 'shares'])('without its %s block', (block) => {
      rejects(
        parseDataQuality,
        broken((x) => {
          delete (x.flags_by_year as Obj)[block]
        }),
        `data_quality.flags_by_year: missing required key "${block}"`,
      )
    })
    it.each(['counts', 'shares'])('a %s block that is not an object', (block) => {
      rejects(parseDataQuality, broken((x) => ((x.flags_by_year as Obj)[block] = [1])), `data_quality.flags_by_year.${block}: expected an object`)
    })
    it.each(['counts', 'shares'])('a flag missing from %s', (block) => {
      rejects(
        parseDataQuality,
        broken((x) => {
          delete (x.flags_by_year as unknown as Record<string, Cols>)[block].CROSSED
        }),
        `data_quality.flags_by_year.${block}: missing required key "CROSSED"`,
      )
    })
    it.each(['counts', 'shares'])('a %s column that is not an array', (block) => {
      rejects(
        parseDataQuality,
        broken((x) => ((x.flags_by_year as unknown as Record<string, Obj>)[block].ZERO_BID = 7)),
        `data_quality.flags_by_year.${block}.ZERO_BID: expected an array`,
      )
    })
    it.each(['counts', 'shares'])('a %s column of the wrong length', (block) => {
      rejects(
        parseDataQuality,
        broken((x) => (x.flags_by_year as unknown as Record<string, Cols>)[block].ZERO_BID.pop()),
        `data_quality.flags_by_year.${block}.ZERO_BID: has 3 values but the table has 4 rows`,
      )
    })
    it('a counts cell that is not a whole number', () => {
      rejects(
        parseDataQuality,
        broken((x) => (x.flags_by_year.counts.CROSSED[3] = 1.5)),
        'data_quality.flags_by_year.counts.CROSSED[3]: expected a whole number of at least 0, got 1.5',
      )
    })
    it('a shares cell above 1 (a percentage written as a share)', () => {
      rejects(
        parseDataQuality,
        broken((x) => (x.flags_by_year.shares.ZERO_BID[1] = 10)),
        'data_quality.flags_by_year.shares.ZERO_BID[1]: expected a share between 0 and 1, got 10',
      )
    })
    it('more quotes carrying a flag than the row has quotes, naming the flag and the row', () => {
      rejects(
        parseDataQuality,
        broken((x) => (x.flags_by_year.counts.ZERO_BID[1] = 1001)),
        'data_quality.flags_by_year.counts.ZERO_BID[1]: 1001 quotes carry the flag but the row has only 1000',
      )
    })
    it('a share that is not counts / rows, naming the flag, the row and what it should be', () => {
      // ZERO_BID in 2010: 100 of 1000 quotes is 0.1; the file says 0.2, which is a valid share on its own
      rejects(
        parseDataQuality,
        broken((x) => (x.flags_by_year.shares.ZERO_BID[1] = 0.2)),
        'data_quality.flags_by_year.shares.ZERO_BID[1]: is 0.2 but 100 of 1000 quotes is 0.100000',
      )
    })
    it('a share that is off by more than the rounding of its 6 decimals', () => {
      rejects(
        parseDataQuality,
        broken((x) => (x.flags_by_year.shares.BID_NULL[1] = 0.030002)), // 30 / 1000 = 0.03, 2e-6 away
        'data_quality.flags_by_year.shares.BID_NULL[1]: is 0.030002 but 30 of 1000 quotes is 0.030000',
      )
    })
    it('a share above 0 for a source-year that has no quotes', () => {
      rejects(
        parseDataQuality,
        broken((x) => {
          x.flags_by_year.rows[1] = 0
          for (const name of FLAG_NAMES) {
            x.flags_by_year.counts[name][1] = 0
            x.flags_by_year.shares[name][1] = 0
          }
          x.flags_by_year.shares.CROSSED[1] = 0.5
        }),
        'data_quality.flags_by_year.shares.CROSSED[1]: is 0.5 but 0 of 0 quotes is 0.000000',
      )
    })
    it('a counts column changed without its shares (the page shows the shares, so they would disagree with the counts)', () => {
      rejects(
        parseDataQuality,
        broken((x) => (x.flags_by_year.counts.STALE[3] = 800)), // 800 / 4000 = 0.2, the file's share stays 0.02
        'data_quality.flags_by_year.shares.STALE[3]: is 0.02 but 800 of 4000 quotes is 0.200000',
      )
    })
  })

  describe('cross_vendor', () => {
    it('cross_vendor that is not an object', () => {
      rejects(parseDataQuality, broken((x) => ((x as Obj).cross_vendor = 'agree')), 'data_quality.cross_vendor: expected an object')
    })
    it.each(['label', 'overlap_dates', 'basis', 'distributions', 'within_thresholds', 'by_year'])('without %s', (key) => {
      rejects(
        parseDataQuality,
        broken((x) => {
          delete x.cross_vendor[key]
        }),
        `data_quality.cross_vendor: missing required key "${key}"`,
      )
    })
    it('a file of the earlier shape (tolerances and a verdict, no within_thresholds), naming the first key it lacks', () => {
      rejects(
        parseDataQuality,
        broken((x) => {
          const cv = x.cross_vendor as Obj
          delete cv.within_thresholds
          delete cv.by_year
          delete cv.basis
          x.cross_vendor.tolerances = { check: ['iv30'] }
          x.cross_vendor.passed = true
          x.cross_vendor.failures = []
        }),
        'data_quality.cross_vendor: missing required key "within_thresholds"',
      )
    })
    it('an empty label', () => {
      rejects(parseDataQuality, broken((x) => (x.cross_vendor.label = '')), 'data_quality.cross_vendor.label: expected a non-empty string')
    })
    it('an empty basis', () => {
      rejects(parseDataQuality, broken((x) => (x.cross_vendor.basis = ' ')), 'data_quality.cross_vendor.basis: expected a non-empty string')
    })
    it.each([-1, 2.5, '100'])('overlap_dates of %j', (bad) => {
      const d = broken((x) => (x.cross_vendor.overlap_dates = bad))
      let err: unknown
      try {
        parseDataQuality(d)
      } catch (e) {
        err = e
      }
      expect(err).toBeInstanceOf(ContractError)
      expect((err as Error).message).toMatch(/^data_quality\.cross_vendor\.overlap_dates: expected a (whole number of at least 0|finite number)/)
    })
    it('quantiles out of order, naming the row and its key', () => {
      rejects(
        parseDataQuality,
        broken((x) => (x.cross_vendor.distributions.median[1] = -30)),
        'data_quality.cross_vendor.distributions: row 1 ("spot_dolthub_vs_close_bp") has quantiles out of order: -18, -4.5, -30, 7.5, 21',
      )
    })
    it.each(['p05', 'p25', 'median', 'p75', 'p95'])('a %s that breaks the order', (column) => {
      const d = broken((x) => {
        const values = x.cross_vendor.distributions[column] as number[]
        values[0] = column === 'p05' ? 99 : -99
      })
      rejects(parseDataQuality, d, 'data_quality.cross_vendor.distributions: row 0 ("iv30_diff_pts_dolthub_minus_optionsdx") has quantiles out of order')
    })
    it('a threshold table with no rows', () => {
      rejects(
        parseDataQuality,
        broken((x) => {
          x.cross_vendor.within_thresholds = { key: [], label: [], threshold: [], unit: [], dates: [], share_within: [] }
        }),
        'data_quality.cross_vendor.within_thresholds.key: needs at least 1 row',
      )
    })
    it('a by-year column of another length than the years', () => {
      rejects(
        parseDataQuality,
        broken((x) => x.cross_vendor.by_year.iv30_share_within.pop()),
        'data_quality.cross_vendor.by_year.iv30_share_within: has 3 values but "year" has 4',
      )
    })
  })

  describe('gate', () => {
    it('gate that is not an object', () => {
      rejects(parseDataQuality, broken((x) => ((x as Obj).gate = null)), 'data_quality.gate: expected an object')
    })
    it.each(['thresholds', 'passed', 'failures'])('without %s', (key) => {
      rejects(
        parseDataQuality,
        broken((x) => {
          delete x.gate[key]
        }),
        `data_quality.gate: missing required key "${key}"`,
      )
    })
    it.each(['avg', 'MAX', '', 3])('a bound of %j', (bad) => {
      const d = broken((x) => (x.gate.thresholds.bound[2] = bad))
      let err: unknown
      try {
        parseDataQuality(d)
      } catch (e) {
        err = e
      }
      expect(err).toBeInstanceOf(ContractError)
      expect((err as Error).message).toMatch(/^data_quality\.gate\.thresholds\.bound\[2\]: expected (a non-empty string|"max" or "min")/)
    })
    it('a bound of "avg" is named in the message', () => {
      rejects(
        parseDataQuality,
        broken((x) => (x.gate.thresholds.bound[1] = 'avg')),
        'data_quality.gate.thresholds.bound[1]: expected "max" or "min", got "avg"',
      )
    })
    it('a passed that is not true or false', () => {
      rejects(parseDataQuality, broken((x) => (x.gate.passed = 1)), 'data_quality.gate.passed: expected true or false')
    })
    it('failures that is not an array', () => {
      rejects(parseDataQuality, broken((x) => (x.gate.failures = 'none')), 'data_quality.gate.failures: expected an array')
    })
    it('passed true beside a listed failure', () => {
      rejects(
        parseDataQuality,
        broken((x) => (x.gate.failures = ['a', 'b'])),
        'data_quality.gate.passed: is true but 2 failure(s) are listed',
      )
    })
    it('passed false with no failure listed', () => {
      rejects(parseDataQuality, broken((x) => (x.gate.passed = false)), 'data_quality.gate.passed: is false but no failure is listed')
    })
    it('passed true although a "max" row\'s worst is above its limit, naming the row', () => {
      // row 3: optionsdx VENDOR_IV_INVALID, limit 0.12; a worst of 0.13 broke it
      rejects(
        parseDataQuality,
        broken((x) => (x.gate.thresholds.worst[3] = 0.13)),
        'data_quality.gate.passed: is true but thresholds row 3 (optionsdx max_share: "VENDOR_IV_INVALID share of a year\'s quotes") has worst 0.13 beyond its max limit 0.12',
      )
    })
    it('passed true although a "min" row\'s worst is below its limit, naming the row', () => {
      // row 11: dolthub min_dates_per_year for 2024, limit 140; a year of 139 dates broke it
      rejects(
        parseDataQuality,
        broken((x) => (x.gate.thresholds.worst[11] = 139)),
        'data_quality.gate.passed: is true but thresholds row 11 (dolthub min_dates_per_year: "snapshot dates in 2024 (Mon/Wed/Fri to 09-09 with no dates 07-30 to 08-09, then daily)") has worst 139 beyond its min limit 140',
      )
    })
    it('reports the first row beyond its limit when several are', () => {
      rejects(
        parseDataQuality,
        broken((x) => {
          x.gate.thresholds.worst[20] = 51
          x.gate.thresholds.worst[2] = 0.02
        }),
        'thresholds row 2 (optionsdx max_share',
      )
    })
    it('accepts a worst beyond its limit when the gate says it failed (the failure is the reason)', () => {
      const d = broken((x) => {
        x.gate.passed = false
        x.gate.failures = ['optionsdx 2010: VENDOR_IV_INVALID on 13.00% of rows (limit 12%)']
        x.flags_by_year.counts.VENDOR_IV_INVALID[1] = 130 // 130 / 1000: the year the gate's worst comes from
        x.flags_by_year.shares.VENDOR_IV_INVALID[1] = 0.13
        x.gate.thresholds.worst[3] = 0.13
      })
      expect(parseDataQuality(d).gate.thresholds.worst[3]).toBe(0.13)
    })
  })

  describe('tables that contradict each other', () => {
    const parse = parseDataQuality
    const FIRST = 'data_quality.flags_by_year'

    /** The gate with row `i` of every column removed. */
    const dropGateRow = (x: Doc, i: number) => Object.values(x.gate.thresholds).forEach((column) => column.splice(i, 1))
    /** The gate as failed, so a worst beyond its limit is not itself the contradiction. */
    const failGate = (x: Doc) => {
      x.gate.passed = false
      x.gate.failures = ['the gate failed']
    }

    describe('flags_by_year, sources and calendar', () => {
      it('a (source, year) row that repeats, naming the row and where it first was', () => {
        rejects(parse, broken((x) => (x.flags_by_year.year[3] = 2011)), `${FIRST}.year[3]: duplicate row for optionsdx 2011 (first at row 2)`)
      })
      it('accepts one year in two sources: the row is the pair', () => {
        const d = broken((x) => (x.flags_by_year.year[1] = 2021)) // dolthub 2021 is row 0
        expect(parse(d).flags_by_year.year).toEqual([2021, 2021, 2011, 2012])
      })
      it('a source whose quotes are not the sum of its years, naming both numbers', () => {
        rejects(parse, broken((x) => (x.sources.rows[1] = 6999)), 'data_quality.sources.rows[1]: is 6999 for optionsdx but flags_by_year has 7000 quotes of it')
        rejects(parse, broken((x) => (x.sources.rows[0] = 1999)), 'data_quality.sources.rows[0]: is 1999 for dolthub but flags_by_year has 2000 quotes of it')
      })
      it('a source of flags_by_year that sources does not list', () => {
        rejects(parse, broken((x) => (x.sources.source[1] = 'kaggle')), `${FIRST}.source[1]: "optionsdx" has no row in sources`)
      })
      it('a source listed twice in sources', () => {
        rejects(parse, broken((x) => (x.sources.source[1] = 'dolthub')), 'data_quality.sources.source[1]: duplicate row for dolthub (first at row 0)')
      })
      it.each(['teleport', 'relabel', 'Session'])('a calendar action of "%s", naming the two there are', (bad) => {
        rejects(parse, broken((x) => (x.calendar.action[0] = bad)), `data_quality.calendar.action[0]: expected "session" or "drop", got "${bad}"`)
      })
      it('a (source, action) row that repeats in the calendar', () => {
        rejects(parse, broken((x) => (x.calendar.action[0] = 'session')), 'data_quality.calendar.action[1]: duplicate row for dolthub session (first at row 0)')
      })
    })

    describe('the rule set of the gate', () => {
      it.each(['vibes', 'constructor', '__proto__'])('a rule of "%s", which the gate does not have', (bad) => {
        rejects(parse, broken((x) => (x.gate.thresholds.rule[0] = bad)), `data_quality.gate.thresholds.rule[0]: "${bad}" is not a rule of the quality gate (the gate has max_share, `)
      })
      it('a bound turned round for its rule', () => {
        rejects(parse, broken((x) => (x.gate.thresholds.bound[0] = 'min')), 'data_quality.gate.thresholds.bound[0]: max_share is a "max" limit, got "min"')
        rejects(parse, broken((x) => (x.gate.thresholds.bound[9] = 'max')), 'data_quality.gate.thresholds.bound[9]: min_dates_per_year is a "min" limit, got "max"')
      })
      it.each(['cboe', 'constructor'])('a source "%s", which the rule has no limit for', (bad) => {
        rejects(parse, broken((x) => (x.gate.thresholds.source[0] = bad)), `data_quality.gate.thresholds.source[0]: max_share has no limit for source "${bad}"`)
      })
      it('a source the rule limits for the other source only', () => {
        // the p99 of the underlying is an OptionsDX limit; DoltHub has no underlying price to take it from
        rejects(parse, broken((x) => (x.gate.thresholds.source[20] = 'dolthub')), 'data_quality.gate.thresholds.source[20]: max_underlying_p99_cents has no limit for source "dolthub"')
      })
      it('a share limit that names no flag', () => {
        rejects(parse, broken((x) => (x.gate.thresholds.what[0] = 'the bid is missing')), 'data_quality.gate.thresholds.what[0]: "the bid is missing" is not a share limit of optionsdx (it limits BID_NULL, ASK_NULL, CROSSED, VENDOR_IV_INVALID, UNDERLYING_MISMATCH)')
      })
      it('a share limit for a flag the source is not limited on', () => {
        rejects(
          parse,
          broken((x) => (x.gate.thresholds.what[5] = "UNDERLYING_MISMATCH share of a year's quotes")),
          'data_quality.gate.thresholds.what[5]: "UNDERLYING_MISMATCH share of a year\'s quotes" is not a share limit of dolthub (it limits BID_NULL, ASK_NULL, CROSSED, VENDOR_IV_INVALID)',
        )
      })
      it('two share limits for one flag of a source (a row swapped for a copy of another)', () => {
        rejects(parse, broken((x) => (x.gate.thresholds.what[1] = "BID_NULL share of a year's quotes")), 'data_quality.gate.thresholds.what[1]: optionsdx has two share limits for BID_NULL')
      })
      it('a row dropped, naming the rule, the source and the count it should have', () => {
        rejects(parse, broken((x) => dropGateRow(x, 20)), 'data_quality.gate.thresholds.rule: has 0 max_underlying_p99_cents row(s) for optionsdx but the gate has 1')
        rejects(parse, broken((x) => dropGateRow(x, 12)), 'data_quality.gate.thresholds.rule: has 3 min_dates_per_year row(s) for dolthub but the gate has 4')
      })
      it('a row added', () => {
        const d = broken((x) => {
          for (const column of Object.values(x.gate.thresholds)) column.push(column[20])
        })
        rejects(parse, d, 'data_quality.gate.thresholds.rule: has 2 max_underlying_p99_cents row(s) for optionsdx but the gate has 1')
      })
      it('has, in the contract, the rows of the exporter: 21 in all', () => {
        const rows = Object.values(GATE_RULES).flatMap((spec) => Object.values(spec.rows))
        expect(rows.reduce((a, b) => a + b, 0)).toBe(21)
        expect(GATE_SHARE_FLAGS.optionsdx).toHaveLength(GATE_RULES.max_share.rows.optionsdx)
        expect(GATE_SHARE_FLAGS.dolthub).toHaveLength(GATE_RULES.max_share.rows.dolthub)
      })
    })

    describe('a gate worst that the other tables do not bear out', () => {
      it('a share limit whose worst is far below a year in flags_by_year (the gate says 3.02%, a year shows 30%)', () => {
        const d = broken((x) => {
          x.flags_by_year.counts.BID_NULL[2] = 600 // 600 of the 2000 optionsdx quotes of 2011
          x.flags_by_year.shares.BID_NULL[2] = 0.3
        })
        rejects(parse, d, 'data_quality.gate.thresholds.worst[0]: is 0.03 for optionsdx BID_NULL, but its highest share in flags_by_year is 0.3')
      })
      it('a share limit whose worst is the share of another year than the highest', () => {
        rejects(parse, broken((x) => (x.gate.thresholds.worst[0] = 0.01)), 'worst[0]: is 0.01 for optionsdx BID_NULL, but its highest share in flags_by_year is 0.03')
      })
      it('a share limit whose worst is above the highest share', () => {
        rejects(parse, broken((x) => (x.gate.thresholds.worst[0] = 0.04)), 'worst[0]: is 0.04 for optionsdx BID_NULL, but its highest share in flags_by_year is 0.03')
      })
      it('a share limit whose worst comes from the other source\'s years', () => {
        // dolthub never has a BID_NULL quote in the fixture; optionsdx peaks at 0.03
        const d = broken((x) => {
          failGate(x)
          x.gate.thresholds.worst[5] = 0.03
        })
        rejects(parse, d, 'worst[5]: is 0.03 for dolthub BID_NULL, but its highest share in flags_by_year is 0')
      })
      it('is checked on a failed gate too', () => {
        rejects(parse, broken((x) => { failGate(x); x.gate.thresholds.worst[0] = 0.5 }), 'worst[0]: is 0.5 for optionsdx BID_NULL')
      })
      it('a share limit for a source that flags_by_year has no year of', () => {
        const d = broken((x) => {
          x.flags_by_year.source[0] = 'optionsdx' // dolthub 2021 becomes optionsdx 2021: dolthub has no year left
          x.flags_by_year.year[0] = 2009
          x.sources.rows = [0, 9000]
          x.gate.thresholds.worst[2] = 0.005 // that year's CROSSED share, now the highest of optionsdx
        })
        rejects(parse, d, 'data_quality.gate.thresholds.worst[5]: flags_by_year has no rows for dolthub, so BID_NULL has no share to compare')
      })
      it.each([
        ['optionsdx', 1, 14],
        ['dolthub', 0, 15],
      ])('a min_dates worst that is not the snapshot dates of %s in sources', (source, row, gateRow) => {
        const d = broken((x) => (x.sources.dates[row] = 7))
        rejects(parse, d, `worst[${gateRow}]: is ${row === 1 ? 6 : 3} for ${source} min_dates, but the other tables give 7`)
      })
      it.each([
        ['optionsdx', 2, 18, 1],
        ['dolthub', 0, 19, 2],
      ])('a max_dropped_dates worst that is not the dates %s drops in the calendar', (source, calendarRow, gateRow, worst) => {
        const d = broken((x) => (x.calendar.dates[calendarRow] = 5))
        rejects(parse, d, `worst[${gateRow}]: is ${worst} for ${source} max_dropped_dates, but the other tables give 5`)
      })
    })

    describe('cross_vendor', () => {
      it.each([
        ['passed', true],
        ['failures', []],
      ])('a "%s" key: the check reports measurements and has no verdict', (key, value) => {
        rejects(parse, broken((x) => (x.cross_vendor[key] = value)), `data_quality.cross_vendor.${key}: is a verdict, but the cross-vendor check reports measurements and has none`)
      })
      it('a distribution over more dates than the vendors overlap on', () => {
        rejects(
          parse,
          broken((x) => (x.cross_vendor.distributions.n[0] = 101)),
          'data_quality.cross_vendor.distributions.n[0]: 101 dates for "iv30_diff_pts_dolthub_minus_optionsdx" but the vendors overlap on only 100',
        )
      })
      it.each([
        ['a positive mean', 0, 0.25, 0.5],
        ['a negative mean', 1, 9, -9.25],
      ])('a mean of |gap| below the |mean|, with %s', (_name, row, meanAbs, mean) => {
        const d = broken((x) => {
          x.cross_vendor.distributions.mean_abs[row] = meanAbs
          x.cross_vendor.distributions.mean[row] = mean
        })
        rejects(parse, d, `data_quality.cross_vendor.distributions.mean_abs[${row}]: is ${meanAbs} for `)
      })
      it('accepts a mean of |gap| equal to the |mean| (all gaps of one sign), and a threshold of 0', () => {
        const d = broken((x) => {
          x.cross_vendor.distributions.mean_abs[0] = 0.5
          x.cross_vendor.distributions.mean[0] = -0.5
          x.cross_vendor.within_thresholds.threshold[0] = 0
        })
        expect(parse(d).cross_vendor.distributions.mean_abs[0]).toBe(0.5)
      })
      it('a negative threshold', () => {
        rejects(
          parse,
          broken((x) => (x.cross_vendor.within_thresholds.threshold[1] = -25)),
          'data_quality.cross_vendor.within_thresholds.threshold[1]: is -25 for "spot", but a threshold on |gap| cannot be negative',
        )
      })
      it('a threshold row counting more dates than the vendors overlap on', () => {
        rejects(
          parse,
          broken((x) => (x.cross_vendor.within_thresholds.dates[1] = 101)),
          'data_quality.cross_vendor.within_thresholds.dates[1]: 101 dates for "spot" but the vendors overlap on only 100',
        )
      })
      it.each([24, 26])('years that add up to %i dates when the overlap is 100', (first) => {
        rejects(
          parse,
          broken((x) => (x.cross_vendor.by_year.dates[0] = first)),
          `data_quality.cross_vendor.by_year.dates: sum to ${first + 75} but the vendors overlap on 100 dates`,
        )
      })
      it('a pooled share that is not the date-weighted share of the years, naming what it should be', () => {
        rejects(
          parse,
          broken((x) => (x.cross_vendor.within_thresholds.share_within[1] = 0.9)),
          'data_quality.cross_vendor.within_thresholds.share_within[1]: is 0.9 for "spot" but by_year.spot_dolthub_share_within, weighted by the dates of each year, gives 0.930000',
        )
      })
      it('a pooled share off by more than the rounding of its 6 decimals, and one that is not', () => {
        rejects(parse, broken((x) => (x.cross_vendor.within_thresholds.share_within[1] = 0.930002)), 'share_within[1]: is 0.930002 for "spot"')
        expect(parse(broken((x) => (x.cross_vendor.within_thresholds.share_within[1] = 0.9300008))).cross_vendor.within_thresholds.share_within[1]).toBe(0.9300008)
      })
      it('a pooled share a missing date cannot explain: 98 of 100 dates have an IV, so it lies between two bounds', () => {
        const said = 'weighted by the dates of each year, gives 0.969388 to 0.971020'
        rejects(parse, broken((x) => (x.cross_vendor.within_thresholds.share_within[0] = 0.9693)), said)
        rejects(parse, broken((x) => (x.cross_vendor.within_thresholds.share_within[0] = 0.9711)), said)
        rejects(parse, broken((x) => (x.cross_vendor.within_thresholds.share_within[0] = 0.96)), said)
      })
      it('weights each year by its dates, not by one vote a year', () => {
        const years = (x: Doc) => {
          x.cross_vendor.by_year.dates = [10, 20, 30, 40] // spot: (8.4 + 18.4 + 28.8 + 40) / 100 = 0.956, where the plain mean is 0.93
          x.cross_vendor.within_thresholds.share_within[0] = 0.984 // iv30: between 96.4 / 98 and 96.56 / 98
        }
        const ok = broken((x) => {
          years(x)
          x.cross_vendor.within_thresholds.share_within[1] = 0.956
        })
        expect(parse(ok).cross_vendor.within_thresholds.share_within).toEqual([0.984, 0.956])
        rejects(parse, broken(years), 'share_within[1]: is 0.93 for "spot" but by_year.spot_dolthub_share_within, weighted by the dates of each year, gives 0.956000')
      })
      it('takes the missing dates from the years that have them: a year with fewer dates than are missing gives all it has, then the next', () => {
        const years = (x: Doc) => {
          x.cross_vendor.by_year.dates = [40, 50, 1, 9]
          x.cross_vendor.by_year.iv30_share_within = [0.9, 0.5, 1, 0.8]
          x.cross_vendor.within_thresholds.share_within[1] = 0.8956 // spot: (36 + 46 + 0.96 + 9) / 100 with the fixture's shares
        }
        // 98 of 100 dates have an IV. Lowest pooled share: the missing two come from the 1 date at 1.0 and one at 0.9,
        // (69.2 - 1 - 0.9) / 98 = 0.686735. Highest: both from the 0.5 year, (69.2 - 1) / 98 = 0.695918.
        const at = (share: number) => broken((x) => { years(x); x.cross_vendor.within_thresholds.share_within[0] = share })
        expect(parse(at(0.686735)).cross_vendor.within_thresholds.share_within[0]).toBe(0.686735)
        expect(parse(at(0.695918)).cross_vendor.within_thresholds.share_within[0]).toBe(0.695918)
        rejects(parse, at(0.6862), 'gives 0.686735 to 0.695918')
        rejects(parse, at(0.6962), 'gives 0.686735 to 0.695918')
      })
      it('leaves a threshold row alone when the file gives no by-year column for its key', () => {
        const d = broken((x) => {
          x.cross_vendor.within_thresholds.key = ['a', 'b']
          x.cross_vendor.within_thresholds.share_within = [0.1, 0.2]
        })
        expect(parse(d).cross_vendor.within_thresholds.share_within).toEqual([0.1, 0.2])
      })
    })
  })
})

/** The table at a dotted path such as "cross_vendor.distributions", for tests that remove a column. */
function tableOf(d: Doc, path: string): Cols {
  return path.split('.').reduce<Obj>((node, key) => node[key] as Obj, d) as Cols
}

describe('assertDatasetMatchesEntry', () => {
  const entry = { name: 'illustrative_surface', path: 'illustrative_surface.json', schema_version: '0.1.0', description: 'x' }
  it('accepts a dataset whose schema_version equals the manifest entry', () => {
    expect(() => assertDatasetMatchesEntry(entry, { schema_version: '0.1.0' })).not.toThrow()
  })
  it.each(['0.1.1', '0.2.0', '0.0.9'])('rejects a dataset claiming %s when the manifest lists 0.1.0', (version) => {
    let err: unknown
    try {
      assertDatasetMatchesEntry(entry, { schema_version: version })
    } catch (e) {
      err = e
    }
    expect(err).toBeInstanceOf(ContractError)
    expect((err as Error).message).toBe(
      `illustrative_surface: the manifest lists schema_version "0.1.0" but illustrative_surface.json says "${version}"`,
    )
  })
})

describe('findDataset', () => {
  it('finds a dataset by name, returns undefined otherwise', () => {
    const m = parseManifest(manifestFixture)
    expect(findDataset(m, 'illustrative_surface')?.path).toBe('illustrative_surface.json')
    expect(findDataset(m, 'nope')).toBeUndefined()
  })
})

describe('commitState', () => {
  it.each([
    ['a1b2c3d4e5f6', 'clean'],
    ['a1b2c3d4e5f6-dirty', 'dirty'],
    ['uncommitted', 'uncommitted'],
  ])('%s -> %s', (sha, state) => {
    expect(commitState(sha)).toBe(state)
  })
})
