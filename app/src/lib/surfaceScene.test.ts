import { describe, expect, it } from 'vitest'
import { AXIS_SEGMENTS, ORBIT_TARGET, meshAttributes } from './surfaceScene'
import { axisLabels, buildSurfaceGeometry } from './surfaceGeometry'

const close = (actual: ArrayLike<number>, expected: number[]) => {
  expect(actual.length).toBe(expected.length)
  expected.forEach((e, i) => expect(actual[i], `element ${i}`).toBeCloseTo(e, 6))
}

describe('meshAttributes: 2 x 2 grid (hand-worked, same grid as surfaceGeometry.test.ts)', () => {
  // moneyness [-0.2, 0.2], dte [10, 30], iv [[0.2, 0.3], [0.4, 0.6]]; vertex v = i * 2 + j.
  const geo = buildSurfaceGeometry([-0.2, 0.2], [10, 30], [[0.2, 0.3], [0.4, 0.6]])
  const attrs = meshAttributes(geo)

  it('position holds x, y, z per vertex (not the colours)', () => {
    close(attrs.position, [0, 0, 0, 1, 0.25, 0, 0, 0.5, 1, 1, 1, 1])
  })

  it('color holds linear-light r, g, b per vertex (not the positions)', () => {
    // v0 is the light end of the ramp (#86b6ef), v3 the dark end (#184f95), decoded to linear light.
    close(attrs.color.slice(0, 3), [0.238398, 0.467784, 0.863157])
    close(attrs.color.slice(9, 12), [0.009134, 0.078187, 0.300544])
    expect(attrs.color).toHaveLength(12)
  })

  it('index is the 2 triangles of the filled mesh, lineIndex the 4 edges of the wireframe', () => {
    expect(Array.from(attrs.index)).toEqual([0, 2, 1, 1, 2, 3])
    expect(Array.from(attrs.lineIndex)).toEqual([0, 1, 0, 2, 1, 3, 2, 3])
    // Different lengths (6 vs 8), so feeding one where the other belongs cannot go unnoticed.
    expect(attrs.index).toHaveLength(6)
    expect(attrs.lineIndex).toHaveLength(8)
  })

  it('keeps the typed-array kinds three.js needs: float positions and colours, unsigned-int indices', () => {
    expect(attrs.position).toBeInstanceOf(Float32Array)
    expect(attrs.color).toBeInstanceOf(Float32Array)
    expect(attrs.index).toBeInstanceOf(Uint32Array)
    expect(attrs.lineIndex).toBeInstanceOf(Uint32Array)
  })
})

describe('AXIS_SEGMENTS', () => {
  it('is three segments of two points: x along the front edge, z along the right edge, y up the front-left edge', () => {
    expect(Array.from(AXIS_SEGMENTS)).toEqual([
      0, 0, 1, 1, 0, 1, // x axis, log-moneyness: (0,0,1) to (1,0,1)
      1, 0, 1, 1, 0, 0, // z axis, days to expiry: (1,0,1) to (1,0,0)
      0, 0, 1, 0, 1, 1, // y axis, implied vol: (0,0,1) to (0,1,1)
    ])
    expect(AXIS_SEGMENTS).toBeInstanceOf(Float32Array)
  })

  it('has each axis end at the point its min and max tick labels sit beside', () => {
    // axisLabels() anchors the labels just outside the box next to each axis end. Compare the
    // coordinate ALONG the axis exactly, and the others within the label offset (at most 0.3).
    const labels = axisLabels({ moneyness: [-0.2, 0.2], dte: [10, 30], iv: [0.2, 0.6] })
    const point = (segment: number, end: number) => Array.from(AXIS_SEGMENTS.slice(6 * segment + 3 * end, 6 * segment + 3 * end + 3))
    const beside = (label: number, p: number[]) => {
      const at = labels[label].at
      at.forEach((c, axis) => expect(Math.abs(c - p[axis])).toBeLessThanOrEqual(0.3))
    }
    // x axis (segment 0): min tick = label 0 at x = 0, max tick = label 1 at x = 1.
    beside(0, point(0, 0)); beside(1, point(0, 1))
    // z axis (segment 1): min tick = label 3 (dte min, z = 0), max tick = label 4 (z = 1). The segment runs 1 -> 0.
    beside(3, point(1, 1)); beside(4, point(1, 0))
    // y axis (segment 2): min tick = label 6 (iv min, y = 0), max tick = label 7 (y = 1).
    beside(6, point(2, 0)); beside(7, point(2, 1))
  })
})

describe('ORBIT_TARGET', () => {
  it('is the middle of x and z and below the middle of y, inside the unit box', () => {
    expect(ORBIT_TARGET).toEqual([0.5, 0.35, 0.5])
    ORBIT_TARGET.forEach((c) => {
      expect(c).toBeGreaterThanOrEqual(0)
      expect(c).toBeLessThanOrEqual(1)
    })
  })
})
