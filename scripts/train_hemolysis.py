"""Hemolysis classifier: choose by grouped cross-validation, then score the test split once.

Usage:  python -u scripts/train_hemolysis.py

Models: logistic regression (baseline), SVM with RBF kernel, Random Forest, each with a small
fixed grid. Selection: repeated (3 x 5-fold) grouped cross-validation on train + val, in which
every fold also drops training peptides >= 0.7 similar to a held-out peptide (clusters alone
leave near-copies on both sides). Winner = best mean ROC AUC; a simpler model (logistic
regression, then SVM, then forest) is preferred when it is within 0.005 of the best.
Then the winner is refit on all of train + val and the test split is scored ONCE, with a 95%
confidence interval from resampling whole clusters.

Only the 35 descriptors are used (the HAPPENN end-modification flags are metadata).
Writes reports/hemolysis_cv.json, reports/hemolysis_final_test.json and
models/saved/hemolysis_final.joblib.
"""

import json
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, matthews_corrcoef, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from amp_triage import config
from amp_triage.data.clustering import similar_pairs
from amp_triage.features.descriptors import FEATURE_NAMES

SEED = 0
REPEATS = 3
FOLDS = 5
TAU = 0.7
TIE_MARGIN = 0.005
PREFERENCE = ["logreg", "svm", "rf"]  # simplest first

data = pd.read_csv(config.PROCESSED_DIR / "hemolysis_dataset.csv")
pool = data[data.split.isin(["train", "val"])].reset_index(drop=True)
test = data[data.split == "test"].reset_index(drop=True)
X, y = pool[FEATURE_NAMES].to_numpy(), pool.label.to_numpy()
print(f"pool {len(pool):,} peptides ({y.mean():.0%} hemolytic), test {len(test):,}", flush=True)

pa, pb, ps = similar_pairs(pool.sequence.tolist(), min_sim=TAU, verbose=False)
print(f"{len(pa):,} similar pairs (>= {TAU}) inside the pool", flush=True)


def purge(train_idx: np.ndarray, test_idx: np.ndarray) -> np.ndarray:
    """Training rows minus peptides >= TAU similar to a held-out peptide (asserted)."""
    in_test = np.zeros(len(pool), bool)
    in_test[test_idx] = True
    drop = np.zeros(len(pool), bool)
    drop[pb[in_test[pa] & ~in_test[pb]]] = True
    drop[pa[in_test[pb] & ~in_test[pa]]] = True
    kept = train_idx[~drop[train_idx]]
    in_kept = np.zeros(len(pool), bool)
    in_kept[kept] = True
    assert not ((in_test[pa] & in_kept[pb]) | (in_test[pb] & in_kept[pa])).any()
    return kept


def make(family: str, **p):
    if family == "logreg":
        return make_pipeline(StandardScaler(), LogisticRegression(max_iter=5000, **p))
    if family == "svm":
        return make_pipeline(StandardScaler(), SVC(kernel="rbf", **p))
    return RandomForestClassifier(n_estimators=500, n_jobs=-1, random_state=SEED, **p)


def score(model, X_te: np.ndarray) -> np.ndarray:
    return model.decision_function(X_te) if hasattr(model, "decision_function") else (
        model.predict_proba(X_te)[:, 1]
    )


grids = {
    "logreg": [{"C": c} for c in (0.01, 0.1, 1.0, 10.0)],
    "svm": [{"C": c, "gamma": g} for c in (0.3, 1, 3, 10, 30) for g in (0.003, 0.01, 0.03, 0.1)],
    "rf": [{"max_features": mf, "min_samples_leaf": leaf}
           for mf in ("sqrt", 0.5) for leaf in (1, 3, 5)],
}

folds = []
for r in range(REPEATS):
    splitter = StratifiedGroupKFold(FOLDS, shuffle=True, random_state=SEED + r)
    folds += list(splitter.split(X, y, pool.group))

report, best_of = {}, {}
for family, grid in grids.items():
    t = time.time()
    for params in grid:
        aucs, prs, accs, mccs = [], [], [], []
        for tr_all, te in folds:
            tr = purge(tr_all, te)
            model = make(family, **params).fit(X[tr], y[tr])
            s = score(model, X[te])
            pred = model.predict(X[te])
            aucs.append(roc_auc_score(y[te], s))
            prs.append(average_precision_score(y[te], s))
            accs.append(float(np.mean(pred == y[te])))
            mccs.append(matthews_corrcoef(y[te], pred))
        key = f"{family} {json.dumps(params)}"
        report[key] = {"family": family, "params": params,
                       "roc_auc": [float(np.mean(aucs)), float(np.std(aucs))],
                       "pr_auc": float(np.mean(prs)), "accuracy": float(np.mean(accs)),
                       "mcc": float(np.mean(mccs))}
        if family not in best_of or report[key]["roc_auc"][0] > best_of[family]["roc_auc"][0]:
            best_of[family] = report[key]
    b = best_of[family]
    print(f"{family}: {len(grid)} settings in {time.time() - t:.0f}s; best ROC AUC "
          f"{b['roc_auc'][0]:.3f} +- {b['roc_auc'][1]:.3f}  {b['params']}", flush=True)

top = max(v["roc_auc"][0] for v in best_of.values())
winner = next(best_of[f] for f in PREFERENCE if best_of[f]["roc_auc"][0] >= top - TIE_MARGIN)
(config.ROOT / "reports" / "hemolysis_cv.json").write_text(json.dumps(report, indent=1))

print("\n=== grouped CV on train+val (3 x 5 folds, purged); mean over folds ===")
print(pd.DataFrame(
    [{"model": f, "ROC AUC": v["roc_auc"][0], "spread": v["roc_auc"][1], "PR AUC": v["pr_auc"],
      "accuracy": v["accuracy"], "MCC": v["mcc"]} for f, v in best_of.items()]
).round(3).to_string(index=False))
print(f"\nchosen: {winner['family']} {winner['params']}", flush=True)

# ---- final: refit on all of train + val, score test once -----------------------------------
params = dict(winner["params"])
if winner["family"] == "svm":
    params["probability"] = True  # Platt scaling, so the pipeline gets a 0-1 risk
    params["random_state"] = SEED
model = make(winner["family"], **params).fit(X, y)
joblib.dump(model, config.MODELS_DIR / "hemolysis_final.joblib")

X_te, y_te = test[FEATURE_NAMES].to_numpy(), test.label.to_numpy()
proba = model.predict_proba(X_te)[:, 1]
pred = (proba >= 0.5).astype(int)


def metrics(idx: np.ndarray) -> list[float]:
    yt, pt, dt = y_te[idx], proba[idx], pred[idx]
    return [roc_auc_score(yt, pt), average_precision_score(yt, pt),
            float(np.mean(dt == yt)), matthews_corrcoef(yt, dt)]


point = metrics(np.arange(len(test)))
rng = np.random.default_rng(SEED)
clusters = test.group.unique()
members = {g: np.flatnonzero(test.group.to_numpy() == g) for g in clusters}
boot = []
for _ in range(2000):
    idx = np.concatenate([members[g] for g in rng.choice(clusters, len(clusters))])
    if 0 < y_te[idx].mean() < 1:
        boot.append(metrics(idx))
lo, hi = np.percentile(boot, [2.5, 97.5], axis=0)

names = ["ROC AUC", "PR AUC", "accuracy", "MCC"]
final = {n: {"value": float(v), "ci95": [float(a), float(b)]}
         for n, v, a, b in zip(names, point, lo, hi, strict=True)}
(config.ROOT / "reports" / "hemolysis_final_test.json").write_text(
    json.dumps({"model": winner["family"], "params": winner["params"], "test": final,
                "n_test": len(test), "hemolytic_share": float(y_te.mean())}, indent=1)
)
print(f"\n=== TEST ({len(test)} peptides, scored once): {winner['family']} ===")
for n in names:
    print(f"{n:9s} {final[n]['value']:.3f}   95% CI {final[n]['ci95'][0]:.3f} to "
          f"{final[n]['ci95'][1]:.3f}")
