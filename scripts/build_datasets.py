"""Build the two training datasets with all 35 descriptors.

Usage:  python scripts/build_datasets.py

Needs: data/processed/positives.csv and positives_split.csv (scripts/build_positives.py,
cluster_positives.py, build_splits.py), the UniProt files, and the HAPPENN supplement.
Writes data/processed/activity_dataset.csv and data/processed/hemolysis_dataset.csv.
"""

import time

import numpy as np
import pandas as pd
from Bio import SeqIO

from amp_triage import config
from amp_triage.data.datasets import (
    activity_metadata,
    build_hemolysis_metadata,
    validate_activity,
    validate_hemolysis,
    with_descriptors,
)
from amp_triage.data.happenn import load_happenn, pdf_to_text
from amp_triage.data.negatives import kmer_set, load_mixed_pool, sample_windows

SEED = 1
NEG_PER_POSITIVE = {"train": 20, "val": 100, "test": 100}
MAX_PROTEINS = 60000
MAMMAL_SHARE = 0.7  # share of negative proteins that are mammalian (all 41,928 are used)

all_pos = pd.read_csv(config.PROCESSED_DIR / "positives.csv")
pos_split = pd.read_csv(config.PROCESSED_DIR / "positives_split.csv")

# ---- activity: negatives --------------------------------------------------------------
t = time.time()
human_acc = {
    r.id.split("|")[1]
    for r in SeqIO.parse(str(config.RAW_DIR / "uniprot" / "human_reviewed.fasta"), "fasta")
}
accs, seqs, n_mammal = load_mixed_pool(
    config.RAW_DIR / "uniprot" / "swissprot_not_amp.fasta", human_acc, MAX_PROTEINS,
    MAMMAL_SHARE, seed=0,
)
print(f"negative proteins: {len(accs):,} ({n_mammal:,} mammalian)")
banned = kmer_set(all_pos.sequence)
# every length 8-50 equally often, like the windows of a scan (copying the positives' lengths
# left only 13% of negatives long, against 35% of the windows in a scan)
scan_lengths = np.arange(config.MIN_PEPTIDE_LEN, config.MAX_PEPTIDE_LEN + 1)
frames = []
for split, ratio in NEG_PER_POSITIVE.items():
    n = ratio * int((pos_split.split == split).sum())
    frames.append(sample_windows(accs, seqs, scan_lengths, n, split, banned, seed=SEED))
negatives = pd.concat(frames, ignore_index=True)
before = len(negatives)
# the same short window can occur in proteins of two splits: keep the first, so no sequence is
# shared between splits
negatives = negatives.drop_duplicates("sequence", keep="first").reset_index(drop=True)
removed = before - len(negatives)
print(f"negatives: {len(negatives):,} windows ({removed} cross-split duplicates removed) "
      f"in {time.time() - t:.0f}s")
print(negatives.split.value_counts().to_dict())

# ---- activity: descriptors and checks --------------------------------------------------
t = time.time()
activity = with_descriptors(activity_metadata(pos_split, negatives))
print(f"activity descriptors for {len(activity):,} rows in {time.time() - t:.0f}s")
validate_activity(activity, set(all_pos.sequence))
activity.to_csv(config.PROCESSED_DIR / "activity_dataset.csv", index=False)

# ---- hemolysis -------------------------------------------------------------------------
txt = config.INTERIM_DIR / "happenn" / "supp_raw.txt"
if not txt.exists():
    txt.parent.mkdir(parents=True, exist_ok=True)
    pdf_to_text(config.RAW_DIR / "happenn" / "41598_2020_67701_MOESM1_ESM.pdf", txt)
hemo_meta, n_dropped = build_hemolysis_metadata(load_happenn(txt))
hemolysis = with_descriptors(hemo_meta)
validate_hemolysis(hemolysis)
hemolysis.to_csv(config.PROCESSED_DIR / "hemolysis_dataset.csv", index=False)

# ---- summary ---------------------------------------------------------------------------
print("\n=== ACTIVITY dataset (data/processed/activity_dataset.csv) ===")
tab = activity.groupby(["split", "label"]).size().unstack(fill_value=0)
tab.columns = ["negatives (0)", "positives (1)"]
tab["natural_pos"] = activity[activity.label == 1].groupby("split").origin.apply(
    lambda o: int((o == "natural").sum())
)
tab["neg:pos"] = (tab["negatives (0)"] / tab["positives (1)"].replace(0, np.nan)).round(1)
print(tab.loc[["train", "val", "test", "human"]].fillna("-").to_string())
print("\n=== HEMOLYSIS dataset (data/processed/hemolysis_dataset.csv) ===")
htab = hemolysis.groupby(["split", "label"]).size().unstack(fill_value=0)
htab.columns = ["non-hemolytic (0)", "hemolytic (1)"]
htab["hemolytic share"] = (htab["hemolytic (1)"] / htab.sum(axis=1)).round(2)
print(htab.loc[["train", "val", "test"]].to_string())
print(f"dropped as too similar: {n_dropped} of 1,923")
overlap = set(hemolysis.sequence) & set(all_pos.sequence)
print(f"\nhemolysis peptides that are also activity positives: {len(overlap)}")
print("\nall dataset checks passed")
