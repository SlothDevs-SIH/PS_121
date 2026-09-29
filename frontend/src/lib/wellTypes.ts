import { Droplet, Flame, Waves, type LucideIcon } from 'lucide-react'

import type { WellTypeFilter } from '../stores/ui'

export type FluidType = 'oil' | 'gas' | 'water'

export interface FluidMeta {
  id: FluidType
  label: string
  plural: string
  /** CSS variable holding the colour (tokens only; see styles/index.css). */
  colorVar: string
  textClass: string
  bgClass: string
  icon: LucideIcon
}

export const FLUIDS: Record<FluidType, FluidMeta> = {
  oil: {
    id: 'oil',
    label: 'Oil',
    plural: 'Oil wells',
    colorVar: 'var(--well-oil)',
    textClass: 'text-oil',
    bgClass: 'bg-oil',
    icon: Droplet,
  },
  gas: {
    id: 'gas',
    label: 'Gas',
    plural: 'Gas wells',
    colorVar: 'var(--well-gas)',
    textClass: 'text-gas',
    bgClass: 'bg-gas',
    icon: Flame,
  },
  water: {
    id: 'water',
    label: 'Water',
    plural: 'Water wells',
    colorVar: 'var(--well-water)',
    textClass: 'text-water',
    bgClass: 'bg-water',
    icon: Waves,
  },
}

export const FLUID_ORDER: FluidType[] = ['oil', 'gas', 'water']

/** Wells without a known fluid (planned, drilling) only show under "All". */
export function matchesFilter(fluid: string | null | undefined, filter: WellTypeFilter): boolean {
  return filter === 'all' || fluid === filter
}

export function fluidOf(value: string | null | undefined): FluidType | null {
  return value === 'oil' || value === 'gas' || value === 'water' ? value : null
}
