/**
 * The Signal and Strategies pages drawn from the REAL committed M4 files (app/public/data/signals_timeline.json and
 * strategy_positions.json), loaded through the real loader: the render check of milestone 4's export (task 13).
 * The page tests (src/views/*.test.tsx) use made-up fixtures; this one fails if the exporter writes a file the pages
 * cannot draw.
 */
import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { loadAppData } from '../data/loadAppData'
import { SignalPage } from '../views/SignalPage'
import { StrategiesPage } from '../views/StrategiesPage'
import { fakeFetch } from './fakeFetch'

const committed = import.meta.glob('../../public/data/*.json', { query: '?raw', import: 'default', eager: true }) as Record<
  string,
  string
>

/** Every committed file, as the loader fetches it. */
function files(): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [path, text] of Object.entries(committed)) out[`./data/${path.split('/').pop()}`] = JSON.parse(text)
  return out
}

async function ready() {
  const data = await loadAppData(fakeFetch(files(), []))
  return { status: 'ready' as const, data }
}

describe('the M4 pages on the real committed files', () => {
  it('draw the Signal page: both charts, the threshold levels and the scored forecast test', async () => {
    const state = await ready()
    const file = state.data.signalsTimeline!
    render(<SignalPage state={state} />)
    for (const name of ['IV30, forecast vol and ex-post realised vol', 'Log variance ratio']) {
      const figure = screen.getByRole('figure', { name })
      expect(within(figure).getByRole('img')).toBeInTheDocument()
    }
    expect(screen.getByRole('figure', { name: 'IV30, forecast vol and ex-post realised vol' })).toHaveTextContent(
      `${file.dates[0]} to ${file.dates.at(-1)}`,
    )
    expect(screen.getByRole('list', { name: 'Threshold levels' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 3, name: 'Forecast test' })).toBeInTheDocument()
    expect(screen.queryByText('Forecast test: not scored yet')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('draw the Strategies page: the banner first, then one card and one timeline per run', async () => {
    const state = await ready()
    const file = state.data.strategyPositions!
    render(<StrategiesPage state={state} />)
    expect(screen.getByRole('region', { name: 'Trial count' })).toHaveTextContent(file.banner)
    const cards = screen.getAllByRole('region', { name: /^Run of / })
    expect(cards).toHaveLength(file.runs.length)
    cards.forEach((card, i) => {
      expect(within(card).getByText(file.runs[i].params.structure as string, { selector: 'dd' })).toBeInTheDocument()
      expect(within(card).getByRole('img', { name: `When each position of ${file.runs[i].strategy} was open` })).toBeInTheDocument()
    })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
