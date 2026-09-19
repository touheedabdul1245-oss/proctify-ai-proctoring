import { useEffect, useRef, useState } from 'react'

// Deferred ease-out count-up used for KPI numbers. Renders the plain number —
// the value itself always comes from the API; this only animates the walk-up.
export default function AnimatedCounter({ value, duration = 700, decimals = 0 }) {
  const target = Number(value) || 0
  const [display, setDisplay] = useState(0)
  const raf = useRef(0)
  const last = useRef(0)

  useEffect(() => {
    const from = last.current
    const to = target
    const t0 = performance.now()
    cancelAnimationFrame(raf.current)
    const tick = (t) => {
      const p = Math.min(1, (t - t0) / duration)
      const eased = 1 - Math.pow(1 - p, 3)
      setDisplay(from + (to - from) * eased)
      if (p < 1) raf.current = requestAnimationFrame(tick)
      else last.current = to
    }
    raf.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, duration])

  return <>{display.toFixed(decimals)}</>
}