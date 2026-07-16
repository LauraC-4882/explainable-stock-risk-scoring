import { useEffect, useRef, useState } from 'react'

// Animates a number from its previous value to `target` using requestAnimationFrame.
// Used to give the risk score (and its gauge) a smooth "counting up" feel on load/update.
export function useCountUp(target, duration = 700) {
  const [value, setValue] = useState(target ?? 0)
  const fromRef = useRef(target ?? 0)

  useEffect(() => {
    if (target == null || Number.isNaN(+target)) return undefined
    const from = fromRef.current
    const to = +target
    if (from === to) return undefined

    let raf
    const start = performance.now()
    function tick(now) {
      const progress = Math.min((now - start) / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      const current = from + (to - from) * eased
      setValue(current)
      if (progress < 1) {
        raf = requestAnimationFrame(tick)
      } else {
        fromRef.current = to
      }
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, duration])

  return value
}
