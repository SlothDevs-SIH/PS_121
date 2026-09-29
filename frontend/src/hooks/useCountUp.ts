import { animate, useReducedMotion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'

/** Counts from the previous value up to `target` (from 0 on first mount). With reduced
 *  motion the target is shown at once. */
export function useCountUp(target: number | null, duration = 0.9): number | null {
  const reduce = useReducedMotion()
  const [animated, setAnimated] = useState(0)
  const from = useRef(0)

  useEffect(() => {
    if (target === null || reduce) return
    const controls = animate(from.current, target, {
      duration,
      ease: [0.22, 1, 0.36, 1],
      onUpdate: setAnimated,
    })
    from.current = target
    return () => controls.stop()
  }, [target, duration, reduce])

  if (target === null) return null
  return reduce ? target : animated
}
