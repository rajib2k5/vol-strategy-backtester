/**
 * Where an axis label goes on screen. SurfaceHero.tsx projects each label's 3D anchor with three.js
 * (Vector3.project gives normalised device coordinates); this file turns those into the pixel
 * position of the DOM element, so the two conventions that are easy to get backwards are pinned by
 * a test with hand-worked values:
 *
 *   - NDC x runs left to right, NDC y runs BOTTOM to TOP, both in [-1, 1].
 *   - Screen pixels start at the top-left corner and y runs TOP to BOTTOM.
 *
 * So y changes sign, and an anchor higher in the scene must get a SMALLER pixel y.
 *
 * Pure: no I/O, no DOM, no three.js import.
 */

/** Normalised device coordinates: what a camera projection returns for a point in view. */
export interface Ndc {
  x: number
  y: number
}

/** The stage the labels are laid over, in CSS pixels. */
export interface StageSize {
  width: number
  height: number
}

/** NDC -> pixels from the stage's top-left corner. (0, 0) is the middle of the stage. */
export function ndcToPixels(ndc: Ndc, size: StageSize): { x: number; y: number } {
  return {
    x: (ndc.x * 0.5 + 0.5) * size.width,
    y: (-ndc.y * 0.5 + 0.5) * size.height,
  }
}

/** CSS transform that puts the CENTRE of an element (positioned at the stage's top-left) on a pixel. */
export function labelTransform(pixel: { x: number; y: number }): string {
  return `translate(${pixel.x}px, ${pixel.y}px) translate(-50%, -50%)`
}
