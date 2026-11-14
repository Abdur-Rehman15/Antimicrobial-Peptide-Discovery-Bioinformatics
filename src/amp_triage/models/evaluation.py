"""Metrics for the activity classifier.

The val/test sets hold 100 random windows for every real peptide, far more peptides than the
real world has AMPs, so plain precision would be misleading. Instead we fix a false-positive rate
on the negatives and report what it means at a chosen real-world rarity:

    precision = recall * p / (recall * p + fpr * (1 - p))     (p = share of windows that are AMPs)

`recall` and `fpr` are measured on the evaluation set; `p` is a stated assumption.
"""

from __future__ import annotations

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

FPR_LEVELS = (1e-3, 1e-4)
PREVALENCES = (1e-2, 1e-3, 1e-4)


def precision_at_prevalence(recall: float, fpr: float, prevalence: float) -> float:
    """Expected precision when `prevalence` of all windows are true AMPs."""
    tp = recall * prevalence
    fp = fpr * (1.0 - prevalence)
    return float(tp / (tp + fp)) if tp + fp > 0 else float("nan")


def recall_at_fpr(
    pos_scores: np.ndarray,
    neg_scores: np.ndarray,
    fpr: float,
    neg_weight: np.ndarray | None = None,
) -> tuple[float, float]:
    """(recall, actual fpr) when the threshold lets about `fpr` of negatives through.

    Ties can make the actual false-positive rate lower than asked, so it is returned too.
    `neg_weight` counts some negatives more than others (used when pooled sets have different
    negatives-per-positive ratios); the false-positive rate is then a weighted share.
    """
    if neg_weight is None:
        thr = np.quantile(neg_scores, 1.0 - fpr)
        return float(np.mean(pos_scores > thr)), float(np.mean(neg_scores > thr))
    values, inverse = np.unique(neg_scores, return_inverse=True)
    weight_at = np.bincount(inverse, weights=neg_weight)
    total = weight_at.sum()
    above = total - np.cumsum(weight_at)  # weight of negatives strictly above each value
    i = int(np.argmax(above / total <= fpr))  # first value that lets <= fpr through
    return float(np.mean(pos_scores > values[i])), float(above[i] / total)


def summarize(y: np.ndarray, score: np.ndarray, neg_weight: np.ndarray | None = None) -> dict:
    """All headline numbers for one set of positives (y=1) against negatives (y=0).

    `neg_weight` (one value per row; positives are always weight 1) makes every number reflect
    a chosen negatives-per-positive ratio.
    """
    y = np.asarray(y)
    score = np.asarray(score, dtype=float)
    pos, neg = score[y == 1], score[y == 0]
    if neg_weight is None:
        row_weight, neg_w = None, None
    else:
        row_weight = np.where(y == 1, 1.0, np.asarray(neg_weight, dtype=float))
        neg_w = row_weight[y == 0]
    out = {
        "n_pos": int(len(pos)),
        "n_neg": int(len(neg)),
        "roc_auc": float(roc_auc_score(y, score, sample_weight=row_weight)),
        "pr_auc": float(average_precision_score(y, score, sample_weight=row_weight)),
    }
    for fpr in FPR_LEVELS:
        rec, actual = recall_at_fpr(pos, neg, fpr, neg_w)
        out[f"recall@fpr={fpr:g}"] = rec
        out[f"actual_fpr@{fpr:g}"] = actual
        for p in PREVALENCES:
            out[f"precision@fpr={fpr:g},p={p:g}"] = precision_at_prevalence(rec, actual, p)
    return out


def summarize_by_origin(
    y: np.ndarray, score: np.ndarray, origin: np.ndarray, neg_weight: np.ndarray | None = None
) -> dict:
    """`summarize` for all positives, and for natural and synthetic positives separately.

    Every group is scored against the same negatives.
    """
    y, score, origin = map(np.asarray, (y, score, origin))
    w = None if neg_weight is None else np.asarray(neg_weight, dtype=float)
    result = {"all": summarize(y, score, w)}
    for kind in ("natural", "synthetic"):
        keep = (y == 0) | (origin == kind)
        result[kind] = summarize(y[keep], score[keep], None if w is None else w[keep])
    return result
