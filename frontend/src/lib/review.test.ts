import { buildCorrection, canCorrect, initialDraft, labelFor } from './review'

const PROPOSED = {
  od_in: null,
  returns: 'full',
  toc_md_m: 2383,
  shoe_md_m: 3900,
  hole_size_in: 8.5,
}

describe('review corrections', () => {
  it('only sends the fields that changed, parsed to canonical values', () => {
    const draft = { ...initialDraft('casing', PROPOSED), od_in: '7', shoe_md_m: '3,900' }
    expect(buildCorrection('casing', PROPOSED, draft)).toEqual({ fields: { od_in: 7 }, errors: {} })
    const cleared = { ...initialDraft('casing', PROPOSED), returns: '' }
    expect(buildCorrection('casing', PROPOSED, cleared).fields).toEqual({ returns: null })
  })

  it('rejects numbers out of range, non-numbers and unknown options', () => {
    const draft = {
      ...initialDraft('casing', PROPOSED),
      od_in: '50',
      toc_md_m: 'abc',
      returns: 'lots',
    }
    const { fields, errors } = buildCorrection('casing', PROPOSED, draft)
    expect(fields).toEqual({})
    expect(Object.keys(errors).sort()).toEqual(['od_in', 'returns', 'toc_md_m'])
  })

  it('knows which kinds can be corrected and names their fields', () => {
    expect(canCorrect('mud')).toBe(true)
    expect(canCorrect('alias')).toBe(false)
    expect(labelFor('mud', 'mw_sg')).toBe('Mud weight')
    expect(labelFor('alias', 'raw_name')).toBe('raw name')
    expect(initialDraft('mitigation', { outcome: 'fail', action_code: 'REAM' })).toMatchObject({
      outcome: 'fail',
      action_code: 'REAM',
      npt_hours_after: '',
    })
  })
})
