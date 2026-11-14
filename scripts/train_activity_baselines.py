"""Train the activity baselines and the Random Forest; score them on the validation set.

Usage:  python scripts/train_activity_baselines.py

Trains on split == "train", evaluates on split == "val". The test split is NOT touched here: it
is kept for one final evaluation after all choices are made.
Writes reports/activity_baselines.json and models/saved/activity_{logreg,rf}.joblib.
"""

import json
import time

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from amp_triage import config
from amp_triage.features.descriptors import FEATURE_NAMES
from amp_triage.models.evaluation import summarize_by_origin

SEED = 0

data = pd.read_csv(config.PROCESSED_DIR / "activity_dataset.csv")
train = data[data.split == "train"]
val = data[data.split == "val"]
X_tr, y_tr = train[FEATURE_NAMES].to_numpy(), train.label.to_numpy()
X_va, y_va = val[FEATURE_NAMES].to_numpy(), val.label.to_numpy()
print(f"train {len(train):,} rows ({y_tr.sum():,} positives), val {len(val):,} "
      f"({y_va.sum():,} positives)")

results, timing = {}, {}

# 1. charge only: no training, the net charge itself is the score
results["charge_only"] = summarize_by_origin(y_va, val.net_charge.to_numpy(), val.origin.to_numpy())

# 2. logistic regression on all 35 features
models = {
    "logreg": make_pipeline(
        StandardScaler(),
        LogisticRegression(C=1.0, class_weight="balanced", max_iter=2000),
    ),
    # 3. random forest, all cores
    "rf": RandomForestClassifier(
        n_estimators=300,
        min_samples_leaf=2,
        max_features="sqrt",
        class_weight="balanced_subsample",
        n_jobs=-1,
        random_state=SEED,
    ),
}
for name, model in models.items():
    t = time.time()
    model.fit(X_tr, y_tr)
    fit_s = time.time() - t
    t = time.time()
    score = model.predict_proba(X_va)[:, 1]
    pred_s = time.time() - t
    results[name] = summarize_by_origin(y_va, score, val.origin.to_numpy())
    timing[name] = {
        "fit_seconds": round(fit_s, 1),
        "predict_rows_per_second": round(len(X_va) / pred_s),
    }
    joblib.dump(model, config.MODELS_DIR / f"activity_{name}.joblib")
    print(f"{name}: fit {fit_s:.0f}s, predicts {len(X_va) / pred_s:,.0f} rows/s")

importance = pd.Series(models["rf"].feature_importances_, index=FEATURE_NAMES).sort_values(
    ascending=False
)
(config.ROOT / "reports").mkdir(exist_ok=True)
(config.ROOT / "reports" / "activity_baselines.json").write_text(
    json.dumps({"val": results, "timing": timing, "rf_importance": importance.round(4).to_dict()},
               indent=1)
)

# ---- summary ------------------------------------------------------------------------------
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
print("\nRandom forest, top 10 features:")
print(importance.head(10).round(3).to_string())
