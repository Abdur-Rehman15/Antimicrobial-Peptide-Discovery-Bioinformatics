"""Build the table of active (positive) peptides from APD3, DRAMP and DBAASP.

Rules (see docs/DATA_SOURCES.md for the reasoning):
* APD3: every natural AMP.
* DRAMP: only the curated sets (General, Clinical, Specific). Patent and Candidate rows are
  not experimentally verified and are left out.
* DBAASP: peptides whose best definite bacterial MIC is <= 32 µM (see dbaasp_activity.py).
* All sources: sequence of the 20 standard amino acids only, 8-50 residues, no D-amino acids
  (lowercase in DBAASP). DBAASP peptides with lipid or other exotic terminal groups are removed.
* A peptide that DBAASP measured as clearly inactive but that APD3 or DRAMP list as an AMP is a
  conflict. Conflicts are excluded and reported.
"""

from __future__ import annotations

import pandas as pd

from amp_triage import config
from amp_triage.data.apd import load_apd_fasta
from amp_triage.data.dbaasp_activity import (
    MIC_THRESHOLD_UM,
    details_dir,
    load_details,
    summarize_peptide,
)
from amp_triage.data.dramp import load_dramp

STANDARD = set(config.AMINO_ACIDS)
ALLOWED_N_TERM = {None, "ACT"}  # none, or acetyl
ALLOWED_C_TERM = {None, "AMD"}  # none, or amide
DRAMP_CURATED = {"General", "Clinical", "Clincial", "Specific"}  # "Clincial" is DRAMP's typo


def valid_sequence(seq: str) -> bool:
    in_range = config.MIN_PEPTIDE_LEN <= len(seq) <= config.MAX_PEPTIDE_LEN
    return bool(seq) and set(seq) <= STANDARD and in_range


def _terminal(record: dict, key: str) -> str | None:
    value = record.get(key[0].lower() + key[1:]) or record.get(key[0].upper() + key[1:])
    return (value or {}).get("name")


def build_dbaasp(threshold_um: float = MIC_THRESHOLD_UM) -> tuple[pd.DataFrame, dict]:
    """One row per DBAASP peptide that passes the sequence and terminal-group filters."""
    funnel = {"detail_files": 0, "d_amino_acids": 0, "bad_sequence": 0, "exotic_terminal": 0}
    rows = []
    for path in sorted(details_dir().glob("*.json.gz")):
        rec = load_details(path)
        funnel["detail_files"] += 1
        raw = rec.get("sequence") or ""
        if any(c.islower() for c in raw):
            funnel["d_amino_acids"] += 1
            continue
        seq = raw.upper()
        if not valid_sequence(seq) or rec.get("unusualAminoAcids"):
            funnel["bad_sequence"] += 1
            continue
        n_term, c_term = _terminal(rec, "nTerminus"), _terminal(rec, "cTerminus")
        if n_term not in ALLOWED_N_TERM or c_term not in ALLOWED_C_TERM:
            funnel["exotic_terminal"] += 1
            continue
        mic = summarize_peptide(rec, seq, threshold_um)
        organisms = sorted({g.get("source") or "" for g in rec.get("sourceGenes") or []} - {""})
        rows.append(
            {
                "sequence": seq,
                "dbaasp_id": rec["dbaaspId"],
                "origin": "synthetic"
                if (rec.get("synthesisType") or {}).get("name") == "Synthetic"
                else "natural",
                "n_term": n_term,
                "c_term": c_term,
                "mic_status": mic.status,
                "min_mic_um": mic.min_mic_um,
                "n_bacterial_mic": mic.n_bacterial_mic,
                "best_species": mic.best_species,
                "source_organisms": "; ".join(organisms),
                "human_source": any("homo sapiens" in o.lower() for o in organisms),
            }
        )
    return pd.DataFrame(rows), funnel


def build_apd() -> pd.DataFrame:
    nat = load_apd_fasta(config.RAW_DIR / "apd3" / "naturalAMPs_APD2024a.fasta")
    human_ids = set(load_apd_fasta(config.RAW_DIR / "apd3" / "humanAMPs_APD2024.fasta").apd_id)
    nat = nat[nat.sequence.apply(valid_sequence)].copy()
    nat["human_source"] = nat.apd_id.isin(human_ids)
    return nat[["sequence", "apd_id", "human_source"]]


def build_dramp() -> pd.DataFrame:
    ab = load_dramp(config.RAW_DIR / "dramp" / "Antibacterial_amps.txt")
    cur = ab[ab.Dataset.isin(DRAMP_CURATED)].copy()
    cur = cur[cur.Sequence.apply(valid_sequence)]
    cur["origin"] = cur.Source.str.contains("synthetic", case=False).map(
        {True: "synthetic", False: "natural"}
    )
    cur["human_source"] = cur.Source.str.contains("homo sapiens|human", case=False)
    return cur.rename(columns={"Sequence": "sequence", "DRAMP_ID": "dramp_id"})[
        ["sequence", "dramp_id", "origin", "human_source", "Dataset"]
    ]


def merge_positives(dbaasp: pd.DataFrame, apd: pd.DataFrame, dramp: pd.DataFrame):
    """Union of the three sources, one row per distinct sequence, plus a conflict report."""
    db_active = dbaasp[dbaasp.mic_status == "active"]
    db_inactive = set(dbaasp[dbaasp.mic_status == "inactive"].sequence)

    long = pd.concat(
        [
            apd.assign(source="apd3", origin="natural", id=apd.apd_id),
            dramp.assign(source="dramp", id=dramp.dramp_id),
            db_active.assign(source="dbaasp", id=db_active.dbaasp_id),
        ],
        ignore_index=True,
    )[["sequence", "source", "origin", "human_source", "id"]]
    long["human_source"] = long["human_source"].fillna(False).astype(bool)

    merged = long.groupby("sequence").agg(
        sources=("source", lambda s: ";".join(sorted(set(s)))),
        n_sources=("source", "nunique"),
        # a sequence found in nature counts as natural even if another source made it in a lab
        origin=("origin", lambda s: "natural" if (s == "natural").any() else "synthetic"),
        human_source=("human_source", "any"),
        ids=("id", lambda s: ";".join(sorted(set(s)))),
    ).reset_index()
    mic = db_active.groupby("sequence").min_mic_um.min()
    merged["min_mic_um"] = merged.sequence.map(mic)
    merged["length"] = merged.sequence.str.len()

    curated = set(apd.sequence) | set(dramp.sequence)
    conflicts = merged[merged.sequence.isin(curated & db_inactive)]
    merged = merged[~merged.sequence.isin(conflicts.sequence)].reset_index(drop=True)
    return merged, conflicts
