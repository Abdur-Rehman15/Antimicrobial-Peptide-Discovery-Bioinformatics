"""Download the raw datasets for Phase 1. Usage:

    python scripts/download_data.py apd happenn uniprot     # everything fast
    python -m amp_triage.data.dbaasp                        # DBAASP list (slow, ~20 min)

Raw files go to data/raw/<source>/ and each is recorded in data/MANIFEST.json.
"""

from __future__ import annotations

import sys

from amp_triage import config
from amp_triage.data.download import download_file

APD_BASE = "https://aps.unmc.edu/assets/sequences/"
APD_FILES = ["naturalAMPs_APD2024a.fasta", "humanAMPs_APD2024.fasta"]

HAPPENN_PDF = (
    "https://static-content.springer.com/esm/art%3A10.1038%2Fs41598-020-67701-3/"
    "MediaObjects/41598_2020_67701_MOESM1_ESM.pdf"
)

UNIPROT_STREAM = "https://rest.uniprot.org/uniprotkb/stream"
# Keywords marking antimicrobial proteins: Antimicrobial, Antibiotic, Bacteriocin, Defensin,
# Fungicide, Bacteriolytic enzyme. Checked against rest.uniprot.org/keywords/<id>.
AMP_KEYWORDS = ["KW-0929", "KW-0044", "KW-0078", "KW-0211", "KW-0295", "KW-0081"]
_KW_OR = " OR ".join(f"keyword:{k}" for k in AMP_KEYWORDS)
UNIPROT_JOBS = {
    "human_reviewed.fasta": "proteome:UP000005640 AND reviewed:true",
    "swissprot_amp_annotated.fasta": f"reviewed:true AND ({_KW_OR})",
    "swissprot_not_amp.fasta": f"reviewed:true AND NOT ({_KW_OR})",
}


# DRAMP (CC BY 4.0, stated on the download page). The site is only reliably reachable over
# http from some networks; https timed out when tested.
DRAMP_BASE = "http://dramp.cpu-bioinfor.org/downloads/download.php?filename=download_data/DRAMP3.0_new/"
DRAMP_FILES = [
    "general_amps.txt",
    "Antibacterial_amps.txt",
    "Anti-Gram-positive_amps.txt",
    "Anti-Gram-_amps.txt",
    "natural_amps.txt",
    "synthetic_amps.txt",
]


def get_dramp() -> None:
    for name in DRAMP_FILES:
        entry = download_file(
            DRAMP_BASE + name, config.RAW_DIR / "dramp" / name, "DRAMP (CC BY 4.0)", timeout=180
        )
        print("dramp", name, entry["bytes"], "bytes", flush=True)


def get_apd() -> None:
    for name in APD_FILES:
        entry = download_file(APD_BASE + name, config.RAW_DIR / "apd3" / name, "APD3")
        print("apd", name, entry["bytes"], "bytes")


def get_happenn() -> None:
    dest = config.RAW_DIR / "happenn" / "41598_2020_67701_MOESM1_ESM.pdf"
    entry = download_file(HAPPENN_PDF, dest, "HAPPENN supplement (Sci Rep 2020)")
    print("happenn", entry["bytes"], "bytes")


def get_uniprot() -> None:
    for fname, query in UNIPROT_JOBS.items():
        entry = download_file(
            UNIPROT_STREAM,
            config.RAW_DIR / "uniprot" / fname,
            "UniProtKB release 2026_04",
            note=query,
            params={"query": query, "format": "fasta", "compressed": "false"},
            timeout=600,
        )
        print("uniprot", fname, entry["bytes"], "bytes", flush=True)


STEPS = {"apd": get_apd, "dramp": get_dramp, "happenn": get_happenn, "uniprot": get_uniprot}

if __name__ == "__main__":
    wanted = sys.argv[1:] or list(STEPS)
    for step in wanted:
        STEPS[step]()
