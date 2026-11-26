import { useEffect, useRef, useState } from 'react'

/** True once the element has been scrolled into view, and true from the start where the browser
 *  has no IntersectionObserver (so nothing is ever left invisible). */
export function useInView<T extends HTMLElement>(margin = '-40px') {
  const ref = useRef<T>(null)
  const [seen, setSeen] = useState(() => typeof IntersectionObserver === 'undefined')

  useEffect(() => {
    const el = ref.current
    if (!el || seen || typeof IntersectionObserver === 'undefined') return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setSeen(true)
          observer.disconnect()
        }
      },
      { rootMargin: margin },
    )
    observer.observe(el)
    // safety net: whatever the observer does, the content is never left hidden
    const fallback = setTimeout(() => setSeen(true), 1500)
    return () => {
      observer.disconnect()
      clearTimeout(fallback)
    }
  }, [seen, margin])

  return [ref, seen] as const
}
