import { describe, it, expect } from 'vitest'
import { fmt, pct, bps, compact } from './format'

describe('formatters', () => {
  it('fmt formats with thousands separators and fixed decimals', () => {
    expect(fmt(1234.5678)).toBe('1,234.57')
    expect(fmt(1, 4)).toBe('1.0000')
  })
  it('pct converts a fraction to a percentage string', () => {
    expect(pct(0.1234)).toBe('12.34%')
    expect(pct(-0.5, 1)).toBe('-50.0%')
  })
  it('bps converts a fraction to basis points', () => {
    expect(bps(0.0012)).toBe('12.0 bps')
  })
  it('compact shortens a large count to thousands or millions with one decimal at most', () => {
    expect(compact(1_088_170)).toBe('1.1M')
    expect(compact(525_956)).toBe('526K')
    expect(compact(18_857_058)).toBe('18.9M')
    expect(compact(66)).toBe('66')
    expect(compact(0)).toBe('0')
  })
  it('all return an em dash for non-finite input', () => {
    expect(fmt(NaN)).toBe('—')
    expect(pct(Infinity)).toBe('—')
    expect(bps(NaN)).toBe('—')
    expect(compact(NaN)).toBe('—')
  })
})
