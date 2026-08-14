"""Unit test -- Milestone 3.6 Checkpoint 1: metrik drift dua tingkat (PSI +
KS-test/Chi-square). Seluruh test pakai array sintetis (numpy RNG seeded,
tanpa DB) -- pola sama tests/quality/test_checks.py (M2.4)."""

import numpy as np

from churn_prediction.drift.metrics import (
    combined_verdict,
    compute_chi2_pvalue,
    compute_ks_pvalue,
    compute_psi,
    verdict_to_value,
)


def _rng(seed):
    return np.random.default_rng(seed)


# ── PSI numerik ──────────────────────────────────────────────────────────


def test_psi_numeric_identical_distribution_is_low():
    baseline = _rng(1).normal(30, 10, 5000)
    current = _rng(2).normal(30, 10, 1000)
    psi = compute_psi(baseline, current, feature_type="numeric")
    assert psi < 0.1


def test_psi_numeric_shifted_distribution_is_high():
    baseline = _rng(1).normal(30, 10, 5000)
    current = _rng(2).normal(80, 10, 1000)  # mean bergeser jauh
    psi = compute_psi(baseline, current, feature_type="numeric")
    assert psi >= 0.25


def test_psi_numeric_constant_baseline_does_not_crash():
    baseline = np.full(5000, 42.0)
    current = _rng(2).normal(42, 5, 1000)
    psi = compute_psi(baseline, current, feature_type="numeric")
    assert psi == 0.0


# ── PSI kategorikal ──────────────────────────────────────────────────────


def test_psi_categorical_identical_distribution_is_low():
    baseline = _rng(1).choice(["A", "B", "C"], size=5000, p=[0.5, 0.3, 0.2])
    current = _rng(2).choice(["A", "B", "C"], size=1000, p=[0.5, 0.3, 0.2])
    psi = compute_psi(baseline, current, feature_type="categorical")
    assert psi < 0.1


def test_psi_categorical_shifted_distribution_is_high():
    baseline = _rng(1).choice(["A", "B", "C"], size=5000, p=[0.5, 0.3, 0.2])
    current = _rng(2).choice(["A", "B", "C"], size=1000, p=[0.05, 0.05, 0.9])
    psi = compute_psi(baseline, current, feature_type="categorical")
    assert psi >= 0.25


def test_psi_categorical_new_category_not_in_baseline_is_detected():
    baseline = _rng(1).choice(["A", "B"], size=5000, p=[0.5, 0.5])
    current = np.array(["C"] * 1000)  # kategori sama sekali baru
    psi = compute_psi(baseline, current, feature_type="categorical")
    assert psi >= 0.25


def test_compute_psi_unknown_feature_type_raises():
    try:
        compute_psi([1], [1], feature_type="unknown")
        assert False, "harus raise ValueError"
    except ValueError:
        pass


# ── Tier 2: KS-test ──────────────────────────────────────────────────────


def test_ks_pvalue_identical_distribution_is_high():
    baseline = _rng(1).normal(30, 10, 5000)
    current = _rng(2).normal(30, 10, 1000)
    pvalue = compute_ks_pvalue(baseline, current)
    assert pvalue >= 0.05


def test_ks_pvalue_shifted_distribution_is_low():
    baseline = _rng(1).normal(30, 10, 5000)
    current = _rng(2).normal(80, 10, 1000)
    pvalue = compute_ks_pvalue(baseline, current)
    assert pvalue < 0.01


# ── Tier 2: Chi-square ───────────────────────────────────────────────────


def test_chi2_pvalue_identical_distribution_is_high():
    baseline = _rng(1).choice(["A", "B", "C"], size=5000, p=[0.5, 0.3, 0.2])
    current = _rng(2).choice(["A", "B", "C"], size=1000, p=[0.5, 0.3, 0.2])
    pvalue = compute_chi2_pvalue(baseline, current)
    assert pvalue >= 0.05


def test_chi2_pvalue_shifted_distribution_is_low():
    baseline = _rng(1).choice(["A", "B", "C"], size=5000, p=[0.5, 0.3, 0.2])
    current = _rng(2).choice(["A", "B", "C"], size=1000, p=[0.05, 0.05, 0.9])
    pvalue = compute_chi2_pvalue(baseline, current)
    assert pvalue < 0.01


def test_chi2_pvalue_single_category_returns_one():
    baseline = np.array(["A"] * 100)
    current = np.array(["A"] * 50)
    pvalue = compute_chi2_pvalue(baseline, current)
    assert pvalue == 1.0


# ── combined_verdict / verdict_to_value ──────────────────────────────────


def test_combined_verdict_pass():
    assert combined_verdict(psi=0.02, pvalue=0.8) == "pass"


def test_combined_verdict_flag_from_psi():
    assert combined_verdict(psi=0.15, pvalue=0.8) == "flag"


def test_combined_verdict_flag_from_pvalue():
    assert combined_verdict(psi=0.02, pvalue=0.03) == "flag"


def test_combined_verdict_stop_from_psi():
    assert combined_verdict(psi=0.30, pvalue=0.8) == "stop"


def test_combined_verdict_stop_from_pvalue():
    assert combined_verdict(psi=0.02, pvalue=0.005) == "stop"


def test_combined_verdict_stop_takes_precedence_over_flag():
    # PSI bilang flag, p-value bilang stop -- terburuk (stop) yang menang.
    assert combined_verdict(psi=0.15, pvalue=0.005) == "stop"


def test_verdict_to_value_mapping():
    assert verdict_to_value("pass") == 2
    assert verdict_to_value("flag") == 1
    assert verdict_to_value("stop") == 0
