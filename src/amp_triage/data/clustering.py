"""Group similar peptides so that train and test never contain near-copies of each other.

Similarity of two peptides a and b is

    sim(a, b) = SW(a, b) / min(SW(a, a), SW(b, b))

the Smith-Waterman score of the pair as a fraction of the best score the *shorter* peptide
could get (its score against itself). 1.0 means one peptide is contained in the other
unchanged; about 0.5 means roughly half of the shorter peptide matches. It uses the aligner
written for this project, so it also handles insertions and conservative substitutions, which
a simple identity count would miss.

Two ways of grouping are provided.

* `greedy_clusters` (used for splitting): the CD-HIT approach. Peptides are taken longest first;
  each peptide that is not yet in a cluster becomes a representative and claims every
  unclaimed peptide with sim >= threshold to it. Clusters stay compact and no chains form.
* `cluster_labels`: single linkage (connected components), which guarantees that no pair across
  two clusters is similar, but on dense data such as AMP lists it chains almost everything into
  one giant cluster (about 97% of the positives at threshold 0.5), so it is not used for splits.

Greedy clusters can leave similar pairs in different clusters, so after splitting the cross-split
pairs are purged with `purge_similar` to restore the guarantee.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from amp_triage.alignment.fast import EncodedSet


def similar_pairs(
    sequences: Sequence[str], min_sim: float = 0.3, verbose: bool = True
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """All pairs (i < j) with sim >= min_sim, as arrays (i, j, sim)."""
    enc = EncodedSet(sequences)
    self_scores = enc.self_scores()
    rows, cols, sims = [], [], []
    t0 = time.time()
    n = len(enc)
    for i in range(n - 1):
        scores = enc.scores_against(i, first=i + 1)
        sim = scores / np.minimum(self_scores[i], self_scores[i + 1 :])
        hit = np.nonzero(sim >= min_sim)[0]
        if len(hit):
            rows.append(np.full(len(hit), i, dtype=np.int64))
            cols.append(hit + i + 1)
            sims.append(sim[hit])
        if verbose and i % 1000 == 0:
            print(f"  similar_pairs: {i}/{n} rows, {time.time() - t0:.0f}s", flush=True)
    if not rows:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64), np.zeros(0)
    return np.concatenate(rows), np.concatenate(cols), np.concatenate(sims)


def cluster_labels(n: int, rows: np.ndarray, cols: np.ndarray, sims: np.ndarray, threshold: float):
    """Single-linkage cluster id (0..k-1) for each of n items, using pairs with sim >= threshold."""
    keep = sims >= threshold
    graph = coo_matrix((np.ones(keep.sum()), (rows[keep], cols[keep])), shape=(n, n))
    _, labels = connected_components(graph, directed=False)
    return labels


def greedy_clusters(
    lengths: np.ndarray, rows: np.ndarray, cols: np.ndarray, sims: np.ndarray, threshold: float
) -> np.ndarray:
    """CD-HIT-style greedy clustering. Returns a cluster id per item (ids are 0..k-1).

    Items are processed longest first (ties by index). The representative of a cluster is its
    first member in that order.
    """
    n = len(lengths)
    keep = sims >= threshold
    r, c = rows[keep], cols[keep]
    # symmetric adjacency in CSR form
    src = np.concatenate([r, c])
    dst = np.concatenate([c, r])
    order_edges = np.argsort(src, kind="stable")
    src, dst = src[order_edges], dst[order_edges]
    starts = np.searchsorted(src, np.arange(n + 1))

    label = np.full(n, -1, dtype=np.int64)
    next_id = 0
    for item in np.lexsort((np.arange(n), -np.asarray(lengths))):  # longest first
        if label[item] >= 0:
            continue
        label[item] = next_id
        nbrs = dst[starts[item] : starts[item + 1]]
        free = nbrs[label[nbrs] < 0]
        label[free] = next_id
        next_id += 1
    return label


def purge_similar(
    split: np.ndarray,
    rows: np.ndarray,
    cols: np.ndarray,
    sims: np.ndarray,
    threshold: float,
    priority: tuple[str, ...] = ("human", "train", "val", "test"),
) -> np.ndarray:
    """Return a boolean mask of items to DROP so that no two kept items from different
    splits have sim >= threshold.

    For every similar pair across two splits, the item in the lower-priority split is dropped
    (priority order: human hold-out, train, val, test), so the human hold-out is never
    reduced and test is reduced first.
    """
    rank = {name: k for k, name in enumerate(priority)}
    keep = sims >= threshold
    a, b = rows[keep], cols[keep]
    ra = np.array([rank[s] for s in split[a]])
    rb = np.array([rank[s] for s in split[b]])
    cross = ra != rb
    a, b, ra, rb = a[cross], b[cross], ra[cross], rb[cross]
    drop = np.zeros(len(split), dtype=bool)
    drop[np.where(ra > rb, a, b)] = True
    return drop
