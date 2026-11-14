# Data sources

Raw files live in `data/raw/<source>/` (not committed). Every download is recorded with URL,
date and SHA-256 in `data/MANIFEST.json` (committed). Rebuild with
`python scripts/download_data.py apd dramp happenn uniprot` and `python -m amp_triage.data.dbaasp`.

## Downloaded and verified

| Source | Files | What it is | Verified counts | Terms |
|---|---|---|---|---|
| **APD3** (UNMC) | `naturalAMPs_APD2024a.fasta`, `humanAMPs_APD2024.fasta` | Curated natural AMPs. Human set is a subset of the natural set | 3,306 natural (all unique), 154 human; 2,828 natural are 8-50 aa; no non-standard letters | Citation requested (APD3 / APD6). Content copyright UNMC; not committed to git |
| **DRAMP** (CC BY 4.0) | `general_amps.txt` and 5 subset files | AMP repository with activity, target, hemolysis (free text), modifications | general: 12,784 rows, 11,485 unique sequences, 1,837 rows with non-standard letters | CC BY 4.0 (stated on download page). Cite DRAMP |
| **HAPPENN** | supplementary PDF, parsed by `data/happenn.py` | Hemolytic / non-hemolytic labels | 3,738 peptides (1,543 / 2,195); RR90: 823 / 1,100; length 7-35. Matches the paper exactly | Paper supplement. Cite Timmons & Hewage 2020 |
| **UniProt** release 2026_04 | `human_reviewed.fasta`, `swissprot_amp_annotated.fasta`, `swissprot_not_amp.fasta` | Proteome to search; source of negatives | 20,414 / 3,611 / 572,462 records, match the API counts | CC BY 4.0 |
| **DBAASP** | `peptides_list.json` (list view only) | AMP entries, sequences only | 25,542 entries, all unique. 24,867 are monomers; 19,874 of those have standard-letter sequences (17,332 unique, 15,952 of them 8-50 aa). 675 multimer entries hold sequences only inside `monomers` | Free use with acknowledgement (terms page) |

## Findings that affect the design

1. **HAPPENN has same-sequence conflicts, explained by terminal chemistry.** 187 sequences repeat in
   the full set and 19 carry both labels. In all 19 cases the copies differ in the `cTer`/`nTer`
   flag, which fits "same sequence, different terminal modification" (inference, to confirm).
   A sequence-only model cannot see this. The RR90 subset has no duplicates and no conflicts,
   so RR90 is the main set.
2. **DRAMP is mostly not curated experimental data.** The antibacterial file has 28,702 rows:
   16,357 from patents, 5,909 "Candidate" and only 6,164 "General". Using everything as positives
   would mix verified peptides with unverified ones. Positives should be General (plus Clinical,
   Specific) only, with the others tested as a sensitivity check at most.
3. **DRAMP hemolysis is free text** ("Human erythrocytes: <20% Hemolysis =160 µM", 6,966 rows say
   "no information"). It cannot be used as labels without a lot of parsing, which is why HAPPENN
   is the hemolysis source.
4. **Human AMPs are easy to hold out.** APD's 154 human AMPs are a subset of its natural set.
   The human reviewed proteome contains cathelicidin (CAMP, P49913) and beta-defensin 1 (DEFB1,
   P60022), which are good validation targets.
5. **DBAASP's detail API needs one request per peptide.** The list view has sequences only; activity
   and hemolysis measurements need the detail view. Speed varied: 14-60 s per request in one
   test, 1.4 s median later. The crawl below uses 6 workers (about 3.8 requests per second).
6. **DRAMP availability.** `https` timed out in testing and `http` worked, but both timed out at
   other moments. If the site is down, re-run later.

## DBAASP detail data (crawl of 17,886 candidate peptides)

Candidates: single-chain, standard amino acids, 8-50 aa. Stored as gzip JSON per peptide in
`data/raw/dbaasp/details/` (resumable: `python -m amp_triage.data.dbaasp_details`).

First look at 400 records (to be re-checked on the full set):
- **Every record has activity measurements**, but a measurement is not a verdict: DBAASP records
  weak results too (e.g. MIC of 100+ µM). "Positive" needs an explicit threshold on MIC.
  Measure types seen: MIC (most), IC50, MBC, LD50, LC50. Units are µg/ml or µM, so values must
  be converted to one unit before thresholding.
- **Mostly synthetic peptides** (374 of 400 are "Synthetic", 26 "Ribosomal"). That differs from
  the natural encrypted peptides this project searches for, and designed peptides can have
  idealised, easy-to-spot patterns. Natural and synthetic positives should be tracked separately
  and the effect of including synthetic ones tested.
- **231 of 400 have a C-terminal amide.** This supports reading HAPPENN's `cTer` flag as
  C-terminal amidation, but that is still an inference.
- **Hemolysis data exists in a structured form** (185 of 400 have hemolytic/cytotoxic entries,
  with concentration, unit and target cell), so the HAPPENN rule could in principle be applied
  to newer DBAASP data to extend HAPPENN. Optional.
