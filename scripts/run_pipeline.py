"""Run proteins through the whole pipeline and write the ranked candidates.

Usage:  python scripts/run_pipeline.py proteins.fasta [--top 200] [--out candidates.csv]

Needs the saved models (models/saved/activity_final.joblib, hemolysis_final.joblib), the known-AMP
reference (scripts/build_known_amps.py) and reports/novelty_calibration.json.
"""

import argparse
import sys
import time

import pandas as pd

from amp_triage.pipeline import Models, read_fasta, run_pipeline

parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
parser.add_argument("fasta", help="FASTA file with one or more proteins")
parser.add_argument("--top", type=int, default=200, help="how many candidates to keep")
parser.add_argument("--max-overlap", type=float, default=0.5,
                    help="windows overlapping a better one by more than this share are merged")
parser.add_argument("--out", help="write the ranked candidates to this CSV file")
args = parser.parse_args()

t = time.time()
models = Models.load()
print(f"models loaded in {time.time() - t:.0f}s", file=sys.stderr)
accessions, sequences = read_fasta(args.fasta)
last = [0.0]


def show(fraction: float, message: str) -> None:
    if fraction - last[0] >= 0.1 or fraction == 1.0:
        print(f"  {fraction:4.0%}  {message}", file=sys.stderr)
        last[0] = fraction


result = run_pipeline(accessions, sequences, models, top_n=args.top,
                      max_overlap=args.max_overlap, progress=show)
print(f"{result.n_proteins:,} proteins, {result.n_windows:,} windows scored in "
      f"{result.seconds:.0f}s -> {len(result.table)} candidates", file=sys.stderr)
if args.out:
    result.table.to_csv(args.out, index=False)
    print(f"written to {args.out}", file=sys.stderr)
with pd.option_context("display.width", 200, "display.max_colwidth", 30):
    print(result.table.head(15).round(3).to_string(index=False))
