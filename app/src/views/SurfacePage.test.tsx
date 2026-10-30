import type { ReactElement } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { SurfacePage } from './SurfacePage'
import { SceneContents } from './SurfaceHero'
import { DataLoadError } from '../data/loadAppData'
import { parseDataQuality, parseIllustrativeSurface, parseManifest, parseSurfaceFrames } from '../lib/contract'
import { EXTRAPOLATION_NOTE, FRAME_STATS } from '../content/surface'
import { canvasControl } from '../test/mockFiberControl'
import manifestFixture from '../test/fixtures/manifest.json'
import surfaceFixture from '../test/fixtures/illustrative_surface.json'
import dataQualityFixture from '../test/fixtures/data_quality.json'
import surfaceFramesFixture from '../test/fixtures/surface_frames.json'

// jsdom has no WebGL: swap fiber's Canvas for a marker div, and drei for no-ops.
vi.mock('@react-three/fiber', () => import('../test/mockFiber'))
vi.mock('@react-three/drei', () => ({ OrbitControls: () => null }))

const surfaceFrames = parseSurfaceFrames(surfaceFramesFixture)
const ready = () => ({
  status: 'ready' as const,
  data: {
    manifest: parseManifest(manifestFixture),
    surface: parseIllustrativeSurface(surfaceFixture),
    dataQuality: parseDataQuality(dataQualityFixture),
    surfaceFrames,
  },
})

/** The stat tiles as [title, value, unit] text triples, in page order. */
function tiles(): string[][] {
  return [...document.querySelectorAll('.stat')].map((tile) => [...tile.children].map((c) => c.textContent ?? ''))
}

const datePicker = () => screen.getByRole('group', { name: 'Surface date' })

beforeEach(() => {
  // Pretend WebGL exists, so SurfaceHero mounts (the mocked) canvas rather than the heatmap.
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({} as never)
})

afterEach(() => {
  canvasControl.lastProps = null
  vi.restoreAllMocks()
})

describe('SurfacePage: states', () => {
  it('while loading, shows progress text and no surface', () => {
    render(<SurfacePage state={{ status: 'loading' }} />)
    expect(screen.getByRole('heading', { level: 2, name: 'Surface' })).toBeInTheDocument()
    expect(screen.getByText('Loading the exported surfaces…')).toBeInTheDocument()
    expect(screen.queryByTestId('r3f-canvas')).not.toBeInTheDocument()
  })

  it('on a load failure, shows the reason and the command that regenerates the data', () => {
    const error = new DataLoadError('fetch', './data/surface_frames.json answered HTTP 404')
    render(<SurfacePage state={{ status: 'error', error }} />)
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('./data/surface_frames.json answered HTTP 404')
    expect(alert).toHaveTextContent('uv run python tools/export_app_data.py')
    expect(screen.queryByRole('group', { name: 'Surface date' })).not.toBeInTheDocument()
  })
})

describe('SurfacePage: one frame at a time', () => {
  it('offers one button per frame, in file order, with the first one chosen', () => {
    render(<SurfacePage state={ready()} />)
    const buttons = within(datePicker()).getAllByRole('button')
    expect(buttons.map((b) => b.textContent)).toEqual(['2020-01-03', '2020-03-16'])
    expect(buttons.map((b) => b.getAttribute('aria-pressed'))).toEqual(['true', 'false'])
  })

  it("shows the first frame's own numbers, formatted, each with the file's unit", () => {
    render(<SurfacePage state={ready()} />)
    expect(document.querySelector('.frame-label')).toHaveTextContent('2020-01-03: calm: a made-up quiet day')
    expect(tiles()).toEqual([
      ['SPY close', '$320.50', 'USD, the SPY close'],
      ['VIX close', '12.47', 'index points, the Cboe VIX close'],
      ['30-day ATM implied vol', '19.0%', 'implied volatility at k = 0 and 30 days, decimal'],
      ['Quoted share of the grid', '33.3%', 'fraction of grid cells read without strike or tenor extrapolation'],
      ['Expiries used', '4', 'listed expiries with a usable smile (5 or more valid OTM quotes)'],
    ])
    expect(FRAME_STATS).toHaveLength(5)
  })

  it('switches to another date: its numbers, its badge and its surface', () => {
    render(<SurfacePage state={ready()} />)
    fireEvent.click(within(datePicker()).getByRole('button', { name: '2020-03-16' }))
    const buttons = within(datePicker()).getAllByRole('button')
    expect(buttons.map((b) => b.getAttribute('aria-pressed'))).toEqual(['false', 'true'])
    expect(document.querySelector('.frame-label')).toHaveTextContent('2020-03-16: stress: a made-up crash')
    expect(screen.queryByText(/calm: a made-up quiet day/)).not.toBeInTheDocument()
    expect(tiles().map(([, value]) => value)).toEqual(['$239.85', '82.69', '75.0%', '83.3%', '5'])
    expect(screen.getByText('SPY implied-vol surface, 2020-03-16: market data (OptionsDX)')).toBeInTheDocument()
    // The scene is built from the second frame's IVs on the file's grid.
    const scene = canvasControl.lastProps?.children as ReactElement<{ geo: { extent: unknown } }>
    expect(scene.type).toBe(SceneContents)
    expect(scene.props.geo.extent).toEqual({ moneyness: [-0.1, 0.1], dte: [7, 30], iv: [0.65, 1.2] })
  })

  it('labels the surface as market data, never as the illustrative one', () => {
    render(<SurfacePage state={ready()} />)
    expect(screen.getByText('SPY implied-vol surface, 2020-01-03: market data (OptionsDX)')).toBeInTheDocument()
    expect(screen.queryByText(/Illustrative SSVI surface/)).not.toBeInTheDocument()
  })

  it('says plainly which cells are extrapolated, citing ADR-0004', () => {
    render(<SurfacePage state={ready()} />)
    expect(screen.getByText(EXTRAPOLATION_NOTE)).toBeInTheDocument()
    expect(EXTRAPOLATION_NOTE).toContain('ADR-0004')
    expect(EXTRAPOLATION_NOTE).toContain('extrapolations, not quotes')
  })

  it('names the pricing build that made the file', () => {
    render(<SurfacePage state={ready()} />)
    const meta = document.querySelector('dl.meta') as HTMLElement
    expect(within(meta).getByText('Run').nextElementSibling).toHaveTextContent('pricing-9fc92382fa7c')
    expect(within(meta).getByText('Dates').nextElementSibling).toHaveTextContent('2020-01-03 to 2020-03-16')
    expect(within(meta).getByText('Schema version').nextElementSibling).toHaveTextContent('0.3.0')
    expect(screen.getByText('Test fixture (OptionsDX): two made-up surfaces on a 2 x 3 grid')).toBeInTheDocument()
  })

  it("names the file's vendor in the badge: the display name of run.data_source, not a fixed word", () => {
    const doc = JSON.parse(JSON.stringify(surfaceFramesFixture)) as typeof surfaceFramesFixture
    doc.run.data_source = 'dolthub'
    doc.label = 'Test fixture (DoltHub): two made-up surfaces on a 2 x 3 grid'
    const data = { ...ready().data, surfaceFrames: parseSurfaceFrames(doc) }
    render(<SurfacePage state={{ status: 'ready', data }} />)
    expect(screen.getByText('SPY implied-vol surface, 2020-01-03: market data (DoltHub)')).toBeInTheDocument()
    expect(screen.queryByText(/market data \(OptionsDX\)/)).not.toBeInTheDocument()
  })

  it('falls back to the heatmap of the chosen frame without WebGL', () => {
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
    render(<SurfacePage state={ready()} />)
    expect(screen.queryByTestId('r3f-canvas')).not.toBeInTheDocument()
    const heat = screen.getByRole('img', { name: 'Heatmap' })
    // 2 dte rows x 3 moneyness columns, labelled from the file's grid
    expect(within(heat).getAllByTestId('vsb-heat-cell')).toHaveLength(6)
    for (const t of ['7d', '30d', '-0.10', '0.00', '0.10']) expect(within(heat).getByText(t)).toBeInTheDocument()
  })
})

describe('SurfacePage: the data notice', () => {
  const notice = () => screen.getByRole('region', { name: 'Data sources and terms' })

  it.each([
    ['loading', { status: 'loading' as const }],
    ['error', { status: 'error' as const, error: new DataLoadError('fetch', './data/surface_frames.json answered HTTP 404') }],
    ['ready', ready()],
  ])('is shown while %s', (_name, state) => {
    render(<SurfacePage state={state} />)
    expect(within(notice()).getByRole('heading', { level: 3, name: 'Data sources and terms' })).toBeInTheDocument()
  })

  it('names the sources of an OptionsDX file: OptionsDX via Kaggle, Yahoo Finance through yfinance, Cboe', () => {
    render(<SurfacePage state={ready()} />)
    expect(notice()).toHaveTextContent(
      "These surfaces are computed from OptionsDX end-of-day option quotes, obtained through the Kaggle dataset dudesurfin/spy-options-eod-volatility-surface-2010-2023. Kaggle lists that dataset under the MIT licence, but the numbers are OptionsDX's, so we treat them as vendor data and publish only values derived from them.",
    )
    expect(notice()).toHaveTextContent(
      'SPY closes come from Yahoo Finance, downloaded with yfinance, and VIX closes from Cboe’s VIX historical data. DATA.md, linked below, gives the terms of each.',
    )
    expect(notice()).toHaveTextContent("The data is not covered by this repository's MIT licence.")
  })

  it('states no terms of its own for the closes: it names the sources and leaves the terms to DATA.md', () => {
    render(<SurfacePage state={ready()} />)
    expect(notice()).not.toHaveTextContent(/used under/i)
    expect(notice()).not.toHaveTextContent(/non-commercial/i)
  })

  it('says nothing about DoltHub for an OptionsDX file: no DoltHub data is on the page', () => {
    render(<SurfacePage state={ready()} />)
    expect(notice()).not.toHaveTextContent(/DoltHub/i)
  })

  describe('for a DoltHub file (run.data_source "dolthub")', () => {
    const dolthub = () => {
      const doc = JSON.parse(JSON.stringify(surfaceFramesFixture)) as typeof surfaceFramesFixture
      doc.run.data_source = 'dolthub'
      doc.label = 'Test fixture (DoltHub): two made-up surfaces on a 2 x 3 grid'
      return { status: 'ready' as const, data: { ...ready().data, surfaceFrames: parseSurfaceFrames(doc) } }
    }

    it('names DoltHub and carries the CC BY-SA 4.0 attribution, in full', () => {
      render(<SurfacePage state={dolthub()} />)
      expect(notice()).toHaveTextContent('These surfaces are computed from the SPY option quotes of the DoltHub database post-no-preference/options.')
      expect(notice()).toHaveTextContent(
        'Contains information derived from the DoltHub database post-no-preference/options, licensed under CC BY-SA 4.0. Changes: each out-of-the-money quote had its early-exercise premium removed and its implied vol solved, and the smiles were read on a fixed grid of log-moneyness and days to expiry; no quote row is reproduced. The DoltHub-derived surfaces on this page are shared under the same licence.',
      )
      expect(notice()).toHaveTextContent('SPY closes come from Yahoo Finance, downloaded with yfinance, and VIX closes from Cboe’s VIX historical data.')
    })

    it('does not show the OptionsDX notice', () => {
      render(<SurfacePage state={dolthub()} />)
      expect(notice()).not.toHaveTextContent(/OptionsDX/)
      expect(notice()).not.toHaveTextContent(/Kaggle/)
    })

    it('links the DoltHub database and the licence, beside DATA.md and the notice served next to the data', () => {
      render(<SurfacePage state={dolthub()} />)
      const link = (name: string) => within(notice()).getByRole('link', { name })
      expect(link('post-no-preference/options')).toHaveAttribute('href', 'https://www.dolthub.com/repositories/post-no-preference/options')
      expect(link('CC BY-SA 4.0')).toHaveAttribute('href', 'https://creativecommons.org/licenses/by-sa/4.0/')
      expect(within(notice()).getAllByRole('link')).toHaveLength(4)
    })
  })

  it.each([
    ['loading', { status: 'loading' as const }],
    ['error', { status: 'error' as const, error: new DataLoadError('fetch', './data/surface_frames.json answered HTTP 404') }],
  ])('names no vendor while %s: with no file there is no run.data_source to follow', (_name, state) => {
    render(<SurfacePage state={state} />)
    expect(notice()).not.toHaveTextContent(/OptionsDX|DoltHub|Yahoo|Cboe/)
    expect(notice()).toHaveTextContent("The data is not covered by this repository's MIT licence.")
  })

  it('links to DATA.md on GitHub and to the notice served next to the data', () => {
    render(<SurfacePage state={ready()} />)
    expect(within(notice()).getByRole('link', { name: 'DATA.md' })).toHaveAttribute(
      'href',
      'https://github.com/rajib2k5/vol-strategy-backtester/blob/main/DATA.md',
    )
    expect(within(notice()).getByRole('link', { name: 'data/LICENSE-DATA.md' })).toHaveAttribute('href', './data/LICENSE-DATA.md')
  })
})
