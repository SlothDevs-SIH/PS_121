/**
 * Service-worker lifecycle state for the UI (update prompt), and the theme-colour sync for
 * the installed app's status bar. Registration itself lives in ./register.ts (main.tsx only).
 */
import { create } from 'zustand'

interface PwaState {
  /** Set when a new version is installed and waiting: calling it activates it and reloads. */
  applyUpdate: (() => void) | null
  setUpdate: (apply: (() => void) | null) => void
}

export const usePwaStore = create<PwaState>()((set) => ({
  applyUpdate: null,
  setUpdate: (applyUpdate) => set({ applyUpdate }),
}))

/**
 * Keeps <meta name="theme-color"> equal to the active theme's --bg token, so the Android
 * status bar and task switcher follow Deep Rig / Daylight Field / Command Blue.
 * Returns a stop function.
 */
export function syncThemeColor(root: HTMLElement = document.documentElement): () => void {
  const apply = () => {
    const meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')
    const bg = getComputedStyle(root).getPropertyValue('--bg').trim()
    if (meta && bg) meta.content = bg
  }
  apply()
  const observer = new MutationObserver(apply)
  observer.observe(root, { attributes: true, attributeFilter: ['data-theme'] })
  return () => observer.disconnect()
}
