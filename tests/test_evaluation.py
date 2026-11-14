import numpy as np
import pytest

from amp_triage.models.evaluation import (
    precision_at_prevalence,
    recall_at_fpr,
    summarize,
    summarize_by_origin,
)


def test_precision_formula_by_hand():
    # recall 0.5, fpr 0.01, 1 in 100 windows are AMPs: tp=0.005, fp=0.0099
    assert precision_at_prevalence(0.5, 0.01, 0.01) == pytest.approx(0.005 / (0.005 + 0.0099))


def test_precision_is_one_without_false_positives():
    assert precision_at_prevalence(0.3, 0.0, 0.001) == 1.0


def test_precision_drops_when_the_target_gets_rarer():
    assert precision_at_prevalence(0.5, 0.001, 1e-4) < precision_at_prevalence(0.5, 0.001, 1e-2)


def test_recall_at_fpr_hand_example():
    neg = np.arange(1000) / 1000.0  # 0.000 ... 0.999
    pos = np.array([0.5, 0.995, 0.9995, 2.0])
    recall, fpr = recall_at_fpr(pos, neg, 0.01)  # threshold is about 0.989
    assert recall == pytest.approx(0.75)
    assert fpr == pytest.approx(0.01, abs=0.002)


def test_perfect_scores():
    y = np.array([0] * 200 + [1] * 20)
    s = np.where(y == 1, 0.9, 0.1)
    r = summarize(y, s)
    assert r["roc_auc"] == 1.0 and r["pr_auc"] == 1.0
    assert r["recall@fpr=0.001"] == 1.0


def test_random_scores_give_chance_level():
    rng = np.random.default_rng(0)
    y = np.array([0] * 20000 + [1] * 2000)
    r = summarize(y, rng.random(len(y)))
    assert r["roc_auc"] == pytest.approx(0.5, abs=0.02)


def test_weight_of_one_changes_nothing():
    rng = np.random.default_rng(1)
    y = np.array([0] * 3000 + [1] * 300)
    s = rng.random(len(y)) + 0.4 * y
    plain, weighted = summarize(y, s), summarize(y, s, np.ones(len(y)))
    for key in ("roc_auc", "pr_auc"):
        assert plain[key] == pytest.approx(weighted[key])
    assert weighted["recall@fpr=0.001"] == pytest.approx(plain["recall@fpr=0.001"], abs=0.01)


def test_weighting_negatives_equals_repeating_them():
    """Weight 5 on a negative must behave like five copies of it."""
    rng = np.random.default_rng(2)
    neg_a, neg_b = rng.random(2000), rng.random(500)  # a: weight 1, b: weight 5
    pos = rng.random(100) + 0.3
    y = np.array([0] * 2500 + [1] * 100)
    score = np.concatenate([neg_a, neg_b, pos])
    weight = np.concatenate([np.ones(2000), np.full(500, 5.0), np.ones(100)])
    copies = np.concatenate([neg_a, np.repeat(neg_b, 5), pos])
    y_copies = np.array([0] * (2000 + 2500) + [1] * 100)
    weighted = summarize(y, score, weight)
    repeated = summarize(y_copies, copies)
    for key in ("roc_auc", "pr_auc", "recall@fpr=0.001"):
        assert weighted[key] == pytest.approx(repeated[key], abs=1e-6)


def test_by_origin_scores_each_kind_against_the_same_negatives():
    y = np.array([0] * 100 + [1] * 10 + [1] * 10)
    origin = np.array(["random_window"] * 100 + ["natural"] * 10 + ["synthetic"] * 10)
    s = np.concatenate([np.linspace(0, 0.5, 100), np.full(10, 0.9), np.full(10, 0.1)])
    r = summarize_by_origin(y, s, origin)
    assert r["natural"]["roc_auc"] == 1.0
    assert r["synthetic"]["roc_auc"] < 0.5
    assert r["natural"]["n_neg"] == r["synthetic"]["n_neg"] == 100
    assert r["all"]["n_pos"] == 20
