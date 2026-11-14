"""How much does the top of the ranking depend on the (unfitted) weights?

Usage:  python -u scripts/ranking_stability.py

Runs the pipeline once on SAMPLE random human proteins (seed 0) to get a realistic candidate
table, then re-ranks that same table under many weight settings and compares each ranking with
the default one (all exponents 1, novelty factors 0.05 / 0.5 / 1, rarity 1 in 1,000):
  * exponents: activity {0.5, 1, 2} x safety {0, 0.5, 1, 2, 3} x novelty {0, 0.5, 1, 2, 3};
  * novelty factors: known {0, 0.05, 0.2} x related {0.3, 0.5, 0.8};
  * assumed rarity: 1 in 100, 1 in 1,000, 1 in 10,000.
For every setting: how many of the default top 20 / top 50 are still in the top 20 / 50, and the
rank correlation over all candidates. Per candidate: in what share of settings it stays in the
top 20. This measures sensitivity, not correctness: a stable ranking can still be wrong.
Writes reports/ranking_stability.json and data/interim/stability_candidates.csv.
"""

import itertools
import json

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from amp_triage import config
from amp_triage.pipeline import (
    Models,
    RankSettings,
    rank_candidates,
    read_fasta,
    run_pipeline,
    with_prevalence,
)

SEED = 0
SAMPLE = 300
TOP_N = 300
DEFAULT_FACTOR = {"known": 0.05, "related": 0.5, "novel": 1.0}

models = Models.load()
accessions, sequences = read_fasta(config.RAW_DIR / "uniprot" / "human_reviewed.fasta")
rng = np.random.default_rng(SEED)
pick = np.sort(rng.choice(len(accessions), SAMPLE, replace=False))
accessions = [accessions[i] for i in pick]
sequences = [sequences[i] for i in pick]
print(f"{SAMPLE} random human proteins, {sum(map(len, sequences)):,} residues", flush=True)

result = run_pipeline(accessions, sequences, models, top_n=TOP_N,
                      progress=lambda f, m: print(f"  {f:4.0%} {m}", flush=True) if f in (0.9, 1.0)
                      else None)
base = result.table.drop(columns=["rank", "rank_score"])
base.to_csv(config.INTERIM_DIR / "stability_candidates.csv", index=False)
print(f"{result.n_windows:,} windows scored in {result.seconds:.0f}s -> {len(base)} candidates",
      flush=True)
key = base.accession + ":" + base.start.astype(str) + "-" + base.end.astype(str)


def ranked(settings: RankSettings, prevalence: float = 1e-3) -> pd.DataFrame:
    table = base if prevalence == 1e-3 else with_prevalence(base, models, prevalence)
    out = rank_candidates(table, settings)
    out["key"] = out.accession + ":" + out.start.astype(str) + "-" + out.end.astype(str)
    return out


default = ranked(RankSettings())
default_rank = pd.Series(default["rank"].values, index=default.key)
top20, top50 = set(default.key[:20]), set(default.key[:50])

settings = {}
for a, s, n in itertools.product((0.5, 1, 2), (0, 0.5, 1, 2, 3), (0, 0.5, 1, 2, 3)):
    settings[f"a={a} s={s} n={n}"] = (RankSettings(a, s, n), 1e-3, "exponents")
for known, related in itertools.product((0.0, 0.05, 0.2), (0.3, 0.5, 0.8)):
    factor = {"known": known, "related": related, "novel": 1.0}
    settings[f"known={known} related={related}"] = (
        RankSettings(novelty_factor=factor), 1e-3, "novelty factors")
for prevalence in (1e-2, 1e-4):
    settings[f"rarity={prevalence:g}"] = (RankSettings(), prevalence, "rarity")

rows, stays = [], pd.Series(0, index=list(default.key[:20]), dtype=float)
for name, (cfg, prevalence, group) in settings.items():
    r = ranked(cfg, prevalence)
    rank = pd.Series(r["rank"].values, index=r.key)
    in20, in50 = set(r.key[:20]), set(r.key[:50])
    stays[list(top20 & in20)] += 1
    rows.append({
        "setting": name, "group": group,
        "overlap20": len(top20 & in20) / 20, "overlap50": len(top50 & in50) / 50,
        "spearman": float(spearmanr(default_rank, rank.reindex(default_rank.index)).statistic),
    })
res = pd.DataFrame(rows)
stays = (stays / len(settings)).sort_values()

# activity-only ranking versus the default
act_only = ranked(RankSettings(1, 0, 0))
cmp = {
    "default": default.head(20),
    "activity only": act_only.head(20),
}
composition = {
    name: {
        "known": int((t.novelty_class == "known").sum()),
        "related": int((t.novelty_class == "related").sum()),
        "novel": int((t.novelty_class == "novel").sum()),
        "mean_hemolysis_risk": float(t.hemolysis_risk.mean()),
        "mean_activity": float(t.activity.mean()),
    }
    for name, t in cmp.items()
}

summary = {
    "n_candidates": len(base),
    "n_settings": len(res),
    "overlap20": {"median": float(res.overlap20.median()), "min": float(res.overlap20.min()),
                  "p10": float(res.overlap20.quantile(0.1)),
                  "share_at_least_0.8": float((res.overlap20 >= 0.8).mean())},
    "overlap50_median": float(res.overlap50.median()),
    "spearman_median": float(res.spearman.median()),
    "by_group": res.groupby("group")[["overlap20", "overlap50", "spearman"]].median().to_dict(),
    "activity_only_overlap20": float(len(top20 & set(act_only.key[:20])) / 20),
    "composition_top20": composition,
}
(config.ROOT / "reports" / "ranking_stability.json").write_text(json.dumps(summary, indent=1))

print(f"\n=== {len(res)} weight settings compared with the default ranking ===")
print(f"overlap of the top 20: median {res.overlap20.median():.0%}, 10th percentile "
      f"{res.overlap20.quantile(0.1):.0%}, worst {res.overlap20.min():.0%}; "
      f"{(res.overlap20 >= 0.8).mean():.0%} of settings keep at least 16 of the 20")
print(f"overlap of the top 50: median {res.overlap50.median():.0%}; "
      f"rank correlation over all {len(base)} candidates: median {res.spearman.median():.2f}")
print("\nmedian by kind of change:")
print(res.groupby("group")[["overlap20", "overlap50", "spearman"]].median().round(2).to_string())

one = ["a=0.5 s=1 n=1", "a=2 s=1 n=1", "a=1 s=0 n=1", "a=1 s=0.5 n=1", "a=1 s=2 n=1",
       "a=1 s=3 n=1", "a=1 s=1 n=0", "a=1 s=1 n=0.5", "a=1 s=1 n=2", "a=1 s=1 n=3",
       "known=0.0 related=0.5", "known=0.2 related=0.5", "known=0.05 related=0.3",
       "known=0.05 related=0.8", "rarity=0.01", "rarity=0.0001"]
print("\none change at a time (everything else default):")
print(res.set_index("setting").loc[one, ["overlap20", "overlap50", "spearman"]].round(2)
      .to_string())

print("\nthe default top 20: share of settings in which each stays in the top 20")
d20 = default.head(20).assign(stays=[stays.get(k, 0.0) for k in default.key[:20]])
print(d20[["rank", "accession", "start", "end", "length", "activity", "hemolysis_risk",
           "novelty_class", "stays"]].round(3).to_string(index=False))
print("\ncomposition of the top 20:")
print(pd.DataFrame(composition).round(3).to_string())
print(f"\nactivity-only top 20 shares {summary['activity_only_overlap20']:.0%} "
      "of the default top 20")
