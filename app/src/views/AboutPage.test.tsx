import { describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { AboutPage } from './AboutPage'
import { DataLoadError } from '../data/loadAppData'
import { parseIllustrativeSurface, parseManifest } from '../lib/contract'
import { DATA_SOURCES } from '../content/about'
import manifestFixture from '../test/fixtures/manifest.json'
import surfaceFixture from '../test/fixtures/illustrative_surface.json'

vi.mock('@react-three/fiber', () => import('../test/mockFiber'))
vi.mock('@react-three/drei', () => ({ OrbitControls: () => null }))

const manifest = parseManifest(manifestFixture)
const surface = parseIllustrativeSurface(surfaceFixture)
const ready = (m = manifest) => ({ status: 'ready' as const, data: { manifest: m, surface } })

describe('AboutPage: static content (independent of the data)', () => {
  it.each([
    ['loading', { status: 'loading' as const }],
    ['error', { status: 'error' as const, error: new Error('x') }],
    ['ready', ready()],
  ])('always shows the not-financial-advice notice and the pitch while %s', (_name, state) => {
    render(<AboutPage state={state} />)
    const note = screen.getByRole('note')
    expect(note).toHaveTextContent('Educational project — not financial advice.')
    expect(screen.getByText(/volatility-mispricing option strategies on SPY/)).toBeInTheDocument()
  })

  it('lists what it does and does not do', () => {
    render(<AboutPage state={{ status: 'loading' }} />)
    const does = screen.getByRole('heading', { name: 'What it does' }).closest('.card') as HTMLElement
    const doesNot = screen.getByRole('heading', { name: 'What it does not do' }).closest('.card') as HTMLElement
    expect(within(does).getAllByRole('listitem').length).toBeGreaterThanOrEqual(4)
    expect(doesNot).toHaveTextContent('Compute anything in the browser')
    expect(doesNot).toHaveTextContent('Ship market data')
  })

  it('names the pricing model ADR-0008 chose: Black-76 on a put-call-parity forward, not Black-Scholes-Merton', () => {
    render(<AboutPage state={{ status: 'loading' }} />)
    const does = screen.getByRole('heading', { name: 'What it does' }).closest('.card') as HTMLElement
    expect(does).toHaveTextContent('Black-76 on a forward implied from put-call parity')
    expect(does).not.toHaveTextContent('Black-Scholes-Merton')
  })

  it('names every data source and says raw vendor data is never committed', () => {
    render(<AboutPage state={{ status: 'loading' }} />)
    const card = screen.getByRole('heading', { name: 'Data sources' }).nextElementSibling as HTMLElement
    expect(within(card).getAllByRole('listitem')).toHaveLength(DATA_SOURCES.length)
    for (const needle of ['OptionsDX', 'Kaggle', '2010–2023', 'DoltHub', 'post-no-preference/options', '2024–2026', 'yfinance', 'DGS3MO', 'VIX']) {
      expect(card).toHaveTextContent(needle)
    }
    expect(card).toHaveTextContent('Raw vendor data is never committed')
  })
})

describe('AboutPage: data states', () => {
  it('while loading, shows progress text and no hero', () => {
    render(<AboutPage state={{ status: 'loading' }} />)
    expect(screen.getByText('Loading the exported surface…')).toBeInTheDocument()
    expect(screen.queryByText('Illustrative SSVI surface — not market data')).not.toBeInTheDocument()
  })

  it('on a load failure, shows the reason and the command that regenerates the data', () => {
    const error = new DataLoadError('fetch', './data/manifest.json answered HTTP 404')
    render(<AboutPage state={{ status: 'error', error }} />)
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('answered HTTP 404')
    expect(alert).toHaveTextContent('uv run python tools/export_app_data.py')
    expect(alert).toHaveTextContent('app/public/data/')
    expect(screen.queryByText('Illustrative SSVI surface — not market data')).not.toBeInTheDocument()
    expect(screen.getByText(/No manifest loaded/)).toBeInTheDocument()
  })

  it('when ready, shows the labelled hero and the contract metadata from manifest.json', () => {
    render(<AboutPage state={ready()} />)
    expect(screen.getByText('Illustrative SSVI surface — not market data')).toBeInTheDocument()
    const section = screen.getByRole('heading', { name: 'Exported data' }).nextElementSibling as HTMLElement
    expect(within(section).getByText('Schema version').nextElementSibling).toHaveTextContent('0.1.0')
    expect(within(section).getByText('Generated at').nextElementSibling).toHaveTextContent('2026-10-27T23:30:00Z')
    expect(within(section).getByText('Source commit').nextElementSibling).toHaveTextContent('a1b2c3d4e5f6')
    const row = within(section).getByText('illustrative_surface').closest('tr') as HTMLElement
    expect(row).toHaveTextContent('Test fixture: small SSVI-style grid')
    expect(screen.queryByText('exported from a dirty working tree')).not.toBeInTheDocument()
    expect(screen.queryByText('no commit yet')).not.toBeInTheDocument()
  })

  it.each([
    ['a1b2c3d4e5f6-dirty', 'exported from a dirty working tree'],
    ['uncommitted', 'no commit yet'],
  ])('flags a non-reproducible export (source_commit %s)', (sha, warning) => {
    render(<AboutPage state={ready({ ...manifest, source_commit: sha })} />)
    expect(screen.getByText(warning)).toBeInTheDocument()
  })
})
