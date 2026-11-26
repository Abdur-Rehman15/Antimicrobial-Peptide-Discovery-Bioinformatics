import { useState } from 'react'
import type { AlignmentInfo } from '../api/types'
import { RESIDUE_CLASS_NAME, textClass } from '../lib/residues'
import { percent } from '../lib/format'

function Letter({ aa }: { aa: string }) {
  if (aa === '-') return <span className="res-gap">–</span>
  return <span className={RESIDUE_CLASS_NAME[textClass(aa)]}>{aa}</span>
}

/** Identity as a ring, so the headline number is readable at a glance. */
function IdentityRing({ fraction }: { fraction: number }) {
  const r = 26
  const circumference = 2 * Math.PI * r
  return (
    <div className="identity-ring">
      <svg width="68" height="68" viewBox="0 0 68 68" aria-hidden>
        <circle cx="34" cy="34" r={r} fill="none" stroke="var(--border)" strokeWidth="5" />
        <circle
          cx="34"
          cy="34"
          r={r}
          fill="none"
          stroke="var(--accent)"
          strokeWidth="5"
          strokeLinecap="round"
          strokeDasharray={`${circumference * fraction} ${circumference}`}
          transform="rotate(-90 34 34)"
        />
      </svg>
      <span className="identity-value">{percent(fraction)}</span>
    </div>
  )
}

/**
 * The Smith-Waterman alignment as two sequences rather than a block of monospace text: the
 * candidate above, the closest known AMP below, and a bar between them wherever the two agree.
 * The raw text is still one click away, because that is the form you paste into a paper.
 */
export function AlignmentView({ alignment }: { alignment: AlignmentInfo }) {
  const [copied, setCopied] = useState(false)
  const columns = [...alignment.aligned_query].map((aa, i) => ({
    query: aa,
    target: alignment.aligned_target[i] ?? '-',
    mark: alignment.midline[i] ?? ' ',
  }))

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(alignment.text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1600)
    } catch {
      setCopied(false)
    }
  }

  return (
    <div className="stack">
      <div className="align-head">
        <IdentityRing fraction={alignment.identity} />
        <dl className="align-facts">
          <div>
            <dt className="label">Identical</dt>
            <dd>{percent(alignment.identity)}</dd>
          </div>
          <div>
            <dt className="label">Similar</dt>
            <dd>{percent(alignment.similarity)}</dd>
          </div>
          <div>
            <dt className="label">Score</dt>
            <dd>{alignment.score}</dd>
          </div>
          <div>
            <dt className="label">Gaps</dt>
            <dd>{alignment.gaps}</dd>
          </div>
        </dl>
        <button className="quiet" onClick={copy}>
          {copied ? 'Copied' : 'Copy raw'}
        </button>
      </div>

      <div className="align-grid" role="img" aria-label={`Alignment: ${percent(alignment.identity)} of columns identical`}>
        <span className="label align-row-label">This peptide</span>
        <div className="align-row">
          {columns.map((c, i) => (
            // eslint-disable-next-line react/no-array-index-key -- column position is the identity
            <span key={i} className="align-cell">
              <Letter aa={c.query} />
            </span>
          ))}
        </div>
        <span />
        <div className="align-row">
          {columns.map((c, i) => (
            // eslint-disable-next-line react/no-array-index-key -- column position is the identity
            <span key={i} className="align-cell">
              <span
                className={`align-link${c.mark === '|' ? ' same' : c.mark === ':' ? ' alike' : ''}`}
              />
            </span>
          ))}
        </div>
        <span className="label align-row-label">{alignment.known_id || 'Known AMP'}</span>
        <div className="align-row">
          {columns.map((c, i) => (
            // eslint-disable-next-line react/no-array-index-key -- column position is the identity
            <span key={i} className="align-cell">
              <Letter aa={c.target} />
            </span>
          ))}
        </div>
      </div>
      <p className="hint">
        A bar joins two residues that are identical; a shorter one means the swap is a
        conservative one under BLOSUM62.
      </p>
    </div>
  )
}
