import {
  formatBearing,
  formatBytes,
  formatDepth,
  formatDistance,
  formatMudWeight,
  formatNumber,
  formatVolume,
} from './units'

describe('unit formatting (mirrors backend/app/core/units.py)', () => {
  it('uses Indian digit grouping', () => {
    expect(formatNumber(123456)).toBe('1,23,456')
  })

  it('always names the depth reference', () => {
    expect(formatDepth(2340, 'metric', 'MD')).toBe('2,340 m MD')
    expect(formatDepth(304.8, 'oilfield', 'TVDSS')).toBe('1,000 ft TVDSS')
  })

  it('formats distances', () => {
    expect(formatDistance(850.4)).toBe('850 m')
    expect(formatDistance(3240)).toBe('3.2 km')
  })

  it('converts mud weight and volume with the backend factors', () => {
    expect(formatMudWeight(1.2, 'metric')).toBe('1.20 SG')
    expect(formatMudWeight(1.2, 'oilfield')).toBe('10.0 ppg') // 1.2 × 8.345 = 10.014
    expect(formatVolume(100, 'metric')).toBe('15.9 m³') // 100 × 0.158987
    expect(formatVolume(100, 'oilfield')).toBe('100 bbl')
  })

  it('formats bearings and sizes', () => {
    expect(formatBearing(0)).toBe('0° N')
    expect(formatBearing(-90)).toBe('270° W')
    expect(formatBearing(null)).toBe('—')
    expect(formatBytes(2048)).toBe('2 KB')
  })
})
