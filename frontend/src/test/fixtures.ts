import type {
  Candidate,
  CandidateDetail,
  ProteinDetail,
  ProteinSummary,
  ResultsPage,
  Run,
} from '../api/types'

export function candidate(overrides: Partial<Candidate> = {}): Candidate {
  return {
    rank: 1,
    accession: 'P02788',
    start: 360,
    end: 367,
    length: 8,
    sequence: 'RRARVVWC',
    activity_score: 0.979,
    activity: 0.438,
    hemolysis_score: 0.09,
    hemolysis_risk: 0.09,
    hemolysis_band: 'low',
    novelty_class: 'novel',
    max_similarity: 0.64,
    closest_known: 'AGRQWIKAYLRREIRKVGRKARIAW',
    closest_id: 'DBAASPS_17143',
    rank_score: 0.399,
    ...overrides,
  }
}

export function run(overrides: Partial<Run> = {}): Run {
  return {
    id: 'abc123def456',
    label: 'Test run',
    kind: 'accessions',
    status: 'done',
    progress: 1,
    message: 'done',
    created_at: '2026-11-15T10:00:00+00:00',
    started_at: '2026-11-15T10:00:01+00:00',
    finished_at: '2026-11-15T10:00:09+00:00',
    n_proteins: 12,
    n_residues: 2820,
    n_windows: 106812,
    seconds: 11.9,
    error: null,
    notes: [],
    options: { top_n: 120, prevalence: 0.001 },
    ...overrides,
  }
}

export function resultsPage(rows: Candidate[], overrides: Partial<ResultsPage> = {}): ResultsPage {
  return {
    total: rows.length,
    offset: 0,
    limit: 25,
    prevalence: 0.001,
    weights: { activity: 1, safety: 1, novelty: 1 },
    rows,
    ...overrides,
  }
}

export const rows3: Candidate[] = [
  candidate(),
  candidate({
    rank: 2,
    accession: 'P68871',
    start: 65,
    end: 77,
    length: 13,
    sequence: 'GKKVLGAFSDGLA',
    activity: 0.34,
    hemolysis_band: 'medium',
    hemolysis_risk: 0.5,
    novelty_class: 'related',
    rank_score: 0.17,
  }),
  candidate({
    rank: 3,
    accession: 'P59665',
    start: 58,
    end: 94,
    length: 37,
    sequence: 'GSRKNMACYCRIPACIAGERRYGTCIYQGRLWAFCC',
    activity: 0.56,
    hemolysis_band: 'high',
    hemolysis_risk: 0.8,
    novelty_class: 'known',
    rank_score: 0.0099,
  }),
]

export const proteins: ProteinSummary[] = [
  { accession: 'P02788', name: 'Lactotransferrin', length: 710, n_candidates: 35, best_activity_score: 0.98 },
  { accession: 'P68871', name: 'Hemoglobin subunit beta', length: 147, n_candidates: 9, best_activity_score: 0.9 },
]

export const proteinDetail: ProteinDetail = {
  accession: 'P02788',
  name: 'Lactotransferrin',
  length: 710,
  sequence: 'A'.repeat(710),
  candidates: [
    {
      rank: 1, start: 360, end: 367, length: 8, sequence: 'RRARVVWC', activity: 0.44,
      hemolysis_risk: 0.09, hemolysis_band: 'low', novelty_class: 'novel', rank_score: 0.4,
    },
    {
      rank: 7, start: 362, end: 380, length: 19, sequence: 'ARVVWCAVGEQELRKCNQW', activity: 0.05,
      hemolysis_risk: 0.2, hemolysis_band: 'low', novelty_class: 'related', rank_score: 0.02,
    },
  ],
}

export function detail(overrides: Partial<CandidateDetail> = {}): CandidateDetail {
  return {
    candidate: candidate(),
    features: {
      length: 8, net_charge: 2.85, charge_density: 0.36, isoelectric_point: 12.18,
      hydrophobic_fraction: 0.63, mean_hydrophobicity: -0.46, gravy: -0.21,
      hydrophobic_moment_helix: 0.51, aliphatic_index: 85, boman_index: 3.91,
      frac_positive: 0.38, frac_negative: 0, frac_aromatic: 0.13,
    },
    composition: Object.fromEntries([...'ACDEFGHIKLMNPQRSTVWY'].map((a) => [a, a === 'R' ? 0.375 : 0])),
    alignment: {
      known_sequence: 'AGRQWIKAYLRREIRKVGRKARIAW', known_id: 'DBAASPS_17143', score: 30,
      identity: 0.57, similarity: 0.86, gaps: 0, query_start: 0, target_start: 18,
      aligned_query: 'RRARVVW', aligned_target: 'RKARIAW', midline: '|:||: |',
      text: 'Score = 30, Identities = 4/7 (57%)\ncandidate 1 RRARVVW 7',
    },
    protein: {
      accession: 'P02788', name: 'Lactotransferrin', length: 710, sequence: 'M'.repeat(710),
      context: 'LRKSEEEVAARRARVVWCAVGEQELRKC',
    },
    notes: ['Not clearly similar to any known AMP in the reference of 17,492.', 'Hemolysis risk band: low.'],
    ...overrides,
  }
}
