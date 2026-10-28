import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { LineChart } from './LineChart'

// jsdom cannot measure text, so these tests work from the SVG attributes. Text is 10px
// monospace: a glyph is about 0.6em wide (6px) and a line occupies roughly y-10..y+2 of its
// baseline. Two labels overlap when their boxes intersect on both axes.
const FONT = 10
const GLYPH_W = 6

function texts(container: HTMLElement) {
  return [...container.querySelectorAll('text')].map((t) => ({
    text: t.textContent ?? '',
    x: Number(t.getAttribute('x')),
    y: Number(t.getAttribute('y')),
    anchor: t.getAttribute('text-anchor') ?? 'start',
  }))
}

function box(t: ReturnType<typeof texts>[number]) {
  const w = t.text.length * GLYPH_W
  const left = t.anchor === 'end' ? t.x - w : t.x
  return { left, right: left + w, top: t.y - FONT, bottom: t.y + 2 }
}

const overlaps = (a: ReturnType<typeof box>, b: ReturnType<typeof box>) =>
  Math.min(a.right, b.right) - Math.max(a.left, b.left) > 0 && Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 0

describe('LineChart layout', () => {
  it('keeps the y-axis label clear of the top tick value', () => {
    const { container } = render(<LineChart yLabel="$m outstanding per quarter" series={[{ name: 'a', values: [1, 5, 908.4] }]} />)
    const all = texts(container)
    const label = all.find((t) => t.text === '$m outstanding per quarter')!
    // tick values are end-anchored at the left axis; the top tick is the one nearest the top
    const top = all.filter((t) => t.anchor === 'end').sort((a, b) => a.y - b.y)[0]
    expect(label).toBeDefined()
    expect(top).toBeDefined()
    expect(overlaps(box(label), box(top))).toBe(false)
  })

  it('does not reserve label space when there is no label', () => {
    const { container } = render(<LineChart series={[{ name: 'a', values: [1, 2] }]} />)
    const top = texts(container).filter((t) => t.anchor === 'end').sort((a, b) => a.y - b.y)[0]
    // plot top stays at the original 12px padding: tick baseline = 12 + 4
    expect(top.y).toBe(16)
  })

  it('never overlaps legend entries, wrapping long names onto extra rows', () => {
    const names = ['European cumulative carry', 'American cumulative carry', 'American carry minus European', 'zero']
    const { container } = render(<LineChart series={names.map((name, i) => ({ name, values: [i, i + 1, i + 2] }))} />)
    const legend = texts(container).filter((t) => t.text.startsWith('──'))
    expect(legend).toHaveLength(names.length)
    for (let i = 0; i < legend.length; i++)
      for (let j = i + 1; j < legend.length; j++) expect(overlaps(box(legend[i]), box(legend[j]))).toBe(false)
    // every entry stays inside the 720-wide viewBox
    for (const t of legend) expect(box(t).right).toBeLessThanOrEqual(720)
  })
})
