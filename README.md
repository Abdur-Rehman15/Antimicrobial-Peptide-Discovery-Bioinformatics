# AMP Triage: AI-Assisted Antimicrobial Peptide Discovery

Mines a proteome for hidden antimicrobial peptides (AMPs), scores each candidate for
antimicrobial activity and hemolytic (toxicity) risk, checks novelty with a from-scratch
Smith-Waterman alignment, and shows a ranked dashboard.

Author: Abdur Rehman (23L-0694), FAST Lahore. Bioinformatics semester project.

## Setup (Windows, Python 3.12)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
```

## Run the dashboard

The trained models and datasets are not in git (they are large and rebuilt by the scripts in
`scripts/`; see [docs/DATASETS.md](docs/DATASETS.md)). With them in place:

```powershell
# one-time: build the web dashboard (needs Node 20+)
cd frontend; npm install; npm run build; cd ..

# start everything: API + dashboard on http://localhost:8000
.\.venv\Scripts\python -m uvicorn amp_triage.api.main:app --port 8000
```

Open http://localhost:8000 for the dashboard and http://localhost:8000/docs for the API.
For development run the API as above and `npm run dev` in `frontend/` (http://localhost:5173,
which forwards `/api` to port 8000). Details: [docs/API.md](docs/API.md),
[docs/FRONTEND.md](docs/FRONTEND.md). Tests: `pytest` (Python) and `npm test` (in `frontend/`).

## Layout

| Path | What it holds |
|---|---|
| `src/amp_triage/data/` | Downloading and cleaning AMP, hemolysis and UniProt data |
| `src/amp_triage/features/` | Physicochemical descriptors (charge, hydrophobic moment, ...) |
| `src/amp_triage/alignment/` | Smith-Waterman and BLOSUM62, written from scratch |
| `src/amp_triage/candidates/` | Every window of a proteome with all 35 descriptors, computed in bulk |
| `src/amp_triage/models/` | Activity and hemolysis classifiers |
| `src/amp_triage/novelty/` | Novelty check against 17,492 known AMPs (Smith-Waterman) |
| `src/amp_triage/pipeline/` | Scan, merge overlapping windows, check hemolysis and novelty, rank |
| `src/amp_triage/api/` | FastAPI backend: runs, progress, re-ranking, CSV export |
| `frontend/` | React + TypeScript dashboard (Vite) |
| `data/` | `raw/`, `interim/`, `processed/`, `cache/`. Rebuilt by scripts, not committed |
| `models/saved/` | Trained models. Not committed |
| `notebooks/` | Exploration and Colab training notebooks |
| `docs/` | Plan and design decisions |
| `tests/` | pytest tests |

Plan: [docs/PLAN.md](docs/PLAN.md). Design decisions: [docs/DECISIONS.md](docs/DECISIONS.md).
