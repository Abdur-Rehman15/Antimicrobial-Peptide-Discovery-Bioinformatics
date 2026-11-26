import { useMemo } from 'react'
import { RESIDUE_CLASS_NAME, textClass } from '../lib/residues'

const ROWS = 4
const PER_ROW = 150

/**
 * A real protein sequence drifting behind the page heading, each residue in its own colour: the
 * subject matter used as texture rather than an invented pattern. It is the sequence of the
 * protein that produced the most candidates in the newest run.
 *
 * Drawn as a few offset rows so it reads as a field rather than a stray line of text, kept to a
 * bounded number of letters so the DOM stays small, and stopped for anyone who asks for less
 * motion.
 */
export function ResidueRibbon({ sequence }: { sequence: string }) {
  const rows = useMemo(() => {
    if (sequence.length < 8) return []
    return Array.from({ length: ROWS }, (_, row) => {
      // start each row at a different point in the protein so they do not march in step
      const offset = (row * 61) % sequence.length
      const rotated = (sequence + sequence).slice(offset, offset + PER_ROW)
      const text = rotated.repeat(Math.max(2, Math.ceil(PER_ROW / Math.max(rotated.length, 1))))
      return [...text.slice(0, PER_ROW)]
    })
  }, [sequence])

  if (rows.length === 0) return null

  return (
    <div className="ribbon" aria-hidden>
      {rows.map((letters, row) => {
        const run = letters.map((aa, i) => (
          // eslint-disable-next-line react/no-array-index-key -- position is the identity
          <span key={i} className={RESIDUE_CLASS_NAME[textClass(aa)]}>
            {aa}
          </span>
        ))
        return (
          <div
            className="ribbon-run"
            key={row}
            style={{
              animationDuration: `${150 + row * 40}s`,
              animationDirection: row % 2 ? 'reverse' : 'normal',
            }}
          >
            <span>{run}</span>
            <span>{run}</span>
          </div>
        )
      })}
    </div>
  )
}
