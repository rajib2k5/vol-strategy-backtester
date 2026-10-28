import { describe, it, expect } from 'vitest'
import { getStoredTheme, setStoredTheme, applyTheme } from './theme'
import type { StorageLike } from './storage'

function memStorage(): StorageLike {
  const map = new Map<string, string>()
  return {
    getItem: (k) => (map.has(k) ? (map.get(k) as string) : null),
    setItem: (k, v) => void map.set(k, v),
    removeItem: (k) => void map.delete(k),
  }
}

function throwingStorage(): StorageLike {
  const boom = () => {
    throw new Error('blocked')
  }
  return { getItem: boom, setItem: boom, removeItem: boom }
}

describe('theme storage', () => {
  it('round-trips and namespaces by slug', () => {
    const st = memStorage()
    expect(getStoredTheme('a', st)).toBeNull()
    setStoredTheme('a', 'light', st)
    expect(getStoredTheme('a', st)).toBe('light')
    expect(getStoredTheme('b', st)).toBeNull()
  })
  it('rejects corrupt values (including the retired "corporate" name) and survives unavailable storage', () => {
    const st = memStorage()
    st.setItem('a:theme', 'neon')
    expect(getStoredTheme('a', st)).toBeNull()
    st.setItem('a:theme', 'corporate')
    expect(getStoredTheme('a', st)).toBeNull()
    expect(getStoredTheme('a', null)).toBeNull()
    expect(() => setStoredTheme('a', 'dark', null)).not.toThrow()
  })
  it('swallows storage exceptions on read and write', () => {
    expect(getStoredTheme('a', throwingStorage())).toBeNull()
    expect(() => setStoredTheme('a', 'dark', throwingStorage())).not.toThrow()
  })
  it('applyTheme stamps the document element', () => {
    applyTheme('light')
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    applyTheme('dark')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })
})
