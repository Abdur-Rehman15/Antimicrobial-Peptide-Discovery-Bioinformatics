# Project Plan

Deadline: about one week from 2026-11-14. Solo project. The pipeline and ML models are the core;
the dashboard is needed for the demo but can be simple.

## Phases and one-week schedule

| Day | Phase | Work | Done when |
|---|---|---|---|
| 1 | 0. Setup | Folders, Python 3.12 env, tools, design notes | Skeleton runs, tests pass |
| 1-2 | 1. Data | Download APD3, DRAMP, DBAASP, hemolysis data. Clean. Build negatives. UniProt downloader with cache | One clean, reproducible dataset |
| 2 | 2. Smith-Waterman | From scratch, BLOSUM62, affine gaps, traceback. Tested against Biopython | Matches Biopython on random pairs |
| 3 | 2/3. Descriptors and candidates | Peptide properties. Sliding window and gates. Speed test on human proteome | Human proteome processed in reasonable time |
| 4 | 4. Models | Baseline, Random Forest, SVM. Activity and hemolysis models. Similarity-aware split. Metrics | Saved models with accuracy, precision, recall, F1, AUC-ROC |
| 5 | 5/6. Novelty, ranking, API | Align top candidates to known AMPs. Ranking score. FastAPI endpoints and CSV export | Full run works without the UI |
| 6 | 7/8. Dashboard and validation | React dashboard. Human-proteome check with human AMPs held out | Demo works. Results table ready |
| 7 | 9. Finish | README, report, slides, demo rehearsal on a cached proteome. Buffer | Everything ready to present |

## Cut list (cut from the top if behind)
1. Extras (helical wheels, text explanations, batch compare)
2. BiLSTM (not planned; sklearn models run fine on CPU, so no GPU or Colab needed)
3. FASTA upload, extra filters in the dashboard
4. Never cut: activity model, hemolysis model, Smith-Waterman, ranked dashboard, validation

## Not doing for now
GitHub Actions, Docker.
