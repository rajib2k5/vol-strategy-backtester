import type { ReactElement } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { SceneContents, SurfaceHero } from './SurfaceHero'
import { parseIllustrativeSurface, type IllustrativeSurface } from '../lib/contract'
import { SURFACE_LABEL } from '../content/about'
import { canvasControl } from '../test/mockFiberControl'
import surfaceFixture from '../test/fixtures/illustrative_surface.json'

// jsdom has no WebGL: swap fiber's Canvas for a marker div, and drei for no-ops.
vi.mock('@react-three/fiber', () => import('../test/mockFiber'))
vi.mock('@react-three/drei', () => ({ OrbitControls: () => null }))

const surface = parseIllustrativeSurface(surfaceFixture)

afterEach(() => {
  canvasControl.shouldThrow = false
  canvasControl.lastProps = null
  vi.restoreAllMocks()
})

describe('SurfaceHero with WebGL', () => {
  it('shows the "not market data" label and mounts the 3D canvas', () => {
    render(<SurfaceHero surface={surface} webglAvailable={() => true} />)
    expect(screen.getByText('Illustrative SSVI surface — not market data')).toBeInTheDocument()
    expect(SURFACE_LABEL).toBe('Illustrative SSVI surface — not market data')
    expect(screen.getByTestId('r3f-canvas')).toHaveAccessibleName('Rotatable 3D implied volatility surface')
    expect(screen.queryByText(/3D view unavailable/)).not.toBeInTheDocument()
    expect(screen.queryByRole('img', { name: 'Heatmap' })).not.toBeInTheDocument()
  })

  it('turns tone mapping off with `flat`, so the colours on screen are the ramp the legend shows', () => {
    // react-three-fiber 9 applies ACES Filmic tone mapping to every material unless Canvas is `flat`.
    // That recolours the vertex colours (and the grey guide lines), so the surface would not match
    // the CSS legend drawn from the same ramp stops, nor the contrast figures documented in colorRamp.ts.
    render(<SurfaceHero surface={surface} webglAvailable={() => true} />)
    expect(canvasControl.lastProps).toMatchObject({ flat: true })
  })

  it('redraws on demand rather than continuously, at up to 2x pixel density', () => {
    render(<SurfaceHero surface={surface} webglAvailable={() => true} />)
    expect(canvasControl.lastProps).toMatchObject({ frameloop: 'demand', dpr: [1, 2] })
  })

  it('puts the surface scene inside the canvas, built from this dataset', () => {
    render(<SurfaceHero surface={surface} webglAvailable={() => true} />)
    const scene = canvasControl.lastProps?.children as ReactElement<{ geo: { extent: unknown } }>
    expect(scene.type).toBe(SceneContents)
    // fixture: moneyness -0.2..0.1, dte 7..90, iv 0.20..0.30
    expect(scene.props.geo.extent).toEqual({ moneyness: [-0.2, 0.1], dte: [7, 90], iv: [0.2, 0.3] })
  })

  it('shows the label from the component, not from the dataset, so a changed dataset label cannot hide it', () => {
    const relabelled: IllustrativeSurface = { ...surface, label: 'something else' }
    render(<SurfaceHero surface={relabelled} webglAvailable={() => true} />)
    expect(screen.getByText('Illustrative SSVI surface — not market data')).toBeInTheDocument()
    expect(screen.queryByText('something else')).not.toBeInTheDocument()
  })

  it("shows the caller's label when one is given (the Surface page's real surfaces)", () => {
    render(<SurfaceHero surface={surface} label="SPY implied-vol surface, 2020-03-16" webglAvailable={() => true} />)
    expect(screen.getByText('SPY implied-vol surface, 2020-03-16')).toBeInTheDocument()
    expect(screen.queryByText('Illustrative SSVI surface — not market data')).not.toBeInTheDocument()
  })

  it('describes the axes with the data ranges and shows a colour legend', () => {
    // fixture: moneyness -0.2..0.1, iv min 0.20 / max 0.30, dte 7..90
    const { container } = render(<SurfaceHero surface={surface} webglAvailable={() => true} />)
    const caption = container.querySelector('figcaption') as HTMLElement
    expect(caption.textContent).toContain('log-moneyness -0.20 to 0.10')
    expect(caption.textContent).toContain('implied vol 20.0% to 30.0%')
    expect(caption.textContent).toContain('days to expiry 7 to 90')
    expect(caption.textContent).toContain('Drag to rotate.')
    const bar = container.querySelector('.ramp-bar') as HTMLElement
    // the legend gradient runs from the low-IV anchor to the high-IV anchor of the ramp
    const style = bar.getAttribute('style') ?? ''
    expect(style).toContain('linear-gradient(to right, #86b6ef, #5598e7, #2a78d6, #184f95)')
    expect(within(caption).getAllByText('20.0%').length).toBeGreaterThan(0)
    expect(within(caption).getAllByText('30.0%').length).toBeGreaterThan(0)
  })

  it('overlays the axis labels as DOM text (hidden from screen readers, which get the caption instead)', () => {
    const { container } = render(<SurfaceHero surface={surface} webglAvailable={() => true} />)
    const overlay = container.querySelector('.hero-labels') as HTMLElement
    expect(overlay).toHaveAttribute('aria-hidden', 'true')
    // fixture ranges: moneyness -0.20..0.10, dte 7..90, iv 0.20..0.30
    const texts = Array.from(overlay.querySelectorAll('span')).map((e) => e.textContent)
    expect(texts).toEqual(['-0.20', '0.10', 'log-moneyness', '7d', '90d', 'days to expiry', '20.0%', '30.0%', 'implied vol'])
    // axis titles are styled apart from tick values
    expect(overlay.querySelectorAll('.hero-axis-title')).toHaveLength(3)
  })

  it('probes WebGL exactly once per mount, not on every re-render', () => {
    const probe = vi.fn(() => true)
    const { rerender } = render(<SurfaceHero surface={surface} webglAvailable={probe} />)
    rerender(<SurfaceHero surface={{ ...surface }} webglAvailable={probe} />)
    expect(probe).toHaveBeenCalledTimes(1)
  })

  it('falls back to the heatmap if the canvas throws after mounting (context lost)', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    canvasControl.shouldThrow = true
    render(<SurfaceHero surface={surface} webglAvailable={() => true} />)
    expect(screen.queryByTestId('r3f-canvas')).not.toBeInTheDocument()
    expect(screen.getByText(/3D view unavailable/)).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Heatmap' })).toBeInTheDocument()
    expect(screen.getByText('Illustrative SSVI surface — not market data')).toBeInTheDocument()
    expect(document.querySelector('.hero-labels')).toBeNull()
  })
})

describe('SurfaceHero without WebGL', () => {
  it('renders the label, an explanation and the grid as a heatmap instead of the canvas', () => {
    render(<SurfaceHero surface={surface} webglAvailable={() => false} />)
    expect(screen.getByText('Illustrative SSVI surface — not market data')).toBeInTheDocument()
    expect(screen.queryByTestId('r3f-canvas')).not.toBeInTheDocument()
    expect(screen.getByText(/could not start WebGL/)).toBeInTheDocument()
    const heat = screen.getByRole('img', { name: 'Heatmap' })
    // 3 dte rows x 4 moneyness columns
    expect(within(heat).getAllByTestId('vsb-heat-cell')).toHaveLength(12)
    // axis labels come straight from the data
    for (const t of ['7d', '30d', '90d', '-0.20', '-0.10', '0.00', '0.10']) {
      expect(within(heat).getByText(t)).toBeInTheDocument()
    }
  })
  it('draws no 3D axis labels', () => {
    const { container } = render(<SurfaceHero surface={surface} webglAvailable={() => false} />)
    expect(container.querySelector('.hero-labels')).toBeNull()
  })
  it('omits the drag hint, which only makes sense for the 3D view', () => {
    render(<SurfaceHero surface={surface} webglAvailable={() => false} />)
    expect(screen.queryByText(/Drag to rotate/)).not.toBeInTheDocument()
  })
})
