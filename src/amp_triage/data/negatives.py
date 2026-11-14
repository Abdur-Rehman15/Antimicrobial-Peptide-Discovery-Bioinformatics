"""Sample the "not an AMP" windows used to train and test the models.

Rules (the reasoning is in docs/DECISIONS.md):
* Windows are cut from reviewed proteins that carry none of UniProt's antimicrobial keywords.
* Human proteins are left out completely: the human proteome is the final, untouched test.
* Each protein belongs to exactly one split (train / val / test), decided by a hash of its
  accession, so windows from one protein never end up on both sides of a split.
* Window lengths: the sampler draws them from whatever length pool it is given. The first
  version copied the positives' lengths. That made negatives 13% long (36-50) while a scan of a
  proteome is 35% long windows, and human proteins then passed the score threshold 3.6-6.9 times
  more often than the training negatives. The datasets now use every length 8-50 equally often,
  like the windows of a scan, so the model also learns how rare AMPs of each length are.
* Proteins: about 70% are mammalian (see `load_mixed_pool`), because a mammalian proteome is
  what the system is mostly used on, and the rest come from other organisms for variety.
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
HUMAN_OX = "9606"
# UniProt organism ids (OX=) of non-human mammals. Each id was checked against the organism
# name in the Swiss-Prot headers (mouse, rat, cow, pig, macaques, ... 41,928 proteins).
MAMMAL_OX = {
    "10090", "10116", "9913", "9601", "9823", "9541", "9986", "9544", "9598", "9615",
    "9940", "9796", "10141", "9483", "9595", "60711", "9555", "10036", "10029", "9685",
    "10094", "10105", "9534", "9531", "9407", "9258", "9361", "9365", "9371", "10181",
    "10020", "9768", "9669", "9646", "9402", "9739", "9755", "9785", "9813", "9838",
    "9858", "9902", "9915", "9925", "9927", "9931", "9978", "10042", "10047", "10091",
    "10096",
}


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


def load_mixed_pool(
    fasta_path,
    exclude: set[str],
    n_total: int,
    mammal_share: float,
    seed: int,
    mammal_ox: set[str] = MAMMAL_OX,
):
    """Proteins for the negatives: about `mammal_share` mammalian, the rest from other organisms.

    Reads a UniProt FASTA, drops `exclude`d accessions (the human proteins) and anything whose
    header says OX=9606, then draws `n_total` proteins reproducibly. If fewer mammalian proteins
    exist than asked for, all of them are used and the rest of the budget goes to other organisms.
    Returns (accessions, sequences, n_mammalian).
    """
    mammal, other = ([], []), ([], [])
    for rec in SeqIO.parse(str(fasta_path), "fasta"):
        acc = rec.id.split("|")[1] if "|" in rec.id else rec.id
        ox = rec.description.split(" OX=")[1].split()[0] if " OX=" in rec.description else ""
        if acc in exclude or ox == HUMAN_OX:
            continue
        target = mammal if ox in mammal_ox else other
        target[0].append(acc)
        target[1].append(str(rec.seq).upper())
    rng = np.random.default_rng(seed)

    def draw(group, k):
        accs, seqs = group
        keep = np.sort(rng.choice(len(accs), min(k, len(accs)), replace=False))
        return [accs[i] for i in keep], [seqs[i] for i in keep]

    n_mammal = min(int(round(n_total * mammal_share)), len(mammal[0]))
    m_accs, m_seqs = draw(mammal, n_mammal)
    o_accs, o_seqs = draw(other, n_total - len(m_accs))
    return m_accs + o_accs, m_seqs + o_seqs, len(m_accs)


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
