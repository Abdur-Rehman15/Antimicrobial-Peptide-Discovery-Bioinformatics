import numpy as np
import pytest
from Bio.Align import PairwiseAligner, substitution_matrices

from amp_triage.alignment import blosum62, rescore, smith_waterman, sw_score, sw_scores

BIOPYTHON_BLOSUM62 = substitution_matrices.load("BLOSUM62")
AA = "ACDEFGHIKLMNPQRSTVWY"


def biopython_score(q, t, gap_open=11, gap_extend=1):
    """Biopython's local score. Its gap of length k costs open + (k-1)*extend, so our
    'open + k*extend' convention corresponds to open_gap_score = -(open + extend)."""
    aligner = PairwiseAligner(
        mode="local",
        substitution_matrix=BIOPYTHON_BLOSUM62,
        open_gap_score=-(gap_open + gap_extend),
        extend_gap_score=-gap_extend,
    )
    return aligner.score(q, t)


def random_pairs(n, alphabet, seed, lo=3, hi=60):
    rng = np.random.default_rng(seed)
    letters = np.array(list(alphabet))
    pairs = []
    for _ in range(n):
        a = "".join(rng.choice(letters, size=rng.integers(lo, hi)))
        b = "".join(rng.choice(letters, size=rng.integers(lo, hi)))
        pairs.append((a, b))
    return pairs


# ---- the substitution matrix ------------------------------------------------------------


def test_blosum62_matches_biopython_for_every_pair():
    for a in blosum62.ALPHABET:
        for b in blosum62.ALPHABET:
            assert blosum62.score(a, b) == int(BIOPYTHON_BLOSUM62[a, b]), (a, b)


def test_blosum62_symmetric_and_case_insensitive():
    assert np.array_equal(blosum62.MATRIX, blosum62.MATRIX.T)
    assert blosum62.score("w", "W") == 11
    assert blosum62.score("U", "A") == blosum62.score("X", "A")  # unknown letter -> X


# ---- hand-calculated cases --------------------------------------------------------------


def test_identical_pair_scores_sum_of_diagonal():
    aln = smith_waterman("AW", "AW")
    assert aln.score == 4 + 11
    assert (aln.aligned_query, aln.aligned_target) == ("AW", "AW")
    assert aln.identities == 2 and aln.gaps == 0 and aln.identity == 1.0


def test_no_positive_scoring_pair_gives_empty_alignment():
    aln = smith_waterman("W", "P")  # BLOSUM62 W/P = -4, so nothing is worth aligning
    assert aln.score == 0 and aln.length == 0


def test_local_alignment_finds_embedded_motif():
    aln = smith_waterman("WWWW", "PPPPWWWWPPPP")
    assert aln.score == 44
    assert (aln.target_start, aln.target_end) == (4, 8)
    assert (aln.query_start, aln.query_end) == (0, 4)


def test_single_residue_insertion_costs_open_plus_extend():
    query = "ACDEFGHIKLM"  # self score 62 (4+9+6+5+6+6+8+4+5+4+5)
    target = "ACDEF" + "W" + "GHIKLM"
    aln = smith_waterman(query, target)
    assert aln.score == 62 - (11 + 1 * 1)
    assert aln.gaps == 1 and aln.aligned_query[5] == "-"


def test_two_residue_insertion_extends_the_gap():
    query = "ACDEFGHIKLM"
    target = "ACDEF" + "WW" + "GHIKLM"
    aln = smith_waterman(query, target)
    assert aln.score == 62 - (11 + 2 * 1)
    assert aln.gaps == 2 and aln.aligned_query[5:7] == "--"


def test_cathelicidin_ll37_inside_fall39_is_a_perfect_local_match():
    ll37 = "LLGDFFRKSKEKIGKEFKRIVQRIKDFLRNLVPRTES"
    fall39 = "FA" + ll37
    aln = smith_waterman(ll37, fall39)
    assert aln.identity == 1.0 and aln.gaps == 0 and aln.length == len(ll37)
    assert (aln.target_start, aln.target_end) == (2, 2 + len(ll37))
    assert aln.score == smith_waterman(ll37, ll37).score


# ---- properties that must hold for any input --------------------------------------------


def test_empty_and_case_handling():
    assert smith_waterman("", "ACD").score == 0
    assert smith_waterman("ACD", "").score == 0
    assert sw_score("", "ACD") == 0 and sw_score("ACD", "") == 0
    assert smith_waterman("acdef", "ACDEF").score == smith_waterman("ACDEF", "ACDEF").score


@pytest.mark.parametrize("alphabet", [AA, "ACGK"])  # small alphabet = many ties and gaps
def test_matches_biopython_on_random_pairs(alphabet):
    for q, t in random_pairs(150, alphabet, seed=1):
        assert smith_waterman(q, t).score == pytest.approx(biopython_score(q, t)), (q, t)


@pytest.mark.parametrize("gap_open,gap_extend", [(11, 1), (10, 0.5), (9, 1), (5, 2)])
def test_matches_biopython_for_other_gap_penalties(gap_open, gap_extend):
    for q, t in random_pairs(60, AA, seed=2):
        ours = smith_waterman(q, t, gap_open, gap_extend).score
        assert ours == pytest.approx(biopython_score(q, t, gap_open, gap_extend)), (q, t)


@pytest.mark.parametrize("alphabet", [AA, "ACGK"])
def test_returned_alignment_is_internally_consistent(alphabet):
    """The alignment text must add up to the reported score and match the input sequences."""
    for q, t in random_pairs(150, alphabet, seed=3):
        aln = smith_waterman(q, t)
        assert rescore(aln.aligned_query, aln.aligned_target) == pytest.approx(aln.score)
        assert aln.aligned_query.replace("-", "") == q[aln.query_start : aln.query_end]
        assert aln.aligned_target.replace("-", "") == t[aln.target_start : aln.target_end]
        assert len(aln.aligned_query) == len(aln.aligned_target) == len(aln.midline)


def test_score_is_symmetric():
    for q, t in random_pairs(80, AA, seed=4):
        assert smith_waterman(q, t).score == smith_waterman(t, q).score


# ---- the fast version -------------------------------------------------------------------


@pytest.mark.parametrize("alphabet", [AA, "ACGK"])
def test_fast_score_equals_reference(alphabet):
    for q, t in random_pairs(150, alphabet, seed=5):
        assert sw_score(q, t) == smith_waterman(q, t).score, (q, t)


def test_fast_other_gap_penalties_equal_reference():
    for q, t in random_pairs(60, AA, seed=6):
        assert sw_score(q, t, 10, 0.5) == pytest.approx(smith_waterman(q, t, 10, 0.5).score)


def test_sw_scores_matches_one_at_a_time():
    pairs = random_pairs(100, AA, seed=7)
    query = pairs[0][0]
    targets = [t for _, t in pairs]
    many = sw_scores(query, targets)
    assert many.shape == (len(targets),)
    for score, target in zip(many, targets, strict=True):
        assert score == smith_waterman(query, target).score
    assert sw_scores(query, []).shape == (0,)
    assert sw_scores("", targets).tolist() == [0.0] * len(targets)


def test_format_renders_alignment_blocks():
    aln = smith_waterman("ACDEFGHIKLM", "ACDEFWGHIKLM")
    text = aln.format(query_name="cand", target_name="AP1")
    assert "Identities = 11/12" in text and "Gaps = 1/12" in text
    assert "cand" in text and "AP1" in text
