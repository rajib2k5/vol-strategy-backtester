import { afterEach, describe, expect, it, vi } from 'vitest'
import { DataLoadError, describeLoadFailure, loadAppData, type FetchLike } from './loadAppData'
import { fakeFetch } from '../test/fakeFetch'
import manifestFixture from '../test/fixtures/manifest.json'
import surfaceFixture from '../test/fixtures/illustrative_surface.json'
import dataQualityFixture from '../test/fixtures/data_quality.json'

const FILES = {
  './data/manifest.json': manifestFixture,
  './data/illustrative_surface.json': surfaceFixture,
  './data/data_quality.json': dataQualityFixture,
}
const URLS = ['./data/manifest.json', './data/illustrative_surface.json', './data/data_quality.json']

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
  })

  it('takes each dataset path from the manifest, not from a hard-coded name', async () => {
    const moved = JSON.parse(JSON.stringify(manifestFixture)) as { datasets: { path: string }[] }
    moved.datasets[0].path = 'surfaces/v1/s.json'
    moved.datasets[1].path = 'quality/q.json'
    const requested: string[] = []
    await loadAppData(
      fakeFetch(
        { './data/manifest.json': moved, './data/surfaces/v1/s.json': surfaceFixture, './data/quality/q.json': dataQualityFixture },
        requested,
      ),
    )
    expect(requested).toEqual(['./data/manifest.json', './data/surfaces/v1/s.json', './data/quality/q.json'])
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
    m.datasets.pop()
    const e = await failure(fakeFetch({ ...FILES, './data/manifest.json': m }))
    expect(e.kind).toBe('contract')
    expect(e.message).toContain('does not list the "data_quality" dataset')
  })
  it.each(['0.3.0', '0.2.1'])('a dataset (%s) whose schema_version differs from its manifest entry (0.2.0)', async (version) => {
    // Both files are individually valid; only the pair is inconsistent.
    const other = { ...surfaceFixture, schema_version: version }
    const e = await failure(fakeFetch({ ...FILES, './data/illustrative_surface.json': other }))
    expect(e.kind).toBe('contract')
    expect(e.message).toBe(
      `manifest.json: illustrative_surface: the manifest lists schema_version "0.2.0" but illustrative_surface.json says "${version}"`,
    )
  })
  it('a data-quality file whose schema_version differs from its manifest entry', async () => {
    const other = { ...dataQualityFixture, schema_version: '0.2.1' }
    const e = await failure(fakeFetch({ ...FILES, './data/data_quality.json': other }))
    expect(e.kind).toBe('contract')
    expect(e.message).toBe('manifest.json: data_quality: the manifest lists schema_version "0.2.0" but data_quality.json says "0.2.1"')
  })
  it('a manifest entry whose schema_version differs from its (valid) dataset file', async () => {
    const m = JSON.parse(JSON.stringify(manifestFixture)) as { datasets: { schema_version: string }[] }
    m.datasets[0].schema_version = '0.3.0'
    const e = await failure(fakeFetch({ ...FILES, './data/manifest.json': m }))
    expect(e.kind).toBe('contract')
    expect(e.message).toContain('the manifest lists schema_version "0.3.0" but illustrative_surface.json says "0.2.0"')
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
