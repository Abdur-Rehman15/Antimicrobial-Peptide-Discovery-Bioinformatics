"""Stage 1 of the two-stage search: a fast screen that must not lose real AMPs.

Why a screen at all: a proteome has about 466 million windows of 8-50 residues, far too many
to describe fully and score with the main model. Stage 1 uses only quantities that can be read
off running totals (amino-acid fractions, length, net charge), so it can score every window in
about a minute, and drops the windows that are clearly not antimicrobial.

Why not a hard charge/hydrophobicity gate (as first proposed): any single-number gate that
keeps most real AMPs also keeps most windows, and a gate that removes most windows loses a
large share of natural AMPs (see docs/DECISIONS.md). A weighted combination of several cheap
features is a better screen at the same recall.

The threshold is chosen by RECALL on validation peptides that were not used for training, not
by accuracy: stage 1 may let junk through (stage 2 removes it) but must not drop real AMPs.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

from amp_triage.features import descriptors as D

FEATURE_NAMES = [f"aac_{a}" for a in D.AA] + ["length", "net_charge"]


def peptide_features(sequences: Sequence[str], ph: float = D.PH_BLOOD) -> np.ndarray:
    """Feature matrix (n, 22): 20 amino-acid fractions, length, net charge."""
    rows = []
    for s in sequences:
        codes = D.encode(s)
        counts = np.bincount(codes, minlength=20)
        rows.append([*(counts / len(codes)), float(len(codes)), D.charge_at_ph(counts, ph)])
    return np.array(rows)


@dataclass
class Stage1Model:
    """A linear screen: score = intercept + w . [fractions, length, charge].

    Higher means more AMP-like. Windows with score >= threshold pass.
    """

    aac_weights: list[float]
    length_weight: float
    charge_weight: float
    intercept: float
    threshold: float = -1.0e18  # lets everything through until calibrated
    ph: float = D.PH_BLOOD

    def scores(self, sequences: Sequence[str]) -> np.ndarray:
        x = peptide_features(sequences, self.ph)
        w = np.array([*self.aac_weights, self.length_weight, self.charge_weight])
        return x @ w + self.intercept

    def passes(self, sequences: Sequence[str]) -> np.ndarray:
        return self.scores(sequences) >= self.threshold

    def window_scores(self, proteome, length: int):
        """(starts, charge, score) for every valid window of `length` in a Proteome."""
        return proteome.linear_scores(
            np.array(self.aac_weights),
            self.length_weight,
            self.charge_weight,
            self.intercept,
            length,
            self.ph,
        )

    def save(self, path: Path) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2) + "\n")

    @classmethod
    def load(cls, path: Path) -> Stage1Model:
        return cls(**json.loads(Path(path).read_text()))


def train_stage1(
    positives: Sequence[str], negatives: Sequence[str], c: float = 1.0, seed: int = 0
) -> Stage1Model:
    """Fit the linear screen. Classes are balanced so the many negatives do not swamp the AMPs.

    Features are standardised for fitting, then the scaling is folded back into the weights so
    the saved model works directly on raw fractions, length and charge.
    """
    x = np.vstack([peptide_features(positives), peptide_features(negatives)])
    y = np.r_[np.ones(len(positives)), np.zeros(len(negatives))]
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale == 0] = 1.0
    clf = LogisticRegression(C=c, class_weight="balanced", max_iter=2000, random_state=seed)
    clf.fit((x - mean) / scale, y)
    w = clf.coef_[0] / scale
    intercept = float(clf.intercept_[0] - (clf.coef_[0] * mean / scale).sum())
    return Stage1Model(
        aac_weights=[float(v) for v in w[:20]],
        length_weight=float(w[20]),
        charge_weight=float(w[21]),
        intercept=intercept,
    )


def threshold_for_recall(positive_scores: np.ndarray, recall: float) -> float:
    """Largest threshold that still keeps at least `recall` of the given positive scores."""
    scores = np.sort(np.asarray(positive_scores))
    k = int(np.floor((1.0 - recall) * len(scores)))  # how many may be lost
    return float(scores[k])
