"""Calibration: when a model says 0.8, is it right 80% of the time?

Tools
* reliability_table: scores sorted into bins; mean predicted score vs share truly positive.
* calibration_fit: logistic regression of the outcome on logit(score). Intercept 0 and slope 1
  mean perfectly calibrated; slope < 1 means over-confident, slope > 1 under-confident.
* brier, expected_calibration_error: single-number summaries (lower is better).
* shift_prior: moves a score from one class balance to another. The activity model trained on
  about 3 positives in 100 windows; a real proteome has far fewer, so its scores are too high for
  real use. Prior shift multiplies the odds by (real odds) / (training odds).
* LogisticRecalibrator: score -> sigmoid(intercept + slope * logit(score)).

`weights` give every row a weight (positives usually 1) so that an evaluation set can stand in
for a different class balance: see `negative_weight`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

EPS = 1e-6
ACTIVITY_EDGES = (0.0, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 1.0001)
EVEN_EDGES = tuple(np.linspace(0.0, 1.0001, 6))  # five equal bins


def _clip(p) -> np.ndarray:
    return np.clip(np.asarray(p, dtype=float), EPS, 1.0 - EPS)


def logit(p) -> np.ndarray:
    p = _clip(p)
    return np.log(p / (1.0 - p))


def sigmoid(z) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.asarray(z, dtype=float)))


def negative_weight(n_pos: float, n_neg: float, prevalence: float) -> float:
    """Weight for each negative so that positives make up `prevalence` of the weighted rows."""
    return n_pos * (1.0 - prevalence) / (prevalence * n_neg)


def shift_prior(p, prevalence_from: float, prevalence_to: float) -> np.ndarray:
    """Rewrite scores for a different share of positives (odds times the odds ratio)."""
    p = _clip(p)
    k = (prevalence_to / (1.0 - prevalence_to)) / (prevalence_from / (1.0 - prevalence_from))
    odds = p / (1.0 - p) * k
    return odds / (1.0 + odds)


def reliability_table(y, p, weights=None, edges=ACTIVITY_EDGES) -> pd.DataFrame:
    """Per score bin: rows, weight, mean predicted score, observed share of positives."""
    y, p = np.asarray(y, dtype=float), np.asarray(p, dtype=float)
    w = np.ones(len(y)) if weights is None else np.asarray(weights, dtype=float)
    bin_of = np.clip(np.digitize(p, edges[1:-1]), 0, len(edges) - 2)
    rows = []
    for b in range(len(edges) - 1):
        m = bin_of == b
        if not m.any():
            continue
        rows.append(
            {
                "low": edges[b],
                "high": min(edges[b + 1], 1.0),
                "n": int(m.sum()),
                "weight": float(w[m].sum()),
                "mean_predicted": float(np.average(p[m], weights=w[m])),
                "observed": float(np.average(y[m], weights=w[m])),
            }
        )
    return pd.DataFrame(rows)


def expected_calibration_error(table: pd.DataFrame) -> float:
    """Weighted mean gap between predicted and observed rate over the bins."""
    gap = (table.mean_predicted - table.observed).abs()
    return float(np.average(gap, weights=table.weight))


def brier(y, p, weights=None) -> float:
    y, p = np.asarray(y, dtype=float), np.asarray(p, dtype=float)
    return float(np.average((p - y) ** 2, weights=weights))


def calibration_fit(y, p, weights=None) -> tuple[float, float]:
    """(intercept, slope) of logit(P(y=1)) = intercept + slope * logit(score)."""
    fit = LogisticRegression(C=1e6, max_iter=2000).fit(
        logit(p).reshape(-1, 1), np.asarray(y, dtype=int), sample_weight=weights
    )
    return float(fit.intercept_[0]), float(fit.coef_[0, 0])


def summarize(y, p, weights=None, edges=ACTIVITY_EDGES) -> dict:
    table = reliability_table(y, p, weights, edges)
    intercept, slope = calibration_fit(y, p, weights)
    return {
        "brier": brier(y, p, weights),
        "ece": expected_calibration_error(table),
        "intercept": intercept,
        "slope": slope,
    }


@dataclass(frozen=True)
class LogisticRecalibrator:
    intercept: float = 0.0
    slope: float = 1.0

    @classmethod
    def fit(cls, y, p, weights=None) -> LogisticRecalibrator:
        return cls(*calibration_fit(y, p, weights))

    def apply(self, p) -> np.ndarray:
        return sigmoid(self.intercept + self.slope * logit(p))


@dataclass(frozen=True)
class ActivityCalibration:
    """Raw activity score -> calibrated probability for an assumed share of AMP windows.

    The same arithmetic the pipeline's `Models.activity_probability` uses, without the heavy
    models, so a server can re-rank saved results (new rarity, new weights) cheaply.
    """

    recalibrator: LogisticRecalibrator = LogisticRecalibrator()
    training_prevalence: float | None = None

    def activity_probability(self, score, prevalence: float) -> np.ndarray:
        p = self.recalibrator.apply(score)
        if self.training_prevalence is not None:
            p = shift_prior(p, self.training_prevalence, prevalence)
        return p

    @classmethod
    def from_json(cls, path) -> ActivityCalibration:
        import json
        from pathlib import Path

        saved = json.loads(Path(path).read_text())
        return cls(LogisticRecalibrator(saved["intercept"], saved["slope"]),
                   float(saved["pi_train"]))
