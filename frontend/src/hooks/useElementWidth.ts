import { useEffect, useRef, useState } from 'react'

/** The rendered width of an element, kept up to date, so charts can be drawn at 1:1 scale
 *  (an SVG scaled down from a fixed width shrinks its text and marks with it). */
export function useElementWidth<T extends HTMLElement>(fallback = 720) {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(fallback)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (el.clientWidth) setWidth(el.clientWidth)
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(([entry]) =>
      setWidth(Math.max(280, Math.round(entry.contentRect.width))),
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  return [ref, width] as const
}
