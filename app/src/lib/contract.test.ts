import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  ContractError,
  MAX_IV,
  SUPPORTED_MAJOR,
  assertDatasetMatchesEntry,
  commitState,
  findDataset,
  parseIllustrativeSurface,
  parseManifest,
} from './contract'
import manifestFixture from '../test/fixtures/manifest.json'
import surfaceFixture from '../test/fixtures/illustrative_surface.json'

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
    rejects(parseManifest, m, 'manifest.datasets[1].name: duplicate dataset name "illustrative_surface"')
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
