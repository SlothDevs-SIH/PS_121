import { describe, expect, it } from 'vitest'

import { parseAnswer, parseInline, plainText } from './copilotMarkdown'

describe('copilot answer markdown', () => {
  it('makes one paragraph per line and groups list lines', () => {
    const blocks = parseAnswer('Intro:\n- one [1]\n- two\n\n1. first\n2) second\nEnd.\n')
    expect(blocks.map((b) => b.kind)).toEqual(['p', 'ul', 'ol', 'p'])
    expect(blocks[1]).toEqual({
      kind: 'ul',
      items: [
        [
          { kind: 'text', text: 'one ' },
          { kind: 'cite', n: 1 },
        ],
        [{ kind: 'text', text: 'two' }],
      ],
    })
  })

  it('reads bold and adjacent citation marks, and leaves an unclosed ** literal', () => {
    expect(parseInline('**LCM pill** worked [1][12].')).toEqual([
      { kind: 'bold', text: 'LCM pill' },
      { kind: 'text', text: ' worked ' },
      { kind: 'cite', n: 1 },
      { kind: 'cite', n: 12 },
      { kind: 'text', text: '.' },
    ])
    expect(parseInline('**LCM pi')).toEqual([{ kind: 'text', text: '**LCM pi' }])
  })

  it('keeps markup as text: nothing is parsed as HTML', () => {
    expect(parseInline('<img src=x onerror=alert(1)>')).toEqual([
      { kind: 'text', text: '<img src=x onerror=alert(1)>' },
    ])
  })

  it('strips marks and markup for the screen-reader announcement', () => {
    expect(plainText('**LCM** worked [1][2]\nCaveat.\n')).toBe('LCM worked Caveat.')
  })
})
