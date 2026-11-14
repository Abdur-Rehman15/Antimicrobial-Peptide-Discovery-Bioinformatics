"""Gradient boosting for the activity classifier, compared with the Random Forest.

Usage:  python -u scripts/train_activity_boosting.py

Trains on split == "train" and scores on split == "val" (test stays untouched).
Early stopping is not used: scikit-learn would hold out random training rows, and rows from the
same cluster are alike, so that hold-out would look too easy. Instead the model is fit with many
trees, the validation PR AUC is read off every 50 trees, and the best tree count is used.
Choosing the tree count on val is mild tuning, so the final number comes from the test set later.
Writes reports/activity_boosting.json and models/saved/activity_hgb.joblib.
"""

import json
import time

import joblib
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score

from amp_triage import config
from amp_triage.features.descriptors import FEATURE_NAMES
from amp_triage.models.evaluation import summarize_by_origin

SEED = 0
MAX_TREES = 600
CHECK_EVERY = 50

data = pd.read_csv(config.PROCESSED_DIR / "activity_dataset.csv")
train = data[data.split == "train"]
val = data[data.split == "val"]
X_tr, y_tr = train[FEATURE_NAMES].to_numpy(), train.label.to_numpy()
X_va, y_va = val[FEATURE_NAMES].to_numpy(), val.label.to_numpy()
print(f"train {len(train):,} rows, val {len(val):,} rows", flush=True)

variants = {
    "hgb_plain": dict(class_weight=None),
    "hgb_balanced": dict(class_weight="balanced"),
}


def make(max_iter: int, **extra) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        learning_rate=0.1, max_iter=max_iter, early_stopping=False, random_state=SEED, **extra
    )


results, timing, curves = {}, {}, {}
best_name, best_pr = None, -1.0
for name, extra in variants.items():
    t = time.time()
    big = make(MAX_TREES, **extra).fit(X_tr, y_tr)
    print(f"{name}: fit {MAX_TREES} trees in {time.time() - t:.0f}s", flush=True)
    curve = {}
    for n, proba in enumerate(big.staged_predict_proba(X_va), start=1):
        if n % CHECK_EVERY == 0:
            curve[n] = float(average_precision_score(y_va, proba[:, 1]))
            print(f"  {n:4d} trees: val PR AUC {curve[n]:.3f}", flush=True)
    curves[name] = curve
    n_best = max(curve, key=curve.get)

    model = make(n_best, **extra).fit(X_tr, y_tr)
    t = time.time()
    score = model.predict_proba(X_va)[:, 1]
    pred_s = time.time() - t
    results[name] = summarize_by_origin(y_va, score, val.origin.to_numpy())
    timing[name] = {"trees": n_best, "predict_rows_per_second": round(len(X_va) / pred_s)}
    print(f"{name}: best {n_best} trees, predicts {len(X_va) / pred_s:,.0f} rows/s", flush=True)
    if curve[n_best] > best_pr:
        best_name, best_pr = name, curve[n_best]
        joblib.dump(model, config.MODELS_DIR / "activity_hgb.joblib")

previous = json.loads((config.ROOT / "reports" / "activity_baselines.json").read_text())
results["rf (earlier run)"] = previous["val"]["rf"]
timing["rf (earlier run)"] = previous["timing"]["rf"]

(config.ROOT / "reports" / "activity_boosting.json").write_text(
    json.dumps(
        {"val": results, "timing": timing, "pr_auc_by_trees": curves, "saved": best_name},
        indent=1,
    )
)

rows = []
for name, by_origin in results.items():
    for group, r in by_origin.items():
        rows.append(
            {
                "model": name,
                "positives": group,
                "ROC AUC": r["roc_auc"],
                "PR AUC": r["pr_auc"],
                "recall@FPR1e-3": r["recall@fpr=0.001"],
                "recall@FPR1e-4": r["recall@fpr=0.0001"],
                "precision@1e-3,p=1e-3": r["precision@fpr=0.001,p=0.001"],
            }
        )
print("\n=== validation set ===")
print(pd.DataFrame(rows).round(3).to_string(index=False))
print("\nsaved model:", best_name)
