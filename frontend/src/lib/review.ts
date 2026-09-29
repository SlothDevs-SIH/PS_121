/**
 * Review queue editing rules, mirroring the backend's correction models per item kind
 * (app/extract/review_service.py _FIXES): only these fields can be corrected, in canonical
 * units. Alias and "other" items can only be accepted or rejected.
 */
import type { components } from './api/schema'
import { EVENT_TYPES } from './eventTypes'

export type ActionCode = components['schemas']['MitigationOut']['action_code']

export const ACTION_CODES: ActionCode[] = [
  'LCM_PILL_FINE',
  'LCM_PILL_COARSE',
  'LCM_BACKGROUND',
  'REDUCE_MW',
  'REDUCE_FLOW_RATE',
  'CEMENT_PLUG',
  'SQUEEZE',
  'SET_CASING_EARLY',
  'DRILL_BLIND',
  'JAR_UP',
  'JAR_DOWN',
  'SPOT_PIPE_RELEASE_PILL',
  'WORK_PIPE',
  'INCREASE_FLOW',
  'BACKOFF_AND_FISH',
  'SIDETRACK',
  'DRILLERS_METHOD',
  'WAIT_AND_WEIGHT',
  'BULLHEAD',
  'REMEDIAL_SQUEEZE',
  'TOP_JOB',
  'LIGHTWEIGHT_SLURRY',
  'REAM',
  'WIPER_TRIP',
  'ADD_LUBRICANT',
  'REDUCE_RPM',
  'ADD_DETERGENT',
  'INCREASE_MW',
  'CIRCULATE',
  'CHANGE_BHA',
  'FISHING',
  'REPAIR_EQUIPMENT',
  'WAIT',
  'OTHER',
]

export interface FieldSpec {
  label: string
  kind: 'number' | 'text' | 'select' | 'date'
  unit?: string
  options?: readonly string[]
  min?: number
  max?: number
}

const CASING: Record<string, FieldSpec> = {
  od_in: { label: 'Casing OD', kind: 'number', unit: 'in', min: 0, max: 40 },
  hole_size_in: { label: 'Hole size', kind: 'number', unit: 'in', min: 0, max: 40 },
  shoe_md_m: { label: 'Shoe depth', kind: 'number', unit: 'm MD', min: 0, max: 15000 },
  toc_md_m: { label: 'Top of cement', kind: 'number', unit: 'm MD', min: 0, max: 15000 },
  returns: { label: 'Cement returns', kind: 'select', options: ['full', 'partial', 'none'] },
}

export const FIELD_SPECS: Record<string, Record<string, FieldSpec>> = {
  event: {
    event_type: { label: 'Event type', kind: 'select', options: Object.keys(EVENT_TYPES) },
    subtype: { label: 'Subtype', kind: 'text' },
    severity: { label: 'Severity', kind: 'select', options: ['low', 'medium', 'high'] },
    md_m: { label: 'Depth', kind: 'number', unit: 'm MD', min: 0, max: 15000 },
    event_date: { label: 'Date', kind: 'date' },
    npt_hours: { label: 'NPT', kind: 'number', unit: 'h', min: 0 },
  },
  mitigation: {
    action_code: { label: 'Action', kind: 'select', options: ACTION_CODES },
    action_text: { label: 'As written', kind: 'text' },
    outcome: {
      label: 'Outcome',
      kind: 'select',
      options: ['success', 'partial', 'fail', 'unknown'],
    },
    npt_hours_after: { label: 'NPT after', kind: 'number', unit: 'h', min: 0 },
  },
  casing: CASING,
  cement: CASING,
  mud: {
    md_from_m: { label: 'From', kind: 'number', unit: 'm MD', min: 0, max: 15000 },
    md_to_m: { label: 'To', kind: 'number', unit: 'm MD', min: 0, max: 15000 },
    hole_size_in: { label: 'Hole size', kind: 'number', unit: 'in', min: 0, max: 40 },
    mud_type: { label: 'Mud type', kind: 'text' },
    mw_sg: { label: 'Mud weight', kind: 'number', unit: 'SG', min: 0.8, max: 2.6 },
  },
}

export function canCorrect(kind: string): boolean {
  return kind in FIELD_SPECS
}

export function labelFor(kind: string, key: string): string {
  return FIELD_SPECS[kind]?.[key]?.label ?? key.replace(/_/g, ' ')
}

export type Draft = Record<string, string>

/** Editable fields of an item, as input strings (empty for unknown values). */
export function initialDraft(kind: string, proposed: Record<string, unknown>): Draft {
  const specs = FIELD_SPECS[kind] ?? {}
  const out: Draft = {}
  for (const key of Object.keys(specs)) {
    const v = proposed[key]
    out[key] = v === null || v === undefined ? '' : String(v)
  }
  return out
}

/** The fields a reviewer changed, parsed to canonical values, plus per-field errors. */
export function buildCorrection(
  kind: string,
  proposed: Record<string, unknown>,
  draft: Draft,
): { fields: Record<string, unknown>; errors: Record<string, string> } {
  const specs = FIELD_SPECS[kind] ?? {}
  const fields: Record<string, unknown> = {}
  const errors: Record<string, string> = {}
  for (const [key, spec] of Object.entries(specs)) {
    if (!(key in draft)) continue
    const raw = (draft[key] ?? '').trim()
    const before = proposed[key] ?? null
    let value: unknown = raw === '' ? null : raw
    if (spec.kind === 'number' && raw !== '') {
      const n = Number(raw.replace(/,/g, ''))
      if (!Number.isFinite(n)) {
        errors[key] = 'not a number'
        continue
      }
      if ((spec.min !== undefined && n < spec.min) || (spec.max !== undefined && n > spec.max)) {
        errors[key] = `must be between ${spec.min ?? '−∞'} and ${spec.max ?? '∞'}`
        continue
      }
      value = n
    }
    if (spec.kind === 'select' && raw !== '' && spec.options && !spec.options.includes(raw)) {
      errors[key] = 'not an allowed value'
      continue
    }
    const same =
      typeof value === 'number' && typeof before === 'number'
        ? Math.abs(value - before) < 1e-9
        : String(value ?? '') === String(before ?? '')
    if (!same) fields[key] = value
  }
  return { fields, errors }
}
