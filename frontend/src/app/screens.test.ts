import { SCREENS, screensFor } from './screens'
import openapi from '../lib/api/openapi.json'

const PHASES = new Set(['F0', 'F1', 'P2', 'F2', 'F3', 'F4', 'F5', 'F6'])

describe('screen registry', () => {
  it('has unique ids and paths', () => {
    expect(new Set(SCREENS.map((s) => s.id)).size).toBe(SCREENS.length)
    expect(new Set(SCREENS.map((s) => s.path)).size).toBe(SCREENS.length)
  })

  it('covers all 10 screens of master plan §10', () => {
    const numbers = SCREENS.map((s) => s.planNo)
      .filter((n) => n > 0)
      .sort((a, b) => a - b)
    expect(numbers).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
  })

  it('uses valid phases; Part 3 (F2) built Well 360, the Correlation Panel and Search', () => {
    expect(SCREENS.every((s) => PHASES.has(s.phase))).toBe(true)
    expect(SCREENS.filter((s) => s.status === 'built').map((s) => s.id)).toEqual([
      'dashboard',
      'map',
      'well360',
      'correlation',
      'search',
      'documents',
      'system',
    ])
    expect(SCREENS.filter((s) => s.status === 'in_progress')).toEqual([])
  })

  it('only references endpoints that exist in the backend OpenAPI contract', () => {
    const paths = Object.keys((openapi as { paths: Record<string, unknown> }).paths)
    const toPattern = (p: string) => new RegExp('^' + p.replace(/\{[^}]+\}/g, '[^/]+') + '$')
    const patterns = paths.map(toPattern)
    const wsPaths = ['/ws/wells/1/live', '/ws/alerts']
    for (const s of SCREENS) {
      for (const e of s.endpoints) {
        const bare = e.path.split('?')[0] ?? ''
        const known =
          e.method === 'WS' ? wsPaths.includes(bare) : patterns.some((re) => re.test(bare))
        expect(known, `${s.id}: ${e.method} ${e.path}`).toBe(true)
      }
    }
  })

  it('field mode shows a reduced navigation', () => {
    const field = screensFor('field').map((s) => s.id)
    expect(field).toContain('live')
    expect(field).not.toContain('admin')
    // RTMAC engineers work in the office and watch live wells (master plan §2.3).
    expect(screensFor('office').map((s) => s.id)).toContain('live')
    expect(field.length).toBeLessThan(screensFor('office').length)
  })
})
