import numpy as np
import pytest

from amp_triage.models.calibration import (
    EVEN_EDGES,
    LogisticRecalibrator,
    brier,
    calibration_fit,
    expected_calibration_error,
    negative_weight,
    reliability_table,
    shift_prior,
    sigmoid,
    summarize,
)
from amp_triage.models.cv import purge_training_rows


def simulated(n=200_000, sharpen=1.0, seed=0):
    """Scores p and outcomes drawn from the TRUE probability; `sharpen` makes p over-confident."""
    rng = np.random.default_rng(seed)
    true_p = rng.beta(0.6, 3.0, n)
    y = (rng.random(n) < true_p).astype(int)
    z = np.log(true_p / (1 - true_p)) * sharpen
    return y, sigmoid(z), true_p


def test_calibrated_scores_have_slope_one_intercept_zero():
    y, p, _ = simulated()
    intercept, slope = calibration_fit(y, p)
    assert slope == pytest.approx(1.0, abs=0.03)
    assert intercept == pytest.approx(0.0, abs=0.03)


def test_overconfident_scores_have_slope_below_one():
    y, p, _ = simulated(sharpen=2.0)
    assert calibration_fit(y, p)[1] == pytest.approx(0.5, abs=0.05)


def test_reliability_table_matches_a_hand_example():
    y = np.array([0, 0, 1, 1, 1])
    p = np.array([0.1, 0.1, 0.9, 0.9, 0.9])
    t = reliability_table(y, p, edges=EVEN_EDGES)
    low, high = t.iloc[0], t.iloc[1]
    assert (low.n, low.mean_predicted, low.observed) == (2, pytest.approx(0.1), 0.0)
    assert (high.n, high.mean_predicted, high.observed) == (3, pytest.approx(0.9), 1.0)
    assert expected_calibration_error(t) == pytest.approx((2 * 0.1 + 3 * 0.1) / 5)


def test_weights_act_like_repeated_rows():
    y = np.array([0, 1, 1, 0])
    p = np.array([0.2, 0.7, 0.6, 0.4])
    w = np.array([3.0, 1.0, 1.0, 1.0])
    repeated_y, repeated_p = np.repeat(y, w.astype(int)), np.repeat(p, w.astype(int))
    assert brier(y, p, w) == pytest.approx(brier(repeated_y, repeated_p))
    a = reliability_table(y, p, w, EVEN_EDGES)
    b = reliability_table(repeated_y, repeated_p, None, EVEN_EDGES)
    assert a.mean_predicted.tolist() == pytest.approx(b.mean_predicted.tolist())
    assert a.observed.tolist() == pytest.approx(b.observed.tolist())


def test_brier_by_hand():
    assert brier([1, 0], [0.8, 0.3]) == pytest.approx((0.04 + 0.09) / 2)


def test_prior_shift_arithmetic():
    assert shift_prior([0.5], 0.1, 0.1) == pytest.approx([0.5])
    # same odds ratio both ways: 0.5 at prior 0.5 -> odds 1; at prior 0.01 odds 1/99
    assert shift_prior([0.5], 0.5, 0.01) == pytest.approx([0.01])
    assert shift_prior([0.9], 0.5, 0.01)[0] < 0.9  # rarer positives -> lower score


def test_prior_shift_makes_scores_right_at_the_new_balance():
    """Train on a 50/50 balance, apply to 1 in 20: shifted scores must be calibrated there."""
    rng = np.random.default_rng(1)
    n = 400_000
    y = (rng.random(n) < 0.05).astype(int)  # the real world: 5% positives
    feature = rng.normal(loc=1.5 * y, scale=1.0)
    # exact posterior if the classes were balanced: likelihood ratio of two unit-variance normals
    p_balanced = sigmoid(1.5 * feature - 1.125)
    shifted = shift_prior(p_balanced, 0.5, 0.05)
    assert calibration_fit(y, shifted)[1] == pytest.approx(1.0, abs=0.05)
    assert calibration_fit(y, shifted)[0] == pytest.approx(0.0, abs=0.08)
    assert abs(calibration_fit(y, p_balanced)[0]) > 2.0  # unshifted scores are far off


def test_negative_weight_gives_the_requested_prevalence():
    n_pos, n_neg = 1000, 100_000
    w = negative_weight(n_pos, n_neg, 0.001)
    assert n_pos / (n_pos + w * n_neg) == pytest.approx(0.001)


def test_recalibrator_repairs_overconfident_scores():
    y, p, true_p = simulated(sharpen=2.0)
    fixed = LogisticRecalibrator.fit(y, p).apply(p)
    assert abs(calibration_fit(y, fixed)[1] - 1.0) < 0.03
    assert abs(brier(y, fixed) - brier(y, true_p)) < 0.002
    assert brier(y, fixed) < brier(y, p)


def test_identity_recalibrator_changes_nothing():
    p = np.array([0.01, 0.3, 0.9])
    assert LogisticRecalibrator().apply(p) == pytest.approx(p)


def test_summarize_has_all_numbers():
    y, p, _ = simulated(20_000)
    assert set(summarize(y, p)) == {"brier", "ece", "intercept", "slope"}


# ---- the shared purge helper ------------------------------------------------------------


def test_purge_drops_training_rows_similar_to_heldout_rows():
    pa, pb = np.array([0, 1]), np.array([3, 4])  # similar pairs: 0-3 and 1-4
    kept = purge_training_rows(np.array([0, 1, 2, 4, 5]), np.array([3]), pa, pb, 6)
    assert kept.tolist() == [1, 2, 4, 5]  # row 0 is similar to held-out row 3; 1-4 are both train


def test_purge_works_when_the_pair_is_listed_the_other_way_round():
    pa, pb = np.array([3]), np.array([0])
    kept = purge_training_rows(np.array([0, 1, 2]), np.array([3, 4, 5]), pa, pb, 6)
    assert kept.tolist() == [1, 2]
