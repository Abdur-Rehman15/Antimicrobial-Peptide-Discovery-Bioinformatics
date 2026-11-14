import math
import warnings

import numpy as np
import pytest
from Bio.SeqUtils.ProtParam import ProteinAnalysis
from peptides import Peptide, tables

from amp_triage.features import descriptors as D

AA = D.AA
MAGAININ = "GIGKFLHSAKKFGKAFVGEIMNS"
LL37 = "LLGDFFRKSKEKIGKEFKRIVQRIKDFLRNLVPRTES"


def random_peptides(n, seed, lo=8, hi=50):
    rng = np.random.default_rng(seed)
    letters = np.array(list(AA))
    return ["".join(rng.choice(letters, size=rng.integers(lo, hi + 1))) for _ in range(n)]


# ---- constants are copied by hand, so check them against the published library tables -------


def test_constant_tables_match_peptides_library():
    assert D.PKA == tables.PK["Lehninger"]
    assert {k: float(v) for k, v in D.CHARGE_SIGN.items()} == tables.CHARGE["sign"]
    assert D.EISENBERG == tables.HYDROPHOBICITY["Eisenberg"]
    assert D.KYTE_DOOLITTLE == tables.HYDROPHOBICITY["KyteDoolittle"]
    assert {k: v for k, v in D.BOMAN.items() if k != "P"} == tables.BOMAN["Boman"]
    assert D.BOMAN["P"] == 0.0


# ---- hand-calculated values ----------------------------------------------------------------


def test_aliphatic_index_by_hand():
    # A,V,I,L each 25%: (0.25 + 2.9*0.25 + 3.9*(0.25+0.25)) * 100
    assert D.descriptors("AVIL" * 3)["aliphatic_index"] == pytest.approx(292.5)


def test_hydrophobic_fraction_by_hand():
    assert D.descriptors("ACFILMVWGG")["hydrophobic_fraction"] == pytest.approx(0.8)
    assert D.descriptors("KKKKDDDDSS")["hydrophobic_fraction"] == 0.0


def test_two_residue_hydrophobic_moment_by_hand():
    # mu = |h1 + h2*exp(i*delta)| / 2 = sqrt(h1^2 + h2^2 + 2*h1*h2*cos(delta)) / 2
    h1, h2 = D.EISENBERG["A"], D.EISENBERG["R"]
    delta = math.radians(100)
    expected = math.sqrt(h1**2 + h2**2 + 2 * h1 * h2 * math.cos(delta)) / 2
    assert D.hydrophobic_moment(D.encode("AR"), 100) == pytest.approx(expected)


def test_composition_sums_to_one_and_matches_counts():
    d = D.descriptors("AAAKKR" + "G" * 4)
    assert sum(d[f"aac_{a}"] for a in AA) == pytest.approx(1.0)
    assert d["aac_A"] == pytest.approx(0.3) and d["aac_G"] == pytest.approx(0.4)
    assert d["frac_positive"] == pytest.approx(0.3)  # K, K, R
    assert d["frac_negative"] == 0.0


def test_charge_extremes_and_termini():
    counts = np.bincount(D.encode("KKKKGGGG"), minlength=20)
    assert D.charge_at_ph(counts, 0.0) == pytest.approx(5.0, abs=0.01)  # 4 Lys + N-terminus
    assert D.charge_at_ph(counts, 14.0) < 0  # everything deprotonated: only the C-terminus left
    acid = np.bincount(D.encode("DDEEGGGG"), minlength=20)
    assert D.charge_at_ph(acid, 7.4) < -3.5


def test_charge_falls_with_ph_and_is_zero_at_isoelectric_point():
    for seq in random_peptides(40, seed=1):
        counts = np.bincount(D.encode(seq), minlength=20)
        charges = [D.charge_at_ph(counts, ph) for ph in np.linspace(1, 13, 25)]
        assert all(a >= b for a, b in zip(charges, charges[1:], strict=False)), seq
        assert D.charge_at_ph(counts, D.isoelectric_point(counts)) == pytest.approx(0, abs=1e-6)


def test_known_peptide_charges():
    assert D.descriptors(MAGAININ)["net_charge"] == pytest.approx(3.0, abs=0.2)  # about +3
    assert D.descriptors(LL37)["net_charge"] == pytest.approx(6.0, abs=0.5)  # LL-37 is +6


# ---- amphipathic patterns give a large moment at the matching angle ------------------------


def _helical_pattern(n=18):
    """Water-repelling Leu where cos(100 deg * i) > 0, charged Lys elsewhere: a perfect
    amphipathic alpha-helix pattern."""
    return "".join("L" if math.cos(math.radians(100 * i)) > 0 else "K" for i in range(n))


def test_amphipathic_helix_has_big_helix_moment_and_beats_shuffles():
    seq = _helical_pattern()
    codes = D.encode(seq)
    moment = D.hydrophobic_moment(codes, 100)
    rng = np.random.default_rng(0)
    shuffled = [D.hydrophobic_moment(D.encode("".join(rng.permutation(list(seq)))), 100)
                for _ in range(100)]
    assert moment > 2 * np.mean(shuffled)
    assert moment > D.hydrophobic_moment(codes, 160)  # the helix pattern is not a strand pattern


def test_alternating_pattern_has_big_strand_moment():
    # Alternation is a beta-strand pattern. Length 10, not 18: with 18 residues the 160-degree
    # sum happens to make exactly one full turn and cancels to zero for any alternating pattern.
    # By hand for 10 residues: strand = 1.28*|sin(100)/sin(10)|/10 = 0.72, helix = 0.13.
    codes = D.encode("LK" * 5)
    strand, helix = D.hydrophobic_moment(codes, 160), D.hydrophobic_moment(codes, 100)
    assert strand == pytest.approx(0.72, abs=0.02)
    assert helix == pytest.approx(0.13, abs=0.02)
    assert strand > 3 * helix


# ---- agreement with independent implementations --------------------------------------------


def test_charge_and_pi_match_peptides_library_exactly():
    for seq in random_peptides(60, seed=2):
        lib = Peptide(seq)
        counts = np.bincount(D.encode(seq), minlength=20)
        for ph in (2.0, 5.5, 7.4, 9.0, 12.0):
            assert D.charge_at_ph(counts, ph) == pytest.approx(
                lib.charge(pH=ph, pKscale="Lehninger"), abs=1e-9
            )
        assert D.isoelectric_point(counts) == pytest.approx(
            lib.isoelectric_point(pKscale="Lehninger"), abs=1e-4
        )


def test_other_descriptors_match_peptides_library():
    for seq in random_peptides(60, seed=3):
        lib, mine = Peptide(seq), D.descriptors(seq)
        assert mine["aliphatic_index"] == pytest.approx(lib.aliphatic_index())
        assert mine["boman_index"] == pytest.approx(lib.boman())
        assert mine["hydrophobic_moment_helix_w11"] == pytest.approx(
            lib.hydrophobic_moment(window=11, angle=100)
        )


def test_gravy_and_aromaticity_match_biopython():
    for seq in random_peptides(60, seed=4):
        bio, mine = ProteinAnalysis(seq), D.descriptors(seq)
        assert mine["gravy"] == pytest.approx(bio.gravy())
        assert mine["frac_aromatic"] == pytest.approx(bio.aromaticity())


def test_matches_modlamp_on_real_peptides():
    from modlamp.descriptors import GlobalDescriptor

    seqs = [MAGAININ, LL37]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        g = GlobalDescriptor(seqs)
        g.calculate_all(amide=False)
    names = list(g.featurenames)
    for row, seq in zip(g.descriptor, seqs, strict=True):
        ref, mine = dict(zip(names, row, strict=True)), D.descriptors(seq)
        assert mine["net_charge"] == pytest.approx(ref["Charge"], abs=0.01)
        assert mine["aliphatic_index"] == pytest.approx(ref["AliphaticInd"], abs=0.01)
        assert mine["boman_index"] == pytest.approx(ref["BomanInd"], abs=0.01)
        assert mine["hydrophobic_fraction"] == pytest.approx(ref["HydrophRatio"], abs=0.01)
        assert mine["frac_aromatic"] == pytest.approx(ref["Aromaticity"], abs=0.01)


# ---- table interface and bad input ---------------------------------------------------------


def test_compute_descriptors_table_shape_and_order():
    seqs = [MAGAININ, LL37, "KKKK" + "LLLLLL"]
    df = D.compute_descriptors(seqs)
    assert df.sequence.tolist() == seqs
    assert list(df.columns) == ["sequence", *D.FEATURE_NAMES]
    assert len(D.FEATURE_NAMES) == 15 + 20
    assert not df.isna().any().any()
    assert D.compute_descriptors(seqs).equals(df)  # deterministic


@pytest.mark.parametrize("bad", ["", "ACDXK", "acdef", "AC-DE", "ACDEB", "ACDE*"])
def test_rejects_non_standard_input(bad):
    with pytest.raises(ValueError):
        D.descriptors(bad)


def test_moment_is_per_residue_so_length_does_not_inflate_it():
    helix = _helical_pattern(18)
    long_helix = _helical_pattern(36)
    assert D.hydrophobic_moment(D.encode(long_helix), 100) == pytest.approx(
        D.hydrophobic_moment(D.encode(helix), 100), rel=0.2
    )
