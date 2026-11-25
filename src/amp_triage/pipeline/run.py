"""The whole pipeline: proteins in, ranked candidate peptides out.

    1. scan     every window of 8-50 residues is scored by the activity model
    2. merge    overlapping windows collapse to one candidate per region (best window kept)
    3. shortlist the best `top_n` candidates continue
    4. check    hemolysis risk (SVM) and novelty (Smith-Waterman against known AMPs)
    5. rank     activity x safety x novelty (pipeline/rank.py)

Steps 4 and 5 only touch the shortlist, so they take seconds; step 1 is the cost: about 23,000
windows per second with the current activity model, so one protein takes about a second and a
whole proteome is an offline job.

Scores and probabilities. The models' raw scores are not probabilities (the activity model's
calibration slope is 0.52). Each candidate therefore carries both:
    activity_score / hemolysis_score   the raw model scores
    activity / hemolysis_risk          calibrated (scripts/calibrate_scores.py)
The calibrated `activity` also depends on an ASSUMED rarity: "if 1 window in 1,000 were an AMP".
The real rarity is unknown; 1 in 1,000 is the setting the calibration was checked at (1 in 100
too; 1 in 10,000 is too noisy to check). Calibration is monotone, so the shortlist and the order
by raw score do not depend on it; the ranking, which multiplies the numbers, does.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import joblib
import numpy as np
import pandas as pd

from amp_triage import config
from amp_triage.candidates.window_features import iter_proteome_chunks
from amp_triage.features.descriptors import FEATURE_NAMES, compute_descriptors
from amp_triage.models.calibration import LogisticRecalibrator, shift_prior
from amp_triage.novelty.reference import load_known_amps
from amp_triage.novelty.search import NoveltyIndex, classify
from amp_triage.pipeline.merge import merge_overlaps
from amp_triage.pipeline.rank import RankSettings, rank_candidates
from amp_triage.pipeline.scan import scan_proteome

DEFAULT_PREVALENCE = 1e-3
OUTPUT_COLUMNS = [
    "rank", "accession", "start", "end", "length", "sequence", "activity_score", "activity",
    "hemolysis_score", "hemolysis_risk", "novelty_class", "max_similarity", "closest_known",
    "closest_id", "rank_score",
]  # fmt: skip
Progress = Callable[[float, str], None]


@dataclass
class Models:
    """Everything the pipeline needs besides the proteins."""

    activity: object  # predict_proba on the 35 descriptors
    hemolysis: object  # predict_proba on the 35 descriptors
    novelty: NoveltyIndex
    related_cutoff: float  # similarity at or above this counts as related (see novelty/search)
    activity_recalibrator: LogisticRecalibrator = field(default_factory=LogisticRecalibrator)
    training_prevalence: float | None = None  # positives' share when the model was trained
    hemolysis_recalibrator: LogisticRecalibrator = field(default_factory=LogisticRecalibrator)

    @classmethod
    def load(cls) -> Models:
        saved = config.MODELS_DIR
        for name in ("activity_calibration.json", "hemolysis_calibration.json"):
            if not (saved / name).exists():
                raise FileNotFoundError(f"{saved / name} missing: run scripts/calibrate_scores.py")
        act = json.loads((saved / "activity_calibration.json").read_text())
        hem = json.loads((saved / "hemolysis_calibration.json").read_text())
        known = load_known_amps()
        calibration = json.loads((config.ROOT / "reports" / "novelty_calibration.json").read_text())
        return cls(
            activity=joblib.load(saved / "activity_final.joblib"),
            hemolysis=joblib.load(saved / "hemolysis_final.joblib"),
            novelty=NoveltyIndex(known.sequence, known.ids),
            related_cutoff=float(calibration["related_cutoff"]),
            activity_recalibrator=LogisticRecalibrator(act["intercept"], act["slope"]),
            training_prevalence=float(act["pi_train"]),
            hemolysis_recalibrator=LogisticRecalibrator(hem["intercept"], hem["slope"]),
        )

    def activity_probability(self, score, prevalence: float = DEFAULT_PREVALENCE) -> np.ndarray:
        """Raw activity score -> calibrated probability if `prevalence` of windows were AMPs."""
        p = self.activity_recalibrator.apply(score)
        if self.training_prevalence is not None:
            p = shift_prior(p, self.training_prevalence, prevalence)
        return p

    def hemolysis_probability(self, score) -> np.ndarray:
        return self.hemolysis_recalibrator.apply(score)


@dataclass
class PipelineResult:
    table: pd.DataFrame  # ranked candidates (OUTPUT_COLUMNS)
    n_proteins: int
    n_windows: int  # valid windows that were scored
    seconds: float
    prevalence: float = DEFAULT_PREVALENCE
    # raw activity score of the best window covering each residue, per shortlisted protein
    profiles: dict[str, list[float]] = field(default_factory=dict)


def _clean(sequence: str) -> str:
    return "".join(sequence.split()).replace("*", "").upper()


def with_prevalence(table: pd.DataFrame, models: Models, prevalence: float) -> pd.DataFrame:
    """Recompute the calibrated `activity` for another assumed rarity (cheap: no rescanning)."""
    out = table.copy()
    out["activity"] = models.activity_probability(out.activity_score.to_numpy(float), prevalence)
    return out


def evaluate_candidates(candidates: pd.DataFrame, models: Models) -> pd.DataFrame:
    """Add hemolysis and novelty columns to merged candidates (needs `sequence`)."""
    out = candidates.copy()
    if out.empty:
        for col in ("hemolysis_score", "hemolysis_risk", "max_similarity"):
            out[col] = pd.Series(dtype=float)
        for col in ("novelty_class", "closest_known", "closest_id"):
            out[col] = pd.Series(dtype=object)
        return out
    X = compute_descriptors(out.sequence.tolist())[FEATURE_NAMES].to_numpy()
    out["hemolysis_score"] = models.hemolysis.predict_proba(X)[:, 1]
    out["hemolysis_risk"] = models.hemolysis_probability(out.hemolysis_score.to_numpy())
    hits = models.novelty.search(out.sequence.tolist())
    out["max_similarity"] = hits.max_similarity.values
    out["closest_known"] = hits.closest_known.values
    out["closest_id"] = hits.closest_id.values
    out["novelty_class"] = [classify(s, models.related_cutoff) for s in hits.max_similarity]
    return out


def run_pipeline(
    accessions: Sequence[str],
    sequences: Sequence[str],
    models: Models,
    top_n: int = 200,
    max_overlap: float = 0.5,
    keep_per_length: int = 2000,
    settings: RankSettings | None = None,
    prevalence: float = DEFAULT_PREVALENCE,
    progress: Progress | None = None,
) -> PipelineResult:
    """Run proteins through the whole pipeline. Accessions must be unique."""
    if len(accessions) != len(sequences):
        raise ValueError("accessions and sequences must have the same length")
    if len(set(accessions)) != len(accessions):
        raise ValueError("protein accessions must be unique")
    started = time.time()
    seqs = [_clean(s) for s in sequences]
    report = progress or (lambda fraction, message: None)

    pools, n_windows, done = [], 0, 0
    profiles: dict[str, np.ndarray] = {}
    total_residues = max(sum(len(s) for s in seqs), 1)
    report(0.0, "scanning windows")
    for chunk in iter_proteome_chunks(accessions, seqs):
        shape = np.zeros(len(chunk.codes), dtype=np.float32)
        hits, n = scan_proteome(
            chunk, models.activity, keep_per_length=keep_per_length, profile=shape
        )
        for i, acc in enumerate(chunk.accessions):
            at, length = int(chunk.starts[i]), int(chunk.lengths[i])
            profiles[acc] = shape[at : at + length]
        pools.append(hits)
        n_windows += n
        done += chunk.n_residues
        report(0.9 * done / total_residues, f"scanned {done:,} of {total_residues:,} residues")
    pool = pd.concat(pools, ignore_index=True) if pools else pd.DataFrame(
        columns=["accession", "start", "length", "activity"]
    )

    report(0.9, "merging overlapping windows")
    merged = merge_overlaps(pool, max_overlap=max_overlap, top_n=top_n)
    by_accession = dict(zip(accessions, seqs, strict=True))
    merged["sequence"] = [
        by_accession[a][s : s + n]
        for a, s, n in zip(merged.accession, merged.start, merged.length, strict=True)
    ]
    merged["end"] = merged.start + merged.length  # 0-based, exclusive
    merged["start"] = merged.start + 1  # shown 1-based, like UniProt
    merged = merged.rename(columns={"activity": "activity_score"})
    raw = merged.activity_score.to_numpy(float)
    merged["activity"] = models.activity_probability(raw, prevalence)

    report(0.93, "hemolysis and novelty checks")
    table = rank_candidates(evaluate_candidates(merged, models), settings)
    table = table.reindex(columns=OUTPUT_COLUMNS)
    report(1.0, "done")
    # only the shortlisted proteins are ever drawn, so only their profiles are worth keeping
    shown = set(table.accession) if not table.empty else set()
    return PipelineResult(
        table=table,
        n_proteins=len(seqs),
        n_windows=n_windows,
        seconds=time.time() - started,
        prevalence=prevalence,
        profiles={a: np.round(profiles[a], 4).tolist() for a in shown if a in profiles},
    )


def read_fasta(path) -> tuple[list[str], list[str]]:
    """Accessions and sequences from a FASTA file (UniProt 'sp|P12345|NAME' ids give P12345)."""
    from Bio import SeqIO

    accs, seqs = [], []
    for rec in SeqIO.parse(str(path), "fasta"):
        parts = rec.id.split("|")
        accs.append(parts[1] if len(parts) >= 2 else rec.id)
        seqs.append(str(rec.seq))
    return accs, seqs
