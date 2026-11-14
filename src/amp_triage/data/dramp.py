"""Read DRAMP downloads (http://dramp.cpu-bioinfor.org/downloads/, CC BY 4.0).

The .txt files are tab-separated with quoted, multi-line text fields, so they are read with
pandas using the C-parser quote rules rather than splitting on newlines.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd


def load_dramp(path: Path) -> pd.DataFrame:
    df = pd.read_csv(
        path,
        sep="\t",
        quotechar='"',
        quoting=csv.QUOTE_MINIMAL,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8",
        encoding_errors="replace",
    )
    df["Sequence"] = df["Sequence"].str.strip().str.upper()
    # Column layouts differ between files: the subset files (e.g. Antibacterial_amps.txt)
    # have "Length" and a "Dataset" column; the general file has "Sequence_Length".
    length_col = "Sequence_Length" if "Sequence_Length" in df.columns else "Length"
    df["length"] = pd.to_numeric(df[length_col], errors="coerce")
    return df
