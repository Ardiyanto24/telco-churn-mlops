"""Unit test murni (tanpa DB) untuk `churn_prediction.quality.checks` --
Milestone 2.4 Checkpoint 2.

Skenario mengikuti KK sumber milestone: data normal tidak memicu false alert,
penyimpangan buatan (volume anjlok, NULL melonjak, distribusi kategori
bergeser) terdeteksi dan diklasifikasi bertingkat (stop/flag).
"""

from churn_prediction.quality.checks import (
    aggregate_verdict,
    check_category_distribution,
    check_null_proportion,
    check_volume,
)


# ── check_volume ─────────────────────────────────────────────────────────────

def test_check_volume_passes_when_baseline_insufficient():
    result = check_volume(today_count=594194, baseline_counts=None)
    assert result.verdict == "pass"
    assert "belum cukup data" in result.message


def test_check_volume_passes_on_normal_fluctuation():
    # baseline rata-rata 594194, hari ini 594194 -- deviasi 0%, sesuai statistik
    # real telco_customers_source (594.194 baris).
    result = check_volume(today_count=594194, baseline_counts=[590000, 594194, 598000])
    assert result.verdict == "pass"


def test_check_volume_flags_moderate_drop():
    # baseline mean 100000, hari ini 75000 -> deviasi 25% (di atas flag 20%, di bawah stop 50%)
    result = check_volume(today_count=75000, baseline_counts=[100000, 100000, 100000])
    assert result.verdict == "flag"


def test_check_volume_stops_on_severe_drop():
    # deviasi 60% -- di atas ambang stop (50%)
    result = check_volume(today_count=40000, baseline_counts=[100000, 100000, 100000])
    assert result.verdict == "stop"


def test_check_volume_stops_on_severe_spike():
    # kenaikan drastis juga anomali, bukan cuma penurunan
    result = check_volume(today_count=200000, baseline_counts=[100000, 100000, 100000])
    assert result.verdict == "stop"


# ── check_null_proportion ────────────────────────────────────────────────────

def test_check_null_proportion_passes_when_clean():
    # sesuai temuan real: 0 NULL di 18 kolom fitur model (notebook-audit.md Bagian H.2)
    result = check_null_proportion({"tenure": 0.0, "MonthlyCharges": 0.0})
    assert result.verdict == "pass"


def test_check_null_proportion_flags_moderate_spike():
    result = check_null_proportion({"tenure": 0.0, "MonthlyCharges": 0.05})
    assert result.verdict == "flag"


def test_check_null_proportion_stops_on_severe_spike():
    result = check_null_proportion({"tenure": 0.15, "MonthlyCharges": 0.0})
    assert result.verdict == "stop"


# ── check_category_distribution ─────────────────────────────────────────────

def test_check_category_distribution_passes_when_baseline_insufficient():
    result = check_category_distribution(today_dist={"Contract": {"Month-to-month": 0.5}}, baseline_dist=None)
    assert result.verdict == "pass"


def test_check_category_distribution_passes_on_normal_variation():
    today = {"Contract": {"Month-to-month": 0.51, "One year": 0.18, "Two year": 0.31}}
    baseline = {"Contract": {"Month-to-month": 0.503, "One year": 0.182, "Two year": 0.315}}
    result = check_category_distribution(today, baseline)
    assert result.verdict == "pass"


def test_check_category_distribution_flags_moderate_shift():
    # Month-to-month bergeser 15 poin (0.503 -> 0.65), di atas flag (10pt), di bawah stop (30pt)
    today = {"Contract": {"Month-to-month": 0.65}}
    baseline = {"Contract": {"Month-to-month": 0.503}}
    result = check_category_distribution(today, baseline)
    assert result.verdict == "flag"


def test_check_category_distribution_stops_on_severe_shift():
    # bergeser 40 poin -- di atas ambang stop (30pt)
    today = {"Contract": {"Month-to-month": 0.90}}
    baseline = {"Contract": {"Month-to-month": 0.503}}
    result = check_category_distribution(today, baseline)
    assert result.verdict == "stop"


# ── aggregate_verdict ─────────────────────────────────────────────────────────

def test_aggregate_verdict_all_pass():
    from churn_prediction.quality.checks import CheckResult
    results = [CheckResult("a", "pass", "ok"), CheckResult("b", "pass", "ok")]
    assert aggregate_verdict(results) == "pass"


def test_aggregate_verdict_flag_beats_pass():
    from churn_prediction.quality.checks import CheckResult
    results = [CheckResult("a", "pass", "ok"), CheckResult("b", "flag", "meh")]
    assert aggregate_verdict(results) == "flag"


def test_aggregate_verdict_stop_beats_everything():
    from churn_prediction.quality.checks import CheckResult
    results = [CheckResult("a", "flag", "meh"), CheckResult("b", "stop", "bad"), CheckResult("c", "pass", "ok")]
    assert aggregate_verdict(results) == "stop"


def test_aggregate_verdict_empty_is_pass():
    assert aggregate_verdict([]) == "pass"
