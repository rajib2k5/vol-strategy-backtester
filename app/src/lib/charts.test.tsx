import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { binValues, normalizeMatrix, Histogram, Heatmap } from './charts'

describe('binValues (oracle-backed)', () => {
  it('bins a uniform 0..9 sequence into equal counts with the max in the last bin', () => {
    const { counts, min, max } = binValues([0, 1, 2, 3, 4, 5, 6, 7, 8, 9], 5)
    expect(counts).toEqual([2, 2, 2, 2, 2])
    expect(min).toBe(0)
    expect(max).toBe(9)
  })
  it('puts all constant values into the first bin and drops non-finite input', () => {
    expect(binValues([5, 5, 5, NaN, Infinity], 4).counts).toEqual([3, 0, 0, 0])
  })
  it('returns empty for no data or invalid bin count', () => {
    expect(binValues([], 10).counts).toEqual([])
    expect(binValues([1, 2], 0).counts).toEqual([])
  })
})

describe('normalizeMatrix (oracle-backed)', () => {
  it('scales to [0,1] with exact endpoints and passes NaN through as null', () => {
    expect(normalizeMatrix([[10, 20], [30, NaN]])).toEqual([
      [0, 0.5],
      [1, null],
    ])
  })
  it('handles an all-equal matrix without dividing by zero', () => {
    expect(normalizeMatrix([[7, 7]])).toEqual([[0, 0]])
  })
})

describe('components', () => {
  it('Histogram renders one bar per non-empty bin request and axis range labels', () => {
    const { container } = render(<Histogram values={[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]} bins={5} />)
    expect(container.querySelectorAll('[data-testid="vsb-hist-bar"]')).toHaveLength(5)
    expect(container.querySelectorAll('rect.vsb-bar-grow')).toHaveLength(5) // grow-in animation on every bar
    expect(screen.getByText('0.000')).toBeInTheDocument()
    expect(screen.getByText('9.000')).toBeInTheDocument()
  })
  it('Histogram shows an empty state for no data', () => {
    render(<Histogram values={[]} />)
    expect(screen.getByText('No data to bin.')).toBeInTheDocument()
  })
  it('Heatmap renders rows x cols cells plus provided labels', () => {
    const { container } = render(
      <Heatmap rows={[[1, 2, 3], [4, 5, 6]]} xLabels={['a', 'b', 'c']} yLabels={['r1', 'r2']} />,
    )
    expect(container.querySelectorAll('[data-testid="vsb-heat-cell"]')).toHaveLength(6)
    expect(container.querySelectorAll('rect.vsb-cell-in')).toHaveLength(6) // fade-in animation on every cell
    expect(screen.getByText('r2')).toBeInTheDocument()
    expect(screen.getByText('c')).toBeInTheDocument()
  })
})
