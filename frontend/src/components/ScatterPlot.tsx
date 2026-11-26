import { useMemo, useState } from 'react'
import { useElementWidth } from '../hooks/useElementWidth'
import type { Candidate, NoveltyClass } from '../api/types'
import { probability } from '../lib/format'
import { NOVELTY_COLOR, NOVELTY_LABEL } from './Chips'

interface Props {
  candidates: Candidate[]
  onSelect: (candidate: Candidate) => void
  loading?: boolean
}

const MARGIN = { left: 56, right: 16, top: 16, bottom: 52 }
const HEIGHT = 420
const DOT = 5 // radius; the visible dot is 10px, the hit area is the nearest point within HIT px
const HIT = 28
const CLASSES: NoveltyClass[] = ['novel', 'related', 'known']

const formatTick = (t: number) => (t >= 1 ? '1' : String(Number(t.toPrecision(1))))

/** The decades the activity axis spans: powers of ten from the lowest to the highest value,
 *  never below 1e-4 (a probability that small is indistinguishable from zero on screen). */
export function logRange(activities: number[]): { minExp: number; maxExp: number } {
  const clean = activities.filter((a) => Number.isFinite(a) && a > 0)
  if (clean.length === 0) return { minExp: -3, maxExp: 0 }
  const hi = Math.log10(Math.min(1, Math.max(1e-4, ...clean)))
  const lo = Math.log10(Math.max(1e-4, Math.min(1, ...clean)))
  let maxExp = Math.ceil(hi - 1e-9) || 0 // `|| 0` turns -0 into 0
  let minExp = Math.max(-4, Math.floor(lo + 1e-9)) || 0
  if (minExp >= maxExp) minExp = maxExp - 1
  return { minExp, maxExp }
}

export function ScatterPlot({ candidates, onSelect, loading = false }: Props) {
  const [box, width] = useElementWidth<HTMLDivElement>(760)
  const [hover, setHover] = useState<{ c: Candidate; x: number; y: number } | null>(null)

  const plot = useMemo(() => {
    const { minExp, maxExp } = logRange(candidates.map((c) => c.activity))
    const innerW = width - MARGIN.left - MARGIN.right
    const innerH = HEIGHT - MARGIN.top - MARGIN.bottom
    const x = (risk: number) => MARGIN.left + Math.min(1, Math.max(0, risk)) * innerW
    const y = (activity: number) => {
      const e = Math.log10(Math.max(activity, 10 ** minExp))
      return MARGIN.top + innerH - ((e - minExp) / (maxExp - minExp)) * innerH
    }
    const yTicks = Array.from({ length: maxExp - minExp + 1 }, (_, i) => 10 ** (minExp + i))
    return { innerW, innerH, x, y, yTicks }
  }, [candidates, width])

  const counts = useMemo(() => {
    const out: Record<NoveltyClass, number> = { novel: 0, related: 0, known: 0 }
    for (const c of candidates) out[c.novelty_class] += 1
    return out
  }, [candidates])

  // Point positions in screen pixels, for the nearest-point hover (an 8-10px dot is too small
  // to aim at, so the pointer only has to be CLOSEST to a point, not on it).
  const points = useMemo(
    () => candidates.map((c) => ({ c, px: plot.x(c.hemolysis_risk), py: plot.y(c.activity) })),
    [candidates, plot],
  )

  function nearest(clientX: number, clientY: number) {
    const rect = box.current?.getBoundingClientRect()
    if (!rect) return null
    const scale = width / rect.width
    const mx = (clientX - rect.left) * scale
    const my = (clientY - rect.top) * scale
    let best: (typeof points)[number] | null = null
    let bestD = HIT
    for (const p of points) {
      const d = Math.hypot(p.px - mx, p.py - my)
      if (d < bestD) {
        best = p
        bestD = d
      }
    }
    return best ? { c: best.c, x: best.px / scale, y: best.py / scale } : null
  }

  const plotMax = Math.max(...candidates.map((c) => c.activity), 1e-9)
  const top3 = new Set(candidates.slice(0, 3).map((c) => c.rank))
  const bandX = [1 / 3, 2 / 3].map(plot.x)
  const bottom = MARGIN.top + plot.innerH

  return (
    <div className={`stack${loading ? ' dim' : ''}`} aria-busy={loading}>
      <div className="legend" aria-label="Novelty classes">
        {CLASSES.map((cls) => (
          <span key={cls}>
            <span className="dot" style={{ background: NOVELTY_COLOR[cls] }} aria-hidden />
            {NOVELTY_LABEL[cls]} ({counts[cls]})
          </span>
        ))}
      </div>
      <div className="chart" ref={box}
        onPointerMove={(e) => setHover(nearest(e.clientX, e.clientY))}
        onPointerLeave={() => setHover(null)}
        onClick={(e) => {
          const hit = nearest(e.clientX, e.clientY)
          if (hit) onSelect(hit.c)
        }}>
        <svg viewBox={`0 0 ${width} ${HEIGHT}`} role="img"
          aria-label={`Scatter plot of ${candidates.length} candidates: hemolysis risk on the horizontal axis, calibrated activity on the vertical axis. The ranked list shows the same data.`}>
          {plot.yTicks.map((t) => (
            <g key={t}>
              <line className="grid" x1={MARGIN.left} x2={width - MARGIN.right}
                y1={plot.y(t)} y2={plot.y(t)} />
              <text x={MARGIN.left - 8} y={plot.y(t) + 4} textAnchor="end">
                {formatTick(t)}
              </text>
            </g>
          ))}
          <line className="axis" x1={MARGIN.left} x2={width - MARGIN.right} y1={bottom} y2={bottom} />
          {[0, 0.25, 0.5, 0.75, 1].map((t) => (
            <text key={t} x={plot.x(t)} y={bottom + 16} textAnchor="middle">
              {t.toFixed(2)}
            </text>
          ))}
          {/* hemolysis bands as quiet washes rather than lines */}
          {[
            ['low', MARGIN.left, bandX[0], 'var(--risk-low)'],
            ['medium', bandX[0], bandX[1], 'var(--risk-med)'],
            ['high', bandX[1], width - MARGIN.right, 'var(--risk-high)'],
          ].map(([label, from, to, colour]) => (
            <rect key={label as string} x={from as number} y={MARGIN.top}
              width={Math.max(0, (to as number) - (from as number))} height={plot.innerH}
              fill={colour as string} opacity={0.045} />
          ))}
          {/* the corner the ranking favours: strong activity, little risk */}
          <rect x={MARGIN.left} y={MARGIN.top} width={Math.max(0, bandX[0] - MARGIN.left)}
            height={plot.innerH / 2} fill="var(--accent)" opacity={0.06} />
          <text className="muted-text" x={MARGIN.left + 8} y={MARGIN.top + 14}>
            best candidates
          </text>
          {[
            ['low', (MARGIN.left + bandX[0]) / 2],
            ['medium', (bandX[0] + bandX[1]) / 2],
            ['high', (bandX[1] + width - MARGIN.right) / 2],
          ].map(([label, cx]) => (
            <text key={label as string} className="muted-text" x={cx as number}
              y={bottom - 6} textAnchor="middle">
              {label as string} risk
            </text>
          ))}
          <text x={MARGIN.left + plot.innerW / 2} y={HEIGHT - 6} textAnchor="middle">
            Hemolysis risk (model score)
          </text>
          <text transform={`translate(14 ${MARGIN.top + plot.innerH / 2}) rotate(-90)`}
            textAnchor="middle">
            Activity (calibrated, log scale)
          </text>
          {points.map(({ c, px, py }, i) => {
            const active = hover?.c === c
            const size = DOT - 1 + 4 * Math.min(1, c.activity / Math.max(plotMax, 1e-9))
            const colour = NOVELTY_COLOR[c.novelty_class]
            return (
              <g
                key={`${c.accession}:${c.start}-${c.end}`}
                className="dot-in"
                style={{ animationDelay: `${Math.min(i, 70) * 9}ms` }}
              >
                <circle cx={px} cy={py} r={size * 2.4} fill={colour} opacity={active ? 0.3 : 0.16} />
                <circle cx={px} cy={py} r={active ? size + 2 : size} fill={colour}
                  stroke="var(--bg-surface)" strokeWidth={1.5} data-testid="point" />
              </g>
            )
          })}
          {points
            .filter(({ c }) => top3.has(c.rank))
            .map(({ c, px, py }) => (
              <text key={`l${c.rank}`} x={px + 9} y={py - 8}>
                {c.rank}
              </text>
            ))}
        </svg>
        {hover && (
          <div className="tooltip" role="tooltip"
            style={{
              left: Math.min(hover.x + 14, Math.max(0, (box.current?.clientWidth ?? width) - 290)),
              top: Math.max(0, hover.y - 8),
            }}>
            <div className="tt-title">
              #{hover.c.rank} · {hover.c.accession} {hover.c.start}–{hover.c.end}
            </div>
            <div className="tt-seq">{hover.c.sequence}</div>
            <div className="tt-row">
              <span>Activity</span>
              <strong>{probability(hover.c.activity)}</strong>
            </div>
            <div className="tt-row">
              <span>Hemolysis risk</span>
              <strong>
                {hover.c.hemolysis_risk.toFixed(2)} ({hover.c.hemolysis_band})
              </strong>
            </div>
            <div className="tt-row">
              <span>Novelty</span>
              <strong>{NOVELTY_LABEL[hover.c.novelty_class]}</strong>
            </div>
          </div>
        )}
      </div>
      <p className="hint">
        The best candidates sit top left: high activity and low hemolysis risk. Activity is on a
        log scale because most candidates are far below the best. Click a dot to open the
        candidate. The ranked list shows the same candidates.
      </p>
    </div>
  )
}
