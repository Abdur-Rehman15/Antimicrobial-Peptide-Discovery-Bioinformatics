import numpy as np
import pytest

from amp_triage.candidates.stage1 import (
    Stage1Model,
    peptide_features,
    threshold_for_recall,
    train_stage1,
)
from amp_triage.candidates.windows import Proteome
from amp_triage.features import descriptors as D


def random_seqs(n, seed, lo=8, hi=50, bias=""):
    rng = np.random.default_rng(seed)
    letters = np.array(list(D.AA + bias))
    return ["".join(rng.choice(letters, size=rng.integers(lo, hi + 1))) for _ in range(n)]


def test_peptide_features_layout_and_values():
    x = peptide_features(["KKAA"])
    assert x.shape == (1, 22)
    assert x[0, D.AA.index("K")] == 0.5 and x[0, D.AA.index("A")] == 0.5
    assert x[0, 20] == 4
    assert x[0, 21] == pytest.approx(D.descriptors("KKAA")["net_charge"])


def test_train_separates_cationic_from_ordinary():
    pos = random_seqs(300, 1, bias="KKKRRLLL")  # enriched in K, R, L
    neg = random_seqs(600, 2)
    model = train_stage1(pos, neg)
    s_pos, s_neg = model.scores(pos), model.scores(neg)
    assert s_pos.mean() > s_neg.mean() + 1.0
    auc = (s_pos[:, None] > s_neg[None, :]).mean()
    assert auc > 0.9


def test_window_scores_equal_scoring_each_window_as_a_peptide():
    model = train_stage1(random_seqs(200, 3, bias="KKRR"), random_seqs(400, 4))
    rng = np.random.default_rng(5)
    seqs = ["".join(rng.choice(list(D.AA), size=rng.integers(20, 90))) for _ in range(12)]
    prot = Proteome.from_sequences([f"P{i}" for i in range(12)], seqs)
    for length in (8, 15, 33):
        starts, _, score = model.window_scores(prot, length)
        for k in rng.choice(len(starts), size=min(40, len(starts)), replace=False):
            peptide = prot.sequence_at(starts[k], length)
            assert score[k] == pytest.approx(model.scores([peptide])[0], abs=1e-8)


def test_threshold_keeps_the_requested_recall():
    scores = np.linspace(0, 1, 1000)
    t = threshold_for_recall(scores, 0.95)
    assert (scores >= t).mean() >= 0.95
    assert (scores >= t).mean() < 0.96


def test_model_round_trips_through_json(tmp_path):
    model = train_stage1(random_seqs(100, 6, bias="KKRR"), random_seqs(200, 7))
    model.threshold = -0.25
    f = tmp_path / "m.json"
    model.save(f)
    loaded = Stage1Model.load(f)
    seqs = random_seqs(20, 8)
    assert np.allclose(model.scores(seqs), loaded.scores(seqs))
    assert loaded.threshold == -0.25
