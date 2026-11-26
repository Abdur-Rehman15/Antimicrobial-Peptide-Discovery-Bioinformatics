// Small formatting helpers shared by the pages.

const grouped = new Intl.NumberFormat('en-US')

export const count = (n: number | null | undefined): string =>
  n === null || n === undefined ? '-' : grouped.format(n)

/** "1 protein", "12 proteins" - never "1 protein(s)". */
export function plural(n: number, one: string, many = one + 's'): string {
  return `${count(n)} ${n === 1 ? one : many}`
}

export const percent = (x: number, digits = 0): string => `${(x * 100).toFixed(digits)}%`

/** A calibrated probability for display: 0.438, 0.024, <0.001. */
export function probability(p: number): string {
  if (p < 0.001) return '<0.001'
  if (p < 0.1) return p.toFixed(3)
  return p.toFixed(2)
}

/** 0.001 -> "1 in 1,000". */
export function rarity(prevalence: number): string {
  return `1 in ${grouped.format(Math.round(1 / prevalence))}`
}

export function duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '-'
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)} s`
  const minutes = Math.floor(seconds / 60)
  const rest = Math.round(seconds - minutes * 60)
  if (minutes < 60) return rest === 0 ? `${minutes} min` : `${minutes} min ${rest} s`
  const hours = Math.floor(minutes / 60)
  return `${hours} h ${minutes - hours * 60} min`
}

/** Rough scan time: about 14,000 windows per protein of 360 residues at 23,000 windows/s. */
export function estimatedSeconds(proteins: number, averageLength = 360): number {
  const windows = proteins * 43 * Math.max(averageLength - 28, 0)
  return windows / 23_000
}

/** "4 min ago", "3 h ago", and a date once it is more than a week old. */
export function relativeTime(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return iso
  const seconds = Math.round((Date.now() - then) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.round(hours / 24)
  if (days < 7) return days === 1 ? 'yesterday' : `${days} days ago`
  return shortDate(iso)
}

export function shortDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export const FEATURE_LABELS: Record<string, { label: string; hint: string }> = {
  length: { label: 'Length', hint: 'residues' },
  net_charge: { label: 'Net charge', hint: 'at pH 7.4; AMPs are usually positive' },
  charge_density: { label: 'Charge per residue', hint: 'net charge divided by length' },
  isoelectric_point: { label: 'Isoelectric point', hint: 'pH where the net charge is zero' },
  hydrophobic_fraction: { label: 'Hydrophobic share', hint: 'fraction of A, C, F, I, L, M, V, W' },
  mean_hydrophobicity: { label: 'Mean hydrophobicity', hint: 'Eisenberg scale' },
  gravy: { label: 'GRAVY', hint: 'Kyte-Doolittle average; negative means water-loving' },
  hydrophobic_moment_helix: {
    label: 'Helical moment',
    hint: 'how one-sided the oily face is if it folds into a helix',
  },
  aliphatic_index: { label: 'Aliphatic index', hint: 'relative volume of A, V, I, L' },
  boman_index: { label: 'Boman index', hint: 'tendency to bind other proteins' },
  frac_positive: { label: 'Positive residues', hint: 'fraction of K and R' },
  frac_negative: { label: 'Negative residues', hint: 'fraction of D and E' },
  frac_aromatic: { label: 'Aromatic residues', hint: 'fraction of F, W, Y' },
}
