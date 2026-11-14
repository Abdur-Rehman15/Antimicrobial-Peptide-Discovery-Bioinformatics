import numpy as np
import pytest

from amp_triage.candidates.window_features import (
    COLUMNS,
    WindowFeatureEngine,
    iter_proteome_chunks,
)
from amp_triage.candidates.windows import Proteome
from amp_triage.features import descriptors as D


def random_proteins(n, seed, lo=5, hi=150):
    rng = np.random.default_rng(seed)
    letters = np.array(list(D.AA))
    seqs = ["".join(rng.choice(letters, size=rng.integers(lo, hi))) for _ in range(n)]
    return [f"P{i:05d}" for i in range(n)], seqs


def check_against_per_peptide(prot, engine, length, sample, seed, all_windows_valid=True):
    starts, X = engine.descriptors(length)
    assert X.shape == (len(starts), len(COLUMNS)) and X.dtype == np.float32
    if all_windows_valid:
        assert len(starts) == prot.n_windows(length)
    rng = np.random.default_rng(seed)
    for k in rng.choice(len(starts), size=min(sample, len(starts)), replace=False):
        want = D.descriptors(prot.sequence_at(int(starts[k]), length))
        for c, name in enumerate(COLUMNS):
            # float32 storage: about 7 significant digits
            assert X[k, c] == pytest.approx(want[name], rel=2e-5, abs=2e-5), (length, name)


@pytest.mark.parametrize("length", [8, 10, 11, 12, 17, 25, 36, 50])
def test_every_descriptor_equals_the_per_peptide_code(length):
    accs, seqs = random_proteins(40, seed=length)
    prot = Proteome.from_sequences(accs, seqs)
    check_against_per_peptide(prot, WindowFeatureEngine(prot), length, sample=150, seed=1)


def test_columns_are_the_35_descriptors_in_order():
    assert COLUMNS == D.FEATURE_NAMES and len(COLUMNS) == 35


def test_every_window_is_covered_not_just_a_sample():
    accs, seqs = random_proteins(8, seed=7, lo=30, hi=60)
    prot = Proteome.from_sequences(accs, seqs)
    engine = WindowFeatureEngine(prot)
    starts, X = engine.descriptors(13)
    for k, s in enumerate(starts):  # all of them
        want = D.descriptors(prot.sequence_at(int(s), 13))
        got = dict(zip(COLUMNS, X[k], strict=True))
        for name in COLUMNS:
            assert got[name] == pytest.approx(want[name], rel=2e-5, abs=2e-5), name


def test_windows_with_unknown_residues_and_protein_edges_are_handled():
    seqs = ["KKLLKKLLKKLLKKXKLLKKLLKKLLKK", "GGGGGGGGGGGG", "DDEEDDEEDDEEKK"]
    prot = Proteome.from_sequences(["A", "B", "C"], seqs)
    engine = WindowFeatureEngine(prot)
    for length in (8, 11, 12):
        starts, X = engine.descriptors(length)
        assert len(starts) == prot.n_windows(length) - sum(
            1 for s in range(len(seqs[0]) - length + 1) if "X" in seqs[0][s : s + length]
        )
        assert np.isfinite(X).all()
        check_against_per_peptide(prot, engine, length, 50, 3, all_windows_valid=False)


def test_too_long_a_window_gives_an_empty_result():
    prot = Proteome.from_sequences(["A"], ["KKKKKKKKKK"])
    starts, X = WindowFeatureEngine(prot).descriptors(50)
    assert len(starts) == 0 and X.shape == (0, 35)


def test_chunks_cover_the_same_windows_as_one_big_proteome():
    accs, seqs = random_proteins(60, seed=11, lo=20, hi=80)
    whole = Proteome.from_sequences(accs, seqs)
    chunks = list(iter_proteome_chunks(accs, seqs, max_residues=800))
    assert len(chunks) > 1
    assert sum(c.n_windows(15) for c in chunks) == whole.n_windows(15)
    # descriptors of one window are the same whichever chunk it falls into
    got = {}
    for c in chunks:
        starts, X = WindowFeatureEngine(c).descriptors(15)
        for s, row in zip(starts, X, strict=True):
            got[c.sequence_at(int(s), 15)] = row
    starts, X = WindowFeatureEngine(whole).descriptors(15)
    for s, row in zip(starts[::25], X[::25], strict=True):
        assert np.allclose(got[whole.sequence_at(int(s), 15)], row, rtol=1e-5, atol=1e-5)
