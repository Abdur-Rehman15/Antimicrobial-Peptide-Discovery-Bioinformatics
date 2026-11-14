"""Step 2: merge overlapping windows into one candidate per region.

One real peptide is scored many times (residues 40-60, 41-60, 40-61, ...). Without merging the
top of the list would be dozens of near-copies. This is greedy non-maximum suppression:

  1. sort windows by activity, best first;
  2. keep the best window, drop every window of the same protein that overlaps it by more than
     `max_overlap` (a share of the SHORTER of the two windows);
  3. repeat with the best window that is left.

The kept window is a real fragment of the protein, so it can be scored by the later steps.
"""

from __future__ import annotations

import pandas as pd


def merge_overlaps(
    hits: pd.DataFrame, max_overlap: float = 0.5, top_n: int | None = None
) -> pd.DataFrame:
    """Best window of each region. `hits` needs columns accession, start, length, activity.

    Stops after `top_n` windows are kept (they come out best first). Ties in activity keep the
    row order of `hits`, so the result is deterministic.
    """
    if not 0.0 <= max_overlap <= 1.0:
        raise ValueError("max_overlap must be between 0 and 1")
    ordered = hits.sort_values("activity", ascending=False, kind="stable")
    kept_intervals: dict[str, list[tuple[int, int]]] = {}
    kept_index = []
    for idx, acc, start, length in zip(
        ordered.index, ordered.accession, ordered.start, ordered.length, strict=True
    ):
        end = start + length
        intervals = kept_intervals.setdefault(acc, [])
        overlaps = False
        for s, e in intervals:
            inter = min(end, e) - max(start, s)
            if inter > 0 and inter / min(length, e - s) > max_overlap:
                overlaps = True
                break
        if overlaps:
            continue
        intervals.append((start, end))
        kept_index.append(idx)
        if top_n is not None and len(kept_index) >= top_n:
            break
    return ordered.loc[kept_index].reset_index(drop=True)
