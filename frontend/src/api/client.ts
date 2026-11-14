import type {
  CandidateDetail,
  Info,
  Organism,
  ProteinDetail,
  ProteinSummary,
  ResultsPage,
  Run,
  RunRequest,
  View,
} from './types'
import { viewToApi } from '../lib/view'

/** An error with a message that is fit to show the user. */
export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, init)
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, 'Cannot reach the backend. Is it running on port 8000?')
  }
  if (!response.ok) {
    let message = `The backend answered with HTTP ${response.status}.`
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') message = body.detail
      else if (Array.isArray(body.detail)) {
        message = body.detail
          .map((d: { loc?: string[]; msg?: string }) => `${(d.loc ?? []).slice(1).join('.')}: ${d.msg}`)
          .join('; ')
      }
    } catch {
      /* the body was not JSON; keep the generic message */
    }
    throw new ApiError(response.status, message)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export interface Paging {
  limit: number
  offset: number
}

function resultsQuery(view: View, paging?: Paging): string {
  const params = viewToApi(view)
  if (paging) {
    params.set('limit', String(paging.limit))
    params.set('offset', String(paging.offset))
  }
  return params.toString()
}

const run = (id: string) => `/api/runs/${encodeURIComponent(id)}`

export const api = {
  health: (signal?: AbortSignal) => request<{ status: string }>('/health', { signal }),
  info: (signal?: AbortSignal) => request<Info>('/api/info', { signal }),
  organisms: (q: string, signal?: AbortSignal) =>
    request<Organism[]>(`/api/organisms?q=${encodeURIComponent(q)}`, { signal }),
  createRun: (body: RunRequest) =>
    request<{ id: string; status_url: string }>('/api/runs', json(body)),
  listRuns: (signal?: AbortSignal) => request<Run[]>('/api/runs', { signal }),
  getRun: (id: string, signal?: AbortSignal) => request<Run>(run(id), { signal }),
  deleteRun: (id: string) => request<void>(run(id), { method: 'DELETE' }),
  results: (id: string, view: View, paging: Paging, signal?: AbortSignal) =>
    request<ResultsPage>(`${run(id)}/results?${resultsQuery(view, paging)}`, { signal }),
  csvUrl: (id: string, view: View) => `${run(id)}/results.csv?${resultsQuery(view)}`,
  candidate: (
    id: string,
    accession: string,
    start: number,
    end: number,
    prevalence: number,
    signal?: AbortSignal,
  ) =>
    request<CandidateDetail>(
      `${run(id)}/candidate?` +
        new URLSearchParams({
          accession,
          start: String(start),
          end: String(end),
          prevalence: String(prevalence),
        }),
      { signal },
    ),
  proteins: (id: string, signal?: AbortSignal) =>
    request<ProteinSummary[]>(`${run(id)}/proteins`, { signal }),
  protein: (id: string, accession: string, view: View, signal?: AbortSignal) =>
    request<ProteinDetail>(
      `${run(id)}/proteins/${encodeURIComponent(accession)}?${resultsQuery(view)}`,
      { signal },
    ),
}
