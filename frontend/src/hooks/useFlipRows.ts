import { useLayoutEffect, useRef } from 'react'

/**
 * Makes re-ordered rows slide to their new places instead of jumping.
 *
 * First, Last, Invert, Play: remember where every row was, let React paint the new order, then
 * animate each row from the offset it just moved by back to zero. The browser does the work on
 * the compositor, so a long list stays smooth.
 *
 * Returns a callback ref to attach to each row, keyed by something stable for that row.
 */
export function useFlipRows(signature: string, duration = 420) {
  const nodes = useRef(new Map<string, HTMLElement>())
  const previous = useRef(new Map<string, number>())

  useLayoutEffect(() => {
    const still =
      typeof window !== 'undefined' &&
      (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false)

    const now = new Map<string, number>()
    for (const [key, node] of nodes.current) now.set(key, node.getBoundingClientRect().top)

    if (!still && previous.current.size > 0) {
      for (const [key, node] of nodes.current) {
        const before = previous.current.get(key)
        const after = now.get(key)
        if (before === undefined || after === undefined) continue
        const delta = before - after
        if (Math.abs(delta) < 1) continue
        // jsdom has no Web Animations API, so this is simply skipped under test
        node.animate?.(
          [{ transform: `translateY(${delta}px)` }, { transform: 'translateY(0)' }],
          { duration, easing: 'cubic-bezier(0.32, 0.72, 0, 1)' },
        )
      }
    }
    previous.current = now
  }, [signature, duration])

  return (key: string) => (node: HTMLElement | null) => {
    if (node) nodes.current.set(key, node)
    else nodes.current.delete(key)
  }
}
