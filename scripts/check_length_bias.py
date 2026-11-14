"""Why is the top of the proteome ranking full of 8-12 residue windows?

Usage:  python -u scripts/check_length_bias.py

Uses the out-of-fold activity scores (data/interim/activity_oof.npy, from calibrate_scores.py),
so no model has seen the rows it is scored on, and the stability candidates
(data/interim/stability_candidates.csv, from ranking_stability.py).

Questions
  A. Is the model weaker on short windows? (ROC AUC and recall per length band)
  B. Do short negatives pass a global threshold more often? (false-positive rate per band)
  C. A proteome has the SAME number of windows at every length 8-50, but the training negatives
     copy the lengths of known AMPs. If every length contributed equally, what share of the false
     alarms would be short, according to the out-of-fold false-positive rate of each length?
     Compare with the share of short windows among the top-ranked candidates of a real scan.
Writes reports/length_bias.json.
"""

import json

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from amp_triage import config
from amp_triage.models.calibration import calibration_fit

BANDS = [(8, 12), (13, 20), (21, 35), (36, 50)]
FPRS = (1e-3, 1e-4)


def band_of(length: pd.Series) -> pd.Series:
    out = pd.Series("", index=length.index)
    for lo, hi in BANDS:
        out[length.between(lo, hi)] = f"{lo}-{hi}"
    return out


data = pd.read_csv(config.PROCESSED_DIR / "activity_dataset.csv", usecols=[
    "label", "split", "origin", "length"])
pool = data[data.split.isin(["train", "val"])].reset_index(drop=True)
pool["score"] = np.load(config.INTERIM_DIR / "activity_oof.npy")
pool["band"] = band_of(pool.length)
neg, pos = pool[pool.label == 0], pool[pool.label == 1]
out = {}

# ---- A. how well does the model separate AMPs from non-AMPs within each band? --------------
rows = []
for lo, hi in BANDS:
    name = f"{lo}-{hi}"
    sub = pool[pool.band == name]
    intercept, slope = calibration_fit(sub.label, sub.score)
    rows.append({
        "band": name,
        "positives": int((sub.label == 1).sum()),
        "negatives": int((sub.label == 0).sum()),
        "roc_auc": float(roc_auc_score(sub.label, sub.score)),
        "calib_slope": slope,
        "positive_rate": float(sub.label.mean()),
    })
A = pd.DataFrame(rows).set_index("band")
out["A_per_band"] = A.to_dict("index")
print("=== A. separation within each length band (out-of-fold) ===")
print(A.round(3).to_string())

# ---- B. false-positive rate per band at a global threshold ---------------------------------
out["B_global_threshold"] = {}
for fpr in FPRS:
    thr = float(np.quantile(neg.score, 1 - fpr))
    rows = []
    for lo, hi in BANDS:
        name = f"{lo}-{hi}"
        n, p = neg[neg.band == name], pos[pos.band == name]
        rows.append({
            "band": name,
            "share_of_negatives": len(n) / len(neg),
            "fpr": float((n.score > thr).mean()),
            "share_of_false_alarms": float((n.score > thr).sum() / (neg.score > thr).sum()),
            "recall": float((p.score > thr).mean()),
        })
    B = pd.DataFrame(rows).set_index("band")
    out["B_global_threshold"][f"{fpr:g}"] = {"threshold": thr, **B.to_dict("index")}
    print(f"\n=== B. one global threshold (overall false-positive rate {fpr:g}, "
          f"score > {thr:.3f}) ===")
    print(B.round(4).to_string())

# ---- C. what would a proteome (same number of windows at every length) look like? ----------
cand = pd.read_csv(config.INTERIM_DIR / "stability_candidates.csv")
seen = band_of(cand.length).value_counts(normalize=True)
out["C_expected_vs_seen"] = {}
rows = {}
for fpr in FPRS:
    thr = float(np.quantile(neg.score, 1 - fpr))
    per_length = neg.groupby("length").score.apply(lambda s, t=thr: float((s > t).mean()))
    per_length = per_length.reindex(range(8, 51)).fillna(0.0)
    bands = band_of(pd.Series(per_length.index, index=per_length.index))
    share = per_length.groupby(bands).sum() / per_length.sum()
    rows[f"expected false alarms, threshold at fpr {fpr:g}"] = share
rows["windows scanned (equal per length)"] = pd.Series(
    {f"{lo}-{hi}": (hi - lo + 1) / 43 for lo, hi in BANDS})
rows["top 300 candidates of a real scan"] = seen
rows["known AMPs (17,492)"] = band_of(pd.read_csv(
    config.PROCESSED_DIR / "known_amps.csv").length).value_counts(normalize=True)
C = pd.DataFrame(rows).T[[f"{lo}-{hi}" for lo, hi in BANDS]]
out["C_expected_vs_seen"] = C.to_dict("index")
print("\n=== C. share of each length band ===")
print(C.round(3).to_string())

# ---- D. do the evaluation negatives look like the windows a scan produces? -----------------
uniform = pd.Series({f"{lo}-{hi}": (hi - lo + 1) / 43 for lo, hi in BANDS})
mix = neg.band.value_counts(normalize=True).reindex(uniform.index)
D = pd.DataFrame({"training negatives": mix, "real scan (equal per length)": uniform})
out["D_length_mix"] = D.to_dict("index")
print("\n=== D. length mix: training negatives vs the windows a scan produces ===")
print(D.round(3).to_string())

(config.ROOT / "reports" / "length_bias.json").write_text(json.dumps(out, indent=1))
