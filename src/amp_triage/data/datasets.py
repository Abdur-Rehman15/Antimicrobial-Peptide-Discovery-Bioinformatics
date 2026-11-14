"""Assemble the two training datasets (activity and hemolysis) with all 35 descriptors.

Activity dataset  (data/processed/activity_dataset.csv)
    label 1: the cleaned active peptides, in their train / val / test / human splits
    label 0: random windows from non-human, non-antimicrobial proteins, in train / val / test
    Splits for positives come from clustering (scripts/build_splits.py); negatives are split by
    protein. `group` is a cluster id (positives) or a protein accession (negatives): use it for
    grouped cross-validation so related rows never straddle a fold.

Hemolysis dataset (data/processed/hemolysis_dataset.csv)
    HAPPENN-RR90 (823 hemolytic, 1,100 non-hemolytic). Split by similarity here, in the same way
    as the positives, and purged so no similar pair crosses two splits.

`validate_*` raise AssertionError with a clear message if a dataset breaks a rule; they run at
the end of every build.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from amp_triage.data.clustering import greedy_clusters, purge_similar, similar_pairs
from amp_triage.data.negatives import kmer_set, shares_kmer
from amp_triage.data.splits import assign_splits
from amp_triage.features.descriptors import FEATURE_NAMES, compute_descriptors

SIM_THRESHOLD = 0.7
META = ["sequence", "label", "split", "origin", "group"]


def with_descriptors(meta: pd.DataFrame) -> pd.DataFrame:
    """Append the 35 descriptor columns (computed from `sequence`) to a metadata frame."""
    feats = compute_descriptors(meta["sequence"]).drop(columns="sequence")
    return pd.concat([meta.reset_index(drop=True), feats.reset_index(drop=True)], axis=1)


def activity_metadata(positives_split: pd.DataFrame, negatives: pd.DataFrame) -> pd.DataFrame:
    """Combine positives (split table from build_splits) and sampled negatives."""
    pos = positives_split[positives_split.split.isin(["train", "val", "test", "human"])]
    pos = pd.DataFrame(
        {
            "sequence": pos.sequence.values,
            "label": 1,
            "split": pos.split.values,
            "origin": pos.origin.values,  # natural / synthetic
            "group": "c" + pos.cluster.astype(str).values,
        }
    )
    neg = pd.DataFrame(
        {
            "sequence": negatives.sequence.values,
            "label": 0,
            "split": negatives.split.values,
            "origin": "random_window",
            "group": negatives.accession.values,
        }
    )
    return pd.concat([pos, neg], ignore_index=True)


def validate_common(df: pd.DataFrame) -> None:
    assert list(df.columns[: len(META)]) == META, "metadata columns changed"
    assert list(df.columns[len(META) :]) == FEATURE_NAMES, "feature columns changed"
    assert df.label.isin([0, 1]).all(), "labels must be 0 or 1"
    bad = df[FEATURE_NAMES].isna().sum().sum()
    assert bad == 0, f"{bad} missing feature values"
    assert np.isfinite(df[FEATURE_NAMES].to_numpy()).all(), "non-finite feature values"
    dup = df.sequence.duplicated()
    assert not dup.any(), f"{dup.sum()} duplicated sequences (e.g. {df.sequence[dup].iloc[0]})"


def validate_activity(df: pd.DataFrame, positive_sequences: set[str]) -> None:
    validate_common(df)
    assert set(df.split) <= {"train", "val", "test", "human"}
    human = df[df.split == "human"]
    assert (human.label == 1).all(), "the human split must contain positives only"
    banned = kmer_set(positive_sequences)
    neg = df[df.label == 0]
    leaking = neg.sequence[neg.sequence.apply(lambda s: shares_kmer(s, banned))]
    assert leaking.empty, f"{len(leaking)} negatives share a 7-mer with a known AMP"
    assert not neg.sequence.isin(positive_sequences).any(), "a negative equals a positive"
    prot_split = neg.groupby("group").split.nunique()
    assert (prot_split == 1).all(), "a protein feeds more than one split"
    for split in ("train", "val", "test"):
        part = df[df.split == split]
        assert part.label.nunique() == 2, f"{split} needs both classes"


def build_hemolysis_metadata(
    happenn: pd.DataFrame, seed: int = 0
) -> tuple[pd.DataFrame, int]:
    """HAPPENN-RR90 peptides, split by similarity, purged, with the split guarantee verified.

    Returns (metadata of the kept peptides, number dropped for being too similar).
    """
    rr = happenn[happenn.in_rr90].drop_duplicates("sequence").reset_index(drop=True)
    seqs = rr.sequence.tolist()
    i, j, s = similar_pairs(seqs, min_sim=0.3, verbose=False)
    cluster = greedy_clusters(rr.length.values, i, j, s, SIM_THRESHOLD)
    hemolytic = (rr.hemolytic == 1).values
    # stratify by class: the "natural" stratum of assign_splits is used for hemolytic peptides
    split = assign_splits(cluster, np.zeros(len(rr), bool), hemolytic, seed=seed)
    drop = purge_similar(split, i, j, s, SIM_THRESHOLD)
    final = np.where(drop, "dropped_similar", split)
    crossing = (s >= SIM_THRESHOLD) & (final[i] != final[j]) & ~drop[i] & ~drop[j]
    assert not crossing.any(), f"{crossing.sum()} similar pairs cross splits"
    meta = pd.DataFrame(
        {
            "sequence": rr.sequence,
            "label": rr.hemolytic.astype(int),
            "split": final,
            "origin": np.where(rr.hemolytic == 1, "hemolytic", "non_hemolytic"),
            "group": "c" + pd.Series(cluster).astype(str),
            "n_ter_flag": rr.n_ter_flag.astype(int),
            "c_ter_flag": rr.c_ter_flag.astype(int),
        }
    )
    return meta[meta.split != "dropped_similar"].reset_index(drop=True), int(drop.sum())


def validate_hemolysis(df: pd.DataFrame) -> None:
    extra = ["n_ter_flag", "c_ter_flag"]
    validate_common(df.drop(columns=extra).copy())
    assert set(df.split) <= {"train", "val", "test"}
    for split in ("train", "val", "test"):
        part = df[df.split == split]
        assert part.label.nunique() == 2, f"{split} needs both classes"
