"""Build and evaluate the stage-1 screen.  Usage:  python scripts/build_stage1.py [recall]

1. sample stage-1 negatives (random windows from non-human, non-antimicrobial proteins)
2. train the linear screen on the training split
3. choose the threshold by recall on the validation split (default recall 0.97)
4. report recall / AUC on the untouched test split and the human hold-out
5. run the screen over every window of the human proteome and compare with hard gates that
   keep the same share of validation AMPs

Writes data/processed/stage1_negatives.csv, models/saved/stage1.json, reports/stage1_metrics.json
"""

import json
import sys
import time

import numpy as np
import pandas as pd
from Bio import SeqIO
from sklearn.metrics import roc_auc_score

from amp_triage import config
from amp_triage.candidates.stage1 import (
    peptide_features,
    threshold_for_recall,
    train_stage1,
)
from amp_triage.candidates.windows import LENGTHS, load_proteome
from amp_triage.data.negatives import kmer_set, load_pool, sample_windows

TARGET_RECALL = float(sys.argv[1]) if len(sys.argv) > 1 else 0.97
RATIO = 10  # negatives per positive in each split
MAX_PROTEINS = 60000
SEED = 0

pos = pd.read_csv(config.PROCESSED_DIR / "positives_split.csv")
all_pos = pd.read_csv(config.PROCESSED_DIR / "positives.csv")
human_acc = {r.id.split("|")[1] for r in SeqIO.parse(
    str(config.RAW_DIR / "uniprot" / "human_reviewed.fasta"), "fasta")}

# 1. negatives ---------------------------------------------------------------------------
t = time.time()
accs, seqs = load_pool(config.RAW_DIR / "uniprot" / "swissprot_not_amp.fasta",
                       human_acc, MAX_PROTEINS, SEED)
print(f"negative pool: {len(accs):,} non-human, non-antimicrobial proteins ({time.time()-t:.0f}s)")
banned = kmer_set(all_pos.sequence)
frames = []
for split in ("train", "val", "test"):
    n = RATIO * int((pos.split == split).sum())
    frames.append(sample_windows(accs, seqs, all_pos.length.values, n, split, banned, seed=SEED))
neg = pd.concat(frames, ignore_index=True)
neg.to_csv(config.PROCESSED_DIR / "stage1_negatives.csv", index=False)
print("negatives per split:", neg.split.value_counts().to_dict())

# 2. train -------------------------------------------------------------------------------
P = {s: pos[pos.split == s] for s in ("train", "val", "test", "human")}
N = {s: neg[neg.split == s] for s in ("train", "val", "test")}
model = train_stage1(P["train"].sequence, N["train"].sequence)
sc = {f"{s}_pos": model.scores(P[s].sequence.tolist()) for s in P}
sc.update({f"{s}_neg": model.scores(N[s].sequence.tolist()) for s in N})
nat = {s: (P[s].origin == "natural").values for s in P}



def auc_for(split, mask):
    """AUC of the chosen positives of `split` against that split's random windows."""
    n_neg = len(N[split])
    return roc_auc_score(
        np.r_[np.ones(mask.sum()), np.zeros(n_neg)],
        np.r_[sc[f"{split}_pos"][mask], sc[f"{split}_neg"]],
    )


print("\nAUC (positives vs random windows)        all   natural  synthetic")
for s in ("val", "test"):
    everyone = np.ones(len(P[s]), bool)
    a, b, c = auc_for(s, everyone), auc_for(s, nat[s]), auc_for(s, ~nat[s])
    print(f"  {s:5}                                   {a:.3f}   {b:.3f}    {c:.3f}")

# 3. threshold by recall on validation ---------------------------------------------------
val_charge = peptide_features(P["val"].sequence.tolist())[:, 21]
print("\nthreshold chosen on validation by recall (min over all / natural so both reach it):")
rows = []
for r in (0.90, 0.95, 0.97, 0.99):
    thr = min(
        threshold_for_recall(sc["val_pos"], r),
        threshold_for_recall(sc["val_pos"][nat["val"]], r),
    )
    cthr = min(
        threshold_for_recall(val_charge, r),
        threshold_for_recall(val_charge[nat["val"]], r),
    )
    rows.append({
        "target_recall": r, "threshold": thr, "charge_gate": cthr,
        "test_recall_all": float((sc["test_pos"] >= thr).mean()),
        "test_recall_natural": float((sc["test_pos"][nat["test"]] >= thr).mean()),
        "human_recall": float((sc["human_pos"] >= thr).mean()),
        "test_neg_pass": float((sc["test_neg"] >= thr).mean()),
        "charge_gate_test_recall_natural": float(
            (peptide_features(P["test"].sequence.tolist())[nat["test"], 21] >= cthr).mean()),
        "charge_gate_test_neg_pass": float(
            (peptide_features(N["test"].sequence.tolist())[:, 21] >= cthr).mean()),
    })
res = pd.DataFrame(rows)
print(res.round(3).to_string(index=False))

# 4. final model at the target recall ----------------------------------------------------
chosen = res[res.target_recall == TARGET_RECALL].iloc[0]
model.threshold = float(chosen.threshold)
config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
model.save(config.MODELS_DIR / "stage1.json")

# 5. human proteome pass-through ---------------------------------------------------------
print(f"\nrunning the screen over the human proteome at recall target {TARGET_RECALL} ...")
t = time.time()
prot = load_proteome(config.RAW_DIR / "uniprot" / "human_reviewed.fasta")
total = 0
passed = {float(r.target_recall): 0 for r in res.itertuples()}
passed_charge = dict.fromkeys(passed, 0)
thr_by_r = {float(r.target_recall): (r.threshold, r.charge_gate) for r in res.itertuples()}
for length in LENGTHS:
    _, charge, score = model.window_scores(prot, length)
    total += len(score)
    for r, (thr, cthr) in thr_by_r.items():
        passed[r] += int((score >= thr).sum())
        passed_charge[r] += int((charge >= cthr).sum())
print(f"scored {total:,} windows in {time.time()-t:.0f}s")
print(
    f"\n{'recall':>6} | {'stage 1 passes':>16} {'(share)':>8} | "
    f"{'charge-only gate':>17} {'(share)':>8}"
)
for r in passed:
    print(
        f"{r:>6} | {passed[r]:>16,} {passed[r] / total:>8.1%} | "
        f"{passed_charge[r]:>17,} {passed_charge[r] / total:>8.1%}"
    )

json.dump(
    {"target_recall": TARGET_RECALL, "windows_total": total,
     "table": rows, "human_pass": {str(k): v for k, v in passed.items()},
     "charge_gate_pass": {str(k): v for k, v in passed_charge.items()}},
    open(config.ROOT / "reports" / "stage1_metrics.json", "w"), indent=2)
print("\nsaved models/saved/stage1.json and reports/stage1_metrics.json")
