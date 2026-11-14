import numpy as np

from amp_triage.data.splits import assign_splits


def make(n_clusters=300, seed=0):
    rng = np.random.default_rng(seed)
    sizes = rng.integers(1, 12, size=n_clusters)
    labels = np.repeat(np.arange(n_clusters), sizes)
    human = np.zeros(len(labels), dtype=bool)
    for c in rng.choice(n_clusters, size=20, replace=False):
        human[np.nonzero(labels == c)[0][0]] = True  # one human peptide in 20 clusters
    natural = rng.random(len(labels)) < 0.35
    return labels, human, natural


def test_clusters_are_never_split():
    labels, human, natural = make()
    out = assign_splits(labels, human, natural)
    for c in np.unique(labels):
        assert len(set(out[labels == c])) == 1


def test_clusters_with_a_human_peptide_go_to_human_holdout_whole():
    labels, human, natural = make()
    out = assign_splits(labels, human, natural)
    human_clusters = np.unique(labels[human])
    assert all((out[labels == c] == "human").all() for c in human_clusters)
    assert (out[~np.isin(labels, human_clusters)] != "human").all()


def test_every_peptide_gets_a_split():
    labels, human, natural = make()
    assert set(assign_splits(labels, human, natural)) <= {"train", "val", "test", "human"}


def test_shares_are_close_to_the_targets_overall_and_for_natural_peptides():
    labels, human, natural = make(n_clusters=1500)
    out = assign_splits(labels, human, natural, fractions=(0.70, 0.15, 0.15))
    rest = out != "human"
    for split, share in (("train", 0.70), ("val", 0.15), ("test", 0.15)):
        assert abs((out[rest] == split).mean() - share) < 0.02
        nat = natural & rest
        assert abs((out[nat] == split).mean() - share) < 0.03


def test_deterministic_for_a_seed_and_changes_with_it():
    labels, human, natural = make()
    a = assign_splits(labels, human, natural, seed=1)
    assert (a == assign_splits(labels, human, natural, seed=1)).all()
    assert (a != assign_splits(labels, human, natural, seed=2)).any()
