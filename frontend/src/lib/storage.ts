/**
 * localStorage for per-viewer conveniences only (theme, mode). Every access is guarded:
 * storage can be unavailable (private windows, blocked site data) and the app must still work.
 */
export function readPref(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

export function writePref(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // Preference simply isn't remembered; nothing else depends on it.
  }
}
