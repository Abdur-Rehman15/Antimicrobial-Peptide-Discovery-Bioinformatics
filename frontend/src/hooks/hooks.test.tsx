import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, vi } from 'vitest'
import { api } from '../api/client'
import { run } from '../test/fixtures'
import { useAsync } from './useAsync'
import { useDebounced } from './useDebounced'
import { useRunStatus } from './useRunStatus'

function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: Error) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('useAsync', () => {
  it('keeps the previous data on screen while the next request loads', async () => {
    const second = deferred<string>()
    const loader = vi.fn((signal: AbortSignal) => {
      void signal
      return loader.mock.calls.length === 1 ? Promise.resolve('first') : second.promise
    })
    const { result, rerender } = renderHook(({ n }) => useAsync(loader, [n]), { initialProps: { n: 1 } })
    await waitFor(() => expect(result.current.data).toBe('first'))
    rerender({ n: 2 })
    await waitFor(() => expect(result.current.loading).toBe(true))
    expect(result.current.data).toBe('first') // not blanked
    await act(async () => second.resolve('second'))
    await waitFor(() => expect(result.current.data).toBe('second'))
    expect(result.current.loading).toBe(false)
  })

  it('ignores an answer that arrives after a newer request was made', async () => {
    const slow = deferred<string>()
    const fast = deferred<string>()
    const loader = vi.fn(() => (loader.mock.calls.length === 1 ? slow.promise : fast.promise))
    const { result, rerender } = renderHook(({ n }) => useAsync(loader, [n]), { initialProps: { n: 1 } })
    rerender({ n: 2 })
    await act(async () => fast.resolve('new'))
    await waitFor(() => expect(result.current.data).toBe('new'))
    await act(async () => slow.resolve('stale'))
    expect(result.current.data).toBe('new') // the stale answer did not overwrite it
  })

  it('reports an error and does not run when disabled', async () => {
    const failing = renderHook(() => useAsync(() => Promise.reject(new Error('nope')), []))
    await waitFor(() => expect(failing.result.current.error?.message).toBe('nope'))
    const loader = vi.fn(() => Promise.resolve(1))
    renderHook(() => useAsync(loader, [], false))
    expect(loader).not.toHaveBeenCalled()
  })
})

describe('useDebounced', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('only follows the value once it has stopped changing', () => {
    const { result, rerender } = renderHook(({ v }) => useDebounced(v, 250), { initialProps: { v: 1 } })
    rerender({ v: 2 })
    rerender({ v: 3 })
    expect(result.current).toBe(1)
    act(() => vi.advanceTimersByTime(249))
    expect(result.current).toBe(1)
    act(() => vi.advanceTimersByTime(2))
    expect(result.current).toBe(3)
  })
})

describe('useRunStatus', () => {
  afterEach(() => vi.restoreAllMocks())

  it('polls until the run is done and then stops', async () => {
    const getRun = vi
      .spyOn(api, 'getRun')
      .mockResolvedValueOnce(run({ status: 'running', progress: 0.3 }))
      .mockResolvedValueOnce(run({ status: 'running', progress: 0.8 }))
      .mockResolvedValue(run({ status: 'done', progress: 1 }))
    const { result } = renderHook(() => useRunStatus('abc123def456', 20))
    await waitFor(() => expect(result.current.run?.status).toBe('done'))
    const calls = getRun.mock.calls.length
    expect(calls).toBe(3)
    await new Promise((r) => setTimeout(r, 80))
    expect(getRun.mock.calls.length).toBe(calls) // no more polling
  })

  it('keeps trying after an error and recovers', async () => {
    vi.spyOn(api, 'getRun')
      .mockRejectedValueOnce(new Error('backend restarting'))
      .mockResolvedValue(run({ status: 'done' }))
    // the hook retries after 3 x the interval, so 100 ms keeps the error visible for 300 ms
    const { result } = renderHook(() => useRunStatus('abc123def456', 100))
    await waitFor(() => expect(result.current.error?.message).toBe('backend restarting'))
    await waitFor(() => expect(result.current.run?.status).toBe('done'))
    expect(result.current.error).toBeNull()
  })

  it('does not poll a finished run again', async () => {
    const getRun = vi.spyOn(api, 'getRun').mockResolvedValue(run({ status: 'failed', error: 'x' }))
    const { result } = renderHook(() => useRunStatus('abc123def456', 10))
    await waitFor(() => expect(result.current.run?.status).toBe('failed'))
    await new Promise((r) => setTimeout(r, 50))
    expect(getRun).toHaveBeenCalledTimes(1)
  })
})
