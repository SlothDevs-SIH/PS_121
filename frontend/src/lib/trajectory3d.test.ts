import { describe, expect, it } from 'vitest'

import { atMd, bounds, displacement, project, toLocal, viewport, VIEWS } from './trajectory3d'

const P = { east: 300, north: -400, tvdss: 2000 }

describe('camera', () => {
  it('plan view shows east right and north up', () => {
    const q = project(P, VIEWS.plan)
    expect(q.x).toBeCloseTo(300)
    expect(q.y).toBeCloseTo(400) // south of the wellhead is down the screen
  })

  it('section view looking north shows east right and depth down', () => {
    const q = project(P, VIEWS.section)
    expect(q.x).toBeCloseTo(300)
    expect(q.y).toBeCloseTo(2000)
    expect(q.z).toBeCloseTo(-400) // nearer the viewer than the wellhead
  })

  it('turning by 90° brings north to the right-hand side', () => {
    const q = project({ east: 0, north: 100, tvdss: 0 }, { yaw: -90, pitch: 0 })
    expect(q.x).toBeCloseTo(100)
  })

  it('keeps one scale however the scene turns', () => {
    const pts = [
      { east: 0, north: 0, tvdss: -100 },
      { east: 400, north: -300, tvdss: 3600 },
    ]
    const map = viewport(pts, 800, 600)
    const len = (v: typeof VIEWS.plan) => {
      const a = map(pts[0]!, v)
      const b = map(pts[1]!, v)
      return Math.hypot(a.x - b.x, a.y - b.y)
    }
    // The projected length changes with the view, but never exceeds the fitted diameter.
    for (const v of [VIEWS.plan, VIEWS.section, VIEWS.perspective])
      expect(len(v)).toBeLessThanOrEqual(600 - 48 + 1e-6)
    expect(bounds(pts).radius).toBeCloseTo(Math.hypot(400, 300, 3700) / 2)
  })
})

describe('geometry helpers', () => {
  it('converts lat/lon to local metres', () => {
    const d = toLocal(27.4, 95.25, 27.41, 95.25)
    expect(d.north).toBeCloseTo(1111.95, 0)
    expect(Math.abs(d.east)).toBeLessThan(1e-6)
    expect(toLocal(27.4, 95.25, 27.4, 95.26).east).toBeCloseTo(987.2, 0) // 1,111.95 m × cos 27.4°
  })

  it('interpolates along the stations by MD and clamps at the ends', () => {
    const st = [
      { md_m: 0, east_m: 0, north_m: 0, tvdss_m: -100 },
      { md_m: 1000, east_m: 100, north_m: 0, tvdss_m: 880 },
    ]
    expect(atMd(st, 500)).toEqual({ east: 50, north: 0, tvdss: 390 })
    expect(atMd(st, 5000)?.tvdss).toBe(880)
    expect(atMd([], 10)).toBeNull()
  })

  it('reports the final displacement and its azimuth', () => {
    const d = displacement([{ md_m: 0, east_m: 300, north_m: -300, tvdss_m: 0 }])
    expect(d.distance).toBeCloseTo(424.26, 1)
    expect(d.azimuth).toBeCloseTo(135)
  })
})
