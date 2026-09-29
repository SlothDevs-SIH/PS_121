/**
 * Drilling event types: label, short code, colour token and marker shape. Colour is never
 * the only signal (FRONTEND_PLAN §3.4): markers also differ by shape and carry the code.
 *   triangle = well control (kick, gas, overpressure) · circle = losses
 *   square = mechanical (stuck, tight, torque, instability, balling, fishing)
 *   diamond = cement, casing, equipment and waiting
 */
export type MarkerShape = 'circle' | 'square' | 'diamond' | 'triangle'

export interface EventTypeMeta {
  label: string
  short: string
  colorVar: string
  shape: MarkerShape
}

export const EVENT_TYPES: Record<string, EventTypeMeta> = {
  LOSS: { label: 'Lost circulation', short: 'LC', colorVar: 'var(--ev-loss)', shape: 'circle' },
  KICK: { label: 'Kick', short: 'KK', colorVar: 'var(--ev-kick)', shape: 'triangle' },
  GAS: { label: 'Gas', short: 'GS', colorVar: 'var(--ev-gas)', shape: 'triangle' },
  OVERP: { label: 'Overpressure', short: 'OP', colorVar: 'var(--ev-overp)', shape: 'triangle' },
  STUCK: { label: 'Stuck pipe', short: 'SP', colorVar: 'var(--ev-stuck)', shape: 'square' },
  TIGHT: { label: 'Tight hole', short: 'TH', colorVar: 'var(--ev-tight)', shape: 'square' },
  TORQUE: { label: 'High torque', short: 'TQ', colorVar: 'var(--ev-torque)', shape: 'square' },
  INSTAB: { label: 'Instability', short: 'WI', colorVar: 'var(--ev-instab)', shape: 'square' },
  BALLING: { label: 'Bit balling', short: 'BB', colorVar: 'var(--ev-balling)', shape: 'square' },
  FISH: { label: 'Fishing', short: 'FI', colorVar: 'var(--ev-other)', shape: 'square' },
  CEMENT: { label: 'Cementing', short: 'CM', colorVar: 'var(--ev-cement)', shape: 'diamond' },
  CASING: { label: 'Casing', short: 'CS', colorVar: 'var(--ev-cement)', shape: 'diamond' },
  EQUIP: { label: 'Equipment', short: 'EQ', colorVar: 'var(--ev-other)', shape: 'diamond' },
  WAIT: { label: 'Waiting', short: 'WT', colorVar: 'var(--ev-other)', shape: 'diamond' },
  OTHER_NPT: { label: 'Other NPT', short: 'NP', colorVar: 'var(--ev-other)', shape: 'diamond' },
}

const FALLBACK: EventTypeMeta = {
  label: 'Event',
  short: '?',
  colorVar: 'var(--ev-other)',
  shape: 'diamond',
}

export function eventMeta(type: string): EventTypeMeta {
  return EVENT_TYPES[type] ?? { ...FALLBACK, label: type }
}

/** SVG path of a marker centred on (0, 0) with "radius" r. */
export function markerPath(shape: MarkerShape, r: number): string {
  switch (shape) {
    case 'circle':
      return `M ${-r} 0 A ${r} ${r} 0 1 0 ${r} 0 A ${r} ${r} 0 1 0 ${-r} 0 Z`
    case 'square':
      return `M ${-r} ${-r} H ${r} V ${r} H ${-r} Z`
    case 'diamond':
      return `M 0 ${-r * 1.25} L ${r * 1.25} 0 L 0 ${r * 1.25} L ${-r * 1.25} 0 Z`
    case 'triangle':
      return `M 0 ${-r * 1.2} L ${r * 1.1} ${r * 0.9} L ${-r * 1.1} ${r * 0.9} Z`
  }
}

/** Marker radius (px) from NPT hours: 4 px with no NPT, growing with √h up to 10 px. */
export function markerRadius(nptHours: number | null | undefined): number {
  if (!nptHours || nptHours <= 0) return 4
  return Math.min(10, 4 + Math.sqrt(nptHours) * 1.2)
}
