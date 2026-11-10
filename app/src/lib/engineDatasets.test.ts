/**
 * The contract of blotter.json and positions_timeline.json (milestone 3): every rule of the dataset spec has a case that
 * breaks it and a case on its edge that passes. A fixture file is parsed, then one thing is changed, and the parser must
 * name the path and the problem of that one thing.
 */
import { describe, expect, it } from 'vitest'
import {
  BLOTTER_UNITS,
  BLOTTER_UNIT_KEYS,
  ContractError,
  ENGINE_DATASETS_MIN_VERSION,
  ENGINE_RUN_KEYS,
  EVENT_TYPES,
  EXIT_REASONS,
  FILL_INTENTS,
  POSITIONS_TIMELINE_UNITS,
  POSITIONS_TIMELINE_UNIT_KEYS,
  parseBlotter,
  parsePositionsTimeline,
} from './contract'
import blotterFixture from '../test/fixtures/blotter.json'
import positionsFixture from '../test/fixtures/positions_timeline.json'

type Obj = Record<string, unknown>
type Run = Obj
type BlotterDoc = Obj & { run: Run; units: Obj; fills: Obj[]; events: Obj[] }
type PositionsDoc = Obj & { run: Run; units: Obj; positions: (Obj & { legs: Obj[] })[]; dates: unknown[]; open_count: unknown[] }

const copyBlotter = (): BlotterDoc => JSON.parse(JSON.stringify(blotterFixture)) as BlotterDoc
const copyPositions = (): PositionsDoc => JSON.parse(JSON.stringify(positionsFixture)) as PositionsDoc

/** The fixture with one change applied. */
function brokenBlotter(change: (d: BlotterDoc) => void): BlotterDoc {
  const d = copyBlotter()
  change(d)
  return d
}
function brokenPositions(change: (d: PositionsDoc) => void): PositionsDoc {
  const d = copyPositions()
  change(d)
  return d
}

/** Assert parse(raw) throws a ContractError whose message contains `fragment`. */
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

const rejectsB = (raw: unknown, fragment: string): void => rejects(parseBlotter, raw, fragment)
const rejectsP = (raw: unknown, fragment: string): void => rejects(parsePositionsTimeline, raw, fragment)

const HEX64_A = 'a'.repeat(64)
const COMMIT = 'e1067ebdfbded211745ed7a12f08b7c80b6ca029'
const OSI = 'SPY   150123C00205000'

// ---------------------------------------------------------------- what both datasets open with

const DATASETS = [
  { name: 'blotter', parse: parseBlotter as (raw: unknown) => unknown, copy: copyBlotter, fixture: blotterFixture, unitKeys: BLOTTER_UNIT_KEYS, units: BLOTTER_UNITS },
  {
    name: 'positions_timeline',
    parse: parsePositionsTimeline as (raw: unknown) => unknown,
    copy: copyPositions,
    fixture: positionsFixture,
    unitKeys: POSITIONS_TIMELINE_UNIT_KEYS,
    units: POSITIONS_TIMELINE_UNITS,
  },
] as const

describe.each(DATASETS)('$name: the envelope, the run block, the units and the label', ({ name, parse, copy, fixture, unitKeys, units }) => {
  const reject = (raw: unknown, fragment: string): void => rejects(parse, raw, fragment)
  /** The fixture with `change` applied to its (shared) top-level object. */
  const broken = (change: (d: Obj & { run: Run; units: Obj }) => void): unknown => {
    const d = copy() as unknown as Obj & { run: Run; units: Obj }
    change(d)
    return d
  }

  it('returns the fixture unchanged (every field survives)', () => {
    expect(parse(fixture)).toEqual(fixture)
  })

  it('reads the run block in ENGINE_RUN_KEYS order, fifteen keys', () => {
    const run = (parse(fixture) as { run: Obj }).run
    expect(Object.keys(run)).toEqual([...ENGINE_RUN_KEYS])
    expect(ENGINE_RUN_KEYS).toHaveLength(15)
  })

  it('drops unknown keys, at the top, in run and in units (a MINOR bump may add fields)', () => {
    const parsed = parse(
      broken((d) => {
        d.future = 1
        d.run.future = 'x'
        d.units.future = 'x'
      }),
    ) as Obj & { run: Obj; units: Obj }
    expect(parsed).not.toHaveProperty('future')
    expect(parsed.run).not.toHaveProperty('future')
    expect(parsed.units).not.toHaveProperty('future')
  })

  it('knows the schema version that introduced the file', () => {
    expect(ENGINE_DATASETS_MIN_VERSION).toBe('0.4.0')
    expect((fixture as Obj).schema_version).toBe('0.4.0')
  })

  it.each(['0.4.1', '0.5.0', '0.10.0'])('accepts the later MINOR/PATCH version %s (compared as numbers, not as text)', (version) => {
    expect((parse(broken((d) => void (d.schema_version = version))) as Obj).schema_version).toBe(version)
  })

  it.each(['0.3.0', '0.3.9', '0.0.1'])('refuses the version %s, older than the one that introduced the file', (version) => {
    reject(
      broken((d) => void (d.schema_version = version)),
      `${name}.schema_version: "${version}" is older than 0.4.0, the version that introduced this file`,
    )
  })

  it('refuses another major version, a version that is not MAJOR.MINOR.PATCH and a missing one', () => {
    reject(broken((d) => void (d.schema_version = '1.0.0')), `${name}.schema_version: unsupported major version 1`)
    reject(broken((d) => void (d.schema_version = '0.4')), `${name}.schema_version: "0.4" is not MAJOR.MINOR.PATCH`)
    reject(broken((d) => void delete d.schema_version), `${name}: missing required key "schema_version"`)
  })

  it.each([
    ['null', null],
    ['an array', []],
    ['a string', 'x'],
  ])('refuses %s in place of the file', (_what, raw) => {
    reject(raw, `${name}: expected an object`)
  })

  it('refuses a generated_at that is not a real timestamp, and a source_commit that is not a commit', () => {
    reject(broken((d) => void (d.generated_at = '2026-02-30T00:00:00Z')), `${name}.generated_at: "2026-02-30T00:00:00Z" is not an ISO-8601 timestamp`)
    reject(broken((d) => void delete d.generated_at), `${name}: missing required key "generated_at"`)
    reject(broken((d) => void (d.source_commit = 'main')), `${name}.source_commit: "main" is not <sha>, <sha>-dirty or uncommitted`)
  })

  describe('run', () => {
    it('is required, and an object', () => {
      reject(broken((d) => void delete (d as Obj).run), `${name}: missing required key "run"`)
      reject(broken((d) => void ((d as Obj).run = [])), `${name}.run: expected an object`)
    })

    it.each([...ENGINE_RUN_KEYS])('needs the key %s', (key) => {
      reject(broken((d) => void delete d.run[key]), `${name}.run: missing required key "${key}"`)
    })

    it.each(['run_id', 'config_hash', 'data_fingerprint'])('refuses a %s that is not 64 lowercase hex digits', (key) => {
      for (const bad of ['a'.repeat(63), 'a'.repeat(65), 'A'.repeat(64), `${'a'.repeat(63)}g`, `${'a'.repeat(63)} `]) {
        reject(
          broken((d) => void (d.run[key] = bad)),
          `${name}.run.${key}: "${bad}" is not a SHA-256 (64 lowercase hex digits)`,
        )
      }
      reject(broken((d) => void (d.run[key] = 7)), `${name}.run.${key}: expected a non-empty string`)
      reject(broken((d) => void (d.run[key] = '')), `${name}.run.${key}: expected a non-empty string`)
    })

    it.each(['a'.repeat(64), '0'.repeat(64)])('accepts the 64 hex digits %s as run_id', (id) => {
      expect(((parse(broken((d) => void (d.run.run_id = id))) as { run: Obj }).run).run_id).toBe(id)
    })

    it('accepts an engine commit of 40 hex digits, with or without -dirty', () => {
      for (const commit of [COMMIT, `${COMMIT}-dirty`, '0123456789abcdef'.repeat(2) + '01234567']) {
        expect(((parse(broken((d) => void (d.run.engine_commit = commit))) as { run: Obj }).run).engine_commit).toBe(commit)
      }
    })

    it.each([
      ['39 digits', COMMIT.slice(1)],
      ['41 digits', `${COMMIT}0`],
      ['64 digits (a SHA-256 is not the engine commit)', HEX64_A],
      ['upper case', COMMIT.toUpperCase()],
      ['a non-hex digit', `${COMMIT.slice(1)}g`],
      ['-DIRTY', `${COMMIT}-DIRTY`],
      ['a bare dash', `${COMMIT}-`],
      ['-dirty twice', `${COMMIT}-dirty-dirty`],
      ['-dirty first', `-dirty${COMMIT}`],
      ['uncommitted', 'uncommitted'],
      ['a short sha', 'a1b2c3d'],
    ])('refuses an engine commit of %s', (_what, commit) => {
      reject(
        broken((d) => void (d.run.engine_commit = commit)),
        `${name}.run.engine_commit: "${commit}" is not 40 lowercase hex digits, optionally followed by -dirty`,
      )
    })

    it.each([['optionsdx'], ['dolthub']])('accepts the data source %s', (source) => {
      expect(((parse(broken((d) => void (d.run.data_source = source))) as { run: Obj }).run).data_source).toBe(source)
    })

    it.each(['yahoo', 'OptionsDX', 'constructor', 'toString', '__proto__'])('refuses the data source "%s"', (source) => {
      reject(
        broken((d) => void (d.run.data_source = source)),
        `${name}.run.data_source: "${source}" is not a known data source (optionsdx, dolthub)`,
      )
    })

    const ENUMS: [string, string[]][] = [
      ['execution_mode', ['quote', 'surface']],
      ['fill_timing', ['next_close', 'same_close']],
      ['cap_mode', ['hard_only', 'volume']],
      ['chain_mask', ['none']],
      ['split', ['development', 'validation', 'holdout']],
      ['run_purpose', ['trial', 'diagnostic']],
      ['status', ['ok', 'ruin']],
    ]
    it.each(ENUMS)('accepts each value of %s, and refuses any other', (key, allowed) => {
      for (const value of allowed) {
        const file = parse(
          broken((d) => {
            d.run[key] = value
            // A ruined run gives the position it left unclosed an exit reason (positions_timeline only).
            if (key === 'status' && value === 'ruin' && Array.isArray(d.positions)) (d.positions as Obj[])[3].exit_reason = 'ruin'
          }),
        ) as { run: Obj }
        expect(file.run[key]).toBe(value)
      }
      const listed = allowed.map((a) => `"${a}"`).join(', ')
      for (const bad of ['bogus', 'None', ' none', '', null, 3]) {
        reject(
          broken((d) => void (d.run[key] = bad)),
          `${name}.run.${key}: expected one of ${listed}, got ${JSON.stringify(bad)}`,
        )
      }
    })

    it('needs a strategy that is a non-empty string', () => {
      for (const bad of ['', '   ', 5, null]) reject(broken((d) => void (d.run.strategy = bad)), `${name}.run.strategy: expected a non-empty string`)
    })

    it.each(['sample_start', 'sample_end'])('needs %s to be a calendar date', (key) => {
      for (const bad of ['2015-02-30', '2015-1-2', '20150102', 'x', '2015-13-01', '']) {
        reject(
          broken((d) => void (d.run[key] = bad)),
          `${name}.run.${key}`,
        )
      }
      reject(broken((d) => void (d.run[key] = '2015-02-30')), `${name}.run.${key}: "2015-02-30" is not a calendar date YYYY-MM-DD`)
      reject(broken((d) => void (d.run[key] = 20150102)), `${name}.run.${key}: expected a non-empty string`)
    })

    it('refuses a sample that ends before it starts, and accepts one that starts and ends on the same day', () => {
      reject(
        broken((d) => {
          d.run.sample_start = '2015-03-21'
        }),
        `${name}.run.sample_end: 2015-03-20 is before sample_start 2015-03-21`,
      )
      const sameDay = parse(
        broken((d) => {
          d.run.sample_start = '2015-03-20'
          if ('fills' in d) {
            d.fills = []
            d.events = []
          } else {
            d.positions = []
            d.dates = ['2015-03-20']
            d.open_count = [0]
          }
        }),
      ) as { run: Obj }
      expect([sameDay.run.sample_start, sameDay.run.sample_end]).toEqual(['2015-03-20', '2015-03-20'])
    })
  })

  describe('units', () => {
    it('are the exporter’s strings, exactly, key by key', () => {
      expect((parse(fixture) as { units: Obj }).units).toEqual(units)
      expect(Object.keys(units)).toEqual([...unitKeys])
    })

    it('are required, and an object', () => {
      reject(broken((d) => void delete (d as Obj).units), `${name}: missing required key "units"`)
      reject(broken((d) => void ((d as Obj).units = 'USD')), `${name}.units: expected an object`)
    })

    it.each([...unitKeys])('need the key %s, and exactly its string', (key) => {
      reject(broken((d) => void delete d.units[key]), `${name}.units: missing required key "${key}"`)
      reject(broken((d) => void (d.units[key] = '')), `${name}.units.${key}: expected a non-empty string`)
      reject(
        broken((d) => void (d.units[key] = `${(units as Record<string, string>)[key]} `)),
        `${name}.units.${key}: "${(units as Record<string, string>)[key]} " is not the exporter's unit for ${key}, "${(units as Record<string, string>)[key]}"`,
      )
      reject(broken((d) => void (d.units[key] = 'percent')), `${name}.units.${key}: "percent" is not the exporter's unit for ${key}`)
    })
  })

  describe('illustrative and label', () => {
    it.each([true, 'false', 0, null])('refuses illustrative = %s: only a literal false is a run', (value) => {
      reject(
        broken((d) => void ((d as Obj).illustrative = value)),
        `${name}.illustrative: must be false`,
      )
    })

    it('needs illustrative to be present', () => {
      reject(broken((d) => void delete (d as Obj).illustrative), `${name}: missing required key "illustrative"`)
    })

    it('needs a non-empty label', () => {
      for (const bad of ['', '  ', 4, null]) reject(broken((d) => void ((d as Obj).label = bad)), `${name}.label: expected a non-empty string`)
      reject(broken((d) => void delete (d as Obj).label), `${name}: missing required key "label"`)
    })
  })
})

// ---------------------------------------------------------------- blotter.json

describe('parseBlotter: accepts', () => {
  it('reads every fill and event of the fixture, typed', () => {
    const file = parseBlotter(blotterFixture)
    expect(file.illustrative).toBe(false)
    expect(file.fills).toHaveLength(13)
    expect(file.events.map((e) => e.event_type)).toEqual(['assigned', 'expired_worthless', 'early_assigned'])
    expect(file.fills[8]).toEqual({
      fill_id: 9,
      date: '2015-02-23',
      instrument: 'share',
      osi_symbol: null,
      qty: 1000,
      price: 205.25,
      mid: null,
      half_spread: null,
      fees: 10,
      fill_source: 'close',
      intent: 'share_liquidation',
    })
    expect(file.events[2]).toMatchObject({ settlement_price: null, effective_date: '2015-03-06', date: '2015-03-05' })
  })

  it('drops unknown keys on a fill and on an event', () => {
    const file = parseBlotter(
      brokenBlotter((d) => {
        d.fills[0].future = 1
        d.events[0].future = 2
      }),
    )
    expect(file.fills[0]).not.toHaveProperty('future')
    expect(file.events[0]).not.toHaveProperty('future')
  })

  it('accepts a file with no fills and no events (a run that never traded)', () => {
    const file = parseBlotter(
      brokenBlotter((d) => {
        d.fills = []
        d.events = []
      }),
    )
    expect([file.fills, file.events]).toEqual([[], []])
  })

  it('knows the intents of the spec', () => {
    expect([...FILL_INTENTS]).toEqual(['open', 'close', 'reduce_risk', 'margin_liquidation', 'share_liquidation'])
    expect([...EVENT_TYPES]).toEqual(['expired_worthless', 'exercised', 'assigned', 'early_exercised', 'early_assigned'])
  })

  // fills[4] is the first fill of the fixture that closes something, so every intent is valid on it.
  it.each(['open', 'close', 'reduce_risk', 'margin_liquidation'])('accepts the intent %s on an option fill', (intent) => {
    expect(parseBlotter(brokenBlotter((d) => void (d.fills[4].intent = intent))).fills[4].intent).toBe(intent)
  })

  it('accepts a surface-priced option fill', () => {
    expect(parseBlotter(brokenBlotter((d) => void (d.fills[0].fill_source = 'surface'))).fills[0].fill_source).toBe('surface')
  })

  it('accepts a mid, a half-spread and fees of exactly 0', () => {
    const fill = parseBlotter(
      brokenBlotter((d) => {
        d.fills[0].mid = 0
        d.fills[0].half_spread = 0
        d.fills[0].fees = 0
      }),
    ).fills[0]
    expect([fill.mid, fill.half_spread, fill.fees]).toEqual([0, 0, 0])
  })

  it('accepts a fill on each end of the sample, and several fills on one day', () => {
    const file = parseBlotter(
      brokenBlotter((d) => {
        d.fills[12].date = '2015-03-20'
      }),
    )
    expect([file.fills[0].date, file.fills[12].date]).toEqual(['2015-01-02', '2015-03-20'])
    expect(file.fills[0].date).toBe(file.fills[1].date)
  })

  it('accepts OSI symbols with a longer or digit-only root, and any strike', () => {
    for (const symbol of ['SPXW  150123P00205000', '123456150123C00205000', 'SPY   150123C00000500', 'ABCDEF150123P99999999']) {
      // fills[4] closes fills[0]'s symbol, so it opens a position of its own here.
      const file = parseBlotter(brokenBlotter((d) => ((d.fills[0].osi_symbol = symbol), (d.fills[4].intent = 'open'))))
      expect(file.fills[0].osi_symbol).toBe(symbol)
    }
  })

  it('accepts a price of one cent, and a quantity of either sign', () => {
    // fills[4] would close the short that fills[0] no longer opens, so it opens a position of its own here.
    const fill = parseBlotter(brokenBlotter((d) => ((d.fills[0].price = 0.01), (d.fills[0].qty = 7), (d.fills[4].intent = 'open')))).fills[0]
    expect([fill.price, fill.qty]).toEqual([0.01, 7])
  })

  it('takes the sign of a delivery from ADR-0003’s table: a short call assigned delivers shares, a short put receives them', () => {
    expect(parseBlotter(brokenBlotter(() => undefined)).events[0].shares_delivered).toBe(-1000)
    expect(() => parseBlotter(brokenBlotter((d) => void (d.events[0].shares_delivered = 1000)))).toThrow(
      'blotter.events[0].shares_delivered: is 1000 but -10 contract(s) of a call deliver -1000 shares',
    )
    expect(parseBlotter(brokenBlotter(() => undefined)).events[2].shares_delivered).toBe(1000)
    expect(() => parseBlotter(brokenBlotter((d) => void (d.events[2].shares_delivered = -1000)))).toThrow(
      'blotter.events[2].shares_delivered: is -1000 but -10 contract(s) of a put deliver 1000 shares',
    )
  })

  it('refuses a long lot assigned and a short lot exercised', () => {
    expect(() =>
      parseBlotter(brokenBlotter((d) => void Object.assign(d.events[0], { contracts: 10, shares_delivered: 1000 }))),
    ).toThrow('blotter.events[0].contracts: is 10 but only a short lot (contracts < 0) is assigned')
    expect(() =>
      parseBlotter(brokenBlotter((d) => void Object.assign(d.events[2], { contracts: 10, shares_delivered: -1000 }))),
    ).toThrow('blotter.events[2].contracts: is 10 but only a short lot (contracts < 0) is assigned')
    expect(() =>
      parseBlotter(
        brokenBlotter((d) => void Object.assign(d.events[0], { event_type: 'exercised', contracts: -10, shares_delivered: -1000 })),
      ),
    ).toThrow('blotter.events[0].contracts: is -10 but only a long lot (contracts > 0) is exercised')
    expect(() =>
      parseBlotter(
        brokenBlotter((d) =>
          void Object.assign(d.events[2], { event_type: 'early_exercised', contracts: -10, shares_delivered: 1000 }),
        ),
      ),
    ).toThrow('blotter.events[2].contracts: is -10 but only a long lot (contracts > 0) is exercised')
  })

  it.each([
    ['exercised', 10, 1000, 205.25, false],
    ['assigned', -3, -300, 205.75, false],
    ['assigned', -3, -300, 205.5, true],
    ['assigned', -3, -300, 205.51, false],
    ['expired_worthless', 5, 0, 204.75, false],
    ['expired_worthless', -5, 0, 204.5, true],
    ['early_exercised', 2, 200, null, false],
    ['early_assigned', -2, -200, null, false],
  ])('accepts a %s event of %s contracts delivering %s shares, settling at %s, pinned %s', (type, contracts, shares, settlement, pin) => {
    const event = parseBlotter(
      brokenBlotter((d) => {
        // events[0] is a call struck at 205. A short lot settling within 50 cents of the strike is pinned and no other
        // lot is (the engine's rule, ADR-0003); an early event has no price to pin to.
        Object.assign(d.events[0], { event_type: type, contracts, shares_delivered: shares, settlement_price: settlement, pin_flag: pin })
      }),
    ).events[0]
    expect(event).toMatchObject({ event_type: type, contracts, shares_delivered: shares, settlement_price: settlement, pin_flag: pin })
  })

  it('settles a contract whose expiry was not a session on the session before it (ADR-0003 D16)', () => {
    const file = parseBlotter(brokenBlotter((d) => nonSessionExpiry(d, '2018-12-04', '2018-12-04')))
    expect([file.events[0].date, file.events[0].osi_symbol]).toEqual(['2018-12-04', 'SPY   181205C00205000'])
  })

  it('accepts an early event that books after the end of the sample, and one that books the day it was decided', () => {
    const file = parseBlotter(
      brokenBlotter((d) => {
        // An expiry on 2015-04-17 leaves room for an effective date after the sample's end.
        d.events[2].osi_symbol = 'SPY   150417P00207000'
        d.events[2].date = '2015-03-20'
        d.events[2].effective_date = '2015-03-23'
        d.events[0].effective_date = d.events[0].date
      }),
    )
    expect(file.events[2].effective_date).toBe('2015-03-23')
    expect(file.events[0].effective_date).toBe(file.events[0].date)
  })
})

describe('parseBlotter: refuses a fill that', () => {
  const fillCases: [string, (d: BlotterDoc) => void, string][] = [
    ['has no fill_id', (d) => void delete d.fills[0].fill_id, 'blotter.fills[0]: missing required key "fill_id"'],
    ['has a fill_id of 0', (d) => void (d.fills[0].fill_id = 0), 'blotter.fills[0].fill_id: expected a whole number of at least 1, got 0'],
    ['has a negative fill_id', (d) => void (d.fills[0].fill_id = -3), 'blotter.fills[0].fill_id: expected a whole number of at least 1, got -3'],
    ['has a fractional fill_id', (d) => void (d.fills[0].fill_id = 1.5), 'blotter.fills[0].fill_id: expected a whole number of at least 1, got 1.5'],
    ['has a fill_id that is text', (d) => void (d.fills[0].fill_id = '1'), 'blotter.fills[0].fill_id: expected a whole number of at least 1, got 1'],
    ['repeats the fill_id above', (d) => void (d.fills[1].fill_id = 1), 'blotter.fills[1].fill_id: must be strictly increasing, but 1 follows 1'],
    ['has a fill_id below the one above', (d) => void (d.fills[2].fill_id = 1), 'blotter.fills[2].fill_id: must be strictly increasing, but 1 follows 2'],
    ['is not an object', (d) => void (d.fills[0] = 5 as never), 'blotter.fills[0]: expected an object'],
    ['has no date', (d) => void delete d.fills[0].date, 'blotter.fills[0]: missing required key "date"'],
    ['has a date that does not exist', (d) => void (d.fills[0].date = '2015-02-30'), 'blotter.fills[0].date: "2015-02-30" is not a calendar date YYYY-MM-DD'],
    ['is dated on a Saturday', (d) => void (d.fills[0].date = '2015-01-03'), 'blotter.fills[0].date: 2015-01-03 is a Saturday: a session is a weekday'],
    ['is dated on a Sunday', (d) => void (d.fills[0].date = '2015-01-04'), 'blotter.fills[0].date: 2015-01-04 is a Sunday: a session is a weekday'],
    [
      'is dated before the sample',
      (d) => void (d.fills[0].date = '2014-12-31'),
      "blotter.fills[0].date: 2014-12-31 is outside the run's sample 2015-01-02 to 2015-03-20",
    ],
    [
      'is dated after the sample',
      (d) => void (d.fills[12].date = '2015-03-23'),
      "blotter.fills[12].date: 2015-03-23 is outside the run's sample 2015-01-02 to 2015-03-20",
    ],
    [
      'is dated before the fill above it',
      (d) => void (d.fills[3].date = '2015-01-08'),
      'blotter.fills[3].date: must not go back in time, but 2015-01-08 follows 2015-01-09',
    ],
    [
      'has an instrument that is neither option nor share',
      (d) => void (d.fills[0].instrument = 'future'),
      'blotter.fills[0].instrument: expected one of "option", "share", got "future"',
    ],
    ['has no instrument', (d) => void delete d.fills[0].instrument, 'blotter.fills[0]: missing required key "instrument"'],
    [
      'is an option without an OSI symbol',
      (d) => void (d.fills[0].osi_symbol = null),
      'blotter.fills[0].osi_symbol: null is not a 21-character OSI symbol (root padded to 6, YYMMDD, C or P, strike x 1000 as 8 digits)',
    ],
    ['is an option with no osi_symbol key', (d) => void delete d.fills[0].osi_symbol, 'blotter.fills[0]: missing required key "osi_symbol"'],
    [
      'is a share with an OSI symbol',
      (d) => void (d.fills[8].osi_symbol = OSI),
      'blotter.fills[8].osi_symbol: a share fill has no OSI symbol, so this must be null',
    ],
    ['is a share with no osi_symbol key', (d) => void delete d.fills[8].osi_symbol, 'blotter.fills[8]: missing required key "osi_symbol"'],
    ['has a zero quantity', (d) => void (d.fills[0].qty = 0), 'blotter.fills[0].qty: expected a whole number other than 0, got 0'],
    ['has a fractional quantity', (d) => void (d.fills[0].qty = 1.5), 'blotter.fills[0].qty: expected a whole number other than 0, got 1.5'],
    ['has a quantity that is text', (d) => void (d.fills[0].qty = '10'), 'blotter.fills[0].qty: expected a whole number other than 0, got 10'],
    ['has no quantity', (d) => void delete d.fills[0].qty, 'blotter.fills[0]: missing required key "qty"'],
    ['has a zero price', (d) => void (d.fills[0].price = 0), 'blotter.fills[0].price: expected a number above 0, got 0'],
    ['has a negative price', (d) => void (d.fills[0].price = -1), 'blotter.fills[0].price: expected a number above 0, got -1'],
    ['has a price that is text', (d) => void (d.fills[0].price = '3.1'), 'blotter.fills[0].price: expected a number above 0, got 3.1'],
    ['has a price that is not finite', (d) => void (d.fills[0].price = Infinity), 'blotter.fills[0].price: expected a number above 0, got Infinity'],
    ['has a price that is not a number', (d) => void (d.fills[0].price = NaN), 'blotter.fills[0].price: expected a number above 0, got NaN'],
    ['has a share price of zero', (d) => void (d.fills[8].price = 0), 'blotter.fills[8].price: expected a number above 0, got 0'],
    ['is an option without a mid', (d) => void (d.fills[0].mid = null), 'blotter.fills[0].mid: expected a number of at least 0, got null'],
    ['has a negative mid', (d) => void (d.fills[0].mid = -0.01), 'blotter.fills[0].mid: expected a number of at least 0, got -0.01'],
    ['has a mid that is text', (d) => void (d.fills[0].mid = '1'), 'blotter.fills[0].mid: expected a number of at least 0, got 1'],
    ['has a mid that is not finite', (d) => void (d.fills[0].mid = Infinity), 'blotter.fills[0].mid: expected a number of at least 0, got Infinity'],
    ['has no mid key', (d) => void delete d.fills[0].mid, 'blotter.fills[0]: missing required key "mid"'],
    ['is a share with a mid', (d) => void (d.fills[8].mid = 205.2), 'blotter.fills[8].mid: a share fill has no quote, so this must be null, got 205.2'],
    ['is a share with a mid of 0', (d) => void (d.fills[8].mid = 0), 'blotter.fills[8].mid: a share fill has no quote, so this must be null, got 0'],
    ['is an option without a half-spread', (d) => void (d.fills[0].half_spread = null), 'blotter.fills[0].half_spread: expected a number of at least 0, got null'],
    ['has a negative half-spread', (d) => void (d.fills[0].half_spread = -0.025), 'blotter.fills[0].half_spread: expected a number of at least 0, got -0.025'],
    ['has no half_spread key', (d) => void delete d.fills[0].half_spread, 'blotter.fills[0]: missing required key "half_spread"'],
    [
      'is a share with a half-spread',
      (d) => void (d.fills[8].half_spread = 0.01),
      'blotter.fills[8].half_spread: a share fill has no quote, so this must be null, got 0.01',
    ],
    ['has negative fees', (d) => void (d.fills[0].fees = -0.01), 'blotter.fills[0].fees: expected a number of at least 0, got -0.01'],
    ['has fees that are text', (d) => void (d.fills[0].fees = '6.5'), 'blotter.fills[0].fees: expected a number of at least 0, got 6.5'],
    ['has no fees', (d) => void delete d.fills[0].fees, 'blotter.fills[0]: missing required key "fees"'],
    [
      'is an option priced at the close',
      (d) => void (d.fills[0].fill_source = 'close'),
      'blotter.fills[0].fill_source: expected one of "quote", "surface", got "close"',
    ],
    [
      'is an option with an unknown source',
      (d) => void (d.fills[0].fill_source = 'mid'),
      'blotter.fills[0].fill_source: expected one of "quote", "surface", got "mid"',
    ],
    ['is a share priced from a quote', (d) => void (d.fills[8].fill_source = 'quote'), 'blotter.fills[8].fill_source: expected one of "close", got "quote"'],
    ['is a share priced from the surface', (d) => void (d.fills[8].fill_source = 'surface'), 'blotter.fills[8].fill_source: expected one of "close", got "surface"'],
    [
      'has an intent the spec does not know',
      (d) => void (d.fills[0].intent = 'hedge'),
      'blotter.fills[0].intent: expected one of "open", "close", "reduce_risk", "margin_liquidation", "share_liquidation", got "hedge"',
    ],
    [
      'is an option with the share-liquidation intent',
      (d) => void (d.fills[0].intent = 'share_liquidation'),
      'blotter.fills[0].intent: an option fill never has the intent "share_liquidation"',
    ],
    [
      'is a share with another intent',
      (d) => void (d.fills[8].intent = 'open'),
      'blotter.fills[8].intent: a share fill has the intent "share_liquidation", got "open"',
    ],
    ['is an option priced in a fraction of a cent', (d) => void (d.fills[0].price = 3.125), 'blotter.fills[0].price: 3.125 is not a whole number of cents (ADR-0002 §2)'],
    [
      'is an option traded after its contract expired',
      (d) => void (d.fills[0].date = '2015-01-26'),
      'blotter.fills[0].date: 2015-01-26 is after the expiry 2015-01-23 of "SPY   150123C00205000"',
    ],
    [
      'is an option closed that no earlier fill opened (a short fill relabelled close)',
      (d) => void (d.fills[0].intent = 'close'),
      'blotter.fills[0].intent: is "close" (reduce-only) but -10 of "SPY   150123C00205000" reduces more long contracts than the fills before it opened',
    ],
    [
      'is an option bought back that no earlier fill sold (the opening sale became a purchase)',
      (d) => void (d.fills[0].qty = 10),
      'blotter.fills[4].intent: is "close" (reduce-only) but 10 of "SPY   150123C00205000" reduces more short contracts than the fills before it opened',
    ],
  ]
  it.each(fillCases)('%s', (_what, change, fragment) => {
    rejectsB(brokenBlotter(change), fragment)
  })

  it.each([
    ['fills', 'blotter.fills: expected an array'],
    ['events', 'blotter.events: expected an array'],
  ])('is not in %s unless that is an array', (key, fragment) => {
    rejectsB(brokenBlotter((d) => void ((d as Obj)[key] = {})), fragment)
    rejectsB(brokenBlotter((d) => void delete (d as Obj)[key]), `blotter: missing required key "${key}"`)
  })
})

/** events[0] on a call that expired on 2018-12-05, a Wednesday that was no session: it settled on the 4th (the sample is widened to hold it, and the other events dropped). */
function nonSessionExpiry(d: BlotterDoc, date: string, effective: string): void {
  d.run.sample_end = '2018-12-31'
  d.events = [d.events[0]]
  Object.assign(d.events[0], { osi_symbol: 'SPY   181205C00205000', date, effective_date: effective })
}

describe('parseBlotter: refuses an event that', () => {
  const eventCases: [string, (d: BlotterDoc) => void, string][] = [
    ['has no event_id', (d) => void delete d.events[0].event_id, 'blotter.events[0]: missing required key "event_id"'],
    ['has an event_id of 0', (d) => void (d.events[0].event_id = 0), 'blotter.events[0].event_id: expected a whole number of at least 1, got 0'],
    ['has a fractional event_id', (d) => void (d.events[0].event_id = 2.5), 'blotter.events[0].event_id: expected a whole number of at least 1, got 2.5'],
    ['repeats the event_id above', (d) => void (d.events[1].event_id = 1), 'blotter.events[1].event_id: must be strictly increasing, but 1 follows 1'],
    ['has an event_id below the one above', (d) => void (d.events[2].event_id = 1), 'blotter.events[2].event_id: must be strictly increasing, but 1 follows 2'],
    ['is not an object', (d) => void (d.events[1] = [] as never), 'blotter.events[1]: expected an object'],
    ['is dated on a Saturday', (d) => void (d.events[0].date = '2015-02-21'), 'blotter.events[0].date: 2015-02-21 is a Saturday: a session is a weekday'],
    ['is dated on a Sunday', (d) => void (d.events[0].date = '2015-02-22'), 'blotter.events[0].date: 2015-02-22 is a Sunday: a session is a weekday'],
    [
      'is dated before the sample',
      (d) => void ((d.events[0].date = '2014-12-31'), (d.events[0].effective_date = '2014-12-31')),
      "blotter.events[0].date: 2014-12-31 is outside the run's sample 2015-01-02 to 2015-03-20",
    ],
    [
      'is dated after the sample',
      (d) => void ((d.events[2].date = '2015-03-23'), (d.events[2].effective_date = '2015-03-23')),
      "blotter.events[2].date: 2015-03-23 is outside the run's sample 2015-01-02 to 2015-03-20",
    ],
    [
      'is dated before the event above it',
      // events[2] is early, so its date is free of the settle date.
      (d) => void ((d.events[2].date = '2015-02-19'), (d.events[2].effective_date = '2015-02-19')),
      'blotter.events[2].date: must not go back in time, but 2015-02-19 follows 2015-02-20',
    ],
    ['has no effective_date', (d) => void delete d.events[0].effective_date, 'blotter.events[0]: missing required key "effective_date"'],
    ['books on a date that does not exist', (d) => void (d.events[0].effective_date = '2015-02-30'), 'blotter.events[0].effective_date: "2015-02-30" is not a calendar date YYYY-MM-DD'],
    ['books before it was decided', (d) => void (d.events[0].effective_date = '2015-02-19'), 'blotter.events[0].effective_date: 2015-02-19 is before date 2015-02-20'],
    ['books on a Saturday', (d) => void (d.events[2].effective_date = '2015-03-07'), 'blotter.events[2].effective_date: 2015-03-07 is a Saturday: a session is a weekday'],
    ['books on a Sunday', (d) => void (d.events[2].effective_date = '2015-03-08'), 'blotter.events[2].effective_date: 2015-03-08 is a Sunday: a session is a weekday'],
    [
      'has an osi_symbol that is not one',
      (d) => void (d.events[0].osi_symbol = 'SPY'),
      'blotter.events[0].osi_symbol: "SPY" is not a 21-character OSI symbol',
    ],
    ['has no osi_symbol', (d) => void delete d.events[0].osi_symbol, 'blotter.events[0]: missing required key "osi_symbol"'],
    [
      'has an event_type the spec does not know',
      (d) => void (d.events[0].event_type = 'called_away'),
      'blotter.events[0].event_type: expected one of "expired_worthless", "exercised", "assigned", "early_exercised", "early_assigned", got "called_away"',
    ],
    ['has zero contracts', (d) => void (d.events[0].contracts = 0), 'blotter.events[0].contracts: expected a whole number other than 0, got 0'],
    ['has fractional contracts', (d) => void (d.events[0].contracts = -1.5), 'blotter.events[0].contracts: expected a whole number other than 0, got -1.5'],
    ['has no contracts', (d) => void delete d.events[0].contracts, 'blotter.events[0]: missing required key "contracts"'],
    ['has no shares_delivered', (d) => void delete d.events[0].shares_delivered, 'blotter.events[0]: missing required key "shares_delivered"'],
    ['has fractional shares', (d) => void (d.events[0].shares_delivered = -1000.5), 'blotter.events[0].shares_delivered: expected a whole number, got -1000.5'],
    ['has shares that are text', (d) => void (d.events[0].shares_delivered = '-1000'), 'blotter.events[0].shares_delivered: expected a whole number, got -1000'],
    [
      'delivers shares though it expired worthless',
      (d) => void (d.events[1].shares_delivered = 1000),
      'blotter.events[1].shares_delivered: is 1000 but an option that expired worthless delivers no shares',
    ],
    [
      'delivers fewer shares than 100 a contract',
      (d) => void (d.events[0].shares_delivered = -999),
      'blotter.events[0].shares_delivered: is -999 but -10 contract(s) of a call deliver -1000 shares',
    ],
    [
      'delivers more shares than 100 a contract',
      (d) => void (d.events[2].shares_delivered = 1100),
      'blotter.events[2].shares_delivered: is 1100 but -10 contract(s) of a put deliver 1000 shares',
    ],
    [
      'delivers no shares though it was assigned',
      (d) => void (d.events[0].shares_delivered = 0),
      'blotter.events[0].shares_delivered: is 0 but -10 contract(s) of a call deliver -1000 shares',
    ],
    ['has a strike of 0', (d) => void (d.events[0].strike = 0), 'blotter.events[0].strike: expected a number above 0, got 0'],
    ['has a negative strike', (d) => void (d.events[0].strike = -205), 'blotter.events[0].strike: expected a number above 0, got -205'],
    ['has a strike that is text', (d) => void (d.events[0].strike = '205'), 'blotter.events[0].strike: expected a number above 0, got 205'],
    ['has no strike', (d) => void delete d.events[0].strike, 'blotter.events[0]: missing required key "strike"'],
    ['has no settlement_price key', (d) => void delete d.events[0].settlement_price, 'blotter.events[0]: missing required key "settlement_price"'],
    ['has no settlement_price key on an early event', (d) => void delete d.events[2].settlement_price, 'blotter.events[2]: missing required key "settlement_price"'],
    [
      'is not early and has no settlement price',
      (d) => void (d.events[0].settlement_price = null),
      'blotter.events[0].settlement_price: expected a number above 0, got null',
    ],
    [
      'expired worthless without a settlement price',
      (d) => void (d.events[1].settlement_price = null),
      'blotter.events[1].settlement_price: expected a number above 0, got null',
    ],
    ['has a settlement price of 0', (d) => void (d.events[0].settlement_price = 0), 'blotter.events[0].settlement_price: expected a number above 0, got 0'],
    ['has a negative settlement price', (d) => void (d.events[0].settlement_price = -1), 'blotter.events[0].settlement_price: expected a number above 0, got -1'],
    [
      'is early and has a settlement price',
      (d) => void (d.events[2].settlement_price = 207),
      'blotter.events[2].settlement_price: an early event settles at the strike, not a close, so this must be null, got 207',
    ],
    [
      'is early_exercised and has a settlement price',
      (d) => void ((d.events[2].event_type = 'early_exercised'), (d.events[2].contracts = 10), (d.events[2].shares_delivered = -1000), (d.events[2].settlement_price = 207.5)),
      'blotter.events[2].settlement_price: an early event settles at the strike, not a close, so this must be null, got 207.5',
    ],
    ['has no pin_flag', (d) => void delete d.events[0].pin_flag, 'blotter.events[0]: missing required key "pin_flag"'],
    ['has a pin_flag that is text', (d) => void (d.events[0].pin_flag = 'yes'), 'blotter.events[0].pin_flag: expected true or false, got yes'],
    ['has a pin_flag that is a number', (d) => void (d.events[0].pin_flag = 1), 'blotter.events[0].pin_flag: expected true or false, got 1'],
    [
      'has a strike that is not the strike of its OSI symbol',
      (d) => void (d.events[0].strike = 206),
      'blotter.events[0].strike: is 206 but the OSI symbol "SPY   150220C00205000" names the strike 205',
    ],
    [
      'expired worthless though its call finished in the money',
      (d) => void Object.assign(d.events[0], { event_type: 'expired_worthless', shares_delivered: 0 }),
      'blotter.events[0].event_type: is "expired_worthless" but the call struck at 205 settled at 205.25, which is in the money by a cent or more',
    ],
    [
      'was assigned though its put finished out of the money',
      (d) => void Object.assign(d.events[1], { event_type: 'assigned', shares_delivered: 1000 }),
      'blotter.events[1].event_type: is "assigned" but the put struck at 205 settled at 205.25, which is not in the money by a cent or more',
    ],
    [
      'was assigned though its call settled exactly at the strike',
      (d) => void Object.assign(d.events[0], { settlement_price: 205, pin_flag: false }),
      'blotter.events[0].event_type: is "assigned" but the call struck at 205 settled at 205, which is not in the money by a cent or more',
    ],
    [
      'was assigned though its put settled exactly at the strike',
      (d) => void Object.assign(d.events[1], { event_type: 'assigned', shares_delivered: 1000, settlement_price: 205 }),
      'blotter.events[1].event_type: is "assigned" but the put struck at 205 settled at 205, which is not in the money by a cent or more',
    ],
    [
      'is a pin on a long lot',
      (d) => void Object.assign(d.events[0], { event_type: 'exercised', contracts: 10, shares_delivered: 1000 }),
      'blotter.events[0].pin_flag: is true but the long lot (contracts 10) settled at 205.25, 25 cents from the strike 205: only a short lot within 50 cents is pinned',
    ],
    [
      'is a pin though the settlement is more than 50 cents from the strike',
      (d) => void (d.events[0].settlement_price = 205.51),
      'blotter.events[0].pin_flag: is true but the short lot (contracts -10) settled at 205.51, 51 cents from the strike 205',
    ],
    [
      'is not a pin though its short lot settled within 50 cents of the strike',
      (d) => void (d.events[0].pin_flag = false),
      'blotter.events[0].pin_flag: is false but the short lot (contracts -10) settled at 205.25, 25 cents from the strike 205: only a short lot within 50 cents is pinned',
    ],
    [
      'is not a pin though its short lot settled exactly 50 cents from the strike',
      (d) => void Object.assign(d.events[1], { settlement_price: 204.5, event_type: 'assigned', shares_delivered: 1000, pin_flag: false }),
      'blotter.events[1].pin_flag: is false but the short lot (contracts -10) settled at 204.5, 50 cents from the strike 205',
    ],
    [
      'has a strike in a fraction of a cent (the review: K = 450.125 against S = 450.13)',
      (d) => void Object.assign(d.events[0], { osi_symbol: 'SPY   150220C00205125', strike: 205.125, settlement_price: 205.13 }),
      'blotter.events[0].strike: 205.125 is not a whole number of cents',
    ],
    [
      'has a settlement price in a fraction of a cent',
      (d) => void (d.events[0].settlement_price = 205.255),
      'blotter.events[0].settlement_price: 205.255 is not a whole number of cents',
    ],
    [
      'is a pin though it is an early event with no settlement price',
      (d) => void (d.events[2].pin_flag = true),
      'blotter.events[2].pin_flag: is true but an early event has no settlement price to pin to',
    ],
    [
      'was decided after its contract expired',
      (d) => void ((d.events[0].date = '2015-02-23'), (d.events[0].effective_date = '2015-02-23')),
      'blotter.events[0].date: 2015-02-23 is after the expiry 2015-02-20 of "SPY   150220C00205000"',
    ],
    [
      'books after its contract expired',
      (d) => void (d.events[2].effective_date = '2015-03-23'),
      'blotter.events[2].effective_date: 2015-03-23 is after the expiry 2015-03-20 of "SPY   150320P00207000"',
    ],
    [
      'settles before the contract’s settle date',
      (d) => void ((d.events[0].date = '2015-02-19'), (d.events[0].effective_date = '2015-02-19')),
      "blotter.events[0].date: is 2015-02-19 but a settlement event is on the contract's settle date 2015-02-20",
    ],
    [
      'settles on the expiry of a contract whose expiry was not a session (ADR-0003 D16)',
      (d) => void nonSessionExpiry(d, '2018-12-05', '2018-12-05'),
      "blotter.events[0].date: is 2018-12-05 but a settlement event is on the contract's settle date 2018-12-04",
    ],
    [
      'settles on its settle date but books on another',
      (d) => void nonSessionExpiry(d, '2018-12-04', '2018-12-05'),
      'blotter.events[0].effective_date: is 2018-12-05 but a settlement event books on its own date 2018-12-04',
    ],
  ]
  it.each(eventCases)('%s', (_what, change, fragment) => {
    rejectsB(brokenBlotter(change), fragment)
  })
})

describe('parseBlotter: the OSI symbol, on a fill and on an event', () => {
  const bad: [string, string][] = [
    ['a lower-case root', 'spy   150123C00205000'],
    ['a 5-character root', 'SPY  150123C00205000'],
    ['a 7-character root', 'SPY    150123C00205000'],
    ['a root with a dash', 'SPY-  150123C00205000'],
    ['a 5-digit date', 'SPY   15012C00205000'],
    ['a 7-digit date', 'SPY   1501230C00205000'],
    ['a date with a letter', 'SPY   15012xC00205000'],
    ['neither C nor P', 'SPY   150123X00205000'],
    ['a lower-case right', 'SPY   150123c00205000'],
    ['a 7-digit strike', 'SPY   150123C0020500'],
    ['a 9-digit strike', 'SPY   150123C002050000'],
    ['a strike with a letter', 'SPY   150123C0020500x'],
    ['a hex digit in the strike', 'SPY   150123C0020500f'],
    ['a hex digit in the date', 'SPY   15012fC00205000'],
    ['a trailing newline', 'SPY   150123C00205000\n'],
    ['a leading space', ' SPY   150123C00205000'],
    ['an empty string', ''],
    ['text before the symbol', 'x SPY   150123C00205000'],
  ]
  it.each(bad)('refuses %s on a fill', (_what, symbol) => {
    rejectsB(brokenBlotter((d) => void (d.fills[0].osi_symbol = symbol)), `blotter.fills[0].osi_symbol: ${JSON.stringify(symbol)} is not a 21-character OSI symbol`)
  })
  it.each(bad)('refuses %s on an event', (_what, symbol) => {
    rejectsB(brokenBlotter((d) => void (d.events[0].osi_symbol = symbol)), `blotter.events[0].osi_symbol: ${JSON.stringify(symbol)} is not a 21-character OSI symbol`)
  })
  it('refuses a symbol that is not text', () => {
    rejectsB(brokenBlotter((d) => void (d.fills[0].osi_symbol = 150123)), 'blotter.fills[0].osi_symbol: 150123 is not a 21-character OSI symbol')
  })

  it('refuses a valid symbol wrapped in a list, which a pattern test would read as the text inside', () => {
    const wrapped = [OSI]
    rejectsB(brokenBlotter((d) => void (d.fills[0].osi_symbol = wrapped)), 'blotter.fills[0].osi_symbol: ["SPY   150123C00205000"] is not a 21-character OSI symbol')
    rejectsB(brokenBlotter((d) => void (d.events[0].osi_symbol = wrapped)), 'blotter.events[0].osi_symbol: ["SPY   150123C00205000"] is not a 21-character OSI symbol')
    rejectsP(
      brokenPositions((d) => void (d.positions[0].legs[0].osi_symbol = wrapped)),
      'positions_timeline.positions[0].legs[0].osi_symbol: ["SPY   150123C00205000"] is not a 21-character OSI symbol',
    )
  })
})

// ---------------------------------------------------------------- positions_timeline.json

describe('parsePositionsTimeline: accepts', () => {
  it('reads every position, session and count of the fixture, typed', () => {
    const file = parsePositionsTimeline(positionsFixture)
    expect(file.illustrative).toBe(false)
    expect(file.positions.map((p) => [p.position_id, p.closed, p.exit_reason])).toEqual([
      [1, '2015-01-16', 'dte'],
      [2, '2015-02-20', 'expiry'],
      [3, '2015-03-06', 'assignment'],
      [4, null, null],
    ])
    expect(file.positions[0].legs).toEqual([
      { osi_symbol: 'SPY   150123C00205000', ratio: -1 },
      { osi_symbol: 'SPY   150123P00205000', ratio: -1 },
    ])
    expect(file.dates).toHaveLength(12)
    expect(file.open_count).toEqual([1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1])
  })

  it('drops unknown keys on a position and on a leg', () => {
    const file = parsePositionsTimeline(
      brokenPositions((d) => {
        d.positions[0].future = 1
        d.positions[0].legs[0].future = 2
      }),
    )
    expect(file.positions[0]).not.toHaveProperty('future')
    expect(file.positions[0].legs[0]).not.toHaveProperty('future')
  })

  // positions[1] closes on its legs' settle date, so every reason, expiry included, is valid on it.
  it.each([...EXIT_REASONS])('accepts the exit reason %s on a closed position', (reason) => {
    expect(parsePositionsTimeline(brokenPositions((d) => void (d.positions[1].exit_reason = reason))).positions[1].exit_reason).toBe(reason)
  })

  it('accepts a position closed on the day it was opened, and one opened and closed on the sample’s ends', () => {
    const file = parsePositionsTimeline(
      brokenPositions((d) => {
        d.positions[1].closed = d.positions[1].opened
        d.positions[1].exit_reason = 'dte'
        d.positions[0].opened = '2015-01-02'
        d.positions[0].closed = '2015-03-20'
        d.open_count = [1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 1]
      }),
    )
    expect(file.positions[1].closed).toBe(file.positions[1].opened)
    expect([file.positions[0].opened, file.positions[0].closed]).toEqual(['2015-01-02', '2015-03-20'])
  })

  it('accepts a ruined run: an unclosed position then has a reason, and any of them will do', () => {
    for (const reason of ['ruin', 'margin']) {
      const file = parsePositionsTimeline(
        brokenPositions((d) => {
          d.run.status = 'ruin'
          d.positions[3].exit_reason = reason
        }),
      )
      expect(file.positions[3]).toMatchObject({ closed: null, exit_reason: reason })
    }
  })

  it('accepts the exit reason expiry once the earliest of its legs has settled, though a later one has not', () => {
    const file = parsePositionsTimeline(
      brokenPositions((d) => {
        d.positions[1].legs[1].osi_symbol = 'SPY   150123P00205000'
        d.positions[1].closed = '2015-01-30'
        d.open_count = [1, 2, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1]
      }),
    )
    expect([file.positions[1].closed, file.positions[1].exit_reason]).toEqual(['2015-01-30', 'expiry'])
  })

  it('accepts a leg of any size and either sign, and several legs', () => {
    const file = parsePositionsTimeline(
      brokenPositions((d) => {
        d.positions[0].legs = [
          { osi_symbol: OSI, ratio: 3 },
          { osi_symbol: 'SPY   150123P00205000', ratio: -2 },
          { osi_symbol: 'SPY   150123P00200000', ratio: 1 },
        ]
      }),
    )
    expect(file.positions[0].legs.map((l) => l.ratio)).toEqual([3, -2, 1])
  })

  it('accepts a file with no positions', () => {
    const file = parsePositionsTimeline(brokenPositions((d) => ((d.positions = []), (d.open_count = d.open_count.map(() => 0)))))
    expect([file.positions, file.open_count]).toEqual([[], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]])
  })

  it('accepts one session, and zero open positions', () => {
    const file = parsePositionsTimeline(
      brokenPositions((d) => {
        d.positions = []
        d.dates = ['2015-03-20']
        d.open_count = [0]
      }),
    )
    expect([file.dates, file.open_count]).toEqual([['2015-03-20'], [0]])
  })

  it('accepts sessions that do not start on the first day of the sample nor end on the last', () => {
    const file = parsePositionsTimeline(
      brokenPositions((d) => {
        d.dates = ['2015-01-05', '2015-03-19']
        d.open_count = [1, 1]
      }),
    )
    expect(file.dates).toEqual(['2015-01-05', '2015-03-19'])
  })
})

describe('parsePositionsTimeline: refuses a position that', () => {
  const positionCases: [string, (d: PositionsDoc) => void, string][] = [
    ['has no position_id', (d) => void delete d.positions[0].position_id, 'positions_timeline.positions[0]: missing required key "position_id"'],
    ['has a position_id of 0', (d) => void (d.positions[0].position_id = 0), 'positions_timeline.positions[0].position_id: expected a whole number of at least 1, got 0'],
    ['has a fractional position_id', (d) => void (d.positions[0].position_id = 1.5), 'positions_timeline.positions[0].position_id: expected a whole number of at least 1, got 1.5'],
    [
      'repeats the position_id above',
      (d) => void (d.positions[1].position_id = 1),
      'positions_timeline.positions[1].position_id: must be strictly increasing, but 1 follows 1',
    ],
    [
      'has a position_id below the one above',
      (d) => void (d.positions[3].position_id = 2),
      'positions_timeline.positions[3].position_id: must be strictly increasing, but 2 follows 3',
    ],
    ['is not an object', (d) => void (d.positions[2] = 'x' as never), 'positions_timeline.positions[2]: expected an object'],
    ['has a blank structure', (d) => void (d.positions[0].structure = ' '), 'positions_timeline.positions[0].structure: expected a non-empty string'],
    ['has no structure', (d) => void delete d.positions[0].structure, 'positions_timeline.positions[0]: missing required key "structure"'],
    ['has no opened date', (d) => void delete d.positions[0].opened, 'positions_timeline.positions[0]: missing required key "opened"'],
    [
      'opened on a date that does not exist',
      (d) => void (d.positions[0].opened = '2015-02-30'),
      'positions_timeline.positions[0].opened: "2015-02-30" is not a calendar date YYYY-MM-DD',
    ],
    [
      'opened on a Saturday',
      (d) => void (d.positions[0].opened = '2015-01-03'),
      'positions_timeline.positions[0].opened: 2015-01-03 is a Saturday: a session is a weekday',
    ],
    [
      'opened on a Sunday',
      (d) => void (d.positions[0].opened = '2015-01-04'),
      'positions_timeline.positions[0].opened: 2015-01-04 is a Sunday: a session is a weekday',
    ],
    [
      'opened before the sample',
      (d) => void (d.positions[0].opened = '2014-12-31'),
      "positions_timeline.positions[0].opened: 2014-12-31 is outside the run's sample 2015-01-02 to 2015-03-20",
    ],
    [
      'opened after the sample',
      (d) => void ((d.positions[3].opened = '2015-03-23'), (d.positions[3].closed = null)),
      "positions_timeline.positions[3].opened: 2015-03-23 is outside the run's sample 2015-01-02 to 2015-03-20",
    ],
    ['has no closed key', (d) => void delete d.positions[0].closed, 'positions_timeline.positions[0]: missing required key "closed"'],
    [
      'closed on a date that does not exist',
      (d) => void (d.positions[0].closed = '2015-02-30'),
      'positions_timeline.positions[0].closed: "2015-02-30" is not a calendar date YYYY-MM-DD',
    ],
    [
      'closed on a Saturday',
      (d) => void (d.positions[0].closed = '2015-01-17'),
      'positions_timeline.positions[0].closed: 2015-01-17 is a Saturday: a session is a weekday',
    ],
    [
      'closed on a Sunday',
      (d) => void (d.positions[0].closed = '2015-01-18'),
      'positions_timeline.positions[0].closed: 2015-01-18 is a Sunday: a session is a weekday',
    ],
    [
      'closed after the sample',
      (d) => void (d.positions[0].closed = '2015-03-23'),
      "positions_timeline.positions[0].closed: 2015-03-23 is outside the run's sample 2015-01-02 to 2015-03-20",
    ],
    [
      'closed before the sample',
      (d) => void (d.positions[0].closed = '2014-12-31'),
      "positions_timeline.positions[0].closed: 2014-12-31 is outside the run's sample 2015-01-02 to 2015-03-20",
    ],
    [
      'closed before it was opened',
      (d) => void (d.positions[1].closed = '2015-01-08'),
      'positions_timeline.positions[1].closed: 2015-01-08 is before opened 2015-01-09',
    ],
    ['has no legs key', (d) => void delete (d.positions[0] as Obj).legs, 'positions_timeline.positions[0]: missing required key "legs"'],
    ['has legs that are not a list', (d) => void (d.positions[0].legs = {} as never), 'positions_timeline.positions[0].legs: expected an array'],
    ['has no legs', (d) => void (d.positions[0].legs = []), 'positions_timeline.positions[0].legs: needs at least 1 leg'],
    ['has a leg that is not an object', (d) => void (d.positions[0].legs[1] = 3 as never), 'positions_timeline.positions[0].legs[1]: expected an object'],
    [
      'has a leg without an OSI symbol',
      (d) => void (d.positions[0].legs[1].osi_symbol = null),
      'positions_timeline.positions[0].legs[1].osi_symbol: null is not a 21-character OSI symbol',
    ],
    [
      'has a leg with a malformed OSI symbol',
      (d) => void (d.positions[0].legs[0].osi_symbol = 'SPY 150123C00205000'),
      'positions_timeline.positions[0].legs[0].osi_symbol: "SPY 150123C00205000" is not a 21-character OSI symbol',
    ],
    ['has a leg with a ratio of 0', (d) => void (d.positions[0].legs[0].ratio = 0), 'positions_timeline.positions[0].legs[0].ratio: expected a whole number other than 0, got 0'],
    [
      'has a leg with a fractional ratio',
      (d) => void (d.positions[0].legs[1].ratio = 0.5),
      'positions_timeline.positions[0].legs[1].ratio: expected a whole number other than 0, got 0.5',
    ],
    [
      'has a leg with a ratio that is text',
      (d) => void (d.positions[0].legs[0].ratio = '-1'),
      'positions_timeline.positions[0].legs[0].ratio: expected a whole number other than 0, got -1',
    ],
    ['has a leg with no ratio', (d) => void delete d.positions[0].legs[0].ratio, 'positions_timeline.positions[0].legs[0]: missing required key "ratio"'],
    ['has no exit_reason key', (d) => void delete d.positions[0].exit_reason, 'positions_timeline.positions[0]: missing required key "exit_reason"'],
    [
      'is closed and has no exit reason',
      (d) => void (d.positions[0].exit_reason = null),
      'positions_timeline.positions[0].exit_reason: expected one of "dte", "expiry", "assignment", "exercise", "signal", "profit_target", "stop", "risk", "margin", "ruin", got null',
    ],
    [
      'is closed and has an exit reason the spec does not know',
      (d) => void (d.positions[0].exit_reason = 'boredom'),
      'positions_timeline.positions[0].exit_reason: expected one of "dte", "expiry", "assignment", "exercise", "signal", "profit_target", "stop", "risk", "margin", "ruin", got "boredom"',
    ],
    [
      'is still open and has an exit reason',
      (d) => void (d.positions[3].exit_reason = 'dte'),
      'positions_timeline.positions[3].exit_reason: is "dte" but the position is still open in a run that did not end in ruin, so this must be null',
    ],
    [
      'is still open and has the exit reason ruin in a run that is ok',
      (d) => void (d.positions[3].exit_reason = 'ruin'),
      'positions_timeline.positions[3].exit_reason: is "ruin" but the position is still open in a run that did not end in ruin, so this must be null',
    ],
    [
      'is unclosed in a ruined run and has no exit reason',
      (d) => void (d.run.status = 'ruin'),
      'positions_timeline.positions[3].exit_reason: expected one of "dte"',
    ],
    [
      'is closed in a ruined run and has no exit reason',
      (d) => void ((d.run.status = 'ruin'), (d.positions[3].exit_reason = 'ruin'), (d.positions[0].exit_reason = null)),
      'positions_timeline.positions[0].exit_reason: expected one of "dte"',
    ],
    [
      'has the exit reason expiry before its legs settled',
      (d) => void (d.positions[1].closed = '2015-02-19'),
      'positions_timeline.positions[1].exit_reason: is "expiry" but the position closed on 2015-02-19, before its earliest settle date 2015-02-20',
    ],
    [
      'has the exit reason expiry and no close date',
      (d) => void ((d.run.status = 'ruin'), (d.positions[3].exit_reason = 'expiry')),
      'positions_timeline.positions[3].exit_reason: is "expiry" but the position has no close date',
    ],
  ]
  it.each(positionCases)('%s', (_what, change, fragment) => {
    rejectsP(brokenPositions(change), fragment)
  })

  it('is not in positions unless that is an array', () => {
    rejectsP(brokenPositions((d) => void ((d as Obj).positions = {})), 'positions_timeline.positions: expected an array')
    rejectsP(brokenPositions((d) => void delete (d as Obj).positions), 'positions_timeline: missing required key "positions"')
  })
})

describe('parsePositionsTimeline: refuses sessions and counts that', () => {
  const sessionCases: [string, (d: PositionsDoc) => void, string][] = [
    ['are not a list', (d) => void ((d as Obj).dates = '2015-01-02'), 'positions_timeline.dates: expected an array'],
    ['are missing', (d) => void delete (d as Obj).dates, 'positions_timeline: missing required key "dates"'],
    ['are empty', (d) => void ((d.dates = []), (d.open_count = [])), 'positions_timeline.dates: needs at least 1 session'],
    ['include something that is not text', (d) => void (d.dates[2] = 20150116), 'positions_timeline.dates[2]: 20150116 is not a calendar date YYYY-MM-DD'],
    ['include null', (d) => void (d.dates[2] = null), 'positions_timeline.dates[2]: null is not a calendar date YYYY-MM-DD'],
    [
      'include a date wrapped in a list',
      (d) => void (d.dates[2] = ['2015-01-16']),
      'positions_timeline.dates[2]: ["2015-01-16"] is not a calendar date YYYY-MM-DD',
    ],
    ['include a date that does not exist', (d) => void (d.dates[2] = '2015-02-30'), 'positions_timeline.dates[2]: "2015-02-30" is not a calendar date YYYY-MM-DD'],
    ['include a Saturday', (d) => void (d.dates[2] = '2015-01-17'), 'positions_timeline.dates[2]: 2015-01-17 is a Saturday: a session is a weekday'],
    ['include a Sunday', (d) => void (d.dates[2] = '2015-01-18'), 'positions_timeline.dates[2]: 2015-01-18 is a Sunday: a session is a weekday'],
    ['repeat a session', (d) => void (d.dates[1] = '2015-01-02'), 'positions_timeline.dates[1]: must be strictly increasing, but 2015-01-02 follows 2015-01-02'],
    ['go back in time', (d) => void (d.dates[2] = '2015-01-05'), 'positions_timeline.dates[2]: must be strictly increasing, but 2015-01-05 follows 2015-01-09'],
    [
      'start before the sample',
      (d) => void (d.dates[0] = '2014-12-31'),
      "positions_timeline.dates[0]: 2014-12-31 is before the run's sample_start 2015-01-02",
    ],
    [
      'end after the sample',
      (d) => void (d.dates[11] = '2015-03-23'),
      "positions_timeline.dates[11]: 2015-03-23 is after the run's sample_end 2015-03-20",
    ],
    ['have no counts', (d) => void delete (d as Obj).open_count, 'positions_timeline: missing required key "open_count"'],
    ['have counts that are not a list', (d) => void ((d as Obj).open_count = 1), 'positions_timeline.open_count: expected an array'],
    ['have fewer counts than sessions', (d) => void d.open_count.pop(), 'positions_timeline.open_count: has 11 values but dates has 12'],
    ['have more counts than sessions', (d) => void d.open_count.push(1), 'positions_timeline.open_count: has 13 values but dates has 12'],
    [
      'have a count that differs from the positions open at that close',
      (d) => void (d.open_count[3] = 2),
      'positions_timeline.open_count[3]: is 2 but 1 position(s) are open at the close of 2015-01-23',
    ],
    [
      'count a position on the day it closed (it is open at a close only while closed is after that session)',
      (d) => void (d.open_count[2] = 2),
      'positions_timeline.open_count[2]: is 2 but 1 position(s) are open at the close of 2015-01-16',
    ],
    ['have a fractional count', (d) => void (d.open_count[3] = 1.5), 'positions_timeline.open_count[3]: expected a whole number of at least 0, got 1.5'],
    ['have a negative count', (d) => void (d.open_count[3] = -1), 'positions_timeline.open_count[3]: expected a whole number of at least 0, got -1'],
    ['have a count that is text', (d) => void (d.open_count[3] = '1'), 'positions_timeline.open_count[3]: expected a whole number of at least 0, got 1'],
    ['have a count that is null', (d) => void (d.open_count[3] = null), 'positions_timeline.open_count[3]: expected a whole number of at least 0, got null'],
    ['have a count that is not finite', (d) => void (d.open_count[3] = Infinity), 'positions_timeline.open_count[3]: expected a whole number of at least 0, got Infinity'],
  ]
  it.each(sessionCases)('%s', (_what, change, fragment) => {
    rejectsP(brokenPositions(change), fragment)
  })
})
