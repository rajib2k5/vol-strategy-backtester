/**
 * Files the exporter writes from crafted smiles (tests/test_export_surface.py CASES, through src/volbt/build.py
 * surface_frame, and its own verdict from tools/export_app_data.py check_frame_ivs), read by the app. A Python test
 * fails when the exporter would now write something else, so these are the exporter's output, not hand-made frames.
 *
 * The app must accept every file the exporter writes and refuse every file it refuses. Each rule of round 3 (T1, X2,
 * P1, P6, N4) is then tested on one of these files with one contradiction written into it.
 */
import { describe, expect, it } from 'vitest'
import exporter from '../test/fixtures/surface_frames_exporter.json'
import { ContractError, MAX_IV, parseSurfaceFrames } from './contract'

interface Frame {
  expiries_used: number
  iv: number[][]
  cell_flags: number[][]
  quoted_share: number
  atm_iv_30d: number
}
interface Doc {
  run: Record<string, string | null>
  label: string
  grid_dte: number[]
  grid_moneyness: number[]
  frames: Frame[]
}
interface Case {
  name: string
  why: string
  exporter: string
  file: Doc
}

const cases = exporter.cases as unknown as Case[]

/** A fresh deep copy of a case's file, with one change applied to its frame. */
function changed(name: string, change: (f: Frame, d: Doc) => void = () => {}): Doc {
  const found = cases.find((c) => c.name === name)
  if (found === undefined) throw new Error(`no exporter case ${name}`)
  const d = JSON.parse(JSON.stringify(found.file)) as Doc
  change(d.frames[0], d)
  return d
}

/** quoted_share as the exporter writes it after a test edits the flags. */
function reshare(f: Frame): void {
  const cells = f.cell_flags.flat()
  f.quoted_share = Math.round((cells.filter((x) => (x & 5) === 0).length / cells.length) * 1e6) / 1e6
}

function rejects(raw: unknown, ...fragments: string[]): void {
  let err: unknown
  try {
    parseSurfaceFrames(raw)
  } catch (e) {
    err = e
  }
  expect(err, `expected a ContractError containing ${fragments.join(' and ')}`).toBeInstanceOf(ContractError)
  for (const fragment of fragments) expect((err as Error).message).toContain(fragment)
}

const K = (d: Doc, k: number) => d.grid_moneyness.indexOf(k)
const T = (d: Doc, days: number) => d.grid_dte.indexOf(days)

describe('the exporter cases', () => {
  it('are the twelve of tests/test_export_surface.py, two of them refused by the exporter', () => {
    expect(cases.map((c) => [c.name, c.exporter.split(':')[0]])).toEqual([
      ['t1_moved_past_the_back_above_5', 'writes'],
      ['x2_atm_cell_extrapolated_above_5', 'writes'],
      ['x1_wing_above_10', 'refuses'],
      ['rounding_raise_above_5', 'refuses'],
      ['p1_first_inside_row_on_a_later_expiry', 'writes'],
      ['p1_front_row_proven', 'writes'],
      ['p6_first_inside_row_on_a_later_expiry', 'writes'],
      ['p6_front_row_right_run_below_0', 'writes'],
      ['p6_front_row_beyond_everywhere', 'writes'],
      ['p6_front_row_left_run_above_0', 'writes'],
      ['p6_last_inside_row_on_an_earlier_expiry', 'writes'],
      ['n4_dolthub', 'writes'],
    ])
  })

  it.each(cases.map((c) => [c.name, c] as const))('%s: the app accepts it exactly when the exporter writes it', (_name, c) => {
    if (c.exporter === 'writes') {
      expect(parseSurfaceFrames(c.file).frames[0].iv).toEqual(c.file.frames[0].iv)
    } else {
      expect(() => parseSurfaceFrames(c.file)).toThrow(ContractError)
    }
  })
})

describe('T1: an IV above 5 only beyond the strikes, or past the back expiry where the calendar moved it', () => {
  it('the exporter writes 6.58 on a 14-day cell past the back with flags 12 (tenor and calendar, no strike bit)', () => {
    const d = changed('t1_moved_past_the_back_above_5')
    const [i, j] = [T(d, 14), K(d, -0.3)]
    expect([d.frames[0].iv[i][j], d.frames[0].cell_flags[i][j]]).toEqual([6.579568, 12])
    // 7 days is the last row on an expiry; every later row is past the back (10 days), with bit 4.
    expect(d.frames[0].cell_flags.map((row) => (row[0] & 4) !== 0)).toEqual([false, ...Array(10).fill(true)])
    expect(parseSurfaceFrames(d).frames[0].iv[i][j]).toBe(6.579568)
  })

  it('refuses the same cell without bit 8: past the back, bit 4 alone is the unmoved reading at x, inside the strikes', () => {
    // Before round 3 any extrapolation bit allowed 10, so this was accepted (the reviewer's T1 probe).
    const d = changed('t1_moved_past_the_back_above_5', (f, x) => (f.cell_flags[T(x, 14)][K(x, -0.3)] = 4))
    rejects(
      d,
      'surface_frames.frames[0].iv[1][0]: implied vol 6.579568 is outside (0, 5], the ceiling of a cell flagged 4 at k = -0.3 on the 14-day row',
    )
  })

  it('refuses a cell of bit 8 alone above 5 on the row on an expiry', () => {
    // The 7-day row sits on its expiry: bit 8 there moved a value inside some smile's strikes, so a solved IV bounds it.
    const d = changed('t1_moved_past_the_back_above_5', (f, x) => {
      f.cell_flags[0][K(x, -0.3)] = 8
      f.cell_flags[0][K(x, -0.28)] = 8
      reshare(f)
    })
    rejects(d, 'surface_frames.frames[0].iv[0][0]: implied vol 9.304914 is outside (0, 5], the ceiling of a cell flagged 8 at k = -0.3 on the 7-day row')
  })

  it('refuses a solved 5 raised to 5.000001 by the exporter rounding, which the exporter refuses too', () => {
    rejects(changed('rounding_raise_above_5'), 'surface_frames.frames[0].iv[1][0]: implied vol 5.000001 is outside (0, 5], the ceiling of a cell flagged 0')
    expect(MAX_IV).toBe(5)
  })

  it('refuses the wing above 10 that the exporter refuses', () => {
    rejects(changed('x1_wing_above_10'), 'surface_frames.frames[0].iv[0][20]: implied vol 10.005356 is outside (0, 5] (or (0, 10] where extrapolated)')
  })
})

describe('X2: atm_iv_30d has the ceiling of its own cell', () => {
  it('accepts an extrapolated 30-day k = 0 cell of 5.036 and atm_iv_30d equal to it', () => {
    // Before round 3 atm_iv_30d was capped at 5 whatever its cell, so the exporter's file was refused.
    const d = changed('x2_atm_cell_extrapolated_above_5')
    const [i, j] = [T(d, 30), K(d, 0)]
    expect([d.frames[0].atm_iv_30d, d.frames[0].iv[i][j], d.frames[0].cell_flags[i][j]]).toEqual([5.036368, 5.036368, 5])
    expect(parseSurfaceFrames(d).frames[0].atm_iv_30d).toBe(5.036368)
  })
})

describe('P1: bit 8 inside the strikes on the front expiry’s own row, when the file proves which row that is', () => {
  it('accepts bit 8 on the first inside row when more expiries were used than the rows need: it may sit on a later expiry', () => {
    // The exporter wrote it: a 10-day front between the 7- and 14-day rows lifted the 14-day expiry's quotes.
    const d = changed('p1_first_inside_row_on_a_later_expiry')
    expect([d.frames[0].expiries_used, d.frames[0].cell_flags[T(d, 14)][K(d, 0)]]).toEqual([3, 8])
    expect(parseSurfaceFrames(d).frames[0].cell_flags[1][15]).toBe(8)
  })

  it('refuses it once expiries_used is exactly what the rows need: the 14-day row is then the front, which nothing raises', () => {
    // Rows on an expiry: 14 and 60 days; the 21- to 45-day rows between them; so 2 expiries, none below 14 days.
    const d = changed('p1_first_inside_row_on_a_later_expiry', (f) => (f.expiries_used = 2))
    rejects(
      d,
      'surface_frames.frames[0].cell_flags[1][0]: carries SURFACE_CALENDAR_ADJUSTED inside the quoted strikes on the 14-day row, which sits on the front expiry (expiries_used 2 is exactly the expiries the rows need',
    )
  })

  it('accepts the proven front row as the exporter writes it (no bit 8), and refuses bit 8 on any of its quoted cells', () => {
    expect(parseSurfaceFrames(changed('p1_front_row_proven')).frames[0].cell_flags[0].every((x) => x === 0)).toBe(true)
    rejects(
      changed('p1_front_row_proven', (f, x) => (f.cell_flags[0][K(x, -0.3)] = 8)),
      'surface_frames.frames[0].cell_flags[0][0]: carries SURFACE_CALENDAR_ADJUSTED inside the quoted strikes on the 7-day row, which sits on the front expiry',
    )
  })

  it('accepts bit 8 beside bit 1 on the proven front row: a value beyond the strikes can be lowered to the next quote', () => {
    const d = changed('p6_front_row_right_run_below_0')
    expect(d.frames[0].cell_flags[T(d, 14)].slice(1).every((x) => x === 9)).toBe(true)
    expect(parseSurfaceFrames(d).frames[0].cell_flags[1][1]).toBe(9)
  })
})

describe('P6: the rows read off one expiry keep the order of that reading', () => {
  it('accepts a first inside row beyond its strikes at k = -0.3 where the earlier row is not, while it may sit on a later expiry', () => {
    const d = changed('p6_first_inside_row_on_a_later_expiry')
    expect([d.frames[0].cell_flags[0][0], d.frames[0].cell_flags[1][0]]).toEqual([4, 1])
    expect(parseSurfaceFrames(d).frames[0].cell_flags[1][0]).toBe(1)
  })

  it('refuses it once the 14-day row is proven the front: the 7-day row reads the front further left, beyond it too', () => {
    rejects(
      changed('p6_first_inside_row_on_a_later_expiry', (f) => (f.expiries_used = 2)),
      "surface_frames.frames[0].cell_flags[0][0]: carries no SURFACE_EXTRAP_STRIKE at k = -0.3 on the 7-day row, while the 14-day row is beyond the front expiry's left strike there",
    )
  })

  it('accepts what the exporter writes for a front left of the cells: beyond its RIGHT strike at k = -0.28, inside on the 7-day row', () => {
    const d = changed('p6_front_row_right_run_below_0')
    expect([d.frames[0].cell_flags[0][K(d, -0.28)], d.frames[0].cell_flags[1][K(d, -0.28)]]).toEqual([4, 9])
    expect(parseSurfaceFrames(d).frames[0].expiries_used).toBe(2)
  })

  it('accepts a front row beyond its strikes on every cell, the 7-day row inside at k = -0.3: which side each cell is on does not show', () => {
    const d = changed('p6_front_row_beyond_everywhere')
    expect([d.frames[0].cell_flags[1].every((x) => (x & 1) === 1), d.frames[0].cell_flags[0][0]]).toEqual([true, 4])
    expect(parseSurfaceFrames(d).frames[0].expiries_used).toBe(2)
  })

  it('accepts what the exporter writes for a calls-only front: beyond its LEFT strike at k = 0.04, inside on the 7-day row', () => {
    const d = changed('p6_front_row_left_run_above_0')
    expect([d.frames[0].cell_flags[0][K(d, 0.04)], d.frames[0].cell_flags[1][K(d, 0.04)]]).toEqual([4, 1])
    expect(parseSurfaceFrames(d).frames[0].cell_flags[1][K(d, 0.04)]).toBe(1)
  })

  it('accepts rows past the back beyond the strikes where the last inside row is not, while that row may sit on an earlier expiry', () => {
    // The 30-day row sits on a wide 30-day expiry; the back (40 days, narrow) is between the 30- and 45-day rows.
    const d = changed('p6_last_inside_row_on_an_earlier_expiry')
    expect([d.frames[0].cell_flags[T(d, 30)][0], d.frames[0].cell_flags[T(d, 45)][0]]).toEqual([0, 5])
    expect(parseSurfaceFrames(d).frames[0].cell_flags[4][0]).toBe(5)
  })

  it('refuses the front row beyond its LEFT strike at k = -0.3 while the 7-day row is inside there', () => {
    // The front row then reads inside its strikes at k = -0.28 only: a left run at -0.3 and the right run from -0.26.
    rejects(
      changed('p6_front_row_right_run_below_0', (f, x) => {
        f.cell_flags[T(x, 14)][K(x, -0.3)] = 1
        f.cell_flags[T(x, 14)][K(x, -0.28)] = 0
        reshare(f)
      }),
      "surface_frames.frames[0].cell_flags[0][0]: carries no SURFACE_EXTRAP_STRIKE at k = -0.3 on the 7-day row, while the 14-day row is beyond the front expiry's left strike there",
    )
  })

  it('refuses a k = 0 strike bit that differs between the rows read off the front: both read it at x = 0', () => {
    // The 7-day row inside the strikes from k = -0.3 to 0 (a right run only): the front row is beyond at k = 0.
    rejects(
      changed('p6_front_row_right_run_below_0', (f) => {
        f.cell_flags[0] = f.cell_flags[0].map((x, j) => (j <= 15 ? x & ~1 : x))
        reshare(f)
      }),
      "surface_frames.frames[0].cell_flags[1][15]: carries SURFACE_EXTRAP_STRIKE at k = 0 on the 14-day row but the 7-day row does not: both read the front expiry's smile at x = 0",
    )
  })

  it('refuses a k = 0 strike bit on an earlier row that the later row does not carry, when the run rule has nothing to say', () => {
    // The 14-day row proven the front, inside at k = 0; the 7-day row before it beyond there and on every cell right of
    // it and left of -0.24 (two edge runs), so the left run of the front row (k <= -0.26) is covered on the 7-day row.
    rejects(
      changed('p6_first_inside_row_on_a_later_expiry', (f) => {
        f.expiries_used = 2
        f.cell_flags[0] = f.cell_flags[0].map((x, j) => (j <= 2 || j >= 15 ? x | 1 : x))
        reshare(f)
      }),
      "surface_frames.frames[0].cell_flags[1][15]: carries no SURFACE_EXTRAP_STRIKE at k = 0 on the 14-day row but the 7-day row does",
    )
  })

  it('refuses a row past the back beyond its left strike at k = -0.3 while the proven back row is inside there', () => {
    // The 30-day row is proven the back (rows on 7, 14 and 30 days, 3 expiries); 45 days reads it at x = k sqrt(30 / 45),
    // nearer k = 0, so beyond the strikes there means beyond them on the back's own row too.
    rejects(
      changed('p1_front_row_proven', (f, x) => {
        f.cell_flags[T(x, 45)][K(x, -0.3)] |= 1
        reshare(f)
      }),
      "surface_frames.frames[0].cell_flags[3][0]: carries no SURFACE_EXTRAP_STRIKE at k = -0.3 on the 30-day row, while the 45-day row is beyond the back expiry's left strike there",
    )
  })

  it('refuses a row past the back beyond its right strike at k >= 0.16 while the rows between it and the back are not', () => {
    rejects(
      changed('p1_front_row_proven', (f, x) => {
        for (const k of [0.16, 0.18, 0.2]) f.cell_flags[T(x, 60)][K(x, k)] |= 1
        reshare(f)
      }),
      "surface_frames.frames[0].cell_flags[3][23]: carries no SURFACE_EXTRAP_STRIKE at k = 0.16 on the 30-day row, while the 60-day row is beyond the back expiry's right strike there; both read that smile along k sqrt(t / tau), the 30-day row further right",
    )
  })

  it('accepts the proven back row beyond its strikes where the rows past it are not: they read nearer k = 0', () => {
    const d = changed('p1_front_row_proven', (f, x) => {
      f.cell_flags[T(x, 30)][K(x, -0.3)] = 1
      reshare(f)
    })
    expect(parseSurfaceFrames(d).frames[0].cell_flags[3][0]).toBe(1)
  })

  it('refuses a row past the back beyond the strikes at k = -0.3 while a nearer row past it is not, the back row unproven', () => {
    // t1 case: 14 days on is past the 10-day back, which is no row: the 90-day row reads it nearer k = 0 than 45 days.
    rejects(
      changed('t1_moved_past_the_back_above_5', (f, x) => {
        for (const k of [-0.3, -0.28, -0.26]) f.cell_flags[T(x, 90)][K(x, k)] |= 1
        reshare(f)
      }),
      "surface_frames.frames[0].cell_flags[1][0]: carries no SURFACE_EXTRAP_STRIKE at k = -0.3 on the 14-day row, while the 90-day row is beyond the back expiry's left strike there",
    )
  })
})

describe('N4: a DoltHub export', () => {
  it('is accepted with the label the exporter builds for it', () => {
    const d = changed('n4_dolthub')
    expect([d.run.data_source, d.label]).toEqual([
      'dolthub',
      'SPY implied-vol surfaces from de-Americanised out-of-the-money quotes (DoltHub), read on a fixed grid of log-moneyness and days to expiry',
    ])
    expect(parseSurfaceFrames(d).run.data_source).toBe('dolthub')
  })
})
