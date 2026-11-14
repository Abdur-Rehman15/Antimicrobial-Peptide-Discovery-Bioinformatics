"""How close is a candidate to the closest known AMP?

similarity(a, b) = SW(a, b) / min(SW(a, a), SW(b, b))

where SW is the Smith-Waterman local alignment score (BLOSUM62, affine gaps). It runs from 0 to 1:
1 means one peptide is (a fragment of) the other, near 0 means nothing in common. Dividing by the
SHORTER peptide's self-score makes a candidate that is a piece of a longer known AMP score 1,
which is right: a piece of a known AMP is not a discovery.

`NoveltyIndex(reference).search(candidates)` returns, for every candidate, its highest
similarity to any reference peptide and which one that was. The full alignment of a pair (for the
dashboard) comes from `alignment()`, which uses the slow reference implementation on that one pair.

Novelty is 1 - max similarity. `classify` gives a label from two cut-offs:
  * "known":   similarity >= KNOWN (0.99). The candidate is identical to a known AMP or a piece
               of one (a perfect local match).
  * "related": similarity >= `related_cutoff`, a MEASURED chance level
               (scripts/calibrate_novelty.py). Every candidate is compared with ~17,000 peptides
               and keeps its best match, so chance alone produces fairly high values; the cut-off
               is the 99th percentile of what AMP-like non-AMP windows reach.
  * "novel":   below that.
The 0.7 rule used for the dataset splits is a rule for single pairs and does not apply here.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from amp_triage.alignment import Alignment, smith_waterman
from amp_triage.alignment.fast import EncodedSet, sw_score

KNOWN = 0.99  # a perfect local match: identical to, or a piece of, a known AMP


class NoveltyIndex:
    """A reference set of known peptides, ready to be searched with many candidates."""

    def __init__(self, reference: Sequence[str], ids: Sequence[str] | None = None):
        self.sequences = list(reference)
        self.ids = list(ids) if ids is not None else [""] * len(self.sequences)
        if len(self.ids) != len(self.sequences):
            raise ValueError("ids must have one entry per reference sequence")
        self._set = EncodedSet(self.sequences)
        self._self = self._set.self_scores()

    def __len__(self) -> int:
        return len(self.sequences)

    def similarities(self, candidate: str) -> np.ndarray:
        """Similarity (0 to 1) of one candidate to every reference peptide."""
        own = sw_score(candidate, candidate)
        if own == 0:
            return np.zeros(len(self))
        raw = self._set.scores_for(candidate)
        return raw / np.minimum(own, self._self)

    def search(self, candidates: Sequence[str], exclude_identical: bool = False) -> pd.DataFrame:
        """Highest similarity to the reference for each candidate.

        `exclude_identical` ignores a reference entry that is exactly the candidate. It is for
        measuring how close a known peptide is to the REST of the reference.
        """
        best_sim, best_idx = [], []
        for cand in candidates:
            sims = self.similarities(cand)
            if exclude_identical:
                sims = np.where(np.array(self.sequences) == cand, -1.0, sims)
            k = int(np.argmax(sims)) if len(sims) else -1
            best_sim.append(float(sims[k]) if k >= 0 else 0.0)
            best_idx.append(k)
        return pd.DataFrame(
            {
                "candidate": list(candidates),
                "max_similarity": best_sim,
                "novelty": 1.0 - np.array(best_sim),
                "closest_known": [self.sequences[k] if k >= 0 else "" for k in best_idx],
                "closest_id": [self.ids[k] if k >= 0 else "" for k in best_idx],
            }
        )

    def alignment(self, candidate: str, known: str) -> Alignment:
        """Full alignment of a candidate against one known peptide (for display)."""
        return smith_waterman(candidate, known)


def classify(similarity: float, related_cutoff: float) -> str:
    """'known' (identical to / part of a known AMP), 'related' (above chance) or 'novel'."""
    if similarity >= KNOWN:
        return "known"
    if similarity >= related_cutoff:
        return "related"
    return "novel"
