import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import type { Run, View } from '../api/types'
import { ErrorNotice, Meter, Note, Spinner, Stat } from '../components/Bits'
import { StatusChip } from '../components/Chips'
import { ProteinMap } from '../components/ProteinMap'
import { ResultsControls } from '../components/ResultsControls'
import { ResultsTable } from '../components/ResultsTable'
import { ScatterPlot } from '../components/ScatterPlot'
import { useAsync } from '../hooks/useAsync'
import { useDebounced } from '../hooks/useDebounced'
import { useRunStatus } from '../hooks/useRunStatus'
import { count, duration, percent } from '../lib/format'
import { candidateLink } from '../lib/links'
import { parseView, serializeView } from '../lib/view'

const PAGE = 25
type Tab = 'list' | 'chart' | 'proteins'
const TABS: [Tab, string][] = [
  ['list', 'Ranked list'],
  ['chart', 'Activity vs safety'],
  ['proteins', 'Proteins'],
]

function Progress({ run }: { run: Run }) {
  return (
    <div className="card stack" style={{ maxWidth: 640 }}>
      <div className="row spread">
        <h2>{run.status === 'queued' ? 'Waiting for a free worker' : 'Scanning'}</h2>
        <StatusChip state={run.status} />
      </div>
      <Meter value={run.progress} label="Run progress" big />
      <p aria-live="polite">
        <strong>{percent(run.progress)}</strong> · {run.message}
      </p>
      {run.n_proteins !== null && (
        <p className="muted">
          {count(run.n_proteins)} proteins, {count(run.n_residues)} residues.
        </p>
      )}
      <p className="hint">This page updates by itself. You can leave it and come back from Runs.</p>
    </div>
  )
}

function Results({ run }: { run: Run }) {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const tab: Tab = (['list', 'chart', 'proteins'] as const).find((t) => t === params.get('tab')) ?? 'list'

  // `draft` follows the sliders at once; `view` (debounced) drives requests and the URL
  const [draft, setDraft] = useState<View>(() => parseView(params))
  const view = useDebounced(draft, 250)
  const viewKey = serializeView(view).toString()
  const [page, setPage] = useState(0)
  const [selected, setSelected] = useState<string | null>(null)

  useEffect(() => {
    const next = serializeView(view)
    if (tab !== 'list') next.set('tab', tab)
    setParams(next, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewKey, tab])
  useEffect(() => setPage(0), [viewKey])

  const proteins = useAsync((signal) => api.proteins(run.id, signal), [run.id])
  const list = useAsync(
    (signal) => api.results(run.id, view, { limit: PAGE, offset: page * PAGE }, signal),
    [run.id, viewKey, page],
    tab === 'list',
  )
  const all = useAsync(
    (signal) => api.results(run.id, view, { limit: 1000, offset: 0 }, signal),
    [run.id, viewKey],
    tab === 'chart',
  )
  const firstWithCandidates = useMemo(
    () => proteins.data?.slice().sort((a, b) => b.n_candidates - a.n_candidates)[0]?.accession ?? null,
    [proteins.data],
  )
  const accession = selected ?? firstWithCandidates
  const protein = useAsync(
    (signal) => api.protein(run.id, accession as string, view, signal),
    [run.id, accession, viewKey],
    tab === 'proteins' && accession !== null,
  )

  const setTab = (next: Tab) => {
    const p = serializeView(view)
    if (next !== 'list') p.set('tab', next)
    setParams(p, { replace: true })
  }
  const total = list.data?.total ?? 0
  const first = total === 0 ? 0 : page * PAGE + 1
  const last = Math.min(total, (page + 1) * PAGE)

  return (
    <div className="stack">
      <div className="card">
        <div className="stats">
          <Stat label="Proteins" value={count(run.n_proteins)} />
          <Stat label="Residues" value={count(run.n_residues)} />
          <Stat label="Windows scored" value={count(run.n_windows)} />
          <Stat label="Scan time" value={duration(run.seconds)} />
          <Stat label="Candidates kept" value={count(run.options.top_n ?? null)} />
        </div>
        {run.notes.length > 0 && (
          <ul className="plain muted" style={{ marginTop: 14 }}>
            {run.notes.map((n) => <li key={n}>{n}</li>)}
          </ul>
        )}
      </div>

      <div className="workspace">
        <ResultsControls view={draft} onChange={setDraft} proteins={proteins.data} />

        <div className="stack" style={{ minWidth: 0 }}>
          <div className="row spread">
            <div className="tabs" role="tablist" aria-label="Views">
              {TABS.map(([value, text]) => (
                <button key={value} role="tab" aria-selected={tab === value} onClick={() => setTab(value)}>
                  {text}
                </button>
              ))}
            </div>
            <a className="button" href={api.csvUrl(run.id, view)} download>Export CSV</a>
          </div>

          {tab === 'list' && (
            <div className="card flush">
              {list.error && !list.data && <div style={{ padding: 16 }}><ErrorNotice error={list.error} /></div>}
              {!list.data && !list.error && <Spinner label="Loading candidates" />}
              {list.data && (
                <>
                  <ResultsTable runId={run.id} rows={list.data.rows} prevalence={view.prevalence}
                    loading={list.loading} />
                  <div className="pager">
                    <span className="muted">
                      {total === 0 ? 'No candidates' : `Showing ${first}–${last} of ${count(total)}`}
                    </span>
                    <div className="row">
                      <button disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button>
                      <button disabled={last >= total} onClick={() => setPage(page + 1)}>Next</button>
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

          {tab === 'chart' && (
            <div className="card">
              {all.error && !all.data && <ErrorNotice error={all.error} />}
              {!all.data && !all.error && <Spinner label="Loading candidates" />}
              {all.data &&
                (all.data.rows.length === 0 ? (
                  <p className="empty">No candidate matches these filters.</p>
                ) : (
                  <ScatterPlot candidates={all.data.rows} loading={all.loading}
                    onSelect={(c) => navigate(candidateLink(run.id, c, view.prevalence))} />
                ))}
            </div>
          )}

          {tab === 'proteins' && (
            <div className="workspace" style={{ gridTemplateColumns: 'minmax(220px, 300px) minmax(0, 1fr)' }}>
              <div className="card flush">
                {!proteins.data && <Spinner label="Loading proteins" />}
                <div className="protein-list" role="group" aria-label="Proteins">
                  {proteins.data
                    ?.slice()
                    .sort((a, b) => b.n_candidates - a.n_candidates)
                    .map((p) => (
                      <button key={p.accession} aria-pressed={p.accession === accession}
                        onClick={() => setSelected(p.accession)}>
                        <span>
                          <strong>{p.accession}</strong>
                          <br />
                          <span className="faint">{p.name.slice(0, 30) || `${p.length} residues`}</span>
                        </span>
                        <span className="faint">{p.n_candidates}</span>
                      </button>
                    ))}
                </div>
              </div>
              <div className="card" style={{ minWidth: 0 }}>
                {protein.error && <ErrorNotice error={protein.error} />}
                {protein.data && (
                  <div className="stack">
                    <div>
                      <h2>{protein.data.accession}</h2>
                      <p className="muted">
                        {protein.data.name} · {protein.data.length} residues ·{' '}
                        {protein.data.candidates.length} candidate region(s) with the current filters
                      </p>
                    </div>
                    {protein.data.candidates.length === 0 ? (
                      <p className="empty">No candidate region in this protein matches the filters.</p>
                    ) : (
                      <ProteinMap protein={protein.data} runId={run.id} prevalence={view.prevalence} />
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
          <Note>
            Moving a slider re-ranks the saved shortlist; nothing is scanned again. The activity
            number is calibrated for an assumed rarity of AMPs and should be read as an ordering.
          </Note>
        </div>
      </div>
    </div>
  )
}

export function RunPage() {
  const { id = '' } = useParams()
  const { run, error } = useRunStatus(id)

  return (
    <div className="stack">
      <div className="page-head" style={{ marginBottom: 0 }}>
        <div>
          <p><Link to="/">← All runs</Link></p>
          <h1>{run?.label ?? 'Run'}</h1>
          {run && (
            <div className="row" style={{ marginTop: 6 }}>
              <StatusChip state={run.status} />
              {run.kind === 'precomputed' && <span className="chip">Precomputed</span>}
            </div>
          )}
        </div>
      </div>
      {!run && error && <ErrorNotice error={error} title="Could not load this run" />}
      {!run && !error && <Spinner label="Loading run" />}
      {run && (run.status === 'queued' || run.status === 'running') && <Progress run={run} />}
      {run && run.status === 'failed' && (
        <div className="callout error" role="alert">
          <div>
            <strong>This run failed</strong>
            <p>{run.error ?? 'No reason was recorded.'}</p>
            <p style={{ marginTop: 8 }}><Link to="/new">Start a new run</Link></p>
          </div>
        </div>
      )}
      {run && run.status === 'done' && <Results run={run} />}
    </div>
  )
}
