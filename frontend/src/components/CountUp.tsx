import { useEffect, useState } from 'react'
import { count } from '../lib/format'

const prefersStill = () =>
  typeof window !== 'undefined' &&
  (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false)

/** Counts from zero to `target` once, then holds. Reduced motion gets the final value at once. */
export function useCountUp(target: number, duration = 900): number {
  const [value, setValue] = useState(() => (prefersStill() ? target : 0))

  useEffect(() => {
    if (prefersStill() || target === 0) {
      setValue(target)
      return
    }
    let frame = 0
    const start = performance.now()
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration)
      // ease out: fast at first, settling at the end
      setValue(Math.round(target * (1 - (1 - t) ** 3)))
      if (t < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [target, duration])

  return value
}

/** A headline figure with its label above it. `format` turns the running number into text. */
export function Figure({
  label,
  value,
  format = count,
  hero = false,
}: {
  label: string
  value: number
  format?: (n: number) => string
  hero?: boolean
}) {
  const shown = useCountUp(value)
  return (
    <div className={`metric${hero ? ' hero' : ''}`}>
      <span className="label">{label}</span>
      {/* the live region is the final value, so a screen reader hears it once, not every frame */}
      <span className="figure" aria-hidden>
        {format(shown)}
      </span>
      <span className="sr-only">{format(value)}</span>
    </div>
  )
}
