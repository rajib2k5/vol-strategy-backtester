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
  SURFACE_DATASET,
  assertDatasetMatchesEntry,
  commitState,
  findDataset,
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
  it('include the manifest and the illustrative surface', () => {
    // Guards the guard: an empty glob would make every test below pass vacuously.
    expect(Object.keys(committed).map((k) => k.split('/').pop()).sort()).toEqual([
      'illustrative_surface.json',
      'manifest.json',
    ])
  })

  it('pass the manifest parser', () => {
    const manifest = parseManifest(committedJson('manifest.json'))
    expect(manifest.datasets.map((d) => d.name)).toContain(SURFACE_DATASET)
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

  it('agree with each other: same schema_version in the manifest entry and in the file', () => {
    const manifest = parseManifest(committedJson('manifest.json'))
    const surface = parseIllustrativeSurface(committedJson('illustrative_surface.json'))
    const entry = findDataset(manifest, SURFACE_DATASET)
    expect(entry).toBeDefined()
    expect(() => assertDatasetMatchesEntry(entry!, surface)).not.toThrow()
  })

  it('carry a commit stamp the app can classify', () => {
    const { source_commit } = parseManifest(committedJson('manifest.json'))
    expect(['clean', 'dirty', 'uncommitted']).toContain(commitState(source_commit))
  })

  it('load through the real loader, which fetches the manifest and then the surface', async () => {
    const requested: string[] = []
    const files = {
      './data/manifest.json': committedJson('manifest.json'),
      './data/illustrative_surface.json': committedJson('illustrative_surface.json'),
    }
    const data = await loadAppData(fakeFetch(files, requested))
    expect(requested).toEqual(['./data/manifest.json', './data/illustrative_surface.json'])
    expect(data.surface.params).toMatchObject({ model: 'SSVI' })
  })
})
