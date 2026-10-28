import { afterEach, describe, expect, it, vi } from 'vitest'
import { memoryFallback, resetMemoryFallback, safeStorage } from './storage'

afterEach(() => {
  vi.restoreAllMocks()
  resetMemoryFallback()
})

describe('memoryFallback', () => {
  it('stores, reads, removes and resets values', () => {
    expect(memoryFallback.getItem('k')).toBeNull()
    memoryFallback.setItem('k', 'v')
    expect(memoryFallback.getItem('k')).toBe('v')
    memoryFallback.removeItem('k')
    expect(memoryFallback.getItem('k')).toBeNull()
    memoryFallback.setItem('a', '1')
    resetMemoryFallback()
    expect(memoryFallback.getItem('a')).toBeNull()
  })
})

describe('safeStorage', () => {
  it('returns window.localStorage when it works, leaving no probe key behind', () => {
    const s = safeStorage()
    expect(s).toBe(window.localStorage)
    expect(s.getItem('vsb-storage-probe')).toBeNull()
  })
  it('falls back to the in-memory store when localStorage throws (private window / blocked site data)', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError')
    })
    expect(safeStorage()).toBe(memoryFallback)
  })
})
