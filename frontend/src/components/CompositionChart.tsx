import { useElementWidth } from '../hooks/useElementWidth'
import { useInView } from '../hooks/useInView'
import { percent } from '../lib/format'
import { RESIDUE_CLASS_NAME, textClass } from '../lib/residues'

const H = 210
const M = { left: 40, right: 8, top: 22, bottom: 30 }
const FILL: Record<string, string> = {
  'res-basic': 'var(--res-basic)',
  'res-acidic': 'var(--res-acidic)',
  'res-oily': 'var(--res-oily)',
  'res-other': 'var(--res-other)',
  'res-weak': 'var(--res-weak)',
}

/**
 * Share of each amino acid in the peptide, each bar in its own residue colour so the chart
 * reads the same way as the sequence above it: a wall of blue means a very basic peptide.
 * Bars grow from zero the first time the chart is scrolled into view.
 */
export function CompositionChart({ composition }: { composition: Record<string, number> }) {
  const [box, W] = useElementWidth<HTMLDivElement>(640)
  const [seen, inView] = useInView<HTMLDivElement>()
  const entries = Object.entries(composition).sort(([a], [b]) => a.localeCompare(b))
  const max = Math.max(0.1, ...entries.map(([, v]) => v))
  const top = Math.min(1, Math.ceil(max * 10) / 10)
  const innerW = W - M.left - M.right
  const innerH = H - M.top - M.bottom
  const slot = innerW / Math.max(entries.length, 1)
  const bar = Math.min(26, slot - 7)
  const y = (v: number) => M.top + innerH - (v / top) * innerH
  const tallest = entries.reduce((a, b) => (b[1] > a[1] ? b : a), entries[0] ?? ['', 0])
  const ticks = [0, top / 2, top]

  return (
    <div className="chart" ref={box}>
      <div ref={seen}>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label={`Amino acid composition; most common is ${tallest[0]} at ${percent(tallest[1])}`}
        >
          {ticks.map((t) => (
            <g key={t}>
              <line className="grid" x1={M.left} x2={W - M.right} y1={y(t)} y2={y(t)} />
              <text x={M.left - 8} y={y(t) + 4} textAnchor="end">
                {percent(t)}
              </text>
            </g>
          ))}
          {entries.map(([aa, v], i) => {
            const cx = M.left + slot * i + slot / 2
            const height = Math.max(0, M.top + innerH - y(v))
            return (
              <g key={aa}>
                <title>{`${aa}: ${percent(v, 1)}`}</title>
                {v > 0 && (
                  <rect
                    className={inView ? 'bar-grow' : undefined}
                    x={cx - bar / 2}
                    y={y(v)}
                    width={bar}
                    height={height}
                    rx={3}
                    fill={FILL[RESIDUE_CLASS_NAME[textClass(aa)]]}
                    style={{ animationDelay: `${i * 28}ms`, opacity: inView ? undefined : 0 }}
                  />
                )}
                <text x={cx} y={H - 10} textAnchor="middle">
                  {aa}
                </text>
                {aa === tallest[0] && v > 0 && (
                  <text
                    x={cx}
                    y={y(v) - 7}
                    textAnchor="middle"
                    style={{ fill: 'var(--text-primary)', fontWeight: 600 }}
                  >
                    {percent(v)}
                  </text>
                )}
              </g>
            )
          })}
          <line
            className="axis"
            x1={M.left}
            x2={W - M.right}
            y1={M.top + innerH}
            y2={M.top + innerH}
          />
        </svg>
      </div>
    </div>
  )
}
