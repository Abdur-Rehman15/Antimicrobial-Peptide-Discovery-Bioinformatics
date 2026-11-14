"""Assign whole clusters of similar peptides to train / validation / test / human hold-out.

Rules
* A cluster is never divided, so no peptide in one split is similar (>= the clustering
  threshold) to a peptide in another.
* Any cluster that contains a human-derived peptide goes entirely to the "human" hold-out.
  That keeps human sequences, and their close relatives, out of training and out of model
  selection, so the final human-proteome check is a fair test.
* The remaining clusters are shuffled and dealt out to train / val / test so that each split
  gets its target share of peptides. Clusters containing a natural peptide and synthetic-only
  clusters are dealt separately, so natural peptides (the ones the project cares about) are
  spread evenly over the splits.
"""

from __future__ import annotations

import numpy as np

SPLITS = ("train", "val", "test")


def assign_splits(
    labels: np.ndarray,
    human: np.ndarray,
    natural: np.ndarray,
    fractions: tuple[float, float, float] = (0.70, 0.15, 0.15),
    seed: int = 0,
) -> np.ndarray:
    """Return an array of split names ('train','val','test','human') for each peptide."""
    labels, human, natural = map(np.asarray, (labels, human, natural))
    out = np.empty(len(labels), dtype=object)
    rng = np.random.default_rng(seed)

    ids = np.unique(labels)
    size = {c: int((labels == c).sum()) for c in ids}
    has_human = {c: bool(human[labels == c].any()) for c in ids}
    has_natural = {c: bool(natural[labels == c].any()) for c in ids}

    for c in ids:
        if has_human[c]:
            out[labels == c] = "human"

    for stratum in (True, False):  # clusters with a natural peptide, then synthetic-only
        clusters = [c for c in ids if not has_human[c] and has_natural[c] == stratum]
        rng.shuffle(clusters)
        # biggest first: big clusters are placed while there is still room to balance them
        clusters.sort(key=lambda c: -size[c])
        total = sum(size[c] for c in clusters)
        got = dict.fromkeys(SPLITS, 0)
        for c in clusters:
            # put the cluster where the split is furthest below its target share
            deficit = {s: fractions[k] * total - got[s] for k, s in enumerate(SPLITS)}
            choice = max(deficit, key=lambda s: deficit[s])
            out[labels == c] = choice
            got[choice] += size[c]
    return out
