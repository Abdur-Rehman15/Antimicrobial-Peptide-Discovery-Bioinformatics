"""Cluster the positives, split by cluster, purge cross-split near-copies.  Usage:
    python scripts/build_splits.py [threshold]       (default 0.7)
Needs data/interim/positive_pairs.npz (scripts/cluster_positives.py).
Writes data/processed/positives_split.csv.
"""

import sys

import numpy as np
import pandas as pd

from amp_triage import config
from amp_triage.data.clustering import greedy_clusters, purge_similar
from amp_triage.data.splits import assign_splits

TAU = float(sys.argv[1]) if len(sys.argv) > 1 else 0.7

pos = pd.read_csv(config.PROCESSED_DIR / "positives.csv")
z = np.load(config.INTERIM_DIR / "positive_pairs.npz")
i, j, s = z["i"], z["j"], z["sim"]
nat = (pos.origin == "natural").values

cluster = greedy_clusters(pos.length.values, i, j, s, TAU)
split = assign_splits(cluster, pos.holdout_human.values, nat, seed=0)
drop = purge_similar(split, i, j, s, TAU)
final = np.where(drop, "dropped_similar", split)

# verify the guarantee directly: no kept pair from two different splits is similar
cross = (s >= TAU) & (final[i] != final[j]) & ~drop[i] & ~drop[j]
assert not cross.any(), f"{cross.sum()} similar pairs still cross splits"

out = pos[["sequence", "origin", "sources", "length", "holdout_human"]].copy()
out["cluster"], out["split"] = cluster, final
out.to_csv(config.PROCESSED_DIR / "positives_split.csv", index=False)

print(f"threshold {TAU}: {cluster.max() + 1:,} clusters (largest {np.bincount(cluster).max()})")
tab = out.groupby("split").agg(
    peptides=("sequence", "size"),
    natural=("origin", lambda o: int((o == "natural").sum())),
    median_len=("length", "median"),
)
print(tab.loc[["train", "val", "test", "human", "dropped_similar"]].to_string())
print("\nguarantee verified: no kept pair with similarity >=", TAU, "crosses two splits")
n_human = int(out[out.split == "human"].holdout_human.sum())
print("held-out human peptides labelled/found human:", n_human)
