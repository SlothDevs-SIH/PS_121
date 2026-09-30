import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'
import { create } from 'zustand'

import type { PackProgress } from './pack'
import { listPacks, packSupported, removePack, type PackMeta } from './packStore'

export const packsQueryKey = ['offline-packs'] as const

/** The downloaded well packs on this device (Cache Storage; no network involved). */
export function usePacks() {
  return useQuery({
    queryKey: packsQueryKey,
    queryFn: () => listPacks(),
    enabled: packSupported(),
    staleTime: Infinity,
    retry: false,
  })
}

interface Download {
  progress: PackProgress | null
  error: string | null
  controller: AbortController | null
}

const IDLE: Download = { progress: null, error: null, controller: null }

/** Running downloads by well, outside React so progress survives moving Map ↔ Well 360. */
const useDownloads = create<{
  byWell: Record<number, Download>
  patch: (wellId: number, d: Partial<Download>) => void
}>()((set) => ({
  byWell: {},
  patch: (wellId, d) =>
    set((s) => ({ byWell: { ...s.byWell, [wellId]: { ...(s.byWell[wellId] ?? IDLE), ...d } } })),
}))

export function resetDownloads(): void {
  useDownloads.setState({ byWell: {} })
}

export interface WellPack {
  supported: boolean
  meta: PackMeta | null
  busy: boolean
  progress: PackProgress | null
  error: string | null
  download: () => Promise<void>
  cancel: () => void
  remove: () => Promise<void>
}

export function useWellPack(wellId: number): WellPack {
  const client = useQueryClient()
  const packs = usePacks()
  const state = useDownloads((s) => s.byWell[wellId]) ?? IDLE
  const patch = useDownloads((s) => s.patch)

  const download = useCallback(async () => {
    const controller = new AbortController()
    patch(wellId, { controller, error: null, progress: null })
    try {
      // The planner and downloader load on first use, off the shell's critical path.
      const { downloadWellPack } = await import('./pack')
      await downloadWellPack(wellId, {
        signal: controller.signal,
        onProgress: (progress) => patch(wellId, { progress }),
      })
    } catch (err) {
      patch(wellId, {
        error:
          err instanceof Error && err.name === 'PackError'
            ? err.message
            : `The pack failed: ${String(err)}`,
      })
    } finally {
      patch(wellId, { controller: null, progress: null })
      await client.invalidateQueries({ queryKey: packsQueryKey })
    }
  }, [wellId, patch, client])

  const remove = useCallback(async () => {
    await removePack(wellId)
    patch(wellId, { error: null })
    await client.invalidateQueries({ queryKey: packsQueryKey })
  }, [wellId, patch, client])

  return {
    supported: packSupported(),
    meta: packs.data?.find((p) => p.wellId === wellId) ?? null,
    busy: state.controller !== null,
    progress: state.progress,
    error: state.error,
    download,
    cancel: () => state.controller?.abort(),
    remove,
  }
}
