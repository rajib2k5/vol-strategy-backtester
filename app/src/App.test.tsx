import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import App from './App'
import { resetMemoryFallback, safeStorage } from './lib/storage'
import { fakeFetch } from './test/fakeFetch'
import manifestFixture from './test/fixtures/manifest.json'
import surfaceFixture from './test/fixtures/illustrative_surface.json'
import dataQualityFixture from './test/fixtures/data_quality.json'

vi.mock('@react-three/fiber', () => import('./test/mockFiber'))
vi.mock('@react-three/drei', () => ({ OrbitControls: () => null }))

const FILES = {
  './data/manifest.json': manifestFixture,
  './data/illustrative_surface.json': surfaceFixture,
  './data/data_quality.json': dataQualityFixture,
}
const STORE = safeStorage()

/** Route the global fetch to the fixtures and report what was requested. */
function serve(files: Record<string, unknown>) {
  const requested: string[] = []
  const f = fakeFetch(files, requested)
  vi.stubGlobal('fetch', (url: string) => f(url))
  return requested
}

beforeEach(() => {
  resetMemoryFallback()
  STORE.removeItem('vol-strategy-backtester:theme')
  window.location.hash = ''
  // Pretend WebGL exists, so SurfaceHero renders (the mocked) canvas rather than the fallback.
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({} as never)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

// Integration: shell + loader + contract parsers + About/Architecture views, end to end.
describe('App (integration)', () => {
  it('loads manifest.json and the surface from relative URLs and shows them on the About page', async () => {
    const requested = serve(FILES)
    render(<App />)
    expect(await screen.findByText('Illustrative SSVI surface — not market data')).toBeInTheDocument()
    expect(requested).toEqual(['./data/manifest.json', './data/illustrative_surface.json', './data/data_quality.json'])
    // contract metadata straight from the fixture manifest
    expect(screen.getByText('a1b2c3d4e5f6')).toBeInTheDocument()
    expect(screen.getByText('2026-10-27T23:30:00Z')).toBeInTheDocument()
    expect(screen.getByRole('note')).toHaveTextContent('Educational project — not financial advice.')
    expect(screen.getByRole('heading', { level: 1, name: 'Vol Strategy Backtester' })).toBeInTheDocument()
  })

  it('shows a friendly message naming the export command when the data files are missing', async () => {
    serve({})
    render(<App />)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('could not be loaded')
    expect(alert).toHaveTextContent('answered HTTP 404')
    expect(alert).toHaveTextContent('uv run python tools/export_app_data.py')
    // the rest of the page still renders
    expect(screen.getByRole('note')).toBeInTheDocument()
  })

  it('refuses data from an incompatible schema major and says so', async () => {
    serve({ ...FILES, './data/manifest.json': { ...manifestFixture, schema_version: '1.0.0' } })
    render(<App />)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('does not match what this app expects')
    expect(alert).toHaveTextContent('unsupported major version 1')
  })

  it('falls back to the heatmap when the browser has no WebGL', async () => {
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
    serve(FILES)
    render(<App />)
    expect(await screen.findByRole('img', { name: 'Heatmap' })).toBeInTheDocument()
    expect(screen.queryByTestId('r3f-canvas')).not.toBeInTheDocument()
  })

  it('navigates to the Architecture tab without refetching the data', async () => {
    const requested = serve(FILES)
    render(<App />)
    await screen.findByText('Illustrative SSVI surface — not market data')
    fireEvent.click(screen.getByRole('link', { name: 'Architecture' }))
    expect(screen.getByRole('img', { name: 'Architecture diagram' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Sequence diagram' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Activity diagram' })).toBeInTheDocument()
    expect(screen.queryByText('Illustrative SSVI surface — not market data')).not.toBeInTheDocument()
    expect(requested).toHaveLength(3)
    // and back again: the loaded data is still there
    fireEvent.click(screen.getByRole('link', { name: 'About' }))
    expect(screen.getByText('Illustrative SSVI surface — not market data')).toBeInTheDocument()
    expect(requested).toHaveLength(3)
  })

  it('navigates to the Data quality tab, which shows the exported aggregates without refetching', async () => {
    const requested = serve(FILES)
    render(<App />)
    await screen.findByText('Illustrative SSVI surface — not market data')
    fireEvent.click(screen.getByRole('link', { name: 'Data quality' }))
    expect(window.location.hash).toBe('#/data-quality')
    expect(screen.getByRole('heading', { level: 2, name: 'Data quality' })).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Quality-gate limits' })).toBeInTheDocument()
    expect(screen.getByText('Passed')).toBeInTheDocument()
    expect(screen.queryByText('Illustrative SSVI surface — not market data')).not.toBeInTheDocument()
    expect(requested).toHaveLength(3)
  })

  it('opens straight on the Data quality tab from its hash', async () => {
    window.location.hash = '#/data-quality'
    serve(FILES)
    render(<App />)
    expect(await screen.findByRole('table', { name: 'Quality-gate limits' })).toBeInTheDocument()
  })

  it('has exactly the About, Data quality and Architecture tabs, and a working theme toggle', async () => {
    serve(FILES)
    render(<App />)
    await screen.findByText('Illustrative SSVI surface — not market data')
    const nav = screen.getByRole('navigation', { name: 'Primary' })
    expect(within(nav).getAllByRole('link').map((a) => a.textContent)).toEqual(['About', 'Data quality', 'Architecture'])
    fireEvent.click(screen.getByRole('button', { name: 'Switch to light theme' }))
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    expect(STORE.getItem('vol-strategy-backtester:theme')).toBe('light')
  })
})
