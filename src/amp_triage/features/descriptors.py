"""Physicochemical descriptors of a peptide, computed from its sequence.

Every descriptor is a number that a model can learn from. They are chosen because antimicrobial
peptides work by sticking to, then breaking, bacterial membranes, and each descriptor measures
one thing that matters for that:

net_charge            positive charge is what attracts the peptide to the negatively charged
                      bacterial membrane
charge_density        net charge per residue (a long peptide needs more charge)
isoelectric_point     the pH at which the peptide has no net charge (high for AMPs)
hydrophobic_fraction  share of water-repelling residues, which let the peptide enter the membrane
mean_hydrophobicity   average of the Eisenberg consensus scale
gravy                 grand average of hydropathy (Kyte-Doolittle), a second hydrophobicity view
hydrophobic_moment_*  how strongly water-repelling and water-loving residues sit on opposite sides
                      of a helix (helix) or strand: the numeric meaning of "amphipathic"
aliphatic_index       relative volume of Ala/Val/Ile/Leu side chains (Ikai, 1980)
boman_index           protein-binding potential (Boman, 2003), high for peptides that bind targets
frac_*                shares of positive, negative and aromatic residues
aac_<A..Y>            amino-acid composition, 20 fractions

Conventions (so every number is reproducible):
* Charge: Henderson-Hasselbalch with the Lehninger pKa set, at pH 7.4 (blood) by default.
* Hydrophobic moment: mu = |sum_n H_n * exp(i * n * delta)| / N with the Eisenberg consensus
  scale H, delta = 100 degrees for an alpha-helix (3.6 residues per turn) or 160 degrees for a
  beta-strand. N is the peptide length, so values are per residue and comparable across lengths.
  `*_w11` is the maximum over every 11-residue window (the form used by peptides.py/modlAMP).
* Only the 20 standard amino acids are accepted; anything else raises ValueError.

tests/test_descriptors.py checks these against peptides.py, modlAMP and Biopython, and against
hand-calculated values.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from amp_triage import config

AA = config.AMINO_ACIDS  # "ACDEFGHIKLMNPQRSTVWY"
_AA_INDEX = {a: i for i, a in enumerate(AA)}

PH_BLOOD = 7.4

# Lehninger pKa values (Nelson & Cox) used for charge and isoelectric point.
PKA = {
    "C": 8.18, "D": 3.65, "E": 4.25, "H": 6.0, "K": 10.53, "R": 12.48, "Y": 10.07,
    "nTer": 9.69, "cTer": 2.34,
}
# +1: group is positive when protonated (loses charge as pH rises); -1: negative when ionised
CHARGE_SIGN = {"C": -1, "D": -1, "E": -1, "H": 1, "K": 1, "R": 1, "Y": -1}

# Eisenberg, Weiss & Terwilliger (1984) normalised consensus hydrophobicity
EISENBERG = {
    "A": 0.62, "R": -2.53, "N": -0.78, "D": -0.90, "C": 0.29, "Q": -0.85, "E": -0.74,
    "G": 0.48, "H": -0.40, "I": 1.38, "L": 1.06, "K": -1.50, "M": 0.64, "F": 1.19,
    "P": 0.12, "S": -0.18, "T": -0.05, "W": 0.81, "Y": 0.26, "V": 1.08,
}
# Kyte & Doolittle (1982) hydropathy
KYTE_DOOLITTLE = {
    "A": 1.8, "R": -4.5, "N": -3.5, "D": -3.5, "C": 2.5, "Q": -3.5, "E": -3.5, "G": -0.4,
    "H": -3.2, "I": 4.5, "L": 3.8, "K": -3.9, "M": 1.9, "F": 2.8, "P": -1.6, "S": -0.8,
    "T": -0.7, "W": -0.9, "Y": -1.3, "V": 4.2,
}
# Boman (2003) solid-phase protein-binding potential, kcal/mol. The published table has no value
# for proline; like peptides.py it is treated as 0.
BOMAN = {
    "P": 0.0,
    "L": 4.92, "I": 4.92, "V": 4.04, "F": 2.98, "M": 2.35, "W": 2.33, "A": 1.81, "C": 1.28,
    "G": 0.94, "Y": -0.14, "T": -2.57, "S": -3.4, "H": -4.66, "Q": -5.54, "K": -5.55,
    "N": -6.64, "E": -6.81, "D": -8.72, "R": -14.92,
}
HYDROPHOBIC_RESIDUES = frozenset("ACFILMVW")  # common AMP-literature definition
HELIX_ANGLE = 100  # degrees per residue, alpha-helix
STRAND_ANGLE = 160  # degrees per residue, beta-strand
MOMENT_WINDOW = 11


def _lut(table: dict[str, float]) -> np.ndarray:
    return np.array([table[a] for a in AA], dtype=np.float64)


_EISENBERG = _lut(EISENBERG)
_KD = _lut(KYTE_DOOLITTLE)
_BOMAN = _lut(BOMAN)
_HYDROPHOBIC_MASK = np.array([a in HYDROPHOBIC_RESIDUES for a in AA])
_ASCII = np.full(256, -1, dtype=np.int64)
for _a, _i in _AA_INDEX.items():
    _ASCII[ord(_a)] = _i


def encode(seq: str) -> np.ndarray:
    """Sequence -> array of 0..19 indices. Raises ValueError on any non-standard letter."""
    if not seq:
        raise ValueError("empty sequence")
    codes = _ASCII[np.frombuffer(seq.encode("ascii", errors="replace"), dtype=np.uint8)]
    if (codes < 0).any():
        bad = sorted({c for c in seq if c not in _AA_INDEX})
        raise ValueError(f"non-standard residue(s) {bad} in {seq!r}")
    return codes


def _counts(codes: np.ndarray) -> np.ndarray:
    return np.bincount(codes, minlength=20)


def charge_at_ph(counts: np.ndarray, ph: float) -> float:
    """Net charge from residue counts (Henderson-Hasselbalch), including both termini."""
    total = 1.0 / (1.0 + 10 ** (ph - PKA["nTer"]))  # N-terminus, positive
    total -= 1.0 / (1.0 + 10 ** (PKA["cTer"] - ph))  # C-terminus, negative
    for aa, sign in CHARGE_SIGN.items():
        n = counts[_AA_INDEX[aa]]
        if n:
            total += n * sign / (1.0 + 10 ** (sign * (ph - PKA[aa])))
    return float(total)


def isoelectric_point(counts: np.ndarray) -> float:
    """pH where the net charge is zero, by bisection (charge falls steadily as pH rises)."""
    lo, hi = 0.0, 14.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if charge_at_ph(counts, mid) > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def hydrophobic_moment(codes: np.ndarray, angle_deg: float = HELIX_ANGLE) -> float:
    """Eisenberg hydrophobic moment per residue over the whole sequence."""
    h = _EISENBERG[codes]
    theta = np.deg2rad(angle_deg) * np.arange(len(codes))
    return float(np.hypot((h * np.cos(theta)).sum(), (h * np.sin(theta)).sum()) / len(codes))


def hydrophobic_moment_windowed(
    codes: np.ndarray, angle_deg: float = HELIX_ANGLE, window: int = MOMENT_WINDOW
) -> float:
    """Largest per-residue moment over all windows of `window` residues (window shrinks to the
    sequence length for short peptides)."""
    window = min(window, len(codes))
    best = 0.0
    for start in range(len(codes) - window + 1):
        best = max(best, hydrophobic_moment(codes[start : start + window], angle_deg))
    return best


def descriptors(seq: str, ph: float = PH_BLOOD) -> dict[str, float]:
    """All descriptors of one peptide as a flat dict (column name -> value)."""
    codes = encode(seq)
    n = len(codes)
    counts = _counts(codes)
    freq = counts / n

    def c(aa: str) -> float:
        return float(freq[_AA_INDEX[aa]])

    charge = charge_at_ph(counts, ph)
    out = {
        "length": float(n),
        "net_charge": charge,
        "charge_density": charge / n,
        "isoelectric_point": isoelectric_point(counts),
        "hydrophobic_fraction": float(_HYDROPHOBIC_MASK[codes].mean()),
        "mean_hydrophobicity": float(_EISENBERG[codes].mean()),
        "gravy": float(_KD[codes].mean()),
        "hydrophobic_moment_helix": hydrophobic_moment(codes, HELIX_ANGLE),
        "hydrophobic_moment_strand": hydrophobic_moment(codes, STRAND_ANGLE),
        "hydrophobic_moment_helix_w11": hydrophobic_moment_windowed(codes, HELIX_ANGLE),
        "aliphatic_index": 100.0 * (c("A") + 2.9 * c("V") + 3.9 * (c("I") + c("L"))),
        "boman_index": float(-_BOMAN[codes].mean()),
        "frac_positive": c("K") + c("R"),
        "frac_negative": c("D") + c("E"),
        "frac_aromatic": c("F") + c("W") + c("Y"),
    }
    for aa in AA:
        out[f"aac_{aa}"] = c(aa)
    return out


FEATURE_NAMES = list(descriptors("ACDEFGHIKLMNPQRSTVWY"))


def compute_descriptors(sequences: Iterable[str], ph: float = PH_BLOOD) -> pd.DataFrame:
    """Descriptor table, one row per sequence, in the order given."""
    seqs = list(sequences)
    rows = [descriptors(s, ph) for s in seqs]
    df = pd.DataFrame(rows, columns=FEATURE_NAMES)
    df.insert(0, "sequence", seqs)
    return df


__all__ = [
    "FEATURE_NAMES",
    "charge_at_ph",
    "compute_descriptors",
    "descriptors",
    "encode",
    "hydrophobic_moment",
    "hydrophobic_moment_windowed",
    "isoelectric_point",
]
