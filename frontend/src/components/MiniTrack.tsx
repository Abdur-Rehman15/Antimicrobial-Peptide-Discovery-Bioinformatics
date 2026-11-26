import type { ProteinSummary } from '../api/types'

const W = 240
const H = 26

/**
 * A run at a glance: every protein it read, laid end to end, each one lit by the best score
 * found inside it. Wide blocks are long proteins; bright blocks are where the model found
 * something. It is the same idea as the full protein track, shrunk to a thumbnail.
 */
export function MiniTrack({ proteins }: { proteins: ProteinSummary[] }) {
  if (proteins.length === 0) return null
  const order = [...proteins].sort((a, b) => b.best_activity_score - a.best_activity_score)
  const total = order.reduce((sum, p) => sum + p.length, 0) || 1
  const gap = order.length > 1 ? 2 : 0
  const usable = W - gap * (order.length - 1)

  let x = 0
  const blocks = order.map((p) => {
    const width = Math.max(3, (p.length / total) * usable)
    const block = { ...p, x, width }
    x += width + gap
    return block
  })

  return (
    <svg
      className="mini-track"
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={`${proteins.length} protein${proteins.length === 1 ? '' : 's'}, shaded by the best score found in each`}
    >
      {blocks.map((b) => (
        <g key={b.accession}>
          <rect x={b.x} y={0} width={b.width} height={H} rx={3} fill="var(--border-subtle)" />
          <rect
            x={b.x}
            y={0}
            width={b.width}
            height={H}
            rx={3}
            fill="var(--accent)"
            opacity={0.15 + 0.85 * Math.min(1, b.best_activity_score)}
          />
        </g>
      ))}
    </svg>
  )
}
