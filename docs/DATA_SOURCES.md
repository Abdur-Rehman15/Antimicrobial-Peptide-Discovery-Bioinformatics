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

## DBAASP detail data (complete: 17,886 candidate peptides)

Candidates: single-chain, standard amino acids, 8-50 aa. Stored untouched as gzip JSON, one file
per peptide, in `data/raw/dbaasp/details/` (resumable: `python -m amp_triage.data.dbaasp_details`).
All 17,886 files were checked: none corrupt, ids match. A burst of 186 connection errors during
the run was fixed by a second pass over the missing ids.

Findings on the full set:
- **Almost all have activity measurements** (only 296, or 1.7%, have none), but a measurement is
  not a verdict: DBAASP records weak results too. "Positive" needs an explicit threshold on MIC.
  Measure types: MIC (101,688 entries), MBC, IC50, LC, MIC50, MFC. Units are µM or µg/ml, and
  8,441 entries have **no unit at all**, so they cannot be converted and must be dropped.
- **84% are synthetic** (15,001 synthetic, 2,854 ribosomal, 31 nonribosomal). That differs from
  the natural encrypted peptides this project searches for, and designed peptides can have
  idealised patterns. Natural and synthetic positives should be tracked separately, and the
  effect of including synthetic ones tested.
- **1,399 sequences contain lowercase letters, which DBAASP uses for D-amino acids.** A
  sequence-only model cannot represent these, so they are excluded at cleaning time.
- **8,407 have a C-terminal modification** (mostly amide). This supports reading HAPPENN's `cTer`
  flag as C-terminal amidation, but that is still an inference.
- **Structured hemolysis data exists for 10,397 peptides (58%), 9,418 of them on erythrocytes**,
  with concentration, unit and cell type. In principle the HAPPENN rule could be applied to it to
  extend HAPPENN. Optional.
- 10,114 peptides link to a UniProt entry (useful for telling natural from designed peptides).

## Cleaned positives (`python scripts/build_positives.py`, 12,075 distinct sequences)

Output: `data/processed/positives.csv` (one row per distinct sequence, with sources, natural or
synthetic origin, minimum MIC, and human hold-out flags). Per-source tables are in
`data/interim/`. Code: `data/positives.py`, `data/dbaasp_activity.py`, `data/holdout.py`.

**Rule for "active":** the best definite bacterial MIC is at most **32 µM**.

| Step | Result |
|---|---|
| DBAASP detail files | 17,886 |
| removed: D-amino acids (lowercase) | 1,399 |
| removed: lipid or other exotic terminal groups (only free, acetyl N-term and free, amide C-term kept) | 527 |
| DBAASP peptides kept | 15,960: **9,775 active**, 2,407 clearly inactive, 174 ambiguous, 3,604 with no usable bacterial MIC |
| APD3 (8-50 aa, standard letters) | 2,828 |
| DRAMP curated sets (General, Clinical, Specific), 8-50 aa | 4,772 |
| Union, distinct sequences | 12,387 |
| removed: **312 conflicts** (APD3/DRAMP list it as AMP, DBAASP measured it clearly above 32 µM) | 12,075 left |

Final positives: **4,254 natural, 7,821 synthetic** (a sequence found in nature counts as natural
even if DBAASP lists a lab-made copy).

How MIC is read (all unit-tested): only bacterial MIC entries count (fungi, parasites, viruses,
cells are excluded by genus); ranges use the upper end; "MIC > v" is never evidence of activity;
µg/ml is converted to µM with the peptide's molecular weight; unit-less placeholder entries
(value 1,111,111) are dropped. DBAASP's own `activity` number is always µg/ml: it agrees with
our molecular-weight conversion for 98% of entries.

About the 312 conflicts: spot checks show the DBAASP data really is weak (for example
`FPVTWPTKWLKG`: MIC > 250 µg/ml against *E. coli* and *S. aureus*). The curated lists include
peptides that work poorly in the lab, so these are removed rather than trusted either way.
They are listed in `data/interim/positive_conflicts.csv`.

**Human hold-out: 297 positives.** 109 are labelled human by a database. A further 188 are not
labelled human but occur word-for-word inside a human reviewed protein (mostly lab-made
fragments of human proteins, e.g. pieces of beta-defensin 1 recorded as "synthetic"). Using the
labels alone would have leaked human sequences into training. LL-37 (inside cathelicidin, P49913)
is among those held out. Similar-but-not-identical peptides (for example from other species) are
handled later by clustering, so that a whole similar group is held out together.

## Open points before negatives and the split

* **Negatives must be drawn from windows that pass the same filters as real candidates.**
  Random protein fragments are mostly not positively charged, so a model could separate them
  from AMPs by charge alone and then fail on the real task. So the charge and hydrophobicity
  filters (and the descriptors behind them) come before the negatives.
* **Near-duplicates inside the positives** (for example peptides padded with extra alanines)
  need clustering. The same clusters are used to split train and test.
