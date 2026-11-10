import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { PositionsPage } from './PositionsPage'
import { ROW_STEP } from './rowLimit'
import { DataLoadError } from '../data/loadAppData'
import { parseBlotter, parseDataQuality, parseIllustrativeSurface, parseManifest, parsePositionsTimeline, parseSurfaceFrames } from '../lib/contract'
import { EXIT_REASON_COLOR, EXIT_REASON_TEXT, OPEN_POSITION_COLOR } from '../content/engineRun'
import { NO_POSITIONS, POSITIONS_PAGE_INTRO } from '../content/positions'
import manifestFixture from '../test/fixtures/manifest.json'
import surfaceFixture from '../test/fixtures/illustrative_surface.json'
import dataQualityFixture from '../test/fixtures/data_quality.json'
import surfaceFramesFixture from '../test/fixtures/surface_frames.json'
import blotterFixture from '../test/fixtures/blotter.json'
import positionsTimelineFixture from '../test/fixtures/positions_timeline.json'

type Obj = Record<string, unknown>
type Doc = Obj & { run: Obj; positions: (Obj & { legs: Obj[] })[]; dates: unknown[]; open_count: unknown[] }
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T

/** The page's state with the positions fixture after `edit`, parsed (so a test cannot feed the page something the contract refuses). */
function ready(edit: (d: Doc) => void = () => {}) {
  const d = clone(positionsTimelineFixture) as unknown as Doc
  edit(d)
  return {
    status: 'ready' as const,
    data: {
      manifest: parseManifest(manifestFixture),
      surface: parseIllustrativeSurface(surfaceFixture),
      dataQuality: parseDataQuality(dataQualityFixture),
      surfaceFrames: parseSurfaceFrames(surfaceFramesFixture),
      blotter: parseBlotter(blotterFixture),
      positionsTimeline: parsePositionsTimeline(d),
    },
  }
}

const timeline = () => screen.getByRole('img', { name: 'When each position was open' })
const bars = (): SVGRectElement[] => [...timeline().querySelectorAll<SVGRectElement>('rect[data-position]')]
const bar = (id: number): SVGRectElement => timeline().querySelector(`rect[data-position="${id}"]`) as SVGRectElement
const num = (el: Element, attr: string): number => Number(el.getAttribute(attr))
const right = (el: Element): number => num(el, 'x') + num(el, 'width')

/** The fixture's last position closed on 2015-03-13 by the dte rule, so none is open at the end (open_count follows). */
function closeLastPosition(d: Doc): void {
  d.positions[3].closed = '2015-03-13'
  d.positions[3].exit_reason = 'dte'
  d.open_count = [1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0]
}

/** The rows of a table as arrays of cell texts, header row first. */
function cells(table: HTMLElement): string[][] {
  return within(table)
    .getAllByRole('row')
    .map((row) => [...row.children].map((c) => c.textContent ?? ''))
}

/** A run that ended in ruin with positions 3 and 4 unclosed (closed null, exit reason ruin) and positions 1 and 2 closed. */
function ruinedRun(d: Doc): void {
  d.run.status = 'ruin'
  d.positions[2].closed = null
  d.positions[2].exit_reason = 'ruin'
  d.positions[3].exit_reason = 'ruin'
  d.open_count = [1, 2, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2]
}

describe('PositionsPage: states', () => {
  it.each([
    ['loading', { status: 'loading' as const }],
    ['error', { status: 'error' as const, error: new Error('x') }],
    ['ready', ready()],
  ])('always shows its heading, what the page is for and the notice that this is no result while %s', (_name, state) => {
    render(<PositionsPage state={state} />)
    expect(screen.getByRole('heading', { level: 2, name: 'Positions' })).toBeInTheDocument()
    expect(screen.getByText(POSITIONS_PAGE_INTRO)).toBeInTheDocument()
    const notice = screen.getByRole('region', { name: 'What this run is' })
    expect(notice).toHaveTextContent('A diagnostic run, not a strategy result.')
    expect(notice).toHaveTextContent('diagnostic run of the milestone-3 reference strategy')
    expect(notice).toHaveTextContent('on the development split')
    expect(notice).toHaveTextContent('made to exercise the engine')
    expect(notice).toHaveTextContent('It carries no P&L, NAV, return or Sharpe ratio')
    expect(screen.getByRole('region', { name: 'Data sources and terms' })).toBeInTheDocument()
  })

  it('while loading, shows progress text, no chart and no vendor in the data notice', () => {
    render(<PositionsPage state={{ status: 'loading' }} />)
    expect(screen.getByText('Loading the exported positions…')).toBeInTheDocument()
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.queryByText(/OptionsDX/)).not.toBeInTheDocument()
  })

  it('on a load failure, shows the reason and the command that regenerates the data, and no chart', () => {
    const error = new DataLoadError('fetch', './data/positions_timeline.json answered HTTP 404')
    render(<PositionsPage state={{ status: 'error', error }} />)
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('./data/positions_timeline.json answered HTTP 404')
    expect(alert).toHaveTextContent('uv run python tools/export_app_data.py')
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })

  it('names the strategy and the split the file says, in its notice', () => {
    render(<PositionsPage state={ready()} />)
    expect(screen.getByRole('region', { name: 'What this run is' })).toHaveTextContent(
      'diagnostic run of the milestone-3 reference strategy (RollingShortStraddle) on the development split',
    )
  })

  it('does not call a run diagnostic when the file says it is a trial', () => {
    render(<PositionsPage state={ready((d) => void (d.run.run_purpose = 'trial'))} />)
    const notice = screen.getByRole('region', { name: 'What this run is' })
    expect(notice).toHaveTextContent('Records of an engine run, not a strategy result.')
    expect(notice).toHaveTextContent('marks the run as a trial run of RollingShortStraddle on the development split, not as a diagnostic one')
    expect(notice).toHaveTextContent('It carries no P&L, NAV, return or Sharpe ratio')
  })
})

describe('PositionsPage: the timeline', () => {
  it('draws one bar for each position, in file order from the top', () => {
    render(<PositionsPage state={ready()} />)
    expect(bars().map((b) => b.getAttribute('data-position'))).toEqual(['1', '2', '3', '4'])
    const tops = bars().map((b) => num(b, 'y'))
    expect([...tops].sort((a, b) => a - b)).toEqual(tops)
    expect(new Set(tops).size).toBe(4)
  })

  it('places each bar from the day the position opened to the day it closed, on one time scale', () => {
    render(<PositionsPage state={ready()} />)
    // Opened 01-02, 01-09, 02-20, 03-06; closed 01-16, 02-20, 03-06, never. The scale is linear in days.
    const x = [1, 2, 3, 4].map((id) => num(bar(id), 'x'))
    expect(x[0]).toBeLessThan(x[1])
    expect(x[1]).toBeLessThan(x[2])
    expect(x[2]).toBeLessThan(x[3])
    // Position 2 closes the day position 3 opens, and position 3 the day position 4 opens.
    expect(right(bar(2))).toBeCloseTo(x[2], 6)
    expect(right(bar(3))).toBeCloseTo(x[3], 6)
    // 14 days against 42: the second bar is three times as long as the first.
    expect(num(bar(2), 'width') / num(bar(1), 'width')).toBeCloseTo(3, 6)
  })

  it('puts the first day of the sample at the left label and the last day at the right label, whatever the span', () => {
    for (const [start, end] of [
      ['2015-03-19', '2015-03-20'],
      ['2015-03-16', '2015-03-20'],
    ]) {
      const { unmount } = render(
        <PositionsPage
          state={ready((d) => {
            d.run.sample_start = start
            d.run.sample_end = end
            d.dates = [start, end]
            d.open_count = [1, 0]
            d.positions = [d.positions[0]]
            d.positions[0].opened = start
            d.positions[0].closed = end
          })}
        />,
      )
      expect(num(bar(1), 'x')).toBeCloseTo(num(within(timeline()).getByText(start), 'x'), 6)
      expect(right(bar(1))).toBeCloseTo(num(within(timeline()).getByText(end), 'x'), 6)
      unmount()
    }
  })

  it('draws a one-day sample without a division by zero', () => {
    render(
      <PositionsPage
        state={ready((d) => {
          d.run.sample_start = '2015-03-20'
          d.run.sample_end = '2015-03-20'
          d.dates = ['2015-03-20']
          d.open_count = [0]
          d.positions = [d.positions[0]]
          d.positions[0].opened = '2015-03-20'
          d.positions[0].closed = '2015-03-20'
        })}
      />,
    )
    expect(Number.isFinite(num(bar(1), 'x'))).toBe(true)
    expect(Number.isFinite(num(bar(1), 'width'))).toBe(true)
  })

  it('colours each bar by its exit reason', () => {
    render(<PositionsPage state={ready()} />)
    expect(bar(1)).toHaveAttribute('fill', EXIT_REASON_COLOR.dte)
    expect(bar(2)).toHaveAttribute('fill', EXIT_REASON_COLOR.expiry)
    expect(bar(3)).toHaveAttribute('fill', EXIT_REASON_COLOR.assignment)
    expect(new Set([EXIT_REASON_COLOR.dte, EXIT_REASON_COLOR.expiry, EXIT_REASON_COLOR.assignment]).size).toBe(3)
  })

  it('gives every exit reason its own colour', () => {
    expect(new Set(Object.values(EXIT_REASON_COLOR)).size).toBe(10)
    expect(Object.keys(EXIT_REASON_TEXT)).toEqual(Object.keys(EXIT_REASON_COLOR))
  })

  it('draws a position with no close date to the end of the sample, dashed, and marks it open', () => {
    render(<PositionsPage state={ready()} />)
    const open = bar(4)
    expect(open).toHaveAttribute('fill', OPEN_POSITION_COLOR)
    expect(open).toHaveAttribute('stroke-dasharray')
    expect(open).toHaveAttribute('fill-opacity', '0.35')
    // Closed bars are solid.
    for (const id of [1, 2, 3]) {
      expect(bar(id)).not.toHaveAttribute('stroke-dasharray')
      expect(bar(id)).toHaveAttribute('fill-opacity', '1')
    }
    // It ends where a position closed on the last day of the sample would.
    const mark = within(timeline()).getByText('open')
    expect(mark.tagName.toLowerCase()).toBe('text')
    expect(num(mark, 'x')).toBeGreaterThan(right(open))
  })

  it('ends a position with no close date where a position closed on the sample’s last day ends', () => {
    render(
      <PositionsPage
        state={ready((d) => {
          d.positions[2].closed = '2015-03-20'
          d.open_count = [1, 2, 1, 1, 1, 1, 1, 1, 1, 2, 2, 1]
        })}
      />,
    )
    expect(right(bar(4))).toBeCloseTo(right(bar(3)), 6)
  })

  it('gives a position opened and closed on one day a bar you can see', () => {
    render(
      <PositionsPage
        state={ready((d) => {
          d.positions[0].closed = d.positions[0].opened
          d.open_count = [0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
        })}
      />,
    )
    expect(num(bar(1), 'width')).toBe(1.5)
  })

  it('marks an unclosed position of a ruined run by its reason, in its reason’s colour, still dashed', () => {
    render(
      <PositionsPage
        state={ready((d) => {
          d.run.status = 'ruin'
          d.positions[3].exit_reason = 'ruin'
        })}
      />,
    )
    expect(bar(4)).toHaveAttribute('fill', EXIT_REASON_COLOR.ruin)
    expect(bar(4)).toHaveAttribute('stroke-dasharray')
    expect(within(timeline()).getByText('ruin')).toBeInTheDocument()
    expect(within(timeline()).queryByText('open')).not.toBeInTheDocument()
  })

  it('describes a ruined run by its positions with no close date, whatever their exit reason', () => {
    render(<PositionsPage state={ready(ruinedRun)} />)
    // Positions 3 and 4 were still held when the run ended in ruin: no close date, and the exit reason ruin, not null.
    expect(timeline()).toHaveAccessibleDescription(/2 of them have no close date and are drawn to 2015-03-20, dashed\./)
    expect([3, 4].map((id) => bar(id).hasAttribute('stroke-dasharray'))).toEqual([true, true])
    expect([1, 2].map((id) => bar(id).hasAttribute('stroke-dasharray'))).toEqual([false, false])
  })

  it('has a hover title on every bar saying what the position was', () => {
    render(<PositionsPage state={ready()} />)
    expect(bar(1).querySelector('title')).toHaveTextContent('Position 1, short_straddle: opened 2015-01-02, closed 2015-01-16, exit reason dte')
    expect(bar(4).querySelector('title')).toHaveTextContent(
      'Position 4, short_straddle: opened 2015-03-06, no close date (drawn to the end of the sample), open',
    )
  })

  it('describes the chart for a screen reader: what the bars are, the dates, and how many have no close date', () => {
    render(<PositionsPage state={ready()} />)
    const chart = timeline()
    expect(chart).toHaveAccessibleName('When each position was open')
    expect(chart).toHaveAccessibleDescription(/4 positions from 2015-01-02 to 2015-03-20, one bar each, in the order they were opened, top to bottom\./)
    expect(chart).toHaveAccessibleDescription(/coloured by its exit reason/)
    expect(chart).toHaveAccessibleDescription(/1 of them have no close date and are drawn to 2015-03-20, dashed\./)
  })

  it('says nothing about open positions in the description when every position closed', () => {
    render(<PositionsPage state={ready(closeLastPosition)} />)
    expect(timeline()).not.toHaveAccessibleDescription(/no close date/)
  })

  it('labels the first and last day of the sample', () => {
    render(<PositionsPage state={ready()} />)
    expect(within(timeline()).getByText('2015-01-02')).toBeInTheDocument()
    expect(within(timeline()).getByText('2015-03-20')).toBeInTheDocument()
  })

  it('puts a tick on January 1st of a year inside a longer sample, and thins them to about eight', () => {
    render(
      <PositionsPage
        state={ready((d) => {
          d.run.sample_start = '2010-01-04'
          d.run.sample_end = '2019-12-31'
          d.dates = ['2010-01-04', '2019-12-31']
          d.open_count = [1, 0]
          d.positions = [d.positions[0]]
          d.positions[0].opened = '2010-01-04'
          d.positions[0].closed = '2019-12-31'
        })}
      />,
    )
    // 2011 to 2019 is nine years: every second one, from 2011.
    const years = [...timeline().querySelectorAll('text')].map((t) => t.textContent ?? '').filter((t) => /^\d{4}$/.test(t))
    expect(years).toEqual(['2011', '2013', '2015', '2017', '2019'])
  })

  it('draws all eight ticks of an eight-year span, and no fewer', () => {
    render(
      <PositionsPage
        state={ready((d) => {
          d.run.sample_start = '2010-01-04'
          d.run.sample_end = '2018-12-31'
          d.dates = ['2010-01-04', '2018-12-31']
          d.open_count = [1, 0]
          d.positions = [d.positions[0]]
          d.positions[0].opened = '2010-01-04'
          d.positions[0].closed = '2018-12-31'
        })}
      />,
    )
    const years = [...timeline().querySelectorAll('text')].map((t) => t.textContent ?? '').filter((t) => /^\d{4}$/.test(t))
    expect(years).toEqual(['2011', '2012', '2013', '2014', '2015', '2016', '2017', '2018'])
  })

  it('draws no year tick inside a sample that stays within one year', () => {
    render(<PositionsPage state={ready()} />)
    const years = [...timeline().querySelectorAll('text')].map((t) => t.textContent ?? '').filter((t) => /^\d{4}$/.test(t))
    expect(years).toEqual([])
  })

  it('draws every year of a shorter span, one tick each', () => {
    render(
      <PositionsPage
        state={ready((d) => {
          d.run.sample_end = '2018-12-31'
          d.run.sample_start = '2015-01-02'
          d.dates = ['2015-01-02', '2018-12-31']
          d.open_count = [1, 0]
          d.positions = [d.positions[0]]
          d.positions[0].closed = '2018-12-31'
        })}
      />,
    )
    const years = [...timeline().querySelectorAll('text')].map((t) => t.textContent ?? '').filter((t) => /^\d{4}$/.test(t))
    expect(years).toEqual(['2016', '2017', '2018'])
  })
})

describe('PositionsPage: the legend', () => {
  const legend = () => screen.getByRole('list', { name: 'Exit reasons' })

  it('lists each exit reason of the file with what it means and how many positions had it, in the order of the spec', () => {
    render(<PositionsPage state={ready()} />)
    const items = within(legend()).getAllByRole('listitem')
    expect(items.map((li) => li.textContent)).toEqual([
      'dte: closed by the days-to-expiry rule (1)',
      'expiry: held to expiry (1)',
      'assignment: assigned (1)',
      'open: no close date, drawn to the end of the sample (1)',
    ])
  })

  it('gives each entry the colour of its bars', () => {
    render(<PositionsPage state={ready()} />)
    const swatches = [...legend().querySelectorAll<HTMLElement>('.swatch')]
    expect(swatches.map((s) => s.style.background)).toEqual([EXIT_REASON_COLOR.dte, EXIT_REASON_COLOR.expiry, EXIT_REASON_COLOR.assignment, ''])
    expect(swatches[3]).toHaveClass('open')
    // The swatches are decoration: the text beside each one is the entry.
    for (const s of swatches) expect(s).toHaveAttribute('aria-hidden', 'true')
  })

  it('counts positions that share a reason, and leaves out the reasons the file does not use', () => {
    render(
      <PositionsPage
        state={ready((d) => {
          d.positions[1].exit_reason = 'dte'
          d.positions[3].closed = '2015-03-13'
          d.positions[3].exit_reason = 'stop'
          d.open_count = [1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0]
        })}
      />,
    )
    const items = within(legend()).getAllByRole('listitem').map((li) => li.textContent)
    expect(items).toEqual(['dte: closed by the days-to-expiry rule (2)', 'assignment: assigned (1)', 'stop: stop loss (1)'])
  })

  it('lists the unclosed positions of a ruined run under ruin, and has no “open” entry', () => {
    render(<PositionsPage state={ready(ruinedRun)} />)
    const items = within(legend()).getAllByRole('listitem').map((li) => li.textContent)
    expect(items).toEqual(['dte: closed by the days-to-expiry rule (1)', 'expiry: held to expiry (1)', 'ruin: ruin (2)'])
    expect(legend().querySelector('.swatch.open')).toBeNull()
  })

  it('has no “open” entry when every position closed', () => {
    render(<PositionsPage state={ready(closeLastPosition)} />)
    expect(within(legend()).queryByText(/^open/)).not.toBeInTheDocument()
    expect(legend().querySelector('.swatch.open')).toBeNull()
  })
})

describe('PositionsPage: positions open at each close', () => {
  const figure = () => screen.getByRole('figure', { name: 'Positions open at each close' })
  const points = (): number[][] =>
    (figure().querySelector('polyline')?.getAttribute('points') ?? '').split(' ').map((p) => p.split(',').map(Number))

  it('draws open_count with the line chart, one point per session', () => {
    render(<PositionsPage state={ready()} />)
    expect(points()).toHaveLength(12)
    // The second session has two positions open, the most: its point is the highest (smallest y), the others share one height.
    const ys = points().map((p) => p[1])
    expect(ys[1]).toBe(Math.min(...ys))
    expect(new Set(ys.filter((_, i) => i !== 1)).size).toBe(1)
    expect(ys[0]).toBeGreaterThan(ys[1])
  })

  it('puts the sessions left to right, evenly', () => {
    render(<PositionsPage state={ready()} />)
    const xs = points().map((p) => p[0])
    expect([...xs].sort((a, b) => a - b)).toEqual(xs)
    expect(new Set(xs).size).toBe(12)
  })

  it('names the unit on the axis as the file gives it, and describes the chart', () => {
    render(<PositionsPage state={ready()} />)
    expect(within(figure()).getByText("positions open at the session's close")).toBeInTheDocument()
    expect(figure()).toHaveAccessibleDescription(/12 sessions, 2015-01-02 to 2015-03-20, left to right\./)
    expect(figure()).toHaveAccessibleDescription(/One point per session of the run, oldest on the left\./)
  })

  it('labels the chart with a heading', () => {
    render(<PositionsPage state={ready()} />)
    expect(screen.getByRole('heading', { level: 3, name: 'Positions open at each close' })).toBeInTheDocument()
  })

  it('draws a run with no position open at any close', () => {
    render(
      <PositionsPage
        state={ready((d) => {
          // One position opened and closed on one day is open at no close.
          d.positions = [d.positions[0]]
          d.positions[0].closed = d.positions[0].opened
          d.open_count = d.open_count.map(() => 0)
        })}
      />,
    )
    expect(points()).toHaveLength(12)
  })
})

describe('PositionsPage: the table of positions', () => {
  const table = () => screen.getByRole('table', { name: 'Positions' })

  it('lists each position with its dates, its exit reason and its legs', () => {
    render(<PositionsPage state={ready()} />)
    const rows = cells(table())
    expect(rows[0]).toEqual(['Position', 'Structure', 'Opened', 'Closed', 'Exit reason', 'Legs'])
    expect(rows).toHaveLength(5)
    expect(rows[1]).toEqual([
      '1',
      'short_straddle',
      '2015-01-02',
      '2015-01-16',
      'dte',
      'SPY   150123C00205000 × -1SPY   150123P00205000 × -1',
    ])
    expect(rows[2].slice(0, 5)).toEqual(['2', 'short_straddle', '2015-01-09', '2015-02-20', 'expiry'])
    expect(rows[3].slice(0, 5)).toEqual(['3', 'short_straddle', '2015-02-20', '2015-03-06', 'assignment'])
  })

  it('says “no close date” and “open” for a position the sample ended on', () => {
    render(<PositionsPage state={ready()} />)
    expect(cells(table())[4].slice(0, 5)).toEqual(['4', 'short_straddle', '2015-03-06', 'no close date', 'open'])
  })

  it('shows a long leg with a plus sign and several legs one under another', () => {
    render(
      <PositionsPage
        state={ready((d) => {
          d.positions[0].legs = [
            { osi_symbol: 'SPY   150123C00205000', ratio: 2 },
            { osi_symbol: 'SPY   150123P00200000', ratio: -1 },
            { osi_symbol: 'SPY   150123P00195000', ratio: 1 },
          ]
        })}
      />,
    )
    const legs = within(table()).getAllByRole('row')[1].querySelectorAll('li')
    expect([...legs].map((li) => li.textContent)).toEqual(['SPY   150123C00205000 × +2', 'SPY   150123P00200000 × -1', 'SPY   150123P00195000 × +1'])
  })

  it('gives the table column headers and a header cell on each row', () => {
    render(<PositionsPage state={ready()} />)
    expect(within(table()).getAllByRole('columnheader')).toHaveLength(6)
    expect(within(table()).getAllByRole('rowheader')).toHaveLength(4)
  })

  it('shows each unit as the file gives it', () => {
    render(<PositionsPage state={ready()} />)
    const units = (screen.getByRole('heading', { name: 'The positions' }).closest('.card') as HTMLElement).querySelector('dl') as HTMLElement
    expect([...units.querySelectorAll('dt')].map((dt) => [dt.textContent, dt.nextElementSibling?.textContent])).toEqual([
      ['open_count', "positions open at the session's close"],
      ['ratio', 'contracts per package, signed: + long, - short'],
    ])
  })

  it('names the run that made the file', () => {
    render(<PositionsPage state={ready()} />)
    const meta = (screen.getByRole('heading', { name: 'Where these numbers come from' }).closest('.card') as HTMLElement).querySelector('dl') as HTMLElement
    expect(within(meta).getByText('Run').nextElementSibling).toHaveTextContent(positionsTimelineFixture.run.run_id)
    expect(within(meta).getByText('Dates').nextElementSibling).toHaveTextContent('2015-01-02 to 2015-03-20')
    expect(within(meta).getByText('Schema version').nextElementSibling).toHaveTextContent('0.4.0')
    expect(screen.getByText(positionsTimelineFixture.label)).toBeInTheDocument()
  })
})

describe('PositionsPage: a file with no positions', () => {
  it('says so instead of drawing an empty chart and an empty table, and still draws the count', () => {
    render(<PositionsPage state={ready((d) => ((d.positions = []), (d.open_count = d.open_count.map(() => 0))))} />)
    expect(screen.getAllByText(NO_POSITIONS)).toHaveLength(2)
    expect(screen.queryByRole('img', { name: 'When each position was open' })).not.toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Exit reasons' })).not.toBeInTheDocument()
    expect(screen.getByRole('figure', { name: 'Positions open at each close' })).toBeInTheDocument()
  })
})

/** The fixture with `n` positions, a day apart in sessions, each one session long. */
function longFile(n: number) {
  return ready((d) => {
    const days: string[] = []
    for (let t = Date.parse('2015-01-02T00:00:00Z'); days.length < n + 1; t += 86_400_000) {
      const day = new Date(t)
      if (day.getUTCDay() !== 0 && day.getUTCDay() !== 6) days.push(day.toISOString().slice(0, 10))
    }
    d.run.sample_end = days[days.length - 1]
    d.dates = [days[0], days[days.length - 1]]
    d.open_count = [1, 0]
    d.positions = days.slice(0, n).map((opened, i) => ({ ...d.positions[0], position_id: i + 1, opened, closed: days[i + 1], legs: d.positions[0].legs }))
  })
}

describe('PositionsPage: a long file', () => {
  const rowCount = (): number => within(screen.getByRole('table', { name: 'Positions' })).getAllByRole('row').length - 1

  it('draws every bar but shows the first rows of the table and a button for the next ones', () => {
    render(<PositionsPage state={longFile(ROW_STEP + 30)} />)
    expect(bars()).toHaveLength(ROW_STEP + 30)
    expect(rowCount()).toBe(ROW_STEP)
    expect(screen.getByText(/250 of 280 rows shown\./)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show 30 more' }))
    expect(rowCount()).toBe(ROW_STEP + 30)
    expect(screen.queryByRole('button', { name: /Show .* more/ })).not.toBeInTheDocument()
  })
})

describe('PositionsPage: the data notice', () => {
  const notice = () => screen.getByRole('region', { name: 'Data sources and terms' })

  it('names OptionsDX for an OptionsDX file, says no quote or price is shown, and carries no DoltHub attribution', () => {
    render(<PositionsPage state={ready()} />)
    expect(notice()).toHaveTextContent('named from OptionsDX end-of-day option quotes')
    expect(notice()).toHaveTextContent('dudesurfin/spy-options-eod-volatility-surface-2010-2023')
    expect(notice()).toHaveTextContent('the page shows no quote and no price')
    expect(notice()).toHaveTextContent("The data is not covered by this repository's MIT licence.")
    expect(notice()).not.toHaveTextContent('DoltHub')
    expect(within(notice()).queryByRole('link', { name: 'CC BY-SA 4.0' })).not.toBeInTheDocument()
  })

  it('names DoltHub for a DoltHub file, and carries the CC BY-SA 4.0 attribution', () => {
    render(<PositionsPage state={ready((d) => void (d.run.data_source = 'dolthub'))} />)
    expect(notice()).toHaveTextContent('named from the SPY option quotes of the DoltHub database post-no-preference/options')
    expect(notice()).toHaveTextContent('Contains information derived from the DoltHub database')
    expect(notice()).toHaveTextContent('no quote row and no price is reproduced')
    expect(within(notice()).getByRole('link', { name: 'CC BY-SA 4.0' })).toHaveAttribute('href', 'https://creativecommons.org/licenses/by-sa/4.0/')
    expect(notice()).not.toHaveTextContent('OptionsDX')
  })
})
