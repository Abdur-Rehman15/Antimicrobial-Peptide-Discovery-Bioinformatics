# Backend API

FastAPI, code in `src/amp_triage/api/`. Start it with

    uvicorn amp_triage.api.main:app --reload        # http://localhost:8000, docs at /docs

The first run loads the models (about 4 seconds); after that they stay in memory. The dashboard
(a Vite dev server on port 5173 by default; set `AMP_CORS_ORIGINS` for other addresses) may call
it from the browser.

## How a run works

1. `POST /api/runs` queues a run and returns its id at once (HTTP 202).
2. One background worker runs jobs one at a time (the scan already uses every CPU core).
3. `GET /api/runs/{id}` shows `status` (queued / running / done / failed), `progress` (0 to 1)
   and a message. Poll it every second or so.
4. When it is `done`, the results can be read, re-ranked, filtered and exported as often as
   wanted. **Nothing is rescanned**: every request re-ranks the saved shortlist.

Runs live in `data/cache/runs/<id>/` (git-ignored) and survive a restart. A run that was still
running when the server died is marked `failed`.

## Where the proteins come from (`source`)

| `type` | Body | Notes |
|---|---|---|
| `fasta` | `{"type": "fasta", "text": ">sp\|P69905\|HBA_HUMAN ...\nMVLSP..."}` | Checked at once; bad input is an HTTP 422 and no run is created |
| `accessions` | `{"type": "accessions", "accessions": ["P69905", "P02788"]}` | Fetched from UniProt, up to 200 |
| `organism` | `{"type": "organism", "taxon_id": 83333, "max_proteins": 100, "seed": 0}` | A random sample of that organism's reviewed (Swiss-Prot) proteins |

`GET /api/organisms?q=escherichia coli` finds organism ids (reviewed proteins only; a full
proteome with unreviewed entries can be 200,000 proteins). If UniProt cannot be reached the
answer is HTTP 503 with a readable message.

## Limits, and why

A scan runs at about 23,000 windows per second, which is about 1 second per protein of 500
residues. A live run may hold at most **100,000 residues** (about 4 minutes) and 5,000 proteins
(`AMP_MAX_RESIDUES` changes the first). A larger input is refused with the expected time.
Whole proteomes are an offline job:

    python scripts/precompute_run.py --organism 83333 --label "E. coli K-12"
    python scripts/precompute_run.py --fasta proteome.fasta --label "My proteome"

The result is stored as a `precomputed` run and appears in `GET /api/runs` like any other.

## Reading results

`GET /api/runs/{id}/results` (JSON, paged with `limit` and `offset`) and
`GET /api/runs/{id}/results.csv` take the same parameters:

| Parameter | Meaning |
|---|---|
| `activity_weight`, `safety_weight`, `novelty_weight` | The exponents a, s, n of the rank formula, 0 to 5 (default 1) |
| `prevalence` | Assumed share of windows that are real AMPs (default 0.001); sets the calibrated `activity` |
| `min_activity`, `max_hemolysis` | Keep candidates with `activity` at least / hemolysis risk at most this |
| `hide_known`, `novelty` | Drop "known" candidates / keep only the listed classes (`novel,related`) |
| `min_length`, `max_length`, `accession` | Length range, one protein |

    rank score = activity ^ a  x  (1 - hemolysis risk) ^ s  x  novelty factor ^ n

(novelty factor: known 0.05, related 0.5, novel 1). Ranks are renumbered after filtering.

Each row has: `rank, accession, start, end` (1-based, inclusive), `length, sequence`,
`activity_score` (raw model score), `activity` (calibrated), `hemolysis_score`, `hemolysis_risk`,
`hemolysis_band` (low / medium / high), `novelty_class`, `max_similarity`, `closest_known`,
`closest_id`, `rank_score`.

`GET /api/runs/{id}/candidate?accession=&start=&end=` adds the 13 main descriptors, the amino
acid composition, the full Smith-Waterman alignment against the closest known AMP, the protein
context and short plain-language notes. `GET /api/runs/{id}/proteins[/{accession}]` lists the
proteins and where their candidates sit, for a protein map.

`GET /api/info` returns the formula, the limits, the test metrics of both models and the caveat
below.

## Reading the numbers honestly

* The activity score is not a probability. Raw scores are overconfident (calibration slope 0.52);
  `activity` is the calibrated version for the assumed rarity. The real rarity is unknown, so
  treat it as an ordering. Changing `prevalence` changes the ranking, because it changes how
  strongly activity counts against safety.
* The hemolysis number is only roughly calibrated (slope 0.59 on the test set, 208 peptides).
  Show the band, not a percentage.
* Short candidates (8-12 residues) are over-represented near the top of a scan: isolated short
  hot spots each count as one candidate. The detail view says so.
* "Novel" means unlike every known AMP, not "probably an AMP". Half of real AMPs are novel in
  this sense.

## Errors

| Code | When |
|---|---|
| 404 | unknown run id, candidate or protein |
| 409 | results asked for while the run is queued / running / failed (the message says which, and why it failed) |
| 422 | unusable input (empty or non-protein FASTA, over the limits) or a parameter out of range |
| 503 | UniProt cannot be reached |
