import { momentDirection, wheelPositions, type ResidueClass } from '../lib/wheel'

const SIZE = 340
const CENTER = SIZE / 2
const RADIUS = 125
const DOT = 12

const FILL: Record<ResidueClass, string> = {
  positive: 'var(--c-novel)', // blue
  negative: 'var(--c-related)', // orange
  hydrophobic: 'var(--c-known)', // aqua
  polar: 'var(--grid)',
}
const NAME: Record<ResidueClass, string> = {
  positive: 'Positive (K, R)',
  negative: 'Negative (D, E)',
  hydrophobic: 'Oily (A C F I L M V W)',
  polar: 'Other',
}

/** The peptide as seen down the axis of an alpha helix (100 degrees per residue). Many AMPs put
 *  the oily residues on one side and the charged ones on the other; the arrow points to the
 *  oily side. This is only meaningful if the peptide really does fold into a helix. */
export function HelicalWheel({ sequence }: { sequence: string }) {
  // later turns spiral inward so residues of long peptides do not sit on top of each other
  const placed = wheelPositions(sequence, 1).map((r) => {
    const radius = Math.max(RADIUS - (r.index / 3.6) * 5, 48)
    const radians = (r.angle * Math.PI) / 180
    return { ...r, x: CENTER + radius * Math.sin(radians), y: CENTER - radius * Math.cos(radians) }
  })
  const moment = momentDirection(sequence)
  const tip = moment && {
    x: CENTER + 70 * Math.sin((moment.angle * Math.PI) / 180),
    y: CENTER - 70 * Math.cos((moment.angle * Math.PI) / 180),
  }
  const path = placed.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ')

  return (
    <figure style={{ margin: 0 }} className="stack">
      <div className="chart" style={{ maxWidth: 380, margin: '0 auto' }}>
        <svg viewBox={`0 0 ${SIZE} ${SIZE}`} role="img"
          aria-label={`Helical wheel of ${sequence}. Residue 1 is at the top; each next residue is 100 degrees clockwise.`}>
          <circle cx={CENTER} cy={CENTER} r={RADIUS} fill="none" stroke="var(--grid)" />
          <path d={path} fill="none" stroke="var(--axis)" strokeWidth={1} />
          {moment && tip && (
            <g>
              <line x1={CENTER} y1={CENTER} x2={tip.x} y2={tip.y} stroke="var(--ink-2)"
                strokeWidth={2} strokeLinecap="round" />
              <circle cx={tip.x} cy={tip.y} r={4} fill="var(--ink-2)" />
              <text x={CENTER + 92 * Math.sin((moment.angle * Math.PI) / 180)}
                y={CENTER - 92 * Math.cos((moment.angle * Math.PI) / 180) + 4}
                textAnchor="middle" className="muted-text">
                oily side
              </text>
            </g>
          )}
          {placed.map((p) => (
            <g key={p.index}>
              <title>{`Residue ${p.index + 1}: ${p.aa}`}</title>
              <circle cx={p.x} cy={p.y} r={DOT} fill={FILL[p.cls]} stroke="var(--surface)" strokeWidth={2} />
              <text x={p.x} y={p.y + 4} textAnchor="middle"
                style={{ fill: p.cls === 'polar' ? 'var(--ink)' : '#fff', fontWeight: 600 }}>
                {p.aa}
              </text>
            </g>
          ))}
        </svg>
      </div>
      <figcaption className="legend">
        {(Object.keys(FILL) as ResidueClass[]).map((cls) => (
          <span key={cls}>
            <span className="dot" style={{ background: FILL[cls] }} aria-hidden />
            {NAME[cls]}
          </span>
        ))}
      </figcaption>
    </figure>
  )
}
