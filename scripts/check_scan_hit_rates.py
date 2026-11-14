"""How often do windows of real human proteins pass the score thresholds, by length?

Usage:  python -u scripts/check_scan_hit_rates.py   (needs check_length_bias.py to have run)

The thresholds are the ones that let 1 in 1,000 and 1 in 10,000 of the TRAINING negatives through
(random windows of non-human proteins). Real AMPs are so rare in a proteome that almost every hit
in 300 random human proteins is a false alarm, so the hit rate here estimates the false-positive
rate on the windows the system will actually scan. If it is far above 1e-3 / 1e-4, or differs by
length, the training negatives do not represent a proteome.
Uses the same 300 proteins as ranking_stability.py (seed 0).
Writes reports/scan_hit_rates.json.
"""

import json

import joblib
import numpy as np
import pandas as pd

from amp_triage import config
from amp_triage.candidates.window_features import WindowFeatureEngine, iter_proteome_chunks
from amp_triage.pipeline import read_fasta

SEED, SAMPLE = 0, 300
BANDS = [(8, 12), (13, 20), (21, 35), (36, 50)]
bias = json.loads((config.ROOT / "reports" / "length_bias.json").read_text())
thresholds = {k: v["threshold"] for k, v in bias["B_global_threshold"].items()}
print("thresholds:", thresholds, flush=True)

model = joblib.load(config.MODELS_DIR / "activity_final.joblib")
accessions, sequences = read_fasta(config.RAW_DIR / "uniprot" / "human_reviewed.fasta")
pick = np.sort(np.random.default_rng(SEED).choice(len(accessions), SAMPLE, replace=False))
accessions, sequences = [accessions[i] for i in pick], [sequences[i] for i in pick]

windows = np.zeros(51, dtype=np.int64)
hits = {k: np.zeros(51, dtype=np.int64) for k in thresholds}
for chunk in iter_proteome_chunks(accessions, sequences):
    engine = WindowFeatureEngine(chunk)
    for length in range(8, 51):
        starts, X = engine.descriptors(length)
        if len(starts) == 0:
            continue
        score = model.predict_proba(X)[:, 1]
        windows[length] += len(starts)
        for key, thr in thresholds.items():
            hits[key][length] += int((score > thr).sum())
    print("chunk done", flush=True)

out = {}
for key in thresholds:
    rows = []
    for lo, hi in BANDS:
        n, h = windows[lo : hi + 1].sum(), hits[key][lo : hi + 1].sum()
        rows.append({"band": f"{lo}-{hi}", "windows": int(n), "hits": int(h),
                     "hit_rate": h / n, "vs_training_fpr": h / n / float(key)})
    n, h = windows.sum(), hits[key].sum()
    rows.append({"band": "all", "windows": int(n), "hits": int(h), "hit_rate": h / n,
                 "vs_training_fpr": h / n / float(key)})
    table = pd.DataFrame(rows).set_index("band")
    out[key] = table.to_dict("index")
    print(f"\n=== threshold for training false-positive rate {key} (score > "
          f"{thresholds[key]:.3f}) ===")
    print(table.round(5).to_string())
    print("(vs_training_fpr = 1 means human windows pass as often as the training negatives)")
(config.ROOT / "reports" / "scan_hit_rates.json").write_text(json.dumps(out, indent=1))
