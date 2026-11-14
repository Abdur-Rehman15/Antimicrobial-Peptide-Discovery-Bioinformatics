"""All-vs-all similarity of the positives, saved for clustering.  Usage:
    python scripts/cluster_positives.py
Writes data/interim/positive_pairs.npz (pairs with similarity >= 0.3).
"""

import time

import numpy as np
import pandas as pd

from amp_triage import config
from amp_triage.data.clustering import similar_pairs

pos = pd.read_csv(config.PROCESSED_DIR / "positives.csv")
t = time.time()
i, j, s = similar_pairs(pos.sequence.tolist(), min_sim=0.3)
np.savez_compressed(config.INTERIM_DIR / "positive_pairs.npz", i=i, j=j, sim=s)
print(f"done: {len(pos)} peptides, {len(i):,} similar pairs (sim >= 0.3) in {time.time() - t:.0f}s")
