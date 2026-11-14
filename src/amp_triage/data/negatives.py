"""Sample the "not an AMP" windows used to train and test the models.

Rules (the reasoning is in docs/DECISIONS.md):
* Windows are cut from reviewed proteins that carry none of UniProt's antimicrobial keywords.
* Human proteins are left out completely: the human proteome is the final, untouched test.
* Each protein belongs to exactly one split (train / val / test), decided by a hash of its
  accession, so windows from one protein never end up on both sides of a split.
* Window lengths are drawn from the positives' own length distribution, so length alone says
  nothing about the class.
* A window is dropped if it shares any 7-residue stretch with a known AMP: such a window is
  probably a fragment of a relative of a known AMP, so calling it "not an AMP" would be wrong.
* Optionally only windows passing a stage-1 model are kept, which is how the stage-2
  negatives are built (they must look like the windows the main model will really see).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence

import numpy as np
import pandas as pd
from Bio import SeqIO

from amp_triage.candidates.windows import Proteome

KMER = 7
SPLIT_FRACTIONS = (0.70, 0.15, 0.15)


def protein_split(accession: str, fractions=SPLIT_FRACTIONS) -> str:
    """Stable 'train' / 'val' / 'test' assignment from a hash of the accession."""
    u = int(hashlib.md5(accession.encode()).hexdigest()[:8], 16) / 0x100000000
    if u < fractions[0]:
        return "train"
    return "val" if u < fractions[0] + fractions[1] else "test"


def kmer_set(sequences: Iterable[str], k: int = KMER) -> set[str]:
    return {s[i : i + k] for s in sequences for i in range(len(s) - k + 1)}


def shares_kmer(seq: str, kmers: set[str], k: int = KMER) -> bool:
    return any(seq[i : i + k] in kmers for i in range(len(seq) - k + 1))


def load_pool(fasta_path, exclude: set[str], max_proteins: int | None, seed: int):
    """Read a protein FASTA, drop `exclude`d accessions, optionally subsample reproducibly."""
    accs, seqs = [], []
    for rec in SeqIO.parse(str(fasta_path), "fasta"):
        acc = rec.id.split("|")[1] if "|" in rec.id else rec.id
        if acc not in exclude:
            accs.append(acc)
            seqs.append(str(rec.seq).upper())
    if max_proteins and len(accs) > max_proteins:
        keep = np.sort(np.random.default_rng(seed).choice(len(accs), max_proteins, replace=False))
        accs, seqs = [accs[k] for k in keep], [seqs[k] for k in keep]
    return accs, seqs


def sample_windows(
    accessions: Sequence[str],
    sequences: Sequence[str],
    lengths: np.ndarray,
    n: int,
    split: str,
    banned_kmers: set[str],
    stage1=None,
    seed: int = 0,
    oversample: float = 1.3,
) -> pd.DataFrame:
    """Draw about n windows from the proteins of `split`.

    `lengths` is the pool the window lengths are drawn from (typically the positives' lengths).
    If `stage1` (a calibrated Stage1Model) is given, only windows it lets through are eligible.
    """
    rng = np.random.default_rng(seed)
    idx = [k for k, a in enumerate(accessions) if protein_split(a) == split]
    prot = Proteome.from_sequences([accessions[k] for k in idx], [sequences[k] for k in idx])

    want = rng.choice(lengths, size=int(n * oversample))
    rows = []
    for length, count in zip(*np.unique(want, return_counts=True), strict=True):
        length, count = int(length), int(count)
        if stage1 is None:
            starts, _, _ = prot.window_stats(length)
        else:
            starts, _, score = stage1.window_scores(prot, length)
            starts = starts[score >= stage1.threshold]
        if len(starts) == 0:
            continue
        pick = rng.choice(starts, size=count, replace=len(starts) < count)
        for s in pick:
            acc, pos = prot.locate(int(s))
            rows.append((prot.sequence_at(int(s), length), acc, pos, length))

    df = pd.DataFrame(rows, columns=["sequence", "accession", "start", "length"])
    df = df.drop_duplicates("sequence")
    df = df[~df.sequence.apply(lambda s: shares_kmer(s, banned_kmers))]
    df = df.sample(frac=1.0, random_state=seed).head(n).reset_index(drop=True)
    df.insert(0, "split", split)
    return df
