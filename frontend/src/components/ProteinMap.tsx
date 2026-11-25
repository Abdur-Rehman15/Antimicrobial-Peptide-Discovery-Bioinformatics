import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { ProteinDetail } from '../api/types'
import { useElementWidth } from '../hooks/useElementWidth'
import { probability } from '../lib/format'
import { candidateLink } from '../lib/links'
import { NOVELTY_COLOR, NOVELTY_LABEL } from './Chips'

type Segment = ProteinDetail['candidates'][number]

interface Props {
  protein: ProteinDetail
  runId: string
  prevalence: number
}

const LEFT = 46 // gutter for the activity labels; both tracks share it so they stay aligned
const RIGHT = 10
const LANE = 20
const BAR = 16
const RIDGE = 118

/** Put overlapping segments on different rows so none hides another. */
export function assignLanes(segments: Pick<Segment, 'start' | 'end'>[]): number[] {
  const order = segments.map((_, i) => i).sort((a, b) => segments[a].start - segments[b].start)
  const laneEnds: number[] = []
  const lane = new Array<number>(segments.length).fill(0)
  for (const i of order) {
    let k = laneEnds.findIndex((end) => end < segments[i].start)
    if (k === -1) {
      k = laneEnds.length
      laneEnds.push(0)
    }
    laneEnds[k] = segments[i].end
    lane[i] = k
  }
  return lane
}

/** Axis ticks at round residue numbers. */
export function tickStep(length: number): number {
  for (const step of [10, 25, 50, 100, 250, 500, 1000]) if (length / step <= 8) return step
  return 2000
}

/** A round number at or just above `value`, for the top of the activity axis. */
export function ridgeMax(value: number): number {
  if (!(value > 0)) return 1
  const power = 10 ** Math.floor(Math.log10(value))
  return ([1, 2, 2.5, 5, 10].find((m) => m * power >= value) ?? 10) * power
}

/**
 * One protein, drawn as two stacked tracks over a shared residue axis:
 *
 *   the ridge   the best score of any window covering each residue, so the quiet stretches
 *               between candidates are visible too - the shortlist alone cannot show them
 *   the lanes   the candidate regions that survived merging, coloured by novelty
 *
 * Older runs were scanned before the ridge was recorded; they draw the lanes alone.
 */
export function ProteinMap({ protein, runId, prevalence }: Props) {
  const navigate = useNavigate()
  const [box, width] = useElementWidth<HTMLDivElement>(760)
  const [tip, setTip] = useState<{ c: Segment; x: number; y: number } | null>(null)
  const [scan, setScan] = useState<{ pos: number; v: number; x: number; y: number } | null>(null)

  const lanes = useMemo(() => assignLanes(protein.candidates), [protein])
  const laneCount = Math.max(1, ...lanes.map((l) => l + 1))
  const inner = width - LEFT - RIGHT
  const x = (position: number) => LEFT + ((position - 1) / protein.length) * inner

  const profile = protein.profile ?? []
  const hasRidge = profile.length > 0
  const ridgeTop = 10
  const top = ridgeMax(Math.max(0, ...profile))
  // square root, not linear: almost every residue scores near zero and one spot scores far
  // above the rest, so a linear axis would draw a flat line with a single spike. Square root
  // lifts the small values while zero stays zero, which a log axis could not do.
  const y = (v: number) => ridgeTop + RIDGE - Math.sqrt(Math.min(Math.max(v, 0), top) / top) * RIDGE
  const lanesTop = hasRidge ? ridgeTop + RIDGE + 16 : 24
  const axisY = lanesTop + laneCount * LANE + 6
  const height = axisY + 26
  const step = tickStep(protein.length)
  const ticks = [
    1,
    ...Array.from({ length: Math.floor(protein.length / step) }, (_, i) => (i + 1) * step),
  ]

  // one point per pixel column at most, keeping the peak in each column so nothing is smoothed away
  const points = useMemo(() => {
    const n = profile.length
    if (n === 0) return []
    const columns = Math.min(n, Math.max(2, Math.round(inner)))
    const out: { pos: number; v: number }[] = []
    for (let c = 0; c < columns; c++) {
      const from = Math.floor((c * n) / columns)
      const to = Math.max(from + 1, Math.floor(((c + 1) * n) / columns))
      let best = -Infinity
      let at = from
      for (let i = from; i < to; i++) {
        if (profile[i] > best) {
          best = profile[i]
          at = i
        }
      }
      out.push({ pos: at + 1, v: best })
    }
    return out
  }, [profile, inner])

  const line = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(p.pos).toFixed(1)} ${y(p.v).toFixed(1)}`)
  const base = ridgeTop + RIDGE
  const area = points.length
    ? `${line.join(' ')} L${x(points[points.length - 1].pos).toFixed(1)} ${base} L${x(points[0].pos).toFixed(1)} ${base} Z`
    : ''
  const peak = points.reduce((a, b) => (b.v > a.v ? b : a), { pos: 1, v: 0 })

  const showLane = (c: Segment, target: SVGGElement) => {
    const rect = box.current?.getBoundingClientRect()
    const t = target.getBoundingClientRect()
    if (!rect) return
    setTip({ c, x: t.left - rect.left + t.width / 2, y: t.top - rect.top })
  }

  const trackResidue = (clientX: number) => {
    const rect = box.current?.getBoundingClientRect()
    if (!rect || points.length === 0) return
    const scale = width / rect.width
    const px = (clientX - rect.left) * scale
    let best = points[0]
    for (const p of points) if (Math.abs(x(p.pos) - px) < Math.abs(x(best.pos) - px)) best = p
    setScan({ pos: best.pos, v: best.v, x: x(best.pos) / scale, y: y(best.v) / scale })
  }

  return (
    <div className="stack">
      <div className="legend">
        {(['novel', 'related', 'known'] as const).map((cls) => (
          <span key={cls}>
            <span className="dot" style={{ background: NOVELTY_COLOR[cls] }} aria-hidden />
            {NOVELTY_LABEL[cls]}
          </span>
        ))}
        <span className="faint">
          {hasRidge
            ? 'The ridge is the best score of any window covering each residue, on a square-root scale. Numbers are ranks.'
            : 'Numbers are ranks. Overlapping regions sit on separate rows.'}
        </span>
      </div>
      <div
        className="chart"
        ref={box}
        onPointerMove={(e) => trackResidue(e.clientX)}
        onPointerLeave={() => setScan(null)}
      >
        <svg
          viewBox={`0 0 ${width} ${height}`}
          role="group"
          aria-label={`Map of ${protein.accession}, ${protein.length} residues, with ${protein.candidates.length} candidate regions`}
        >
          {hasRidge && (
            <g>
              <title>{`Activity along ${protein.accession}: highest ${probability(peak.v)} near residue ${peak.pos}`}</title>
              {[0, top / 16, top / 4, top].map((v) => (
                <g key={v}>
                  <line className="grid" x1={LEFT} x2={LEFT + inner} y1={y(v)} y2={y(v)} />
                  <text x={LEFT - 8} y={y(v) + 4} textAnchor="end" className="muted-text">
                    {v === 0 ? '0' : probability(v)}
                  </text>
                </g>
              ))}
              <path d={area} fill="var(--accent)" fillOpacity={0.18} />
              <path
                d={line.join(' ')}
                fill="none"
                stroke="var(--accent)"
                strokeWidth={2}
                strokeLinejoin="round"
              />
              {scan && (
                <g>
                  <line
                    className="axis"
                    x1={x(scan.pos)}
                    x2={x(scan.pos)}
                    y1={ridgeTop}
                    y2={axisY}
                  />
                  <circle
                    cx={x(scan.pos)}
                    cy={y(scan.v)}
                    r={5}
                    fill="var(--accent)"
                    stroke="var(--surface)"
                    strokeWidth={2}
                  />
                </g>
              )}
            </g>
          )}
          {!hasRidge && <rect x={LEFT} y={14} width={inner} height={6} rx={3} fill="var(--grid)" />}

          {protein.candidates.map((c, i) => {
            const w = Math.max(4, ((c.end - c.start + 1) / protein.length) * inner)
            const top_ = lanesTop + lanes[i] * LANE
            const label = `Rank ${c.rank}, residues ${c.start} to ${c.end}, ${NOVELTY_LABEL[c.novelty_class]}`
            const open = () =>
              navigate(candidateLink(runId, { accession: protein.accession, ...c }, prevalence))
            return (
              <g
                key={`${c.start}-${c.end}`}
                tabIndex={0}
                role="link"
                aria-label={label}
                style={{ cursor: 'pointer' }}
                onPointerEnter={(e) => showLane(c, e.currentTarget)}
                onPointerLeave={() => setTip(null)}
                onFocus={(e) => showLane(c, e.currentTarget)}
                onBlur={() => setTip(null)}
                onClick={open}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') open()
                }}
              >
                <rect
                  x={x(c.start)}
                  y={top_}
                  width={w}
                  height={BAR}
                  rx={4}
                  fill={NOVELTY_COLOR[c.novelty_class]}
                  stroke="var(--surface)"
                  strokeWidth={2}
                />
                {w >= 20 && (
                  <text
                    x={x(c.start) + w / 2}
                    y={top_ + 12}
                    textAnchor="middle"
                    style={{ fill: '#fff', fontWeight: 600 }}
                  >
                    {c.rank}
                  </text>
                )}
              </g>
            )
          })}
          <line className="axis" x1={LEFT} x2={LEFT + inner} y1={axisY} y2={axisY} />
          {ticks.map((t) => (
            <text key={t} x={x(t)} y={axisY + 16} textAnchor={t === 1 ? 'start' : 'middle'}>
              {t}
            </text>
          ))}
        </svg>

        {tip && (
          <div
            className="tooltip"
            role="tooltip"
            style={{
              left: Math.min(Math.max(0, tip.x - 90), (box.current?.clientWidth ?? width) - 280),
              top: Math.max(0, tip.y - 118),
            }}
          >
            <div className="tt-title">
              #{tip.c.rank} · residues {tip.c.start}–{tip.c.end}
            </div>
            <div className="tt-seq">{tip.c.sequence}</div>
            <div className="tt-row">
              <span>Activity</span>
              <strong>{probability(tip.c.activity)}</strong>
            </div>
            <div className="tt-row">
              <span>Hemolysis</span>
              <strong>{tip.c.hemolysis_band}</strong>
            </div>
            <div className="tt-row">
              <span>Novelty</span>
              <strong>{NOVELTY_LABEL[tip.c.novelty_class]}</strong>
            </div>
          </div>
        )}
        {scan && !tip && (
          <div
            className="tooltip"
            role="tooltip"
            style={{
              left: Math.min(Math.max(0, scan.x - 80), (box.current?.clientWidth ?? width) - 190),
              top: 0,
              minWidth: 170,
            }}
          >
            <div className="tt-title">Residue {scan.pos}</div>
            <div className="tt-row">
              <span>Best window here</span>
              <strong>{probability(scan.v)}</strong>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
