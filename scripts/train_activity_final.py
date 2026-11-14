"""Train the final activity model and score the test split exactly once.

Usage:  python -u scripts/train_activity_final.py

Needs reports/activity_final_config.json (scripts/cv_activity_boosting.py).
Trains on all labelled activity rows (train + val) with the chosen gradient-boosting setting,
then scores:
  * the test split (positives and 100 negatives each): the honest estimate for new peptides;
  * the human hold-out positives: what share score above the thresholds that let through
    1 in 1,000 / 1 in 10,000 test negatives.
The test split is read only here. Do not rerun this to try other settings.
Writes models/saved/activity_final.joblib and reports/activity_final_test.json.
"""

import json
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from amp_triage import config
from amp_triage.features.descriptors import FEATURE_NAMES
from amp_triage.models.evaluation import FPR_LEVELS, summarize_by_origin

SEED = 0

chosen = json.loads((config.ROOT / "reports" / "activity_final_config.json").read_text())
cfg, trees = chosen["config"], chosen["trees"]
print(f"setting {cfg}, {trees} trees", flush=True)

data = pd.read_csv(config.PROCESSED_DIR / "activity_dataset.csv")
fit_rows = data[data.split.isin(["train", "val"])]
test = data[data.split == "test"]
human = data[data.split == "human"]
print(f"fit on {len(fit_rows):,} rows ({int(fit_rows.label.sum()):,} positives); "
      f"test {len(test):,}; human positives {len(human):,}", flush=True)

t = time.time()
model = HistGradientBoostingClassifier(
    max_iter=trees, early_stopping=False, random_state=SEED, **cfg
).fit(fit_rows[FEATURE_NAMES].to_numpy(), fit_rows.label.to_numpy())
print(f"trained in {time.time() - t:.0f}s", flush=True)
joblib.dump(model, config.MODELS_DIR / "activity_final.joblib")

t = time.time()
test_score = model.predict_proba(test[FEATURE_NAMES].to_numpy())[:, 1]
speed = round(len(test) / (time.time() - t))
by_origin = summarize_by_origin(test.label.to_numpy(), test_score, test.origin.to_numpy())

# human hold-out: thresholds taken from the test negatives
human_score = model.predict_proba(human[FEATURE_NAMES].to_numpy())[:, 1]
neg_scores = test_score[test.label.to_numpy() == 0]
human_result = {}
for fpr in FPR_LEVELS:
    thr = np.quantile(neg_scores, 1.0 - fpr)
    entry = {"all": float(np.mean(human_score > thr))}
    for kind in ("natural", "synthetic"):
        entry[kind] = float(np.mean(human_score[(human.origin == kind).to_numpy()] > thr))
    human_result[f"recall@fpr={fpr:g}"] = entry

(config.ROOT / "reports" / "activity_final_test.json").write_text(
    json.dumps(
        {"config": cfg, "trees": trees, "test": by_origin, "human_holdout": human_result,
         "predict_rows_per_second": speed},
        indent=1,
    )
)

print("\n=== TEST set (scored once) ===")
rows = []
for group, r in by_origin.items():
    rows.append(
        {
            "positives": group,
            "n_pos": r["n_pos"],
            "ROC AUC": r["roc_auc"],
            "PR AUC": r["pr_auc"],
            "recall@FPR1e-3": r["recall@fpr=0.001"],
            "recall@FPR1e-4": r["recall@fpr=0.0001"],
            "precision@FPR1e-3,p=1e-3": r["precision@fpr=0.001,p=0.001"],
            "precision@FPR1e-4,p=1e-4": r["precision@fpr=0.0001,p=0.0001"],
        }
    )
print(pd.DataFrame(rows).round(3).to_string(index=False))
print("\n=== human hold-out positives (never used in training) ===")
print(pd.DataFrame(human_result).T.round(3).to_string())
print(f"\nprediction speed: {speed:,} rows/s")
