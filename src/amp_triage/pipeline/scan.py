"""Step 1: score every window of every length with the activity model.

A proteome has hundreds of millions of windows, so only the best `keep_per_length` of each length
are kept (per chunk of the proteome). The rest cannot reach a shortlist of a few hundred anyway.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from amp_triage.candidates.window_features import WindowFeatureEngine
from amp_triage.candidates.windows import LENGTHS, Proteome

HIT_COLUMNS = ["accession", "start", "length", "activity"]


def scan_proteome(
    proteome: Proteome,
    activity_model,
    lengths=LENGTHS,
    keep_per_length: int = 2000,
) -> tuple[pd.DataFrame, int]:
    """Activity score of the best windows of each length.

    Returns (hits, n_windows): a table with columns accession, start (0-based position in the
    protein), length, activity, and the number of valid windows that were scored.
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
