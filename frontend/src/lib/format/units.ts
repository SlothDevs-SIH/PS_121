/**
 * Display-only unit formatting. The backend stores and sends canonical SI units; these
 * factors mirror backend/app/core/units.py exactly (tested against shared reference values).
 */

export type UnitSystem = 'metric' | 'oilfield'

export const FT_TO_M = 0.3048
export const PPG_PER_SG = 8.345
export const BBL_TO_M3 = 0.158987

const nf = (digits: number) =>
  new Intl.NumberFormat('en-IN', { minimumFractionDigits: digits, maximumFractionDigits: digits })

export function formatNumber(value: number, digits = 0): string {
  return nf(digits).format(value)
}

/** Depth with its reference, e.g. "2,340 m MD" or "7,677 ft TVDSS". Never a bare depth. */
export function formatDepth(
  metres: number,
  system: UnitSystem,
  reference: 'MD' | 'TVD' | 'TVDSS',
): string {
  const value = system === 'metric' ? metres : metres / FT_TO_M
  return `${formatNumber(value)} ${system === 'metric' ? 'm' : 'ft'} ${reference}`
}

/** Horizontal distance: metres below 1 km, else km with one decimal (always metric). */
export function formatDistance(metres: number): string {
  return metres < 1000 ? `${formatNumber(metres)} m` : `${formatNumber(metres / 1000, 1)} km`
}

export function formatMudWeight(sg: number, system: UnitSystem): string {
  return system === 'metric'
    ? `${formatNumber(sg, 2)} SG`
    : `${formatNumber(sg * PPG_PER_SG, 1)} ppg`
}

export function formatVolume(bbl: number, system: UnitSystem): string {
  return system === 'metric' ? `${formatNumber(bbl * BBL_TO_M3, 1)} m³` : `${formatNumber(bbl)} bbl`
}

export function formatBearing(deg: number | null | undefined): string {
  if (deg === null || deg === undefined) return '—'
  const dirs = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
  const norm = ((deg % 360) + 360) % 360
  return `${formatNumber(norm)}° ${dirs[Math.round(norm / 45) % 8]}`
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${formatNumber(bytes / 1024)} KB`
  return `${formatNumber(bytes / 1024 / 1024, 1)} MB`
}
