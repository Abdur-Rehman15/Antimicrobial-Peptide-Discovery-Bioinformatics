"""Scan a whole proteome offline and store it as a "precomputed" run the API serves instantly.

Usage:
    python scripts/precompute_run.py --fasta proteome.fasta --label "E. coli K-12"
    python scripts/precompute_run.py --organism 83333 --label "E. coli K-12 (reviewed)"

A scan runs at about 23,000 windows per second: 1 million residues take about 30 minutes.
(E. coli K-12 has 4,531 reviewed proteins, about 1.4 million residues; human about 11 million.)
The result lands in the same folder as live runs (data/cache/runs) and shows up in
GET /api/runs with kind "precomputed".
"""

import argparse
import sys
import threading
import time

from amp_triage import config
from amp_triage.api.jobs import JobManager, Limits, SyncExecutor
from amp_triage.api.schemas import FastaSource, RunOptions, RunRequest
from amp_triage.api.store import RunStore
from amp_triage.api.uniprot import UniProtClient
from amp_triage.pipeline import Models

parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
source = parser.add_mutually_exclusive_group(required=True)
source.add_argument("--fasta", help="FASTA file with the proteome")
source.add_argument("--organism", type=int, help="UniProt taxon id: all its reviewed proteins")
parser.add_argument("--label", required=True)
parser.add_argument("--top", type=int, default=500, help="candidates to keep (default 500)")
parser.add_argument("--max-overlap", type=float, default=0.5)
args = parser.parse_args()

uniprot = UniProtClient(timeout=300)
if args.fasta:
    text = open(args.fasta, encoding="utf-8").read()
else:
    print(f"downloading reviewed proteins of taxon {args.organism} ...", file=sys.stderr)
    text = uniprot.fetch_organism_fasta(args.organism)

store = RunStore(config.CACHE_DIR / "runs")
print("loading models ...", file=sys.stderr)
models = Models.load()
jobs = JobManager(store, lambda: models, uniprot,
                  Limits(max_residues=100_000_000, max_proteins=1_000_000), SyncExecutor())
request = RunRequest(
    source=FastaSource(type="fasta", text=text),
    options=RunOptions(top_n=args.top, max_overlap=args.max_overlap),
    label=args.label,
)

done = threading.Event()


def report_progress() -> None:
    """The sync executor blocks in submit(), so watch whichever run is newest and running."""
    while not done.wait(15):
        runs = store.list()
        if runs and runs[0]["status"] == "running":
            print(f"  {runs[0]['progress']:5.1%}  {runs[0]['message']}", file=sys.stderr)


threading.Thread(target=report_progress, daemon=True).start()
started = time.time()
run_id = jobs.submit(request, kind="precomputed")
done.set()
meta = store.get(run_id)
print(f"{meta['status']} in {time.time() - started:.0f}s: {meta['n_proteins']} proteins, "
      f"{meta['n_windows']} windows -> run {run_id}")
if meta["status"] != "done":
    sys.exit(f"failed: {meta['error']}")
