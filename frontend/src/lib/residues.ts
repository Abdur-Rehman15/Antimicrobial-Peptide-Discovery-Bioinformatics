// How a residue is drawn when a peptide is shown as text.
//
// What makes a peptide antimicrobial is mostly that it is CATIONIC and AMPHIPATHIC, so the
// display gives each of those its own visual channel:
//
//     hue  = charge at pH 7.4  (blue basic, red acidic, neutral otherwise)
//     wash = oily              (a shaded patch behind the letter)
//
// Charge is a diverging quantity, so it gets the diverging colour pair; hydrophobic patches
// become visible as shading rather than as a third hue. Charged and oily residues are disjoint
// sets, so a letter never needs both.
//
// `wheelClass` in `wheel.ts` is a different, four-way grouping for the helical wheel's own
// legend: it has no diverging axis to show and colours histidine as plain polar.

export type TextClass = 'basic' | 'weak-basic' | 'acidic' | 'oily' | 'other'

const OILY = new Set('ACFILMVW')

export function textClass(aa: string): TextClass {
  if (aa === 'K' || aa === 'R') return 'basic'
  if (aa === 'H') return 'weak-basic' // only partly protonated at pH 7.4
  if (aa === 'D' || aa === 'E') return 'acidic'
  return OILY.has(aa) ? 'oily' : 'other'
}

export const RESIDUE_CLASS_NAME: Record<TextClass, string> = {
  basic: 'res-basic',
  'weak-basic': 'res-weak',
  acidic: 'res-acidic',
  oily: 'res-oily',
  other: 'res-other',
}

/** Counts per class, for the one-line summary under a sequence. */
export function chargeSummary(sequence: string): { basic: number; acidic: number; oily: number } {
  let basic = 0
  let acidic = 0
  let oily = 0
  for (const aa of sequence) {
    const cls = textClass(aa)
    if (cls === 'basic') basic += 1
    else if (cls === 'acidic') acidic += 1
    else if (cls === 'oily') oily += 1
  }
  return { basic, acidic, oily }
}
