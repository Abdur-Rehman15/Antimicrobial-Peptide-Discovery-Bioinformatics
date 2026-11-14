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

## Descriptors (`src/amp_triage/features/descriptors.py`)

35 features per peptide: 15 summary descriptors plus 20 amino-acid fractions. All are written from
the published formulas (no hidden state) and checked against peptides.py, modlAMP, Biopython and
hand calculations (22 tests).

* **Charge** by Henderson-Hasselbalch, Lehninger pKa set, pH 7.4 (blood). Matches peptides.py to
  1e-9 and modlAMP to 0.01. LL-37 comes out at +5.99 (literature: +6).
* **Isoelectric point** by bisection on the same charge function. It differs from modlAMP's pI
  (10.58 vs 10.69 for magainin 2) because the pKa tables differ; ours is self-consistent with
  the charge.
* **Amphipathicity** is measured by the Eisenberg hydrophobic moment, per residue, at 100 degrees
  (helix) and 160 degrees (strand). The proposal lists "amphipathicity" and "hydrophobic moment"
  separately; they are the same quantity measured, so there is no extra descriptor for it.
* **Boman index:** the published table has no proline value; it is treated as 0, as in peptides.py.
* Only the 20 standard amino acids are accepted (anything else raises ValueError), because the
  data was cleaned to standard residues.

### What the descriptors show on real data (figure: `reports/figures/descriptor_charge_filter.png`)

12,075 positives vs 20,000 random Swiss-Prot fragments with matching lengths:

| | Real AMPs (median) | Random fragments (median) |
|---|---|---|
| Net charge | +3.99 | -0.01 |
| Water-repelling fraction | 0.46 | 0.40 |
| Hydrophobic moment (helix) | 0.35 | 0.20 |

Single-feature AUC against random fragments: net charge **0.886**, isoelectric point 0.845,
hydrophobic moment 0.710, hydrophobic fraction 0.651. So a model trained on random fragments
could reach a high score on charge alone.

Effect of a charge filter on the positives:

| Filter | Real AMPs kept | Random fragments kept |
|---|---|---|
| charge >= +1 | 87.2% | 25.9% |
| charge >= +2 | 77.8% | 14.7% |
| charge >= +3 | 64.7% | 8.1% |

* After a charge >= +2 filter, charge alone drops to AUC 0.72 while hydrophobic fraction (0.73)
  and hydrophobic moment (0.70) are as informative: the model has to use several features.
* **A hard charge filter throws away real AMPs** (22% at +2). The 5th percentile of AMP charge is
  about 0, so keeping 95% of AMPs needs a filter near charge >= 0, which removes only about half
  of random windows. The proposal's "gates remove the large majority of non-viable candidates"
  therefore costs recall, and the gate thresholds must be chosen on the recall/size trade-off.
  Natural-only positives should be checked separately.
* **Correction (earlier draft said negatives must be matched on charge): that was wrong.** After a
  filter, AMPs are still more charged than the windows that pass it, and that is a *real*
  difference, not a shortcut. What matters is that training negatives come from the same pool the
  model will see at deployment. Forcing charge to match would hide a true signal and distort the
  model's probabilities.

## Candidate gates: what the human proteome says (`candidates/windows.py`)

The human reviewed proteome (20,414 proteins, 11.4 M residues) has **466,225,680 windows** of
8-50 residues. Window charge and hydrophobic fraction are computed for all of them in 47 s with
running totals (exactly equal to the full descriptors, tested).

Share of real AMPs kept by a charge cut-off alone:

| charge >= | all AMPs | natural | synthetic |
|---|---|---|---|
| -2 | 98.2% | 96.5% | 99.1% |
| -1 | 96.7% | 93.4% | 98.6% |
| 0 | 93.9% | 87.6% | 97.4% |
| +1 | 87.2% | 75.0% | 93.8% |
| +2 | 77.8% | 59.5% | 87.7% |

Share of all human windows kept by (charge, hydrophobic fraction) gates, with AMP recall:

| charge >= | hydrophobic >= | all AMPs | natural | windows kept |
|---|---|---|---|---|
| -1 | 0 | 96.7% | 93.4% | 61.0% |
| 0 | 0 | 93.9% | 87.6% | 44.0% |
| 0 | 0.25 | 88.5% | 83.8% | 36.8% |
| +1 | 0 | 87.2% | 75.0% | 28.9% |
| +2 | 0 | 77.8% | 59.5% | 17.7% |
| +2 | 0.3 | 70.0% | 54.3% | 11.4% |

**Finding:** the proposal's hard gates (positive charge plus a minimum hydrophobic fraction) do
not "remove the large majority of non-viable candidates" without losing real AMPs. Natural AMPs
are the ones that suffer: 12.4% of them have a negative charge (for example anionic peptides such
as `ADDKNPLEECFREDDYEGFLEIAKNGLSTTSNPKRVVIVGAGMSGLAAY`), and a +2 gate drops 40% of them. A gate
that keeps 95% of natural AMPs (charge >= -2) still passes most windows.

## Train / validation / test split (`scripts/cluster_positives.py`, `scripts/build_splits.py`)

Similarity of two peptides = Smith-Waterman score / the shorter peptide's self-score (our own
aligner). All 73 M pairs of the 12,075 positives take 80 s.

* **Single-linkage clustering fails on this data**: at similarity 0.5, 11,686 of 12,075 peptides
  fall into one cluster (even at 0.8 the largest has 3,793), because of long families of
  lab-made variants and short peptides that match inside many long ones.
* **Used instead: CD-HIT-style greedy clusters, then a purge.** Whole clusters go to one split;
  clusters holding a human-derived peptide go to the human hold-out; afterwards any peptide still
  similar (>= threshold) to a peptide in a higher-priority split is dropped. The script asserts
  that no kept pair at or above the threshold crosses two splits.
* **Threshold 0.7** (about CD-HIT's 70%). Lower is too destructive:

| threshold | purged | train kept | natural in train |
|---|---|---|---|
| 0.5 | 8,308 | 1,550 | 960 |
| 0.6 | 4,473 | 5,293 | 2,181 |
| **0.7** | **2,019** | **7,299** | **2,237** |
| 0.8 | 1,200 | 7,822 | 2,368 |

Result at 0.7: train 7,299 (2,237 natural), val 1,066 (643), test 1,003 (637), human hold-out
688 (239), dropped 2,019. Val and test are about 60% natural while train is 31%, because the purge
removed many synthetic variants from them. **Always report natural and synthetic results
separately.** The human hold-out (688) is larger than the 297 labelled/identical peptides because
it also contains their close relatives, which is what a fair validation needs.

## Negatives (`data/negatives.py`, `scripts/build_stage1.py`)

Random windows from 60,000 non-human, non-antimicrobial Swiss-Prot proteins, 10 per positive in
each split (train 72,990 / val 10,660 / test 10,030). Proteins are assigned to splits by a hash of
the accession, lengths follow the positives' lengths, and windows sharing a 7-residue stretch with
any known AMP are removed. Human proteins are excluded entirely.

## Result: a cheap "stage 1" screen does not prune enough (negative result)

Idea (Option A): score all windows with a fast model on running-total features (20 amino-acid
fractions, length, charge), keep a threshold chosen to retain 97% of AMPs, and only run the full
model on the survivors. Built and tested (`candidates/stage1.py`; window scores equal per-peptide
scores exactly). It ranks well (test AUC 0.905 overall, 0.886 natural) and its recall transfers to
unseen data (97.9% of test AMPs, 97.3% of natural, 99.0% of human hold-out at the 97% target), but
**it removes little**:

| recall target | linear screen passes | charge-only gate passes | non-linear (boosted trees) |
|---|---|---|---|
| 90% | 52% | 64% | 32% (of test windows) |
| 95% | 76% | 78% | 61% |
| 97% | 84% | 83% | 77% |
| 99% | 96% | 92% | 93% |

(percent of the 466 M human windows; last column on held-out test windows.) Even a non-linear
model on the same cheap features only gets to 77% passing at 97% recall: AMPs and ordinary
windows overlap too much in these features. **So a screen cannot do the heavy lifting.** Savings
must come from elsewhere (vectorised full descriptors on all windows, fewer window lengths, or a
coarse-to-fine scan). The random-window negatives remain the right training negatives, because
with a screen that passes about 80% the main model sees nearly all windows anyway.

### Decision: no screening stage; score every window with fast vectorised descriptors

The stage-1 screen is **not** part of the pipeline. `candidates/stage1.py` and
`scripts/build_stage1.py` stay in the repository as the documented negative result (a useful
baseline and an honest finding for the report), but nothing downstream uses them as a filter.
Candidate generation instead computes the full descriptor set for every window of every length
and lets the main model decide. This needs the descriptors to be computed in bulk from running
totals, which is built in `candidates/windows.py` (`window_descriptors`) and tested against the
per-peptide code in `features/descriptors.py`.
