import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DatedLineChart } from './DatedLineChart'

// 0, 1, 11, 30 and 40 days after the first: unequal gaps, so a chart that spaced points by index would be caught
const DATES = ['2019-01-01', '2019-01-02', '2019-01-12', '2019-01-31', '2019-02-10']
const chart = (): HTMLElement => screen.getByRole('img')
const lines = (name: string): Element[] => [...chart().querySelectorAll(`[data-series="${name}"]`)]
const num = (el: Element, attr: string): number => Number(el.getAttribute(attr))

describe('DatedLineChart', () => {
  it('breaks a line at a null instead of joining across it, and draws a lone point as a dot', () => {
    render(<DatedLineChart dates={DATES} series={[{ name: 'a', values: [0.1, 0.2, null, 0.3, null], color: 'red' }]} />)
    const parts = lines('a')
    expect(parts.map((p) => p.tagName)).toEqual(['polyline', 'circle'])
    expect(parts[0].getAttribute('points')?.split(' ')).toHaveLength(2)
  })
  it('places each point at its date, in proportion to the days between them', () => {
    render(<DatedLineChart dates={DATES} series={[{ name: 'a', values: [1, 2, 3, 4, 5], color: 'red' }]} />)
    const xs = (lines('a')[0].getAttribute('points') as string).split(' ').map((pt) => Number(pt.split(',')[0]))
    const width = xs[4] - xs[0]
    ;[1, 11, 30, 40].forEach((days, i) => expect((xs[i + 1] - xs[0]) / width).toBeCloseTo(days / 40, 6))
  })
  it('draws a level line at its value and widens the axis to include it', () => {
    render(
      <DatedLineChart
        dates={DATES}
        series={[{ name: 'a', values: [0.01, 0.02, 0.03, 0.02, 0.01], color: 'red' }]}
        levels={[
          { y: 0.4, label: '0.4: short entry' },
          { y: -0.4, label: '-0.4: short exit' },
        ]}
      />,
    )
    const top = chart().querySelector('[data-level="0.4"]') as Element
    const bottom = chart().querySelector('[data-level="-0.4"]') as Element
    expect(num(top, 'y1')).toBeLessThan(num(bottom, 'y1'))
    expect(top.textContent).toBe('0.4: short entry')
    expect(chart().textContent).toContain('0.4000')
    expect(chart().textContent).toContain('-0.4000')
  })
  it('draws a date marker inside the range and leaves out one outside it', () => {
    render(
      <DatedLineChart
        dates={DATES}
        series={[{ name: 'a', values: [1, 2, 3, 4, 5], color: 'red' }]}
        marks={[
          { date: '2019-01-12', label: 'refit in' },
          { date: '2018-12-31', label: 'refit before' },
          { date: '2019-02-11', label: 'refit after' },
        ]}
      />,
    )
    const marks = [...chart().querySelectorAll('[data-mark]')]
    expect(marks.map((m) => m.getAttribute('data-mark'))).toEqual(['2019-01-12'])
    const points = (lines('a')[0].getAttribute('points') as string).split(' ').map((pt) => Number(pt.split(',')[0]))
    expect(num(marks[0], 'x1')).toBeCloseTo(points[2], 6)
  })
  it('shows "No data" when every value is null', () => {
    render(<DatedLineChart dates={DATES} series={[{ name: 'a', values: [null, null, null, null, null], color: 'red' }]} />)
    expect(screen.getByText('No data')).toBeInTheDocument()
  })
  it('labels the dates at both ends, the axis, and names several series in a legend', () => {
    render(
      <DatedLineChart
        dates={DATES}
        series={[
          { name: 'IV30', values: [1, 2, 3, 4, 5], color: 'red' },
          { name: 'RV', values: [2, 3, 4, 5, 6], color: 'blue' },
        ]}
        yLabel="decimal"
      />,
    )
    const text = chart().textContent ?? ''
    expect(text).toContain('2019-01-01')
    expect(text).toContain('2019-02-10')
    expect(text).toContain('decimal')
    expect(text).toContain('── IV30')
    expect(text).toContain('── RV')
  })
  it('draws no legend for one series, and does not fail on a single date', () => {
    render(<DatedLineChart dates={['2019-01-01']} series={[{ name: 'only', values: [3], color: 'red' }]} />)
    expect(chart().textContent).not.toContain('── only')
    expect(lines('only')[0].tagName).toBe('circle')
    expect(Number.isFinite(num(lines('only')[0], 'cx'))).toBe(true)
  })
})
