"""Read APD3 FASTA downloads (https://aps.unmc.edu/downloads).

The files start with a pseudo-record ">Your search led to N peptides" that has no sequence;
it is skipped. Real records are ">AP00001" followed by the sequence.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from Bio import SeqIO


def load_apd_fasta(path: Path) -> pd.DataFrame:
    rows = []
    for rec in SeqIO.parse(str(path), "fasta"):
        if not rec.id.startswith("AP") or not str(rec.seq):
            continue  # skip the "Your search led to N peptides" header record
        rows.append({"apd_id": rec.id, "sequence": str(rec.seq).upper()})
    df = pd.DataFrame(rows)
    df["length"] = df["sequence"].str.len()
    return df
