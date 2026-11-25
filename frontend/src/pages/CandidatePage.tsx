import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import { ErrorNotice, Meter, Spinner } from '../components/Bits'
import { BandChip, NOVELTY_HELP, NoveltyChip } from '../components/Chips'
import { CompositionChart } from '../components/CompositionChart'
import { HelicalWheel } from '../components/HelicalWheel'
import { SequenceContext, SequenceHero, SequenceKey } from '../components/Sequence'
import { useAsync } from '../hooks/useAsync'
import { FEATURE_LABELS, percent, plural, probability, rarity } from '../lib/format'
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
        <button className="quiet" onClick={back} style={{ alignSelf: 'flex-start' }}>
          ← Back
        </button>
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
    <div className="stack" style={{ gap: 18 }}>
      <div className="row spread">
        <button className="quiet" onClick={back}>
          ← Back to results
        </button>
        <Link to={`/runs/${id}`} className="muted">
          All candidates of this run
        </Link>
      </div>

      {/* What this peptide is, and the three numbers that decide its place in the list. */}
      <div className="sheet">
        <section className="stack" style={{ gap: 14 }}>
          <div className="row">
            <span className="chip">Rank {c.rank}</span>
            <NoveltyChip value={c.novelty_class} />
            <BandChip band={c.hemolysis_band} risk={c.hemolysis_risk} />
          </div>
          <SequenceHero sequence={c.sequence} />
          <p className="muted">
            Residues {c.start}–{c.end} of {protein.accession}
            {protein.name ? ` (${protein.name})` : ''}, {plural(c.length, 'residue')}
          </p>
          <SequenceKey />
        </section>

        <div className="score-band">
          <div>
            <h3>Antimicrobial activity</h3>
            <span className="big-number">{probability(c.activity)}</span>
            <Meter value={c.activity} label="Calibrated activity" />
            <p className="hint">
              If {rarity(prevalence)} windows were real AMPs. Raw model score{' '}
              {c.activity_score.toFixed(3)}. Read it as an ordering, not as a chance.
            </p>
          </div>
          <div>
            <h3>Hemolysis risk</h3>
            <div>
              <BandChip band={c.hemolysis_band} />
            </div>
            <p className="hint">
              Model score {c.hemolysis_risk.toFixed(2)}, where 1 means likely to burst red blood
              cells. This model is only roughly calibrated, so use the band.
            </p>
          </div>
          <div>
            <h3>Novelty</h3>
            <div>
              <NoveltyChip value={c.novelty_class} />
            </div>
            <p className="hint">
              {NOVELTY_HELP[c.novelty_class]}. Closest known AMP is{' '}
              <strong>{percent(c.max_similarity)}</strong> similar
              {c.closest_id ? ` (${c.closest_id})` : ''}.
            </p>
          </div>
        </div>

        <section>
          <h3>Where it sits in the protein</h3>
          <SequenceContext
            before={before}
            peptide={peptide}
            after={after}
            truncatedStart={lead < start - 1}
            truncatedEnd={end + 10 < (protein.length ?? 0)}
          />
        </section>
      </div>

      {/* What it is made of, and the shape that follows from the order of its residues. */}
      <div className="sheet">
        <div className="split">
          <div>
            <h2>Properties</h2>
            <dl className="facts" style={{ marginTop: 12 }}>
              {Object.entries(FEATURE_LABELS).map(([key, meta]) =>
                features[key] === undefined ? null : (
                  <div key={key} style={{ display: 'contents' }}>
                    <dt>
                      {meta.label}
                      <span className="hint">{meta.hint}</span>
                    </dt>
                    <dd>
                      {Number.isInteger(features[key]) ? features[key] : features[key].toFixed(2)}
                    </dd>
                  </div>
                ),
              )}
            </dl>
          </div>
          <div>
            <h2>Helical wheel</h2>
            <div style={{ marginTop: 12 }}>
              <HelicalWheel sequence={c.sequence} />
            </div>
            <p className="hint" style={{ marginTop: 12 }}>
              If this peptide folds into a helix, the oily and the charged residues end up on
              opposite sides, which is the classic antimicrobial shape. Whether it really folds
              that way is not known here.
            </p>
          </div>
        </div>
        <section>
          <h2>Amino acid composition</h2>
          <CompositionChart composition={composition} />
        </section>
      </div>

      {/* Is it already known, and what should be kept in mind. */}
      <div className="sheet">
        <section>
          <h2>Closest known AMP</h2>
          {alignment ? (
            <>
              <p className="muted" style={{ marginBottom: 12 }}>
                Smith-Waterman local alignment against{' '}
                <strong>{alignment.known_id || 'a database entry'}</strong> (
                <span className="mono">{alignment.known_sequence}</span>): score {alignment.score},{' '}
                {percent(alignment.identity)} identical, {percent(alignment.similarity)} similar
                {alignment.gaps ? `, ${plural(alignment.gaps, 'gap')}` : ''}. In the middle line
                “|” marks an identical residue and “:” a similar one.
              </p>
              <pre className="alignment" aria-label="Alignment">
                {alignment.text}
              </pre>
            </>
          ) : (
            <p className="muted">No alignment is available for this candidate.</p>
          )}
        </section>
        <section>
          <h2>Worth knowing</h2>
          <ul className="plain muted" style={{ marginTop: 12 }}>
            {notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  )
}
