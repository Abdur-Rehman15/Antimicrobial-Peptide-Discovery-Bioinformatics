import { useElementWidth } from '../hooks/useElementWidth'
import { percent } from '../lib/format'

const H = 200
const M = { left: 36, right: 8, top: 18, bottom: 28 }

/** Share of each amino acid in the peptide. One series, so no legend; the tallest bar is
 *  labelled and every bar has a tooltip. */
export function CompositionChart({ composition }: { composition: Record<string, number> }) {
  const [box, W] = useElementWidth<HTMLDivElement>(640)
  const entries = Object.entries(composition).sort(([a], [b]) => a.localeCompare(b))
  const max = Math.max(0.1, ...entries.map(([, v]) => v))
  const top = Math.min(1, Math.ceil(max * 10) / 10)
  const innerW = W - M.left - M.right
  const innerH = H - M.top - M.bottom
  const slot = innerW / entries.length
  const bar = Math.min(24, slot - 6)
  const y = (v: number) => M.top + innerH - (v / top) * innerH
  const tallest = entries.reduce((a, b) => (b[1] > a[1] ? b : a), entries[0] ?? ['', 0])
  const ticks = [0, top / 2, top]

  return (
    <div className="chart" ref={box}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img"
        aria-label={`Amino acid composition; most common is ${tallest[0]} at ${percent(tallest[1])}`}>
        {ticks.map((t) => (
          <g key={t}>
            <line className="grid" x1={M.left} x2={W - M.right} y1={y(t)} y2={y(t)} />
            <text x={M.left - 6} y={y(t) + 4} textAnchor="end">{percent(t)}</text>
          </g>
        ))}
        {entries.map(([aa, v], i) => {
          const cx = M.left + slot * i + slot / 2
          const h = Math.max(0, M.top + innerH - y(v))
          return (
            <g key={aa}>
              <title>{`${aa}: ${percent(v, 1)}`}</title>
              {v > 0 && (
                <path
                  d={`M${cx - bar / 2} ${M.top + innerH} v${-Math.max(h - 4, 0)} q0 -4 4 -4 h${bar - 8} q4 0 4 4 v${Math.max(h - 4, 0)} z`}
                  fill="var(--accent)" />
              )}
              <text x={cx} y={H - 10} textAnchor="middle">{aa}</text>
              {aa === tallest[0] && v > 0 && (
                <text x={cx} y={y(v) - 5} textAnchor="middle" style={{ fill: 'var(--ink)', fontWeight: 600 }}>
                  {percent(v)}
                </text>
              )}
            </g>
          )
        })}
        <line className="axis" x1={M.left} x2={W - M.right} y1={M.top + innerH} y2={M.top + innerH} />
      </svg>
    </div>
  )
}
