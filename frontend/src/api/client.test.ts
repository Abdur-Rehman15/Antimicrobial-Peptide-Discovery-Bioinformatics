import { afterEach, vi } from 'vitest'
import { DEFAULT_VIEW } from '../lib/view'
import { ApiError, api } from './client'

function reply(body: unknown, status = 200): Response {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => vi.restoreAllMocks())

describe('api client', () => {
  it('asks for results with the view and the page as query parameters', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(reply({ rows: [], total: 0 }))
    await api.results(
      'abc',
      { ...DEFAULT_VIEW, safetyWeight: 2, hideKnown: true, novelty: ['novel'] },
      { limit: 25, offset: 50 },
    )
    const url = new URL(String(fetchMock.mock.calls[0][0]), 'http://x')
    expect(url.pathname).toBe('/api/runs/abc/results')
    expect(url.searchParams.get('safety_weight')).toBe('2')
    expect(url.searchParams.get('hide_known')).toBe('true')
    expect(url.searchParams.get('novelty')).toBe('novel')
    expect(url.searchParams.get('limit')).toBe('25')
    expect(url.searchParams.get('offset')).toBe('50')
  })

  it('builds the CSV link from the same view, without paging', () => {
    const link = new URL(api.csvUrl('abc', { ...DEFAULT_VIEW, prevalence: 1e-4 }), 'http://x')
    expect(link.pathname).toBe('/api/runs/abc/results.csv')
    expect(link.searchParams.get('prevalence')).toBe('0.0001')
    expect(link.searchParams.has('limit')).toBe(false)
  })

  it('escapes the run id and the candidate coordinates', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(reply({}))
    await api.candidate('a b', 'P1', 3, 12, 0.001)
    const url = String(fetchMock.mock.calls[0][0])
    expect(url).toContain('/api/runs/a%20b/candidate?')
    expect(url).toContain('accession=P1')
    expect(url).toContain('start=3')
    expect(url).toContain('end=12')
  })

  it('posts a run request as JSON', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(reply({ id: 'x', status_url: '' }, 202))
    const body = {
      source: { type: 'accessions' as const, accessions: ['P69905'] },
      options: { top_n: 50, prevalence: 0.001 },
    }
    await api.createRun(body)
    const init = fetchMock.mock.calls[0][1]!
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual(body)
  })

  it('turns a backend error message into an ApiError', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(reply({ detail: 'No protein of at least 8 residues.' }, 422))
    await expect(api.getRun('x')).rejects.toMatchObject({
      name: 'ApiError',
      status: 422,
      message: 'No protein of at least 8 residues.',
    })
  })

  it('reads validation errors that come as a list', async () => {
    const detail = [{ loc: ['query', 'safety_weight'], msg: 'Input should be >= 0' }]
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(reply({ detail }, 422))
    await expect(api.getRun('x')).rejects.toThrow('safety_weight: Input should be >= 0')
  })

  it('has a fallback message when the error body is not JSON', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('boom', { status: 500 }))
    const error = await api.getRun('x').catch((e) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error.message).toContain('HTTP 500')
  })

  it('says so when the backend cannot be reached', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'))
    const error = await api.listRuns().catch((e) => e)
    expect(error.status).toBe(0)
    expect(error.message).toMatch(/Cannot reach the backend/)
  })

  it('lets an aborted request propagate as an abort, not as a backend error', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new DOMException('aborted', 'AbortError'))
    const error = await api.listRuns().catch((e) => e)
    expect(error.name).toBe('AbortError')
  })

  it('treats 204 as success with no body', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(reply(null, 204))
    await expect(api.deleteRun('x')).resolves.toBeUndefined()
  })
})
