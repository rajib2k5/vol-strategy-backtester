import { describe, expect, it } from 'vitest'
import { BASE_FOV, MAX_FOV, REF_ASPECT, fovForAspect } from './framing'

describe('fovForAspect', () => {
  it('keeps the base field of view on stages at least as wide as the reference aspect', () => {
    expect(BASE_FOV).toBe(38)
    expect(REF_ASPECT).toBe(1.5)
    expect(fovForAspect(1.5)).toBe(38) // exactly at the reference
    expect(fovForAspect(2.3)).toBe(38) // wide desktop stage
  })

  it('widens the field of view on narrower stages, holding tan(fov / 2) * aspect constant', () => {
    // aspect 0.75 is half the reference, so tan(fov/2) doubles: 2 * tan(19 deg) = 0.688655,
    // atan = 34.5534 deg, fov = 69.1069 deg.
    expect(fovForAspect(0.75)).toBeCloseTo(69.1069, 3)
    // aspect 1.0: tan(fov/2) = 1.5 * tan(19 deg) = 0.516491, atan = 27.316 deg, fov = 54.632 deg.
    expect(fovForAspect(1.0)).toBeCloseTo(54.632, 3)
  })

  it('never narrows the view as the stage gets thinner', () => {
    let prev = 0
    for (const aspect of [3, 2, 1.5, 1.2, 1, 0.8, 0.6, 0.4]) {
      const fov = fovForAspect(aspect)
      expect(fov, `aspect ${aspect}`).toBeGreaterThanOrEqual(prev)
      prev = fov
    }
  })

  it('caps the field of view for very thin stages', () => {
    expect(MAX_FOV).toBe(85)
    expect(fovForAspect(0.1)).toBe(85)
  })

  it.each([0, -1, NaN, Infinity])('rejects aspect %s', (bad) => {
    expect(() => fovForAspect(bad)).toThrow(RangeError)
  })
})
