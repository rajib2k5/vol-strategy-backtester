import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { ArchDiagram, SequenceDiagram, ActivityDiagram } from './diagrams'

afterEach(() => {
  vi.useRealTimers()
})

describe('ArchDiagram', () => {
  it('renders every layer label and box, with flowing connector arrows between layers', () => {
    const { container } = render(
      <ArchDiagram
        layers={[
          { label: 'Data', boxes: ['synthetic.json', 'env key'] },
          { label: 'Core', boxes: ['engine'] },
          { label: 'UI', boxes: ['Dashboard', 'Reports', 'Metrics'] },
        ]}
      />,
    )
    for (const t of ['DATA', 'CORE', 'UI', 'synthetic.json', 'engine', 'Metrics']) expect(screen.getByText(t)).toBeInTheDocument()
    expect(container.querySelectorAll('rect')).toHaveLength(6)
    // continuous dashed-flow animation class on both inter-layer connectors
    expect(container.querySelectorAll('line.vsb-arch-flow')).toHaveLength(2)
  })
})

describe('SequenceDiagram (looping stepper)', () => {
  const actors = ['User', 'Engine', 'Store']
  const steps = [
    { from: 0, to: 1, label: 'run()' },
    { from: 1, to: 1, label: 'validate params' },
    { from: 1, to: 2, label: 'read as-of' },
    { from: 2, to: 1, label: 'rows' },
  ]
  it('starts with step 0 running, others pending, and a traveling dot on the active arrow', () => {
    vi.useFakeTimers()
    const { container } = render(<SequenceDiagram actors={actors} steps={steps} />)
    expect(container.querySelectorAll('.vsb-seq-line.run')).toHaveLength(1)
    expect(container.querySelectorAll('.vsb-seq-line.pending')).toHaveLength(2) // self-step is a note
    expect(screen.getByTestId('vsb-seq-dot')).toBeInTheDocument()
    expect(screen.getByText('↺ validate params')).toBeInTheDocument()
  })
  it('advances on the timer, completes all arrows, then loops back to the start', () => {
    vi.useFakeTimers()
    const { container } = render(<SequenceDiagram actors={actors} steps={steps} />)
    act(() => {
      vi.advanceTimersByTime(850 * 3) // phases 1,2,3 -> last arrow running
    })
    expect(container.querySelectorAll('.vsb-seq-line.done')).toHaveLength(2)
    expect(container.querySelectorAll('.vsb-seq-line.run')).toHaveLength(1)
    act(() => {
      vi.advanceTimersByTime(850) // phase 4: hold — everything drawn
    })
    expect(container.querySelectorAll('.vsb-seq-line.done')).toHaveLength(3)
    expect(container.querySelector('.vsb-seq-line.run')).toBeNull()
    act(() => {
      vi.advanceTimersByTime(850 * 3) // remaining holds -> wraps to phase 0
    })
    expect(container.querySelectorAll('.vsb-seq-line.pending')).toHaveLength(2)
    expect(container.querySelectorAll('.vsb-seq-line.run')).toHaveLength(1)
  })
  it('replay resets to the first step and fires the callback', () => {
    vi.useFakeTimers()
    const onReplay = vi.fn()
    const { container } = render(<SequenceDiagram actors={actors} steps={steps} onReplay={onReplay} />)
    act(() => {
      vi.advanceTimersByTime(850 * 4)
    })
    expect(container.querySelector('.vsb-seq-line.run')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Replay sequence' }))
    expect(onReplay).toHaveBeenCalledTimes(1)
    expect(container.querySelectorAll('.vsb-seq-line.run')).toHaveLength(1)
    expect(container.querySelectorAll('.vsb-seq-line.done')).toHaveLength(0)
  })
})

describe('SequenceDiagram actor headers', () => {
  // Header boxes sit at x = 80 + i * pitch with pitch = (720 - 160) / (n - 1). Worked values:
  //   n = 3 -> pitch 280 -> width 104 (the cap);   n = 8 -> pitch 80 -> width 74 (= pitch - 6).
  const headers = (n: number) => {
    const actors = Array.from({ length: n }, (_, i) => `A${i}`)
    const { container } = render(<SequenceDiagram actors={actors} steps={[]} />)
    return Array.from(container.querySelectorAll('svg > g > rect')).map((r) => ({
      x: Number(r.getAttribute('x')),
      w: Number(r.getAttribute('width')),
    }))
  }
  it('keeps the full 104 width when there is room', () => {
    expect(headers(3).map((h) => h.w)).toEqual([104, 104, 104])
  })
  it('shrinks the boxes with 8 actors so neighbours never overlap and each stays centred on its lifeline', () => {
    const h = headers(8)
    expect(h).toHaveLength(8)
    expect(h.every((b) => b.w === 74)).toBe(true)
    for (let i = 0; i < 8; i++) expect(h[i].x + h[i].w / 2).toBeCloseTo(80 + i * 80, 9)
    for (let i = 0; i < 7; i++) expect(h[i].x + h[i].w).toBeLessThan(h[i + 1].x)
  })
})

describe('ActivityDiagram (walking token)', () => {
  const nodes = [
    { id: 's', label: 'load', type: 'start' as const },
    { id: 'k', label: 'API key?', type: 'decision' as const },
    { id: 'live', label: 'fetch live' },
    { id: 'syn', label: 'read synthetic' },
    { id: 'e', label: 'render', type: 'end' as const },
  ]
  const edges = [
    { from: 's', to: 'k' },
    { from: 'k', to: 'live', label: 'yes' },
    { from: 'k', to: 'syn', label: 'no' },
    { from: 'live', to: 'syn' },
    { from: 'syn', to: 'e' },
  ]
  it('renders shapes, decision diamond, side-routed edges, and ignores unknown edge ids', () => {
    vi.useFakeTimers()
    const { container } = render(<ActivityDiagram nodes={nodes} edges={[...edges, { from: 'ghost', to: 'e' }]} />)
    expect(screen.getByText('API key?')).toBeInTheDocument()
    expect(container.querySelectorAll('[data-testid="vsb-act-decision"]')).toHaveLength(1)
    expect(container.querySelectorAll('[data-testid="vsb-act-side"]').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('yes')).toBeInTheDocument()
  })
  it('walks the token down the flow and loops', () => {
    vi.useFakeTimers()
    render(<ActivityDiagram nodes={nodes} edges={edges} />)
    const at = () => screen.getByTestId('vsb-act-token').style.transform
    expect(at()).toBe('translateY(0px)')
    act(() => {
      vi.advanceTimersByTime(800)
    })
    expect(at()).toBe('translateY(74px)')
    act(() => {
      vi.advanceTimersByTime(800 * 3) // reach last node
    })
    expect(at()).toBe(`translateY(${74 * 4}px)`)
    act(() => {
      vi.advanceTimersByTime(800) // hold phase: token hidden
    })
    expect(screen.queryByTestId('vsb-act-token')).toBeNull()
    act(() => {
      vi.advanceTimersByTime(800) // loops back to node 0
    })
    expect(at()).toBe('translateY(0px)')
  })
})
