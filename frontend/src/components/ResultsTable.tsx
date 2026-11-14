import { Link, useNavigate } from 'react-router-dom'
import type { Candidate } from '../api/types'
import { abbreviate, probability } from '../lib/format'
import { candidateLink } from '../lib/links'
import { BandChip, NoveltyChip } from './Chips'
import { Meter } from './Bits'

interface Props {
  runId: string
  rows: Candidate[]
  prevalence: number
  loading?: boolean
}

/** The ranked candidates. This is also the keyboard- and screen-reader path to every point of
 *  the charts: each row links to the candidate's page. */
export function ResultsTable({ runId, rows, prevalence, loading = false }: Props) {
  const navigate = useNavigate()
  if (rows.length === 0) {
    return <p className="empty">No candidate matches these filters.</p>
  }
  return (
    <div className={`table-wrap${loading ? ' dim' : ''}`} aria-busy={loading}>
      <table>
        <caption className="sr-only">Candidate peptides, best first</caption>
        <thead>
          <tr>
            <th className="num" scope="col">#</th>
            <th scope="col">Peptide</th>
            <th scope="col">Where</th>
            <th className="num" scope="col">Length</th>
            <th scope="col">Activity</th>
            <th scope="col">Hemolysis</th>
            <th scope="col">Novelty</th>
            <th className="num" scope="col">Score</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => {
            const href = candidateLink(runId, c, prevalence)
            return (
              <tr key={`${c.accession}:${c.start}-${c.end}`} onClick={() => navigate(href)}
                style={{ cursor: 'pointer' }}>
                <td className="num">{c.rank}</td>
                <td>
                  <Link to={href} className="seq" title={c.sequence}>
                    {abbreviate(c.sequence, 22)}
                  </Link>
                </td>
                <td>
                  <span>{c.accession}</span>{' '}
                  <span className="faint">
                    {c.start}–{c.end}
                  </span>
                </td>
                <td className="num">{c.length}</td>
                <td>
                  <div className="row" style={{ gap: 8, flexWrap: 'nowrap' }}>
                    <span style={{ minWidth: 40, fontVariantNumeric: 'tabular-nums' }}>
                      {probability(c.activity)}
                    </span>
                    <div style={{ width: 44 }}>
                      <Meter value={c.activity} label={`Activity ${probability(c.activity)}`} />
                    </div>
                  </div>
                </td>
                <td>
                  <BandChip band={c.hemolysis_band} risk={c.hemolysis_risk} />
                </td>
                <td>
                  <NoveltyChip value={c.novelty_class} />
                </td>
                <td className="num">{c.rank_score.toPrecision(2)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
