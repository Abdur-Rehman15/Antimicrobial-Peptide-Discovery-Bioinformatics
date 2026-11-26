/**
 * What a typical antimicrobial peptide looks like, so a candidate's numbers can be read against
 * something instead of in a vacuum.
 *
 * Each entry is [10th percentile, median, 90th percentile] measured over the 10,056 known active
 * peptides in this project's own training set (label 1 of data/processed/activity_dataset.csv).
 * They describe peptides that are already known to work; they are not a threshold a candidate
 * has to meet, and sitting outside a band is not a fault.
 */
export const AMP_RANGE: Record<string, [number, number, number]> = {
  length: [12, 20, 38],
  net_charge: [0.99, 3.99, 7.99],
  charge_density: [0.033, 0.211, 0.441],
  isoelectric_point: [8.06, 11.02, 12.79],
  hydrophobic_fraction: [0.3, 0.462, 0.625],
  mean_hydrophobicity: [-0.53, -0.039, 0.365],
  gravy: [-1.409, -0.172, 1.036],
  hydrophobic_moment_helix: [0.104, 0.34, 0.684],
  aliphatic_index: [34, 97.2, 164.2],
  boman_index: [-0.83, 1.235, 3.987],
  frac_positive: [0.087, 0.235, 0.444],
  frac_negative: [0, 0, 0.083],
  frac_aromatic: [0, 0.095, 0.25],
}

export interface Placement {
  /** 0 to 1 across the drawn axis */
  at: number
  median: number
  /** where the typical band starts and ends on that same axis */
  from: number
  to: number
  below: boolean
  above: boolean
}

/**
 * Put a value on an axis that runs a little wider than the typical band, so a peptide outside
 * the band still lands somewhere visible rather than pinned to the very edge.
 */
export function placeInRange(key: string, value: number): Placement | null {
  const range = AMP_RANGE[key]
  if (!range) return null
  const [low, median, high] = range
  const pad = Math.max((high - low) * 0.35, 1e-6)
  const min = low - pad
  const max = high + pad
  const scale = (v: number) => Math.min(1, Math.max(0, (v - min) / (max - min)))
  return {
    at: scale(value),
    median: scale(median),
    from: scale(low),
    to: scale(high),
    below: value < low,
    above: value > high,
  }
}
