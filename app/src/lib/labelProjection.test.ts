import { describe, expect, it } from 'vitest'
import { labelTransform, ndcToPixels } from './labelProjection'

// A 800 x 400 stage. NDC x = -1 / +1 are the left / right edges, NDC y = +1 / -1 the TOP / BOTTOM edges.
const stage = { width: 800, height: 400 }

describe('ndcToPixels', () => {
  it('puts NDC (0, 0), the middle of the view, on the middle of the stage', () => {
    expect(ndcToPixels({ x: 0, y: 0 }, stage)).toEqual({ x: 400, y: 200 })
  })

  it('puts the four corners of the view on the four corners of the stage (y flips: up is NDC +1, pixel 0)', () => {
    expect(ndcToPixels({ x: -1, y: 1 }, stage)).toEqual({ x: 0, y: 0 }) // top-left
    expect(ndcToPixels({ x: 1, y: 1 }, stage)).toEqual({ x: 800, y: 0 }) // top-right
    expect(ndcToPixels({ x: -1, y: -1 }, stage)).toEqual({ x: 0, y: 400 }) // bottom-left
    expect(ndcToPixels({ x: 1, y: -1 }, stage)).toEqual({ x: 800, y: 400 }) // bottom-right
  })

  it('scales a quarter-way point by the stage size: x = 0.5 -> 3/4 of the width, y = 0.5 -> 1/4 of the height', () => {
    // x: (0.5 * 0.5 + 0.5) * 800 = 600.  y: (-0.5 * 0.5 + 0.5) * 400 = 100 (above the middle, which is 200).
    expect(ndcToPixels({ x: 0.5, y: 0.5 }, stage)).toEqual({ x: 600, y: 100 })
    expect(ndcToPixels({ x: -0.5, y: -0.5 }, stage)).toEqual({ x: 200, y: 300 })
  })

  it('moves up the screen (smaller pixel y) as NDC y grows', () => {
    const lower = ndcToPixels({ x: 0, y: -0.2 }, stage)
    const higher = ndcToPixels({ x: 0, y: 0.2 }, stage)
    expect(higher.y).toBeLessThan(lower.y)
    expect(higher.x).toBe(lower.x)
  })
})

describe('labelTransform', () => {
  it('moves the element to the pixel, then back by half its own size so the pixel is its centre', () => {
    expect(labelTransform({ x: 600, y: 100 })).toBe('translate(600px, 100px) translate(-50%, -50%)')
  })
})
