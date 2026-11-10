import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { StrategiesPage } from './StrategiesPage'
import { DataLoadError } from '../data/loadAppData'
import { parseBlotter, parseDataQuality, parseIllustrativeSurface, parseManifest, parsePositionsTimeline, parseStrategyPositions, parseSurfaceFrames } from '../lib/contract'
import { EXIT_REASON_COLOR, OPEN_POSITION_COLOR } from '../content/engineRun'
import { NO_STRATEGY_POSITIONS } from '../content/strategies'
import manifestFixture from '../test/fixtures/manifest.json'
import surfaceFixture from '../test/fixtures/illustrative_surface.json'
import dataQualityFixture from '../test/fixtures/data_quality.json'
import surfaceFramesFixture from '../test/fixtures/surface_frames.json'
import blotterFixture from '../test/fixtures/blotter.json'
import positionsTimelineFixture from '../test/fixtures/positions_timeline.json'
import strategiesFixture from '../test/fixtures/strategy_positions.json'

type Obj = Record<string, unknown>
type Doc = Obj & { runs: (Obj & { positions: Obj[] })[] }
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T

function ready(edit: (d: Doc) => void = () => {}) {
  const d = clone(strategiesFixture) as unknown as Doc
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
      strategyPositions: parseStrategyPositions(d),
    },
  }
}

const SHORT = 'ShortVolOnSignal'
const LONG = 'LongVolOnSignal'
const timeline = (strategy: string): HTMLElement => screen.getByRole('img', { name: `When each position of ${strategy} was open` })
const bar = (strategy: string, id: number): SVGRectElement => timeline(strategy).querySelector(`rect[data-position="${id}"]`) as SVGRectElement
const right = (el: Element): number => Number(el.getAttribute('x')) + Number(el.getAttribute('width'))
const runCard = (strategy: string): HTMLElement => screen.getByRole('region', { name: `Run of ${strategy}` })
const termValue = (scope: HTMLElement, term: string): string => within(scope).getByText(term).nextElementSibling?.textContent ?? ''

describe('StrategiesPage: states', () => {
  it('says it is loading, with no run', () => {
    render(<StrategiesPage state={{ status: 'loading' }} />)
    expect(screen.getByRole('heading', { level: 2, name: 'Strategies' })).toBeInTheDocument()
    expect(screen.getByText('Loading the exported strategies…')).toBeInTheDocument()
    expect(screen.queryByRole('region')).not.toBeInTheDocument()
  })
  it('shows the load problem as an alert', () => {
    render(<StrategiesPage state={{ status: 'error', error: new DataLoadError('contract', 'strategy_positions.json: broken') }} />)
    expect(screen.getByRole('alert')).toHaveTextContent('strategy_positions.json: broken')
    expect(screen.queryByRole('region', { name: 'Trial count' })).not.toBeInTheDocument()
  })
  it('draws nothing but the heading when the file is not there', () => {
    render(<StrategiesPage state={{ ...ready(), data: { ...ready().data, strategyPositions: null } }} />)
    expect(screen.getByRole('heading', { level: 2, name: 'Strategies' })).toBeInTheDocument()
    expect(screen.queryByRole('region')).not.toBeInTheDocument()
  })
})

describe('StrategiesPage: the banner and the runs', () => {
  it('shows the banner as written, before any run', () => {
    render(<StrategiesPage state={ready()} />)
    const banner = screen.getByText('7 development trials (made up); no performance before M6')
    expect(banner.closest('section')).toBe(screen.getByRole('region', { name: 'Trial count' }))
    expect(banner.compareDocumentPosition(runCard(SHORT)) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(banner.compareDocumentPosition(screen.getByRole('heading', { level: 3, name: SHORT })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
  it('shows each run with its strategy, trial group, trial count and params as text', () => {
    render(<StrategiesPage state={ready()} />)
    expect(screen.getByRole('heading', { level: 3, name: SHORT })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 3, name: LONG })).toBeInTheDocument()
    const short = runCard(SHORT)
    expect(termValue(short, 'Trial group')).toBe('short-vol-demo')
    expect(termValue(short, 'Trials in the group')).toBe('4')
    expect(termValue(short, 'entry_theta')).toBe('0.4')
    expect(termValue(short, 'max_open')).toBe('1')
    expect(termValue(short, 'note')).toBe('made up')
    const long = runCard(LONG)
    expect(termValue(long, 'Trial group')).toBe('long-vol-demo')
    expect(termValue(long, 'exit_band')).toBe('0.4')
    expect(termValue(long, 'windows')).toBe('[21,30]')
  })
  it('names each run\'s block under "Where these numbers come from"', () => {
    render(<StrategiesPage state={ready()} />)
    expect(termValue(runCard(SHORT), 'Run')).toBe(strategiesFixture.runs[0].run.run_id)
    expect(termValue(runCard(LONG), 'Run')).toBe(strategiesFixture.runs[1].run.run_id)
    expect(termValue(runCard(LONG), 'Dates')).toBe('2016-01-04 to 2019-06-28')
    expect(termValue(runCard(LONG), 'Split')).toBe('development')
    expect(screen.getByText(strategiesFixture.label)).toBeInTheDocument()
  })
  it('lists the units of ratio and entry_signal', () => {
    render(<StrategiesPage state={ready()} />)
    expect(screen.getByText('contracts per package, signed: + long, - short')).toBeInTheDocument()
    expect(screen.getByText('ln(IV30^2 / RV^2) at the entry decision, dimensionless')).toBeInTheDocument()
  })
})

describe('StrategiesPage: the position timeline', () => {
  it('draws one bar per position, coloured by its exit reason', () => {
    render(<StrategiesPage state={ready()} />)
    expect([...timeline(SHORT).querySelectorAll('rect[data-position]')]).toHaveLength(4)
    expect(bar(SHORT, 1).getAttribute('fill')).toBe(EXIT_REASON_COLOR.signal)
    expect(bar(SHORT, 2).getAttribute('fill')).toBe(EXIT_REASON_COLOR.dte)
    expect(bar(SHORT, 3).getAttribute('fill')).toBe(EXIT_REASON_COLOR.profit_target)
    expect(bar(LONG, 1).getAttribute('fill')).toBe(EXIT_REASON_COLOR.stop)
    expect(bar(LONG, 2).getAttribute('fill')).toBe(EXIT_REASON_COLOR.expiry)
  })
  it('draws an open-at-end position to the sample\'s end, dashed, in the open colour, and marks it "open"', () => {
    render(<StrategiesPage state={ready()} />)
    const open = bar(SHORT, 4)
    const closed = bar(SHORT, 3)
    expect(open.getAttribute('fill')).toBe(OPEN_POSITION_COLOR)
    expect(open.getAttribute('stroke-dasharray')).toBe('3 2')
    expect(closed.getAttribute('stroke-dasharray')).toBeNull()
    // the sample ends on the scale's right edge (720 wide, 48 of right margin); a closed bar stops short of it
    expect(right(open)).toBeCloseTo(672, 6)
    expect(right(closed)).toBeLessThan(672)
    expect(within(timeline(SHORT)).getByText('open')).toBeInTheDocument()
    expect(within(timeline(SHORT)).getAllByText('open')).toHaveLength(1)
    expect(open.querySelector('title')?.textContent).toBe('Position 4, short_straddle: opened 2019-12-02, no close date (drawn to the end of the sample), open')
  })
  it('draws the other run\'s open position to that run\'s own sample end, every bar inside the plot', () => {
    render(<StrategiesPage state={ready()} />)
    expect(right(bar(LONG, 3))).toBeCloseTo(672, 6)
    expect(right(bar(LONG, 2))).toBeLessThan(672)
    // each run is on the scale of its own sample: no bar starts left of the plot's 12-unit margin, whichever run it is in
    for (const strategy of [SHORT, LONG]) {
      for (const rect of timeline(strategy).querySelectorAll('rect[data-position]')) expect(Number(rect.getAttribute('x'))).toBeGreaterThanOrEqual(12)
    }
  })
})

describe('StrategiesPage: the legend, which names reasons and counts none', () => {
  it('names the exit reasons the run uses, and "open" when a position is open', () => {
    render(<StrategiesPage state={ready()} />)
    const legend = screen.getByRole('list', { name: `Exit reasons of ${SHORT}` })
    expect(within(legend).getAllByRole('listitem').map((li) => li.textContent)).toEqual([
      'dte: closed by the days-to-expiry rule',
      'signal: exit signal',
      'profit_target: profit target',
      'open: no close date, drawn to the end of the sample',
    ])
    const swatch = within(legend).getByText('signal').closest('li')?.querySelector('.swatch')
    expect(swatch?.getAttribute('style')).toContain(EXIT_REASON_COLOR.signal)
  })
  it('names only the reasons of its own run', () => {
    render(<StrategiesPage state={ready()} />)
    const legend = screen.getByRole('list', { name: `Exit reasons of ${LONG}` })
    expect(within(legend).getAllByRole('listitem').map((li) => li.textContent)).toEqual(['expiry: held to expiry', 'stop: stop loss', 'open: no close date, drawn to the end of the sample'])
  })
  it('has no "open" entry when every position is closed', () => {
    render(
      <StrategiesPage
        state={ready((d) => {
          d.runs[0].positions[3].closed = '2019-12-20'
          d.runs[0].positions[3].exit_reason = 'dte'
        })}
      />,
    )
    const legend = screen.getByRole('list', { name: `Exit reasons of ${SHORT}` })
    expect(within(legend).queryByText('open', { exact: false })).not.toBeInTheDocument()
  })
  it('shows no count of positions anywhere on the page', () => {
    const { container } = render(<StrategiesPage state={ready()} />)
    const text = container.textContent ?? ''
    expect(text).not.toMatch(/\(\d+\)/)
    expect(text).not.toMatch(/\b\d+ positions?\b/i)
    expect(within(screen.getByRole('list', { name: `Exit reasons of ${SHORT}` })).queryByText(/\d/)).not.toBeInTheDocument()
  })
})

describe('StrategiesPage: the positions table', () => {
  const cells = (table: HTMLElement): string[][] =>
    within(table)
      .getAllByRole('row')
      .map((row) => [...row.children].map((c) => c.textContent ?? ''))
  it('lists each position with its structure, dates, exit reason, entry signal and legs', () => {
    render(<StrategiesPage state={ready()} />)
    const rows = cells(screen.getByRole('table', { name: `Positions of ${SHORT}` }))
    expect(rows[0]).toEqual(['Position', 'Structure', 'Opened', 'Closed', 'Exit reason', 'Entry signal', 'Legs'])
    expect(rows[1]).toEqual(['1', 'short_straddle', '2018-02-05', '2018-02-16', 'signal', '0.3100', 'SPY   180316C00270000 × -1SPY   180316P00270000 × -1'])
    expect(rows[3][1]).toBe('straddle_calendar')
    expect(rows[3][5]).toBe('—')
    expect(rows[3][6]).toContain('SPY   181019C00290000 × +1')
    expect(rows[4].slice(3, 5)).toEqual(['open', '—'])
  })
  it('says a run with no positions opened none, and draws no timeline for it', () => {
    render(
      <StrategiesPage
        state={ready((d) => {
          d.runs[1].positions = []
        })}
      />,
    )
    expect(within(runCard(LONG)).getByText(NO_STRATEGY_POSITIONS)).toBeInTheDocument()
    expect(screen.queryByRole('img', { name: `When each position of ${LONG} was open` })).not.toBeInTheDocument()
    expect(screen.queryByRole('list', { name: `Exit reasons of ${LONG}` })).not.toBeInTheDocument()
    expect(timeline(SHORT)).toBeInTheDocument()
  })
})
