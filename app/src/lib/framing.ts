/**
 * Camera framing for the 3D hero. A perspective camera's field of view is vertical, so a stage that
 * is narrower than the scene needs would crop it left and right. Below a reference aspect ratio we
 * widen the vertical field of view just enough to keep the horizontal extent the same.
 *
 * Pure: no I/O, no DOM.
 */

/** Vertical fov (degrees) used on stages at least REF_ASPECT wide. */
export const BASE_FOV = 38
/** Width / height the scene (including its labels) needs; narrower stages get a wider fov. */
export const REF_ASPECT = 1.5
/** Cap, so a very tall, thin stage does not turn into a fish-eye. */
export const MAX_FOV = 85

/**
 * Keeping the horizontal half-extent fixed means tan(fov / 2) * aspect stays constant, so below
 * REF_ASPECT:  tan(fov / 2) = tan(BASE_FOV / 2) * REF_ASPECT / aspect.
 */
export function fovForAspect(aspect: number): number {
  if (!(aspect > 0) || !Number.isFinite(aspect)) throw new RangeError(`aspect must be a positive finite number, got ${aspect}`)
  if (aspect >= REF_ASPECT) return BASE_FOV
  const half = Math.atan((Math.tan((BASE_FOV * Math.PI) / 360) * REF_ASPECT) / aspect)
  return Math.min(MAX_FOV, (2 * half * 180) / Math.PI)
}
