/** Lithology classes for depth-track fill patterns (components/correlation/Lithology.tsx). */
export type Lithology = 'sand' | 'clay' | 'shale' | 'lime' | 'igneous' | 'none'

/** Dominant lithology from the formation dictionary text ("shale, coal, sandstone" → shale). */
export function lithologyOf(text: string | null | undefined): Lithology {
  const first = (text ?? '').toLowerCase().split(',')[0]?.trim() ?? ''
  if (first.includes('sand')) return 'sand'
  if (first.includes('clay')) return 'clay'
  if (first.includes('shale')) return 'shale'
  if (first.includes('lime')) return 'lime'
  if (first.includes('granit') || first.includes('basement')) return 'igneous'
  return 'none'
}
