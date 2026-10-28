import type { FetchLike } from '../data/loadAppData'

/**
 * A fetch stand-in serving JSON bodies from a url -> body table. Unknown urls answer HTTP 404.
 * Every requested url is appended to `requested`, so tests can assert exactly what was fetched.
 */
export function fakeFetch(files: Record<string, unknown>, requested: string[] = []): FetchLike {
  return async (url) => {
    requested.push(url)
    if (!(url in files)) return { ok: false, status: 404, json: async () => ({}) }
    return { ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(files[url])) as unknown }
  }
}
