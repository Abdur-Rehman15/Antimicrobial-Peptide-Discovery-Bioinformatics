"""Step 5: combine activity, safety and novelty into one ranking.

    rank score = activity ** a  *  (1 - hemolysis risk) ** s  *  novelty_factor ** n

A product, not a sum: a weighted sum would let high activity make up for high toxicity or for a
candidate that is already known. With a product a poor value on any one factor pulls the whole
candidate down. The exponents (a, s, n) default to 1; 0 switches a factor off and larger values
make it count more. The dashboard sliders set them.

There is no ground truth for "the best candidate", so the weights are NOT fitted to anything. The
defaults are a neutral starting point, and the report checks how stable the top of the list is
when they change. Note that activity and hemolysis risk are model scores, not calibrated
probabilities.

The novelty factor depends on the label from novelty/search.py: known (a rediscovery) is nearly
removed, related is halved, novel is unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import pandas as pd

DEFAULT_NOVELTY_FACTOR = {"known": 0.05, "related": 0.5, "novel": 1.0}


@dataclass(frozen=True)
class RankSettings:
    activity: float = 1.0  # exponent of the activity score
    safety: float = 1.0  # exponent of (1 - hemolysis risk)
    novelty: float = 1.0  # exponent of the novelty factor
    novelty_factor: Mapping[str, float] = field(
        default_factory=lambda: dict(DEFAULT_NOVELTY_FACTOR)
    )

    def __post_init__(self):
        for name in ("activity", "safety", "novelty"):
            if getattr(self, name) < 0:
                raise ValueError(f"the {name} weight cannot be negative")
        missing = set(DEFAULT_NOVELTY_FACTOR) - set(self.novelty_factor)
        if missing:
            raise ValueError(f"novelty_factor is missing {sorted(missing)}")


def rank_candidates(
    table: pd.DataFrame,
    settings: RankSettings | None = None,
    max_hemolysis: float | None = None,
    hide_known: bool = False,
) -> pd.DataFrame:
    """Add `rank_score` and `rank` (1 = best) to a candidate table, best first.

    `table` needs activity, hemolysis_risk and novelty_class. `max_hemolysis` drops candidates
    with a higher risk, `hide_known` drops the ones labelled known. Ranks are renumbered after
    filtering, so this is cheap to rerun when a slider moves.
    """
    settings = settings or RankSettings()
    out = table.copy()
    if max_hemolysis is not None:
        out = out[out.hemolysis_risk <= max_hemolysis]
    if hide_known:
        out = out[out.novelty_class != "known"]
    factor = out.novelty_class.map(settings.novelty_factor).astype(float)
    out["rank_score"] = (
        out.activity.astype(float) ** settings.activity
        * (1.0 - out.hemolysis_risk.astype(float)) ** settings.safety
        * factor**settings.novelty
    )
    out = out.sort_values("rank_score", ascending=False, kind="stable").reset_index(drop=True)
    out["rank"] = range(1, len(out) + 1)
    return out
