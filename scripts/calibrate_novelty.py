"""Measure what similarity to known AMPs means, so the novelty labels are not arbitrary.

Usage:  python -u scripts/calibrate_novelty.py

Every candidate is compared with ~17,000 known AMPs and keeps its BEST match, so even a random
fragment reaches a fairly high similarity by chance. Three groups show what is chance and what is
real, all compared with the reference of known AMPs:
  * random background: random windows of non-AMP proteins (validation negatives);
  * hard background:   the 1% of those windows that the activity model finds most AMP-like.
                       These resemble the candidates we will actually shortlist, so they show
                       the chance level that matters. Scored with models/saved/activity_hgb.joblib,
                       which was trained on train rows only, so validation rows are unseen;
  * real AMPs:         test-split positives, compared with the rest of the reference (their own
                       sequence is skipped).
The "related" cut-off is the 99th percentile of the HARD background. The test split's AMPs are
used only for this comparison, not for any model choice.
Writes reports/novelty_calibration.json.
"""

import json
import time

import joblib
import numpy as np
import pandas as pd

from amp_triage import config
from amp_triage.features.descriptors import FEATURE_NAMES
from amp_triage.novelty.reference import load_known_amps
from amp_triage.novelty.search import KNOWN, NoveltyIndex

SEED = 0
N_RANDOM = 3000
HARD_SHARE = 0.01
QUANTILES = [0.5, 0.9, 0.95, 0.99, 0.999]
BANDS = [(8, 15), (16, 25), (26, 50)]

known = load_known_amps()
index = NoveltyIndex(known.sequence, known.ids)
data = pd.read_csv(config.PROCESSED_DIR / "activity_dataset.csv")
val_neg = data[(data.split == "val") & (data.label == 0)].reset_index(drop=True)
real = data[(data.split == "test") & (data.label == 1)]

rng = np.random.default_rng(SEED)
random_bg = val_neg.sequence.iloc[rng.choice(len(val_neg), N_RANDOM, replace=False)].tolist()
model = joblib.load(config.MODELS_DIR / "activity_hgb.joblib")
score = model.predict_proba(val_neg[FEATURE_NAMES].to_numpy())[:, 1]
n_hard = int(len(val_neg) * HARD_SHARE)
hard_bg = val_neg.sequence.iloc[np.argsort(-score)[:n_hard]].tolist()
print(f"reference {len(index):,}; random background {len(random_bg):,}; hard background "
      f"{len(hard_bg):,}; real AMPs {len(real):,}", flush=True)


def run(name, seqs, **kw):
    t = time.time()
    out = index.search(seqs, **kw)
    out["length"] = out.candidate.str.len()
    print(f"{name} done in {time.time() - t:.0f}s", flush=True)
    return out


rand = run("random background", random_bg)
hard = run("hard background", hard_bg)
rl = run("real AMPs", real.sequence.tolist(), exclude_identical=True)
rl["origin"] = real.origin.values


def quant(sim):
    return {f"p{q * 100:g}": float(np.quantile(sim, q)) for q in QUANTILES}


related_cutoff = float(np.quantile(hard.max_similarity, 0.99))
out = {
    "related_cutoff": related_cutoff,
    "known": KNOWN,
    "random_background": quant(rand.max_similarity),
    "hard_background": quant(hard.max_similarity),
    "hard_background_by_length": {
        f"{lo}-{hi}": {"n": int(hard.length.between(lo, hi).sum()),
                       **quant(hard[hard.length.between(lo, hi)].max_similarity)}
        for lo, hi in BANDS
    },
    "real_amps": {},
}
for name, sub in [("all", rl), ("natural", rl[rl.origin == "natural"]),
                  ("synthetic", rl[rl.origin == "synthetic"])]:
    s = sub.max_similarity
    out["real_amps"][name] = {
        "n": int(len(s)),
        "median": float(s.median()),
        "share_known": float((s >= KNOWN).mean()),
        "share_related": float(((s >= related_cutoff) & (s < KNOWN)).mean()),
        "share_novel": float((s < related_cutoff).mean()),
    }
(config.ROOT / "reports" / "novelty_calibration.json").write_text(json.dumps(out, indent=1))

print("\n=== best similarity to known AMPs, reached by CHANCE ===")
table = {"random windows": out["random_background"], "AMP-like windows": out["hard_background"]}
print(pd.DataFrame(table).round(3).to_string())
print("\nAMP-like windows by length band:")
print(pd.DataFrame({k: {q: v[q] for q in out["hard_background"]}
                    for k, v in out["hard_background_by_length"].items()}).round(3).to_string())
print(f"\nrelated cut-off (99th percentile of AMP-like windows): {related_cutoff:.3f}")
print("\n=== REAL test AMPs vs the rest of the reference ===")
print(pd.DataFrame(out["real_amps"]).T.round(3).to_string())
