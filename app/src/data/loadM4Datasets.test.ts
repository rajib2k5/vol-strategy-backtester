/** How loadAppData treats the two milestone-4 datasets: optional, so a manifest that does not list them gets null and no request. */
import { describe, expect, it } from 'vitest'
import { DataLoadError, loadAppData, type FetchLike } from './loadAppData'
import { fakeFetch } from '../test/fakeFetch'
import manifestFixture from '../test/fixtures/manifest.json'
import surfaceFixture from '../test/fixtures/illustrative_surface.json'
import dataQualityFixture from '../test/fixtures/data_quality.json'
import surfaceFramesFixture from '../test/fixtures/surface_frames.json'
import blotterFixture from '../test/fixtures/blotter.json'
import positionsTimelineFixture from '../test/fixtures/positions_timeline.json'
import signalsFixture from '../test/fixtures/signals_timeline.json'
import strategiesFixture from '../test/fixtures/strategy_positions.json'

const SIGNALS_ENTRY = { name: 'signals_timeline', path: 'signals_timeline.json', schema_version: '0.5.0', description: 'Test fixture: a made-up signal' }
const STRATEGIES_ENTRY = { name: 'strategy_positions', path: 'strategy_positions.json', schema_version: '0.5.0', description: 'Test fixture: made-up runs' }

/** The fixture manifest with `entries` added after the M3 datasets. */
const manifestWith = (...entries: object[]): unknown => ({ ...manifestFixture, datasets: [...manifestFixture.datasets, ...entries] })

const BASE = {
  './data/illustrative_surface.json': surfaceFixture,
  './data/data_quality.json': dataQualityFixture,
  './data/surface_frames.json': surfaceFramesFixture,
  './data/blotter.json': blotterFixture,
  './data/positions_timeline.json': positionsTimelineFixture,
}
const M3_URLS = ['./data/manifest.json', ...Object.keys(BASE)]
const BOTH_FILES = { ...BASE, './data/manifest.json': manifestWith(SIGNALS_ENTRY, STRATEGIES_ENTRY), './data/signals_timeline.json': signalsFixture, './data/strategy_positions.json': strategiesFixture }

async function failure(fetchFn: FetchLike): Promise<DataLoadError> {
  try {
    await loadAppData(fetchFn)
  } catch (e) {
    expect(e).toBeInstanceOf(DataLoadError)
    return e as DataLoadError
  }
  throw new Error('expected loadAppData to reject')
}

describe('loadAppData: the milestone-4 datasets are optional', () => {
  it('gives null for both, and fetches nothing more, when the manifest lists neither', async () => {
    const requested: string[] = []
    const data = await loadAppData(fakeFetch({ ...BASE, './data/manifest.json': manifestFixture }, requested))
    expect(data.signalsTimeline).toBeNull()
    expect(data.strategyPositions).toBeNull()
    expect(requested).toEqual(M3_URLS)
  })
  it('loads both after the M3 datasets, in that order, when the manifest lists them', async () => {
    const requested: string[] = []
    const data = await loadAppData(fakeFetch(BOTH_FILES, requested))
    expect(requested).toEqual([...M3_URLS, './data/signals_timeline.json', './data/strategy_positions.json'])
    expect(data.signalsTimeline?.dates).toHaveLength(60)
    expect(data.strategyPositions?.banner).toBe(strategiesFixture.banner)
  })
  it('loads the one the manifest lists and gives null for the other', async () => {
    const requested: string[] = []
    const data = await loadAppData(fakeFetch({ ...BOTH_FILES, './data/manifest.json': manifestWith(STRATEGIES_ENTRY) }, requested))
    expect(data.signalsTimeline).toBeNull()
    expect(data.strategyPositions?.runs).toHaveLength(2)
    expect(requested).toEqual([...M3_URLS, './data/strategy_positions.json'])
  })
  it('takes the path from the manifest entry', async () => {
    const requested: string[] = []
    const moved = manifestWith({ ...SIGNALS_ENTRY, path: 'm4/sig.json' })
    await loadAppData(fakeFetch({ ...BASE, './data/manifest.json': moved, './data/m4/sig.json': signalsFixture }, requested))
    expect(requested[requested.length - 1]).toBe('./data/m4/sig.json')
  })
  it('fails like any dataset when a listed file is missing (HTTP 404)', async () => {
    const { './data/signals_timeline.json': _missing, ...rest } = BOTH_FILES
    void _missing
    const e = await failure(fakeFetch(rest))
    expect(e.kind).toBe('fetch')
    expect(e.message).toBe('./data/signals_timeline.json answered HTTP 404')
  })
  it('fails like any dataset when a listed file breaks its contract, naming the file and the field', async () => {
    const bad = JSON.parse(JSON.stringify(strategiesFixture)) as { runs: { run: { split: string } }[] }
    bad.runs[0].run.split = 'holdout'
    const e = await failure(fakeFetch({ ...BOTH_FILES, './data/strategy_positions.json': bad }))
    expect(e.kind).toBe('contract')
    expect(e.message).toContain('strategy_positions.json: strategy_positions.runs[0].run.split: is "holdout"')
  })
  it('fails when the file says another schema_version than its manifest entry', async () => {
    const e = await failure(fakeFetch({ ...BOTH_FILES, './data/signals_timeline.json': { ...signalsFixture, schema_version: '0.5.1' } }))
    expect(e.kind).toBe('contract')
    expect(e.message).toBe('manifest.json: signals_timeline: the manifest lists schema_version "0.5.0" but signals_timeline.json says "0.5.1"')
  })
})
