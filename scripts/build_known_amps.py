"""Build the reference set of known AMPs used for novelty.

Usage:  python scripts/build_known_amps.py
Writes data/processed/known_amps.csv (see src/amp_triage/novelty/reference.py).
"""

import pandas as pd

from amp_triage import config
from amp_triage.novelty.reference import PATH, build_known_amps

known = build_known_amps()
known.to_csv(PATH, index=False)

positives = pd.read_csv(config.PROCESSED_DIR / "positives.csv")
in_ref = positives.sequence.isin(set(known.sequence))
print(f"known AMPs: {len(known):,} distinct sequences -> {PATH}")
print(known.sources.value_counts().to_string())
print(f"\nthe {len(positives):,} training positives are all in it: {bool(in_ref.all())}")
print(f"length range {known.length.min()}-{known.length.max()}, median {known.length.median():.0f}")
