import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { DataQualityPage } from './DataQualityPage'
import { DataLoadError } from '../data/loadAppData'
import { CALENDAR_ACTION_NAMES, FLAG_NAMES, parseDataQuality, parseIllustrativeSurface, parseManifest } from '../lib/contract'
import { BY_YEAR_NOTE, CALENDAR_ACTIONS, CHART_FLAGS, CROSSVENDOR_NOTE } from '../content/dataQuality'
import manifestFixture from '../test/fixtures/manifest.json'
import surfaceFixture from '../test/fixtures/illustrative_surface.json'
import dataQualityFixture from '../test/fixtures/data_quality.json'

const manifest = parseManifest(manifestFixture)
const surface = parseIllustrativeSurface(surfaceFixture)

type Obj = Record<string, unknown>
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T

/** The fixture with `edit` applied, parsed (so a test cannot feed the page something the contract refuses). */
type Doc = Obj & { gate: Obj & { thresholds: Record<string, unknown[]> }; cross_vendor: Obj & { within_thresholds: Record<string, unknown[]>; by_year: Record<string, unknown[]> } }
function dataQuality(edit: (d: Doc) => void = () => {}) {
  const d = clone(dataQualityFixture) as unknown as Doc
  edit(d)
  return parseDataQuality(d)
}
const ready = (dq = dataQuality()) => ({ status: 'ready' as const, data: { manifest, surface, dataQuality: dq } })

/** The rows of a table as arrays of cell texts, header row first (row-header cells included). */
function cells(table: HTMLElement): string[][] {
  return within(table)
    .getAllByRole('row')
    .map((row) => [...row.children].map((c) => c.textContent ?? ''))
}

const card = (heading: string): HTMLElement => screen.getByRole('heading', { level: 3, name: heading }).closest('.card') as HTMLElement

describe('DataQualityPage: states', () => {
  it.each([
    ['loading', { status: 'loading' as const }],
    ['error', { status: 'error' as const, error: new Error('x') }],
    ['ready', ready()],
  ])('always shows its heading and what the page is for while %s', (_name, state) => {
    render(<DataQualityPage state={state} />)
    expect(screen.getByRole('heading', { level: 2, name: 'Data quality' })).toBeInTheDocument()
    expect(screen.getByText(/each part of the engine picks the flags it cares about/)).toBeInTheDocument()
  })

  it('while loading, shows progress text and no table', () => {
    render(<DataQualityPage state={{ status: 'loading' }} />)
    expect(screen.getByText('Loading the exported data-quality file…')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('on a load failure, shows the reason and the command that regenerates the data, and no table', () => {
    const error = new DataLoadError('fetch', './data/data_quality.json answered HTTP 404')
    render(<DataQualityPage state={{ status: 'error', error }} />)
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('./data/data_quality.json answered HTTP 404')
    expect(alert).toHaveTextContent('uv run python tools/export_app_data.py')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })
})

describe('DataQualityPage: the quality gate', () => {
  it('shows the verdict and all 21 limits beside the worst value reached, in the unit the file gives', () => {
    render(<DataQualityPage state={ready()} />)
    expect(screen.getByRole('heading', { level: 2, name: 'Quality gate' })).toBeInTheDocument()
    const gate = screen.getByRole('table', { name: 'Quality-gate limits' })
    expect(cells(gate)).toEqual([
      ['Source', 'Check', 'Limit', 'Worst seen'],
      ['optionsdx', "BID_NULL share of a year's quotes", '≤ 5.00%', '3.00%'],
      ['optionsdx', "ASK_NULL share of a year's quotes", '≤ 5.00%', '3.00%'],
      ['optionsdx', "CROSSED share of a year's quotes", '≤ 1.00%', '0.20%'],
      ['optionsdx', "VENDOR_IV_INVALID share of a year's quotes", '≤ 12.00%', '5.00%'],
      ['optionsdx', "UNDERLYING_MISMATCH share of a year's quotes", '≤ 8.00%', '2.00%'],
      ['dolthub', "BID_NULL share of a year's quotes", '≤ 1.00%', '0.00%'],
      ['dolthub', "ASK_NULL share of a year's quotes", '≤ 1.00%', '0.00%'],
      ['dolthub', "CROSSED share of a year's quotes", '≤ 1.00%', '0.50%'],
      ['dolthub', "VENDOR_IV_INVALID share of a year's quotes", '≤ 1.00%', '0.00%'],
      ['optionsdx', 'snapshot dates in the thinnest year of 2010-2023 (daily)', '≥ 230 dates', '245 dates'],
      ['dolthub', 'snapshot dates in the thinnest year of 2020-2023 (Mon/Wed/Fri)', '≥ 120 dates', '143 dates'],
      ['dolthub', 'snapshot dates in 2024 (Mon/Wed/Fri to 09-09 with no dates 07-30 to 08-09, then daily)', '≥ 140 dates', '173 dates'],
      ['dolthub', 'snapshot dates in 2025 (daily)', '≥ 200 dates', '248 dates'],
      ['dolthub', 'snapshot dates in 2026 (daily, a partial year: the export ends on 2026-10-26)', '≥ 160 dates', '198 dates'],
      ['optionsdx', 'snapshot dates in all', '≥ 5 dates', '6 dates'],
      ['dolthub', 'snapshot dates in all', '≥ 3 dates', '3 dates'],
      ['optionsdx', 'quotes on the thinnest snapshot date', '≥ 1,000 quotes', '1,790 quotes'],
      ['dolthub', 'quotes on the thinnest snapshot date from 2020-01-06', '≥ 40 quotes', '60 quotes'],
      ['optionsdx', 'vendor dates the calendar drops', '≤ 15 dates', '1 dates'],
      ['dolthub', 'vendor dates the calendar drops', '≤ 130 dates', '2 dates'],
      ['optionsdx', '99th percentile of |UNDERLYING_LAST minus the SPY close|', '≤ 50 cents', '24 cents'],
    ])
    expect(cells(gate)).toHaveLength(1 + 21)
    const verdict = within(gate.closest('.card') as HTMLElement).getByText('Passed')
    expect(verdict).toHaveClass('ok-badge')
    expect(screen.queryByText('Failed')).not.toBeInTheDocument()
  })

  it('shows a number that is not whole with two decimals', () => {
    render(
      <DataQualityPage
        state={ready(dataQuality((d) => { d.gate.thresholds.limit[20] = 49.5; d.gate.thresholds.worst[20] = 24.25 }))}
      />,
    )
    const rows = cells(screen.getByRole('table', { name: 'Quality-gate limits' }))
    expect(rows[21].slice(2)).toEqual(['≤ 49.50 cents', '24.25 cents'])
  })

  it('shows a failed gate with its reasons', () => {
    const failed = dataQuality((d) => {
      d.gate.passed = false
      d.gate.failures = ['optionsdx 2010: BID_NULL on 6.00% of rows (limit 5%)']
    })
    render(<DataQualityPage state={ready(failed)} />)
    const gate = (screen.getByRole('table', { name: 'Quality-gate limits' }).closest('.card')) as HTMLElement
    expect(within(gate).getByText('Failed')).toHaveClass('err-badge')
    expect(within(gate).getByRole('alert')).toHaveTextContent('optionsdx 2010: BID_NULL on 6.00% of rows (limit 5%)')
    expect(within(gate).queryByText('Passed')).not.toBeInTheDocument()
  })
})

describe('DataQualityPage: rows per source and the calendar', () => {
  it('shows the quotes and snapshot dates of each source', () => {
    render(<DataQualityPage state={ready()} />)
    const heading = screen.getByRole('heading', { level: 2, name: 'Rows per source' })
    const tiles = heading.nextElementSibling as HTMLElement
    const [dolthub, optionsdx] = [...tiles.querySelectorAll('.stat')] as HTMLElement[]
    expect(dolthub).toHaveTextContent('dolthub')
    expect(dolthub).toHaveTextContent('2,000')
    expect(dolthub).toHaveTextContent('quotes on 3 snapshot dates')
    expect(optionsdx).toHaveTextContent('optionsdx')
    expect(optionsdx).toHaveTextContent('7,000')
    expect(optionsdx).toHaveTextContent('quotes on 6 snapshot dates')
  })

  it('explains the two calendar actions, session and drop, and lists their counts', () => {
    render(<DataQualityPage state={ready()} />)
    const section = screen.getByRole('table', { name: 'Calendar fixes' }).closest('.card') as HTMLElement
    for (const { action, meaning } of CALENDAR_ACTIONS) {
      const item = within(section).getByText(action, { selector: 'strong' }).closest('li') as HTMLElement
      expect(item).toHaveTextContent(meaning)
    }
    expect(cells(screen.getByRole('table', { name: 'Calendar fixes' }))).toEqual([
      ['Source', 'Action', 'Vendor dates', 'Quotes'],
      ['dolthub', 'drop', '2', '7'],
      ['dolthub', 'session', '3', '2,000'],
      ['optionsdx', 'drop', '1', '6'],
      ['optionsdx', 'session', '6', '7,000'],
    ])
  })

  it('explains exactly the actions the contract accepts, and says there are two', () => {
    render(<DataQualityPage state={ready()} />)
    expect(CALENDAR_ACTIONS.map((a) => a.action)).toEqual([...CALENDAR_ACTION_NAMES])
    const section = screen.getByRole('table', { name: 'Calendar fixes' }).closest('.card') as HTMLElement
    expect(section).toHaveTextContent('each vendor date gets one of two actions')
    expect(section).not.toHaveTextContent(/relabel/i)
  })
})

describe('DataQualityPage: flags by year', () => {
  it('has one card per source, each with a year column per year of that source', () => {
    render(<DataQualityPage state={ready()} />)
    const optionsdx = screen.getByRole('table', { name: 'Quality flags by year, optionsdx' })
    expect(cells(optionsdx)[0]).toEqual(['Flag', '2010', '2011', '2012'])
    const dolthub = screen.getByRole('table', { name: 'Quality flags by year, dolthub' })
    expect(cells(dolthub)[0]).toEqual(['Flag', '2021'])
  })

  it('starts on the share of each year’s quotes, with the quotes of the year on the first row', () => {
    render(<DataQualityPage state={ready()} />)
    const rows = cells(screen.getByRole('table', { name: 'Quality flags by year, optionsdx' }))
    // shortened in this view so 14 years fit the page; the exact number is the cell's tooltip
    expect(rows[1]).toEqual(['quotes', '1K', '2K', '4K'])
    expect(screen.getAllByTitle('4,000')).toHaveLength(1)
    const bidNull = rows.find((r) => r[0].startsWith('BID_NULL'))!
    expect(bidNull.slice(1)).toEqual(['3.00%', '1.00%', '1.00%'])
    expect(rows.find((r) => r[0].startsWith('CROSSED'))!.slice(1)).toEqual(['0.00%', '0.20%', '0.20%'])
  })

  it('switches to the number of quotes and back, reading the other array of the file', () => {
    render(<DataQualityPage state={ready()} />)
    const select = screen.getByRole('combobox', { name: 'Tables show' })
    fireEvent.change(select, { target: { value: 'counts' } })
    const counts = cells(screen.getByRole('table', { name: 'Quality flags by year, optionsdx' }))
    expect(counts[1]).toEqual(['quotes', '1,000', '2,000', '4,000'])
    expect(counts.find((r) => r[0].startsWith('BID_NULL'))!.slice(1)).toEqual(['30', '20', '40'])
    expect(counts.find((r) => r[0].startsWith('VENDOR_IV_INVALID'))!.slice(1)).toEqual(['50', '60', '120'])
    // both sources follow the one switch
    expect(cells(screen.getByRole('table', { name: 'Quality flags by year, dolthub' })).find((r) => r[0].startsWith('ZERO_BID'))!.slice(1)).toEqual(['200'])
    fireEvent.change(select, { target: { value: 'shares' } })
    const shares = cells(screen.getByRole('table', { name: 'Quality flags by year, optionsdx' }))
    expect(shares.find((r) => r[0].startsWith('BID_NULL'))!.slice(1)).toEqual(['3.00%', '1.00%', '1.00%'])
  })

  it('names every flag with its description', () => {
    render(<DataQualityPage state={ready()} />)
    const table = screen.getByRole('table', { name: 'Quality flags by year, optionsdx' })
    for (const [name, text] of [['BID_NULL', 'the bid is missing'], ['ZERO_BID', 'the bid is zero'], ['CROSSED', 'the bid is above the ask'], ['VENDOR_IV_INVALID', "the vendor's implied vol is missing, zero or negative"]]) {
      const row = within(table).getByText(name, { exact: false, selector: 'th' })
      expect(row).toHaveTextContent(text)
      expect(row).toHaveAttribute('title', text)
    }
  })

  it('draws a chart of the gated flags for a source with several years, one line per chart flag', () => {
    render(<DataQualityPage state={ready()} />)
    const chart = card('optionsdx').querySelector('svg') as SVGElement
    expect(chart).not.toBeNull()
    expect(chart.querySelectorAll('polyline')).toHaveLength(CHART_FLAGS.length)
    expect(CHART_FLAGS.map((c) => c.flag)).toEqual(['BID_NULL', 'CROSSED', 'VENDOR_IV_INVALID', 'UNDERLYING_MISMATCH'])
    for (const { flag } of CHART_FLAGS) expect(chart.textContent).toContain(flag)
    expect(chart.textContent).toContain('% of the year’s quotes')
    // each line takes its colour from the theme, so it stays readable in both themes
    expect([...chart.querySelectorAll('polyline')].map((l) => l.getAttribute('stroke'))).toEqual([
      'var(--accent)',
      'var(--teal)',
      'var(--down)',
      'var(--blue)',
    ])
    expect(card('optionsdx')).toHaveTextContent('Years 2010 to 2012, left to right.')
  })

  it('charts only flags the contract knows: a chart flag that is not one of the 13 would be dropped without a sound', () => {
    for (const { flag } of CHART_FLAGS) expect(FLAG_NAMES as readonly string[]).toContain(flag)
  })

  it('draws the shares the file gives, as percentages', () => {
    // BID_NULL of the fixture: 0.03, 0.01, 0.01. Raise it to 50%, 25% and 12.5% of 2010 to 2012 (counts and shares together,
    // as the contract requires, and the gate's worst with them: the gate then reports the failure).
    const edited = dataQuality((d) => {
      const f = d.flags_by_year as { counts: Record<string, number[]>; shares: Record<string, number[]> }
      f.counts.BID_NULL = [0, 500, 500, 500]
      f.shares.BID_NULL = [0, 0.5, 0.25, 0.125]
      d.gate.thresholds.worst[0] = 0.5
      d.gate.passed = false
      d.gate.failures = ['optionsdx 2010: BID_NULL on 50.00% of rows (limit 5%)']
    })
    render(<DataQualityPage state={ready(edited)} />)
    const chart = card('optionsdx').querySelector('svg') as SVGElement
    expect(chart.textContent).toContain('50.00') // the top tick is the file's largest BID_NULL share (0.5), shown as a percentage
  })

  it('draws no chart for a source with a single year', () => {
    render(<DataQualityPage state={ready()} />)
    expect(card('dolthub').querySelector('svg')).toBeNull()
    expect(card('dolthub')).not.toHaveTextContent('left to right')
  })
})

describe('DataQualityPage: cross-vendor agreement', () => {
  /** The three cards of the section, found by their tables. */
  const thresholds = () => screen.getByRole('table', { name: 'Cross-vendor dates inside a threshold' })
  const byYear = () => screen.getByRole('table', { name: 'Cross-vendor agreement by year' })

  it('shows the label, the overlap and why the thresholds are measurements', () => {
    render(<DataQualityPage state={ready()} />)
    const section = thresholds().closest('.card') as HTMLElement
    expect(section).toHaveTextContent('Both vendors, 2020-01-06 to 2023-12-29: test fixture; 100 dates in both.')
    expect(section).toHaveTextContent('Measurements, not a test. The thresholds were chosen after looking at these same overlap dates')
    expect(screen.getByText(CROSSVENDOR_NOTE)).toBeInTheDocument()
  })

  it('shows each threshold with its dates and the share within it, and no pass or fail', () => {
    const { container } = render(<DataQualityPage state={ready()} />)
    expect(cells(thresholds())).toEqual([
      ['Gap', 'Threshold', 'Dates', 'Share within'],
      ['30-day ATM IV: |DoltHub minus OptionsDX|', '≤ 1 vol pts', '98', '97.0%'],
      ['Parity spot: |DoltHub / SPY close minus 1|', '≤ 25 bp', '100', '93.0%'],
    ])
    // No verdict anywhere in the cross-vendor cards: no badge, no alert, no result column.
    for (const table of [thresholds(), byYear(), screen.getByRole('table', { name: 'Cross-vendor differences' })]) {
      const card = table.closest('.card') as HTMLElement
      expect(card.querySelector('.badge')).toBeNull()
      expect(within(card).queryByRole('alert')).not.toBeInTheDocument()
      expect(within(card).queryByRole('columnheader', { name: /result|required/i })).not.toBeInTheDocument()
    }
    expect(screen.queryByText(/Tolerances? (met|missed)/)).not.toBeInTheDocument()
    // The only badge on the whole page is the quality gate's.
    expect([...container.querySelectorAll('.badge')].map((b) => b.textContent)).toEqual(['Passed'])
  })

  it('shows the same cross-vendor numbers whatever the shares are: a low share is a measurement, not a failure', () => {
    const low = dataQuality((d) => {
      // the pooled shares and the years' shares move together, as the contract requires
      d.cross_vendor.within_thresholds.share_within = [0.1, 0.2]
      d.cross_vendor.by_year.iv30_share_within = [0.1, 0.1, 0.1, 0.1]
      d.cross_vendor.by_year.spot_dolthub_share_within = [0.2, 0.2, 0.2, 0.2]
    })
    const { container } = render(<DataQualityPage state={ready(low)} />)
    expect(cells(thresholds()).slice(1).map((r) => r[3])).toEqual(['10.0%', '20.0%'])
    expect(thresholds().closest('.card')!.querySelector('.badge')).toBeNull()
    expect([...container.querySelectorAll('.badge')].map((b) => b.textContent)).toEqual(['Passed'])
  })

  it('reads the thresholds from the file, in the table and in the headings of the table by year', () => {
    const wider = dataQuality((d) => { d.cross_vendor.within_thresholds.threshold = [2, 30] })
    render(<DataQualityPage state={ready(wider)} />)
    expect(cells(thresholds()).slice(1).map((r) => r[1])).toEqual(['≤ 2 vol pts', '≤ 30 bp'])
    expect(cells(byYear())[0].slice(2, 4)).toEqual(['30-day IV gap ≤ 2 vol pts', 'DoltHub spot miss ≤ 30 bp'])
  })

  it('heads the by-year columns without a threshold when the file has no such row', () => {
    const none = dataQuality((d) => { d.cross_vendor.within_thresholds.key = ['a', 'b'] })
    render(<DataQualityPage state={ready(none)} />)
    expect(cells(byYear())[0].slice(2, 4)).toEqual(['30-day IV gap', 'DoltHub spot miss'])
  })

  it('shows the shares and median misses of each calendar year', () => {
    render(<DataQualityPage state={ready()} />)
    expect(cells(byYear())).toEqual([
      ['Year', 'Dates', '30-day IV gap ≤ 1 vol pts', 'DoltHub spot miss ≤ 25 bp', 'DoltHub spot, median miss of the close (bp)', 'OptionsDX spot, median miss of the close (bp)'],
      ['2020', '25', '92.0%', '84.0%', '3.50', '1.00'],
      ['2021', '25', '96.0%', '92.0%', '2.25', '0.05'],
      ['2022', '25', '100.0%', '96.0%', '-0.75', '-2.25'],
      ['2023', '25', '100.0%', '100.0%', '0.13', '-2.50'],
    ])
    expect(byYear().closest('.card')).toHaveTextContent(BY_YEAR_NOTE)
  })

  it('lists the quantiles of each difference with its unit', () => {
    render(<DataQualityPage state={ready()} />)
    expect(cells(screen.getByRole('table', { name: 'Cross-vendor differences' }))).toEqual([
      ['Difference', 'Unit', 'Dates', 'P5', 'P25', 'Median', 'P75', 'P95', 'Mean |gap|'],
      ['30-day ATM IV, DoltHub minus OptionsDX', 'vol pts', '98', '-0.25', '0.13', '0.25', '0.50', '1.50', '0.75'],
      ['DoltHub parity spot against the SPY close', 'bp', '100', '-18.00', '-4.50', '1.50', '7.50', '21.00', '9.25'],
    ])
  })
})

describe('DataQualityPage: where the numbers come from', () => {
  it('shows the schema version, the time and the commit of data_quality.json', () => {
    render(<DataQualityPage state={ready()} />)
    const section = screen.getByRole('heading', { name: 'Where these numbers come from' }).nextElementSibling as HTMLElement
    expect(section).toHaveTextContent('Test fixture: small data-quality aggregates')
    expect(within(section).getByText('Schema version').nextElementSibling).toHaveTextContent('0.2.0')
    expect(within(section).getByText('Generated at').nextElementSibling).toHaveTextContent('2026-10-27T23:30:00Z')
    expect(within(section).getByText('Source commit').nextElementSibling).toHaveTextContent('a1b2c3d4e5f6')
    expect(screen.queryByText('exported from a dirty working tree')).not.toBeInTheDocument()
    expect(screen.queryByText('no commit yet')).not.toBeInTheDocument()
  })

  it.each([
    ['a1b2c3d4e5f6-dirty', 'exported from a dirty working tree'],
    ['uncommitted', 'no commit yet'],
  ])('flags a non-reproducible export (source_commit %s)', (sha, warning) => {
    render(<DataQualityPage state={ready(dataQuality((d) => { d.source_commit = sha }))} />)
    expect(screen.getByText(warning)).toBeInTheDocument()
  })
})
