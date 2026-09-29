import { Command } from 'cmdk'
import { CornerDownLeft, FileText, Search } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router'

import { screensFor } from '../../app/screens'
import { useDocuments, useWells } from '../../lib/api/hooks'
import { easeOutExpo } from '../../lib/motion'
import { FLUIDS, fluidOf } from '../../lib/wellTypes'
import { useUiStore } from '../../stores/ui'

const itemClass =
  'flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-sm text-text data-[selected=true]:bg-surface-2 data-[selected=true]:ring-1 data-[selected=true]:ring-border'
const groupClass =
  '[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:pt-3 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:text-[0.65rem] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-muted [&_[cmdk-group-heading]]:uppercase'

/** ⌘K / Ctrl+K: jump to any page, well or document (FRONTEND_SPEC §3.2). Loaded on first
 *  use by CommandPaletteHost, which owns the shortcut. */
export default function CommandPalette() {
  const open = useUiStore((s) => s.paletteOpen)
  const setOpen = useUiStore((s) => s.setPaletteOpen)
  const mode = useUiStore((s) => s.mode)
  const navigate = useNavigate()
  const wells = useWells()
  const docs = useDocuments(undefined, open)
  const returnFocus = useRef<Element | null>(null)

  useEffect(() => {
    if (open) {
      returnFocus.current = document.activeElement
    } else if (returnFocus.current instanceof HTMLElement) {
      returnFocus.current.focus()
    }
  }, [open])

  const go = (to: string) => {
    setOpen(false)
    navigate(to)
  }

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="palette"
          className="fixed inset-0 z-(--z-modal) flex items-start justify-center bg-black/50 px-4 pt-[12vh] backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          onMouseDown={(e) => e.target === e.currentTarget && setOpen(false)}
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label="Command palette"
            data-testid="command-palette"
            className="w-full max-w-xl overflow-hidden rounded-2xl border border-border bg-surface shadow-card"
            initial={{ opacity: 0, y: -12, scale: 0.98 }}
            animate={{
              opacity: 1,
              y: 0,
              scale: 1,
              transition: { duration: 0.2, ease: easeOutExpo },
            }}
            exit={{ opacity: 0, y: -8, scale: 0.98, transition: { duration: 0.1 } }}
          >
            <Command
              label="Command palette"
              loop
              onKeyDown={(e) => {
                if (e.key === 'Escape') {
                  e.preventDefault()
                  setOpen(false)
                }
              }}
            >
              <div className="flex items-center gap-2 border-b border-border px-4">
                <Search size={16} aria-hidden className="text-muted" />
                <Command.Input
                  autoFocus
                  placeholder="Jump to a well, document or page…"
                  className="h-12 w-full bg-transparent text-sm text-text outline-none placeholder:text-muted focus-visible:outline-none"
                />
                <kbd className="rounded border border-border px-1.5 py-0.5 font-mono text-[0.65rem] text-muted">
                  Esc
                </kbd>
              </div>
              <Command.List className="max-h-[55vh] overflow-y-auto p-2">
                <Command.Empty className="px-3 py-6 text-center text-sm text-muted">
                  Nothing matches.
                </Command.Empty>
                <Command.Group heading="Pages" className={groupClass}>
                  {screensFor(mode).map((s) => (
                    <Command.Item
                      key={s.id}
                      value={`page ${s.title}`}
                      data-kind="page"
                      keywords={[s.purpose]}
                      onSelect={() => go(s.navPath)}
                      className={itemClass}
                    >
                      <s.icon size={16} aria-hidden className="text-muted" />
                      <span className="flex-1">{s.title}</span>
                      {s.status !== 'built' && (
                        <span className="text-[0.65rem] text-muted">{s.phase}</span>
                      )}
                    </Command.Item>
                  ))}
                </Command.Group>
                <Command.Group heading="Wells" className={groupClass}>
                  {(wells.data?.items ?? []).map((w) => {
                    const f = fluidOf(w.fluid_type)
                    const Icon = f ? FLUIDS[f].icon : CornerDownLeft
                    return (
                      <Command.Item
                        key={w.id}
                        value={`well ${w.name} ${w.id}`}
                        data-kind="well"
                        keywords={[w.status, w.fluid_type ?? '', w.field]}
                        onSelect={() => go(`/map?well=${w.id}`)}
                        className={itemClass}
                      >
                        <Icon
                          size={16}
                          aria-hidden
                          className={f ? FLUIDS[f].textClass : 'text-muted'}
                        />
                        <span className="flex-1 font-medium">{w.name}</span>
                        <span className="text-xs text-muted">
                          {w.status}
                          {f ? ` · ${f}` : ''}
                        </span>
                      </Command.Item>
                    )
                  })}
                </Command.Group>
                <Command.Group heading="Documents" className={groupClass}>
                  {(docs.data?.items ?? []).map((d) => (
                    <Command.Item
                      key={d.id}
                      value={`document ${d.filename} ${d.id}`}
                      data-kind="document"
                      keywords={[d.doc_type ?? '', d.well_name ?? '']}
                      onSelect={() => go(`/documents?doc=${d.id}`)}
                      className={itemClass}
                    >
                      <FileText size={16} aria-hidden className="text-muted" />
                      <span className="flex-1 truncate">{d.filename}</span>
                      <span className="text-xs text-muted">{d.doc_type ?? '—'}</span>
                    </Command.Item>
                  ))}
                </Command.Group>
              </Command.List>
            </Command>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
