import { AnimatePresence, motion } from 'motion/react'
import { useState } from 'react'
import { useLocation, useOutlet } from 'react-router'

import { pageTransition } from '../../lib/motion'

/** The outlet as it was when this page mounted, so the leaving page keeps its content
 *  during its exit animation instead of re-rendering as the next route. */
function FrozenOutlet() {
  const outlet = useOutlet()
  const [frozen] = useState(outlet)
  return frozen
}

/** Route changes fade/slide (transform + opacity only), keyed by path (§7 rule 8). */
export function AnimatedOutlet() {
  const location = useLocation()
  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={location.pathname}
        initial={pageTransition.initial}
        animate={pageTransition.animate}
        exit={pageTransition.exit}
        className="min-h-full"
      >
        <FrozenOutlet />
      </motion.div>
    </AnimatePresence>
  )
}
