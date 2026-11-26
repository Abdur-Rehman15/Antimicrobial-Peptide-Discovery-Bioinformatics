import { useEffect, useState } from 'react'

export const STAGES = [
  {
    name: 'Scan',
    blurb: 'Every fragment of 8 to 50 residues is described by 35 numbers and scored.',
    icon: (
      <>
        <rect x="2" y="7" width="20" height="3" rx="1.5" fill="currentColor" opacity="0.35" />
        <rect x="5" y="4" width="7" height="9" rx="2" fill="currentColor" />
      </>
    ),
  },
  {
    name: 'Merge',
    blurb: 'Overlapping fragments are one finding, so the best of each region is kept.',
    icon: (
      <>
        <rect x="2" y="4" width="9" height="4" rx="2" fill="currentColor" opacity="0.35" />
        <rect x="6" y="9" width="9" height="4" rx="2" fill="currentColor" opacity="0.35" />
        <rect x="2" y="14" width="13" height="4" rx="2" fill="currentColor" />
      </>
    ),
  },
  {
    name: 'Check',
    blurb: 'Hemolysis risk, and novelty against 17,492 known antimicrobial peptides.',
    icon: (
      <>
        <circle cx="9" cy="9" r="6" fill="none" stroke="currentColor" strokeWidth="2" />
        <path d="M13.5 13.5 19 19" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </>
    ),
  },
  {
    name: 'Rank',
    blurb: 'Activity, safety and novelty combine into one order you control.',
    icon: (
      <>
        <rect x="3" y="12" width="4" height="7" rx="1.5" fill="currentColor" opacity="0.45" />
        <rect x="9.5" y="7" width="4" height="12" rx="1.5" fill="currentColor" opacity="0.7" />
        <rect x="16" y="3" width="4" height="16" rx="1.5" fill="currentColor" />
      </>
    ),
  },
] as const

/** Which stage a progress message belongs to, using the words the backend actually sends. */
export function stageFromMessage(message: string): number {
  const m = message.toLowerCase()
  if (m.includes('merging')) return 1
  if (m.includes('hemolysis') || m.includes('novelty')) return 2
  if (m.includes('done')) return 3
  return 0
}

/**
 * The four things a run does, shown as a diagram rather than a list.
 *
 * With `idle` it walks through the stages on a loop, as a preview of what pressing the button
 * will do. With a real `active` stage it is the live state of a run.
 */
export function PipelineStages({
  active,
  idle = false,
  horizontal = false,
  detail,
}: {
  active?: number
  idle?: boolean
  horizontal?: boolean
  detail?: string
}) {
  const [looped, setLooped] = useState(0)

  useEffect(() => {
    if (!idle) return
    const still = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
    if (still) return
    const timer = setInterval(() => setLooped((n) => (n + 1) % STAGES.length), 1300)
    return () => clearInterval(timer)
  }, [idle])

  const current = idle ? looped : (active ?? 0)

  return (
    <ol className={`pipeline${horizontal ? ' horizontal' : ''}`}>
      {STAGES.map((stage, i) => {
        const state = i < current ? 'done' : i === current ? 'now' : 'next'
        return (
          <li key={stage.name} className={`pipe-step ${state}`}>
            <span className="pipe-icon" aria-hidden>
              <svg width="22" height="22" viewBox="0 0 22 22">
                {stage.icon}
              </svg>
            </span>
            <span className="pipe-body">
              <span className="pipe-name">{stage.name}</span>
              <span className="hint">{stage.blurb}</span>
              {i === current && detail && !idle && <span className="pipe-detail">{detail}</span>}
            </span>
          </li>
        )
      })}
    </ol>
  )
}
