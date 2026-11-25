import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { ErrorNotice, Meter, Spinner } from '../components/Bits'
import { StatusChip } from '../components/Chips'
import { useAsync } from '../hooks/useAsync'
import { count, duration, shortDate } from '../lib/format'

const KIND: Record<string, string> = {
  fasta: 'Pasted FASTA',
  accessions: 'UniProt accessions',
  organism: 'Organism sample',
  precomputed: 'Precomputed',
}

export function RunsPage() {
  const runs = useAsync((signal) => api.listRuns(signal), [])
  const active = runs.data?.some((r) => r.status === 'queued' || r.status === 'running') ?? false
  const { reload } = runs

  // keep the list fresh while something is running
  useEffect(() => {
    if (!active) return
    const timer = setInterval(reload, 2000)
    return () => clearInterval(timer)
  }, [active, reload])

  async function remove(id: string, label: string) {
    if (!window.confirm(`Delete the run “${label}”? Its results are removed.`)) return
    try {
      await api.deleteRun(id)
    } finally {
      reload()
    }
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Runs</h1>
          <p className="lead">
            Each run reads proteins, scores every fragment of 8 to 50 residues, and ranks the ones
            that look antimicrobial.
          </p>
        </div>
        <Link to="/new" className="button primary">
          New run
        </Link>
      </div>

      {runs.error && !runs.data && (
        <ErrorNotice error={runs.error} title="Could not load the runs" />
      )}
      {runs.loading && !runs.data && <Spinner label="Loading runs" />}
      {runs.data && runs.data.length === 0 && (
        <div className="card empty">
          <h2>No runs yet</h2>
          <p style={{ margin: '10px auto 18px', maxWidth: '46ch' }}>
            Start with a handful of proteins. The UniProt accessions P69905, P02788 and P59665 are
            a good first look: lactoferrin carries a known hidden peptide.
          </p>
          <Link to="/new" className="button primary">
            Start the first run
          </Link>
        </div>
      )}
      {runs.data && runs.data.length > 0 && (
        <div className="card flush">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Run</th>
                  <th scope="col">Status</th>
                  <th className="num" scope="col">
                    Proteins
                  </th>
                  <th className="num" scope="col">
                    Windows scanned
                  </th>
                  <th className="num" scope="col">
                    Time
                  </th>
                  <th scope="col">Started</th>
                  <th scope="col">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {runs.data.map((r) => (
                  <tr key={r.id} className="run-row">
                    <td style={{ padding: '14px' }}>
                      <Link to={`/runs/${r.id}`}>
                        <strong>{r.label}</strong>
                      </Link>
                      <div className="sub">{KIND[r.kind] ?? r.kind}</div>
                    </td>
                    <td>
                      <div className="row" style={{ gap: 10, flexWrap: 'nowrap' }}>
                        <StatusChip state={r.status} />
                        {r.status === 'running' && (
                          <div style={{ width: 72 }}>
                            <Meter value={r.progress} label={`${r.label} progress`} />
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="num">{count(r.n_proteins)}</td>
                    <td className="num">{count(r.n_windows)}</td>
                    <td className="num">{duration(r.seconds)}</td>
                    <td className="faint">{shortDate(r.created_at)}</td>
                    <td>
                      <button
                        className="quiet danger"
                        disabled={r.status === 'running'}
                        onClick={() => remove(r.id, r.label)}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
