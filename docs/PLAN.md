# Project Plan

Solo project. The pipeline and ML models are the core; the dashboard is needed for the demo but
can be simple. The deadline pressure was lifted, so quality and understanding come first.
Status below is current as of the last commit; details of every decision are in DECISIONS.md and
DATA_SOURCES.md.

## Phases

| Phase | What | Status |
|---|---|---|
| 0. Setup | Repo, Python 3.12 env, ruff, pytest, notes | Done |
| 1. Data | APD3, DRAMP, DBAASP (list and 17,886 details), HAPPENN, UniProt downloaded with a manifest. Active-peptide table (12,075, MIC <= 32 uM), human hold-out (297 labelled or found in a human protein), conflicts removed | Done |
| 2. Core algorithms | Smith-Waterman from scratch (affine gaps, BLOSUM62, numba score-only version), tested against Biopython. 35 descriptors, tested against peptides.py, modlAMP, Biopython | Done |
| 3. Similarity, splits, negatives | All-vs-all similarity with our own aligner. CD-HIT-style clusters, split by cluster, cross-split purge at 0.7 (verified no leakage). Human hold-out (688). Random-window negatives (93,680) | Done |
| 3b. Candidate engine | All 35 descriptors for every window of every length in bulk, from running totals (`candidates/window_features.py`). Stage-1 screen tested and **dropped** as a filter (negative result) | Engine built and tested. Benchmark: 0.21 M windows/s on one core, about 38 min for all 466 M human windows (features only, extrapolated from one chunk); chunks are independent so 8 cores should bring it to under 10 min (not yet tested) |
| 4. Models | Activity classifier and hemolysis classifier (Random Forest, SVM, baselines), similarity-aware evaluation, natural vs synthetic reported separately, calibration | Next |
| 5. Novelty and ranking | Align each top candidate against all known AMPs (our Smith-Waterman), define "novel", ranking score | Planned |
| 6. Backend | FastAPI: organism search, run, progress, results, CSV export | Planned |
| 7. Dashboard | React: ranked table, filters, candidate detail with the alignment | Planned |
| 8. Validation | Human proteome with the human hold-out; do known encrypted peptides rank high? Ablations. Report failures too | Planned |
| 9. Finish | README, report, slides, demo on a cached proteome | Planned |
| 10. Extras | Helical wheels, text explanations, batch comparison | Only if the rest is done |

## Things to remember for the report
* The proposal's hard charge/hydrophobicity gates lose real AMPs (40% of natural AMPs at charge
  >= +2) and prune too little at high recall; a cheap two-stage screen also prunes too little.
  Both are documented negative results.
* Positives are 35% natural and 65% synthetic (DBAASP is 84% synthetic). Always report natural
  and synthetic separately; validation and test are about 60% natural.
* "Not an AMP" windows are not guaranteed to contain no hidden AMP (that is the project's premise).
* Hemolysis labels come from the HAPPENN benchmark (published rule), RR90 subset.

## Not doing for now
GitHub Actions, Docker, BiLSTM (CPU-only is enough).
