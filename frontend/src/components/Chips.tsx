import type { HemolysisBand, NoveltyClass, RunState } from '../api/types'

export const NOVELTY_COLOR: Record<NoveltyClass, string> = {
  novel: 'var(--c-novel)',
  related: 'var(--c-related)',
  known: 'var(--c-known)',
}

export const NOVELTY_LABEL: Record<NoveltyClass, string> = {
  novel: 'Novel',
  related: 'Related',
  known: 'Known',
}

export const NOVELTY_HELP: Record<NoveltyClass, string> = {
  novel: 'Not clearly similar to any known AMP',
  related: 'Similar to a known AMP, more than chance explains',
  known: 'Identical to, or a piece of, a known AMP',
}

/** A coloured dot plus the word: colour never carries the meaning alone. */
export function NoveltyChip({ value }: { value: NoveltyClass }) {
  return (
    <span className="chip" title={NOVELTY_HELP[value]}>
      <span className="dot" style={{ background: NOVELTY_COLOR[value] }} aria-hidden />
      {NOVELTY_LABEL[value]}
    </span>
  )
}

const BAND_TEXT: Record<HemolysisBand, string> = {
  low: 'Low risk',
  medium: 'Medium risk',
  high: 'High risk',
}

/** Status colours are always paired with an icon and a label. */
export function BandChip({ band, risk }: { band: HemolysisBand; risk?: number }) {
  const colour = { low: 'var(--good)', medium: 'var(--warn)', high: 'var(--crit)' }[band]
  const title =
    `Predicted hemolysis (red blood cell damage): ${band}.` +
    (risk !== undefined ? ` Model score ${risk.toFixed(2)}, only roughly calibrated.` : '')
  return (
    <span className={`chip band-${band}`} title={title}>
      <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
        {band === 'low' && (
          <>
            <circle cx="7" cy="7" r="6" fill={colour} />
            <path d="M4 7.2 6.1 9.2 10 5" stroke="#fff" strokeWidth="1.8" fill="none" />
          </>
        )}
        {band === 'medium' && (
          <>
            <path d="M7 1 13 12H1z" fill={colour} />
            <path d="M7 5v3.2M7 9.6v.2" stroke="#0b0b0b" strokeWidth="1.6" />
          </>
        )}
        {band === 'high' && (
          <>
            <circle cx="7" cy="7" r="6" fill={colour} />
            <path d="M4.6 4.6 9.4 9.4M9.4 4.6 4.6 9.4" stroke="#fff" strokeWidth="1.8" />
          </>
        )}
      </svg>
      <span style={{ color: 'var(--ink)' }}>{BAND_TEXT[band]}</span>
    </span>
  )
}

const STATE_TEXT: Record<RunState, string> = {
  queued: 'Queued',
  running: 'Running',
  done: 'Done',
  failed: 'Failed',
}

export function StatusChip({ state }: { state: RunState }) {
  const colour = {
    queued: 'var(--muted)',
    running: 'var(--accent)',
    done: 'var(--good)',
    failed: 'var(--crit)',
  }[state]
  return (
    <span className="chip">
      <span className="dot" style={{ background: colour }} aria-hidden />
      {STATE_TEXT[state]}
    </span>
  )
}
