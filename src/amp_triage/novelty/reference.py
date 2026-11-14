"""The reference set for novelty: every peptide the literature already calls an AMP.

A candidate is only a discovery if it is not already known, so "known" is deliberately broad.
It is the union of
  * APD3 natural AMPs,
  * DRAMP curated sets (General, Clinical, Specific),
  * DBAASP peptides of any measured status (active, weak, inactive, no data),
restricted to the 20 standard amino acids, 8-50 residues, no D-amino acids, no exotic terminal
groups, one row per distinct sequence. Weakly active or inactive DBAASP entries are kept on
purpose: a candidate that is a near-copy of any published AMP candidate is not new.

This is a wider set than the training positives (which need MIC <= 32 uM).
Build once with scripts/build_known_amps.py; load with `load_known_amps()`.
"""

from __future__ import annotations

import pandas as pd

from amp_triage import config
from amp_triage.data.positives import build_apd, build_dbaasp, build_dramp

PATH = config.PROCESSED_DIR / "known_amps.csv"


def build_known_amps() -> pd.DataFrame:
    """One row per distinct known AMP: sequence, sources, ids."""
    dbaasp, _ = build_dbaasp()
    apd, dramp = build_apd(), build_dramp()
    long = pd.concat(
        [
            apd.assign(source="apd3", id=apd.apd_id),
            dramp.assign(source="dramp", id=dramp.dramp_id),
            dbaasp.assign(source="dbaasp", id=dbaasp.dbaasp_id),
        ],
        ignore_index=True,
    )[["sequence", "source", "id"]]
    known = (
        long.groupby("sequence")
        .agg(
            sources=("source", lambda s: ";".join(sorted(set(s)))),
            ids=("id", lambda s: ";".join(sorted(set(s)))),
        )
        .reset_index()
    )
    known["length"] = known.sequence.str.len()
    return known.sort_values("sequence").reset_index(drop=True)


def load_known_amps() -> pd.DataFrame:
    if not PATH.exists():
        raise FileNotFoundError(f"{PATH} not found: run python scripts/build_known_amps.py")
    return pd.read_csv(PATH)
