"""Step 1: score every window of every length with the activity model.

A proteome has hundreds of millions of windows, so only the best `keep_per_length` of each length
are kept (per chunk of the proteome). The rest cannot reach a shortlist of a few hundred anyway.

Passing `profile` also records, for every residue, the best score of any window covering it. That
is the shape of the signal along a protein, which the shortlist alone cannot show: the shortlist
keeps one window per region and says nothing about the quiet stretches between them.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.ndimage import maximum_filter1d

from amp_triage.candidates.window_features import WindowFeatureEngine
from amp_triage.candidates.windows import LENGTHS, Proteome

HIT_COLUMNS = ["accession", "start", "length", "activity"]


def _cover_with_best(profile: np.ndarray, starts: np.ndarray, score: np.ndarray, length: int):
    """Raise `profile[i]` to the best score of any window of `length` covering residue i.

    A window starting at s covers residues s .. s+length-1, so residue i is covered by the
    starts i-length+1 .. i: a trailing sliding maximum over the per-start scores.
    """
    best_at_start = np.full(profile.shape, -np.inf)
    best_at_start[starts] = score
    covered = maximum_filter1d(
        best_at_start,
        size=length,
        origin=(length - 1) - length // 2,  # window [i - length + 1, i]
        mode="constant",
        cval=-np.inf,
    )
    np.maximum(profile, covered, out=profile, where=np.isfinite(covered))


def scan_proteome(
    proteome: Proteome,
    activity_model,
    lengths=LENGTHS,
    keep_per_length: int = 2000,
    profile: np.ndarray | None = None,
) -> tuple[pd.DataFrame, int]:
    """Activity score of the best windows of each length.

    Returns (hits, n_windows): a table with columns accession, start (0-based position in the
    protein), length, activity, and the number of valid windows that were scored.

    `profile`, if given, is an array over the proteome's flat positions that is raised in place
    to the best score covering each residue (before any pruning, so it sees every window).
    """
    engine = WindowFeatureEngine(proteome)
    accessions = np.array(proteome.accessions, dtype=object)
    parts, n_windows = [], 0
    for length in lengths:
        flat_starts, X = engine.descriptors(length)
        if len(flat_starts) == 0:
            continue
        n_windows += len(flat_starts)
        score = activity_model.predict_proba(X)[:, 1]
        if profile is not None:
            _cover_with_best(profile, flat_starts, score, length)
        if len(score) > keep_per_length:
            top = np.argpartition(-score, keep_per_length - 1)[:keep_per_length]
            flat_starts, score = flat_starts[top], score[top]
        pid = proteome.protein_id[flat_starts]
        parts.append(
            pd.DataFrame(
                {
                    "accession": accessions[pid],
                    "start": flat_starts - proteome.starts[pid],
                    "length": length,
                    "activity": score.astype(float),
                }
            )
        )
    hits = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=HIT_COLUMNS)
    return hits, n_windows
