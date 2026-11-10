import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import App from './App'
import { resetMemoryFallback } from './lib/storage'
import { fakeFetch } from './test/fakeFetch'
import manifestFixture from './test/fixtures/manifest.json'
import surfaceFixture from './test/fixtures/illustrative_surface.json'
import dataQualityFixture from './test/fixtures/data_quality.json'
import surfaceFramesFixture from './test/fixtures/surface_frames.json'
import blotterFixture from './test/fixtures/blotter.json'
import positionsTimelineFixture from './test/fixtures/positions_timeline.json'
import signalsFixture from './test/fixtures/signals_timeline.json'
import strategiesFixture from './test/fixtures/strategy_positions.json'

vi.mock('@react-three/fiber', () => import('./test/mockFiber'))
vi.mock('@react-three/drei', () => ({ OrbitControls: () => null }))

const SIGNALS_ENTRY = { name: 'signals_timeline', path: 'signals_timeline.json', schema_version: '0.5.0', description: 'Test fixture' }
const STRATEGIES_ENTRY = { name: 'strategy_positions', path: 'strategy_positions.json', schema_version: '0.5.0', description: 'Test fixture' }
const manifestWith = (...entries: object[]): unknown => ({ ...manifestFixture, datasets: [...manifestFixture.datasets, ...entries] })

const BASE = {
  './data/illustrative_surface.json': surfaceFixture,
  './data/data_quality.json': dataQualityFixture,
  './data/surface_frames.json': surfaceFramesFixture,
  './data/blotter.json': blotterFixture,
  './data/positions_timeline.json': positionsTimelineFixture,
  './data/signals_timeline.json': signalsFixture,
  './data/strategy_positions.json': strategiesFixture,
}
const WITHOUT = { ...BASE, './data/manifest.json': manifestFixture }
const WITH_BOTH = { ...BASE, './data/manifest.json': manifestWith(SIGNALS_ENTRY, STRATEGIES_ENTRY) }

function serve(files: Record<string, unknown>) {
  const requested: string[] = []
  const f = fakeFetch(files, requested)
  vi.stubGlobal('fetch', (url: string) => f(url))
  return requested
}
const tabs = (): (string | null)[] => within(screen.getByRole('navigation', { name: 'Primary' })).getAllByRole('link').map((a) => a.textContent)

beforeEach(() => {
  resetMemoryFallback()
  window.location.hash = ''
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({} as never)
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('App: the Signal and Strategies tabs follow the manifest', () => {
  it('has no such tabs when the manifest lists neither dataset, even if the files are served', async () => {
    const requested = serve(WITHOUT)
    render(<App />)
    await screen.findByText('Illustrative SSVI surface — not market data')
    expect(tabs()).toEqual(['About', 'Surface', 'Blotter', 'Positions', 'Data quality', 'Architecture'])
    expect(requested).not.toContain('./data/signals_timeline.json')
    expect(requested).not.toContain('./data/strategy_positions.json')
  })
  it('has both tabs, after Positions, when the manifest lists both', async () => {
    serve(WITH_BOTH)
    render(<App />)
    await screen.findByText('Illustrative SSVI surface — not market data')
    expect(tabs()).toEqual(['About', 'Surface', 'Blotter', 'Positions', 'Signal', 'Strategies', 'Data quality', 'Architecture'])
  })
  it('has only the Signal tab when only signals_timeline is listed', async () => {
    serve({ ...WITH_BOTH, './data/manifest.json': manifestWith(SIGNALS_ENTRY) })
    render(<App />)
    await screen.findByText('Illustrative SSVI surface — not market data')
    expect(tabs()).toEqual(['About', 'Surface', 'Blotter', 'Positions', 'Signal', 'Data quality', 'Architecture'])
  })
  it('has only the Strategies tab when only strategy_positions is listed', async () => {
    serve({ ...WITH_BOTH, './data/manifest.json': manifestWith(STRATEGIES_ENTRY) })
    render(<App />)
    await screen.findByText('Illustrative SSVI surface — not market data')
    expect(tabs()).toEqual(['About', 'Surface', 'Blotter', 'Positions', 'Strategies', 'Data quality', 'Architecture'])
  })
  it('opens the Signal tab, which draws the charts without refetching', async () => {
    const requested = serve(WITH_BOTH)
    render(<App />)
    await screen.findByText('Illustrative SSVI surface — not market data')
    fireEvent.click(screen.getByRole('link', { name: 'Signal' }))
    expect(window.location.hash).toBe('#/signal')
    expect(screen.getByRole('heading', { level: 2, name: 'Signal' })).toBeInTheDocument()
    expect(screen.getByRole('figure', { name: 'Log variance ratio' })).toBeInTheDocument()
    expect(screen.getByText('Forecast test')).toBeInTheDocument()
    expect(requested).toHaveLength(8)
  })
  it('opens the Strategies tab, which shows the banner without refetching', async () => {
    const requested = serve(WITH_BOTH)
    render(<App />)
    await screen.findByText('Illustrative SSVI surface — not market data')
    fireEvent.click(screen.getByRole('link', { name: 'Strategies' }))
    expect(window.location.hash).toBe('#/strategies')
    expect(screen.getByRole('heading', { level: 2, name: 'Strategies' })).toBeInTheDocument()
    expect(screen.getByText('7 development trials (made up); no performance before M6')).toBeInTheDocument()
    expect(requested).toHaveLength(8)
  })
  it('opens straight on the Signal and Strategies tabs from their hashes, once the data has loaded', async () => {
    window.location.hash = '#/signal'
    serve(WITH_BOTH)
    const first = render(<App />)
    expect(await screen.findByRole('figure', { name: 'Log variance ratio' })).toBeInTheDocument()
    first.unmount()
    window.location.hash = '#/strategies'
    render(<App />)
    expect(await screen.findByText('7 development trials (made up); no performance before M6')).toBeInTheDocument()
  })
  it('falls back to About for the hash of a tab the manifest does not list', async () => {
    window.location.hash = '#/signal'
    serve(WITHOUT)
    render(<App />)
    expect(await screen.findByText('Illustrative SSVI surface — not market data')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { level: 2, name: 'Signal' })).not.toBeInTheDocument()
  })
})
