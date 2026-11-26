import { useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { ProteinSummary, Run } from '../api/types'
import { ErrorNotice, Meter, Spinner } from '../components/Bits'
import { StatusChip } from '../components/Chips'
import { Figure } from '../components/CountUp'
import { MiniTrack } from '../components/MiniTrack'
import { ResidueRibbon } from '../components/ResidueRibbon'
import { useAsync } from '../hooks/useAsync'
import { count, duration, relativeTime } from '../lib/format'
import { DEFAULT_VIEW } from '../lib/view'

const KIND: Record<string, string> = {
  fasta: 'Pasted FASTA',
  accessions: 'UniProt accessions',
  organism: 'Organism sample',
  precomputed: 'Precomputed',
}
const DETAILED = 8 // how many finished runs get their proteins fetched for the thumbnails

type Summaries = Record<string, ProteinSummary[]>

function TrashIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path
        d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.6 8a1 1 0 0 0 1 .9h3.8a1 1 0 0 0 1-.9l.6-8"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/** A dimmed helical wheel, drawn rather than photographed, for the page with nothing on it. */
function EmptyMark() {
  const dots = Array.from({ length: 7 }, (_, i) => {
    const radians = ((i * 100) % 360) * (Math.PI / 180)
    return { x: 60 + 40 * Math.sin(radians), y: 60 - 40 * Math.cos(radians), i }
  })
  return (
    <svg width="120" height="120" viewBox="0 0 120 120" aria-hidden style={{ opacity: 0.5 }}>
      <circle cx="60" cy="60" r="40" fill="none" stroke="var(--border)" />
      <path
        d={dots.map((d, i) => `${i === 0 ? 'M' : 'L'}${d.x.toFixed(1)} ${d.y.toFixed(1)}`).join(' ')}
        fill="none"
        stroke="var(--border)"
      />
      {dots.map((d) => (
        <circle key={d.i} cx={d.x} cy={d.y} r="6" fill="none" stroke="var(--border-strong)" />
      ))}
    </svg>
  )
}

function RunCard({
  run,
  proteins,
  index,
  onDelete,
}: {
  run: Run
  proteins: ProteinSummary[] | undefined
  index: number
  onDelete: () => void
}) {
  const candidates = proteins?.reduce((sum, p) => sum + p.n_candidates, 0)
  return (
    <article
      className="run-card stagger-item"
      style={{ '--i': index } as React.CSSProperties}
    >
      <div className="run-card-head">
        <StatusChip state={run.status} />
        <button
          className="quiet card-delete"
          aria-label={`Delete run ${run.label}`}
          disabled={run.status === 'running'}
          onClick={onDelete}
        >
          <TrashIcon />
        </button>
      </div>

      <h2>
        <Link to={`/runs/${run.id}`}>{run.label}</Link>
      </h2>
      <p className="faint" style={{ fontSize: 'var(--t-small)' }}>
        {KIND[run.kind] ?? run.kind} · {relativeTime(run.created_at)}
      </p>

      {run.status === 'running' && (
        <Meter value={run.progress} label={`${run.label} progress`} />
      )}
      {run.status === 'failed' && <p className="hint">{run.error ?? 'No reason was recorded.'}</p>}
      {proteins && proteins.length > 0 && <MiniTrack proteins={proteins} />}

      <dl className="run-card-stats">
        <div>
          <dt className="label">Proteins</dt>
          <dd>{count(run.n_proteins)}</dd>
        </div>
        <div>
          <dt className="label">Windows</dt>
          <dd>{count(run.n_windows)}</dd>
        </div>
        <div>
          <dt className="label">{candidates === undefined ? 'Time' : 'Candidates'}</dt>
          <dd>{candidates === undefined ? duration(run.seconds) : count(candidates)}</dd>
        </div>
      </dl>
    </article>
  )
}

export function RunsPage() {
  const runs = useAsync((signal) => api.listRuns(signal), [])
  const active = runs.data?.some((r) => r.status === 'queued' || r.status === 'running') ?? false
  const { reload } = runs

  useEffect(() => {
    if (!active) return
    const timer = setInterval(reload, 2000)
    return () => clearInterval(timer)
  }, [active, reload])

  const finished = useMemo(
    () => (runs.data ?? []).filter((r) => r.status === 'done').slice(0, DETAILED),
    [runs.data],
  )
  const key = finished.map((r) => r.id).join(',')

  // one request per finished run: it carries both the thumbnail and the totals below
  const summaries = useAsync<Summaries>(
    async (signal) => {
      const pairs = await Promise.all(
        finished.map(
          async (r) => [r.id, await api.proteins(r.id, signal).catch(() => [])] as const,
        ),
      )
      return Object.fromEntries(pairs)
    },
    [key],
    finished.length > 0,
  )

  // the ribbon shows a real sequence: the protein with the most candidates in the newest run
  const top = useMemo(() => {
    const newest = finished[0]
    const list = newest ? summaries.data?.[newest.id] : undefined
    if (!newest || !list?.length) return null
    const best = [...list].sort((a, b) => b.n_candidates - a.n_candidates)[0]
    return { runId: newest.id, accession: best.accession }
  }, [finished, summaries.data])

  const ribbon = useAsync(
    async (signal) =>
      top ? (await api.protein(top.runId, top.accession, DEFAULT_VIEW, signal)).sequence : '',
    [top?.runId, top?.accession],
    top !== null,
  )

  const totals = useMemo(() => {
    const all = runs.data ?? []
    const lists = Object.values(summaries.data ?? {})
    return {
      windows: all.reduce((s, r) => s + (r.n_windows ?? 0), 0),
      proteins: all.reduce((s, r) => s + (r.n_proteins ?? 0), 0),
      candidates: lists.flat().reduce((s, p) => s + p.n_candidates, 0),
      residues: all.reduce((s, r) => s + (r.n_residues ?? 0), 0),
    }
  }, [runs.data, summaries.data])

  async function remove(id: string, label: string) {
    if (!window.confirm(`Delete the run “${label}”? Its results are removed.`)) return
    try {
      await api.deleteRun(id)
    } finally {
      reload()
    }
  }

  const hasRuns = (runs.data?.length ?? 0) > 0

  return (
    <div>
      {/* the heading is always here; the ribbon and the totals need runs to exist */}
      <section className="hero-band">
        {hasRuns && <ResidueRibbon sequence={ribbon.data ?? ''} />}
        <div className="hero-inner">
            <div className="page-head" style={{ marginBottom: 0 }}>
              <div>
                <h1>Runs</h1>
                <p className="lead">
                  Each run reads proteins, scores every fragment of 8 to 50 residues, and ranks
                  the ones that look antimicrobial.
                </p>
              </div>
              <Link to="/new" className="button primary">
                New run
              </Link>
            </div>
          {hasRuns && (
            <div className="metric-strip">
              <Figure label="Windows scored" value={totals.windows} hero />
              <Figure label="Candidates kept" value={totals.candidates} />
              <Figure label="Proteins scanned" value={totals.proteins} />
              <Figure label="Residues read" value={totals.residues} />
            </div>
          )}
        </div>
      </section>

      {runs.error && !runs.data && (
        <ErrorNotice error={runs.error} title="Could not load the runs" />
      )}
      {runs.loading && !runs.data && <Spinner label="Loading runs" />}

      {runs.data && runs.data.length === 0 && (
        <div className="card empty stack" style={{ alignItems: 'center', gap: 'var(--s-4)' }}>
          <EmptyMark />
          <h2>No runs yet</h2>
          <p style={{ maxWidth: '46ch' }}>
            Start with a handful of proteins. The UniProt accessions P69905, P02788 and P59665 are
            a good first look: lactoferrin carries a known hidden peptide.
          </p>
          <Link to="/new" className="button primary">
            Start the first run
          </Link>
        </div>
      )}

      {hasRuns && (
        <div className="run-grid">
          {runs.data!.map((r, i) => (
            <RunCard
              key={r.id}
              run={r}
              index={i}
              proteins={summaries.data?.[r.id]}
              onDelete={() => remove(r.id, r.label)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
