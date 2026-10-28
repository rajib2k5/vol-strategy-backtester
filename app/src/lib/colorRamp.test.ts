import { describe, expect, it } from 'vitest'
import { RAMP_STOPS, hexToSrgb, rampLinear, rampSrgb, srgbToLinear } from './colorRamp'

// Hand-decoded anchors (hex pairs -> 0..255):
//   #86b6ef = (0x86, 0xb6, 0xef) = (134, 182, 239)
//   #5598e7 = (0x55, 0x98, 0xe7) = ( 85, 152, 231)
//   #2a78d6 = (0x2a, 0x78, 0xd6) = ( 42, 120, 214)
//   #184f95 = (0x18, 0x4f, 0x95) = ( 24,  79, 149)
const bytes = (r: number, g: number, b: number) => [r / 255, g / 255, b / 255]

describe('hexToSrgb', () => {
  it('decodes #rrggbb into 0..1 components (case-insensitive)', () => {
    expect(hexToSrgb('#86b6ef')).toEqual(bytes(134, 182, 239))
    expect(hexToSrgb('#86B6EF')).toEqual(bytes(134, 182, 239))
    expect(hexToSrgb('#000000')).toEqual([0, 0, 0])
    expect(hexToSrgb('#ffffff')).toEqual([1, 1, 1])
  })
  it.each(['red', '#fff', '86b6ef', '#86b6e', '#86b6eg', ''])('rejects %j', (bad) => {
    expect(() => hexToSrgb(bad)).toThrow(RangeError)
  })
})

describe('srgbToLinear', () => {
  // External reference: IEC 61966-2-1 sRGB decoding. 0.5 -> 0.214041 is the standard worked example;
  // 0.04045 is the knee where the linear segment (c / 12.92) meets the power segment.
  it('matches the standard transfer function at known points', () => {
    expect(srgbToLinear(0)).toBe(0)
    expect(srgbToLinear(1)).toBeCloseTo(1, 12)
    expect(srgbToLinear(0.5)).toBeCloseTo(0.214041, 6)
    expect(srgbToLinear(0.04045)).toBeCloseTo(0.04045 / 12.92, 12) // = 0.0031308
    expect(srgbToLinear(0.02)).toBeCloseTo(0.02 / 12.92, 12) // below the knee: linear segment
  })
})

describe('rampSrgb', () => {
  it('hits the first and last anchors exactly at t = 0 and t = 1', () => {
    expect(rampSrgb(0)).toEqual(bytes(134, 182, 239))
    expect(rampSrgb(1)).toEqual(bytes(24, 79, 149))
  })
  it('hits the inner anchors at t = 1/3 and 2/3', () => {
    // 3 segments, so t * 3 = 1 and 2 land exactly on anchors 1 and 2.
    expect(rampSrgb(1 / 3)).toEqual(bytes(85, 152, 231))
    expect(rampSrgb(2 / 3)).toEqual(bytes(42, 120, 214))
  })
  it('interpolates linearly inside a segment', () => {
    // t = 1/6 is halfway through segment 0: mean of (134,182,239) and (85,152,231) = (109.5, 167, 235).
    const mid0 = rampSrgb(1 / 6)
    expect(mid0[0]).toBeCloseTo(109.5 / 255, 12)
    expect(mid0[1]).toBeCloseTo(167 / 255, 12)
    expect(mid0[2]).toBeCloseTo(235 / 255, 12)
    // t = 5/6 is halfway through the last segment: mean of (42,120,214) and (24,79,149) = (33, 99.5, 181.5).
    const mid2 = rampSrgb(5 / 6)
    expect(mid2[0]).toBeCloseTo(33 / 255, 12)
    expect(mid2[1]).toBeCloseTo(99.5 / 255, 12)
    expect(mid2[2]).toBeCloseTo(181.5 / 255, 12)
  })
  it('clamps positions outside [0, 1] and rejects NaN', () => {
    expect(rampSrgb(-5)).toEqual(rampSrgb(0))
    expect(rampSrgb(7)).toEqual(rampSrgb(1))
    expect(rampSrgb(Infinity)).toEqual(rampSrgb(1))
    expect(() => rampSrgb(NaN)).toThrow(RangeError)
  })
  it('gets monotonically darker (relative luminance strictly falls) along the whole ramp', () => {
    const lum = ([r, g, b]: number[]) => 0.2126 * srgbToLinear(r) + 0.7152 * srgbToLinear(g) + 0.0722 * srgbToLinear(b)
    let prev = Infinity
    for (let k = 0; k <= 100; k++) {
      const y = lum(rampSrgb(k / 100))
      expect(y, `luminance at t=${k / 100}`).toBeLessThan(prev)
      prev = y
    }
  })
  it('uses the documented anchors', () => {
    expect(RAMP_STOPS).toEqual(['#86b6ef', '#5598e7', '#2a78d6', '#184f95'])
  })
})

describe('rampLinear', () => {
  // Independent reference values, decoded from the 8-bit anchors with the sRGB formula:
  //   (134,182,239) -> (0.238398, 0.467784, 0.863157)   (24,79,149) -> (0.009134, 0.078187, 0.300544)
  it('returns linear-light colours at the ends', () => {
    const lo = rampLinear(0)
    expect(lo[0]).toBeCloseTo(0.238398, 6)
    expect(lo[1]).toBeCloseTo(0.467784, 6)
    expect(lo[2]).toBeCloseTo(0.863157, 6)
    const hi = rampLinear(1)
    expect(hi[0]).toBeCloseTo(0.009134, 6)
    expect(hi[1]).toBeCloseTo(0.078187, 6)
    expect(hi[2]).toBeCloseTo(0.300544, 6)
  })
})
