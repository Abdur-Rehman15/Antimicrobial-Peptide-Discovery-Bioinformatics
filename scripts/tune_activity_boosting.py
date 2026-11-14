"""Random search over gradient-boosting settings for the activity classifier.

Usage:  python -u scripts/tune_activity_boosting.py

Fixed budget: N_CONFIGS random settings (seeded), each fit on split == "train" with up to
MAX_TREES trees. The tree count is chosen for free from the validation curve (checked every
CHECK_EVERY trees). Objective: PR AUC of natural positives against all validation negatives,
because finding natural (hidden) peptides is the project's goal.

Choosing among 40 settings on one validation set favours lucky settings, so the best few are
re-judged by grouped cross-validation (scripts/cv_activity_boosting.py). The test split is not
touched. Results are appended to reports/activity_tuning.jsonl, so an interrupted run resumes.
"""

import json
import time

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score

from amp_triage import config
from amp_triage.features.descriptors import FEATURE_NAMES

SEED = 0
N_CONFIGS = 40
MAX_TREES = 1000
CHECK_EVERY = 100
OUT = config.ROOT / "reports" / "activity_tuning.jsonl"


def sample_config(rng: np.random.Generator) -> dict:
    return {
        "learning_rate": round(float(np.exp(rng.uniform(np.log(0.05), np.log(0.2)))), 3),
        "max_leaf_nodes": int(rng.choice([15, 31, 63, 127])),
        "min_samples_leaf": int(rng.choice([20, 50, 100, 200])),
        "l2_regularization": float(rng.choice([0.0, 1.0, 10.0, 30.0])),
        "max_features": float(rng.choice([0.3, 0.5, 0.8, 1.0])),
    }


REFERENCE = {"learning_rate": 0.1, "max_leaf_nodes": 31, "min_samples_leaf": 20,
             "l2_regularization": 0.0, "max_features": 1.0}
rng = np.random.default_rng(SEED)
configs = [sample_config(rng) for _ in range(N_CONFIGS)]
# the setting used so far, as the reference point
configs.insert(0, REFERENCE)

data = pd.read_csv(config.PROCESSED_DIR / "activity_dataset.csv")
train, val = data[data.split == "train"], data[data.split == "val"]
X_tr, y_tr = train[FEATURE_NAMES].to_numpy(), train.label.to_numpy()
X_va, y_va = val[FEATURE_NAMES].to_numpy(), val.label.to_numpy()
is_nat = ((val.origin == "natural") | (val.label == 0)).to_numpy()
print(f"train {len(train):,}, val {len(val):,}; {len(configs)} settings", flush=True)

done = set()
if OUT.exists():
    done = {json.dumps(json.loads(line)["config"], sort_keys=True) for line in OUT.open()}

for k, cfg in enumerate(configs, start=1):
    key = json.dumps(cfg, sort_keys=True)
    if key in done:
        continue
    t = time.time()
    model = HistGradientBoostingClassifier(
        max_iter=MAX_TREES, early_stopping=False, random_state=SEED, **cfg
    ).fit(X_tr, y_tr)
    best = {"natural_pr": -1.0}
    for n, proba in enumerate(model.staged_predict_proba(X_va), start=1):
        if n % CHECK_EVERY:
            continue
        p = proba[:, 1]
        nat = float(average_precision_score(y_va[is_nat], p[is_nat]))
        if nat > best["natural_pr"]:
            all_pr = float(average_precision_score(y_va, p))
            best = {"trees": n, "natural_pr": nat, "all_pr": all_pr}
    row = {"config": cfg, **best, "seconds": round(time.time() - t)}
    with OUT.open("a") as f:
        f.write(json.dumps(row) + "\n")
    print(f"[{k}/{len(configs)}] natural PR {best['natural_pr']:.3f}, all PR {best['all_pr']:.3f}, "
          f"{best['trees']} trees, {row['seconds']}s  {cfg}", flush=True)

rows = [json.loads(line) for line in OUT.open()]
rows.sort(key=lambda r: -r["natural_pr"])
print("\n=== top 5 by natural PR AUC (validation) ===")
for r in rows[:5]:
    print(f"natural {r['natural_pr']:.3f}  all {r['all_pr']:.3f}  trees {r['trees']}  "
          f"{r['config']}")
ref = next(r for r in rows if r["config"] == REFERENCE)
print(f"\nreference (old setting): natural {ref['natural_pr']:.3f}  all {ref['all_pr']:.3f}")
