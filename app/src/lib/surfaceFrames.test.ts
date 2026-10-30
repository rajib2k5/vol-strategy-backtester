import { describe, expect, it } from 'vitest'
import {
  ContractError,
  DATA_SOURCE_NAMES,
  EXTRAPOLATED_BITS,
  MAX_EXTRAPOLATED_IV,
  MAX_IV,
  MAX_SPY_CLOSE,
  MAX_VIX_CLOSE,
  MIN_SPY_CLOSE,
  MIN_VIX_CLOSE,
  RUN_KEYS,
  SURFACE_CELL_FLAG_NAMES,
  SURFACE_UNITS,
  SURFACE_UNIT_KEYS,
  dataSourceName,
  parseSurfaceFrames,
} from './contract'
import fixture from '../test/fixtures/surface_frames.json'

// A fresh, mutable deep copy per test so one case cannot leak into the next.
type Frame = Record<string, unknown> & { iv: unknown[]; cell_flags: unknown[] }
type Doc = Record<string, unknown> & { run: Record<string, unknown>; units: Record<string, unknown>; frames: Frame[] }
const copy = (): Doc => JSON.parse(JSON.stringify(fixture)) as Doc

/** The fixture with one change applied. */
function broken(change: (d: Doc) => void): Doc {
  const d = copy()
  change(d)
  return d
}

/** Assert parseSurfaceFrames(raw) throws a ContractError whose message contains `fragment`. */
function rejects(raw: unknown, fragment: string): void {
  let err: unknown
  try {
    parseSurfaceFrames(raw)
  } catch (e) {
    err = e
  }
  expect(err, `expected a ContractError containing "${fragment}"`).toBeInstanceOf(ContractError)
  expect((err as Error).message).toContain(fragment)
}

describe('parseSurfaceFrames: accepts', () => {
  it('returns the fixture unchanged (every field survives)', () => {
    expect(parseSurfaceFrames(fixture)).toEqual(fixture)
  })

  it('reads the run block in ADR-0001 order, the execution fields as null', () => {
    const run = parseSurfaceFrames(fixture).run
    expect(Object.keys(run)).toEqual([...RUN_KEYS])
    expect([run.execution_mode, run.fill_timing, run.cap_mode]).toEqual([null, null, null])
  })

  it('accepts the execution fields as strings too (a backtest run writes them)', () => {
    const d = broken((x) => {
      x.run.execution_mode = 'quote'
      x.run.fill_timing = 'next_close'
      x.run.cap_mode = 'hard'
    })
    expect(parseSurfaceFrames(d).run).toMatchObject({ execution_mode: 'quote', fill_timing: 'next_close', cap_mode: 'hard' })
  })

  it('drops unknown keys, at the top, in run, in units and in a frame (a MINOR bump may add fields)', () => {
    const d = broken((x) => {
      x.future = 1
      x.run.future = 'x'
      x.units.future = 'x'
      x.frames[0].future = 2
    })
    const parsed = parseSurfaceFrames(d)
    expect(parsed).not.toHaveProperty('future')
    expect(parsed.run).not.toHaveProperty('future')
    expect(parsed.units).not.toHaveProperty('future')
    expect(parsed.frames[0]).not.toHaveProperty('future')
  })

  it('accepts a quoted share rounded to 6 decimals (1/3 written as 0.333333)', () => {
    expect(parseSurfaceFrames(fixture).frames[0].quoted_share).toBe(0.333333)
  })

  it('counts only bits 1 and 4 as extrapolation: a cell between two expiries (bit 2) is quoted', () => {
    expect(EXTRAPOLATED_BITS).toBe(5)
    const d = broken((x) => {
      x.frames[0].cell_flags = [[2, 2, 2], [2, 2, 2]]
      x.frames[0].quoted_share = 1
    })
    expect(parseSurfaceFrames(d).frames[0].quoted_share).toBe(1)
  })

  it('accepts one frame whose date is both ends of the run sample', () => {
    const d = broken((x) => {
      x.frames.pop()
      x.run.sample_end = '2020-01-03'
    })
    expect(parseSurfaceFrames(d).frames).toHaveLength(1)
  })

  it('knows four cell flags, in bit order (1, 2, 4, 8); bit 8 is the calendar adjustment, which moves a value up or down', () => {
    expect([...SURFACE_CELL_FLAG_NAMES]).toEqual(['SURFACE_EXTRAP_STRIKE', 'SURFACE_CROSS_EXPIRY', 'SURFACE_EXTRAP_TENOR', 'SURFACE_CALENDAR_ADJUSTED'])
    expect(fixture.cell_flag_names).toEqual([...SURFACE_CELL_FLAG_NAMES])
  })

  it('reads each unit as the exporter writes it (SURFACE_UNITS), and the fixture carries exactly those', () => {
    expect(parseSurfaceFrames(fixture).units).toEqual(SURFACE_UNITS)
    expect(Object.keys(SURFACE_UNITS)).toEqual([...SURFACE_UNIT_KEYS])
    expect(SURFACE_UNITS.cell_flags).toBe(
      'bitmask of SURFACE_EXTRAP_STRIKE (1), SURFACE_CROSS_EXPIRY (2), SURFACE_EXTRAP_TENOR (4), SURFACE_CALENDAR_ADJUSTED (8)',
    )
  })

  it('accepts an adjusted cell: bit 8 beside bit 4, or beside bit 1, is a valid bitmask', () => {
    // 12 = tenor extrapolation + adjusted, 13 = strike + tenor + adjusted: both keep the cell extrapolated, so quoted_share stays.
    // Frame 0's 7-day row is before its front expiry (the 30-day row is between two), where the running minimum can lower a
    // cell; k = -0.1 is not k = 0, the one cell of that row the adjustment cannot move.
    const d = broken((x) => {
      x.frames[0].cell_flags = [[12, 4, 4], [10, 2, 3]]
    })
    expect(parseSurfaceFrames(d).frames[0].cell_flags[0][0]).toBe(12)
    const e = broken((x) => {
      x.frames[0].cell_flags = [[13, 4, 4], [10, 2, 3]]
    })
    expect(parseSurfaceFrames(e).frames[0].cell_flags[0][0]).toBe(13)
  })

  it('accepts a cell raised to exactly the variance above (equal is not falling), flagged or not', () => {
    // Frame 0, 30-day k = -0.1 cell: 0.12076147288491199 gives the same total variance as 0.25 at 7 days.
    expect(parseSurfaceFrames(fixture).frames[0].cell_flags[1][0] & 8).toBe(8)
    const unflagged = broken((x) => {
      x.frames[0].cell_flags = [[4, 4, 4], [2, 2, 3]]
    })
    expect(parseSurfaceFrames(unflagged).frames[0].cell_flags[1][0]).toBe(2)
  })

  it('accepts an implied vol of 4.99, and of exactly 5, where total variance still rises into it: the solver searches [1e-4, 5], so a high IV is a result', () => {
    // Frame 1, 30 days, k = -0.1: a quoted cell (flag 2) on the last tenor row, so variance only rises into it from the
    // 7-day row and nothing below can fall from it; atm_iv_30d is another cell. The refusal of 4.99 above a row of
    // ordinary IVs is under "total variance ... falling" below.
    for (const value of [4.99, MAX_IV]) {
      const d = broken((x) => {
        ;(x.frames[1].iv[1] as number[])[0] = value
      })
      expect(parseSurfaceFrames(d).frames[1].iv[1][0]).toBe(value)
    }
  })

  it('accepts an IV above 5 in an extrapolated cell, and refuses it in a quoted one', () => {
    // Round-2 review of E4: the exporter's strike wing (Lee's slope up to 2) can read 5.07 at a 7-day k = -0.30, which
    // the solver's [1e-4, 5] does not bound. Frame 0, 30 days, k = 0.1: flag 3 (strike-extrapolated), the last row.
    const wing = broken((x) => {
      ;(x.frames[0].iv[1] as number[])[2] = 6.5
    })
    expect(parseSurfaceFrames(wing).frames[0].iv[1][2]).toBe(6.5)
    expect(MAX_EXTRAPOLATED_IV).toBe(10)
    const percent = broken((x) => {
      ;(x.frames[0].iv[1] as number[])[2] = 10.5
    })
    expect(() => parseSurfaceFrames(percent)).toThrow('surface_frames.frames[0].iv[1][2]: implied vol 10.5 is outside (0, 5] (or (0, 10] where extrapolated)')
    // Frame 1, 30 days, k = -0.1: flag 2, read between two listed expiries without extrapolation.
    const quoted = broken((x) => {
      ;(x.frames[1].iv[1] as number[])[0] = 6.5
    })
    expect(() => parseSurfaceFrames(quoted)).toThrow(
      'surface_frames.frames[1].iv[1][0]: implied vol 6.5 is outside (0, 5], the ceiling of a cell flagged 2 at k = -0.1 on the 30-day row: only a cell beyond the quoted strikes, or one past the back expiry that the calendar adjustment moved, reads above a solved IV (5)')
  })

  it.each([
    ['spot', MIN_SPY_CLOSE],
    ['spot', MAX_SPY_CLOSE],
    ['vix_close', MIN_VIX_CLOSE],
    ['vix_close', MAX_VIX_CLOSE],
  ])('accepts %s = %j, an end of its plausible range', (key, value) => {
    expect(parseSurfaceFrames(broken((x) => (x.frames[0][key] = value))).frames[0][key as 'spot']).toBe(value)
  })

  it('states the plausible ranges: SPY [50, 2000] USD, VIX [5, 150] points', () => {
    expect([MIN_SPY_CLOSE, MAX_SPY_CLOSE, MIN_VIX_CLOSE, MAX_VIX_CLOSE]).toEqual([50, 2000, 5, 150])
  })

  it('accepts a cross-expiry cell with 2 expiries, and 1 expiry when no cell is between expiries', () => {
    expect(parseSurfaceFrames(broken((x) => (x.frames[0].expiries_used = 2))).frames[0].expiries_used).toBe(2)
    // 1 expiry at 30 days: the 7-day row is before it, and the 30-day row sits on it with its own smile, unadjusted.
    // Beyond its right strike at k = 0.1 on its own row, so beyond it on the 7-day row too, which reads x = 0.1 sqrt(30 / 7).
    const d = broken((x) => {
      x.frames[0].expiries_used = 1
      x.frames[0].cell_flags = [[4, 4, 5], [0, 0, 1]]
    })
    expect(parseSurfaceFrames(d).frames[0].expiries_used).toBe(1)
  })

  it('accepts a data_last_date on the very date of generated_at', () => {
    const d = broken((x) => (x.run.data_last_date = (x.generated_at as string).slice(0, 10)))
    expect(parseSurfaceFrames(d).run.data_last_date).toBe('2026-10-27')
  })

  it.each([
    ['2020-01-03', 'Friday'],
    ['2020-01-06', 'Monday'],
  ])('accepts a frame dated %s, a %s', (date) => {
    const d = broken((x) => {
      x.frames[0].date = date
      x.run.sample_start = date
    })
    expect(parseSurfaceFrames(d).frames[0].date).toBe(date)
  })

  it('accepts a data_last_date equal to the last frame date, and the dolthub vendor when the label names DoltHub', () => {
    const d = broken((x) => {
      x.run.data_last_date = '2020-03-16'
      x.run.data_source = 'dolthub'
      x.label = 'Test fixture (DoltHub): two made-up surfaces'
    })
    const parsed = parseSurfaceFrames(d)
    expect([parsed.run.data_last_date, parsed.run.data_source]).toEqual(['2020-03-16', 'dolthub'])
  })

  it.each(['0.3.0', '0.3.1', '0.4.0', '0.10.0'])('accepts schema_version %s (0.3.0 introduced the file; later minors are numbers, not strings)', (version) => {
    expect(parseSurfaceFrames(broken((x) => (x.schema_version = version))).schema_version).toBe(version)
  })
})

describe('dataSourceName', () => {
  it('maps each vendor to the name the Surface page shows', () => {
    expect(dataSourceName('optionsdx')).toBe('OptionsDX')
    expect(dataSourceName('dolthub')).toBe('DoltHub')
    expect(DATA_SOURCE_NAMES).toEqual({ optionsdx: 'OptionsDX', dolthub: 'DoltHub' })
  })
  it.each(['yahoo', 'OptionsDX', 'constructor', 'toString', '__proto__'])('refuses %s', (source) => {
    expect(() => dataSourceName(source)).toThrow(ContractError)
    expect(() => dataSourceName(source)).toThrow(`data_source: "${source}" is not a known data source`)
  })
})

describe('parseSurfaceFrames: rejects the envelope and the blocks', () => {
  it('a value that is not an object', () => {
    rejects([], 'surface_frames: expected an object')
  })
  it('an unsupported schema major', () => {
    rejects(broken((x) => (x.schema_version = '1.0.0')), 'surface_frames.schema_version: unsupported major version 1')
  })
  it.each(['0.2.9', '0.2.0', '0.1.0', '0.0.1'])('a schema_version (%s) older than the one that introduced surface_frames', (version) => {
    rejects(
      broken((x) => (x.schema_version = version)),
      `surface_frames.schema_version: "${version}" is older than 0.3.0, the version that introduced this file`,
    )
  })
  it('a bad generated_at', () => {
    rejects(broken((x) => (x.generated_at = '2026-02-30T00:00:00Z')), 'surface_frames.generated_at')
  })
  it('a bad source_commit', () => {
    rejects(broken((x) => (x.source_commit = 'main')), 'surface_frames.source_commit')
  })
  it('a missing run block', () => {
    rejects(broken((x) => delete (x as Record<string, unknown>).run), 'surface_frames: missing required key "run"')
  })
  it.each([...RUN_KEYS])('a run block without %s', (key) => {
    rejects(broken((x) => delete x.run[key]), `surface_frames.run: missing required key "${key}"`)
  })
  it.each(['run_id', 'config_hash', 'data_fingerprint', 'data_source', 'data_last_date', 'chain_mask'])('a null %s (only the execution fields may be null)', (key) => {
    rejects(broken((x) => (x.run[key] = null)), `surface_frames.run.${key}: expected a non-empty string`)
  })
  it('an execution field that is neither a string nor null', () => {
    rejects(broken((x) => (x.run.cap_mode = 0)), 'surface_frames.run.cap_mode: expected a non-empty string or null')
  })
  describe.each(['config_hash', 'data_fingerprint'])('%s that is not a SHA-256', (key) => {
    const good = fixture.run[key as 'config_hash']
    it.each([
      ['a word', 'x'],
      ['63 hex digits', good.slice(1)],
      ['65 hex digits', `${good}0`],
      ['uppercase hex', good.toUpperCase()],
      ['a non-hex digit', `g${good.slice(1)}`],
      ['a git commit id (40 hex digits)', good.slice(0, 40)],
    ])('%s', (_what, value) => {
      rejects(broken((x) => (x.run[key] = value)), `surface_frames.run.${key}: "${value}" is not a SHA-256 (64 lowercase hex digits)`)
    })
  })
  it.each(['yahoo', 'OptionsDX', 'constructor', 'toString'])('a data_source (%s) that is not optionsdx or dolthub', (source) => {
    rejects(broken((x) => (x.run.data_source = source)), `surface_frames.run.data_source: "${source}" is not a known data source (optionsdx, dolthub)`)
  })
  it('a data_source that the label does not name: dolthub while the label says OptionsDX', () => {
    rejects(
      broken((x) => (x.run.data_source = 'dolthub')),
      'surface_frames.label: does not name DoltHub, the vendor of run.data_source "dolthub"',
    )
  })
  it('a label that names no vendor at all', () => {
    rejects(
      broken((x) => (x.label = 'Test fixture: two made-up surfaces')),
      'surface_frames.label: does not name OptionsDX, the vendor of run.data_source "optionsdx"',
    )
  })
  it('a data_last_date that is not a calendar date', () => {
    rejects(broken((x) => (x.run.data_last_date = '2020-02-30')), 'surface_frames.run.data_last_date: "2020-02-30" is not a calendar date')
  })
  it('a sample that ends after the last date the source has', () => {
    rejects(
      broken((x) => (x.run.data_last_date = '2020-03-15')),
      'surface_frames.run.sample_end: 2020-03-16 is after data_last_date 2020-03-15, the last quote date the source has',
    )
  })
  it('a frame dated after the last date the source has, the sample adjusted to match', () => {
    rejects(
      broken((x) => {
        x.frames[1].date = '2031-01-03'
        x.run.sample_end = '2031-01-03'
      }),
      'surface_frames.run.sample_end: 2031-01-03 is after data_last_date 2020-04-30',
    )
  })
  it('a sample date that is not a calendar date', () => {
    rejects(broken((x) => (x.run.sample_start = '2020-01-32')), 'surface_frames.run.sample_start: "2020-01-32" is not a calendar date')
  })
  it('a sample that ends before it starts', () => {
    rejects(
      broken((x) => {
        x.run.sample_start = '2020-03-16'
        x.run.sample_end = '2020-01-03'
      }),
      'surface_frames.run.sample_end: 2020-01-03 is before sample_start 2020-03-16',
    )
  })
  it('a run sample that is not the span of the frames', () => {
    rejects(broken((x) => (x.run.sample_end = '2020-03-17')), 'surface_frames.run: samples 2020-01-03 to 2020-03-17 but the frames run from 2020-01-03 to 2020-03-16')
  })
  it.each([...SURFACE_UNIT_KEYS])('units without a unit for %s', (key) => {
    rejects(broken((x) => delete x.units[key]), `surface_frames.units: missing required key "${key}"`)
  })
  it('an empty unit string', () => {
    rejects(broken((x) => (x.units.iv = ' ')), 'surface_frames.units.iv: expected a non-empty string')
  })
  it.each([...SURFACE_UNIT_KEYS])('a unit for %s that is not the exporter’s string, by one word', (key) => {
    const edited = `${SURFACE_UNITS[key]} (edited)`
    rejects(broken((x) => (x.units[key] = edited)), `surface_frames.units.${key}: "${edited}" is not the exporter's unit for ${key}, "${SURFACE_UNITS[key]}"`)
  })
  it('the units of before the rename: bit 8 named SURFACE_CALENDAR_FLOOR', () => {
    rejects(
      broken((x) => (x.units.cell_flags = (x.units.cell_flags as string).replace('SURFACE_CALENDAR_ADJUSTED', 'SURFACE_CALENDAR_FLOOR'))),
      "surface_frames.units.cell_flags: \"bitmask of SURFACE_EXTRAP_STRIKE (1), SURFACE_CROSS_EXPIRY (2), SURFACE_EXTRAP_TENOR (4), SURFACE_CALENDAR_FLOOR (8)\" is not the exporter's unit",
    )
  })
  it.each([
    ['another hash', 'pricing-000000000000'],
    ['13 digits of the hash', 'pricing-9fc92382fa7c1'],
    ['11 digits of the hash', 'pricing-9fc92382fa7'],
    ['another prefix', 'backtest-9fc92382fa7c'],
  ])('a run_id that is not "pricing-" and the first 12 hex digits of config_hash (%s)', (_what, value) => {
    rejects(
      broken((x) => (x.run.run_id = value)),
      `surface_frames.run.run_id: "${value}" is not "pricing-9fc92382fa7c", the pricing build's name for config_hash 9fc92382fa7c1899027d2799e5e4d7354e23da15f013f5b4b297f3b84fc63339`,
    )
  })
  it('a data_last_date after the date of generated_at: the file holds quotes from after it was written', () => {
    rejects(
      broken((x) => (x.run.data_last_date = '2026-10-28')),
      'surface_frames.run.data_last_date: 2026-10-28 is after 2026-10-27, the date of generated_at: a file cannot hold quotes from after it was written',
    )
  })
  it('a generated_at before the frames, read as the date it writes (2020-04-29 at 23:00, five hours behind UTC)', () => {
    // In UTC that is 2020-04-30 04:00, on data_last_date; but 2020-04-30's quotes did not exist at 23:00 the night before.
    rejects(
      broken((x) => (x.generated_at = '2020-04-29T23:00:00-05:00')),
      'surface_frames.run.data_last_date: 2020-04-30 is after 2020-04-29, the date of generated_at',
    )
  })
  it.each([
    ['2020-03-14', 'Saturday'],
    ['2020-03-15', 'Sunday'],
  ])('a frame dated %s, a %s: a frame is one session, and a weekday is the proxy for one', (date, day) => {
    rejects(
      broken((x) => {
        x.frames[1].date = date
        x.run.sample_end = date
      }),
      `surface_frames.frames[1].date: ${date} is a ${day}: a frame is one session's quotes, and SPY does not trade at weekends`,
    )
  })
  it('units that are not an object', () => {
    rejects(broken((x) => ((x as Record<string, unknown>).units = ['USD'])), 'surface_frames.units: expected an object')
  })
  it.each([true, 'false', null])('illustrative = %s (must be exactly false)', (value) => {
    rejects(broken((x) => (x.illustrative = value)), 'surface_frames.illustrative: must be false')
  })
  it('an empty label', () => {
    rejects(broken((x) => (x.label = '')), 'surface_frames.label: expected a non-empty string')
  })
})

describe('parseSurfaceFrames: rejects the grid', () => {
  it('a log-moneyness grid that is not increasing', () => {
    rejects(broken((x) => (x.grid_moneyness = [-0.1, 0.1, 0.1])), 'surface_frames.grid_moneyness[2]: grid must be strictly increasing')
  })
  it('a non-finite log-moneyness', () => {
    rejects(broken((x) => (x.grid_moneyness = [-0.1, null, 0.1])), 'surface_frames.grid_moneyness[1]: expected a finite number')
  })
  it('a one-point grid', () => {
    rejects(broken((x) => (x.grid_moneyness = [0])), 'surface_frames.grid_moneyness: needs at least 2 values')
  })
  it.each([
    [[0, 30], 'surface_frames.grid_dte[0]: expected a whole number of days above 0, got 0'],
    [[7.5, 30], 'surface_frames.grid_dte[0]: expected a whole number of days above 0, got 7.5'],
    [[30, 7], 'surface_frames.grid_dte[1]: grid must be strictly increasing'],
  ])('a tenor grid %j', (grid, message) => {
    rejects(broken((x) => (x.grid_dte = grid)), message)
  })
  it('a tenor grid without the 30-day row, which atm_iv_30d is read from', () => {
    rejects(broken((x) => (x.grid_dte = [7, 31])), 'surface_frames.grid_dte: has no 30-day row, which atm_iv_30d is read from')
  })
  it('a moneyness grid without the k = 0 column, which atm_iv_30d is read from', () => {
    rejects(broken((x) => (x.grid_moneyness = [-0.1, 0.05, 0.1])), 'surface_frames.grid_moneyness: has no k = 0 column, which atm_iv_30d is read from')
  })
  it.each([
    [[...SURFACE_CELL_FLAG_NAMES].reverse(), 'reordered'],
    [SURFACE_CELL_FLAG_NAMES.slice(0, 3), 'the three names before the calendar adjustment'],
    [['SURFACE_EXTRAP_STRIKE', 'SURFACE_CROSS_EXPIRY', 'SURFACE_EXTRAP_TENOR', 'SURFACE_CALENDAR_FLOOR'], 'bit 8 under its old name'],
    [SURFACE_CELL_FLAG_NAMES.slice(0, 2), 'two short'],
    [[...SURFACE_CELL_FLAG_NAMES, 'MARK_JUMP'], 'one extra'],
  ])('cell_flag_names %j (%s)', (names) => {
    rejects(
      broken((x) => (x.cell_flag_names = names)),
      'surface_frames.cell_flag_names: expected SURFACE_EXTRAP_STRIKE, SURFACE_CROSS_EXPIRY, SURFACE_EXTRAP_TENOR, SURFACE_CALENDAR_ADJUSTED in bit order',
    )
  })
})

describe('parseSurfaceFrames: rejects a frame', () => {
  it('frames that are not an array, or none', () => {
    rejects(broken((x) => ((x as Record<string, unknown>).frames = {})), 'surface_frames.frames: expected an array')
    rejects(broken((x) => (x.frames = [])), 'surface_frames.frames: needs at least 1 frame')
  })
  it('a frame that is not an object', () => {
    rejects(broken((x) => ((x.frames as unknown[])[0] = 3)), 'surface_frames.frames[0]: expected an object')
  })
  it.each(['2020-02-30', '03/16/2020', '2020-3-16'])('a date %s', (date) => {
    rejects(broken((x) => (x.frames[1].date = date)), `surface_frames.frames[1].date: "${date}" is not a calendar date YYYY-MM-DD`)
  })
  it('two frames on the same date', () => {
    rejects(
      broken((x) => {
        x.frames[1].date = '2020-01-03'
        x.run.sample_end = '2020-01-03'
      }),
      'surface_frames.frames[1].date: frames must be in strictly increasing date order',
    )
  })
  it('an empty frame label', () => {
    rejects(broken((x) => (x.frames[0].label = ' ')), 'surface_frames.frames[0].label: expected a non-empty string')
  })
  it.each([
    ['spot', 0, 'is outside [50, 2000], the plausible range of a SPY close in USD'],
    ['spot', 49.99, '49.99 is outside [50, 2000]'],
    ['spot', 2000.01, '2000.01 is outside [50, 2000]'],
    ['spot', 32050, '32050 is outside [50, 2000]'],
    ['spot', '320', 'expected a finite number'],
    ['vix_close', -1, 'is outside [5, 150], the plausible range of a VIX close in index points'],
    ['vix_close', 0, 'is outside [5, 150]'],
    ['vix_close', 0.1247, '0.1247 is outside [5, 150]'],
    ['vix_close', 4.99, '4.99 is outside [5, 150]'],
    ['vix_close', 150.01, '150.01 is outside [5, 150]'],
    ['vix_close', 9999, 'is outside [5, 150]'],
    ['atm_iv_30d', '0.19', 'expected a finite number'],
    ['atm_iv_30d', 0, `is outside (0, ${MAX_IV}]`],
    ['atm_iv_30d', MAX_IV + 0.01, `is outside (0, ${MAX_IV}]`],
  ])('%s = %j', (key, value, message) => {
    rejects(broken((x) => (x.frames[0][key] = value)), `surface_frames.frames[0].${key}: `)
    rejects(broken((x) => (x.frames[0][key] = value)), message)
  })
  it.each([
    [0, 'a surface needs at least 1 usable expiry'],
    [2.5, 'expected a whole number of at least 0'],
  ])('expiries_used = %j', (value, message) => {
    rejects(broken((x) => (x.frames[0].expiries_used = value)), `surface_frames.frames[0].expiries_used: ${message}`)
  })
  it('an iv grid with a row too few', () => {
    rejects(broken((x) => x.frames[0].iv.pop()), 'surface_frames.frames[0].iv: has 1 rows but grid_dte has 2 values')
  })
  it('a ragged iv row', () => {
    rejects(broken((x) => (x.frames[0].iv[1] = [0.2, 0.2])), 'surface_frames.frames[0].iv[1]: has 2 values but grid_moneyness has 3 (ragged grid)')
  })
  it('an iv row that is not an array', () => {
    rejects(broken((x) => (x.frames[0].iv[1] = 0.2)), 'surface_frames.frames[0].iv[1]: expected an array of numbers')
  })
  it('an iv grid that is not an array', () => {
    rejects(broken((x) => ((x.frames[0] as Record<string, unknown>).iv = 'none')), 'surface_frames.frames[0].iv: expected an array')
  })
  it.each([
    [null, 'expected a finite number'],
    [0, `is outside (0, ${MAX_IV}]`],
    [18, `is outside (0, ${MAX_IV}]`],
  ])('an iv cell %j', (value, message) => {
    rejects(broken((x) => ((x.frames[0].iv[0] as unknown[])[2] = value)), `surface_frames.frames[0].iv[0][2]: `)
    rejects(broken((x) => ((x.frames[0].iv[0] as unknown[])[2] = value)), message)
  })
  it('a cell_flags grid of the wrong shape', () => {
    rejects(broken((x) => x.frames[1].cell_flags.pop()), 'surface_frames.frames[1].cell_flags: has 1 rows but grid_dte has 2 values')
  })
  it.each([16, -1, 1.5])('a cell flag %j', (value) => {
    rejects(broken((x) => ((x.frames[1].cell_flags[0] as unknown[])[0] = value)), `surface_frames.frames[1].cell_flags[0][0]: expected a bitmask from 0 to 15, got ${value}`)
  })
  it.each([6, 7, 14, 15])('a cell flag %j: between two expiries and outside the listed tenors at once', (value) => {
    // Frame 0, 7-day k = -0.1 is flagged 4. Every value here keeps it extrapolated (bit 4), so quoted_share stays right
    // and the whole 7-day row still carries bit 4: the one contradiction left is bit 2 beside bit 4.
    rejects(
      broken((x) => ((x.frames[0].cell_flags[0] as unknown[])[0] = value)),
      `surface_frames.frames[0].cell_flags[0][0]: flags ${value} set SURFACE_CROSS_EXPIRY and SURFACE_EXTRAP_TENOR together`,
    )
  })
  it('a cross-expiry cell in a frame that used 1 expiry', () => {
    // Frame 0 has 3 cells between expiries (flags 10, 2 and 3).
    rejects(
      broken((x) => (x.frames[0].expiries_used = 1)),
      'surface_frames.frames[0].expiries_used: is 1 but 3 cell(s) carry SURFACE_CROSS_EXPIRY, which needs at least 2 listed expiries',
    )
  })
  it('a tenor extrapolation on some cells of a row but not all', () => {
    // Frame 0, 7-day row: 4, 4, 1. Cell 2 swaps bit 4 for bit 1, so it is still an extrapolation and quoted_share stays.
    rejects(
      broken((x) => ((x.frames[0].cell_flags[0] as unknown[])[2] = 1)),
      'surface_frames.frames[0].cell_flags[0]: 2 of 3 cells of the 7-day row carry SURFACE_EXTRAP_TENOR; the flag is for a whole row or none',
    )
  })
  it('a tenor extrapolation on one cell of a row that has none', () => {
    // Frame 1, 30-day row: 2, 2, 3 becomes 2, 2, 5; cell 2 is extrapolated either way, and the tenor bit is checked first.
    rejects(
      broken((x) => ((x.frames[1].cell_flags[1] as unknown[])[2] = 5)),
      'surface_frames.frames[1].cell_flags[1]: 1 of 3 cells of the 30-day row carry SURFACE_EXTRAP_TENOR; the flag is for a whole row or none',
    )
  })
  it('a frame dated after the last date the source has (the run sample left alone)', () => {
    rejects(
      broken((x) => (x.frames[1].date = '2020-05-01')),
      'surface_frames.frames[1].date: 2020-05-01 is after run.data_last_date 2020-04-30, the last quote date the source has',
    )
  })
  describe('total variance iv * iv * dte / 365 falling from one tenor row to the next at a fixed k', () => {
    // Frame 0, k = 0.1: 0.18 at 7 days is variance 0.0324 * 7 / 365; 0.05 at 30 days is 0.0025 * 30 / 365, lower.
    it('is refused when the later cell carries no calendar bit', () => {
      rejects(
        broken((x) => ((x.frames[0].iv[1] as unknown[])[2] = 0.05)),
        'surface_frames.frames[0].iv[1][2]: total variance 0.000205479 at 30 days is below 0.000621370 at 7 days (k = 0.1)',
      )
    })
    it('is refused when the falling cell itself carries bit 8: the adjustment says a value moved, never that it may fall', () => {
      // Until round 2 bit 8 excused a fall (the test was "accepts a flagged cell whose variance is below the row above").
      const d = broken((x) => {
        ;(x.frames[0].iv[1] as number[])[2] = 0.05
        ;(x.frames[0].cell_flags[1] as number[])[2] = 11
      })
      rejects(
        d,
        "surface_frames.frames[0].iv[1][2]: total variance 0.000205479 at 30 days is below 0.000621370 at 7 days (k = 0.1); it never falls with tenor, whatever the cell's flags",
      )
    })
    it('is not excused by bit 8 on another cell of the row', () => {
      // [1][0] already carries bit 8 in the fixture; the falling cell is [1][2].
      const d = broken((x) => ((x.frames[0].iv[1] as unknown[])[2] = 0.05))
      expect((d.frames[0].cell_flags[1] as number[])[0]).toBe(10)
      rejects(d, 'surface_frames.frames[0].iv[1][2]: total variance')
    })
    it('refuses an IV of 4.99 above a row of ordinary IVs: the cell check passes it, the calendar check does not', () => {
      // Frame 1, 7 days, k = -0.1: 4.99 is variance 24.9001 * 7 / 365, far above 0.81 * 30 / 365 at 30 days.
      rejects(
        broken((x) => ((x.frames[1].iv[0] as number[])[0] = 4.99)),
        'surface_frames.frames[1].iv[1][0]: total variance 0.0665753 at 30 days is below 0.477536 at 7 days (k = -0.1)',
      )
    })
    describe('on a grid of three tenors, row against the row directly above', () => {
      /** The fixture with a 90-day row added to both frames (flags keep quoted_share at 4/9 and 7/9). */
      const threeTenors = (change: (d: Doc) => void = () => {}): Doc =>
        broken((x) => {
          x.grid_dte = [7, 30, 90]
          x.frames[0].iv.push([0.3, 0.25, 0.3])
          x.frames[0].cell_flags.push([2, 2, 3])
          x.frames[0].quoted_share = 0.444444
          x.frames[1].iv.push([0.9, 0.8, 0.7])
          x.frames[1].cell_flags.push([2, 2, 3])
          x.frames[1].quoted_share = 0.777778
          ;(x.frames[0].iv[1] as number[])[2] = 0.5
          change(x)
        })
      it('accepts a column that rises at every step', () => {
        expect(parseSurfaceFrames(threeTenors()).frames[0].iv).toHaveLength(3)
      })
      it('refuses a fall from 30 to 90 days even though 90 days is still above 7 days', () => {
        // k = 0.1 in frame 0: 7 days 0.18 (variance 0.0324 * 7), 30 days 0.5 (0.25 * 30), 90 days 0.2 (0.04 * 90): above the first, below the second.
        rejects(
          threeTenors((x) => ((x.frames[0].iv[2] as unknown[])[2] = 0.2)),
          'surface_frames.frames[0].iv[2][2]: total variance 0.00986301 at 90 days is below 0.0205479 at 30 days (k = 0.1)',
        )
      })
    })
    describe('against the float slack, 1e-12 of the variance above', () => {
      // Frame 0, 30 days, k = -0.1, unflagged: an IV whose variance is the 7-day one (0.25 at 7 days) times 1 - rel.
      const fallBy = (rel: number): Doc =>
        broken((x) => {
          ;(x.frames[0].iv[1] as number[])[0] = Math.sqrt(((((0.25 * 0.25 * 7) / 365) * (1 - rel)) * 365) / 30)
          x.frames[0].cell_flags = [[4, 4, 4], [2, 2, 3]]
        })
      it('accepts a fall of 5e-13 of the variance: float noise, not a fall', () => {
        expect(parseSurfaceFrames(fallBy(5e-13)).frames[0].iv[1][0]).toBeLessThan(0.12076147288491199)
      })
      it('refuses a fall of 2e-12 of the variance', () => {
        rejects(fallBy(2e-12), 'surface_frames.frames[0].iv[1][0]: total variance')
      })
      it('accepts an IV a few doubles below the exact raise (0.12076147288491197), which the exact check of round 1 refused', () => {
        // 0.12076147288491199 gives exactly the variance of 0.25 at 7 days (see the accepting test above).
        const d = broken((x) => {
          ;(x.frames[0].iv[1] as unknown[])[0] = 0.12076147288491197
          x.frames[0].cell_flags = [[4, 4, 4], [2, 2, 3]]
        })
        expect(parseSurfaceFrames(d).frames[0].iv[1][0]).toBe(0.12076147288491197)
      })
    })
  })
  describe('flags that do not fit the tenors and strikes they sit on', () => {
    it('a cross-expiry bit on some cells of a row but not all: a row is between two expiries or it is not', () => {
      // Frame 1, 30-day row: 2, 2, 3 becomes 0, 2, 3; no extrapolation bit changes, so quoted_share stays.
      rejects(
        broken((x) => ((x.frames[1].cell_flags[1] as unknown[])[0] = 0)),
        'surface_frames.frames[1].cell_flags[1]: 2 of 3 cells of the 30-day row carry SURFACE_CROSS_EXPIRY; the flag is for a whole row or none',
      )
    })
    it('more rows on a listed expiry than the frame used expiries', () => {
      // Frame 1 with both rows on an expiry (no tenor bit) needs 2 expiries; it says 1.
      rejects(
        broken((x) => {
          x.frames[1].cell_flags = [[0, 0, 0], [0, 0, 1]]
          x.frames[1].expiries_used = 1
        }),
        'surface_frames.frames[1].expiries_used: is 1 but the rows need at least 2 listed expiries: 2 row(s) on an expiry',
      )
    })
    it('a strike-extrapolated cell with quoted cells on both sides of it', () => {
      // Frame 1, 30-day row: 2, 2, 3 becomes 2, 3, 2: still one extrapolated cell, now at k = 0 between two quoted ones.
      rejects(
        broken((x) => (x.frames[1].cell_flags[1] = [2, 3, 2])),
        'surface_frames.frames[1].cell_flags[1][1]: carries SURFACE_EXTRAP_STRIKE at k = 0 in the 30-day row, with cells read inside the quoted strikes on both sides',
      )
    })
    it('accepts strike-extrapolated runs from both edges of a row', () => {
      const d = broken((x) => {
        x.frames[1].cell_flags[1] = [3, 2, 3]
        x.frames[1].quoted_share = 0.666667
      })
      expect(parseSurfaceFrames(d).frames[1].cell_flags[1]).toEqual([3, 2, 3])
    })
    it('bit 8 on the row of a frame that used 1 expiry: there is no other expiry to adjust its own smile against', () => {
      // Until round 2 this file was accepted (the test was "accepts ... 1 expiry when no cell is between expiries").
      rejects(
        broken((x) => {
          x.frames[0].expiries_used = 1
          x.frames[0].cell_flags = [[4, 4, 5], [8, 0, 1]]
        }),
        "surface_frames.frames[0].cell_flags[1][0]: carries SURFACE_CALENDAR_ADJUSTED on the 30-day row, which sits on the frame's only expiry",
      )
    })
    it('bit 8 at k = 0 before the front expiry, inside its strikes: the variance there rises linearly to the quoted front', () => {
      // Frame 0's 7-day row is before the front expiry (the 30-day row is between two); its k = 0 cell carries no strike bit.
      rejects(
        broken((x) => (x.frames[0].cell_flags[0] = [4, 12, 4])),
        'surface_frames.frames[0].cell_flags[0][1]: carries SURFACE_CALENDAR_ADJUSTED at k = 0 on the 7-day row, before the front expiry and inside its strikes',
      )
    })
    it.each([
      ['beyond the front strikes at k = 0 (the front is extrapolated there, so it may have been moved)', [[5, 13, 4], [10, 2, 3]], 0.333333],
      ['when every row is outside the listed expiries, so which rows lead is unknown', [[4, 12, 4], [12, 4, 5]], 0],
      ['on a row between two expiries', [[4, 4, 4], [10, 10, 3]], 0.333333],
    ])('accepts bit 8 at k = 0 %s', (_why, cell_flags, quoted_share) => {
      const d = broken((x) => {
        x.frames[0].cell_flags = cell_flags
        x.frames[0].quoted_share = quoted_share
      })
      expect(parseSurfaceFrames(d).frames[0].cell_flags).toEqual(cell_flags)
    })
  })
  it.each([1.2, -0.1])('a quoted share %j outside [0, 1]', (value) => {
    rejects(broken((x) => (x.frames[0].quoted_share = value)), 'surface_frames.frames[0].quoted_share: expected a share between 0 and 1')
  })
  it('a quoted share that is not the share of cells without an extrapolation flag', () => {
    rejects(
      broken((x) => (x.frames[0].quoted_share = 0.5)),
      'surface_frames.frames[0].quoted_share: is 0.5 but 0.333333 of the cells carry no extrapolation flag',
    )
  })
  it.each([
    [0.5, 'a number that is no cell of the grid'],
    [0.2, 'the 7-day k = 0 cell (frame 0)'],
    [0.18, 'the 30-day k = 0.1 cell (frame 0)'],
    [0.19000000000000003, 'the right cell plus one ulp'],
  ])('atm_iv_30d = %j (%s) is not the grid\'s 30-day, k = 0 cell', (value) => {
    expect(value).not.toBe(0.19)
    rejects(
      broken((x) => (x.frames[0].atm_iv_30d = value)),
      `surface_frames.frames[0].atm_iv_30d: is ${value} but the grid's 30-day, k = 0 cell is 0.19`,
    )
  })
  it('a quoted share that counts the cross-expiry bit as extrapolation', () => {
    // Frame 1 has 1 cell with bit 1, 2 cells with only bit 2 and 3 with none: quoted 5/6, not 1/6.
    rejects(broken((x) => (x.frames[1].quoted_share = 0.166667)), 'is 0.166667 but 0.833333 of the cells')
  })
})

describe('round 3 (F9): the ceiling of each cell, atm_iv_30d, and bit 8 on the proven front row', () => {
  // Frame 1: 7 days on an expiry, 30 days between two. Made outside, its 30-day row is past the back expiry.
  const pastBack = (flags: number[]): Doc =>
    broken((x) => {
      x.frames[1].cell_flags[1] = flags
      ;(x.frames[1].iv[1] as number[])[0] = 6
      x.frames[1].quoted_share = 0.5
    })
  it('accepts an IV above 5 on a cell past the back expiry flagged 12: the calendar adjustment read beyond the back smile', () => {
    expect(parseSurfaceFrames(pastBack([12, 4, 5])).frames[1].iv[1][0]).toBe(6)
  })
  it('refuses it flagged 4 alone: unmoved, the cell is the back smile read at x, inside its strikes', () => {
    rejects(pastBack([4, 4, 5]), 'surface_frames.frames[1].iv[1][0]: implied vol 6 is outside (0, 5], the ceiling of a cell flagged 4 at k = -0.1 on the 30-day row')
  })
  // Frame 0: its 7-day row is before the front expiry (the 30-day row is between two).
  const beforeFront = (cell_flags: number[][], quoted_share: number): Doc =>
    broken((x) => {
      ;(x.frames[0].iv[0] as number[])[0] = 5.5
      ;(x.frames[0].iv[1] as number[])[0] = 2.66 // total variance 2.66^2 x 30 above 5.5^2 x 7: it still rises
      x.frames[0].cell_flags = cell_flags
      x.frames[0].quoted_share = quoted_share
    })
  it('refuses an IV above 5 flagged 12 before the front expiry: there the running minimum only lowers the value', () => {
    rejects(
      beforeFront([[12, 4, 4], [10, 2, 3]], 0.333333),
      'surface_frames.frames[0].iv[0][0]: implied vol 5.5 is outside (0, 5], the ceiling of a cell flagged 12 at k = -0.1 on the 7-day row',
    )
  })
  it('accepts it when every row is outside the listed expiries: either row may be past the back', () => {
    expect(parseSurfaceFrames(beforeFront([[12, 4, 4], [12, 4, 5]], 0)).frames[0].iv[0][0]).toBe(5.5)
  })
  it('accepts atm_iv_30d above 5 when its cell is beyond the strikes: its ceiling is that cell’s (X2)', () => {
    // Before round 3 atm_iv_30d was capped at 5 whatever its cell.
    const d = broken((x) => {
      x.frames[0].cell_flags[1] = [10, 3, 3]
      ;(x.frames[0].iv[1] as number[])[1] = 6
      x.frames[0].atm_iv_30d = 6
      x.frames[0].quoted_share = 0.166667
    })
    expect(parseSurfaceFrames(d).frames[0].atm_iv_30d).toBe(6)
  })
  it('refuses atm_iv_30d above its cell’s ceiling of 5 where the cell is quoted', () => {
    rejects(broken((x) => (x.frames[0].atm_iv_30d = 5.5)), 'surface_frames.frames[0].atm_iv_30d: 5.5 is outside (0, 5]')
  })
  // Frame 1 needs 2 expiries: one on its 7-day row, one above its 30-day row (between two).
  const frontBit8 = (expiries_used: number): Doc =>
    broken((x) => {
      x.frames[1].expiries_used = expiries_used
      x.frames[1].cell_flags[0] = [8, 0, 0]
    })
  it('accepts bit 8 on a quoted cell of the first inside row when the frame used more expiries than its rows need', () => {
    expect(parseSurfaceFrames(frontBit8(5)).frames[1].cell_flags[0][0]).toBe(8)
  })
  it('refuses it when expiries_used is exactly what the rows need: the 7-day row is then the front, which nothing raises (P1)', () => {
    rejects(
      frontBit8(2),
      'surface_frames.frames[1].cell_flags[0][0]: carries SURFACE_CALENDAR_ADJUSTED inside the quoted strikes on the 7-day row, which sits on the front expiry (expiries_used 2 is exactly the expiries the rows need, so none is shorter)',
    )
  })
})
