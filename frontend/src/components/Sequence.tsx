import { RESIDUE_CLASS_NAME, textClass } from '../lib/residues'

/** Each residue as its own span: hue carries charge, weight of ink carries oiliness. */
function residues(sequence: string) {
  return [...sequence].map((aa, i) => (
    // eslint-disable-next-line react/no-array-index-key -- position is the identity here
    <span key={i} className={RESIDUE_CLASS_NAME[textClass(aa)]}>
      {aa}
    </span>
  ))
}

/** A peptide at reading size, for tables and lists. */
export function Sequence({ sequence, title }: { sequence: string; title?: string }) {
  return (
    <span className="seq" title={title ?? sequence}>
      {residues(sequence)}
    </span>
  )
}

/** The peptide as the headline of its own page. */
export function SequenceHero({ sequence }: { sequence: string }) {
  return (
    <h1 className="seq-hero" aria-label={`Peptide ${sequence}`}>
      {residues(sequence)}
    </h1>
  )
}

/** The peptide inside the protein it came from, with its surroundings in grey. */
export function SequenceContext({
  before,
  peptide,
  after,
  truncatedStart,
  truncatedEnd,
}: {
  before: string
  peptide: string
  after: string
  truncatedStart: boolean
  truncatedEnd: boolean
}) {
  return (
    <p className="seq-context">
      {truncatedStart && '…'}
      {before}
      <span className="in-peptide">{residues(peptide)}</span>
      {after}
      {truncatedEnd && '…'}
    </p>
  )
}

/** What the colours mean. Shown once, next to the peptide it explains. */
export function SequenceKey() {
  return (
    <p className="seq-key">
      <span>
        <span className="sample res-basic">K R</span> basic
      </span>
      <span>
        <span className="sample res-acidic">D E</span> acidic
      </span>
      <span>
        <span className="sample res-oily">A L V</span> oily
      </span>
      <span>
        <span className="sample res-other">S G N</span> other
      </span>
      <span className="faint">Antimicrobial peptides are usually basic and part-oily.</span>
    </p>
  )
}
