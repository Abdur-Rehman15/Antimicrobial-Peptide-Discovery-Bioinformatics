import { useEffect, useRef, useState } from 'react'

export interface AsyncState<T> {
  data: T | null
  error: Error | null
  /** true while a request is in flight (also on the first load) */
  loading: boolean
}

/**
 * Run `load` whenever `deps` change. While the next result is loading the previous data stays
 * on screen (`loading` is true), so a slider drag dims the table instead of blanking it.
 * A request that is superseded is aborted and its answer ignored.
 */
export function useAsync<T>(
  load: (signal: AbortSignal) => Promise<T>,
  deps: unknown[],
  enabled = true,
): AsyncState<T> & { reload: () => void } {
  const [state, setState] = useState<AsyncState<T>>({ data: null, error: null, loading: enabled })
  const [tick, setTick] = useState(0)
  const loadRef = useRef(load)
  loadRef.current = load

  useEffect(() => {
    if (!enabled) return
    const controller = new AbortController()
    setState((s) => ({ ...s, loading: true, error: null }))
    loadRef
      .current(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setState({ data, error: null, loading: false })
      })
      .catch((error: Error) => {
        if (controller.signal.aborted || error.name === 'AbortError') return
        setState((s) => ({ ...s, error, loading: false }))
      })
    return () => controller.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, enabled, tick])

  return { ...state, reload: () => setTick((t) => t + 1) }
}
