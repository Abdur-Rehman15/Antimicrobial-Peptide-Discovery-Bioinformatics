import type { Candidate } from '../api/types'

/** URL of a candidate's detail page; `prevalence` keeps the calibrated numbers consistent. */
export function candidateLink(
  runId: string,
  c: Pick<Candidate, 'accession' | 'start' | 'end'>,
  prevalence: number,
): string {
  const params = new URLSearchParams({
    accession: c.accession,
    start: String(c.start),
    end: String(c.end),
    p: String(prevalence),
  })
  return `/runs/${encodeURIComponent(runId)}/candidate?${params}`
}
