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

const LEFT = 8
const RIGHT = 8
const LANE = 20
const BAR = 16

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

/** The protein as a bar, with every candidate region drawn where it sits. */
export function ProteinMap({ protein, runId, prevalence }: Props) {
  const navigate = useNavigate()
  const [box, WIDTH] = useElementWidth<HTMLDivElement>(700)
  const [tip, setTip] = useState<{ c: Segment; x: number; y: number } | null>(null)
  const lanes = useMemo(() => assignLanes(protein.candidates), [protein])
  const laneCount = Math.max(1, ...lanes.map((l) => l + 1))
  const inner = WIDTH - LEFT - RIGHT
  const x = (position: number) => LEFT + ((position - 1) / protein.length) * inner
  const barTop = 10
  const lanesTop = barTop + 14
  const axisY = lanesTop + laneCount * LANE + 6
  const height = axisY + 26
  const step = tickStep(protein.length)
  const ticks = [1, ...Array.from({ length: Math.floor(protein.length / step) }, (_, i) => (i + 1) * step)]

  const show = (c: Segment, target: SVGGElement) => {
    const rect = box.current?.getBoundingClientRect()
    const t = target.getBoundingClientRect()
    if (!rect) return
    setTip({ c, x: t.left - rect.left + t.width / 2, y: t.top - rect.top })
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
        <span className="faint">Numbers are ranks. Overlapping regions sit on separate rows.</span>
      </div>
      <div className="chart" ref={box}>
        <svg viewBox={`0 0 ${WIDTH} ${height}`} role="group"
          aria-label={`Map of ${protein.accession}, ${protein.length} residues, with ${protein.candidates.length} candidate regions`}>
          <rect x={LEFT} y={barTop} width={inner} height={6} rx={3} fill="var(--grid)" />
          {protein.candidates.map((c, i) => {
            const w = Math.max(4, ((c.end - c.start + 1) / protein.length) * inner)
            const y = lanesTop + lanes[i] * LANE
            const label = `Rank ${c.rank}, residues ${c.start} to ${c.end}, ${NOVELTY_LABEL[c.novelty_class]}`
            return (
              <g key={`${c.start}-${c.end}`} tabIndex={0} role="link" aria-label={label}
                style={{ cursor: 'pointer' }}
                onPointerEnter={(e) => show(c, e.currentTarget)}
                onPointerLeave={() => setTip(null)}
                onFocus={(e) => show(c, e.currentTarget)}
                onBlur={() => setTip(null)}
                onClick={() => navigate(candidateLink(runId, { accession: protein.accession, ...c }, prevalence))}
                onKeyDown={(e) => {
                  if (e.key === 'Enter')
                    navigate(candidateLink(runId, { accession: protein.accession, ...c }, prevalence))
                }}>
                <rect x={x(c.start)} y={y} width={w} height={BAR} rx={4}
                  fill={NOVELTY_COLOR[c.novelty_class]} stroke="var(--surface)" strokeWidth={2} />
                {w >= 20 && (
                  <text x={x(c.start) + w / 2} y={y + 12} textAnchor="middle"
                    style={{ fill: '#fff', fontWeight: 600 }}>
                    {c.rank}
                  </text>
                )}
              </g>
            )
          })}
          <line className="axis" x1={LEFT} x2={LEFT + inner} y1={axisY} y2={axisY} />
          {ticks.map((t) => (
            <text key={t} x={x(t)} y={axisY + 16}
              textAnchor={t === 1 ? 'start' : 'middle'}>
              {t}
            </text>
          ))}
        </svg>
        {tip && (
          <div className="tooltip" role="tooltip"
            style={{ left: Math.min(Math.max(0, tip.x - 90), (box.current?.clientWidth ?? WIDTH) - 280),
              top: Math.max(0, tip.y - 118) }}>
            <div className="tt-title">
              #{tip.c.rank} · residues {tip.c.start}–{tip.c.end}
            </div>
            <div className="tt-seq">{tip.c.sequence}</div>
            <div className="tt-row"><span>Activity</span><strong>{probability(tip.c.activity)}</strong></div>
            <div className="tt-row">
              <span>Hemolysis</span>
              <strong>{tip.c.hemolysis_band}</strong>
            </div>
            <div className="tt-row"><span>Novelty</span><strong>{NOVELTY_LABEL[tip.c.novelty_class]}</strong></div>
          </div>
        )}
      </div>
    </div>
  )
}
