import numpy as np
import pytest

from amp_triage.candidates.windows import Proteome, load_proteome
from amp_triage.features import descriptors as D


def random_proteins(n, seed):
    rng = np.random.default_rng(seed)
    letters = np.array(list(D.AA))
    seqs = ["".join(rng.choice(letters, size=rng.integers(5, 120))) for _ in range(n)]
    return [f"P{i:05d}" for i in range(n)], seqs


def test_window_stats_equal_the_full_descriptors_for_every_window():
    accs, seqs = random_proteins(25, seed=1)
    prot = Proteome.from_sequences(accs, seqs)
    for length in (8, 11, 20, 33, 50):
        starts, charge, frac = prot.window_stats(length)
        assert len(starts) == prot.n_windows(length)
        for k in np.random.default_rng(length).choice(len(starts), size=min(60, len(starts))):
            seq = prot.sequence_at(starts[k], length)
            d = D.descriptors(seq)
            assert charge[k] == pytest.approx(d["net_charge"], abs=1e-9)
            assert frac[k] == pytest.approx(d["hydrophobic_fraction"], abs=1e-12)


def test_windows_never_span_two_proteins():
    prot = Proteome.from_sequences(["A", "B"], ["KKKKKKKKKK", "DDDDDDDDDD"])  # 10 + 10
    starts, charge, _ = prot.window_stats(12)
    assert len(starts) == 0  # neither protein is long enough alone
    starts, charge, _ = prot.window_stats(10)
    assert len(starts) == 2 and charge[0] > 8 and charge[1] < -8


def test_window_counts_match_the_arithmetic():
    prot = Proteome.from_sequences(["A", "B", "C"], ["K" * 10, "K" * 8, "K" * 7])
    assert prot.n_windows(8) == 3 + 1 + 0
    assert prot.n_windows(10) == 1


def test_non_standard_residues_are_skipped_not_crashed():
    prot = Proteome.from_sequences(["A"], ["KKKKKKKKKXKKKKKKKKKK"])  # X in the middle
    starts, _, _ = prot.window_stats(8)
    for s in starts:  # every reported window avoids the X at position 9
        assert not (s <= 9 < s + 8)
    assert len(starts) == 20 - 8 + 1 - 8  # the 8 windows covering the X are dropped


def test_locate_reports_protein_and_position():
    prot = Proteome.from_sequences(["P1", "P2"], ["AAAAAAAAAA", "CCCCCCCCCCCC"])
    starts, _, _ = prot.window_stats(9)
    names = [prot.locate(int(s)) for s in starts]
    assert names[0] == ("P1", 0) and names[1] == ("P1", 1)
    assert names[2] == ("P2", 0)


def test_load_proteome_reads_fasta(tmp_path):
    f = tmp_path / "x.fasta"
    f.write_text(">sp|Q00001|AAA_HUMAN one\nKKKKKKKKKK\n>sp|Q00002|BBB_HUMAN two\nDDDDDDDDDD\n")
    prot = load_proteome(f)
    assert prot.accessions == ["Q00001", "Q00002"] and prot.n_residues == 20
