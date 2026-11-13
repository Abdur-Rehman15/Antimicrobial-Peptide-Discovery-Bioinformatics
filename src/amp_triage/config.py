"""Project-wide paths and constants."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
CACHE_DIR = DATA_DIR / "cache"

MODELS_DIR = ROOT / "models" / "saved"
FIGURES_DIR = ROOT / "reports" / "figures"

# Peptide length range used for candidates and training data
MIN_PEPTIDE_LEN = 8
MAX_PEPTIDE_LEN = 50

# The 20 standard amino acids
AMINO_ACIDS = "ACDEFGHIKLMNPQRSTVWY"
