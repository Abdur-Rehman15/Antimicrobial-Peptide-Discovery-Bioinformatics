// Shapes of the backend's JSON (see docs/API.md and src/amp_triage/api/).

export type RunState = 'queued' | 'running' | 'done' | 'failed'
export type NoveltyClass = 'known' | 'related' | 'novel'
export type HemolysisBand = 'low' | 'medium' | 'high'

export interface Run {
  id: string
  label: string
  kind: 'fasta' | 'accessions' | 'organism' | 'precomputed'
  status: RunState
  progress: number
  message: string
  created_at: string
  started_at: string | null
  finished_at: string | null
  n_proteins: number | null
  n_residues: number | null
  n_windows: number | null
  seconds: number | null
  error: string | null
  notes: string[]
  options: { top_n?: number; max_overlap?: number; prevalence?: number }
}

export interface Candidate {
  rank: number
  accession: string
  start: number // 1-based, inclusive
  end: number
  length: number
  sequence: string
  activity_score: number // raw model score
  activity: number // calibrated for the assumed rarity
  hemolysis_score: number
  hemolysis_risk: number
  hemolysis_band: HemolysisBand
  novelty_class: NoveltyClass
  max_similarity: number
  closest_known: string
  closest_id: string
  rank_score: number
}

export interface ResultsPage {
  total: number
  offset: number
  limit: number
  prevalence: number
  weights: { activity: number; safety: number; novelty: number }
  rows: Candidate[]
}

export interface AlignmentInfo {
  known_sequence: string
  known_id: string
  score: number
  identity: number
  similarity: number
  gaps: number
  query_start: number
  target_start: number
  aligned_query: string
  aligned_target: string
  midline: string
  text: string
}

export interface CandidateDetail {
  candidate: Candidate
  features: Record<string, number>
  composition: Record<string, number>
  alignment: AlignmentInfo | null
  protein: { accession: string; name: string; length: number | null; sequence: string; context: string }
  notes: string[]
}

export interface ProteinSummary {
  accession: string
  name: string
  length: number
  n_candidates: number
  best_activity_score: number
}

export interface ProteinDetail {
  accession: string
  name: string
  length: number
  sequence: string
  candidates: Pick<
    Candidate,
    | 'rank'
    | 'start'
    | 'end'
    | 'length'
    | 'sequence'
    | 'activity'
    | 'hemolysis_risk'
    | 'hemolysis_band'
    | 'novelty_class'
    | 'rank_score'
  >[]
}

export interface Organism {
  taxon_id: number
  name: string
  reviewed_proteins: number
}

export type MetricSet = Record<string, number>

export interface Info {
  default_prevalence: number
  limits: { max_residues: number; max_proteins: number; scan_speed_windows_per_second: number }
  rank_formula: string
  novelty_labels: Record<NoveltyClass, string>
  activity_test: { all: MetricSet; natural: MetricSet; synthetic: MetricSet } | null
  hemolysis_test: Record<string, { value: number; ci95: [number, number] }> | null
  caveat: string
}

export type RunSource =
  | { type: 'fasta'; text: string }
  | { type: 'accessions'; accessions: string[] }
  | { type: 'organism'; taxon_id: number; max_proteins: number; seed?: number }

export interface RunRequest {
  source: RunSource
  options: { top_n: number; max_overlap?: number; prevalence: number }
  label?: string
}

/** How the saved shortlist is re-ranked and filtered (nulls mean "not set"). */
export interface View {
  activityWeight: number
  safetyWeight: number
  noveltyWeight: number
  prevalence: number
  hideKnown: boolean
  novelty: NoveltyClass[] // empty = all classes
  maxHemolysis: number | null
  minLength: number | null
  maxLength: number | null
  accession: string | null
}
