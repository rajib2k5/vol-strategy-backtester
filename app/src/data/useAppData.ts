import { useEffect, useState } from 'react'
import { loadAppData, type AppData } from './loadAppData'

export type AppDataState =
  | { status: 'loading' }
  | { status: 'ready'; data: AppData }
  | { status: 'error'; error: unknown }

/**
 * Loads the exported results once on mount. `load` is injectable so tests need no network; pass a
 * stable reference (a module-level function), because the effect re-runs whenever `load` changes.
 */
export function useAppData(load: () => Promise<AppData> = loadAppData): AppDataState {
  const [state, setState] = useState<AppDataState>({ status: 'loading' })
  useEffect(() => {
    let cancelled = false
    load().then(
      (data) => {
        if (!cancelled) setState({ status: 'ready', data })
      },
      (error: unknown) => {
        if (!cancelled) setState({ status: 'error', error })
      },
    )
    return () => {
      cancelled = true
    }
  }, [load])
  return state
}
