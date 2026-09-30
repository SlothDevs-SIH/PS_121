import { motion } from 'motion/react'
import { Fragment, useMemo } from 'react'

import type { CopilotCitation } from '../../lib/copilot'
import { parseAnswer, type Inline } from '../../lib/copilotMarkdown'
import { CitationChip } from './CitationChip'

// Each streamed line fades in; lines already shown keep their key, so they do not replay.
const reveal = {
  initial: { opacity: 0, y: 4 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.2 } },
} as const

function Inlines({ parts, cites }: { parts: Inline[]; cites: Map<number, CopilotCitation> }) {
  return parts.map((part, i) =>
    part.kind === 'text' ? (
      <Fragment key={i}>{part.text}</Fragment>
    ) : part.kind === 'bold' ? (
      <strong key={i} className="font-semibold">
        {part.text}
      </strong>
    ) : (
      <CitationChip key={i} n={part.n} citation={cites.get(part.n)} />
    ),
  )
}

/** A copilot answer as text (never HTML), with `[n]` marks as citation chips. */
export function AnswerText({
  text,
  citations,
  streaming = false,
}: {
  text: string
  citations: CopilotCitation[]
  streaming?: boolean
}) {
  const blocks = useMemo(() => parseAnswer(text), [text])
  const cites = useMemo(() => new Map(citations.map((c) => [c.n, c])), [citations])
  return (
    <div className="space-y-2 text-sm leading-relaxed text-text" data-testid="copilot-answer">
      {blocks.map((b, i) =>
        b.kind === 'p' ? (
          <motion.p key={i} {...reveal}>
            <Inlines parts={b.inlines} cites={cites} />
          </motion.p>
        ) : (
          <motion.div key={i} {...reveal}>
            {b.kind === 'ul' ? (
              <ul className="list-disc space-y-1 pl-5">
                {b.items.map((item, j) => (
                  <li key={j}>
                    <Inlines parts={item} cites={cites} />
                  </li>
                ))}
              </ul>
            ) : (
              <ol className="list-decimal space-y-1 pl-5">
                {b.items.map((item, j) => (
                  <li key={j}>
                    <Inlines parts={item} cites={cites} />
                  </li>
                ))}
              </ol>
            )}
          </motion.div>
        ),
      )}
      {streaming && (
        <span
          aria-hidden
          className="inline-block h-4 w-1.5 animate-pulse rounded-sm bg-accent align-middle"
          data-testid="copilot-caret"
        />
      )}
    </div>
  )
}
