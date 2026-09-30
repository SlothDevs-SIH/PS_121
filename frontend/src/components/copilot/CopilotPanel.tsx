import { Bell, MapPin, Send, Sparkles, Square, Trash2, X } from 'lucide-react'
import { motion } from 'motion/react'
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'

import { useMediaQuery } from '../../hooks/useMediaQuery'
import { describeError, refusalReason, type CopilotContext, type Turn } from '../../lib/copilot'
import type { CopilotChat } from '../../lib/copilotChat'
import { plainText } from '../../lib/copilotMarkdown'
import { easeOutExpo, panelSlide } from '../../lib/motion'
import { Button } from '../ui/Button'
import { CopilotTurn } from './CopilotTurn'

const sheetSlide = {
  initial: { y: '100%' },
  animate: { y: 0, transition: { duration: 0.32, ease: easeOutExpo } },
  exit: { y: '100%', transition: { duration: 0.2, ease: 'easeIn' } },
} as const

interface Props {
  chat: CopilotChat
  context: CopilotContext
  /** Names for the context chips ("SYN-ASM-01", "alert #9"). */
  wellName?: string | null
  /** Text to start the question box with (e.g. from "Ask copilot" on an alert). */
  initialQuestion?: string
  /** Drop the alert context: while it is set every question is about that alert. */
  onClearAlert?: () => void
  onClose: () => void
}

function examples(context: CopilotContext): string[] {
  if (context.alert_id) return ['Why did this alert fire?']
  const base = [
    'What worked for lost circulation in the Tipam Sandstone?',
    'Which wells had kicks in the Barail?',
  ]
  return context.well_id
    ? ['Summarise the drilling problems in offset wells within 5 km of this well.', ...base]
    : base
}

/** What the polite live region says about the latest turn: once per state, never per token. */
function announcement(turn: Turn | undefined): string {
  if (!turn) return ''
  switch (turn.status) {
    case 'streaming':
      return 'The copilot is answering.'
    case 'stopped':
      return 'Stopped. The answer is incomplete.'
    case 'error': {
      const e = describeError(turn.error)
      return `${e.title}. ${e.detail}`
    }
    case 'done': {
      const text = plainText(turn.text)
      if (turn.done?.refused) return `No record found. ${refusalReason(text)}`
      const n = turn.citations.length
      return `Answer: ${text} ${n} ${n === 1 ? 'source' : 'sources'}.`
    }
  }
}

/**
 * The copilot beside Knowledge Search: a side panel on wide screens and a full-height bottom
 * sheet on phones and tablets. Answers stream in with citation chips; each one says why
 * (the tools it called) and can be copied.
 */
export function CopilotPanel({
  chat,
  context,
  wellName,
  initialQuestion = '',
  onClearAlert,
  onClose,
}: Props) {
  const wide = useMediaQuery('(min-width: 1024px)')
  const [draft, setDraft] = useState(initialQuestion)
  const panelRef = useRef<HTMLElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const threadRef = useRef<HTMLDivElement>(null)
  const { turns, busy, retryIn } = chat
  const last = turns[turns.length - 1]

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    inputRef.current?.focus()
    return () => previous?.focus()
  }, [])

  // Keep the newest text in view while it streams, unless the reader has scrolled up.
  const lastLength = last?.text.length ?? 0
  useEffect(() => {
    const el = threadRef.current
    if (!el) return
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 120) el.scrollTop = el.scrollHeight
  }, [turns.length, lastLength, last?.status])

  const send = (question: string) => {
    if (chat.ask(question, context)) setDraft('')
  }
  const submit = (e: FormEvent) => {
    e.preventDefault()
    send(draft)
  }
  const onInputKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      send(draft)
    }
  }
  const onPanelKey = (e: KeyboardEvent<HTMLElement>) => {
    // Keys inside the evidence viewer (a dialog of its own) are the viewer's.
    const target = e.target as Element
    if (target.closest('[role="dialog"]') !== (wide ? null : panelRef.current)) return
    if (e.key === 'Escape') {
      e.stopPropagation()
      onClose()
    }
    if (e.key === 'Tab' && !wide && panelRef.current) {
      // The sheet is modal: keep Tab inside it.
      const focusable = panelRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), textarea, a[href], summary',
      )
      const first = focusable[0]
      const end = focusable[focusable.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        end?.focus()
      } else if (!e.shiftKey && document.activeElement === end) {
        e.preventDefault()
        first?.focus()
      }
    }
  }

  const limited = retryIn > 0
  const body = (
    <>
      <header className="flex items-start gap-2 border-b border-border px-4 py-3">
        {!wide && (
          <span
            aria-hidden
            className="absolute top-1.5 left-1/2 h-1 w-10 -translate-x-1/2 rounded-full bg-border"
          />
        )}
        <Sparkles size={18} className="mt-0.5 text-accent" aria-hidden />
        <div className="min-w-0 flex-1">
          <h2 id="copilot-title" className="font-semibold text-text">
            Copilot
          </h2>
          <p className="text-xs text-muted">
            Answers only from the records, citing each line. Read-only.
          </p>
        </div>
        {turns.length > 0 && (
          <Button
            className="min-h-8 px-2"
            aria-label="Clear the conversation"
            title="Clear the conversation"
            onClick={chat.clear}
          >
            <Trash2 size={15} aria-hidden />
          </Button>
        )}
        <Button className="min-h-8 px-2" aria-label="Close copilot" onClick={onClose}>
          <X size={16} aria-hidden />
        </Button>
      </header>

      {(context.well_id || context.alert_id) && (
        <div
          className="flex flex-wrap items-center gap-1.5 border-b border-border px-4 py-2 text-xs"
          data-testid="copilot-context"
        >
          <span className="text-muted">About:</span>
          {context.well_id && (
            <span className="inline-flex items-center gap-1 rounded-full bg-surface-2 px-2 py-0.5 text-text">
              <MapPin size={12} aria-hidden /> {wellName ?? `well ${context.well_id}`}
            </span>
          )}
          {context.alert_id && (
            <span className="inline-flex items-center gap-1 rounded-full bg-warn-bg px-2 py-0.5 text-warn">
              <Bell size={12} aria-hidden /> alert #{context.alert_id}
              {onClearAlert && (
                <button
                  type="button"
                  onClick={() => {
                    onClearAlert()
                    // The chip (and this button) go away: keep focus in the panel.
                    inputRef.current?.focus()
                  }}
                  className="-mr-1 rounded-full p-0.5 hover:bg-surface-2"
                  aria-label={`Stop asking about alert ${context.alert_id}`}
                >
                  <X size={11} aria-hidden />
                </button>
              )}
            </span>
          )}
        </div>
      )}

      <div
        ref={threadRef}
        className="min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain px-4 py-3"
        data-testid="copilot-thread"
      >
        {turns.length === 0 ? (
          <div className="space-y-2 text-sm">
            <p className="text-muted">
              Ask about past problems, what worked, offset wells, risks or an alert. If the records
              hold no answer, it says “No record found”.
            </p>
            <div className="flex flex-col items-start gap-1.5">
              {examples(context).map((ex) => (
                <button
                  key={ex}
                  type="button"
                  onClick={() => send(ex)}
                  disabled={limited}
                  className="rounded-lg border border-border px-2.5 py-1 text-left text-text hover:bg-surface-2 disabled:opacity-50"
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>
        ) : (
          turns.map((t) => <CopilotTurn key={t.id} turn={t} retryIn={retryIn} />)
        )}
      </div>

      <p className="sr-only" role="status" aria-live="polite" data-testid="copilot-status">
        {announcement(last)}
      </p>

      <form onSubmit={submit} className="space-y-1.5 border-t border-border px-4 py-3">
        <label className="block">
          <span className="sr-only">Ask the copilot</span>
          <textarea
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onInputKey}
            rows={2}
            maxLength={1000}
            placeholder="Ask about the drilling records…"
            className="block w-full resize-none rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text placeholder:text-muted"
            data-testid="copilot-input"
          />
        </label>
        <div className="flex items-center gap-2">
          <p className="min-w-0 flex-1 text-xs text-muted" data-testid="copilot-hint">
            {limited
              ? `Question limit reached: ask again in ${retryIn} s.`
              : 'Enter to send, Shift+Enter for a new line.'}
          </p>
          {busy && (
            <Button onClick={chat.stop} data-testid="copilot-stop">
              <Square size={13} aria-hidden /> Stop
            </Button>
          )}
          <Button
            type="submit"
            variant="primary"
            disabled={!draft.trim() || limited}
            data-testid="copilot-send"
          >
            <Send size={14} aria-hidden /> Ask
          </Button>
        </div>
      </form>
    </>
  )

  if (wide)
    return (
      <motion.aside
        ref={panelRef}
        {...panelSlide}
        aria-labelledby="copilot-title"
        onKeyDown={onPanelKey}
        className="sticky top-[4.5rem] flex h-[calc(100dvh-6rem)] min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-card"
        data-testid="copilot-panel"
      >
        {body}
      </motion.aside>
    )
  return (
    <div className="fixed inset-0 z-(--z-modal)">
      <motion.div
        aria-hidden
        className="absolute inset-0 bg-black/50"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
      />
      <motion.section
        ref={panelRef}
        {...sheetSlide}
        role="dialog"
        aria-modal="true"
        aria-labelledby="copilot-title"
        onKeyDown={onPanelKey}
        className="absolute inset-x-0 top-2 bottom-0 flex min-h-0 flex-col overflow-hidden rounded-t-2xl border-t border-border bg-surface pb-[env(safe-area-inset-bottom)] shadow-card"
        data-testid="copilot-panel"
      >
        {body}
      </motion.section>
    </div>
  )
}
