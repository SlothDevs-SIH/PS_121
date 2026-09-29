/**
 * Shared Framer Motion variants (FRONTEND_SPEC §5). Only transform and opacity animate
 * (§7 rule 1); height changes use the `layout` prop. MotionConfig reducedMotion="user"
 * (app/providers.tsx) turns these into instant changes for users who ask for less motion.
 */
import type { Transition, Variants } from 'motion/react'

export const easeOutExpo = [0.22, 1, 0.36, 1] as const

export const pageTransition = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.22, ease: easeOutExpo } },
  exit: { opacity: 0, y: -6, transition: { duration: 0.12, ease: 'easeIn' } },
} as const

export const staggerContainer: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.05 } },
}

export const staggerItem: Variants = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.28, ease: easeOutExpo } },
}

export const activePillTransition: Transition = { type: 'spring', stiffness: 500, damping: 40 }

export const panelSlide = {
  initial: { x: '100%', opacity: 0.6 },
  animate: { x: 0, opacity: 1, transition: { duration: 0.32, ease: easeOutExpo } },
  exit: { x: '100%', opacity: 0, transition: { duration: 0.18, ease: 'easeIn' } },
} as const
