/**
 * The little Markdown a copilot answer may carry: paragraphs (one per line, as the backend
 * streams one sentence per line), "-"/"*" and "1." lists, **bold**, and `[n]` citation marks.
 * It produces plain data for `AnswerText` to render as React elements, so answer text is
 * never parsed as HTML (FRONTEND_PLAN §11: no `dangerouslySetInnerHTML`).
 *
 * Partial input is fine while streaming: an unclosed `**` stays literal until it closes.
 */

export type Inline =
  { kind: 'text'; text: string } | { kind: 'bold'; text: string } | { kind: 'cite'; n: number }

export type Block =
  | { kind: 'p'; inlines: Inline[] }
  | { kind: 'ul'; items: Inline[][] }
  | { kind: 'ol'; items: Inline[][] }

const TOKEN = /\*\*(.+?)\*\*|\[(\d+)\]/g
const BULLET = /^\s*[-*•]\s+(.*)$/
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/

export function parseInline(text: string): Inline[] {
  const out: Inline[] = []
  let at = 0
  for (const m of text.matchAll(TOKEN)) {
    const i = m.index
    if (i > at) out.push({ kind: 'text', text: text.slice(at, i) })
    if (m[1] !== undefined) out.push({ kind: 'bold', text: m[1] })
    else out.push({ kind: 'cite', n: Number(m[2]) })
    at = i + m[0].length
  }
  if (at < text.length) out.push({ kind: 'text', text: text.slice(at) })
  return out
}

export function parseAnswer(text: string): Block[] {
  const blocks: Block[] = []
  for (const raw of text.split('\n')) {
    const line = raw.trimEnd()
    if (!line.trim()) continue
    const bullet = BULLET.exec(line)
    const numbered = bullet ? null : NUMBERED.exec(line)
    const item = bullet?.[1] ?? numbered?.[1]
    if (item === undefined) {
      blocks.push({ kind: 'p', inlines: parseInline(line.trim()) })
      continue
    }
    const kind = bullet ? 'ul' : 'ol'
    const last = blocks[blocks.length - 1]
    if (last && last.kind === kind) last.items.push(parseInline(item))
    else blocks.push({ kind, items: [parseInline(item)] })
  }
  return blocks
}

/** The answer as a screen reader should hear it once: marks and Markdown stripped. */
export function plainText(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/\s*(\[\d+\])+/g, '')
    .replace(/\s*\n\s*/g, ' ')
    .trim()
}
