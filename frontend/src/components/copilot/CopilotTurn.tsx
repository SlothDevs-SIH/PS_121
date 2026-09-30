import { AlertTriangle, Check, Copy, SearchX, Square } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import {
  answerForClipboard,
  describeError,
  recordHref,
  refusalReason,
  retryAfterSeconds,
  summarizeArgs,
  TOOL_LABELS,
  toolOutcome,
  type Turn,
} from '../../lib/copilot'
import { EvidenceLink } from '../evidence/EvidenceLink'
import { Button } from '../ui/Button'
import { AnswerText } from './AnswerText'

function WhyThisAnswer({ turn }: { turn: Turn }) {
  const done = turn.done
  return (
    <details className="group rounded-lg border border-border text-xs" data-testid="copilot-why">
      <summary className="cursor-pointer rounded-lg px-2.5 py-1.5 font-medium text-muted select-none hover:bg-surface-2 hover:text-text">
        Why this answer?
      </summary>
      <div className="space-y-2 border-t border-border px-2.5 py-2 text-muted">
        <p>
          {done?.engine === 'llm'
            ? 'A language model chose the tools; every sentence it kept cites a tool result.'
            : 'A fixed planner chose these read-only tools; each sentence restates one of their results.'}
          {turn.intent && ` Question type: ${turn.intent}.`}
          {done && ` Answered in ${Math.round(done.took_ms)} ms.`}
        </p>
        {turn.tools.length === 0 ? (
          <p>No tools were called: the question was answered without looking anything up.</p>
        ) : (
          <ol className="space-y-1.5" aria-label="Tools called">
            {turn.tools.map((t, i) => {
              const args = summarizeArgs(t.args)
              return (
                <li key={i} data-testid="copilot-tool">
                  <span className="font-medium text-text">{TOOL_LABELS[t.name] ?? t.name}</span>{' '}
                  <code className="text-[0.7rem]">{t.name}</code>
                  {args && <span className="block">{args}</span>}
                  <span className={t.denied ? 'block text-warn' : 'block'}>→ {toolOutcome(t)}</span>
                </li>
              )
            })}
          </ol>
        )}
        {done?.dropped_sentences ? (
          <p>
            {done.dropped_sentences} sentence{done.dropped_sentences === 1 ? '' : 's'} dropped for
            citing no tool result.
          </p>
        ) : null}
      </div>
    </details>
  )
}

function Sources({ turn }: { turn: Turn }) {
  if (!turn.citations.length) return null
  return (
    <div className="text-xs">
      <p className="mb-1 font-medium text-muted">Sources</p>
      <ol className="space-y-1" data-testid="copilot-sources">
        {turn.citations.map((c) => {
          const href = recordHref(c)
          return (
            <li key={c.n} className="flex gap-1.5">
              <span className="num text-muted">[{c.n}]</span>
              {c.kind === 'page' && c.document_id !== null ? (
                <EvidenceLink
                  documentId={c.document_id}
                  pageNo={c.page_no ?? 1}
                  spanIds={c.span_ids}
                  title={c.filename ?? c.label}
                >
                  {c.label}
                  {c.filename && <span className="text-muted"> · {c.filename}</span>}
                </EvidenceLink>
              ) : href ? (
                <Link to={href} className="text-accent hover:underline">
                  {c.label} (record)
                </Link>
              ) : (
                <span className="text-text">{c.label} (database record)</span>
              )}
            </li>
          )
        })}
      </ol>
    </div>
  )
}

function CopyAnswer({ turn }: { turn: Turn }) {
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle')
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(answerForClipboard(turn))
      setState('copied')
    } catch {
      setState('failed')
    }
    window.setTimeout(() => setState('idle'), 2000)
  }
  return (
    <Button className="min-h-7 px-2 text-xs" onClick={() => void copy()} data-testid="copy-answer">
      {state === 'copied' ? <Check size={13} aria-hidden /> : <Copy size={13} aria-hidden />}
      {state === 'copied' ? 'Copied' : state === 'failed' ? 'Copy failed' : 'Copy answer'}
    </Button>
  )
}

/** One question and its streamed answer. */
export function CopilotTurn({ turn, retryIn }: { turn: Turn; retryIn: number }) {
  const streaming = turn.status === 'streaming'
  const refused = turn.done?.refused ?? false
  const error = turn.status === 'error' ? describeError(turn.error) : null
  const limited = retryAfterSeconds(turn.error) !== null
  return (
    <article className="space-y-2" data-testid="copilot-turn" data-status={turn.status}>
      <p className="ml-auto w-fit max-w-[90%] rounded-xl rounded-br-sm bg-accent/15 px-3 py-2 text-sm whitespace-pre-line text-text">
        <span className="sr-only">You asked: </span>
        {turn.question}
      </p>
      <div
        className="space-y-2 rounded-xl rounded-bl-sm border border-border bg-surface-2/60 p-3"
        aria-busy={streaming}
      >
        {streaming && !turn.text && (
          <p className="text-sm text-muted" data-testid="copilot-thinking">
            {turn.tools.length
              ? `${TOOL_LABELS[turn.tools[turn.tools.length - 1]!.name] ?? 'Looking it up'}…`
              : 'Looking through the records…'}
          </p>
        )}
        {refused ? (
          <div className="flex items-start gap-2 text-sm" data-testid="copilot-no-record">
            <SearchX size={16} className="mt-0.5 shrink-0 text-muted" aria-hidden />
            <div>
              <p className="font-semibold text-text">No record found</p>
              <p className="text-muted">{refusalReason(turn.text)}</p>
              <p className="mt-1 text-xs text-muted">
                Nothing is made up to fill the gap. Try other words, name a well, or search.
              </p>
            </div>
          </div>
        ) : (
          turn.text && (
            <AnswerText text={turn.text} citations={turn.citations} streaming={streaming} />
          )
        )}
        {turn.status === 'stopped' && (
          <p className="flex items-center gap-1.5 text-xs text-muted">
            <Square size={11} aria-hidden /> Stopped: the answer above is incomplete.
          </p>
        )}
        {error && (
          <div
            className="flex items-start gap-2 rounded-lg border border-danger/40 bg-danger-bg px-2.5 py-2 text-sm text-danger"
            data-testid="copilot-error"
          >
            <AlertTriangle size={15} className="mt-0.5 shrink-0" aria-hidden />
            <div>
              <p className="font-semibold">{error.title}</p>
              <p>
                {error.detail}
                {limited &&
                  (retryIn > 0 ? ` You can ask again in ${retryIn} s.` : ' You can ask again now.')}
              </p>
            </div>
          </div>
        )}
        {turn.status === 'done' && !refused && <Sources turn={turn} />}
        {(turn.status === 'done' || turn.status === 'stopped') && (
          <div className="flex flex-wrap items-center gap-2">
            {turn.text && <CopyAnswer turn={turn} />}
            <div className="min-w-0 flex-1">
              <WhyThisAnswer turn={turn} />
            </div>
          </div>
        )}
      </div>
    </article>
  )
}
