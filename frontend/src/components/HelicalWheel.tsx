import type { TextClass } from '../lib/residues'
import { momentDirection, wheelPositions } from '../lib/wheel'

const W = 560
const H = 400
const CX = W / 2
const CY = 150
const RADIUS = 118
const DOT = 16
const HEADS_TOP = 266
const HEADS_BOTTOM = 352
const LIPID_GAP = 22

// The same reading as the sequence itself: hue is charge, and the oily residues are the amber
// ones. A filled disc suits the wheel, whose job is to show whether the oily side is one face.
const FILL: Record<TextClass, string> = {
  basic: 'var(--res-basic)',
  'weak-basic': 'var(--res-weak)',
  acidic: 'var(--res-acidic)',
  oily: 'var(--res-oily)',
  other: 'var(--res-other)',
}
// Every residue colour is a light fill, so a letter on a disc is always dark.
const LETTER = 'var(--bg-base)'
const NAME: Record<TextClass, string> = {
  basic: 'Basic (K, R)',
  'weak-basic': 'Weakly basic (H)',
  acidic: 'Acidic (D, E)',
  oily: 'Oily (A C F I L M V W)',
  other: 'Other',
}
const ORDER: TextClass[] = ['basic', 'weak-basic', 'acidic', 'oily', 'other']

/** A row of lipids: a head group on a stalk of two tails, drifting as if in water. */
function Lipids({ y, pointingDown }: { y: number; pointingDown: boolean }) {
  const length = 40
  const tip = pointingDown ? y + length : y - length
  const count = Math.floor(W / LIPID_GAP)
  return (
    <g aria-hidden>
      {Array.from({ length: count }, (_, i) => {
        const x = (W % LIPID_GAP) / 2 + 11 + i * LIPID_GAP
        return (
          <g
            key={i}
            className="lipid"
            style={{ animationDelay: `${(i % 7) * 320}ms`, transformOrigin: `${x}px ${y}px` }}
          >
            <path
              d={`M${x - 3} ${y} Q${x - 6} ${(y + tip) / 2} ${x - 2} ${tip}`}
              fill="none"
              stroke="var(--border)"
              strokeWidth={2}
              strokeLinecap="round"
            />
            <path
              d={`M${x + 3} ${y} Q${x + 6} ${(y + tip) / 2} ${x + 2} ${tip}`}
              fill="none"
              stroke="var(--border)"
              strokeWidth={2}
              strokeLinecap="round"
            />
            <circle cx={x} cy={y} r={6} fill="var(--border)" />
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
 * The wheel is turned so that the computed hydrophobic moment points down, into a drawn
 * membrane. That is an illustration of a number this app does compute, not a predicted
 * structure: nothing here says the peptide folds into a helix at all.
 */
export function HelicalWheel({
  sequence,
  highlight = null,
  onHover,
}: {
  sequence: string
  highlight?: number | null
  onHover?: (index: number | null) => void
}) {
  const moment = momentDirection(sequence)
  // turn the wheel so the oily face points down (180 degrees in this clockwise-from-up frame)
  const turn = moment ? 180 - moment.angle : 0
  const placed = wheelPositions(sequence, 1).map((r) => {
    const radius = Math.max(RADIUS - (r.index / 3.6) * 5, 48)
    const radians = (((r.angle + turn) % 360) * Math.PI) / 180
    return { ...r, x: CX + radius * Math.sin(radians), y: CY - radius * Math.cos(radians) }
  })
  const path = placed
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)} ${p.y.toFixed(1)}`)
    .join(' ')
  const present = ORDER.filter((cls) => placed.some((p) => p.cls === cls))
  const first = placed[0]
  // where residue 1 sits on the dial, after the wheel is turned to face the membrane
  const firstAngle = ((first?.angle ?? 0) + turn) % 360

  return (
    <figure style={{ margin: 0 }} className="stack">
      <div className="chart wheel-chart">
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
                fill="var(--bg-raised)"
              />
              <Lipids y={HEADS_TOP} pointingDown />
              <Lipids y={HEADS_BOTTOM} pointingDown={false} />
              <text x={10} y={HEADS_TOP - 20} className="muted-text">
                water
              </text>
              <text x={10} y={(HEADS_TOP + HEADS_BOTTOM) / 2 + 4} className="muted-text">
                membrane
              </text>
            </g>
          )}
          <circle
            className="draw"
            cx={CX}
            cy={CY}
            r={RADIUS}
            fill="none"
            stroke="var(--border)"
            pathLength={1}
          />
          <path
            className="draw"
            d={path}
            fill="none"
            stroke="var(--axis)"
            strokeWidth={1.5}
            pathLength={1}
            style={{ animationDelay: '180ms' }}
          />
          {moment && (
            <g className="moment-arrow">
              <line
                x1={CX}
                y1={CY}
                x2={CX}
                y2={CY + 78}
                stroke="var(--text-secondary)"
                strokeWidth={2}
                strokeLinecap="round"
              />
              <path
                d={`M${CX - 6} ${CY + 70} L${CX} ${CY + 82} L${CX + 6} ${CY + 70}`}
                fill="var(--text-secondary)"
              />
            </g>
          )}
          {placed.map((p) => (
            <g
              key={p.index}
              className={`wheel-dot${highlight === p.index ? ' hi' : ''}`}
              style={{ animationDelay: `${260 + p.index * 55}ms` }}
              onPointerEnter={() => onHover?.(p.index)}
              onPointerLeave={() => onHover?.(null)}
            >
              <title>{`Residue ${p.index + 1}: ${p.aa}`}</title>
              {highlight === p.index && (
                <circle cx={p.x} cy={p.y} r={DOT + 8} fill={FILL[p.cls]} opacity={0.3} />
              )}
              <circle
                cx={p.x}
                cy={p.y}
                r={DOT}
                fill={FILL[p.cls]}
                stroke="var(--bg-surface)"
                strokeWidth={2}
              />
              <text
                x={p.x}
                y={p.y + 5}
                textAnchor="middle"
                style={{ fill: LETTER, fontWeight: 600, fontSize: 15 }}
              >
                {p.aa}
              </text>
            </g>
          ))}
          {first && (
            /* Straight up from the first dot lands on a neighbour, because the residues
               spiral inward. Sit the label outside the ring instead, on the same radius. */
            <text
              x={CX + (RADIUS + DOT + 13) * Math.sin((firstAngle * Math.PI) / 180)}
              y={CY - (RADIUS + DOT + 13) * Math.cos((firstAngle * Math.PI) / 180)}
              textAnchor={
                Math.sin((firstAngle * Math.PI) / 180) > 0.3
                  ? 'start'
                  : Math.sin((firstAngle * Math.PI) / 180) < -0.3
                    ? 'end'
                    : 'middle'
              }
              dominantBaseline="middle"
              className="muted-text"
            >
              start
            </text>
          )}
        </svg>
      </div>
      <figcaption className="stack" style={{ gap: 'var(--s-2)' }}>
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
