"""DBAASP per-peptide detail download (activity and hemolysis measurements).

Fetches https://dbaasp.org/peptides/{id} for the peptides worth using as training or reference
data: single-chain, standard amino acids only, 8-50 residues (see candidate_ids). Each response
is stored untouched as gzip JSON in data/raw/dbaasp/details/{id}.json.gz, so a run can be
interrupted and resumed, and the raw data is kept for re-parsing later.

The server is slow and sometimes times out. Use few workers. Ids that fail are simply left
without a file and picked up on the next run.

Usage:
    python -m amp_triage.data.dbaasp_details --limit 40     # speed test on a random sample
    python -m amp_triage.data.dbaasp_details                # everything remaining
"""

from __future__ import annotations

import argparse
import gzip
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from amp_triage import config
from amp_triage.data.download import get_with_retry

DETAIL_URL = "https://dbaasp.org/peptides/{id}"
LIST_PATH = config.RAW_DIR / "dbaasp" / "peptides_list.json"
DETAILS_DIR = config.RAW_DIR / "dbaasp" / "details"
WORKERS = 4
STANDARD = set(config.AMINO_ACIDS)


def candidate_ids(list_path: Path = LIST_PATH) -> list[int]:
    """Ids of single-chain peptides with a standard-amino-acid sequence of 8-50 residues."""
    records = json.loads(list_path.read_text())["data"]
    ids = []
    for r in records:
        seq = (r.get("sequence") or "").upper()
        if (
            r.get("complexity") == "monomer"
            and config.MIN_PEPTIDE_LEN <= len(seq) <= config.MAX_PEPTIDE_LEN
            and set(seq) <= STANDARD
        ):
            ids.append(r["id"])
    return ids


def _path(pid: int) -> Path:
    return DETAILS_DIR / f"{pid}.json.gz"


def fetch_one(pid: int) -> float:
    """Download one peptide's detail JSON. Returns seconds taken."""
    t0 = time.time()
    resp = get_with_retry(DETAIL_URL.format(id=pid), timeout=90, tries=4)
    data = resp.json()  # validate before saving
    if data.get("id") != pid:
        raise ValueError(f"asked for {pid}, got {data.get('id')}")
    tmp = _path(pid).with_suffix(".part")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(data, f)
    tmp.replace(_path(pid))
    return time.time() - t0


def run(limit: int | None = None, workers: int = WORKERS, seed: int = 0) -> None:
    DETAILS_DIR.mkdir(parents=True, exist_ok=True)
    ids = candidate_ids()
    todo = [i for i in ids if not _path(i).exists()]
    if limit:
        random.Random(seed).shuffle(todo)
        todo = todo[:limit]
    print(f"candidates={len(ids)} already_done={len(ids) - len(todo)} to_fetch={len(todo)}",
          flush=True)

    ok, failed, times = 0, [], []
    t_start = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_one, i): i for i in todo}
        for fut in as_completed(futures):
            pid = futures[fut]
            try:
                times.append(fut.result())
                ok += 1
            except (requests.RequestException, ValueError) as exc:
                failed.append(pid)
                print(f"FAILED id={pid}: {type(exc).__name__}", flush=True)
            n = ok + len(failed)
            if n % 100 == 0 or n == len(todo):
                rate = ok / (time.time() - t_start)
                print(f"{n}/{len(todo)} ok={ok} failed={len(failed)} "
                      f"rate={rate:.2f}/s eta={(len(todo) - n) / max(rate, 1e-9) / 60:.0f}min",
                      flush=True)
    if times:
        times.sort()
        print(f"per-request seconds: median={times[len(times) // 2]:.1f} max={times[-1]:.1f}")
    print(f"done. ok={ok} failed={len(failed)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=WORKERS)
    args = ap.parse_args()
    run(limit=args.limit, workers=args.workers)
