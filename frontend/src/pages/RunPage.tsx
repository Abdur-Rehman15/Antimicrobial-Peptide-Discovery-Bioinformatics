import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import type { Run, View } from '../api/types'
import { ErrorNotice, Meter, Spinner } from '../components/Bits'
import { StatusChip } from '../components/Chips'
import { PipelineStages, stageFromMessage } from '../components/PipelineStages'
import { ProteinMap } from '../components/ProteinMap'
import { ResultsControls } from '../components/ResultsControls'
import { ResultsTable } from '../components/ResultsTable'
import { ScatterPlot } from '../components/ScatterPlot'
import { useAsync } from '../hooks/useAsync'
import { useDebounced } from '../hooks/useDebounced'
import { useRunStatus } from '../hooks/useRunStatus'
import { Figure } from '../components/CountUp'
import { count, duration, percent, plural } from '../lib/format'
import { candidateLink } from '../lib/links'
import { parseView, serializeView } from '../lib/view'

const PAGE = 25
type Tab = 'list' | 'proteins'
const TABS: [Tab, string][] = [
  ['list', 'Ranked list'],
  ['proteins', 'Proteins'],
]

function Progress({ run }: { run: Run }) {
  return (
    <div className="card stack" style={{ maxWidth: 620 }}>
      <h2>{run.status === 'queued' ? 'Waiting for a free worker' : 'Scanning'}</h2>
      <Meter value={run.progress} label="Run progress" big />
      <p aria-live="polite">
        <strong>{percent(run.progress)}</strong> · {run.message}
      </p>
      {/* which of the four stages the backend's own message says it is on */}
      <PipelineStages active={stageFromMessage(run.message)} />
      {run.n_proteins !== null && (
        <p className="muted">
          {plural(run.n_proteins, 'protein')}, {count(run.n_residues)} residues.
        </p>
      )}
      <p className="hint">This page updates by itself. You can leave it and come back from Runs.</p>
    </div>
  )
}

function Results({ run }: { run: Run }) {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const tab: Tab = (['list', 'proteins'] as const).find((t) => t === params.get('tab')) ?? 'list'

  // `draft` follows the sliders at once; `view` (debounced) drives requests and the address
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
  )
  const firstWithCandidates = useMemo(
    () =>
      proteins.data?.slice().sort((a, b) => b.n_candidates - a.n_candidates)[0]?.accession ?? null,
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
    <div className="workspace">
      <ResultsControls view={draft} onChange={setDraft} proteins={proteins.data} />

      <div className="stack" style={{ minWidth: 0 }}>
        {!(all.data && all.data.rows.length === 0) && (
          <div className="card">
            <div className="row spread" style={{ marginBottom: 'var(--s-3)' }}>
              <h2>Activity against safety</h2>
              <span className="hint">Every candidate that passes the filters</span>
            </div>
            {all.error && !all.data && <ErrorNotice error={all.error} />}
            {!all.data && !all.error && <Spinner label="Loading candidates" />}
            {all.data && (
              <ScatterPlot
                candidates={all.data.rows}
                loading={all.loading}
                onSelect={(c) => navigate(candidateLink(run.id, c, view.prevalence))}
              />
            )}
          </div>
        )}

        <div className="row spread">
          <div className="tabs" role="tablist" aria-label="Views">
            {TABS.map(([value, text]) => (
              <button
                key={value}
                role="tab"
                aria-selected={tab === value}
                onClick={() => setTab(value)}
              >
                {text}
              </button>
            ))}
          </div>
          <a className="button" href={api.csvUrl(run.id, view)} download>
            Export CSV
          </a>
        </div>

        {tab === 'list' && (
          <div className="card flush">
            {list.error && !list.data && (
              <div style={{ padding: 16 }}>
                <ErrorNotice error={list.error} />
              </div>
            )}
            {!list.data && !list.error && <Spinner label="Loading candidates" />}
            {list.data && (
              <>
                <ResultsTable
                  runId={run.id}
                  rows={list.data.rows}
                  prevalence={view.prevalence}
                  loading={list.loading}
                />
                <div className="pager">
                  <span className="muted">
                    {total === 0 ? 'No candidates' : `Showing ${first}–${last} of ${count(total)}`}
                  </span>
                  <div className="row">
                    <button disabled={page === 0} onClick={() => setPage(page - 1)}>
                      Previous
                    </button>
                    <button disabled={last >= total} onClick={() => setPage(page + 1)}>
                      Next
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>
        )}

        {tab === 'proteins' && (
          <div className="panes">
            <div className="card flush">
              {!proteins.data && <Spinner label="Loading proteins" />}
              <div className="protein-list" role="group" aria-label="Proteins">
                {proteins.data
                  ?.slice()
                  .sort((a, b) => b.n_candidates - a.n_candidates)
                  .map((p) => (
                    <button
                      key={p.accession}
                      aria-pressed={p.accession === accession}
                      onClick={() => setSelected(p.accession)}
                    >
                      <span>
                        <strong>{p.accession}</strong>
                        <br />
                        <span className="faint">
                          {p.name.slice(0, 30) || `${count(p.length)} residues`}
                        </span>
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
                    <p className="muted" style={{ marginTop: 4 }}>
                      {protein.data.name}, {count(protein.data.length)} residues,{' '}
                      {plural(protein.data.candidates.length, 'candidate region')} with the current
                      filters
                    </p>
                  </div>
                  {protein.data.candidates.length === 0 ? (
                    <p className="empty">No candidate region in this protein matches the filters.</p>
                  ) : (
                    <ProteinMap
                      protein={protein.data}
                      runId={run.id}
                      prevalence={view.prevalence}
                    />
                  )}
                </div>
              )}
            </div>
          </div>
        )}
        <p className="callout">
          Moving a slider re-ranks the saved shortlist; nothing is scanned again. The activity
          number is calibrated for an assumed rarity of AMPs and should be read as an ordering.
        </p>
      </div>
    </div>
  )
}

export function RunPage() {
  const { id = '' } = useParams()
  const { run, error } = useRunStatus(id)

  return (
    <div className="stack" style={{ gap: 20 }}>
      <div>
        <p style={{ marginBottom: 10 }}>
          <Link to="/">← All runs</Link>
        </p>
        <div className="stack" style={{ gap: 10 }}>
          <div className="row" style={{ gap: 14 }}>
            <h1>{run?.label ?? 'Run'}</h1>
            {run && <StatusChip state={run.status} />}
            {run?.kind === 'precomputed' && <span className="chip">Precomputed</span>}
          </div>
          {run?.status === 'done' && (
            <div className="metric-strip" aria-label="Run summary" role="group">
              <Figure label="Windows scored" value={run.n_windows ?? 0} hero />
              <Figure label="Proteins" value={run.n_proteins ?? 0} />
              <Figure label="Residues" value={run.n_residues ?? 0} />
              <Figure label="Candidates kept" value={run.options.top_n ?? 0} />
              <Figure
                label="Scan time"
                value={Math.round((run.seconds ?? 0) * 10)}
                format={(n) => duration(n / 10)}
              />
            </div>
          )}
          {run && run.notes.length > 0 && (
            <p className="hint" style={{ maxWidth: '72ch' }}>
              {run.notes.join(' ')}
            </p>
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
            <p style={{ marginTop: 8 }}>
              <Link to="/new">Start a new run</Link>
            </p>
          </div>
        </div>
      )}
      {run && run.status === 'done' && <Results run={run} />}
    </div>
  )
}
