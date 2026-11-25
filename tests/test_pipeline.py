import numpy as np
import pandas as pd
import pytest

from amp_triage.candidates.windows import Proteome
from amp_triage.features.descriptors import FEATURE_NAMES, compute_descriptors
from amp_triage.models.calibration import LogisticRecalibrator, shift_prior
from amp_triage.novelty.search import NoveltyIndex
from amp_triage.pipeline import (
    Models,
    RankSettings,
    merge_overlaps,
    rank_candidates,
    run_pipeline,
    scan_proteome,
    with_prevalence,
)

COL = {name: k for k, name in enumerate(FEATURE_NAMES)}


class FakeActivity:
    """Activity grows with net charge: deterministic and easy to check by brute force."""

    def predict_proba(self, X):
        p = 1.0 / (1.0 + np.exp(-0.5 * X[:, COL["net_charge"]]))
        return np.column_stack([1.0 - p, p])


class FakeHemolysis:
    """Risk is the hydrophobic fraction."""

    def predict_proba(self, X):
        p = X[:, COL["hydrophobic_fraction"]]
        return np.column_stack([1.0 - p, p])


def make_protein(seed=0, n=90):
    rng = np.random.default_rng(seed)
    return "".join(rng.choice(list("ACDEFGHIKLMNPQRSTVWY"), n))


def hits(*rows):
    return pd.DataFrame(rows, columns=["accession", "start", "length", "activity"])


# ---- merging ---------------------------------------------------------------------------


def test_overlapping_windows_collapse_to_the_best_one():
    table = hits(("P", 40, 20, 0.9), ("P", 41, 20, 0.8), ("P", 40, 21, 0.7), ("P", 38, 24, 0.6))
    kept = merge_overlaps(table)
    assert kept[["start", "length"]].values.tolist() == [[40, 20]]


def test_far_apart_windows_are_both_kept_best_first():
    kept = merge_overlaps(hits(("P", 5, 10, 0.4), ("P", 100, 10, 0.9)))
    assert kept.start.tolist() == [100, 5]


def test_different_proteins_never_suppress_each_other():
    kept = merge_overlaps(hits(("A", 10, 20, 0.9), ("B", 10, 20, 0.8)))
    assert len(kept) == 2


def test_overlap_is_measured_against_the_shorter_window():
    # a 10-mer sitting entirely inside a 30-mer overlaps 100% of the shorter one
    assert len(merge_overlaps(hits(("P", 0, 30, 0.9), ("P", 10, 10, 0.8)))) == 1
    # sharing 4 of 10 residues is under the 50% limit, so both stay
    assert len(merge_overlaps(hits(("P", 0, 10, 0.9), ("P", 6, 10, 0.8)))) == 2
    # sharing 6 of 10 is over it
    assert len(merge_overlaps(hits(("P", 0, 10, 0.9), ("P", 4, 10, 0.8)))) == 1


def test_top_n_stops_early_and_ties_are_deterministic():
    table = hits(*[("P", 20 * i, 10, 0.5) for i in range(6)])
    kept = merge_overlaps(table, top_n=3)
    assert kept.start.tolist() == [0, 20, 40]


def test_merge_validates_max_overlap_and_handles_empty():
    with pytest.raises(ValueError):
        merge_overlaps(hits(("P", 0, 10, 0.5)), max_overlap=1.5)
    assert merge_overlaps(hits()).empty


# ---- scanning --------------------------------------------------------------------------


def test_scan_matches_scoring_every_window_one_by_one():
    protein = make_protein(1, 60)
    prot = Proteome.from_sequences(["P"], [protein])
    found, n_windows = scan_proteome(prot, FakeActivity(), keep_per_length=10_000)
    brute = []
    for length in range(8, 51):
        for start in range(len(protein) - length + 1):
            seq = protein[start : start + length]
            X = compute_descriptors([seq])[FEATURE_NAMES].to_numpy()
            brute.append((start, length, FakeActivity().predict_proba(X)[0, 1]))
    brute = pd.DataFrame(brute, columns=["start", "length", "activity"])
    merged = found.merge(brute, on=["start", "length"], suffixes=("", "_brute"))
    assert n_windows == len(brute) == len(found) == len(merged)
    assert merged.activity.values == pytest.approx(merged.activity_brute.values, abs=1e-5)


def test_scan_keeps_only_the_best_windows_of_each_length():
    prot = Proteome.from_sequences(["P"], [make_protein(2, 120)])
    full, _ = scan_proteome(prot, FakeActivity(), keep_per_length=10_000)
    small, _ = scan_proteome(prot, FakeActivity(), keep_per_length=3)
    assert small.groupby("length").size().max() == 3
    for length, part in small.groupby("length"):
        best = full[full.length == length].activity.nlargest(3).values
        assert np.sort(part.activity.values)[::-1] == pytest.approx(best, abs=1e-6)


def test_scan_skips_windows_with_nonstandard_residues():
    prot = Proteome.from_sequences(["P"], ["KKKKKKKKKKXKKKKKKKKKK"])
    found, _ = scan_proteome(prot, FakeActivity())
    for start, length in zip(found.start, found.length, strict=True):
        assert not (start <= 10 < start + length)  # no window covers the X at index 10


# ---- ranking ---------------------------------------------------------------------------


def candidates():
    return pd.DataFrame(
        {
            "accession": ["a", "b", "c", "d"],
            "activity": [0.9, 0.9, 0.9, 0.5],
            "hemolysis_risk": [0.1, 0.8, 0.1, 0.0],
            "novelty_class": ["novel", "novel", "known", "novel"],
        }
    )


def test_rank_score_is_the_product():
    ranked = rank_candidates(candidates())
    top = ranked.iloc[0]
    assert top.accession == "a"
    assert top.rank_score == pytest.approx(0.9 * 0.9 * 1.0)
    row_c = ranked[ranked.accession == "c"].iloc[0]
    assert row_c.rank_score == pytest.approx(0.9 * 0.9 * 0.05)


def test_ranks_are_consecutive_and_sorted_best_first():
    ranked = rank_candidates(candidates())
    assert ranked["rank"].tolist() == [1, 2, 3, 4]
    assert ranked.rank_score.is_monotonic_decreasing


def test_zero_weight_switches_a_factor_off():
    ranked = rank_candidates(candidates(), RankSettings(safety=0.0, novelty=0.0))
    assert ranked.rank_score.tolist() == pytest.approx([0.9, 0.9, 0.9, 0.5])


def test_a_bigger_safety_weight_punishes_toxic_candidates_more():
    base = rank_candidates(candidates()).set_index("accession").rank_score
    heavy = rank_candidates(candidates(), RankSettings(safety=3.0)).set_index("accession")
    assert heavy.loc["b", "rank_score"] < base["b"]


def test_filters_drop_rows_and_renumber():
    ranked = rank_candidates(candidates(), max_hemolysis=0.5, hide_known=True)
    assert sorted(ranked.accession) == ["a", "d"]
    assert ranked["rank"].tolist() == [1, 2]


def test_rank_does_not_change_its_input_and_validates_settings():
    table = candidates()
    rank_candidates(table)
    assert "rank_score" not in table.columns
    with pytest.raises(ValueError):
        RankSettings(activity=-1)
    with pytest.raises(ValueError):
        RankSettings(novelty_factor={"known": 0.1})


# ---- the whole pipeline ----------------------------------------------------------------


@pytest.fixture
def models():
    reference = ["GIGKFLHSAKKFGKFGKAFVGEIMNS", "ILPWKWPWWPWRR"]
    return Models(
        activity=FakeActivity(),
        hemolysis=FakeHemolysis(),
        novelty=NoveltyIndex(reference, ids=["ref1", "ref2"]),
        related_cutoff=0.8,
    )


def test_pipeline_returns_a_consistent_ranked_table(models):
    proteins = {"P1": make_protein(3, 150), "P2": make_protein(4, 100)}
    result = run_pipeline(list(proteins), list(proteins.values()), models, top_n=15)
    table = result.table
    assert len(table) == 15 and result.n_proteins == 2
    assert table["rank"].tolist() == list(range(1, 16))
    assert table.rank_score.is_monotonic_decreasing
    for row in table.itertuples():  # position columns agree with the sequence (1-based)
        assert proteins[row.accession][row.start - 1 : row.end] == row.sequence
        assert row.length == len(row.sequence) == row.end - row.start + 1
    assert set(table.novelty_class) <= {"known", "related", "novel"}
    # no two candidates of one protein overlap by more than half the shorter one
    for _, part in table.groupby("accession"):
        spans = list(zip(part.start - 1, part.end, strict=True))
        for i, (s1, e1) in enumerate(spans):
            for s2, e2 in spans[i + 1 :]:
                inter = max(0, min(e1, e2) - max(s1, s2))
                assert inter / min(e1 - s1, e2 - s2) <= 0.5


def test_pipeline_finds_the_best_window_and_labels_a_planted_known_peptide(models):
    # acidic filler has strongly negative charge, so the fake (charge-driven) model must pick
    # windows inside the planted, positively charged peptide
    known = "GIGKFLHSAKKFGKFGKAFVGEIMNS"
    protein = "DE" * 20 + known + "ED" * 20
    table = run_pipeline(["P"], [protein], models, top_n=10).table
    planted = table[table.sequence.apply(lambda s: s in known)]
    assert not planted.empty
    assert (planted.novelty_class == "known").all()
    assert (planted.closest_id == "ref1").all()
    # the most active candidate is inside the planted peptide, but the ranking demotes it: a
    # known peptide is a rediscovery, so the top-ranked candidate is not labelled known
    assert table.sort_values("activity").iloc[-1].sequence in known
    assert table.iloc[0].novelty_class != "known"


def test_pipeline_best_candidate_matches_brute_force(models):
    protein = make_protein(7, 70)
    top = run_pipeline(["P"], [protein], models, top_n=1).table.iloc[0]
    best = -1.0
    for length in range(8, 51):
        for start in range(len(protein) - length + 1):
            seq = protein[start : start + length]
            X = compute_descriptors([seq])[FEATURE_NAMES].to_numpy()
            best = max(best, float(FakeActivity().predict_proba(X)[0, 1]))
    assert top.activity == pytest.approx(best, abs=1e-5)


def test_pipeline_handles_no_valid_windows_and_bad_input(models):
    assert run_pipeline(["P"], ["KKK"], models).table.empty
    with pytest.raises(ValueError):
        run_pipeline(["P", "P"], ["KKKKKKKKKK", "RRRRRRRRRR"], models)
    with pytest.raises(ValueError):
        run_pipeline(["P"], ["KKKKKKKKKK", "RRRRRRRRRR"], models)


def test_progress_goes_from_zero_to_one(models):
    seen = []
    run_pipeline(["P"], [make_protein(8, 80)], models, top_n=5,
                 progress=lambda f, m: seen.append(f))
    assert seen[0] == 0.0 and seen[-1] == 1.0
    assert seen == sorted(seen)


# ---- calibration inside the pipeline ---------------------------------------------------


@pytest.fixture
def calibrated_models(models):
    models.activity_recalibrator = LogisticRecalibrator(intercept=1.2, slope=0.5)
    models.training_prevalence = 0.03
    models.hemolysis_recalibrator = LogisticRecalibrator(intercept=0.1, slope=0.8)
    return models


def test_calibrated_columns_follow_the_formula(calibrated_models):
    protein = make_protein(9, 120)
    table = run_pipeline(["P"], [protein], calibrated_models, top_n=20, prevalence=1e-3).table
    recal = LogisticRecalibrator(1.2, 0.5).apply(table.activity_score.to_numpy())
    expected = shift_prior(recal, 0.03, 1e-3)
    assert table.activity.to_numpy() == pytest.approx(expected)
    assert table.hemolysis_risk.to_numpy() == pytest.approx(
        LogisticRecalibrator(0.1, 0.8).apply(table.hemolysis_score.to_numpy())
    )
    assert (table.activity < table.activity_score).all()  # a rarer target lowers the number


def test_calibration_does_not_change_the_shortlist(models, calibrated_models):
    protein = make_protein(10, 150)
    raw = run_pipeline(["P"], [protein], models, top_n=25).table
    cal = run_pipeline(["P"], [protein], calibrated_models, top_n=25).table
    assert sorted(zip(raw.start, raw.end, strict=True)) == sorted(
        zip(cal.start, cal.end, strict=True)
    )
    best = cal.sort_values("activity_score").iloc[-1]
    assert best.activity == cal.activity.max()  # monotone: same best candidate either way


def test_with_prevalence_matches_running_at_that_prevalence(calibrated_models):
    protein = make_protein(11, 120)
    at_1e3 = run_pipeline(["P"], [protein], calibrated_models, top_n=15, prevalence=1e-3).table
    at_1e4 = run_pipeline(["P"], [protein], calibrated_models, top_n=15, prevalence=1e-4).table
    moved = with_prevalence(at_1e3, calibrated_models, 1e-4)
    assert moved.activity.to_numpy() == pytest.approx(at_1e4.activity.to_numpy())
    assert (moved.activity <= at_1e3.activity).all()
    assert at_1e3.activity.to_numpy() == pytest.approx(
        with_prevalence(at_1e3, calibrated_models, 1e-3).activity.to_numpy()
    )


# ---- the per-residue score profile --------------------------------------------------------


def test_profile_is_the_best_score_covering_each_residue():
    protein = make_protein(12, 70)
    prot = Proteome.from_sequences(["P"], [protein])
    profile = np.zeros(len(prot.codes), dtype=np.float32)
    scan_proteome(prot, FakeActivity(), keep_per_length=5, profile=profile)

    brute = np.zeros(len(protein))
    for length in range(8, 51):
        for start in range(len(protein) - length + 1):
            X = compute_descriptors([protein[start : start + length]])[FEATURE_NAMES].to_numpy()
            score = FakeActivity().predict_proba(X)[0, 1]
            brute[start : start + length] = np.maximum(brute[start : start + length], score)
    # pruning to the best 5 per length must not touch the profile: it sees every window
    assert profile[: len(protein)] == pytest.approx(brute, abs=1e-6)


def test_the_pipeline_keeps_a_profile_for_every_protein_it_shows(models):
    proteins = {"P1": make_protein(13, 120), "P2": make_protein(14, 90)}
    result = run_pipeline(list(proteins), list(proteins.values()), models, top_n=12)
    shown = set(result.table.accession)
    assert set(result.profiles) == shown
    for accession in shown:
        assert len(result.profiles[accession]) == len(proteins[accession])
    # a candidate's own region is at least as high as its score, since it is one of the windows
    for row in result.table.itertuples():
        covered = result.profiles[row.accession][row.start - 1 : row.end]
        assert max(covered) >= row.activity_score - 1e-4  # the stored profile is rounded to 4 dp


def test_a_protein_with_no_valid_window_has_a_flat_profile(models):
    result = run_pipeline(["P"], ["KKKXKKK" * 3], models, top_n=5)
    assert result.table.empty
    assert result.profiles == {}
