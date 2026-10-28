/**
 * Turns the exported (moneyness x dte -> IV) grid into the flat typed arrays a WebGL mesh needs.
 * Kept free of three.js on purpose: it returns plain Float32Array / Uint32Array, so the whole
 * mapping is unit-testable without a GPU, and SurfaceHero just hands the arrays to three.
 *
 * Coordinates (a unit box, every axis scaled to [0, 1] by its own min and max):
 *   x = log-moneyness   (moneyness[j])
 *   y = implied vol     (iv[i][j])        <- "up", so min IV sits at y = 0 and max IV at y = 1
 *   z = days to expiry  (dte[i])
 *
 * Vertex numbering is row-major over the grid: vertex (i, j) has index i * nK + j, where i walks
 * the dte axis (rows) and j walks the moneyness axis (columns).
 *
 * Pure: no I/O, no DOM, no clock, no randomness.
 */
import { rampLinear } from './colorRamp'
import { fmt, pct } from './format'

export type Extent = [min: number, max: number]

export interface SurfaceGeometry {
  /** x, y, z per vertex, each in [0, 1]. Length 3 * nT * nK. */
  positions: Float32Array
  /** r, g, b per vertex in LINEAR light (what three.js expects for vertex colours). Length 3 * nT * nK. */
  colors: Float32Array
  /** Three vertex indices per triangle, two triangles per grid cell, counter-clockwise seen from +y. */
  indices: Uint32Array
  /** Two vertex indices per line segment: every edge of the grid (for the wireframe overlay). */
  lineIndices: Uint32Array
  /** The original (un-normalised) range of each axis, for axis labels. */
  extent: { moneyness: Extent; dte: Extent; iv: Extent }
}

function extentOf(values: Iterable<number>, what: string): Extent {
  let min = Infinity
  let max = -Infinity
  for (const v of values) {
    if (!Number.isFinite(v)) throw new RangeError(`${what} contains a non-finite value (${String(v)})`)
    if (v < min) min = v
    if (v > max) max = v
  }
  return [min, max]
}

/** Map v from [lo, hi] onto [0, 1]. A degenerate axis (hi === lo) maps to 0 instead of dividing by zero. */
function unit(v: number, [lo, hi]: Extent): number {
  return hi === lo ? 0 : (v - lo) / (hi - lo)
}

export function buildSurfaceGeometry(
  moneyness: readonly number[],
  dte: readonly number[],
  iv: readonly (readonly number[])[],
): SurfaceGeometry {
  const nK = moneyness.length
  const nT = dte.length
  if (nK < 2 || nT < 2) throw new RangeError(`need at least a 2 x 2 grid, got ${nT} x ${nK}`)
  if (iv.length !== nT) throw new RangeError(`iv has ${iv.length} rows but dte has ${nT} values`)
  iv.forEach((row, i) => {
    if (row.length !== nK) throw new RangeError(`iv[${i}] has ${row.length} values but moneyness has ${nK}`)
  })

  const kExt = extentOf(moneyness, 'moneyness')
  const tExt = extentOf(dte, 'dte')
  const vExt = extentOf(
    iv.flatMap((row) => row),
    'iv',
  )

  const nVert = nT * nK
  const positions = new Float32Array(3 * nVert)
  const colors = new Float32Array(3 * nVert)
  for (let i = 0; i < nT; i++) {
    for (let j = 0; j < nK; j++) {
      const v = i * nK + j
      const y = unit(iv[i][j], vExt)
      positions[3 * v] = unit(moneyness[j], kExt)
      positions[3 * v + 1] = y
      positions[3 * v + 2] = unit(dte[i], tExt)
      const [r, g, b] = rampLinear(y)
      colors[3 * v] = r
      colors[3 * v + 1] = g
      colors[3 * v + 2] = b
    }
  }

  // Each grid cell has corners a (i, j), b (i, j+1), c (i+1, j), d (i+1, j+1) and is split into the
  // triangles (a, c, b) and (b, c, d). Seen from above (+y) with x to the right and z toward the
  // viewer, both run counter-clockwise, so the top face of the surface is the front face.
  const indices = new Uint32Array(6 * (nT - 1) * (nK - 1))
  let t = 0
  for (let i = 0; i < nT - 1; i++) {
    for (let j = 0; j < nK - 1; j++) {
      const a = i * nK + j
      const b = a + 1
      const c = a + nK
      const d = c + 1
      indices.set([a, c, b, b, c, d], t)
      t += 6
    }
  }

  // Grid edges: from each vertex, one segment to its right neighbour and one to the neighbour below.
  const lineIndices = new Uint32Array(2 * (nT * (nK - 1) + nK * (nT - 1)))
  let s = 0
  for (let i = 0; i < nT; i++) {
    for (let j = 0; j < nK; j++) {
      const v = i * nK + j
      if (j < nK - 1) {
        lineIndices.set([v, v + 1], s)
        s += 2
      }
      if (i < nT - 1) {
        lineIndices.set([v, v + nK], s)
        s += 2
      }
    }
  }

  return { positions, colors, indices, lineIndices, extent: { moneyness: kExt, dte: tExt, iv: vExt } }
}

export type Vec3 = [number, number, number]

export interface AxisLabel {
  text: string
  /** Where the label is anchored, in the same unit-box coordinates as the surface positions. */
  at: Vec3
  /** Axis titles read stronger than tick values. */
  title: boolean
}

/**
 * Labels for the three axes, anchored just outside the unit box. The surface sits in [0,1]^3 with
 * its viewing corner at (x = 1, y = 0, z = 1); ticks hang off the three edges that meet there:
 *   x axis (log-moneyness) along the front edge:  x = 0 is the minimum, x = 1 the maximum
 *   z axis (days to expiry) along the right edge: z = 0 is the minimum, z = 1 the maximum
 *   y axis (implied vol) up the front-left edge:  y = 0 is the minimum, y = 1 the maximum
 */
export function axisLabels(extent: SurfaceGeometry['extent']): AxisLabel[] {
  const { moneyness: k, dte: t, iv: v } = extent
  return [
    { text: fmt(k[0], 2), at: [0, -0.06, 1.12], title: false },
    { text: fmt(k[1], 2), at: [1, -0.06, 1.12], title: false },
    { text: 'log-moneyness', at: [0.5, -0.12, 1.28], title: true },
    { text: `${t[0]}d`, at: [1.16, -0.06, 0], title: false },
    { text: `${t[1]}d`, at: [1.16, -0.06, 1], title: false },
    { text: 'days to expiry', at: [1.3, -0.12, 0.5], title: true },
    { text: pct(v[0], 1), at: [-0.14, 0, 1], title: false },
    { text: pct(v[1], 1), at: [-0.14, 1, 1], title: false },
    { text: 'implied vol', at: [-0.3, 0.5, 1], title: true },
  ]
}
