"""Find peptides that occur word-for-word inside a set of proteins (e.g. the human proteome).

Used to hold human-derived peptides out of training. The database label "Homo sapiens" is not
enough: many human-derived fragments are recorded as "synthetic" (they were made in a lab) but
their sequence is part of a human protein, so a model trained on them has seen the answer.
"""

from __future__ import annotations

import bisect
import itertools
from collections.abc import Iterable
from pathlib import Path

from Bio import SeqIO


def find_in_proteins(sequences: Iterable[str], fasta_path: Path) -> dict[str, str]:
    """Map each sequence that occurs exactly inside a protein to that protein's accession.

    If a sequence occurs in several proteins, the first one found is reported.
    Proteins are joined with '#', which is not an amino-acid letter, so no match can span
    two proteins.
    """
    accessions, seqs = [], []
    for rec in SeqIO.parse(str(fasta_path), "fasta"):
        parts = rec.id.split("|")
        accessions.append(parts[1] if len(parts) >= 2 else rec.id)
        seqs.append(str(rec.seq))
    big = "#".join(seqs)
    starts = [0, *itertools.accumulate(len(s) + 1 for s in seqs)][:-1]

    hits: dict[str, str] = {}
    for s in sequences:
        if not s or "#" in s:
            continue
        k = big.find(s)
        if k >= 0:
            hits[s] = accessions[bisect.bisect_right(starts, k) - 1]
    return hits
