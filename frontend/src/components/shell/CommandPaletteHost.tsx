import { lazy, Suspense, useEffect, useState } from 'react'

import { useUiStore } from '../../stores/ui'

// cmdk (and its dialog dependencies) stay out of the shell bundle until first use.
const CommandPalette = lazy(() => import('./CommandPalette'))

/** Owns the ⌘K / Ctrl+K shortcut and mounts the palette once it has been opened. */
export function CommandPaletteHost() {
  const open = useUiStore((s) => s.paletteOpen)
  const setOpen = useUiStore((s) => s.setPaletteOpen)
  const [used, setUsed] = useState(open)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setUsed(true)
        setOpen(!useUiStore.getState().paletteOpen)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [setOpen])

  if (!used && !open) return null
  return (
    <Suspense fallback={null}>
      <CommandPalette />
    </Suspense>
  )
}
