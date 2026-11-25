import type { TextClass } from '../lib/residues'
import { momentDirection, wheelPositions } from '../lib/wheel'

const W = 420
const H = 300
const CX = W / 2
const CY = 112
const RADIUS = 84
const DOT = 11
const HEADS_TOP = 196
const HEADS_BOTTOM = 276

// The same reading as the sequence itself: hue is charge, and the oily residues are the dark
// ones. A filled disc suits the wheel, whose job is to show whether the oily side is one face.
const FILL: Record<TextClass, string> = {
  basic: 'var(--res-basic)',
  'weak-basic': 'var(--res-weak)',
  acidic: 'var(--res-acidic)',
  oily: 'var(--res-oily-disc)',
  other: 'var(--line)',
}
const LETTER: Record<TextClass, string> = {
  basic: '#fff',
  'weak-basic': '#fff',
  acidic: '#fff',
  oily: 'var(--res-oily-ink)',
  other: 'var(--ink)',
}
const NAME: Record<TextClass, string> = {
  basic: 'Basic (K, R)',
  'weak-basic': 'Weakly basic (H)',
  acidic: 'Acidic (D, E)',
  oily: 'Oily (A C F I L M V W)',
  other: 'Other',
}
const ORDER: TextClass[] = ['basic', 'weak-basic', 'acidic', 'oily', 'other']

/** A row of lipids: a head group on a stalk of two tails. */
function Lipids({ y, pointingDown }: { y: number; pointingDown: boolean }) {
  const length = 36
  const tip = pointingDown ? y + length : y - length
  return (
    <g aria-hidden>
      {Array.from({ length: Math.floor(W / 20) }, (_, i) => {
        const x = (W % 20) / 2 + 10 + i * 20
        return (
          <g key={i}>
            <path
              d={`M${x - 3} ${y} Q${x - 5} ${(y + tip) / 2} ${x - 2} ${tip}`}
              fill="none"
              stroke="var(--line)"
              strokeWidth={2}
              strokeLinecap="round"
            />
            <path
              d={`M${x + 3} ${y} Q${x + 5} ${(y + tip) / 2} ${x + 2} ${tip}`}
              fill="none"
              stroke="var(--line)"
              strokeWidth={2}
              strokeLinecap="round"
            />
            <circle cx={x} cy={y} r={6} fill="var(--line)" />
          </g>
        )
      })}
    </g>
  )
}

/**
 * The peptide seen down the axis of an alpha helix: each residue sits 100 degrees after the one
 * before it, so a helix with its oily residues on one side shows them as one face.
 *
 * The wheel is turned so that the computed hydrophobic moment points down, into a drawn membrane.
 * That is an illustration of a number this app does compute, not a predicted structure: nothing
 * here says the peptide folds into a helix at all.
 */
export function HelicalWheel({ sequence }: { sequence: string }) {
  const moment = momentDirection(sequence)
  // turn the wheel so the oily face points down (180 degrees in this clockwise-from-up frame)
  const turn = moment ? 180 - moment.angle : 0
  const placed = wheelPositions(sequence, 1).map((r) => {
    const radius = Math.max(RADIUS - (r.index / 3.6) * 4, 34)
    const radians = (((r.angle + turn) % 360) * Math.PI) / 180
    return { ...r, x: CX + radius * Math.sin(radians), y: CY - radius * Math.cos(radians) }
  })
  const path = placed
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)} ${p.y.toFixed(1)}`)
    .join(' ')
  const present = ORDER.filter((cls) => placed.some((p) => p.cls === cls))
  const first = placed[0]

  return (
    <figure style={{ margin: 0 }} className="stack">
      <div className="chart" style={{ maxWidth: 440, margin: '0 auto' }}>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label={`Helical wheel of ${sequence}, turned so its oily face points at a membrane. Each residue sits 100 degrees after the one before it.`}
        >
          {moment && (
            <g>
              <rect
                x={0}
                y={HEADS_TOP}
                width={W}
                height={HEADS_BOTTOM - HEADS_TOP}
                fill="var(--wash)"
              />
              <Lipids y={HEADS_TOP} pointingDown />
              <Lipids y={HEADS_BOTTOM} pointingDown={false} />
              <text x={6} y={HEADS_TOP - 18} className="muted-text">
                water
              </text>
              <text x={6} y={(HEADS_TOP + HEADS_BOTTOM) / 2 + 4} className="muted-text">
                membrane
              </text>
            </g>
          )}
          <circle cx={CX} cy={CY} r={RADIUS} fill="none" stroke="var(--grid)" />
          <path d={path} fill="none" stroke="var(--axis)" strokeWidth={1} />
          {moment && (
            <g>
              <line
                x1={CX}
                y1={CY}
                x2={CX}
                y2={CY + 58}
                stroke="var(--ink-2)"
                strokeWidth={2}
                strokeLinecap="round"
              />
              <path d={`M${CX - 5} ${CY + 52} L${CX} ${CY + 62} L${CX + 5} ${CY + 52}`}
                fill="var(--ink-2)" />
            </g>
          )}
          {placed.map((p) => (
            <g key={p.index}>
              <title>{`Residue ${p.index + 1}: ${p.aa}`}</title>
              <circle
                cx={p.x}
                cy={p.y}
                r={DOT}
                fill={FILL[p.cls]}
                stroke="var(--surface)"
                strokeWidth={2}
              />
              <text
                x={p.x}
                y={p.y + 4}
                textAnchor="middle"
                style={{ fill: LETTER[p.cls], fontWeight: 600 }}
              >
                {p.aa}
              </text>
            </g>
          ))}
          {first && (
            <text x={first.x} y={first.y - DOT - 5} textAnchor="middle" className="muted-text">
              start
            </text>
          )}
        </svg>
      </div>
      <figcaption className="stack" style={{ gap: 8 }}>
        <p className="legend">
          {present.map((cls) => (
            <span key={cls}>
              <span className="dot" style={{ background: FILL[cls] }} aria-hidden />
              {NAME[cls]}
            </span>
          ))}
        </p>
        <p className="hint">
          {moment
            ? 'The arrow is this peptide’s oily side, and the wheel is turned so it faces the membrane. That is how an antimicrobial peptide is thought to attack: the oily face slips between the lipids while the basic residues hold on to the surface. Whether this peptide folds into a helix at all is not known here.'
            : 'This peptide has no oily side to speak of, so there is no direction to show.'}
        </p>
      </figcaption>
    </figure>
  )
}
