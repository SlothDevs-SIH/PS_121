import { RotateCw } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'

import { easeOutExpo } from '../../lib/motion'
import { usePwaStore } from '../../lib/offline/pwa'
import { Button } from '../ui/Button'

/** "Update available – Reload": a new version is installed and waits for the user's go. */
export function UpdatePrompt() {
  const applyUpdate = usePwaStore((s) => s.applyUpdate)
  const setUpdate = usePwaStore((s) => s.setUpdate)
  return (
    <AnimatePresence>
      {applyUpdate && (
        <motion.div
          key="update"
          role="status"
          data-testid="update-prompt"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0, transition: { duration: 0.24, ease: easeOutExpo } }}
          exit={{ opacity: 0, y: 8, transition: { duration: 0.14 } }}
          className="fixed bottom-[max(1rem,env(safe-area-inset-bottom))] left-4 z-(--z-toast) flex items-center gap-2 rounded-xl border border-border bg-surface py-1.5 pr-1.5 pl-3 text-sm text-text shadow-card"
        >
          <span>Update available</span>
          <Button variant="primary" onClick={applyUpdate}>
            <RotateCw size={14} aria-hidden /> Reload
          </Button>
          <Button onClick={() => setUpdate(null)}>Later</Button>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
