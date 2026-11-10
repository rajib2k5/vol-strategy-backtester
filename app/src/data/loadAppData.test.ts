import { afterEach, describe, expect, it, vi } from 'vitest'
import { DataLoadError, describeLoadFailure, loadAppData, type FetchLike } from './loadAppData'
import { fakeFetch } from '../test/fakeFetch'
import manifestFixture from '../test/fixtures/manifest.json'
import surfaceFixture from '../test/fixtures/illustrative_surface.json'
import dataQualityFixture from '../test/fixtures/data_quality.json'
import surfaceFramesFixture from '../test/fixtures/surface_frames.json'
import blotterFixture from '../test/fixtures/blotter.json'
import positionsTimelineFixture from '../test/fixtures/positions_timeline.json'

const FILES = {
  './data/manifest.json': manifestFixture,
  './data/illustrative_surface.json': surfaceFixture,
  './data/data_quality.json': dataQualityFixture,
  './data/surface_frames.json': surfaceFramesFixture,
  './data/blotter.json': blotterFixture,
  './data/positions_timeline.json': positionsTimelineFixture,
}
const URLS = [
  './data/manifest.json',
  './data/illustrative_surface.json',
  './data/data_quality.json',
  './data/surface_frames.json',
  './data/blotter.json',
  './data/positions_timeline.json',
]

afterEach(() => {
  vi.unstubAllGlobals()
})

/** Run loadAppData and return the DataLoadError it rejects with (fails the test if it resolves). */
async function failure(fetchFn: FetchLike): Promise<DataLoadError> {
  try {
    await loadAppData(fetchFn)
  } catch (e) {
    expect(e).toBeInstanceOf(DataLoadError)
    return e as DataLoadError
  }
  throw new Error('expected loadAppData to reject')
}

describe('loadAppData: happy path', () => {
  it('fetches the manifest, then each dataset it lists in turn, using only relative URLs', async () => {
    const requested: string[] = []
    const data = await loadAppData(fakeFetch(FILES, requested))
    expect(requested).toEqual(URLS)
    expect(requested.every((u) => u.startsWith('./'))).toBe(true)
    expect(data.manifest.source_commit).toBe('a1b2c3d4e5f6')
    expect(data.surface.iv).toEqual(surfaceFixture.iv)
    expect(data.dataQuality.sources.rows).toEqual(dataQualityFixture.sources.rows)
    expect(data.surfaceFrames.frames.map((f) => f.date)).toEqual(['2020-01-03', '2020-03-16'])
    expect(data.blotter.fills.map((f) => f.fill_id)).toEqual(blotterFixture.fills.map((f) => f.fill_id))
    expect(data.blotter.events).toHaveLength(3)
    expect(data.positionsTimeline.positions.map((p) => p.position_id)).toEqual([1, 2, 3, 4])
    expect(data.positionsTimeline.run).toEqual(data.blotter.run)
  })

  it('takes each dataset path from the manifest, not from a hard-coded name', async () => {
    const moved = JSON.parse(JSON.stringify(manifestFixture)) as { datasets: { path: string }[] }
    moved.datasets[0].path = 'surfaces/v1/s.json'
    moved.datasets[1].path = 'quality/q.json'
    moved.datasets[2].path = 'real/frames.json'
    moved.datasets[3].path = 'engine/blotter.json'
    moved.datasets[4].path = 'engine/timeline/positions.json'
    const requested: string[] = []
    await loadAppData(
      fakeFetch(
        {
          './data/manifest.json': moved,
          './data/surfaces/v1/s.json': surfaceFixture,
          './data/quality/q.json': dataQualityFixture,
          './data/real/frames.json': surfaceFramesFixture,
          './data/engine/blotter.json': blotterFixture,
          './data/engine/timeline/positions.json': positionsTimelineFixture,
        },
        requested,
      ),
    )
    expect(requested).toEqual([
      './data/manifest.json',
      './data/surfaces/v1/s.json',
      './data/quality/q.json',
      './data/real/frames.json',
      './data/engine/blotter.json',
      './data/engine/timeline/positions.json',
    ])
  })

  it('uses the global fetch when none is injected', async () => {
    const urls: string[] = []
    const stub = fakeFetch(FILES, urls)
    vi.stubGlobal('fetch', (url: string) => stub(url))
    const data = await loadAppData()
    expect(urls).toEqual(URLS)
    expect(data.surface.dte).toEqual([7, 30, 90])
  })
})

describe('loadAppData: transport failures (kind = fetch)', () => {
  it('manifest missing (HTTP 404)', async () => {
    const e = await failure(fakeFetch({}))
    expect(e.kind).toBe('fetch')
    expect(e.message).toBe('./data/manifest.json answered HTTP 404')
  })
  it('dataset missing (HTTP 404) after a good manifest', async () => {
    const e = await failure(fakeFetch({ './data/manifest.json': manifestFixture }))
    expect(e.kind).toBe('fetch')
    expect(e.message).toBe('./data/illustrative_surface.json answered HTTP 404')
  })
  it('the data-quality file missing (HTTP 404) after a good manifest and surface', async () => {
    const e = await failure(fakeFetch({ './data/manifest.json': manifestFixture, './data/illustrative_surface.json': surfaceFixture }))
    expect(e.kind).toBe('fetch')
    expect(e.message).toBe('./data/data_quality.json answered HTTP 404')
  })
  it('the surface-frames file missing (HTTP 404) after the other three', async () => {
    const { './data/surface_frames.json': _missing, ...rest } = FILES
    void _missing
    const e = await failure(fakeFetch(rest))
    expect(e.kind).toBe('fetch')
    expect(e.message).toBe('./data/surface_frames.json answered HTTP 404')
  })
  it('the blotter file missing (HTTP 404) after the other four', async () => {
    const { './data/blotter.json': _missing, ...rest } = FILES
    void _missing
    const e = await failure(fakeFetch(rest))
    expect(e.kind).toBe('fetch')
    expect(e.message).toBe('./data/blotter.json answered HTTP 404')
  })
  it('the positions-timeline file missing (HTTP 404) after the other five', async () => {
    const { './data/positions_timeline.json': _missing, ...rest } = FILES
    void _missing
    const e = await failure(fakeFetch(rest))
    expect(e.kind).toBe('fetch')
    expect(e.message).toBe('./data/positions_timeline.json answered HTTP 404')
  })
  it('network error, keeping the underlying reason', async () => {
    const e = await failure(async () => {
      throw new TypeError('Failed to fetch')
    })
    expect(e.kind).toBe('fetch')
    expect(e.message).toContain('could not reach ./data/manifest.json')
    expect(e.message).toContain('Failed to fetch')
  })
  it('a non-Error rejection', async () => {
    const e = await failure(() => Promise.reject('offline'))
    expect(e.message).toContain('offline')
  })
  it('a body that is not JSON (e.g. a dev server answering with index.html)', async () => {
    const e = await failure(async () => ({
      ok: true,
      status: 200,
      json: async () => {
        throw new SyntaxError('Unexpected token <')
      },
    }))
    expect(e.kind).toBe('fetch')
    expect(e.message).toBe('./data/manifest.json is not valid JSON')
  })
})

describe('loadAppData: contract failures (kind = contract)', () => {
  it('a manifest with an unsupported schema major, naming the file and field', async () => {
    const bad = { ...manifestFixture, schema_version: '1.0.0' }
    const e = await failure(fakeFetch({ './data/manifest.json': bad }))
    expect(e.kind).toBe('contract')
    expect(e.message).toContain('manifest.json: manifest.schema_version: unsupported major version 1')
  })
  it('a manifest that does not list the surface dataset', async () => {
    const e = await failure(fakeFetch({ './data/manifest.json': { ...manifestFixture, datasets: [] } }))
    expect(e.kind).toBe('contract')
    expect(e.message).toContain('does not list the "illustrative_surface" dataset')
  })
  it('a manifest that lists the surface but not the data-quality dataset', async () => {
    const m = JSON.parse(JSON.stringify(manifestFixture)) as { datasets: unknown[] }
    m.datasets.splice(1, 1)
    const e = await failure(fakeFetch({ ...FILES, './data/manifest.json': m }))
    expect(e.kind).toBe('contract')
    expect(e.message).toContain('does not list the "data_quality" dataset')
  })
  it('a manifest that does not list the surface-frames dataset', async () => {
    const m = JSON.parse(JSON.stringify(manifestFixture)) as { datasets: unknown[] }
    m.datasets.splice(2, 1)
    const e = await failure(fakeFetch({ ...FILES, './data/manifest.json': m }))
    expect(e.kind).toBe('contract')
    expect(e.message).toContain('does not list the "surface_frames" dataset')
  })
  it('a manifest that does not list the blotter dataset', async () => {
    const m = JSON.parse(JSON.stringify(manifestFixture)) as { datasets: unknown[] }
    m.datasets.splice(3, 1)
    const e = await failure(fakeFetch({ ...FILES, './data/manifest.json': m }))
    expect(e.kind).toBe('contract')
    expect(e.message).toContain('does not list the "blotter" dataset')
  })
  it('a manifest that does not list the positions-timeline dataset', async () => {
    const m = JSON.parse(JSON.stringify(manifestFixture)) as { datasets: unknown[] }
    m.datasets.pop()
    const e = await failure(fakeFetch({ ...FILES, './data/manifest.json': m }))
    expect(e.kind).toBe('contract')
    expect(e.message).toContain('does not list the "positions_timeline" dataset')
  })
  it('a blotter file that breaks its contract, naming the file and the field', async () => {
    const bad = JSON.parse(JSON.stringify(blotterFixture)) as { fills: { qty: number }[] }
    bad.fills[2].qty = 0
    const e = await failure(fakeFetch({ ...FILES, './data/blotter.json': bad }))
    expect(e.kind).toBe('contract')
    expect(e.message).toBe('blotter.json: blotter.fills[2].qty: expected a whole number other than 0, got 0')
  })
  it('a positions-timeline file that breaks its contract, naming the file and the field', async () => {
    const bad = JSON.parse(JSON.stringify(positionsTimelineFixture)) as { open_count: number[] }
    bad.open_count.pop()
    const e = await failure(fakeFetch({ ...FILES, './data/positions_timeline.json': bad }))
    expect(e.kind).toBe('contract')
    expect(e.message).toBe('positions_timeline.json: positions_timeline.open_count: has 11 values but dates has 12')
  })
  it('a blotter file whose schema_version differs from its manifest entry', async () => {
    const other = { ...blotterFixture, schema_version: '0.4.1' }
    const e = await failure(fakeFetch({ ...FILES, './data/blotter.json': other }))
    expect(e.kind).toBe('contract')
    expect(e.message).toBe('manifest.json: blotter: the manifest lists schema_version "0.4.0" but blotter.json says "0.4.1"')
  })
  it('a positions-timeline file whose schema_version differs from its manifest entry', async () => {
    const other = { ...positionsTimelineFixture, schema_version: '0.5.0' }
    const e = await failure(fakeFetch({ ...FILES, './data/positions_timeline.json': other }))
    expect(e.kind).toBe('contract')
    expect(e.message).toBe('manifest.json: positions_timeline: the manifest lists schema_version "0.4.0" but positions_timeline.json says "0.5.0"')
  })
  it('a blotter file older than the schema that introduced it, even when its manifest entry says the same', async () => {
    const old = { ...blotterFixture, schema_version: '0.3.0' }
    const m = JSON.parse(JSON.stringify(manifestFixture)) as { datasets: { name: string; schema_version: string }[] }
    m.datasets.find((d) => d.name === 'blotter')!.schema_version = '0.3.0'
    const e = await failure(fakeFetch({ ...FILES, './data/manifest.json': m, './data/blotter.json': old }))
    expect(e.kind).toBe('contract')
    expect(e.message).toBe('blotter.json: blotter.schema_version: "0.3.0" is older than 0.4.0, the version that introduced this file')
  })
  it('a surface-frames file that breaks its contract, naming the file and the field', async () => {
    const bad = JSON.parse(JSON.stringify(surfaceFramesFixture)) as { illustrative: boolean }
    bad.illustrative = true
    const e = await failure(fakeFetch({ ...FILES, './data/surface_frames.json': bad }))
    expect(e.kind).toBe('contract')
    expect(e.message).toContain('surface_frames.json: surface_frames.illustrative: must be false')
  })
  it('a surface-frames file whose schema_version differs from its manifest entry', async () => {
    const other = { ...surfaceFramesFixture, schema_version: '0.3.1' }
    const e = await failure(fakeFetch({ ...FILES, './data/surface_frames.json': other }))
    expect(e.kind).toBe('contract')
    expect(e.message).toBe('manifest.json: surface_frames: the manifest lists schema_version "0.3.0" but surface_frames.json says "0.3.1"')
  })
  it.each(['0.4.0', '0.3.1'])('a dataset (%s) whose schema_version differs from its manifest entry (0.3.0)', async (version) => {
    // Both files are individually valid; only the pair is inconsistent.
    const other = { ...surfaceFixture, schema_version: version }
    const e = await failure(fakeFetch({ ...FILES, './data/illustrative_surface.json': other }))
    expect(e.kind).toBe('contract')
    expect(e.message).toBe(
      `manifest.json: illustrative_surface: the manifest lists schema_version "0.3.0" but illustrative_surface.json says "${version}"`,
    )
  })
  it('a data-quality file whose schema_version differs from its manifest entry', async () => {
    const other = { ...dataQualityFixture, schema_version: '0.3.1' }
    const e = await failure(fakeFetch({ ...FILES, './data/data_quality.json': other }))
    expect(e.kind).toBe('contract')
    expect(e.message).toBe('manifest.json: data_quality: the manifest lists schema_version "0.3.0" but data_quality.json says "0.3.1"')
  })
  it('a manifest entry whose schema_version differs from its (valid) dataset file', async () => {
    const m = JSON.parse(JSON.stringify(manifestFixture)) as { datasets: { schema_version: string }[] }
    m.datasets[0].schema_version = '0.4.0'
    const e = await failure(fakeFetch({ ...FILES, './data/manifest.json': m }))
    expect(e.kind).toBe('contract')
    expect(e.message).toContain('the manifest lists schema_version "0.4.0" but illustrative_surface.json says "0.3.0"')
  })
  it('a dataset with a ragged iv grid', async () => {
    const bad = JSON.parse(JSON.stringify(surfaceFixture)) as { iv: number[][] }
    bad.iv[0].pop()
    const e = await failure(fakeFetch({ ...FILES, './data/illustrative_surface.json': bad }))
    expect(e.kind).toBe('contract')
    expect(e.message).toContain('illustrative_surface.json: illustrative_surface.iv[0]: has 3 values but moneyness has 4 (ragged grid)')
  })
  it('a data-quality file with a ragged table, naming the file and the column', async () => {
    const bad = JSON.parse(JSON.stringify(dataQualityFixture)) as { calendar: { rows: number[] } }
    bad.calendar.rows.pop()
    const e = await failure(fakeFetch({ ...FILES, './data/data_quality.json': bad }))
    expect(e.kind).toBe('contract')
    expect(e.message).toBe('data_quality.json: data_quality.calendar.rows: has 3 values but "source" has 4')
  })
})

describe('describeLoadFailure', () => {
  it('says the data could not be loaded for transport failures, with the reason', () => {
    expect(describeLoadFailure(new DataLoadError('fetch', 'x answered HTTP 404'))).toBe(
      'The exported results could not be loaded. (x answered HTTP 404)',
    )
  })
  it('says the data does not match for contract failures', () => {
    expect(describeLoadFailure(new DataLoadError('contract', 'bad field'))).toBe(
      'The exported data does not match what this app expects. (bad field)',
    )
  })
  it('handles arbitrary errors and non-errors', () => {
    expect(describeLoadFailure(new Error('boom'))).toBe('The exported results could not be loaded. (boom)')
    expect(describeLoadFailure('weird')).toBe('The exported results could not be loaded. (weird)')
  })
})
