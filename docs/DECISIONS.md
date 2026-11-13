# Design Decisions

Draft. Review and change as needed. These are written first so results can be defended.

## Definitions
- **AMP (positive):** a peptide of 8-50 standard amino acids listed in APD3, DRAMP or DBAASP
  with antimicrobial activity recorded.
- **Non-AMP (negative):** a fragment of a UniProt protein that is not annotated as antimicrobial,
  cut with the same window method and length distribution as our candidates.
- **Hemolytic:** labelled hemolytic in the hemolysis data source. Output is called "hemolytic
  risk", not general toxicity.
- **Novel:** best Smith-Waterman hit against known AMPs is below a similarity threshold.
  Threshold value is chosen in the novelty phase and justified there.

## Rules for trustworthy results
1. **No leakage into validation.** Human-derived AMPs are held out of training. The human-proteome
   check asks whether the model still ranks known human encrypted peptides highly.
2. **Fair negatives.** Negatives are cut the same way and lengths are matched to positives.
   Results are reported under more than one negative-sampling scheme if time allows.
3. **Similarity-aware split.** Similar sequences stay on the same side of train/test
   (cluster, then split by cluster).
4. **Report imbalance honestly.** AMPs are rare among sliding-window fragments, so report
   precision-recall as well as AUC-ROC.

## Tooling
- Python 3.12 in `.venv`. Python 3.14 is also installed but is not used because some scientific
  libraries may lag behind it.
- `ruff` for style, `pytest` for tests.
- Models are scikit-learn, so CPU is enough. No GPU or Colab is required.
- Smith-Waterman is written from scratch and tested against Biopython's `PairwiseAligner`.
