import numpy as np
import pandas as pd
import pytest

from amp_triage.data.datasets import (
    META,
    activity_metadata,
    build_hemolysis_metadata,
    validate_activity,
    validate_hemolysis,
    with_descriptors,
)
from amp_triage.features.descriptors import FEATURE_NAMES

AA = "ACDEFGHIKLMNPQRSTVWY"


def random_seqs(n, seed, lo=8, hi=30, bias=""):
    rng = np.random.default_rng(seed)
    letters = np.array(list(AA + bias))
    out = set()
    while len(out) < n:
        out.add("".join(rng.choice(letters, size=rng.integers(lo, hi))))
    return sorted(out)


def make_activity(seed=0):
    pos_seqs = random_seqs(60, seed, bias="KKRRLL")
    neg_seqs = random_seqs(300, seed + 1)
    pos = pd.DataFrame(
        {
            "sequence": pos_seqs,
            "origin": ["natural"] * 30 + ["synthetic"] * 30,
            "cluster": range(60),
            "split": ["train"] * 30 + ["val"] * 10 + ["test"] * 10 + ["human"] * 10,
        }
    )
    splits = ["train"] * 180 + ["val"] * 60 + ["test"] * 60
    neg = pd.DataFrame(
        {
            "sequence": neg_seqs,
            "split": splits,
            "accession": [f"Q{i // 5:04d}" for i in range(300)],  # 5 windows per protein
        }
    )
    return pos, neg


def test_activity_dataset_layout_and_validation_pass():
    pos, neg = make_activity()
    df = with_descriptors(activity_metadata(pos, neg))
    assert list(df.columns) == META + FEATURE_NAMES
    assert len(df) == 360 and df.label.sum() == 60
    validate_activity(df, set(pos.sequence))


def test_dropped_similar_positives_are_left_out():
    pos, neg = make_activity()
    pos.loc[:4, "split"] = "dropped_similar"
    meta = activity_metadata(pos, neg)
    assert "dropped_similar" not in set(meta.split) and meta.label.sum() == 55


def test_validation_catches_each_kind_of_breakage():
    pos, neg = make_activity()
    good = with_descriptors(activity_metadata(pos, neg))
    positives = set(pos.sequence)

    dup = pd.concat([good, good.iloc[[0]]], ignore_index=True)
    with pytest.raises(AssertionError, match="duplicated"):
        validate_activity(dup, positives)

    bad = good.copy()
    bad.loc[0, "net_charge"] = np.nan
    with pytest.raises(AssertionError, match="missing"):
        validate_activity(bad, positives)

    human_neg = good.copy()
    i = human_neg.index[(human_neg.label == 0)][0]
    human_neg.loc[i, "split"] = "human"
    with pytest.raises(AssertionError, match="human"):
        validate_activity(human_neg, positives)

    two_splits = good.copy()
    prot = two_splits[two_splits.label == 0].group.iloc[0]
    rows = two_splits.index[two_splits.group == prot]
    two_splits.loc[rows[0], "split"] = "test"
    with pytest.raises(AssertionError, match="more than one split"):
        validate_activity(two_splits, positives)

    with pytest.raises(AssertionError, match="7-mer"):
        leaky = good.copy()
        j = leaky.index[leaky.label == 0][0]
        # a negative that contains a 12-residue stretch of a known AMP
        leaky.loc[j, "sequence"] = "WWWW" + pos.sequence.iloc[0][:12]
        validate_activity(leaky, positives)


def make_happenn(n=240, seed=0):
    rng = np.random.default_rng(seed)
    seqs = random_seqs(n, seed + 5, lo=10, hi=30)
    hemo = rng.random(n) < 0.45
    return pd.DataFrame(
        {
            "sequence": seqs,
            "hemolytic": hemo.astype(int),
            "length": [len(s) for s in seqs],
            "in_rr90": True,
            "n_ter_flag": False,
            "c_ter_flag": rng.random(n) < 0.5,
        }
    )


def test_hemolysis_split_has_all_splits_and_both_classes_and_validates():
    meta, dropped = build_hemolysis_metadata(make_happenn())
    assert {"train", "val", "test"} <= set(meta.split)
    df = with_descriptors(meta)
    validate_hemolysis(df)
    assert dropped >= 0
    assert abs((meta.split == "train").mean() - 0.7) < 0.1


def test_hemolysis_ignores_peptides_outside_rr90():
    h = make_happenn()
    h.loc[:19, "in_rr90"] = False
    meta, _ = build_hemolysis_metadata(h)
    assert not set(h.sequence[:20]) & set(meta.sequence)
