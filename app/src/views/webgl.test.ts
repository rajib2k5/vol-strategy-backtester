import { describe, expect, it } from 'vitest'
import { detectWebGL } from './webgl'

/** A fake document whose canvas answers getContext(kind) from a table; records which kinds were asked. */
function fakeDoc(contexts: Record<string, unknown>, asked: string[] = []): Pick<Document, 'createElement'> {
  return {
    createElement: () => ({ getContext: (kind: string) => (asked.push(kind), contexts[kind] ?? null) }),
  } as unknown as Pick<Document, 'createElement'>
}

describe('detectWebGL', () => {
  it('is true when webgl2 is available, without probing further', () => {
    const asked: string[] = []
    expect(detectWebGL(fakeDoc({ webgl2: {} }, asked))).toBe(true)
    expect(asked).toEqual(['webgl2'])
  })
  it('falls back to webgl1 when webgl2 is missing', () => {
    const asked: string[] = []
    expect(detectWebGL(fakeDoc({ webgl: {} }, asked))).toBe(true)
    expect(asked).toEqual(['webgl2', 'webgl'])
  })
  it('is false when neither context can be created', () => {
    expect(detectWebGL(fakeDoc({}))).toBe(false)
  })
  it('is false (does not throw) when the browser throws while probing', () => {
    const throwing = {
      createElement: () => {
        throw new Error('blocked')
      },
    } as unknown as Pick<Document, 'createElement'>
    expect(detectWebGL(throwing)).toBe(false)
  })
})
