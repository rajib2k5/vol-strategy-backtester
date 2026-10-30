/**
 * The surface_frames rules of round 2, each tested on the file the exporter committed (app/public/data/surface_frames.json)
 * with one contradiction written into it, the way the round-2 design review built its cases A to M. Every case starts from
 * a file the parser accepts (the first test), so a refusal is the contradiction's.
 *
 * The cases lean on the committed grid and expiries (which rows sit on, between or outside the listed expiries), and those
 * are fixed by the frame dates and the grid, not by how the pricing build moves values. A re-export that changes them
 * fails the precondition checks here, by name, rather than testing something else.
 */
import { describe, expect, it } from 'vitest'
import committedText from '../../public/data/surface_frames.json?raw'
import { ContractError, MAX_IV, SURFACE_UNITS, parseSurfaceFrames } from './contract'

interface Frame {
  date: string
  label: string
  spot: number
  vix_close: number
  expiries_used: number
  iv: number[][]
  cell_flags: number[][]
  quoted_share: number
}
interface Doc {
  generated_at: string
  run: Record<string, string | null>
  units: Record<string, string>
  label: string
  grid_dte: number[]
  frames: Frame[]
}

/** A fresh deep copy of the committed file. */
const committed = (): Doc => JSON.parse(committedText) as Doc

/** The committed file with one change applied. */
function changed(change: (d: Doc) => void): Doc {
  const d = committed()
  change(d)
  return d
}

/** quoted_share as the exporter writes it after a test edits the flags: the share of cells with neither bit 1 nor 4, to 6 decimals. */
function reshare(f: Frame): void {
  const cells = f.cell_flags.flat()
  f.quoted_share = Math.round((cells.filter((x) => (x & 5) === 0).length / cells.length) * 1e6) / 1e6
}

/** Assert parseSurfaceFrames(raw) throws a ContractError whose message contains every fragment. */
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

const noTenorBit = (row: number[]) => row.every((x) => (x & 6) === 0)
const crossBit = (row: number[]) => row.every((x) => (x & 2) !== 0)

describe('the committed surface_frames.json', () => {
  it('is accepted as committed, so each case below fails on its own change', () => {
    expect(parseSurfaceFrames(committed()).frames).toHaveLength(4)
  })

  it('has the rows the cases lean on (preconditions)', () => {
    const [f0, f1, f2, f3] = committed().frames
    // Frame 0 (27 expiries): 7, 14 and 21 days sit on listed expiries, 30 to 365 days between two.
    expect([f0.expiries_used, f0.cell_flags.map(noTenorBit)]).toEqual([27, [true, true, true, false, false, false, false, false, false, false, false]])
    expect(f0.cell_flags.slice(3).every(crossBit)).toBe(true)
    // Frame 1: only 30 days sits on an expiry; every other row is between two.
    expect(f1.cell_flags.map(noTenorBit)).toEqual([false, false, false, true, false, false, false, false, false, false, false])
    expect([0, 1, 2, 4, 5, 6, 7, 8, 9, 10].every((i) => crossBit(f1.cell_flags[i]))).toBe(true)
    // Frame 2: its 60-day row sits on an expiry, its 45- and 90-day rows are between two. Frame 3: 30 days is between two.
    expect([noTenorBit(f2.cell_flags[5]), crossBit(f2.cell_flags[4]), crossBit(f2.cell_flags[6])]).toEqual([true, true, true])
    expect(crossBit(f3.cell_flags[3])).toBe(true)
    // Frame 0, 7 days: k = 0 (column 15) carries no flag at all.
    expect(f0.cell_flags[0][15]).toBe(0)
  })
})

describe('the round-2 review cases: each refused, or accepted for the reason given', () => {
  it('A: w falling from 14 to 21 days at k = 0, the falling cell flagged bit 8, is refused: bit 8 never excuses a fall', () => {
    const d = changed((x) => {
      const f = x.frames[0]
      f.iv[2][15] = f.iv[1][15] * 0.3
      f.cell_flags[2][15] |= 8
    })
    rejects(d, 'surface_frames.frames[0].iv[2][15]: total variance', 'at 21 days is below', "it never falls with tenor, whatever the cell's flags")
  })

  it('A2: the 365-day row at half its IV with every cell flagged bit 8 is refused', () => {
    const d = changed((x) => {
      const f = x.frames[1]
      f.iv[10] = f.iv[10].map((v) => v * 0.5)
      f.cell_flags[10] = f.cell_flags[10].map((v) => v | 8)
    })
    rejects(d, 'surface_frames.frames[1].iv[10][', 'at 365 days is below', 'at 270 days')
  })

  it('B: the 60-day row outside the listed tenors while the rows around it are inside them is refused', () => {
    const d = changed((x) => {
      const f = x.frames[2]
      f.cell_flags[5] = f.cell_flags[5].map((v) => (v & ~2) | 4)
      reshare(f)
    })
    rejects(
      d,
      'surface_frames.frames[2].cell_flags[5]: the 60-day row carries SURFACE_EXTRAP_TENOR between the 7-day and 365-day rows, which are inside the listed expiries',
    )
  })

  it('C: 1 expiry, every cell unflagged (all 11 tenors read on an expiry), quoted_share 1, is refused', () => {
    const d = changed((x) => {
      const f = x.frames[0]
      f.expiries_used = 1
      f.cell_flags = f.cell_flags.map((row) => row.map(() => 0))
      f.quoted_share = 1
    })
    rejects(d, 'surface_frames.frames[0].expiries_used: is 1 but the rows need at least 11 listed expiries: 11 row(s) on an expiry')
  })

  it('D: a frame and data_last_date in 2031, after the date of generated_at, are refused', () => {
    const d = changed((x) => {
      x.run.data_last_date = '2031-12-31'
      x.frames[3].date = '2031-06-13'
      x.run.sample_end = '2031-06-13'
    })
    rejects(d, `surface_frames.run.data_last_date: 2031-12-31 is after ${d.generated_at.slice(0, 10)}, the date of generated_at`)
  })

  it('D2: a generated_at in 2012, before the data it holds, is refused', () => {
    const d = changed((x) => (x.generated_at = '2012-01-01T00:00:00Z'))
    rejects(d, `surface_frames.run.data_last_date: ${d.run.data_last_date} is after 2012-01-01, the date of generated_at`)
  })

  it('E: units.iv saying percent over decimal values is refused, and so is any unit that is not the exporter’s', () => {
    rejects(
      changed((x) => (x.units.iv = 'implied volatility in percent (20 = 20%)')),
      `surface_frames.units.iv: "implied volatility in percent (20 = 20%)" is not the exporter's unit for iv, "${SURFACE_UNITS.iv}"`,
    )
    expect(committed().units).toMatchObject(SURFACE_UNITS)
  })

  it('F: a run_id naming another config hash is refused', () => {
    const d = changed((x) => (x.run.run_id = 'pricing-000000000000'))
    rejects(d, `surface_frames.run.run_id: "pricing-000000000000" is not "pricing-${(d.run.config_hash as string).slice(0, 12)}"`)
    expect(committed().run.run_id).toBe(`pricing-${(committed().run.config_hash as string).slice(0, 12)}`)
  })

  it('G: data_source dolthub with a label naming DoltHub is accepted: a DoltHub surface is valid (the Surface page shows its notice)', () => {
    const d = changed((x) => {
      x.run.data_source = 'dolthub'
      x.label = x.label.replace('OptionsDX', 'DoltHub')
    })
    expect(parseSurfaceFrames(d).run.data_source).toBe('dolthub')
  })

  it.each([
    ['2023-06-17', 'Saturday'],
    ['2023-06-18', 'Sunday'],
  ])('H: a frame dated %s, a %s, is refused (a weekday is the proxy for a session)', (date, day) => {
    const d = changed((x) => {
      x.frames[3].date = date
      x.run.sample_end = date
    })
    rejects(d, `surface_frames.frames[3].date: ${date} is a ${day}`)
  })

  it('I: a SPY close of $1,000,000,000 is refused', () => {
    rejects(changed((x) => (x.frames[0].spot = 1e9)), 'surface_frames.frames[0].spot: 1000000000 is outside [50, 2000], the plausible range of a SPY close in USD')
  })

  it('J: a VIX close of 0.001 is refused', () => {
    rejects(changed((x) => (x.frames[0].vix_close = 0.001)), 'surface_frames.frames[0].vix_close: 0.001 is outside [5, 150], the plausible range of a VIX close in index points')
  })

  it('K: bit 8 on every cell of the 7-day row is accepted, because that row sits on a listed expiry, which the adjustment can move', () => {
    // Bit 8 means "moved by the calendar adjustment, up or down". Frame 0's 7-day row is a listed expiry's own smile
    // (no tenor bit), not a row before the front: a quoted value there is raised to a shorter expiry's, and a value read
    // beyond its strikes is held between its quoted neighbours. The frame used 27 expiries and the grid starts at 7
    // days, so the file cannot say none is shorter. Only the moved value is in the file, so the move cannot be checked.
    const d = changed((x) => {
      const f = x.frames[0]
      f.cell_flags[0] = f.cell_flags[0].map((v) => v | 8)
    })
    expect(parseSurfaceFrames(d).frames[0].cell_flags[0].every((v) => (v & 8) === 8)).toBe(true)
  })

  it('L: every frame labelled "calm", VIX 82.69 too, is accepted: the label is the exporter’s hand-written text, not derived from VIX', () => {
    const d = changed((x) => {
      for (const f of x.frames) f.label = 'calm'
    })
    expect(parseSurfaceFrames(d).frames.map((f) => [f.label, f.vix_close])).toContainEqual(['calm', 82.69])
  })

  it('M: the 7-day row between two expiries and the 14-day row before the front expiry is refused', () => {
    const d = changed((x) => {
      const f = x.frames[3]
      f.cell_flags[0] = f.cell_flags[0].map((v) => (v & ~4) | 2)
      f.cell_flags[1] = f.cell_flags[1].map((v) => (v & ~2) | 4)
      reshare(f)
    })
    rejects(d, 'surface_frames.frames[3].cell_flags[1]: the 14-day row carries SURFACE_EXTRAP_TENOR between the 7-day and 365-day rows')
  })
})

describe('each new rule on the committed file', () => {
  it('an IV of 4.99 in a quoted cell above ordinary rows is refused by the calendar check, and accepted on the last row', () => {
    rejects(changed((x) => (x.frames[0].iv[3][15] = 4.99)), 'surface_frames.frames[0].iv[4][15]: total variance', 'at 45 days is below')
    for (const value of [4.99, MAX_IV]) {
      expect(parseSurfaceFrames(changed((x) => (x.frames[0].iv[10][15] = value))).frames[0].iv[10][15]).toBe(value)
    }
  })

  it('a cross-expiry bit missing from one cell of a row between two expiries is refused', () => {
    rejects(
      changed((x) => (x.frames[3].cell_flags[3][15] &= ~2)),
      'surface_frames.frames[3].cell_flags[3]: 25 of 26 cells of the 30-day row carry SURFACE_CROSS_EXPIRY; the flag is for a whole row or none',
    )
  })

  describe('rows outside the listed expiries lead or close the grid', () => {
    it('accepts a leading outside row (the 7-day row before the front expiry)', () => {
      const d = changed((x) => {
        const f = x.frames[0]
        f.cell_flags[0] = f.cell_flags[0].map((v) => (v & ~2) | 4)
        reshare(f)
      })
      expect(parseSurfaceFrames(d).frames[0].cell_flags[0][0] & 4).toBe(4)
    })
    it('accepts closing outside rows (270 and 365 days past the back expiry)', () => {
      const d = changed((x) => {
        const f = x.frames[0]
        for (const i of [9, 10]) f.cell_flags[i] = f.cell_flags[i].map((v) => (v & ~2) | 4)
        reshare(f)
      })
      expect(parseSurfaceFrames(d).frames[0].cell_flags[10][0] & 4).toBe(4)
    })
  })

  describe('expiries_used covers the expiries the rows need', () => {
    // Frame 0: 3 rows on an expiry, the first inside row on one, the last (365 days) between two: 4 expiries at least.
    // Frame 1: 1 row on an expiry, and both the first (7 days) and the last inside row between two: 3 at least.
    it.each([
      [0, 4],
      [1, 3],
    ])('accepts frame %i with exactly the %i expiries its rows need', (frame, needed) => {
      expect(parseSurfaceFrames(changed((x) => (x.frames[frame].expiries_used = needed))).frames[frame].expiries_used).toBe(needed)
    })
    it('refuses frame 0 with 3: one fewer than its rows on an expiry and the one above its last row', () => {
      rejects(
        changed((x) => (x.frames[0].expiries_used = 3)),
        'surface_frames.frames[0].expiries_used: is 3 but the rows need at least 4 listed expiries: 3 row(s) on an expiry',
        '0 below the first inside row and 1 above the last',
      )
    })
    it('refuses frame 1 with 2: its rows need one on an expiry, one below its first row and one above its last', () => {
      rejects(
        changed((x) => (x.frames[1].expiries_used = 2)),
        'surface_frames.frames[1].expiries_used: is 2 but the rows need at least 3 listed expiries: 1 row(s) on an expiry',
        '1 below the first inside row and 1 above the last',
      )
    })
  })

  describe('strike extrapolation runs from the edges of a row', () => {
    it('refuses a strike bit at k = 0 between quoted cells', () => {
      const d = changed((x) => {
        const f = x.frames[0]
        f.cell_flags[3][15] |= 1
        reshare(f)
      })
      rejects(d, 'surface_frames.frames[0].cell_flags[3][15]: carries SURFACE_EXTRAP_STRIKE at k = 0 in the 30-day row')
    })
    it('accepts the left run grown by one cell', () => {
      const d = changed((x) => {
        const f = x.frames[0]
        f.cell_flags[3][10] |= 1
        reshare(f)
      })
      expect(parseSurfaceFrames(d).frames[0].cell_flags[3][10] & 1).toBe(1)
    })
  })

  describe('bit 8 where the adjustment cannot have moved a value', () => {
    /**
     * Frame 0 read off 1 expiry, the 7-day one: that row keeps its strike bits, every other row is past it and reads it
     * at x = k sqrt(7 / tau), nearer k = 0, here inside its strikes (a row past the back is beyond them only where the
     * rows before it are: checkStrikeFlagAlongTenor). No bit 8.
     */
    const oneExpiry = (change: (f: Frame) => void = () => {}): Doc =>
      changed((x) => {
        const f = x.frames[0]
        f.expiries_used = 1
        f.cell_flags = f.cell_flags.map((row, i) => row.map((v) => (i === 0 ? v & 1 : 4)))
        change(f)
        reshare(f)
      })
    it('accepts a frame of 1 expiry whose own row carries no bit 8', () => {
      expect(parseSurfaceFrames(oneExpiry()).frames[0].expiries_used).toBe(1)
    })
    it('accepts bit 8 on the rows past that 1 expiry: there the running maximum can raise a value', () => {
      expect(parseSurfaceFrames(oneExpiry((f) => (f.cell_flags[5][0] |= 8))).frames[0].cell_flags[5][0] & 8).toBe(8)
    })
    it('refuses bit 8 on the row of the only expiry', () => {
      rejects(
        oneExpiry((f) => (f.cell_flags[0][0] |= 8)),
        "surface_frames.frames[0].cell_flags[0][0]: carries SURFACE_CALENDAR_ADJUSTED on the 7-day row, which sits on the frame's only expiry",
      )
    })

    /** Frame 0 with its 7-day row before the front expiry: its cells keep their bits (bit 8 on the wings), plus bit 4. */
    const beforeFront = (change: (f: Frame) => void = () => {}): Doc =>
      changed((x) => {
        const f = x.frames[0]
        f.cell_flags[0] = f.cell_flags[0].map((v) => v | 4)
        change(f)
        reshare(f)
      })
    it('accepts bit 8 on the wings of a row before the front expiry: the running minimum can lower them', () => {
      const parsed = parseSurfaceFrames(beforeFront())
      expect([parsed.frames[0].cell_flags[0][0], parsed.frames[0].cell_flags[0][25]]).toEqual([13, 13])
    })
    it('refuses bit 8 at k = 0 of that row, inside the front strikes (K as the brief pictured it: every cell of a row before the front)', () => {
      rejects(
        beforeFront((f) => (f.cell_flags[0] = f.cell_flags[0].map((v) => v | 8))),
        'surface_frames.frames[0].cell_flags[0][15]: carries SURFACE_CALENDAR_ADJUSTED at k = 0 on the 7-day row, before the front expiry and inside its strikes',
      )
    })
  })
})

describe('the round-3 review cases (docs reviewer, claim 1) on the committed file', () => {
  it('T1: 9.99 at k = 0 on the 365-day row past the back, flagged 4 alone, is refused; flagged 12 it is accepted', () => {
    const t1 = (bit8: number): Doc =>
      changed((x) => {
        const f = x.frames[0]
        f.cell_flags[10] = f.cell_flags[10].map((v) => (v & ~2) | 4)
        f.cell_flags[10][15] |= bit8
        f.iv[10][15] = 9.99
        reshare(f)
      })
    expect(t1(0).frames[0].cell_flags[10][15]).toBe(4)
    rejects(t1(0), 'surface_frames.frames[0].iv[10][15]: implied vol 9.99 is outside (0, 5], the ceiling of a cell flagged 4 at k = 0 on the 365-day row')
    expect(parseSurfaceFrames(t1(8)).frames[0].iv[10][15]).toBe(9.99)
  })

  it('P1: the 7-day row before the front and bit 8 on the 14-day quoted k = 0 cell is accepted: with 36 expiries the 14-day row may sit on a later one', () => {
    // The exporter writes this shape (tests/test_export_surface.py p1_first_inside_row_on_a_later_expiry).
    const d = changed((x) => {
      const f = x.frames[2]
      f.cell_flags[0] = f.cell_flags[0].map((v) => (v & ~2) | 4)
      f.cell_flags[1][15] = (f.cell_flags[1][15] & ~1) | 8
      reshare(f)
    })
    expect([d.frames[2].expiries_used, d.frames[2].cell_flags[1][15]]).toEqual([36, 8])
    expect(parseSurfaceFrames(d).frames[2].cell_flags[1][15]).toBe(8)
  })

  it('P6: the 14-day row beyond its strikes at k = -0.3 where the 7-day row before the front is not is accepted, for the same reason', () => {
    // The exporter writes this shape too (p6_first_inside_row_on_a_later_expiry).
    const d = changed((x) => {
      const f = x.frames[2]
      f.cell_flags[0] = f.cell_flags[0].map((v) => (v & ~3) | 4)
      f.cell_flags[1][0] |= 1
      reshare(f)
    })
    expect([d.frames[2].cell_flags[0][0], d.frames[2].cell_flags[1][0]]).toEqual([4, 1])
    expect(parseSurfaceFrames(d).frames[2].cell_flags[1][0]).toBe(1)
  })
})
