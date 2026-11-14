"""All 35 descriptors for every window of a proteome, computed in bulk from running totals.

features/descriptors.py describes ONE peptide at a time (about 1 ms each). A proteome has
hundreds of millions of windows, so here each descriptor is rebuilt from prefix sums, which give
any window's total in two lookups:

* sums of per-residue values (charge, hydrophobicity, Boman, residue counts) are a difference
  of two prefix values;
* the hydrophobic moment is the size of a sum of h_m * exp(i * delta * m). The window starts at
  residue s, so its own sum is exp(-i * delta * s) times the prefix difference, and the phase
  factor has size 1: moment = |prefix difference| / length;
* the isoelectric point depends only on how many C, D, E, H, K, R, Y a window holds, and many
  windows share the same counts, so it is solved once per distinct combination of counts;
* the 11-residue-window moment is the largest 11-residue moment inside the window: a sliding
  maximum over the per-position 11-residue moments.

Every column equals features.descriptors.descriptors() for the same window (tests/
test_window_features.py). Windows stay inside one protein and contain only the 20 standard
residues.

Use `iter_proteome_chunks` to process a big proteome in pieces of about a million residues:
the prefix tables are then small and fast, and chunks are independent.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from amp_triage.candidates.windows import Proteome
from amp_triage.features import descriptors as D

COLUMNS = D.FEATURE_NAMES  # 35 names, same order as features.descriptors
_IONISABLE = ["C", "D", "E", "H", "K", "R", "Y"]
_ION_IDX = [D._AA_INDEX[a] for a in _IONISABLE]
_ION_PKA = np.array([D.PKA[a] for a in _IONISABLE])
_ION_SIGN = np.array([D.CHARGE_SIGN[a] for a in _IONISABLE], dtype=np.float64)
_BASE = 64  # window counts are at most 50, so 6 bits per residue type are enough in a key


class WindowFeatureEngine:
    """Prefix tables for one Proteome, and the descriptors of all its windows of any length."""

    def __init__(self, proteome: Proteome, ph: float = D.PH_BLOOD):
        self.prot = proteome
        self.ph = ph
        codes = proteome.codes
        usable = codes >= 0
        safe = np.where(usable, codes, 0)

        def per_residue(lut: np.ndarray) -> np.ndarray:
            return np.concatenate([[0.0], np.cumsum(np.where(usable, lut[safe], 0.0))])

        self.eisenberg = per_residue(D._EISENBERG)
        self.kd = per_residue(D._KD)
        self.boman = per_residue(D._BOMAN)
        h = np.where(usable, D._EISENBERG[safe], 0.0)
        m = np.arange(len(codes))
        self.z_helix = np.concatenate(
            [[0j], np.cumsum(h * np.exp(1j * np.deg2rad(D.HELIX_ANGLE) * m))]
        )
        self.z_strand = np.concatenate(
            [[0j], np.cumsum(h * np.exp(1j * np.deg2rad(D.STRAND_ANGLE) * m))]
        )
        self._m11_cache: np.ndarray | None = None

    # ---- helpers ---------------------------------------------------------------------

    def _moment11_per_position(self) -> np.ndarray:
        """Moment of the 11-residue window starting at every position (-inf if not valid)."""
        if self._m11_cache is None:
            n = len(self.prot.codes)
            m11 = np.full(n, -np.inf)
            if n >= D.MOMENT_WINDOW:
                p = np.arange(n - D.MOMENT_WINDOW + 1)
                ok = (
                    self.prot.bad_prefix[p + D.MOMENT_WINDOW] - self.prot.bad_prefix[p]
                ) == 0
                p = p[ok]
                diff = self.z_helix[p + D.MOMENT_WINDOW] - self.z_helix[p]
                m11[p] = np.abs(diff) / D.MOMENT_WINDOW
            self._m11_cache = m11
        return self._m11_cache

    def _isoelectric_points(self, ion_counts: np.ndarray) -> np.ndarray:
        """pI for each window from its (7, n) counts of C, D, E, H, K, R, Y."""
        key = np.zeros(ion_counts.shape[1], dtype=np.int64)
        for row in ion_counts:
            key = key * _BASE + row
        uniq, inverse = np.unique(key, return_inverse=True)
        counts = np.empty((len(_IONISABLE), len(uniq)), dtype=np.float64)
        rest = uniq.copy()
        for t in range(len(_IONISABLE) - 1, -1, -1):
            counts[t] = rest % _BASE
            rest //= _BASE

        lo = np.zeros(len(uniq))
        hi = np.full(len(uniq), 14.0)
        for _ in range(48):
            mid = (lo + hi) / 2
            charge = 1.0 / (1.0 + 10 ** (mid - D.PKA["nTer"]))
            charge -= 1.0 / (1.0 + 10 ** (D.PKA["cTer"] - mid))
            for t in range(len(_IONISABLE)):
                sign = _ION_SIGN[t]
                charge += counts[t] * sign / (1.0 + 10 ** (sign * (mid - _ION_PKA[t])))
            positive = charge > 0
            lo = np.where(positive, mid, lo)
            hi = np.where(positive, hi, mid)
        return ((lo + hi) / 2)[inverse]

    # ---- the descriptors -------------------------------------------------------------

    def descriptors(self, length: int) -> tuple[np.ndarray, np.ndarray]:
        """(starts, X): flat start of each valid window and a float32 matrix (n, 35)."""
        prot = self.prot
        starts, charge, hydrophobic_fraction = prot.window_stats(length, self.ph)
        n = len(starts)
        out = np.empty((n, len(COLUMNS)), dtype=np.float32)
        if n == 0:
            return starts, out
        j = starts + length
        col = {name: k for k, name in enumerate(COLUMNS)}

        counts = (prot.aa_prefix[:, j] - prot.aa_prefix[:, starts]).astype(np.int64)  # (20, n)
        freq = counts / length

        out[:, col["length"]] = length
        out[:, col["net_charge"]] = charge
        out[:, col["charge_density"]] = charge / length
        out[:, col["isoelectric_point"]] = self._isoelectric_points(counts[_ION_IDX])
        out[:, col["hydrophobic_fraction"]] = hydrophobic_fraction
        out[:, col["mean_hydrophobicity"]] = (self.eisenberg[j] - self.eisenberg[starts]) / length
        out[:, col["gravy"]] = (self.kd[j] - self.kd[starts]) / length
        out[:, col["hydrophobic_moment_helix"]] = (
            np.abs(self.z_helix[j] - self.z_helix[starts]) / length
        )
        out[:, col["hydrophobic_moment_strand"]] = (
            np.abs(self.z_strand[j] - self.z_strand[starts]) / length
        )
        if length <= D.MOMENT_WINDOW:  # the window is the whole peptide
            out[:, col["hydrophobic_moment_helix_w11"]] = out[:, col["hydrophobic_moment_helix"]]
        else:
            width = length - D.MOMENT_WINDOW + 1
            m11 = self._moment11_per_position()
            running_max = sliding_window_view(m11, width).max(axis=1)
            out[:, col["hydrophobic_moment_helix_w11"]] = running_max[starts]
        ix = D._AA_INDEX
        out[:, col["aliphatic_index"]] = 100.0 * (
            freq[ix["A"]] + 2.9 * freq[ix["V"]] + 3.9 * (freq[ix["I"]] + freq[ix["L"]])
        )
        out[:, col["boman_index"]] = -(self.boman[j] - self.boman[starts]) / length
        out[:, col["frac_positive"]] = freq[ix["K"]] + freq[ix["R"]]
        out[:, col["frac_negative"]] = freq[ix["D"]] + freq[ix["E"]]
        out[:, col["frac_aromatic"]] = freq[ix["F"]] + freq[ix["W"]] + freq[ix["Y"]]
        for aa in D.AA:
            out[:, col[f"aac_{aa}"]] = freq[ix[aa]]
        return starts, out


def iter_proteome_chunks(
    accessions: Sequence[str], sequences: Sequence[str], max_residues: int = 1_200_000
) -> Iterator[Proteome]:
    """Yield Proteome objects of about `max_residues` residues each (whole proteins only)."""
    accs, seqs, size = [], [], 0
    for a, s in zip(accessions, sequences, strict=True):
        if accs and size + len(s) > max_residues:
            yield Proteome.from_sequences(accs, seqs)
            accs, seqs, size = [], [], 0
        accs.append(a)
        seqs.append(s)
        size += len(s)
    if accs:
        yield Proteome.from_sequences(accs, seqs)
