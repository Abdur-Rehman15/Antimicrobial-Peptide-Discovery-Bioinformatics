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

## Layout

| Path | What it holds |
|---|---|
| `src/amp_triage/data/` | Downloading and cleaning AMP, hemolysis and UniProt data |
| `src/amp_triage/features/` | Physicochemical descriptors (charge, hydrophobic moment, ...) |
| `src/amp_triage/alignment/` | Smith-Waterman and BLOSUM62, written from scratch |
| `src/amp_triage/candidates/` | Sliding window and charge/hydrophobicity gates |
| `src/amp_triage/models/` | Activity and hemolysis classifiers |
| `src/amp_triage/novelty/` | Novelty check against known AMPs, and the ranking score |
| `src/amp_triage/api/` | FastAPI backend |
| `frontend/` | React dashboard (added in the dashboard phase) |
| `data/` | `raw/`, `interim/`, `processed/`, `cache/`. Rebuilt by scripts, not committed |
| `models/saved/` | Trained models. Not committed |
| `notebooks/` | Exploration and Colab training notebooks |
| `docs/` | Plan and design decisions |
| `tests/` | pytest tests |

Plan: [docs/PLAN.md](docs/PLAN.md). Design decisions: [docs/DECISIONS.md](docs/DECISIONS.md).
