"""Why do short windows dominate the merged candidate list when they are few among the hits?

Usage:  python -u scripts/check_region_merge.py   (needs check_length_bias.py to have run)

Rescans the 300 human proteins of ranking_stability.py and keeps the high-scoring windows
(score > the 1-in-10,000 threshold). It then merges them as the pipeline does (best window of
each region) and asks, for every short (8-12) candidate: does its region also contain a longer
window (21+) that scores above the threshold? If so, the short window is the core of a longer
flagged stretch, and picking "the best window" prefers the core.
It also tries a different rule: among the windows of a region that score within MARGIN of the
region's best, keep the LONGEST.
Writes reports/region_merge.json.
"""

import json

import joblib
import numpy as np
import pandas as pd

from amp_triage import config
from amp_triage.candidates.window_features import iter_proteome_chunks
from amp_triage.pipeline import merge_overlaps, read_fasta, scan_proteome

SEED, SAMPLE, TOP = 0, 300, 300
MARGIN = 0.01
BANDS = [(8, 12), (13, 20), (21, 35), (36, 50)]
thr = json.loads((config.ROOT / "reports" / "length_bias.json").read_text())[
    "B_global_threshold"]["0.0001"]["threshold"]

model = joblib.load(config.MODELS_DIR / "activity_final.joblib")
accs, seqs = read_fasta(config.RAW_DIR / "uniprot" / "human_reviewed.fasta")
pick = np.sort(np.random.default_rng(SEED).choice(len(accs), SAMPLE, replace=False))
accs, seqs = [accs[i] for i in pick], [seqs[i] for i in pick]

pool = []
for chunk in iter_proteome_chunks(accs, seqs):  # chunks, not single proteins: far faster
    hits, _ = scan_proteome(chunk, model, keep_per_length=10**9)  # nothing is cut
    pool.append(hits[hits.activity > thr])
    print("chunk done", flush=True)
pool = pd.concat(pool, ignore_index=True)
print(f"{len(pool):,} windows above the threshold ({thr:.3f})", flush=True)


def share(lengths: pd.Series) -> dict:
    return {f"{lo}-{hi}": float(lengths.between(lo, hi).mean()) for lo, hi in BANDS}


kept = merge_overlaps(pool, max_overlap=0.5, top_n=TOP)
out = {"threshold": thr, "n_hits": len(pool),
       "hits_by_band": share(pool.length), "best_window_rule": share(kept.length)}

# for each kept window: what else flagged lies in its region?
longest_in_region, n_in_region = [], []
for r in kept.itertuples():
    same = pool[pool.accession == r.accession]
    end = r.start + r.length
    inter = np.minimum(end, same.start + same.length) - np.maximum(r.start, same.start)
    near = same[(inter > 0) & (inter / np.minimum(r.length, same.length) > 0.5)]
    longest_in_region.append(int(near.length.max()))
    n_in_region.append(len(near))
kept["longest_flagged_in_region"] = longest_in_region
kept["flagged_windows_in_region"] = n_in_region
short = kept[kept.length <= 12]
out["short_candidates"] = {
    "n": len(short),
    "share_with_a_flagged_window_of_21_plus_in_region": float(
        (short.longest_flagged_in_region >= 21).mean()),
    "median_longest_flagged_in_region": float(short.longest_flagged_in_region.median()),
    "median_flagged_windows_in_region": float(short.flagged_windows_in_region.median()),
}

# alternative rule: longest window among those within MARGIN of the region's best
ordered = pool.sort_values("activity", ascending=False, kind="stable")
chosen, taken = [], {}
for r in ordered.itertuples():
    end = r.start + r.length
    if any(min(end, e) - max(r.start, s) > 0
           and (min(end, e) - max(r.start, s)) / min(r.length, e - s) > 0.5
           for s, e in taken.get(r.accession, [])):
        continue
    near = ordered[(ordered.accession == r.accession) & (ordered.activity >= r.activity - MARGIN)]
    inter = np.minimum(end, near.start + near.length) - np.maximum(r.start, near.start)
    near = near[(inter > 0) & (inter / np.minimum(r.length, near.length) > 0.5)]
    pick_row = near.sort_values("length", ascending=False, kind="stable").iloc[0]
    chosen.append(pick_row)
    taken.setdefault(r.accession, []).append((r.start, end))
    taken[r.accession].append((pick_row.start, pick_row.start + pick_row.length))
    if len(chosen) >= TOP:
        break
longest = pd.DataFrame(chosen)
out["longest_within_margin_rule"] = share(longest.length)
out["median_length"] = {"hits": float(pool.length.median()),
                        "best_window_rule": float(kept.length.median()),
                        "longest_within_margin_rule": float(longest.length.median())}
(config.ROOT / "reports" / "region_merge.json").write_text(json.dumps(out, indent=1))

table = pd.DataFrame({
    "all flagged windows": out["hits_by_band"],
    "candidates: best window of region": out["best_window_rule"],
    f"candidates: longest within {MARGIN} of best": out["longest_within_margin_rule"],
}).T
print("\n=== share of each length band ===")
print(table.round(3).to_string())
print("\nmedian length:", {k: round(v) for k, v in out["median_length"].items()})
print("\nshort (8-12) candidates:", out["short_candidates"])
