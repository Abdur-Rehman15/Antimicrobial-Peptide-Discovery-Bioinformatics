import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import { ErrorNotice, Meter, Spinner } from '../components/Bits'
import { BandChip, NOVELTY_HELP, NoveltyChip } from '../components/Chips'
import { CompositionChart } from '../components/CompositionChart'
import { HelicalWheel } from '../components/HelicalWheel'
import { useAsync } from '../hooks/useAsync'
import { FEATURE_LABELS, percent, probability, rarity } from '../lib/format'
import { DEFAULT_PREVALENCE } from '../lib/view'

export function CandidatePage() {
  const { id = '' } = useParams()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const accession = params.get('accession') ?? ''
  const start = Number(params.get('start'))
  const end = Number(params.get('end'))
  const prevalence = Number(params.get('p')) || DEFAULT_PREVALENCE
  const detail = useAsync(
    (signal) => api.candidate(id, accession, start, end, prevalence, signal),
    [id, accession, start, end, prevalence],
  )
  const back = () => (window.history.length > 1 ? navigate(-1) : navigate(`/runs/${id}`))

  if (detail.error && !detail.data) {
    return (
      <div className="stack">
        <button className="quiet" onClick={back} style={{ alignSelf: 'flex-start' }}>← Back</button>
        <ErrorNotice error={detail.error} title="Could not load this candidate" />
      </div>
    )
  }
  if (!detail.data) return <Spinner label="Loading candidate" />

  const { candidate: c, features, composition, alignment, protein, notes } = detail.data
  const lead = Math.min(10, start - 1)
  const before = protein.context.slice(0, lead)
  const peptide = protein.context.slice(lead, lead + c.length)
  const after = protein.context.slice(lead + c.length)

  return (
    <div className="stack">
      <div className="row spread">
        <button className="quiet" onClick={back}>← Back to results</button>
        <Link to={`/runs/${id}`} className="muted">All candidates of this run</Link>
      </div>

      <div className="card stack">
        <div className="row">
          <span className="chip">Rank {c.rank}</span>
          <NoveltyChip value={c.novelty_class} />
          <BandChip band={c.hemolysis_band} risk={c.hemolysis_risk} />
        </div>
        <h1 className="seq-big" aria-label={`Peptide ${c.sequence}`}>{c.sequence}</h1>
        <p className="muted">
          Residues {c.start}–{c.end} of {protein.accession}
          {protein.name ? ` (${protein.name})` : ''}, {c.length} amino acids
        </p>
        <div>
          <p className="hint" style={{ marginBottom: 4 }}>Where it sits in the protein</p>
          <p className="context">
            {lead < start - 1 && '…'}
            {before}
            <mark>{peptide}</mark>
            {after}
            {end + 10 < (protein.length ?? 0) && '…'}
          </p>
        </div>
      </div>

      <div className="two-col">
        <div className="card stack">
          <h2>Activity</h2>
          <div className="stat">
            <span className="value">{probability(c.activity)}</span>
            <span className="label">calibrated, if {rarity(prevalence)} windows were AMPs</span>
          </div>
          <Meter value={c.activity} label="Calibrated activity" />
          <p className="hint">
            Raw model score {c.activity_score.toFixed(3)}. Read the calibrated number as an
            ordering, not as a chance.
          </p>
        </div>
        <div className="card stack">
          <h2>Hemolysis</h2>
          <div><BandChip band={c.hemolysis_band} /></div>
          <p className="muted">
            Model score {c.hemolysis_risk.toFixed(2)} (0 = unlikely to burst red blood cells, 1 =
            likely). The model is only roughly calibrated: use the band.
          </p>
        </div>
        <div className="card stack">
          <h2>Novelty</h2>
          <div><NoveltyChip value={c.novelty_class} /></div>
          <p className="muted">
            {NOVELTY_HELP[c.novelty_class]}. Highest similarity to a known AMP:{' '}
            <strong>{percent(c.max_similarity)}</strong>
            {c.closest_id ? ` (${c.closest_id})` : ''}.
          </p>
        </div>
      </div>

      <div className="two-col">
        <div className="card stack">
          <h2>Properties</h2>
          <dl className="facts">
            {Object.entries(FEATURE_LABELS).map(([key, meta]) =>
              features[key] === undefined ? null : (
                <div key={key} style={{ display: 'contents' }}>
                  <dt>
                    {meta.label}
                    <span className="hint">{meta.hint}</span>
                  </dt>
                  <dd>{Number.isInteger(features[key]) ? features[key] : features[key].toFixed(2)}</dd>
                </div>
              ),
            )}
          </dl>
        </div>
        <div className="card stack">
          <h2>Helical wheel</h2>
          <HelicalWheel sequence={c.sequence} />
          <p className="hint">
            If this peptide folds into a helix, the oily and the charged residues end up on
            opposite sides, a typical AMP shape. Whether it does fold that way is not known here.
          </p>
        </div>
      </div>

      <div className="card stack">
        <h2>Amino acid composition</h2>
        <CompositionChart composition={composition} />
      </div>

      <div className="card stack">
        <h2>Closest known AMP</h2>
        {alignment ? (
          <>
            <p className="muted">
              Smith-Waterman local alignment against <strong>{alignment.known_id || 'a database entry'}</strong>{' '}
              (<span className="mono">{alignment.known_sequence}</span>): score {alignment.score},{' '}
              {percent(alignment.identity)} identical, {percent(alignment.similarity)} similar
              {alignment.gaps ? `, ${alignment.gaps} gap(s)` : ''}. “:” marks a similar residue,
              “|” an identical one.
            </p>
            <pre className="alignment" aria-label="Alignment">{alignment.text}</pre>
          </>
        ) : (
          <p className="muted">No alignment is available for this candidate.</p>
        )}
      </div>

      <div className="card stack">
        <h2>Notes</h2>
        <ul className="plain">
          {notes.map((n) => <li key={n}>{n}</li>)}
        </ul>
      </div>
    </div>
  )
}
