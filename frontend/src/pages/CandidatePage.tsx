import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import { ErrorNotice, Meter, Spinner } from '../components/Bits'
import { AlignmentView } from '../components/AlignmentView'
import { BandChip, NoveltyChip } from '../components/Chips'
import { CompositionChart } from '../components/CompositionChart'
import { HelicalWheel } from '../components/HelicalWheel'
import { PropertyBar } from '../components/PropertyBar'
import { SequenceContext, SequenceHero, SequenceKey } from '../components/Sequence'
import { useAsync } from '../hooks/useAsync'
import { FEATURE_LABELS, percent, plural, probability, rarity } from '../lib/format'
import { DEFAULT_PREVALENCE } from '../lib/view'

const BAND_METER: Record<string, string> = {
  low: 'var(--risk-low)',
  medium: 'var(--risk-med)',
  high: 'var(--risk-high)',
}

export function CandidatePage() {
  const { id = '' } = useParams()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [marked, setMarked] = useState<number | null>(null)
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
    <div className="stack" style={{ gap: 'var(--s-6)' }}>
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
        <section className="stack" style={{ gap: 'var(--s-4)' }}>
          <div className="row">
            <span className="chip">Rank {c.rank}</span>
            <NoveltyChip value={c.novelty_class} />
            <BandChip band={c.hemolysis_band} risk={c.hemolysis_risk} />
          </div>
          <SequenceHero sequence={c.sequence} highlight={marked} onHover={setMarked} />
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
            <Meter value={c.activity} label="Calibrated activity" big />
            <p className="hint">
              If {rarity(prevalence)} windows were real AMPs. Raw model score{' '}
              {c.activity_score.toFixed(3)}. Read it as an ordering, not as a chance.
            </p>
          </div>
          <div>
            <h3>Hemolysis risk</h3>
            <span className="big-number" style={{ color: BAND_METER[c.hemolysis_band] }}>
              {c.hemolysis_risk.toFixed(2)}
            </span>
            <div
              className="meter big"
              role="progressbar"
              aria-label="Hemolysis risk"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(c.hemolysis_risk * 100)}
            >
              <span
                style={{
                  width: `${c.hemolysis_risk * 100}%`,
                  background: BAND_METER[c.hemolysis_band],
                  boxShadow: 'none',
                }}
              />
            </div>
            <p className="hint">
              1 means likely to burst red blood cells. This model is only roughly calibrated, so
              use the band: <strong>{c.hemolysis_band}</strong>.
            </p>
          </div>
          <div>
            <h3>Closest known AMP</h3>
            <span className="big-number">{percent(c.max_similarity)}</span>
            <Meter value={c.max_similarity} label="Similarity to the closest known AMP" big />
            <p className="hint">
              similar to {c.closest_id || 'its nearest match'}. Comparing a peptide with 17,492
              known AMPs and keeping the best match reaches this much by chance alone, which is
              why it still counts as <NoveltyChip value={c.novelty_class} />.
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

      {/* The shape that follows from the order of its residues. */}
      <div className="sheet">
        <section>
          <h2>Helical wheel</h2>
          <HelicalWheel sequence={c.sequence} highlight={marked} onHover={setMarked} />
        </section>
        <section>
          <h2>Properties</h2>
          <p className="hint" style={{ marginBottom: 'var(--s-4)' }}>
            The lit stretch on each bar is where the middle 80% of 10,056 known antimicrobial
            peptides sit, and the notch is their median. Being outside it is information, not a
            fault.
          </p>
          <dl className="facts">
            {Object.entries(FEATURE_LABELS).map(([key, meta]) =>
              features[key] === undefined ? null : (
                <div key={key} style={{ display: 'contents' }}>
                  <dt>
                    {meta.label}
                    <span className="hint">{meta.hint}</span>
                  </dt>
                  <dd className="fact-bar">
                    <PropertyBar name={key} value={features[key]} />
                  </dd>
                  <dd>
                    {Number.isInteger(features[key]) ? features[key] : features[key].toFixed(2)}
                  </dd>
                </div>
              ),
            )}
          </dl>
        </section>
      </div>

      {/* What it is made of, and whether anyone has seen it before. */}
      <div className="sheet">
        <section>
          <h2>Amino acid composition</h2>
          <CompositionChart composition={composition} />
        </section>
        <section>
          <h2>Closest known AMP</h2>
          {alignment ? (
            <AlignmentView alignment={alignment} />
          ) : (
            <p className="muted">No alignment is available for this candidate.</p>
          )}
        </section>
      </div>

      <div className="callout">
        <div className="stack" style={{ gap: 'var(--s-2)' }}>
          <strong className="label">Worth knowing</strong>
          <ul className="plain" style={{ fontSize: 'var(--t-small)' }}>
            {notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}
