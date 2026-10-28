/**
 * Sequential colour ramp for the volatility surface: low IV = light blue, high IV = deep blue.
 *
 * Why this ramp (see the dataviz skill's sequential rules): magnitude is encoded by ONE hue
 * running light to dark, never a rainbow. The four anchors are steps 250, 350, 450 and 600 of
 * the blue ramp, chosen so the surface reads on both app themes:
 *   - the light end (#86b6ef) keeps 2.11:1 contrast on the light card (#ffffff);
 *   - the dark end (#184f95) keeps 2.04:1 contrast on the dark card (#1a1f29);
 *   - lightness falls monotonically with steps >= 0.06 OKLCH L between anchors, hue spread 3 deg
 *     (checked with the skill's validate_palette.js --ordinal in both modes).
 * Height already encodes IV too, so colour is a second, redundant cue, which is what lets a
 * mid-range ramp (rather than a full-range one that would vanish on one theme) do the job.
 *
 * These figures describe the ramp as drawn on screen only because SurfaceHero's <Canvas> is
 * `flat` (no tone mapping). react-three-fiber 9 otherwise applies ACES Filmic to every material,
 * which would shift every colour above and make the CSS legend (built from RAMP_STOPS) disagree
 * with the 3D surface.
 *
 * Pure: no I/O, no DOM.
 */

export const RAMP_STOPS = ['#86b6ef', '#5598e7', '#2a78d6', '#184f95'] as const

export type Rgb = [number, number, number]

/** '#rrggbb' -> sRGB components in 0..1. */
export function hexToSrgb(hex: string): Rgb {
  const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex)
  if (!m) throw new RangeError(`not a #rrggbb colour: ${hex}`)
  return [parseInt(m[1], 16) / 255, parseInt(m[2], 16) / 255, parseInt(m[3], 16) / 255]
}

/** sRGB transfer function, decoded: one 0..1 sRGB component -> linear light (IEC 61966-2-1). */
export function srgbToLinear(c: number): number {
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
}

/**
 * Colour at position t in [0, 1] along the ramp, as sRGB components in 0..1.
 * Piecewise-linear between adjacent anchors; t outside [0, 1] clamps to the ends.
 */
export function rampSrgb(t: number): Rgb {
  if (Number.isNaN(t)) throw new RangeError('ramp position must be a number')
  const clamped = Math.min(1, Math.max(0, t))
  const segments = RAMP_STOPS.length - 1
  const pos = clamped * segments
  const i = Math.min(Math.floor(pos), segments - 1)
  const f = pos - i
  const a = hexToSrgb(RAMP_STOPS[i])
  const b = hexToSrgb(RAMP_STOPS[i + 1])
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f]
}

/**
 * Same colour in linear light. three.js treats vertex-colour attributes as linear and applies the
 * sRGB encoding itself on output, so the vertex buffer must hold these values, not rampSrgb's.
 */
export function rampLinear(t: number): Rgb {
  const [r, g, b] = rampSrgb(t)
  return [srgbToLinear(r), srgbToLinear(g), srgbToLinear(b)]
}
