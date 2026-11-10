import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { SignalPage } from './SignalPage'
import { DataLoadError } from '../data/loadAppData'
import { parseBlotter, parseDataQuality, parseIllustrativeSurface, parseManifest, parsePositionsTimeline, parseSignalsTimeline, parseSurfaceFrames } from '../lib/contract'
import { FORECAST_NOT_SCORED, NO_FITS, SIGNAL_IN_SAMPLE_NOTE, SIGNAL_PAGE_INTRO } from '../content/signal'
import manifestFixture from '../test/fixtures/manifest.json'
import surfaceFixture from '../test/fixtures/illustrative_surface.json'
import dataQualityFixture from '../test/fixtures/data_quality.json'
import surfaceFramesFixture from '../test/fixtures/surface_frames.json'
import blotterFixture from '../test/fixtures/blotter.json'
import positionsTimelineFixture from '../test/fixtures/positions_timeline.json'
import signalsFixture from '../test/fixtures/signals_timeline.json'

type Obj = Record<string, unknown>
type Doc = Obj & { signal: Obj; fits: unknown[]; model_fit_date: unknown[]; dates: unknown[]; forecast_test: Obj | null }
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T

/** The page's state with the signals fixture after `edit`, parsed, so a test cannot feed the page what the contract refuses. */
function ready(edit: (d: Doc) => void = () => {}) {
  const d = clone(signalsFixture) as unknown as Doc
  edit(d)
  return {
    status: 'ready' as const,
    data: {
      manifest: parseManifest(manifestFixture),
      surface: parseIllustrativeSurface(surfaceFixture),
      dataQuality: parseDataQuality(dataQualityFixture),
      surfaceFrames: parseSurfaceFrames(surfaceFramesFixture),
      blotter: parseBlotter(blotterFixture),
      positionsTimeline: parsePositionsTimeline(positionsTimelineFixture),
      signalsTimeline: parseSignalsTimeline(d),
    },
  }
}

const priceChart = (): HTMLElement => within(screen.getByRole('figure', { name: 'IV30, forecast vol and ex-post realised vol' })).getByRole('img')
const ratioChart = (): HTMLElement => within(screen.getByRole('figure', { name: 'Log variance ratio' })).getByRole('img')
const parts = (svg: HTMLElement, name: string): Element[] => [...svg.querySelectorAll(`[data-series="${name}"]`)]
const termValue = (dl: HTMLElement, term: string): string => within(dl).getByText(term).nextElementSibling?.textContent ?? ''

describe('SignalPage: states', () => {
  it.each([
    ['loading', { status: 'loading' as const }],
    ['error', { status: 'error' as const, error: new Error('x') }],
    ['ready', ready()],
    ['ready without the dataset', { ...ready(), data: { ...ready().data, signalsTimeline: null } }],
  ])('%s: the heading, the intro and the in-sample note are always there', (_name, state) => {
    render(<SignalPage state={state} />)
    expect(screen.getByRole('heading', { level: 2, name: 'Signal' })).toBeInTheDocument()
    expect(screen.getByText(SIGNAL_PAGE_INTRO)).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'What this series is' })).toHaveTextContent(SIGNAL_IN_SAMPLE_NOTE)
  })
  it('says it is loading, with no chart', () => {
    render(<SignalPage state={{ status: 'loading' }} />)
    expect(screen.getByText('Loading the exported signal…')).toBeInTheDocument()
    expect(screen.queryByRole('figure')).not.toBeInTheDocument()
  })
  it('shows the load problem as an alert, naming the cause and the export command', () => {
    render(<SignalPage state={{ status: 'error', error: new DataLoadError('fetch', './data/signals_timeline.json answered HTTP 404') }} />)
    expect(screen.getByRole('alert')).toHaveTextContent('answered HTTP 404')
    expect(screen.queryByRole('figure')).not.toBeInTheDocument()
  })
  it('draws nothing when the file is not there', () => {
    render(<SignalPage state={{ ...ready(), data: { ...ready().data, signalsTimeline: null } }} />)
    expect(screen.queryByRole('figure')).not.toBeInTheDocument()
  })
})

describe('SignalPage: the charts', () => {
  it('draws IV30, the forecast and the ex-post vol, each broken where the file has no value', () => {
    render(<SignalPage state={ready()} />)
    const svg = priceChart()
    // iv30 is null on one date (two runs), rv_forecast on the first two dates (one run), rv_realised on the last 16 (one run)
    expect(parts(svg, 'IV30')).toHaveLength(2)
    expect(parts(svg, 'RV forecast')).toHaveLength(1)
    expect(parts(svg, 'RV realised (ex post)')).toHaveLength(1)
    expect((parts(svg, 'RV realised (ex post)')[0].getAttribute('points') as string).split(' ')).toHaveLength(44)
    expect(svg.textContent).toContain('── RV realised (ex post)')
  })
  it('captions the chart with its date range and the number of dates', () => {
    render(<SignalPage state={ready()} />)
    expect(screen.getByRole('figure', { name: 'IV30, forecast vol and ex-post realised vol' })).toHaveTextContent('60 dates, 2019-10-01 to 2019-12-23')
  })
  it('draws the log variance ratio with the three distinct threshold levels of the file, named in a list', () => {
    render(<SignalPage state={ready()} />)
    const levels = [...ratioChart().querySelectorAll('[data-level]')].map((l) => l.getAttribute('data-level'))
    expect(levels).toEqual(['0', '0.4', '-0.4'])
    const list = screen.getByRole('list', { name: 'Threshold levels' })
    expect(within(list).getAllByRole('listitem').map((li) => li.textContent)).toEqual([
      '0: short entry, long entry, short exit',
      '0.4: short entry, long exit',
      '-0.4: short exit',
    ])
  })
  it('marks only the refits that fall inside the date range, in both charts', () => {
    render(<SignalPage state={ready()} />)
    for (const svg of [priceChart(), ratioChart()]) {
      expect([...svg.querySelectorAll('[data-mark]')].map((m) => m.getAttribute('data-mark'))).toEqual(['2019-10-31', '2019-11-29'])
    }
  })
  it('lists every refit date in the text, including the one before the first date', () => {
    render(<SignalPage state={ready()} />)
    expect(screen.getByText('2019-09-30, 2019-10-31, 2019-11-29')).toBeInTheDocument()
  })
  it('says the naive model has no refits, and marks none', () => {
    render(
      <SignalPage
        state={ready((d) => {
          d.signal.rv_model = 'naive'
          d.fits = []
          d.model_fit_date = d.dates.map(() => null)
          d.forecast_test = null
        })}
      />,
    )
    expect(screen.getByText(NO_FITS)).toBeInTheDocument()
    expect(priceChart().querySelectorAll('[data-mark]')).toHaveLength(0)
  })
  it('names the model, its window and its units', () => {
    render(<SignalPage state={ready()} />)
    expect(screen.getByText(/log_variance_ratio_demo: har forecast, 30-day window, 21-session horizon, at least 504 pairs to fit/)).toBeInTheDocument()
    expect(screen.getByText('ln(IV30^2 / RV^2), dimensionless', { selector: 'dd' })).toBeInTheDocument()
    expect(screen.getByText('HAR coefficients [constant, daily, weekly, monthly] on daily squared log returns', { selector: 'dd' })).toBeInTheDocument()
  })
})

describe('SignalPage: the forecast test', () => {
  it('shows the decision, p, EWC t, the interval, block, q, n, the proxy label, the pre-registration id and its SHA-256', () => {
    render(<SignalPage state={ready()} />)
    const heading = screen.getByRole('heading', { level: 3, name: 'Forecast test' })
    const card = heading.parentElement as HTMLElement
    const dl = card.querySelector('dl') as HTMLElement
    expect(termValue(dl, 'Decision')).toBe('har')
    expect(termValue(dl, 'p')).toBe('0.0120')
    expect(termValue(dl, 'p (Holm)')).toBe('0.0120')
    expect(termValue(dl, 'Threshold (p <)')).toBe('0.025')
    expect(termValue(dl, 'Fragile band')).toBe('[0.02, 0.05)')
    expect(termValue(dl, 'Effective size (ABC-weighted, battery / second seed)')).toBe('0.0508 / 0.0502')
    expect(termValue(dl, 'Worst matched size (battery / second seed)')).toContain('0.0815 / 0.0830')
    expect(termValue(dl, 'Worst matched size (battery / second seed)')).toContain('S4 f=0.15 right +d (made up); S4 f=0.1 left -d (made up)')
    expect(within(dl).queryByText('Alpha')).not.toBeInTheDocument()
    expect(termValue(dl, 'EWC t')).toBe('2.31')
    expect(termValue(dl, 'Confidence interval')).toBe('[0.0007, 0.0077]')
    expect(termValue(dl, 'Block')).toBe('21')
    expect(termValue(dl, 'q')).toBe('6')
    expect(termValue(dl, 'n')).toBe('1,500')
    expect(termValue(dl, 'Window')).toBe('2012-01-03 to 2018-12-31 (made up)')
    expect(termValue(dl, 'Label')).toBe('proxy: forecast-loss comparison, not a trading result')
    expect(termValue(dl, 'Pre-registration')).toBe('prereg-demo-001')
    expect(termValue(dl, 'SHA-256')).toBe('4f'.repeat(32))
    expect(screen.queryByText(FORECAST_NOT_SCORED)).not.toBeInTheDocument()
  })
  it('shows a threshold of 0.025 as 0.025, not 0.03, and the sizes to four decimals', () => {
    render(<SignalPage state={ready((d) => ((d.forecast_test as Obj).threshold = 0.025))} />)
    const dl = screen.getByRole('heading', { level: 3, name: 'Forecast test' }).parentElement?.querySelector('dl') as HTMLElement
    expect(termValue(dl, 'Threshold (p <)')).toBe('0.025')
    expect(dl).not.toHaveTextContent('0.03')
    expect(dl).toHaveTextContent('0.0508 / 0.0502')
  })
  it('shows no fragile notice when p is below the band (the fixture, p 0.012), and still shows the band', () => {
    render(<SignalPage state={ready()} />)
    expect(screen.queryByText(/decided by modelling choices/)).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Fragile decision' })).not.toBeInTheDocument()
    expect(screen.getByText('Fragile band')).toBeInTheDocument()
  })
  it('shows "p in [0.02, 0.05): decided by modelling choices" when the file says the result is fragile (p 0.022)', () => {
    const fragile = (d: Doc) => {
      const t = d.forecast_test as Obj
      t.p = 0.022
      t.p_holm = 0.022
      t.fragile = true
    }
    render(<SignalPage state={ready(fragile)} />)
    const notice = screen.getByRole('region', { name: 'Fragile decision' })
    expect(notice).toHaveTextContent(/^p in \[0\.02, 0\.05\): decided by modelling choices$/)
    expect(screen.getByText('p in [0.02, 0.05): decided by modelling choices')).toBeVisible()
    const dl = screen.getByRole('heading', { level: 3, name: 'Forecast test' }).parentElement?.querySelector('dl') as HTMLElement
    expect(termValue(dl, 'Fragile band')).toBe('[0.02, 0.05)')
  })
  it('builds the notice and the band row from the file\'s own band', () => {
    const edit = (d: Doc) => {
      const t = d.forecast_test as Obj
      t.fragile_band = [0.03, 0.04]
      t.p = 0.035
      t.p_holm = 0.035
      t.decision = 'naive'
      t.fragile = true
      d.signal.rv_model = 'naive'
      d.fits = []
      d.model_fit_date = d.dates.map(() => null)
    }
    render(<SignalPage state={ready(edit)} />)
    expect(screen.getByText('p in [0.03, 0.04): decided by modelling choices')).toBeInTheDocument()
    const dl = screen.getByRole('heading', { level: 3, name: 'Forecast test' }).parentElement?.querySelector('dl') as HTMLElement
    expect(termValue(dl, 'Fragile band')).toBe('[0.03, 0.04)')
  })
  it('says "Forecast test: not scored yet" when the file has no test', () => {
    render(<SignalPage state={ready((d) => (d.forecast_test = null))} />)
    const heading = screen.getByRole('heading', { level: 3, name: 'Forecast test' })
    expect(screen.getByText('Forecast test: not scored yet')).toBeInTheDocument()
    expect(heading.parentElement?.querySelector('dl')).toBeNull()
  })
})

describe('SignalPage: where the numbers come from', () => {
  it('shows the run block and the label of the file', () => {
    render(<SignalPage state={ready()} />)
    const heading = screen.getByRole('heading', { level: 3, name: 'Where these numbers come from' })
    const meta = heading.parentElement?.querySelector('dl.meta') as HTMLElement
    expect(termValue(meta, 'Run')).toBe(signalsFixture.run.run_id)
    expect(termValue(meta, 'Strategy')).toBe('SignalDemo')
    expect(termValue(meta, 'Split')).toBe('development')
    expect(termValue(meta, 'Dates')).toBe('2019-10-01 to 2019-12-31')
    expect(termValue(meta, 'Schema version')).toBe('0.5.0')
    expect(screen.getByText(signalsFixture.label)).toBeInTheDocument()
  })
})
