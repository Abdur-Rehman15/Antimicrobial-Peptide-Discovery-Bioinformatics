"""Check (and if needed repair) the calibration of the activity and hemolysis scores.

Usage:  python -u scripts/calibrate_scores.py

Needs scripts/cv_activity_boosting.py (final config), train_activity_final.py and
train_hemolysis.py to have run.

ACTIVITY
  1. 5-fold purged grouped cross-validation on train + val gives a score for every row from a
     model that never saw it (saved to data/interim/activity_oof.npy).
  2. At the model's own class balance (about 3 positives in 100 rows) the scores are checked with a
     reliability table and a calibration intercept/slope.
  3. A 2-parameter logistic recalibrator is fitted on these scores.
  4. The prior shift to real-world rarity (1 in 100, 1 in 1,000, 1 in 10,000) is applied and
     checked against the evaluation rows re-weighted to that rarity.
  5. Confirmation on the TEST split with the final model: raw vs recalibrated, shifted to the
     test split's own balance (1 in 101), where the right answer is known.
HEMOLYSIS
  Same idea on 5-fold purged CV of the chosen SVM, then the test split.
Writes reports/calibration.json, models/saved/activity_calibration.json and
models/saved/hemolysis_calibration.json.
"""

import json
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from amp_triage import config
from amp_triage.data.clustering import similar_pairs
from amp_triage.features.descriptors import FEATURE_NAMES
from amp_triage.models.calibration import (
    ACTIVITY_EDGES,
    EVEN_EDGES,
    LogisticRecalibrator,
    negative_weight,
    reliability_table,
    shift_prior,
    summarize,
)
from amp_triage.models.cv import activity_pool_pairs, purge_training_rows

SEED = 0
FOLDS = 5
PREVALENCES = (1e-2, 1e-3, 1e-4)
REPORT = {}


def show(title: str, rows: dict) -> None:
    print(f"\n{title}")
    print(pd.DataFrame(rows).T.round(4).to_string())


# =============================== ACTIVITY ====================================================
data = pd.read_csv(config.PROCESSED_DIR / "activity_dataset.csv")
pool = data[data.split.isin(["train", "val"])].reset_index(drop=True)
test = data[data.split == "test"].reset_index(drop=True)
X, y = pool[FEATURE_NAMES].to_numpy(), pool.label.to_numpy()
origin = pool.origin.to_numpy()
chosen = json.loads((config.ROOT / "reports" / "activity_final_config.json").read_text())

oof_path = config.INTERIM_DIR / "activity_oof.npy"
if oof_path.exists():
    oof = np.load(oof_path)
    print(f"loaded saved out-of-fold scores {oof_path.name}", flush=True)
else:
    pa, pb = activity_pool_pairs(pool)
    strata = np.where(y == 0, 0, np.where(origin == "natural", 2, 1))
    splitter = StratifiedGroupKFold(FOLDS, shuffle=True, random_state=SEED)
    folds = splitter.split(X, strata, pool.group)
    oof = np.full(len(pool), np.nan)
    for f, (tr_all, te) in enumerate(folds, start=1):
        t = time.time()
        tr = purge_training_rows(tr_all, te, pa, pb, len(pool))
        model = HistGradientBoostingClassifier(
            max_iter=chosen["trees"], early_stopping=False, random_state=SEED, **chosen["config"]
        ).fit(X[tr], y[tr])
        oof[te] = model.predict_proba(X[te])[:, 1]
        print(f"activity fold {f}/{FOLDS} done in {time.time() - t:.0f}s", flush=True)
    np.save(oof_path, oof)
assert not np.isnan(oof).any()

pi_train = float(y.mean())  # the class balance the model was trained on
print(f"\ntraining class balance: {pi_train:.4f} positives ({y.sum():,} of {len(y):,})")
act = {"pi_train": pi_train}

# 2. the model's own balance
tab = reliability_table(y, oof)
print("\n=== ACTIVITY: reliability at the model's own class balance (out-of-fold) ===")
print(tab.round(4).to_string(index=False))
act["own_balance"] = summarize(y, oof)
natural_rows = (y == 0) | (origin == "natural")
act["own_balance_natural"] = summarize(y[natural_rows], oof[natural_rows])
show("calibration at own balance (slope 1 / intercept 0 = perfect)",
     {"all positives": act["own_balance"], "natural positives": act["own_balance_natural"]})

# 3. recalibrator
recal = LogisticRecalibrator.fit(y, oof)
act["recalibrator"] = {"intercept": recal.intercept, "slope": recal.slope, "pi_train": pi_train}
fixed = recal.apply(oof)
act["own_balance_after"] = summarize(y, fixed)
print(f"\nrecalibrator: intercept {recal.intercept:.3f}, slope {recal.slope:.3f}")
show("after recalibration, at own balance", {"raw": act["own_balance"],
                                              "recalibrated": act["own_balance_after"]})

# 4. real-world rarity
n_pos, n_neg = int(y.sum()), int((y == 0).sum())
act["real_world"] = {}
for pi in PREVALENCES:
    w = np.where(y == 1, 1.0, negative_weight(n_pos, n_neg, pi))
    unshifted = summarize(y, oof, w)
    shifted = summarize(y, shift_prior(oof, pi_train, pi), w)
    both = summarize(y, shift_prior(fixed, pi_train, pi), w)
    act["real_world"][f"{pi:g}"] = {"raw": unshifted, "shifted": shifted, "recal+shifted": both}
    show(f"real-world rarity {pi:g}: evaluation rows re-weighted to that rarity",
         {"raw score": unshifted, "after prior shift": shifted, "recalibrated + shifted": both})
    table = reliability_table(y, shift_prior(fixed, pi_train, pi), w, ACTIVITY_EDGES)
    print(table.round(5).to_string(index=False))

# 5. confirmation on the test split (final model trained on all of train + val)
final = joblib.load(config.MODELS_DIR / "activity_final.joblib")
y_te = test.label.to_numpy()
raw_te = final.predict_proba(test[FEATURE_NAMES].to_numpy())[:, 1]
pi_test = float(y_te.mean())
conf = {
    "raw (as trained)": summarize(y_te, raw_te),
    "prior-shifted to test balance": summarize(y_te, shift_prior(raw_te, pi_train, pi_test)),
    "recalibrated + shifted": summarize(
        y_te, shift_prior(recal.apply(raw_te), pi_train, pi_test)
    ),
}
act["test_confirmation"] = {"pi_test": pi_test, **conf}
show(f"TEST split confirmation (its own balance is {pi_test:.4f})", conf)
REPORT["activity"] = act
(config.MODELS_DIR / "activity_calibration.json").write_text(json.dumps(act["recalibrator"]))

# =============================== HEMOLYSIS ===================================================
hemo = pd.read_csv(config.PROCESSED_DIR / "hemolysis_dataset.csv")
hp = hemo[hemo.split.isin(["train", "val"])].reset_index(drop=True)
ht = hemo[hemo.split == "test"].reset_index(drop=True)
Xh, yh = hp[FEATURE_NAMES].to_numpy(), hp.label.to_numpy()
winner = json.loads((config.ROOT / "reports" / "hemolysis_final_test.json").read_text())
params = dict(winner["params"], probability=True, random_state=SEED)
assert winner["model"] == "svm"
ha, hb, _ = similar_pairs(hp.sequence.tolist(), min_sim=0.7, verbose=False)
oof_h = np.full(len(hp), np.nan)
folds = StratifiedGroupKFold(FOLDS, shuffle=True, random_state=SEED).split(Xh, yh, hp.group)
for tr_all, te in folds:
    tr = purge_training_rows(tr_all, te, ha, hb, len(hp))
    model = make_pipeline(StandardScaler(), SVC(kernel="rbf", **params)).fit(Xh[tr], yh[tr])
    oof_h[te] = model.predict_proba(Xh[te])[:, 1]
hem = {}
print("\n=== HEMOLYSIS: reliability (out-of-fold, 5 equal bins) ===")
print(reliability_table(yh, oof_h, edges=EVEN_EDGES).round(3).to_string(index=False))
hem["oof"] = summarize(yh, oof_h, edges=EVEN_EDGES)
hem["base_rate_brier"] = float(yh.mean() * (1 - yh.mean()))
recal_h = LogisticRecalibrator.fit(yh, oof_h)
hem["recalibrator"] = {"intercept": recal_h.intercept, "slope": recal_h.slope}
hem["oof_after"] = summarize(yh, recal_h.apply(oof_h), edges=EVEN_EDGES)
final_h = joblib.load(config.MODELS_DIR / "hemolysis_final.joblib")
raw_h = final_h.predict_proba(ht[FEATURE_NAMES].to_numpy())[:, 1]
hem["test"] = {
    "raw": summarize(ht.label.to_numpy(), raw_h, edges=EVEN_EDGES),
    "recalibrated": summarize(ht.label.to_numpy(), recal_h.apply(raw_h), edges=EVEN_EDGES),
    "base_rate_brier": float(ht.label.mean() * (1 - ht.label.mean())),
}
show("hemolysis calibration (Brier of always guessing the base rate: "
     f"{hem['base_rate_brier']:.3f})",
     {"out-of-fold, raw": hem["oof"], "out-of-fold, recalibrated": hem["oof_after"],
      "TEST, raw": hem["test"]["raw"], "TEST, recalibrated": hem["test"]["recalibrated"]})
print(f"\nhemolysis recalibrator: intercept {recal_h.intercept:.3f}, slope {recal_h.slope:.3f}")
REPORT["hemolysis"] = hem
(config.MODELS_DIR / "hemolysis_calibration.json").write_text(json.dumps(hem["recalibrator"]))

(config.ROOT / "reports" / "calibration.json").write_text(json.dumps(REPORT, indent=1))
print("\nwritten: reports/calibration.json")
