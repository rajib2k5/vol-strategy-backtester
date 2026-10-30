import { describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { useAppData } from './useAppData'
import { parseDataQuality, parseIllustrativeSurface, parseManifest, parseSurfaceFrames } from '../lib/contract'
import manifestFixture from '../test/fixtures/manifest.json'
import surfaceFixture from '../test/fixtures/illustrative_surface.json'
import dataQualityFixture from '../test/fixtures/data_quality.json'
import surfaceFramesFixture from '../test/fixtures/surface_frames.json'

const DATA = {
  manifest: parseManifest(manifestFixture),
  surface: parseIllustrativeSurface(surfaceFixture),
  dataQuality: parseDataQuality(dataQualityFixture),
  surfaceFrames: parseSurfaceFrames(surfaceFramesFixture),
}

describe('useAppData', () => {
  it('starts as loading, then becomes ready with the loaded data', async () => {
    const load = vi.fn().mockResolvedValue(DATA)
    const { result } = renderHook(() => useAppData(load))
    expect(result.current).toEqual({ status: 'loading' })
    await waitFor(() => expect(result.current.status).toBe('ready'))
    expect(result.current).toEqual({ status: 'ready', data: DATA })
    expect(load).toHaveBeenCalledTimes(1)
  })

  it('becomes an error state carrying the rejection', async () => {
    const boom = new Error('nope')
    const load = vi.fn().mockRejectedValue(boom)
    const { result } = renderHook(() => useAppData(load))
    await waitFor(() => expect(result.current.status).toBe('error'))
    expect(result.current).toEqual({ status: 'error', error: boom })
  })

  it('ignores a stale result: when `load` changes, an older request that finishes late cannot overwrite the newer one', async () => {
    const OTHER = { ...DATA, manifest: { ...DATA.manifest, source_commit: 'ffffffffffff' } }
    let resolveSlow!: (d: typeof DATA) => void
    const slow = vi.fn(() => new Promise<typeof DATA>((r) => (resolveSlow = r)))
    const fast = vi.fn().mockResolvedValue(OTHER)
    const { result, rerender } = renderHook(({ load }) => useAppData(load), { initialProps: { load: slow as () => Promise<typeof DATA> } })
    rerender({ load: fast })
    await waitFor(() => expect(result.current.status).toBe('ready'))
    // the superseded request finishes last; act() flushes any state update it (wrongly) triggers
    await act(async () => {
      resolveSlow(DATA)
    })
    expect(result.current).toEqual({ status: 'ready', data: OTHER })
  })
  it('ignores a stale failure too: an older request that fails late cannot replace newer data with an error', async () => {
    let rejectSlow!: (e: Error) => void
    const slow = vi.fn(() => new Promise<typeof DATA>((_, rej) => (rejectSlow = rej)))
    const fast = vi.fn().mockResolvedValue(DATA)
    const { result, rerender } = renderHook(({ load }) => useAppData(load), { initialProps: { load: slow as () => Promise<typeof DATA> } })
    rerender({ load: fast })
    await waitFor(() => expect(result.current.status).toBe('ready'))
    await act(async () => {
      rejectSlow(new Error('too late'))
    })
    expect(result.current).toEqual({ status: 'ready', data: DATA })
  })
})
