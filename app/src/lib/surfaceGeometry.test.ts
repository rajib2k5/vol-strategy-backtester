import { describe, expect, it } from 'vitest'
import { axisLabels, buildSurfaceGeometry } from './surfaceGeometry'

const close = (actual: ArrayLike<number>, expected: number[]) => {
  expect(actual.length).toBe(expected.length)
  expected.forEach((e, i) => expect(actual[i], `element ${i}`).toBeCloseTo(e, 6))
}

describe('buildSurfaceGeometry: 2 x 2 grid (hand-worked)', () => {
  // moneyness [-0.2, 0.2], dte [10, 30], iv = [[0.2, 0.3], [0.4, 0.6]].  Vertex v = i * 2 + j.
  // x = (k + 0.2) / 0.4 -> 0, 1.      z = (dte - 10) / 20 -> 0, 1.
  // y = (iv - 0.2) / 0.4 (min 0.2, max 0.6):  0.2 -> 0,  0.3 -> 0.25,  0.4 -> 0.5,  0.6 -> 1.
  const g = buildSurfaceGeometry([-0.2, 0.2], [10, 30], [[0.2, 0.3], [0.4, 0.6]])

  it('places the 4 vertices in the unit box: min IV at y = 0, max IV at y = 1', () => {
    expect(g.positions).toBeInstanceOf(Float32Array)
    close(g.positions, [
      0, 0, 0, // v0 = (i0, j0): iv 0.2 = the minimum
      1, 0.25, 0, // v1 = (i0, j1)
      0, 0.5, 1, // v2 = (i1, j0)
      1, 1, 1, // v3 = (i1, j1): iv 0.6 = the maximum
    ])
  })

  it('produces exactly 2 triangles with known indices', () => {
    // One cell: a = 0 (i0,j0), b = 1 (i0,j1), c = 2 (i1,j0), d = 3 (i1,j1) -> (a, c, b) and (b, c, d).
    expect(g.indices).toBeInstanceOf(Uint32Array)
    expect(Array.from(g.indices)).toEqual([0, 2, 1, 1, 2, 3])
  })

  it('produces the 4 grid edges as line segments', () => {
    // per vertex: right neighbour, then the neighbour below. v0: (0,1) (0,2); v1: (1,3); v2: (2,3).
    expect(Array.from(g.lineIndices)).toEqual([0, 1, 0, 2, 1, 3, 2, 3])
  })

  it('reports the original axis ranges for labels', () => {
    expect(g.extent).toEqual({ moneyness: [-0.2, 0.2], dte: [10, 30], iv: [0.2, 0.6] })
  })

  it('colours the minimum-IV vertex with the light end of the ramp and the maximum with the dark end (linear light)', () => {
    // Ramp ends decoded from #86b6ef and #184f95 with the sRGB formula (see colorRamp.test.ts).
    close(g.colors.slice(0, 3), [0.238398, 0.467784, 0.863157]) // v0, y = 0
    close(g.colors.slice(9, 12), [0.009134, 0.078187, 0.300544]) // v3, y = 1
    expect(g.colors).toBeInstanceOf(Float32Array)
    expect(g.colors).toHaveLength(12)
  })
})

describe('buildSurfaceGeometry: 3 x 3 grid with uneven spacing (hand-worked)', () => {
  // moneyness [-0.3, -0.1, 0.2]: range 0.5 -> x = 0, 0.2/0.5 = 0.4, 1.
  // dte [10, 20, 50]: range 40 -> z = 0, 10/40 = 0.25, 1.
  // iv rows (one per dte), min 0.20 at (i1, j2), max 0.30 at (i0, j0); y = (iv - 0.20) / 0.10:
  //   i0: 0.30 0.25 0.22 -> 1.0 0.5 0.2
  //   i1: 0.28 0.24 0.20 -> 0.8 0.4 0.0
  //   i2: 0.26 0.23 0.21 -> 0.6 0.3 0.1
  const g = buildSurfaceGeometry(
    [-0.3, -0.1, 0.2],
    [10, 20, 50],
    [
      [0.3, 0.25, 0.22],
      [0.28, 0.24, 0.2],
      [0.26, 0.23, 0.21],
    ],
  )

  it('maps uneven grids by value, not by index', () => {
    close(g.positions, [
      0, 1.0, 0, /* v0 */ 0.4, 0.5, 0, /* v1 */ 1, 0.2, 0, /* v2 */
      0, 0.8, 0.25, /* v3 */ 0.4, 0.4, 0.25, /* v4 */ 1, 0.0, 0.25, /* v5 */
      0, 0.6, 1, /* v6 */ 0.4, 0.3, 1, /* v7 */ 1, 0.1, 1, /* v8 */
    ])
  })

  it('has 2 * (3-1) * (3-1) = 8 triangles in the expected row-major cell order', () => {
    // cell (0,0): a0 b1 c3 d4 -> [0,3,1, 1,3,4]     cell (0,1): a1 b2 c4 d5 -> [1,4,2, 2,4,5]
    // cell (1,0): a3 b4 c6 d7 -> [3,6,4, 4,6,7]     cell (1,1): a4 b5 c7 d8 -> [4,7,5, 5,7,8]
    expect(Array.from(g.indices)).toEqual([0, 3, 1, 1, 3, 4, 1, 4, 2, 2, 4, 5, 3, 6, 4, 4, 6, 7, 4, 7, 5, 5, 7, 8])
  })

  it('has 3 * 2 + 3 * 2 = 12 grid-edge segments', () => {
    expect(Array.from(g.lineIndices)).toEqual([0, 1, 0, 3, 1, 2, 1, 4, 2, 5, 3, 4, 3, 6, 4, 5, 4, 7, 5, 8, 6, 7, 7, 8])
  })

  it('every triangle faces up (+y): the xz-plane cross product is positive', () => {
    // (u x v)_y = u_z * v_x - u_x * v_z with u = q - p, v = r - p. Computed from positions alone.
    const p = g.positions
    for (let t = 0; t < g.indices.length; t += 3) {
      const [i0, i1, i2] = [g.indices[t], g.indices[t + 1], g.indices[t + 2]]
      const u = [p[3 * i1] - p[3 * i0], p[3 * i1 + 2] - p[3 * i0 + 2]] // (dx, dz)
      const v = [p[3 * i2] - p[3 * i0], p[3 * i2 + 2] - p[3 * i0 + 2]]
      expect(u[1] * v[0] - u[0] * v[1], `triangle ${t / 3}`).toBeGreaterThan(0)
    }
  })

  it('stays inside the unit box and touches both ends of every axis', () => {
    for (let axis = 0; axis < 3; axis++) {
      const vals = Array.from({ length: 9 }, (_, v) => g.positions[3 * v + axis])
      expect(Math.min(...vals), `axis ${axis} min`).toBe(0)
      expect(Math.max(...vals), `axis ${axis} max`).toBe(1)
    }
  })

  it('colour follows IV: lowest-IV vertex is the ramp start, highest-IV the ramp end, none NaN', () => {
    close(g.colors.slice(3 * 5, 3 * 5 + 3), [0.238398, 0.467784, 0.863157]) // v5: iv 0.20 (min), y = 0
    close(g.colors.slice(0, 3), [0.009134, 0.078187, 0.300544]) // v0: iv 0.30 (max), y = 1
    expect(Array.from(g.colors).every(Number.isFinite)).toBe(true)
  })

  it('references only real vertices, and every vertex is used', () => {
    const used = new Set([...g.indices])
    expect([...used].sort((a, b) => a - b)).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8])
    expect(Array.from(g.lineIndices).every((i) => i >= 0 && i < 9)).toBe(true)
  })
})

describe('buildSurfaceGeometry: sizes scale with the grid', () => {
  it.each([
    [2, 2],
    [2, 7],
    [5, 3],
    [9, 11],
  ])('%d dte rows x %d moneyness columns', (nT, nK) => {
    const moneyness = Array.from({ length: nK }, (_, j) => -0.3 + j * 0.05)
    const dte = Array.from({ length: nT }, (_, i) => 7 + i * 30)
    const iv = dte.map((_, i) => moneyness.map((_, j) => 0.15 + 0.01 * i + 0.002 * j))
    const g = buildSurfaceGeometry(moneyness, dte, iv)
    expect(g.positions.length).toBe(3 * nT * nK)
    expect(g.colors.length).toBe(3 * nT * nK)
    expect(g.indices.length).toBe(3 * 2 * (nT - 1) * (nK - 1))
    expect(g.lineIndices.length).toBe(2 * (nT * (nK - 1) + nK * (nT - 1)))
  })
})

describe('buildSurfaceGeometry: degenerate and invalid input', () => {
  it('a perfectly flat surface maps to y = 0 everywhere, with no NaN', () => {
    const g = buildSurfaceGeometry([-0.1, 0.1], [7, 30], [[0.2, 0.2], [0.2, 0.2]])
    expect([g.positions[1], g.positions[4], g.positions[7], g.positions[10]]).toEqual([0, 0, 0, 0])
    expect(Array.from(g.positions).every(Number.isFinite)).toBe(true)
    expect(Array.from(g.colors).every(Number.isFinite)).toBe(true)
    expect(g.extent.iv).toEqual([0.2, 0.2])
  })

  it('rejects grids smaller than 2 x 2', () => {
    expect(() => buildSurfaceGeometry([0.1], [7, 30], [[0.2], [0.2]])).toThrow('at least a 2 x 2 grid, got 2 x 1')
    expect(() => buildSurfaceGeometry([-0.1, 0.1], [7], [[0.2, 0.2]])).toThrow('at least a 2 x 2 grid, got 1 x 2')
    expect(() => buildSurfaceGeometry([], [], [])).toThrow(RangeError)
  })

  it('rejects an iv grid whose shape does not match the axes', () => {
    expect(() => buildSurfaceGeometry([-0.1, 0.1], [7, 30], [[0.2, 0.2]])).toThrow('iv has 1 rows but dte has 2')
    expect(() => buildSurfaceGeometry([-0.1, 0.1], [7, 30], [[0.2, 0.2], [0.2]])).toThrow(
      'iv[1] has 1 values but moneyness has 2',
    )
  })

  it.each([
    ['moneyness', [NaN, 0.1], [7, 30], [[0.2, 0.2], [0.2, 0.2]]],
    ['dte', [-0.1, 0.1], [7, Infinity], [[0.2, 0.2], [0.2, 0.2]]],
    ['iv', [-0.1, 0.1], [7, 30], [[0.2, 0.2], [0.2, -Infinity]]],
  ])('rejects a non-finite %s value', (what, k, t, v) => {
    expect(() => buildSurfaceGeometry(k as number[], t as number[], v as number[][])).toThrow(
      `${what} contains a non-finite value`,
    )
  })
})

describe('axisLabels', () => {
  // Ranges: log-moneyness -0.30..0.20, dte 7..365, iv 0.116..0.563.
  // The minimum of each axis sits at coordinate 0 and the maximum at 1 (see buildSurfaceGeometry).
  const labels = axisLabels({ moneyness: [-0.3, 0.2], dte: [7, 365], iv: [0.116, 0.563] })
  const at = (text: string) => labels.find((l) => l.text === text)

  it('puts the minimum of each axis at coordinate 0 and the maximum at 1, along that axis', () => {
    expect(at('-0.30')?.at).toEqual([0, -0.06, 1.12]) // x = 0 -> min moneyness
    expect(at('0.20')?.at).toEqual([1, -0.06, 1.12]) // x = 1 -> max moneyness
    expect(at('7d')?.at).toEqual([1.16, -0.06, 0]) // z = 0 -> min dte
    expect(at('365d')?.at).toEqual([1.16, -0.06, 1]) // z = 1 -> max dte
    expect(at('11.6%')?.at).toEqual([-0.14, 0, 1]) // y = 0 -> min iv
    expect(at('56.3%')?.at).toEqual([-0.14, 1, 1]) // y = 1 -> max iv
  })

  it('has one title per axis, centred on that axis, and nothing else marked as a title', () => {
    expect(labels.filter((l) => l.title).map((l) => l.text)).toEqual(['log-moneyness', 'days to expiry', 'implied vol'])
    expect(at('log-moneyness')?.at[0]).toBe(0.5)
    expect(at('days to expiry')?.at[2]).toBe(0.5)
    expect(at('implied vol')?.at[1]).toBe(0.5)
    expect(labels).toHaveLength(9)
  })

  it('formats from the data ranges it is given', () => {
    const other = axisLabels({ moneyness: [-0.1, 0.1], dte: [30, 90], iv: [0.2, 0.3] })
    expect(other.map((l) => l.text)).toEqual(['-0.10', '0.10', 'log-moneyness', '30d', '90d', 'days to expiry', '20.0%', '30.0%', 'implied vol'])
  })
})
