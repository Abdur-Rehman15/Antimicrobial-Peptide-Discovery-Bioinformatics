import numpy as np
import pytest

from amp_triage.alignment import sw_score, sw_scores
from amp_triage.alignment.fast import EncodedSet
from amp_triage.novelty.search import KNOWN, NoveltyIndex, classify

MAGAININ = "GIGKFLHSAKKFGKFGKAFVGEIMNS"
REFERENCE = [
    MAGAININ,
    "KWKLFKKIEKVGQNIRDGIIKAGPAVAVVGQATQIAK",
    "ILPWKWPWWPWRR",
    "GLFDIVKKVVGALGSL",
]


def test_scores_for_matches_the_one_by_one_scores():
    enc = EncodedSet(REFERENCE)
    query = "KFLHSAKKFGKAF"
    expected = [sw_score(query, t) for t in REFERENCE]
    assert enc.scores_for(query) == pytest.approx(expected)
    assert enc.scores_for(query) == pytest.approx(sw_scores(query, REFERENCE))


def test_scores_for_empty_query_or_set():
    assert EncodedSet(REFERENCE).scores_for("").tolist() == [0.0] * 4
    assert len(EncodedSet([]).scores_for("AAAA")) == 0


def test_identical_peptide_has_similarity_one():
    sims = NoveltyIndex(REFERENCE).similarities(MAGAININ)
    assert sims[0] == pytest.approx(1.0)


def test_fragment_of_a_known_peptide_has_similarity_one():
    """A piece of a known AMP is not a discovery, so it must score as fully similar."""
    index = NoveltyIndex(REFERENCE)
    fragment = MAGAININ[4:20]
    assert index.similarities(fragment)[0] == pytest.approx(1.0)
    hit = index.search([fragment]).iloc[0]
    assert hit.closest_known == MAGAININ and hit.novelty == pytest.approx(0.0)


def test_similarity_is_symmetric_and_between_zero_and_one():
    rng = np.random.default_rng(0)
    letters = np.array(list("ACDEFGHIKLMNPQRSTVWY"))
    for _ in range(30):
        a = "".join(rng.choice(letters, rng.integers(8, 40)))
        b = "".join(rng.choice(letters, rng.integers(8, 40)))
        ab = NoveltyIndex([b]).similarities(a)[0]
        ba = NoveltyIndex([a]).similarities(b)[0]
        assert ab == pytest.approx(ba)
        assert 0.0 <= ab <= 1.0 + 1e-9


def test_unrelated_peptide_scores_far_below_a_close_relative():
    index = NoveltyIndex(REFERENCE)
    relative = MAGAININ.replace("K", "R")  # conservative substitutions
    unrelated = "DDDDEEEENNNNQQQQ"
    assert index.similarities(relative).max() > 0.7
    assert index.similarities(unrelated).max() < 0.4


def test_exclude_identical_skips_only_the_exact_match():
    index = NoveltyIndex(REFERENCE)
    with_self = index.search([MAGAININ]).iloc[0]
    without = index.search([MAGAININ], exclude_identical=True).iloc[0]
    assert with_self.max_similarity == pytest.approx(1.0)
    assert without.closest_known != MAGAININ
    assert without.max_similarity < 1.0


def test_search_reports_ids_and_handles_no_candidates():
    index = NoveltyIndex(REFERENCE, ids=["A", "B", "C", "D"])
    assert index.search([MAGAININ]).iloc[0].closest_id == "A"
    assert len(index.search([])) == 0


def test_ids_must_match_the_reference_length():
    with pytest.raises(ValueError):
        NoveltyIndex(REFERENCE, ids=["only one"])


def test_classify_uses_the_two_cutoffs():
    assert classify(1.0, related_cutoff=0.4) == "known"
    assert classify(KNOWN, related_cutoff=0.4) == "known"
    assert classify(0.98, related_cutoff=0.4) == "related"
    assert classify(0.55, related_cutoff=0.4) == "related"
    assert classify(0.39, related_cutoff=0.4) == "novel"


def test_alignment_of_a_fragment_is_a_perfect_match():
    aln = NoveltyIndex(REFERENCE).alignment(MAGAININ[4:20], MAGAININ)
    assert aln.identity == 1.0 and aln.gaps == 0
