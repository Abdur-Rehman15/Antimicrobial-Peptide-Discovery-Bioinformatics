import { Link, useNavigate } from 'react-router-dom'
import type { Candidate } from '../api/types'
import { useFlipRows } from '../hooks/useFlipRows'
import { probability } from '../lib/format'
import { candidateLink } from '../lib/links'
import { BandChip, NoveltyChip } from './Chips'
import { Sequence } from './Sequence'

interface Props {
  runId: string
  rows: Candidate[]
  prevalence: number
  loading?: boolean
}

const COLUMNS = ['#', 'Peptide', 'Where', 'Length', 'Activity', 'Hemolysis', 'Novelty', 'Score']
const keyOf = (c: Candidate) => `${c.accession}:${c.start}-${c.end}`

/**
 * The ranked candidates, and the keyboard and screen-reader path to every point of the charts:
 * each row links to its candidate.
 *
 * Built from elements carrying table roles rather than a real <table>, because changing a
 * ranking weight re-orders these rows and they animate to their new positions — a transform on
 * a <tr> is not something to rely on.
 */
export function ResultsTable({ runId, rows, prevalence, loading = false }: Props) {
  const navigate = useNavigate()
  const attach = useFlipRows(rows.map(keyOf).join('|'))

  if (rows.length === 0) {
    return <p className="empty">No candidate matches these filters.</p>
  }

  return (
    <div className={`table-wrap${loading ? ' dim' : ''}`} aria-busy={loading}>
      <div className="rank-table" role="table" aria-label="Candidate peptides, best first">
        <div className="rank-row rank-head" role="row">
          {COLUMNS.map((name) => (
            <span key={name} role="columnheader" className="label">
              {name}
            </span>
          ))}
        </div>

        {rows.map((c) => {
          const href = candidateLink(runId, c, prevalence)
          const key = keyOf(c)
          return (
            <div
              key={key}
              ref={attach(key)}
              role="row"
              className={`rank-row${c.rank <= 3 ? ' top' : ''}`}
              onClick={() => navigate(href)}
            >
              <span role="cell" className="rank-mark">
                {c.rank <= 3 ? <span className="rank-chip">{c.rank}</span> : c.rank}
              </span>
              <span role="cell">
                <Link to={href}>
                  <Sequence sequence={c.sequence} />
                </Link>
              </span>
              <span role="cell" className="faint">
                <span style={{ color: 'var(--text-secondary)' }}>{c.accession}</span> {c.start}–
                {c.end}
              </span>
              <span role="cell" className="num">
                {c.length}
              </span>
              <span role="cell" className="activity-cell">
                <span className="num">{probability(c.activity)}</span>
                <span
                  className="inline-bar"
                  aria-hidden
                  style={{ '--w': `${Math.min(100, c.activity * 100)}%` } as React.CSSProperties}
                />
              </span>
              <span role="cell">
                <BandChip band={c.hemolysis_band} risk={c.hemolysis_risk} />
              </span>
              <span role="cell">
                <NoveltyChip value={c.novelty_class} />
              </span>
              <span role="cell" className="num faint">
                {c.rank_score.toPrecision(2)}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
