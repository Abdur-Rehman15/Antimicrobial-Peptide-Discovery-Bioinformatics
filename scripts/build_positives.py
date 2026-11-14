"""Build the table of active peptides.  Usage:  python scripts/build_positives.py

Writes data/interim/{dbaasp,apd3,dramp}_peptides.csv and data/processed/positives.csv and
prints how many peptides each step keeps.
"""

from __future__ import annotations

from amp_triage import config
from amp_triage.data.holdout import find_in_proteins
from amp_triage.data.positives import build_apd, build_dbaasp, build_dramp, merge_positives


def main() -> None:
    config.INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    dbaasp, funnel = build_dbaasp()
    apd, dramp = build_apd(), build_dramp()
    dbaasp.to_csv(config.INTERIM_DIR / "dbaasp_peptides.csv", index=False)
    apd.to_csv(config.INTERIM_DIR / "apd3_peptides.csv", index=False)
    dramp.to_csv(config.INTERIM_DIR / "dramp_peptides.csv", index=False)

    print("DBAASP filters:", funnel)
    print("  kept:", len(dbaasp), "| MIC status:", dbaasp.mic_status.value_counts().to_dict())
    print("APD3 kept (8-50 aa, standard):", len(apd), "| human:", int(apd.human_source.sum()))
    print("DRAMP curated kept:", len(dramp), "| human:", int(dramp.human_source.sum()))

    positives, conflicts = merge_positives(dbaasp, apd, dramp)

    # Human hold-out: labelled human by a database, OR word-for-word inside a human protein.
    hits = find_in_proteins(positives.sequence, config.RAW_DIR / "uniprot" / "human_reviewed.fasta")
    positives["in_human_protein"] = positives.sequence.isin(hits)
    positives["human_protein"] = positives.sequence.map(hits)
    positives["holdout_human"] = positives.human_source | positives.in_human_protein
    positives.to_csv(config.PROCESSED_DIR / "positives.csv", index=False)
    conflicts.to_csv(config.INTERIM_DIR / "positive_conflicts.csv", index=False)
    print("\nconflicts (curated AMP list says AMP, DBAASP measured inactive):", len(conflicts))
    print("POSITIVES:", len(positives), "distinct sequences")
    print("  by origin:", positives.origin.value_counts().to_dict())
    print("  by source combination:", positives.sources.value_counts().to_dict())
    print("  labelled human by a database:", int(positives.human_source.sum()))
    print("  inside a human protein:", int(positives.in_human_protein.sum()))
    print("  HELD OUT for human validation (either):", int(positives.holdout_human.sum()))


if __name__ == "__main__":
    main()
