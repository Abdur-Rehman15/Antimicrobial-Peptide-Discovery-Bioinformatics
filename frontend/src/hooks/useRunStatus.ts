import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Run } from '../api/types'

/** Poll one run until it is done or failed. */
export function useRunStatus(id: string, intervalMs = 1000) {
  const [run, setRun] = useState<Run | null>(null)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const controller = new AbortController()
    setRun(null)
    setError(null)

    const poll = async () => {
      try {
        const next = await api.getRun(id, controller.signal)
        if (cancelled) return
        setRun(next)
        setError(null)
        if (next.status === 'queued' || next.status === 'running') {
          timer = setTimeout(poll, intervalMs)
        }
      } catch (e) {
        if (cancelled || (e instanceof DOMException && e.name === 'AbortError')) return
        setError(e as Error)
        timer = setTimeout(poll, intervalMs * 3) // keep trying: the backend may be restarting
      }
    }
    poll()
    return () => {
      cancelled = true
      controller.abort()
      if (timer) clearTimeout(timer)
    }
  }, [id, intervalMs])

  const refresh = useCallback(() => {
    api.getRun(id).then(setRun).catch(setError)
  }, [id])

  return { run, error, refresh }
}
