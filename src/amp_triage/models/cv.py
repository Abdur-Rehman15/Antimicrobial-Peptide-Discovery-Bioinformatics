"""Helpers for similarity-aware cross-validation.

Clusters alone do not protect a fold: two peptides at least 0.7 similar can sit in different
clusters, so near-copies end up on both sides. `purge_training_rows` therefore drops, for each
fold, every training row that is similar to a held-out row (the rule the real splits use).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from amp_triage import config


def purge_training_rows(
    train_idx: np.ndarray, test_idx: np.ndarray, pa: np.ndarray, pb: np.ndarray, n_rows: int
) -> np.ndarray:
    """`train_idx` without rows paired (via pairs pa[k]-pb[k]) with a held-out row.

    Raises AssertionError if a similar pair still crosses train and held-out.
    """
    in_test = np.zeros(n_rows, bool)
    in_test[test_idx] = True
    drop = np.zeros(n_rows, bool)
    drop[pb[in_test[pa] & ~in_test[pb]]] = True
    drop[pa[in_test[pb] & ~in_test[pa]]] = True
    kept = train_idx[~drop[train_idx]]
    in_kept = np.zeros(n_rows, bool)
    in_kept[kept] = True
    leak = (in_test[pa] & in_kept[pb]) | (in_test[pb] & in_kept[pa])
    assert not leak.any(), f"{int(leak.sum())} similar pairs still cross train and held-out"
    return kept


def activity_pool_pairs(
    pool: pd.DataFrame, threshold: float = 0.7
) -> tuple[np.ndarray, np.ndarray]:
    """Row pairs (indices into `pool`) of activity positives that are >= threshold similar.

    `pool` is the activity dataset restricted to some splits, with a 0..n-1 index.
    """
    split_table = pd.read_csv(config.PROCESSED_DIR / "positives_split.csv")
    z = np.load(config.INTERIM_DIR / "positive_pairs.npz")
    positives = pool.label.to_numpy() == 1
    row_of = {s: r for r, s in enumerate(pool.sequence) if positives[r]}
    row_of_split_row = np.array([row_of.get(s, -1) for s in split_table.sequence])
    a, b = row_of_split_row[z["i"]], row_of_split_row[z["j"]]
    keep = (z["sim"] >= threshold) & (a >= 0) & (b >= 0)
    return a[keep], b[keep]
