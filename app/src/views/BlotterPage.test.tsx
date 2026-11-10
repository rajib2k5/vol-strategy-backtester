import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { BlotterPage } from './BlotterPage'
import { ROW_STEP } from './rowLimit'
import { DataLoadError } from '../data/loadAppData'
import { parseBlotter, parseDataQuality, parseIllustrativeSurface, parseManifest, parsePositionsTimeline, parseSurfaceFrames } from '../lib/contract'
import { BLOTTER_PAGE_INTRO, NO_EVENTS_MATCH, NO_FILLS_MATCH } from '../content/blotter'
import manifestFixture from '../test/fixtures/manifest.json'
import surfaceFixture from '../test/fixtures/illustrative_surface.json'
import dataQualityFixture from '../test/fixtures/data_quality.json'
import surfaceFramesFixture from '../test/fixtures/surface_frames.json'
import blotterFixture from '../test/fixtures/blotter.json'
import positionsTimelineFixture from '../test/fixtures/positions_timeline.json'

type Obj = Record<string, unknown>
type Doc = Obj & { run: Obj; fills: Obj[]; events: Obj[] }
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T

/** The page's state with the blotter fixture after `edit`, parsed (so a test cannot feed the page something the contract refuses). */
function ready(edit: (d: Doc) => void = () => {}) {
  const d = clone(blotterFixture) as unknown as Doc
  edit(d)
  return {
    status: 'ready' as const,
    data: {
      manifest: parseManifest(manifestFixture),
      surface: parseIllustrativeSurface(surfaceFixture),
      dataQuality: parseDataQuality(dataQualityFixture),
      surfaceFrames: parseSurfaceFrames(surfaceFramesFixture),
      blotter: parseBlotter(d),
      positionsTimeline: parsePositionsTimeline(positionsTimelineFixture),
    },
  }
}

/** The rows of a table as arrays of cell texts, header row first. */
function cells(table: HTMLElement): string[][] {
  return within(table)
    .getAllByRole('row')
    .map((row) => [...row.children].map((c) => c.textContent ?? ''))
}

const fills = () => screen.getByRole('table', { name: 'Fills' })
const events = () => screen.getByRole('table', { name: 'Expiry events' })
/** The ids of the fills the table shows, in order. */
const fillIds = (): string[] => cells(fills()).slice(1).map((r) => r[0])
const status = () => screen.getByRole('status')

describe('BlotterPage: states', () => {
  it.each([
    ['loading', { status: 'loading' as const }],
    ['error', { status: 'error' as const, error: new Error('x') }],
    ['ready', ready()],
  ])('always shows its heading, what the page is for and the notice that this is no result while %s', (_name, state) => {
    render(<BlotterPage state={state} />)
    expect(screen.getByRole('heading', { level: 2, name: 'Blotter' })).toBeInTheDocument()
    expect(screen.getByText(BLOTTER_PAGE_INTRO)).toBeInTheDocument()
    const notice = screen.getByRole('region', { name: 'What this run is' })
    expect(notice).toHaveTextContent('A diagnostic run, not a strategy result.')
    expect(notice).toHaveTextContent('diagnostic run of the milestone-3 reference strategy')
    expect(notice).toHaveTextContent('on the development split')
    expect(notice).toHaveTextContent('made to exercise the engine')
    expect(notice).toHaveTextContent('It carries no P&L, NAV, return or Sharpe ratio')
    expect(screen.getByRole('region', { name: 'Data sources and terms' })).toBeInTheDocument()
  })

  it('while loading, shows progress text, no table and no vendor in the data notice', () => {
    render(<BlotterPage state={{ status: 'loading' }} />)
    expect(screen.getByText('Loading the exported blotter…')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.queryByText(/OptionsDX/)).not.toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'Filters' })).not.toBeInTheDocument()
  })

  it('on a load failure, shows the reason and the command that regenerates the data, and no table', () => {
    const error = new DataLoadError('fetch', './data/blotter.json answered HTTP 404')
    render(<BlotterPage state={{ status: 'error', error }} />)
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('./data/blotter.json answered HTTP 404')
    expect(alert).toHaveTextContent('uv run python tools/export_app_data.py')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.queryByText(/OptionsDX/)).not.toBeInTheDocument()
  })

  it('names the strategy and the split the file says, in its notice', () => {
    render(<BlotterPage state={ready()} />)
    expect(screen.getByRole('region', { name: 'What this run is' })).toHaveTextContent(
      'diagnostic run of the milestone-3 reference strategy (RollingShortStraddle) on the development split',
    )
  })

  it('does not call a run diagnostic when the file says it is a trial, and says what the file says', () => {
    render(
      <BlotterPage
        state={ready((d) => {
          d.run.run_purpose = 'trial'
          d.run.split = 'validation'
        })}
      />,
    )
    const notice = screen.getByRole('region', { name: 'What this run is' })
    expect(notice).toHaveTextContent('Records of an engine run, not a strategy result.')
    expect(notice).toHaveTextContent('marks the run as a trial run of RollingShortStraddle on the validation split, not as a diagnostic one')
    expect(notice).toHaveTextContent('It carries no P&L, NAV, return or Sharpe ratio')
    expect(notice).not.toHaveTextContent('made to exercise the engine')
    expect(screen.queryByText('A diagnostic run, not a strategy result.')).not.toBeInTheDocument()
  })
})

describe('BlotterPage: the tables', () => {
  it('lists every fill in file order, each number formatted with the file’s decimals and shown with its sign', () => {
    render(<BlotterPage state={ready()} />)
    const rows = cells(fills())
    expect(rows[0]).toEqual(['Fill', 'Date', 'Instrument', 'Contract', 'Qty', 'Price', 'Mid', 'Half-spread', 'Fees', 'Source', 'Intent'])
    expect(rows).toHaveLength(14)
    expect(rows[1]).toEqual(['1', '2015-01-02', 'option', 'SPY   150123C00205000', '-10', '3.1200', '3.1450', '0.0250', '7.00', 'quote', 'open'])
    expect(rows[5]).toEqual(['5', '2015-01-16', 'option', 'SPY   150123C00205000', '+10', '1.0500', '1.0250', '0.0250', '7.00', 'quote', 'close'])
    // A share fill has no contract, mid or half-spread: a dash, never a zero.
    expect(rows[9]).toEqual(['9', '2015-02-23', 'share', '—', '+1,000', '205.2500', '—', '—', '10.00', 'close', 'share_liquidation'])
    expect(fillIds()).toEqual(['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13'])
  })

  it('puts a plus sign on a bought quantity of 1 as on any other, and none on a delivery of 0', () => {
    render(<BlotterPage state={ready((d) => void (d.fills[4].qty = 1))} />)
    expect(cells(fills())[5][4]).toBe('+1')
    expect(cells(events())[2][6]).toBe('0')
  })

  it('lists every expiry event, with the day it books on, and a dash where an early event has no settlement price', () => {
    render(<BlotterPage state={ready()} />)
    const rows = cells(events())
    expect(rows[0]).toEqual(['Event', 'Date', 'Books on', 'Contract', 'Type', 'Contracts', 'Shares delivered', 'Strike', 'Settlement price', 'Pin'])
    expect(rows.slice(1)).toEqual([
      ['1', '2015-02-20', '2015-02-20', 'SPY   150220C00205000', 'assigned', '-10', '-1,000', '205.0000', '205.2500', 'yes'],
      ['2', '2015-02-20', '2015-02-20', 'SPY   150220P00205000', 'expired_worthless', '-10', '0', '205.0000', '205.2500', 'yes'],
      ['3', '2015-03-05', '2015-03-06', 'SPY   150320P00207000', 'early_assigned', '-10', '+1,000', '207.0000', '—', 'no'],
    ])
  })

  it('gives every table real column headers, and every row a header cell', () => {
    render(<BlotterPage state={ready()} />)
    for (const table of [fills(), events()]) {
      expect(within(table).getAllByRole('columnheader').length).toBeGreaterThanOrEqual(10)
      expect(within(table).getAllByRole('rowheader').length).toBeGreaterThan(0)
    }
  })

  it('shows each unit as the file gives it, beside the key it belongs to', () => {
    render(<BlotterPage state={ready()} />)
    const units = (screen.getByRole('heading', { name: 'Units' }).closest('.card') as HTMLElement).querySelector('dl') as HTMLElement
    const pairs = [...units.querySelectorAll('dt')].map((dt) => [dt.textContent, dt.nextElementSibling?.textContent])
    expect(pairs).toEqual([
      ['qty', 'contracts (options) or shares (SPY), signed: + bought, - sold'],
      ['price', 'USD per share'],
      ['mid', 'USD per share'],
      ['half_spread', 'USD per share'],
      ['fees', 'USD'],
      ['strike', 'USD per share'],
      ['settlement_price', 'USD per share'],
      ['shares_delivered', 'shares, signed: + received, - delivered'],
    ])
  })

  it('names the run that made the file', () => {
    render(<BlotterPage state={ready()} />)
    const meta = (screen.getByRole('heading', { name: 'Where these numbers come from' }).closest('.card') as HTMLElement).querySelector('dl') as HTMLElement
    const value = (term: string) => within(meta).getByText(term).nextElementSibling
    expect(value('Run')).toHaveTextContent(blotterFixture.run.run_id)
    expect(value('Strategy')).toHaveTextContent('RollingShortStraddle')
    expect(value('Purpose')).toHaveTextContent('diagnostic')
    expect(value('Split')).toHaveTextContent('development')
    expect(value('Status')).toHaveTextContent('ok')
    expect(value('Data source')).toHaveTextContent('optionsdx')
    expect(value('Execution')).toHaveTextContent('quote, fills at next close, caps hard only, chain mask none')
    expect(value('Dates')).toHaveTextContent('2015-01-02 to 2015-03-20')
    expect(value('Engine commit')).toHaveTextContent(blotterFixture.run.engine_commit)
    expect(value('Configuration')).toHaveTextContent(blotterFixture.run.config_hash)
    expect(value('Inputs')).toHaveTextContent(blotterFixture.run.data_fingerprint)
    expect(value('Schema version')).toHaveTextContent('0.4.0')
    expect(screen.getByText(blotterFixture.label)).toBeInTheDocument()
  })

  it('shows no P&L, NAV, return or Sharpe anywhere on the page', () => {
    render(<BlotterPage state={ready()} />)
    const headers = screen.getAllByRole('columnheader').map((h) => h.textContent)
    expect(headers.join(' ')).not.toMatch(/p&l|pnl|nav\b|return|sharpe/i)
  })
})

describe('BlotterPage: the filters', () => {
  const intent = () => screen.getByLabelText('Intent')
  const source = () => screen.getByLabelText('Fill source')
  const from = () => screen.getByLabelText('From')
  const to = () => screen.getByLabelText('To')

  it('has a labelled control for each filter, in one group', () => {
    render(<BlotterPage state={ready()} />)
    const group = screen.getByRole('group', { name: 'Filters' })
    for (const control of [intent(), source(), from(), to()]) expect(group).toContainElement(control)
    expect(intent().tagName).toBe('SELECT')
    expect(source().tagName).toBe('SELECT')
    expect(from()).toHaveAttribute('type', 'date')
    expect(to()).toHaveAttribute('type', 'date')
  })

  it('offers only the intents and the sources the file has, after “all”', () => {
    render(<BlotterPage state={ready()} />)
    expect([...(intent() as HTMLSelectElement).options].map((o) => o.value)).toEqual(['all', 'open', 'close', 'reduce_risk', 'share_liquidation'])
    expect([...(source() as HTMLSelectElement).options].map((o) => o.value)).toEqual(['all', 'quote', 'close'])
  })

  it('offers surface when the file has a surface-priced fill', () => {
    render(<BlotterPage state={ready((d) => void (d.fills[0].fill_source = 'surface'))} />)
    expect([...(source() as HTMLSelectElement).options].map((o) => o.value)).toEqual(['all', 'quote', 'surface', 'close'])
  })

  it('limits the date pickers to the run’s sample', () => {
    render(<BlotterPage state={ready()} />)
    for (const picker of [from(), to()]) {
      expect(picker).toHaveAttribute('min', '2015-01-02')
      expect(picker).toHaveAttribute('max', '2015-03-20')
    }
  })

  it('starts with everything shown, and says how many of how many', () => {
    render(<BlotterPage state={ready()} />)
    expect(status()).toHaveTextContent('Showing 13 of 13 fills and 3 of 3 events.')
    expect(screen.getByRole('button', { name: 'Clear filters' })).toBeDisabled()
  })

  it('filters by intent', () => {
    render(<BlotterPage state={ready()} />)
    fireEvent.change(intent(), { target: { value: 'close' } })
    expect(fillIds()).toEqual(['5', '6'])
    expect(status()).toHaveTextContent('Showing 2 of 13 fills and 3 of 3 events.')
    fireEvent.change(intent(), { target: { value: 'share_liquidation' } })
    expect(fillIds()).toEqual(['9', '11'])
    fireEvent.change(intent(), { target: { value: 'open' } })
    expect(fillIds()).toEqual(['1', '2', '3', '4', '7', '8', '12', '13'])
    fireEvent.change(intent(), { target: { value: 'all' } })
    expect(fillIds()).toHaveLength(13)
  })

  it('filters by fill source', () => {
    render(<BlotterPage state={ready()} />)
    fireEvent.change(source(), { target: { value: 'close' } })
    expect(fillIds()).toEqual(['9', '11'])
    fireEvent.change(source(), { target: { value: 'quote' } })
    expect(fillIds()).toHaveLength(11)
    expect(fillIds()).not.toContain('9')
  })

  it('filters by surface-priced fills', () => {
    render(<BlotterPage state={ready((d) => void (d.fills[3].fill_source = 'surface'))} />)
    fireEvent.change(source(), { target: { value: 'surface' } })
    expect(fillIds()).toEqual(['4'])
  })

  it('filters by a date range, both ends included', () => {
    render(<BlotterPage state={ready()} />)
    fireEvent.change(from(), { target: { value: '2015-01-09' } })
    expect(fillIds()).toEqual(['3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13'])
    fireEvent.change(to(), { target: { value: '2015-01-16' } })
    expect(fillIds()).toEqual(['3', '4', '5', '6'])
    expect(status()).toHaveTextContent('Showing 4 of 13 fills and 0 of 3 events.')
    fireEvent.change(from(), { target: { value: '' } })
    expect(fillIds()).toEqual(['1', '2', '3', '4', '5', '6'])
  })

  it('applies the date range to the events too, and the other filters to the fills only', () => {
    render(<BlotterPage state={ready()} />)
    expect(cells(events())).toHaveLength(4)
    fireEvent.change(intent(), { target: { value: 'close' } })
    fireEvent.change(source(), { target: { value: 'quote' } })
    expect(cells(events())).toHaveLength(4)
    fireEvent.change(from(), { target: { value: '2015-03-01' } })
    expect(cells(events()).slice(1).map((r) => r[0])).toEqual(['3'])
    fireEvent.change(from(), { target: { value: '' } })
    fireEvent.change(to(), { target: { value: '2015-02-20' } })
    expect(cells(events()).slice(1).map((r) => r[0])).toEqual(['1', '2'])
  })

  it('combines the filters', () => {
    render(<BlotterPage state={ready()} />)
    fireEvent.change(intent(), { target: { value: 'open' } })
    fireEvent.change(source(), { target: { value: 'quote' } })
    fireEvent.change(from(), { target: { value: '2015-02-21' } })
    fireEvent.change(to(), { target: { value: '2015-03-06' } })
    expect(fillIds()).toEqual(['12', '13'])
    expect(status()).toHaveTextContent('Showing 2 of 13 fills and 1 of 3 events.')
  })

  it('says so when no fill matches, and keeps the events table when only the fills are empty', () => {
    render(<BlotterPage state={ready()} />)
    fireEvent.change(intent(), { target: { value: 'close' } })
    fireEvent.change(source(), { target: { value: 'close' } })
    expect(screen.getByText(NO_FILLS_MATCH)).toBeInTheDocument()
    expect(screen.queryByRole('table', { name: 'Fills' })).not.toBeInTheDocument()
    expect(events()).toBeInTheDocument()
  })

  it('says so when no event falls in the range', () => {
    render(<BlotterPage state={ready()} />)
    fireEvent.change(to(), { target: { value: '2015-01-30' } })
    expect(screen.getByText(NO_EVENTS_MATCH)).toBeInTheDocument()
    expect(screen.queryByRole('table', { name: 'Expiry events' })).not.toBeInTheDocument()
    expect(fills()).toBeInTheDocument()
  })

  it('shows nothing for a range that ends before it starts', () => {
    render(<BlotterPage state={ready()} />)
    fireEvent.change(from(), { target: { value: '2015-03-01' } })
    fireEvent.change(to(), { target: { value: '2015-01-15' } })
    expect(screen.getByText(NO_FILLS_MATCH)).toBeInTheDocument()
    expect(screen.getByText(NO_EVENTS_MATCH)).toBeInTheDocument()
    expect(status()).toHaveTextContent('Showing 0 of 13 fills and 0 of 3 events.')
  })

  it('clears every filter at once', () => {
    render(<BlotterPage state={ready()} />)
    fireEvent.change(intent(), { target: { value: 'close' } })
    fireEvent.change(source(), { target: { value: 'quote' } })
    fireEvent.change(from(), { target: { value: '2015-01-09' } })
    fireEvent.change(to(), { target: { value: '2015-02-01' } })
    const clear = screen.getByRole('button', { name: 'Clear filters' })
    expect(clear).toBeEnabled()
    fireEvent.click(clear)
    expect(intent()).toHaveValue('all')
    expect(source()).toHaveValue('all')
    expect(from()).toHaveValue('')
    expect(to()).toHaveValue('')
    expect(fillIds()).toHaveLength(13)
    expect(clear).toBeDisabled()
  })

  it.each([
    ['the intent', () => fireEvent.change(screen.getByLabelText('Intent'), { target: { value: 'open' } })],
    ['the source', () => fireEvent.change(screen.getByLabelText('Fill source'), { target: { value: 'quote' } })],
    ['the first date', () => fireEvent.change(screen.getByLabelText('From'), { target: { value: '2015-01-09' } })],
    ['the last date', () => fireEvent.change(screen.getByLabelText('To'), { target: { value: '2015-03-06' } })],
  ])('enables “Clear filters” once %s is set', (_what, act) => {
    render(<BlotterPage state={ready()} />)
    act()
    expect(screen.getByRole('button', { name: 'Clear filters' })).toBeEnabled()
  })
})

/** The fixture with `n` option fills, one a day (a long file). */
function longFile(n: number) {
  return ready((d) => {
    const days: string[] = []
    for (let t = Date.parse('2015-01-02T00:00:00Z'); days.length < n; t += 86_400_000) {
      const day = new Date(t)
      if (day.getUTCDay() !== 0 && day.getUTCDay() !== 6) days.push(day.toISOString().slice(0, 10))
    }
    d.run.sample_end = days[days.length - 1]
    // A symbol that expires long after the sample, and the fills open (qty -10, intent open): nothing here closes or expires.
    d.fills = days.map((date, i) => ({ ...d.fills[0], fill_id: i + 1, date, osi_symbol: 'SPY   301215C00205000' }))
    d.events = []
  })
}

describe('BlotterPage: a long file', () => {
  it('shows the first rows and a button for the next ones', () => {
    render(<BlotterPage state={longFile(ROW_STEP + 40)} />)
    expect(fillIds()).toHaveLength(ROW_STEP)
    expect(screen.getByText(/250 of 290 rows shown\./)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show 40 more' }))
    expect(fillIds()).toHaveLength(ROW_STEP + 40)
    expect(fillIds()[ROW_STEP + 39]).toBe(String(ROW_STEP + 40))
    expect(screen.queryByRole('button', { name: /Show .* more/ })).not.toBeInTheDocument()
  })

  it('shows no button when every row fits', () => {
    render(<BlotterPage state={longFile(ROW_STEP)} />)
    expect(fillIds()).toHaveLength(ROW_STEP)
    expect(screen.queryByRole('button', { name: /Show .* more/ })).not.toBeInTheDocument()
  })

  it('starts again from the first rows when a filter changes', () => {
    render(<BlotterPage state={longFile(ROW_STEP * 2 + 10)} />)
    fireEvent.click(screen.getByRole('button', { name: 'Show 250 more' }))
    expect(fillIds()).toHaveLength(ROW_STEP * 2)
    fireEvent.change(screen.getByLabelText('Intent'), { target: { value: 'open' } })
    expect(fillIds()).toHaveLength(ROW_STEP)
  })
})

describe('BlotterPage: the data notice', () => {
  const notice = () => screen.getByRole('region', { name: 'Data sources and terms' })

  it('names OptionsDX for an OptionsDX file, with the terms of its quotes and of the SPY closes, and no DoltHub attribution', () => {
    render(<BlotterPage state={ready()} />)
    expect(notice()).toHaveTextContent('priced from OptionsDX end-of-day option quotes')
    expect(notice()).toHaveTextContent('dudesurfin/spy-options-eod-volatility-surface-2010-2023')
    expect(notice()).toHaveTextContent('never a quote row')
    expect(notice()).toHaveTextContent('SPY closes from Yahoo Finance')
    expect(notice()).toHaveTextContent("The data is not covered by this repository's MIT licence.")
    expect(within(notice()).getByRole('link', { name: 'DATA.md' })).toHaveAttribute('href', expect.stringContaining('DATA.md'))
    expect(within(notice()).getByRole('link', { name: 'data/LICENSE-DATA.md' })).toHaveAttribute('href', './data/LICENSE-DATA.md')
    expect(notice()).not.toHaveTextContent('DoltHub')
    expect(within(notice()).queryByRole('link', { name: 'CC BY-SA 4.0' })).not.toBeInTheDocument()
  })

  it('names DoltHub for a DoltHub file, and carries the CC BY-SA 4.0 attribution', () => {
    render(<BlotterPage state={ready((d) => void (d.run.data_source = 'dolthub'))} />)
    expect(notice()).toHaveTextContent('priced from the SPY option quotes of the DoltHub database post-no-preference/options')
    expect(notice()).toHaveTextContent('Contains information derived from the DoltHub database')
    expect(notice()).toHaveTextContent('no quote row is reproduced')
    expect(within(notice()).getByRole('link', { name: 'CC BY-SA 4.0' })).toHaveAttribute('href', 'https://creativecommons.org/licenses/by-sa/4.0/')
    expect(within(notice()).getByRole('link', { name: 'post-no-preference/options' })).toBeInTheDocument()
    expect(notice()).not.toHaveTextContent('OptionsDX')
  })
})
