import { describe, expect, it } from 'vitest'

import { ALERT_PAGE, DEJAVU_ALERT, KICK_ALERT, alertFixture } from '../test/utils'
import { scoreText, sortAlerts } from './alerts'
import type { AlertOut } from './api/client'

describe('alert helpers', () => {
  it('pins critical well control first, then newest first', () => {
    const items = ALERT_PAGE.body.items as unknown as AlertOut[]
    expect(sortAlerts(items).map((a) => a.id)).toEqual([9, 10, 8])
  })

  it('never calls a similarity a probability', () => {
    expect(scoreText(DEJAVU_ALERT as unknown as AlertOut)).toMatch(
      /^0\.8\d similarity \(not a probability\)$/,
    )
    expect(scoreText(alertFixture(1) as unknown as AlertOut)).toBe('41% model probability')
    expect(scoreText(KICK_ALERT as unknown as AlertOut)).toBe('6.20 physics indicator')
  })
})
