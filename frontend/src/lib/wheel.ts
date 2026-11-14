// Helical wheel geometry: looking down the axis of an alpha helix, consecutive residues sit
// 100 degrees apart (3.6 residues per turn). An AMP typically has an oily side and a charged
// side; the wheel makes that visible.

export type ResidueClass = 'hydrophobic' | 'positive' | 'negative' | 'polar'

const HYDROPHOBIC = new Set('ACFILMVW')

export function residueClass(aa: string): ResidueClass {
  if (aa === 'K' || aa === 'R') return 'positive'
  if (aa === 'D' || aa === 'E') return 'negative'
  if (HYDROPHOBIC.has(aa)) return 'hydrophobic'
  return 'polar'
}

// Eisenberg consensus hydrophobicity scale, the one the backend's helical moment uses.
const EISENBERG: Record<string, number> = {
  A: 0.62, R: -2.53, N: -0.78, D: -0.9, C: 0.29, Q: -0.85, E: -0.74, G: 0.48, H: -0.4,
  I: 1.38, L: 1.06, K: -1.5, M: 0.64, F: 1.19, P: 0.12, S: -0.18, T: -0.05, W: 0.81,
  Y: 0.26, V: 1.08,
}

export const HELIX_ANGLE = 100

export interface WheelResidue {
  index: number // 0-based position in the peptide
  aa: string
  cls: ResidueClass
  angle: number // degrees, 0 = straight up, clockwise
  x: number
  y: number
}

/** Position of every residue on a circle of `radius` around (cx, cy); residue 1 is at the top. */
export function wheelPositions(sequence: string, radius: number, cx = 0, cy = 0): WheelResidue[] {
  return [...sequence].map((aa, index) => {
    const angle = (index * HELIX_ANGLE) % 360
    const radians = (angle * Math.PI) / 180
    return {
      index,
      aa,
      cls: residueClass(aa),
      angle,
      x: cx + radius * Math.sin(radians),
      y: cy - radius * Math.cos(radians),
    }
  })
}

/** Direction (degrees, 0 = up, clockwise) of the hydrophobic moment, and its size per residue.
 *  Returns null when the moment is zero or the sequence is empty. */
export function momentDirection(sequence: string): { angle: number; magnitude: number } | null {
  let sx = 0
  let sy = 0
  let n = 0
  for (const [index, aa] of [...sequence].entries()) {
    const h = EISENBERG[aa]
    if (h === undefined) continue
    const radians = (index * HELIX_ANGLE * Math.PI) / 180
    sx += h * Math.sin(radians)
    sy += h * Math.cos(radians)
    n += 1
  }
  const magnitude = Math.hypot(sx, sy) / Math.max(n, 1)
  if (n === 0 || magnitude < 1e-9) return null
  const angle = ((Math.atan2(sx, sy) * 180) / Math.PI + 360) % 360
  return { angle, magnitude }
}
