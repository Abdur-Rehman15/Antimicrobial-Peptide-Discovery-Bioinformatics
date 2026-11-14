"""Fast score-only Smith-Waterman for searching one peptide against thousands of others.

Same recurrences as smith_waterman.py (see its docstring), but it keeps only one row of the
tables, returns just the best score, and is compiled with numba. Targets are scored in
parallel on all CPU cores. tests/test_alignment.py checks that every score equals the
reference implementation's score.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numba import njit, prange

from amp_triage.alignment import blosum62
from amp_triage.alignment.smith_waterman import DEFAULT_GAP_EXTEND, DEFAULT_GAP_OPEN

_NEG = -1.0e18


@njit(cache=True)
def _score_one(a, b, sub, open_ext, ext):
    m = a.shape[0]
    n = b.shape[0]
    H = np.zeros(n + 1)  # H[j] holds the previous row, then is overwritten with the current one
    F = np.full(n + 1, _NEG)  # F[j]: best score ending with a gap in the target, column j
    best = 0.0
    for i in range(1, m + 1):
        diag = 0.0  # H[i-1][j-1]
        h_left = 0.0  # H[i][j-1]
        e = _NEG  # E[i][j-1], then E[i][j]
        ai = a[i - 1]
        for j in range(1, n + 1):
            h_up = H[j]  # H[i-1][j]
            e = max(h_left - open_ext, e - ext)
            f = max(h_up - open_ext, F[j] - ext)
            F[j] = f
            h = diag + sub[ai, b[j - 1]]
            if e > h:
                h = e
            if f > h:
                h = f
            if h < 0.0:
                h = 0.0
            diag = h_up
            H[j] = h
            h_left = h
            if h > best:
                best = h
    return best


@njit(parallel=True, cache=True)
def _score_many(a, flat, offsets, sub, open_ext, ext):
    k = offsets.shape[0] - 1
    out = np.zeros(k)
    for t in prange(k):
        out[t] = _score_one(a, flat[offsets[t] : offsets[t + 1]], sub, open_ext, ext)
    return out


def sw_score(
    query: str,
    target: str,
    gap_open: float = DEFAULT_GAP_OPEN,
    gap_extend: float = DEFAULT_GAP_EXTEND,
) -> float:
    """Best local alignment score of two sequences (score only)."""
    if not query or not target:
        return 0.0
    return float(
        _score_one(
            blosum62.encode(query),
            blosum62.encode(target),
            blosum62.MATRIX.astype(np.float64),
            float(gap_open + gap_extend),
            float(gap_extend),
        )
    )


def sw_scores(
    query: str,
    targets: Sequence[str],
    gap_open: float = DEFAULT_GAP_OPEN,
    gap_extend: float = DEFAULT_GAP_EXTEND,
) -> np.ndarray:
    """Score `query` against every sequence in `targets`, in parallel. Returns float array."""
    if not targets:
        return np.zeros(0)
    if not query:
        return np.zeros(len(targets))
    encoded = [blosum62.encode(t) for t in targets]
    offsets = np.zeros(len(encoded) + 1, dtype=np.int64)
    np.cumsum([len(e) for e in encoded], out=offsets[1:])
    flat = np.concatenate(encoded) if offsets[-1] else np.zeros(0, dtype=np.int64)
    return _score_many(
        blosum62.encode(query),
        flat,
        offsets,
        blosum62.MATRIX.astype(np.float64),
        float(gap_open + gap_extend),
        float(gap_extend),
    )
