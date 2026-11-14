import numpy as np
import pytest

from amp_triage.alignment import sw_score
from amp_triage.alignment.fast import EncodedSet
from amp_triage.data.clustering import cluster_labels, similar_pairs

A = "GIGKFLHSAKKFGKAFVGEIMNS"  # magainin 2
A_PADDED = "AAAAAAAAAA" + A  # a padded copy, as seen in DBAASP
B = "LLGDFFRKSKEKIGKEFKRIVQRIKDFLRNLVPRTES"  # LL-37, unrelated to A
B_FRAG = B[5:30]  # a fragment of B
C = "WWWWPPPPCCCCNNNNQQQQ"  # something else entirely


def test_encoded_set_scores_equal_one_at_a_time():
    seqs = [A, B, C, A_PADDED, B_FRAG]
    enc = EncodedSet(seqs)
    for i in range(len(seqs)):
        got = enc.scores_against(i, first=0)
        want = [sw_score(seqs[i], s) for s in seqs]
        assert got.tolist() == want
    assert enc.self_scores().tolist() == [sw_score(s, s) for s in seqs]


def test_scores_against_a_later_subset():
    seqs = [A, B, C, A_PADDED]
    enc = EncodedSet(seqs)
    got = enc.scores_against(0, first=2)
    assert got.tolist() == [sw_score(A, C), sw_score(A, A_PADDED)]


def test_contained_peptide_has_similarity_one():
    seqs = [A, A_PADDED, B, B_FRAG, C]
    i, j, s = similar_pairs(seqs, min_sim=0.3, verbose=False)
    pairs = {(a, b): v for a, b, v in zip(i, j, s, strict=True)}
    assert pairs[(0, 1)] == pytest.approx(1.0)  # A inside its padded copy
    assert pairs[(2, 3)] == pytest.approx(1.0)  # fragment inside LL-37
    assert (0, 2) not in pairs and (0, 4) not in pairs  # unrelated pairs stay apart


def test_clusters_group_variants_and_separate_unrelated():
    seqs = [A, A_PADDED, B, B_FRAG, C]
    i, j, s = similar_pairs(seqs, min_sim=0.3, verbose=False)
    labels = cluster_labels(len(seqs), i, j, s, threshold=0.5)
    assert labels[0] == labels[1] and labels[2] == labels[3]
    assert len({labels[0], labels[2], labels[4]}) == 3


def test_no_pairs_gives_singletons():
    labels = cluster_labels(3, np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64),
                            np.zeros(0), threshold=0.5)
    assert sorted(labels) == [0, 1, 2]


def test_chain_links_into_one_cluster_even_if_ends_differ():
    # A-B similar, B-C similar, A-C not: single linkage joins all three
    labels = cluster_labels(3, np.array([0, 1]), np.array([1, 2]), np.array([0.9, 0.9]), 0.5)
    assert labels[0] == labels[1] == labels[2]


# ---- greedy clustering and purging -------------------------------------------------------

from amp_triage.data.clustering import greedy_clusters, purge_similar  # noqa: E402


def test_greedy_clusters_longest_peptide_claims_its_neighbours():
    lengths = np.array([10, 30, 20, 25])
    # item 1 (longest) is similar to 0 and 2; item 3 is similar only to 2
    rows, cols, sims = np.array([0, 1, 2]), np.array([1, 2, 3]), np.array([0.9, 0.8, 0.7])
    lab = greedy_clusters(lengths, rows, cols, sims, threshold=0.5)
    assert lab[0] == lab[1] == lab[2]  # 1 claims 0 and 2
    assert lab[3] != lab[1]  # 3 was only linked through 2, which is not a representative


def test_greedy_clusters_do_not_chain_like_single_linkage():
    lengths = np.array([30, 25, 20])
    rows, cols, sims = np.array([0, 1]), np.array([1, 2]), np.array([0.9, 0.9])  # 0-1, 1-2
    lab = greedy_clusters(lengths, rows, cols, sims, threshold=0.5)
    assert lab[0] == lab[1] and lab[2] != lab[0]
    single = cluster_labels(3, rows, cols, sims, 0.5)
    assert single[0] == single[1] == single[2]  # single linkage would join all three


def test_greedy_threshold_is_respected():
    lab = greedy_clusters(np.array([20, 20]), np.array([0]), np.array([1]), np.array([0.45]), 0.5)
    assert lab[0] != lab[1]


def test_purge_drops_the_lower_priority_side_of_cross_split_pairs():
    split = np.array(["train", "test", "val", "human", "train"], dtype=object)
    rows, cols = np.array([0, 2, 3, 0]), np.array([1, 3, 4, 4])
    sims = np.full(4, 0.9)
    drop = purge_similar(split, rows, cols, sims, threshold=0.5)
    # (train0,test1)->drop test1; (val2,human3)->drop val2; (human3,train4)->drop train4;
    # (train0,train4) same split -> nothing
    assert drop.tolist() == [False, True, True, False, True]


def test_purge_ignores_pairs_below_threshold():
    split = np.array(["train", "test"], dtype=object)
    assert not purge_similar(split, np.array([0]), np.array([1]), np.array([0.4]), 0.5).any()
