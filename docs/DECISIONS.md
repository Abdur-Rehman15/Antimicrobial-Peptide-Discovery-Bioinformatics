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
* The remaining shortcut after a filter: AMPs are more highly charged than random windows that
  pass it (random ones pile up at +2 to +3), so charge keeps some value. The matched negatives
  must also be matched on charge distribution, or this is still a shortcut.
