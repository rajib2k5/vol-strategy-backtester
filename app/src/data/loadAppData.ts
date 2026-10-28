/**
 * Fetches the exported results: `./data/manifest.json`, then each dataset the manifest points at.
 * This is the only place the app touches the network. Everything it fetches goes through the
 * parsers in src/lib/contract.ts before any component sees it.
 *
 * URLs are relative (./data/...) and vite.config.ts keeps `base: './'`, so the same build works
 * from any sub-path.
 *
 * Not in src/lib/ because it does I/O; `fetch` is injected so tests never touch the network.
 */
import {
  ContractError,
  SURFACE_DATASET,
  assertDatasetMatchesEntry,
  findDataset,
  parseIllustrativeSurface,
  parseManifest,
  type IllustrativeSurface,
  type Manifest,
} from '../lib/contract'

export const DATA_DIR = './data'
export const EXPORT_COMMAND = 'uv run python tools/export_app_data.py'

export interface AppData {
  manifest: Manifest
  surface: IllustrativeSurface
}

/** `fetch` = the request itself failed or returned junk; `contract` = valid JSON that breaks the contract. */
export type LoadFailureKind = 'fetch' | 'contract'

export class DataLoadError extends Error {
  readonly kind: LoadFailureKind
  constructor(kind: LoadFailureKind, message: string) {
    super(message)
    this.name = 'DataLoadError'
    this.kind = kind
  }
}

/** The slice of the fetch API we use, so tests can pass a tiny fake. */
export type FetchLike = (url: string) => Promise<{ ok: boolean; status: number; json: () => Promise<unknown> }>

async function getJson(url: string, fetchFn: FetchLike): Promise<unknown> {
  let res: Awaited<ReturnType<FetchLike>>
  try {
    res = await fetchFn(url)
  } catch (e) {
    throw new DataLoadError('fetch', `could not reach ${url} (${e instanceof Error ? e.message : String(e)})`)
  }
  if (!res.ok) throw new DataLoadError('fetch', `${url} answered HTTP ${res.status}`)
  try {
    return await res.json()
  } catch {
    // A dev server answers an unknown URL with index.html (HTTP 200), which is not JSON.
    throw new DataLoadError('fetch', `${url} is not valid JSON`)
  }
}

function asContractFailure<T>(parse: () => T, file: string): T {
  try {
    return parse()
  } catch (e) {
    if (e instanceof ContractError) throw new DataLoadError('contract', `${file}: ${e.message}`)
    throw e
  }
}

export async function loadAppData(fetchFn: FetchLike = (url) => fetch(url)): Promise<AppData> {
  const manifestRaw = await getJson(`${DATA_DIR}/manifest.json`, fetchFn)
  const manifest = asContractFailure(() => parseManifest(manifestRaw), 'manifest.json')

  const entry = findDataset(manifest, SURFACE_DATASET)
  if (!entry) {
    throw new DataLoadError('contract', `manifest.json does not list the "${SURFACE_DATASET}" dataset this app needs`)
  }
  const surfaceRaw = await getJson(`${DATA_DIR}/${entry.path}`, fetchFn)
  const surface = asContractFailure(() => parseIllustrativeSurface(surfaceRaw), entry.path)
  // The manifest's claim about this file must match what the file says about itself.
  asContractFailure(() => assertDatasetMatchesEntry(entry, surface), 'manifest.json')
  return { manifest, surface }
}

/** Plain-language explanation for the UI, always ending with how to regenerate the files. */
export function describeLoadFailure(e: unknown): string {
  const why = e instanceof DataLoadError ? e.message : e instanceof Error ? e.message : String(e)
  const lead =
    e instanceof DataLoadError && e.kind === 'contract'
      ? 'The exported data does not match what this app expects.'
      : 'The exported results could not be loaded.'
  return `${lead} (${why})`
}
