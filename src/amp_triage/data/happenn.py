"""Parse the HAPPENN hemolysis dataset from the paper's supplementary PDF.

Source: Timmons & Hewage (2020), Sci Rep 10, 10869. The supplement
(41598_2020_67701_MOESM1_ESM.pdf) lists every peptide as a FASTA-like record:

    >lcl|2826|lcl|HAPPENN&HAPPENN-RR90&HAPPENN-hard|lcl|subdataset_9|lcl|hemolytic|lcl|cTer
    YKLLKLLLPKLKGLLFKL

Header fields:
    id           record number in the paper
    sets         which sets the peptide belongs to: HAPPENN (full), HAPPENN-RR90
                 (<=90% similarity), HAPPENN-hard (hemolytic paired with the most
                 similar non-hemolytic peptides)
    subdataset   "subdataset_N" tag from the supplement (meaning not yet verified)
    label        hemolytic / non-hemolytic
    nTer, cTer   optional flags (meaning to be confirmed against the paper; most likely
                 N-/C-terminal modification)

The PDF text has the line numbers of the PDF and wraps long header lines, so records are
rebuilt from the "pdftotext -raw" output.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pandas as pd

_LINE_NO = re.compile(r"^(\d+) (.*)$")
_VALID_SEQ = re.compile(r"^[A-Za-z]+$")


def pdf_to_text(pdf_path: Path, txt_path: Path) -> Path:
    """Extract text with poppler's pdftotext (-raw keeps each record in reading order)."""
    try:
        subprocess.run(["pdftotext", "-raw", str(pdf_path), str(txt_path)], check=True)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "pdftotext (poppler) was not found on PATH. Install poppler or run the "
            "extraction step on a machine that has it."
        ) from exc
    return txt_path


def _logical_lines(text: str) -> list[str]:
    """Join wrapped lines. A new logical line starts at '<number> <content>'."""
    lines: list[str] = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw or raw.isdigit():  # blank, or a trailing bare line number
            continue
        m = _LINE_NO.match(raw)
        if m:
            lines.append(m.group(2))
        elif lines:
            lines[-1] += raw
    return lines


def parse_supplement_text(text: str) -> pd.DataFrame:
    """Turn the extracted text into one row per peptide."""
    lines = _logical_lines(text)
    rows = []
    i = 0
    while i < len(lines):
        header = lines[i]
        if not header.startswith(">lcl|"):
            raise ValueError(f"Expected a header at logical line {i}, got: {header[:60]!r}")
        if i + 1 >= len(lines):
            raise ValueError("Header without a sequence at the end of the file")
        seq = lines[i + 1]
        if not _VALID_SEQ.match(seq):
            raise ValueError(f"Bad sequence after header {header[:60]!r}: {seq!r}")

        parts = [p for p in header[1:].split("|") if p != "lcl"]
        # parts = [id, sets, subdataset, label, optional flags...]
        sets = parts[1].split("&")
        flags = set(parts[4:])
        rows.append(
            {
                "record_id": int(parts[0]),
                "sequence": seq.upper(),
                "label": parts[3],
                "in_happenn": "HAPPENN" in sets,
                "in_rr90": "HAPPENN-RR90" in sets,
                "in_hard": "HAPPENN-hard" in sets,
                "subdataset": parts[2],
                "n_ter_flag": "nTer" in flags,
                "c_ter_flag": "cTer" in flags,
            }
        )
        i += 2
    df = pd.DataFrame(rows)
    df["hemolytic"] = (df["label"] == "hemolytic").astype(int)
    df["length"] = df["sequence"].str.len()
    return df


def load_happenn(txt_path: Path) -> pd.DataFrame:
    return parse_supplement_text(Path(txt_path).read_text(encoding="utf-8", errors="replace"))
