import { describe, expect, it } from 'vitest'

import { RISK_PROFILE } from '../test/utils'
import { curveSteps, intervalBase, peakRisk, pct, riskColor, riskStep, topTypes } from './risk'

const profile = RISK_PROFILE.body as Parameters<typeof topTypes>[0]

describe('risk helpers', () => {
  it('maps probabilities onto the 5-step scale', () => {
    expect([0, 0.049, 0.05, 0.2, 0.3, 0.49, 0.5, 1].map(riskStep)).toEqual([0, 0, 1, 2, 3, 3, 4, 4])
    expect(riskColor(0.6)).toBe('var(--risk-4)')
  })

  it('picks the types with the highest peak, above a floor', () => {
    expect(topTypes(profile)).toEqual(['TIGHT', 'LOSS'])
    expect(topTypes(profile, 1)).toEqual(['TIGHT'])
    expect(topTypes(profile, 3, 0.4)).toEqual(['TIGHT'])
  })

  it('builds one step per interval, open base extended', () => {
    const steps = curveSteps(profile, 'LOSS')
    expect(steps.map((s) => [s.formation, s.top, s.base, s.p, s.prognosed])).toEqual([
      ['Girujan Clay', 1200, 2150, 0.04, false],
      ['Tipam Sandstone', 2150, 2300, 0.36, true],
    ])
    expect(intervalBase(profile.intervals[1]!, 50)).toBe(2200)
  })

  it('finds the peak risk of an interval and formats percentages', () => {
    expect(peakRisk(profile.intervals[0]!)?.event_type).toBe('TIGHT')
    expect(peakRisk({ ...profile.intervals[0]!, risks: [] })).toBeNull()
    expect(pct(0.456)).toBe('46%')
    expect(pct(null)).toBe('—')
  })
})
