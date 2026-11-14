"""Grouped cross-validation of the best tuned boosting settings (plus the old reference).

Usage:  python -u scripts/cv_activity_boosting.py

Needs reports/activity_tuning.jsonl (scripts/tune_activity_boosting.py).
Pools train + val, then runs 5-fold cross-validation in which every cluster (positives) and every
protein (negatives) stays inside one fold. Stratified by class and by natural/synthetic.
Clusters alone leave near-copies (>= 0.7 similar, different cluster) on both sides of a fold, so
each fold also drops the training positives similar to any held-out positive and asserts that no
such pair is left.

Train and val have different negatives-per-positive ratios (20 and 100), so held-out train
negatives get weight 5: every fold is then judged at 100 negatives per positive, like val and
test. The human and test splits are not used.
Writes reports/activity_cv.json and reports/activity_final_config.json (best mean natural PR AUC).
"""

import json
import time

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import StratifiedGroupKFold

from amp_triage import config
from amp_triage.features.descriptors import FEATURE_NAMES
from amp_triage.models.evaluation import summarize_by_origin

SEED = 0
FOLDS = 5
TOP_K = 3
REFERENCE = {"learning_rate": 0.1, "max_leaf_nodes": 31, "min_samples_leaf": 20,
             "l2_regularization": 0.0, "max_features": 1.0}

tuning = [json.loads(line) for line in (config.ROOT / "reports" / "activity_tuning.jsonl").open()]
tuning.sort(key=lambda r: -r["natural_pr"])
candidates = [r for r in tuning if r["config"] != REFERENCE][:TOP_K]
candidates.append(next(r for r in tuning if r["config"] == REFERENCE))

data = pd.read_csv(config.PROCESSED_DIR / "activity_dataset.csv")
pool = data[data.split.isin(["train", "val"])].reset_index(drop=True)
X, y = pool[FEATURE_NAMES].to_numpy(), pool.label.to_numpy()
origin = pool.origin.to_numpy()
neg_weight = np.where(pool.split == "train", 5.0, 1.0)  # train 20:1 -> 100:1
strata = np.where(y == 0, 0, np.where(origin == "natural", 2, 1))
folds = list(
    StratifiedGroupKFold(FOLDS, shuffle=True, random_state=SEED).split(X, strata, pool.group)
)

# Clusters alone do not protect a fold: two peptides >= 0.7 similar can sit in different
# clusters (the split only purged pairs ACROSS train/val/test). So for each fold, every training
# positive that is >= TAU similar to a held-out positive is dropped, as the real splits do.
TAU = 0.7
ps = pd.read_csv(config.PROCESSED_DIR / "positives_split.csv")
z = np.load(config.INTERIM_DIR / "positive_pairs.npz")
pool_row_of_pos = pd.Series(-1, index=range(len(ps)))
seq_to_pool = {s: r for r, s in enumerate(pool.sequence) if y[r] == 1}
pool_row_of_pos[:] = [seq_to_pool.get(s, -1) for s in ps.sequence]
pa, pb = pool_row_of_pos.to_numpy()[z["i"]], pool_row_of_pos.to_numpy()[z["j"]]
keep_pair = (z["sim"] >= TAU) & (pa >= 0) & (pb >= 0)
pa, pb = pa[keep_pair], pb[keep_pair]


def purge_for_fold(train_idx: np.ndarray, test_idx: np.ndarray) -> np.ndarray:
    """Training rows minus positives that are >= TAU similar to a held-out positive."""
    in_test = np.zeros(len(pool), bool)
    in_test[test_idx] = True
    drop = np.zeros(len(pool), bool)
    drop[pb[in_test[pa] & ~in_test[pb]]] = True
    drop[pa[in_test[pb] & ~in_test[pa]]] = True
    kept = train_idx[~drop[train_idx]]
    in_kept = np.zeros(len(pool), bool)
    in_kept[kept] = True
    leak = (in_test[pa] & in_kept[pb]) | (in_test[pb] & in_kept[pa])
    assert not leak.any(), f"{leak.sum()} similar pairs still cross train and held-out"
    return kept


print(f"pool {len(pool):,} rows, {y.sum():,} positives, {FOLDS} folds, "
      f"{len(candidates)} settings", flush=True)

METRICS = {
    "natural PR AUC": lambda r: r["natural"]["pr_auc"],
    "all PR AUC": lambda r: r["all"]["pr_auc"],
    "natural ROC AUC": lambda r: r["natural"]["roc_auc"],
    "natural recall@FPR1e-3": lambda r: r["natural"]["recall@fpr=0.001"],
    "natural recall@FPR1e-4": lambda r: r["natural"]["recall@fpr=0.0001"],
    "all recall@FPR1e-3": lambda r: r["all"]["recall@fpr=0.001"],
    "synthetic PR AUC": lambda r: r["synthetic"]["pr_auc"],
}

report = {}
for c, cand in enumerate(candidates, start=1):
    cfg, trees = cand["config"], cand["trees"]
    per_fold = []
    for f, (tr_all, te) in enumerate(folds, start=1):
        t = time.time()
        tr = purge_for_fold(tr_all, te)
        if c == 1:
            lost = int(y[tr_all].sum() - y[tr].sum())
            print(f"fold {f}: purged {lost} of {int(y[tr_all].sum())} training positives that "
                  f"were >= {TAU} similar to a held-out positive", flush=True)
        model = HistGradientBoostingClassifier(
            max_iter=trees, early_stopping=False, random_state=SEED, **cfg
        ).fit(X[tr], y[tr])
        res = summarize_by_origin(
            y[te], model.predict_proba(X[te])[:, 1], origin[te], neg_weight[te]
        )
        per_fold.append({name: fn(res) for name, fn in METRICS.items()})
        print(f"setting {c}/{len(candidates)} fold {f}/{FOLDS}: natural PR "
              f"{per_fold[-1]['natural PR AUC']:.3f} ({time.time() - t:.0f}s)", flush=True)
    frame = pd.DataFrame(per_fold)
    report[json.dumps(cfg)] = {
        "trees": trees,
        "tuning_natural_pr_on_val": cand["natural_pr"],
        "mean": frame.mean().to_dict(),
        "std": frame.std().to_dict(),
        "folds": per_fold,
    }

best_key = max(report, key=lambda k: report[k]["mean"]["natural PR AUC"])
(config.ROOT / "reports" / "activity_cv.json").write_text(json.dumps(report, indent=1))
(config.ROOT / "reports" / "activity_final_config.json").write_text(
    json.dumps({"config": json.loads(best_key), "trees": report[best_key]["trees"]}, indent=1)
)

print("\n=== grouped 5-fold CV on train+val (mean +- std over folds) ===")
for key, r in report.items():
    tag = "REFERENCE" if json.loads(key) == REFERENCE else ""
    print(f"\n{key}  trees={r['trees']}  {tag}")
    for name in METRICS:
        print(f"   {name:26s} {r['mean'][name]:.3f} +- {r['std'][name]:.3f}")
print("\nchosen:", best_key, "trees", report[best_key]["trees"])
