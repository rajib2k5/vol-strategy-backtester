/**
 * End-to-end contract test: the REAL files the Python exporter committed under app/public/data/,
 * run through the REAL parsers and loader.
 *
 * Every other contract test feeds the parsers hand-made fixtures, so a change on the Python side
 * (a renamed key, a new schema_version, a different shape) could break the app without a single
 * test noticing. This one reads whatever tools/export_app_data.py last wrote, so that kind of
 * change fails `npm run verify` here.
 *
 * The files are pulled in with import.meta.glob (Vite reads them from disk as raw text when the
 * test module is built) rather than node's fs: the app's tsconfig has no Node typings, and adding
 * them would leak Node globals into browser code.
 */
import { describe, expect, it } from 'vitest'
import {
  DATA_QUALITY_DATASET,
  SURFACE_DATASET,
  assertDatasetMatchesEntry,
  commitState,
  findDataset,
  parseDataQuality,
  parseIllustrativeSurface,
  parseManifest,
} from '../lib/contract'
import { loadAppData } from '../data/loadAppData'
import { fakeFetch } from './fakeFetch'

const committed = import.meta.glob('../../public/data/*.json', { query: '?raw', import: 'default', eager: true }) as Record<
  string,
  string
>

/** The parsed JSON of a committed file, by its file name (fails the test if the file is missing). */
function committedJson(fileName: string): unknown {
  const text = committed[`../../public/data/${fileName}`]
  if (text === undefined) {
    throw new Error(`app/public/data/${fileName} is not committed; run: uv run python tools/export_app_data.py`)
  }
  return JSON.parse(text)
}

describe('the committed app/public/data files', () => {
  it('include the manifest, the illustrative surface and the data-quality aggregates', () => {
    // Guards the guard: an empty glob would make every test below pass vacuously.
    expect(Object.keys(committed).map((k) => k.split('/').pop()).sort()).toEqual([
      'data_quality.json',
      'illustrative_surface.json',
      'manifest.json',
    ])
  })

  it('pass the manifest parser, which lists both datasets', () => {
    const manifest = parseManifest(committedJson('manifest.json'))
    expect(manifest.datasets.map((d) => d.name)).toEqual([SURFACE_DATASET, DATA_QUALITY_DATASET])
  })

  it('list only files that exist next to the manifest', () => {
    const manifest = parseManifest(committedJson('manifest.json'))
    for (const dataset of manifest.datasets) {
      expect(committed[`../../public/data/${dataset.path}`], dataset.path).toBeDefined()
    }
  })

  it('pass the surface parser, and are flagged illustrative', () => {
    const surface = parseIllustrativeSurface(committedJson('illustrative_surface.json'))
    expect(surface.illustrative).toBe(true)
    expect(surface.iv).toHaveLength(surface.dte.length)
    expect(surface.iv[0]).toHaveLength(surface.moneyness.length)
  })

  it('pass the data-quality parser: 13 flags, both sources, a passing gate, aggregates only', () => {
    const dq = parseDataQuality(committedJson('data_quality.json'))
    expect(dq.flag_names).toHaveLength(13)
    expect(dq.sources.source).toEqual(['dolthub', 'optionsdx'])
    expect(dq.gate.passed).toBe(true)
    // One row per source-year, per limit and per threshold: a handful of rows, never one per quote.
    expect(dq.flags_by_year.source.length).toBeLessThan(100)
    expect(dq.gate.thresholds.rule.length).toBeLessThan(100)
    expect(dq.cross_vendor.distributions.key.length).toBeLessThan(100)
    // The gate page lists every limit of quality.py: 9 flag shares, 5 date counts a year (one per sampling regime),
    // 2 date counts in all, 2 row minimums, 2 dropped-date maximums, 1 p99.
    expect(dq.gate.thresholds.rule).toHaveLength(21)
    // No date is moved to another session: the calendar only keeps a vendor date or drops it.
    expect([...new Set(dq.calendar.action)].sort()).toEqual(['drop', 'session'])
    // The cross-vendor check reports measurements: two thresholds, one row per calendar year of the overlap.
    expect(dq.cross_vendor.within_thresholds.key).toEqual(['iv30', 'spot'])
    expect(dq.cross_vendor.by_year.year).toEqual([2020, 2021, 2022, 2023])
    expect(dq.cross_vendor.by_year.dates.reduce((a, b) => a + b, 0)).toBe(dq.cross_vendor.overlap_dates)
  })

  it('agree with each other: same schema_version in each manifest entry and in its file', () => {
    const manifest = parseManifest(committedJson('manifest.json'))
    const files = {
      [SURFACE_DATASET]: parseIllustrativeSurface(committedJson('illustrative_surface.json')),
      [DATA_QUALITY_DATASET]: parseDataQuality(committedJson('data_quality.json')),
    }
    for (const [name, file] of Object.entries(files)) {
      const entry = findDataset(manifest, name)
      expect(entry, name).toBeDefined()
      expect(() => assertDatasetMatchesEntry(entry!, file)).not.toThrow()
      // One exporter run wrote the manifest and every dataset, so the stamp is the same.
      expect(file.generated_at, name).toBe(manifest.generated_at)
      expect(file.source_commit, name).toBe(manifest.source_commit)
    }
  })

  it('carry a commit stamp the app can classify', () => {
    const { source_commit } = parseManifest(committedJson('manifest.json'))
    expect(['clean', 'dirty', 'uncommitted']).toContain(commitState(source_commit))
  })

  it('load through the real loader, which fetches the manifest and then each dataset', async () => {
    const requested: string[] = []
    const files = {
      './data/manifest.json': committedJson('manifest.json'),
      './data/illustrative_surface.json': committedJson('illustrative_surface.json'),
      './data/data_quality.json': committedJson('data_quality.json'),
    }
    const data = await loadAppData(fakeFetch(files, requested))
    expect(requested).toEqual(['./data/manifest.json', './data/illustrative_surface.json', './data/data_quality.json'])
    expect(data.surface.params).toMatchObject({ model: 'SSVI' })
    expect(data.dataQuality.gate.passed).toBe(true)
  })
})
