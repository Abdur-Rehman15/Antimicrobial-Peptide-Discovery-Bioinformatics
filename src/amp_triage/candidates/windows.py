"""Fast sliding-window statistics for candidate generation.

A proteome has hundreds of millions of windows (every protein x every length 8-50). Computing
full descriptors for each is far too slow, so the first-stage filter uses only two quantities
that can be read off a running total (prefix sum) in one step per window:

* net charge. At a fixed pH each residue adds a fixed amount of charge (Henderson-Hasselbalch
  gives K about +1, D about -1, and so on), so a window's charge is the sum over its residues
  plus a constant for the two ends. This equals descriptors.charge_at_ph exactly.
* hydrophobic fraction: the share of residues in A, C, F, I, L, M, V, W.

Only windows that pass go on to the full descriptors and the models.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np

from amp_triage import config
from amp_triage.features import descriptors as D


def residue_charge_weights(ph: float = D.PH_BLOOD) -> np.ndarray:
    """Charge contributed by each of the 20 amino acids at `ph` (order: config.AMINO_ACIDS)."""
    w = np.zeros(20)
    for aa, sign in D.CHARGE_SIGN.items():
        w[D._AA_INDEX[aa]] = sign / (1.0 + 10 ** (sign * (ph - D.PKA[aa])))
    return w


def termini_charge(ph: float = D.PH_BLOOD) -> float:
    """Constant charge of the free N- and C-terminus."""
    return 1.0 / (1.0 + 10 ** (ph - D.PKA["nTer"])) - 1.0 / (1.0 + 10 ** (D.PKA["cTer"] - ph))


@dataclass
class Proteome:
    """All proteins joined into flat arrays so every window length can be handled at once.

    A separator slot sits between proteins (weight 0, never hydrophobic) and `protein_id`
    marks which protein each slot belongs to, so a window never spans two proteins.
    """

    accessions: list[str]
    lengths: np.ndarray  # residues per protein
    starts: np.ndarray  # offset of each protein in the flat arrays
    codes: np.ndarray  # residue index 0-19, or -1 for separators and non-standard letters
    protein_id: np.ndarray  # protein index per slot, -1 for separators
    charge_prefix: np.ndarray  # running total of per-residue charge, length n+1
    hydrophobic_prefix: np.ndarray  # running total of hydrophobic residues, length n+1
    bad_prefix: np.ndarray  # running total of unusable slots (separator/non-standard)
    _aa_prefix: np.ndarray | None = None  # (20, n+1) count of each amino acid, built on demand

    @classmethod
    def from_sequences(
        cls, accessions: Iterable[str], sequences: Iterable[str], ph: float = D.PH_BLOOD
    ) -> Proteome:
        accs, seqs = list(accessions), list(sequences)
        lengths = np.array([len(s) for s in seqs], dtype=np.int64)
        starts = np.zeros(len(seqs), dtype=np.int64)
        starts[1:] = np.cumsum(lengths[:-1] + 1)
        total = int(lengths.sum() + len(seqs))
        codes = np.full(total, -1, dtype=np.int64)
        pid = np.full(total, -1, dtype=np.int64)
        for i, s in enumerate(seqs):
            if len(s):
                codes[starts[i] : starts[i] + len(s)] = D._ASCII[
                    np.frombuffer(s.encode("ascii", errors="replace"), dtype=np.uint8)
                ]
                pid[starts[i] : starts[i] + len(s)] = i
        usable = codes >= 0
        weights = np.where(usable, residue_charge_weights(ph)[np.where(usable, codes, 0)], 0.0)
        hydrophobic = np.where(usable, D._HYDROPHOBIC_MASK[np.where(usable, codes, 0)], False)
        return cls(
            accessions=accs,
            lengths=lengths,
            starts=starts,
            codes=codes,
            protein_id=pid,
            charge_prefix=np.concatenate([[0.0], np.cumsum(weights)]),
            hydrophobic_prefix=np.concatenate([[0], np.cumsum(hydrophobic)]),
            bad_prefix=np.concatenate([[0], np.cumsum(~usable)]),
        )

    @property
    def n_residues(self) -> int:
        return int(self.lengths.sum())

    def n_windows(self, length: int) -> int:
        return int(np.maximum(self.lengths - length + 1, 0).sum())

    def window_stats(self, length: int, ph: float = D.PH_BLOOD):
        """Charge and hydrophobic fraction of every valid window of `length` residues.

        Returns (starts, charge, hydrophobic_fraction), all arrays over the valid windows.
        A window is valid if it lies inside one protein and has only standard residues.
        """
        n = len(self.codes)
        if length > n:
            empty = np.zeros(0)
            return np.zeros(0, dtype=np.int64), empty, empty
        i = np.arange(n - length + 1)
        valid = (self.bad_prefix[i + length] - self.bad_prefix[i]) == 0
        i = i[valid]
        charge = self.charge_prefix[i + length] - self.charge_prefix[i] + termini_charge(ph)
        frac = (self.hydrophobic_prefix[i + length] - self.hydrophobic_prefix[i]) / length
        return i, charge, frac

    @property
    def aa_prefix(self) -> np.ndarray:
        """Running count of each of the 20 amino acids, shape (20, n + 1), int32."""
        if self._aa_prefix is None:
            n = len(self.codes)
            pre = np.zeros((20, n + 1), dtype=np.int32)
            for a in range(20):
                np.cumsum(self.codes == a, out=pre[a, 1:], dtype=np.int32)
            self._aa_prefix = pre
        return self._aa_prefix

    def linear_scores(
        self,
        aac_weights: np.ndarray,
        length_weight: float,
        charge_weight: float,
        intercept: float,
        length: int,
        ph: float = D.PH_BLOOD,
    ):
        """Score every valid window of `length` residues with a linear model on
        [20 amino-acid fractions, length, net charge].

        Returns (starts, charge, score). Identical to computing the features per peptide
        (checked in tests) but vectorised over the whole proteome.
        """
        i, charge, _ = self.window_stats(length, ph)
        pre = self.aa_prefix
        score = np.full(len(i), intercept + length_weight * length, dtype=np.float64)
        score += charge_weight * charge
        for a in range(20):
            if aac_weights[a] != 0.0:
                score += aac_weights[a] * (pre[a, i + length] - pre[a, i]) / length
        return i, charge, score

    def sequence_at(self, start: int, length: int) -> str:
        return "".join(D.AA[c] for c in self.codes[start : start + length])

    def locate(self, flat_start: int) -> tuple[str, int]:
        """(protein accession, 0-based position within that protein) of a flat window start."""
        p = int(self.protein_id[flat_start])
        return self.accessions[p], int(flat_start - self.starts[p])


def load_proteome(fasta_path, ph: float = D.PH_BLOOD) -> Proteome:
    from Bio import SeqIO

    accs, seqs = [], []
    for rec in SeqIO.parse(str(fasta_path), "fasta"):
        parts = rec.id.split("|")
        accs.append(parts[1] if len(parts) >= 2 else rec.id)
        seqs.append(str(rec.seq).upper())
    return Proteome.from_sequences(accs, seqs, ph)


LENGTHS = range(config.MIN_PEPTIDE_LEN, config.MAX_PEPTIDE_LEN + 1)
