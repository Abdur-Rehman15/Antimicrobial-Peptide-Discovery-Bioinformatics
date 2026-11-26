import { placeInRange } from '../lib/ampRanges'

/**
 * Where one property of this peptide sits against the range covered by known antimicrobial
 * peptides: the lit stretch is the middle 80% of them, the notch is their median, and the dot
 * is this candidate. Being outside the stretch is information, not a failure.
 */
export function PropertyBar({ name, value }: { name: string; value: number }) {
  const place = placeInRange(name, value)
  if (!place) return null
  const outside = place.below || place.above
  return (
    <span
      className="prop-bar"
      title={
        outside
          ? `Outside the range of most known AMPs (${place.below ? 'lower' : 'higher'})`
          : 'Within the range of most known AMPs'
      }
    >
      <span className="prop-track" />
      <span
        className="prop-band"
        style={{ left: `${place.from * 100}%`, right: `${(1 - place.to) * 100}%` }}
      />
      <span className="prop-median" style={{ left: `${place.median * 100}%` }} />
      <span
        className={`prop-dot${outside ? ' outside' : ''}`}
        style={{ left: `${place.at * 100}%` }}
      />
    </span>
  )
}
