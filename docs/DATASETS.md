# Training datasets

Built by `python scripts/build_datasets.py` (about 10 minutes). Both files are in
`data/processed/` (not committed, rebuilt from the raw data) and have the same columns:

`sequence, label, split, origin, group` followed by the 35 descriptors of
`features/descriptors.py` (`FEATURE_NAMES`). The hemolysis file also has `n_ter_flag` and
`c_ter_flag` (HAPPENN end-modification flags, metadata only: windows from a proteome have none).

`group` is for grouped cross-validation: a cluster id (`c123`) for peptides and a protein
accession for random windows, so related rows never straddle a fold.

## Activity dataset: `activity_dataset.csv` (362,907 rows)

| split | positives | of which natural | negatives | negatives per positive |
|---|---|---|---|---|
| train | 7,299 | 2,237 | 145,980 | 20 |
| val | 1,066 | 643 | 106,592 | 100 |
| test | 1,003 | 637 | 100,279 | 100 |
| human | 688 | 239 | none (see below) | |

* **Positives:** the 12,075 cleaned active peptides (MIC <= 32 uM), split by similarity
  (threshold 0.7) with no similar pair across splits; 2,019 dropped by the purge.
* **Negatives:** random windows from 60,000 non-human, non-antimicrobial proteins, 41,928 of them
  mammalian (all that exist in the pool) and the rest from other organisms. Each protein feeds
  one split only. **Window lengths are spread evenly over 8-50**, like the windows of a scan of a
  proteome. (The first version copied the positives' lengths: 13% of negatives were 36-50
  residues long, against 35% of the windows in a scan, and human proteins then passed the score
  threshold 3.6-6.9 times more often than the training negatives. The even lengths cut that
  to 0.9-1.1 times. See DECISIONS.md.) No window shares a 7-residue
  stretch with any known AMP.
* **The human split is positives only.** Its negatives are the other windows of the human
  proteome, scanned in the final validation, so no human protein is used anywhere in training.
* **Why 100 negatives per positive in val/test:** real proteomes contain far more ordinary
  windows than AMPs. At 1 in 100 the evaluation can measure false-positive rates down to about
  1e-5; precision at real-world rates (rarer than 1 in 1,000) is computed by re-weighting.
* Checks that ran: no duplicate sequence anywhere, no sequence in two splits, labels 0/1, no
  missing or infinite feature, no negative sharing a 7-mer with a known AMP, no protein feeding
  two splits, the human split holds positives only, both classes in train, val and test.

## Hemolysis dataset: `hemolysis_dataset.csv` (1,787 rows)

HAPPENN-RR90 (823 hemolytic, 1,100 non-hemolytic), split by the same similarity method and
purged; 136 peptides dropped.

| split | non-hemolytic | hemolytic | hemolytic share |
|---|---|---|---|
| train | 809 | 537 | 0.40 |
| val | 120 | 113 | 0.48 |
| test | 116 | 92 | 0.44 |

## Things to keep in mind

* **The hemolysis set is small** (233 and 208 peptides in val and test), so a single test AUC
  has a wide error bar. Report cross-validation over train+val with the grouping column, and
  a confidence interval.
* **75% of the hemolysis peptides (1,341 of 1,787) are also activity positives.** HAPPENN is a
  set of AMPs, so the hemolysis model learns which AMPs are hemolytic, not which arbitrary
  windows are toxic. It is only meaningful applied to windows already judged antimicrobial,
  which is how the pipeline uses it.
* **Natural versus synthetic:** train positives are 31% natural, val and test about 60%.
  Report natural and synthetic results separately.
* **Class labels in the negatives are not certain:** a random window may hide an antimicrobial
  peptide nobody has annotated.
