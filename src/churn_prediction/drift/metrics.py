"""Metrik drift dua tingkat -- Milestone 3.6.

Tier 1 (``compute_psi``): Population Stability Index, satu rumus untuk
fitur numerik (bin desil dari baseline) maupun kategorikal (bin = nilai
unik) -- heuristik cepat, threshold konvensi industri.

Tier 2 (``compute_ks_pvalue``/``compute_chi2_pvalue``): uji statistik formal
(KS-test untuk numerik, Chi-square untuk kategorikal) -- p-value, threshold
konvensi signifikansi statistik. Dihitung SEKALIGUS dengan Tier 1 tiap
siklus (bukan eskalasi bertingkat) -- keputusan user, lihat
milestones/3.6-monitoring-drift-kualitas-model/decisions.md.

Seluruh fungsi murni (terima array, tidak melakukan I/O) -- pola sama
``src/churn_prediction/quality/checks.py`` (M2.4): pemisahan logika vs I/O
untuk testability.
"""

from typing import Sequence

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, ks_2samp

from churn_prediction.drift.constants import (
    PSI_FLAG_THRESHOLD,
    PSI_NUMERIC_BINS,
    PSI_STOP_THRESHOLD,
    PVALUE_FLAG_THRESHOLD,
    PVALUE_STOP_THRESHOLD,
    VERDICT_ORDER,
)

_PSI_EPSILON = 1e-4


def _psi_from_counts(baseline_counts: np.ndarray, current_counts: np.ndarray) -> float:
    baseline_counts = np.asarray(baseline_counts, dtype=float)
    current_counts = np.asarray(current_counts, dtype=float)
    baseline_prop = baseline_counts / baseline_counts.sum()
    current_prop = current_counts / current_counts.sum()
    # Epsilon smoothing -- hindari log(0)/pembagian nol saat satu bin kosong
    # di salah satu sisi (mis. kategori baru muncul di current, atau baseline
    # kosong utk bin tertentu).
    baseline_prop = np.clip(baseline_prop, _PSI_EPSILON, None)
    current_prop = np.clip(current_prop, _PSI_EPSILON, None)
    return float(np.sum((current_prop - baseline_prop) * np.log(current_prop / baseline_prop)))


def _psi_numeric(baseline: Sequence[float], current: Sequence[float], n_bins: int) -> float:
    baseline_arr = np.asarray(baseline, dtype=float)
    current_arr = np.asarray(current, dtype=float)
    quantiles = np.linspace(0, 1, n_bins + 1)
    bin_edges = np.unique(np.quantile(baseline_arr, quantiles))
    if len(bin_edges) < 2:
        # Baseline konstan (semua nilai sama) -- tidak ada variasi utk di-bin,
        # PSI tidak bermakna secara numerik. Anggap tidak drift (0.0).
        return 0.0
    bin_edges[0] = -np.inf
    bin_edges[-1] = np.inf
    baseline_counts, _ = np.histogram(baseline_arr, bins=bin_edges)
    current_counts, _ = np.histogram(current_arr, bins=bin_edges)
    return _psi_from_counts(baseline_counts, current_counts)


def _psi_categorical(baseline: Sequence, current: Sequence) -> float:
    baseline_s = pd.Series(baseline)
    current_s = pd.Series(current)
    categories = sorted(set(baseline_s.unique()) | set(current_s.unique()))
    baseline_counts = baseline_s.value_counts().reindex(categories, fill_value=0).to_numpy()
    current_counts = current_s.value_counts().reindex(categories, fill_value=0).to_numpy()
    return _psi_from_counts(baseline_counts, current_counts)


def compute_psi(
    baseline: Sequence,
    current: Sequence,
    feature_type: str,
    n_bins: int = PSI_NUMERIC_BINS,
) -> float:
    """Population Stability Index. ``feature_type`` "numeric" -> bin desil
    dari baseline; "categorical" -> bin = union nilai unik baseline+current
    (kategori baru yang tidak pernah muncul di baseline tetap tertangkap,
    dibanding proporsi baseline ~0 di kategori itu)."""
    if feature_type == "numeric":
        return _psi_numeric(baseline, current, n_bins)
    if feature_type == "categorical":
        return _psi_categorical(baseline, current)
    raise ValueError(f"feature_type tidak dikenal: {feature_type!r}")


def compute_ks_pvalue(baseline: Sequence[float], current: Sequence[float]) -> float:
    """Kolmogorov-Smirnov two-sample test -- untuk fitur numerik kontinu.
    H0: baseline dan current berasal dari distribusi yang sama."""
    result = ks_2samp(baseline, current)
    return float(result.pvalue)


def compute_chi2_pvalue(baseline: Sequence, current: Sequence) -> float:
    """Chi-square test of independence -- untuk fitur kategorikal/binary/
    structural/one-hot. H0: proporsi kategori independen dari kelompok
    (baseline vs current)."""
    baseline_s = pd.Series(baseline)
    current_s = pd.Series(current)
    categories = sorted(set(baseline_s.unique()) | set(current_s.unique()))
    if len(categories) < 2:
        # Cuma 1 kategori unik di kedua sisi -- tidak ada variasi utk diuji.
        return 1.0
    baseline_counts = baseline_s.value_counts().reindex(categories, fill_value=0).to_numpy()
    current_counts = current_s.value_counts().reindex(categories, fill_value=0).to_numpy()
    contingency = np.array([baseline_counts, current_counts])
    _, pvalue, _, _ = chi2_contingency(contingency)
    return float(pvalue)


def compute_tier2_pvalue(baseline: Sequence, current: Sequence, feature_type: str) -> float:
    """Dispatch uji Tier 2 sesuai tipe fitur -- KS-test (numerik) atau
    Chi-square (kategorikal)."""
    if feature_type == "numeric":
        return compute_ks_pvalue(baseline, current)
    if feature_type == "categorical":
        return compute_chi2_pvalue(baseline, current)
    raise ValueError(f"feature_type tidak dikenal: {feature_type!r}")


def combined_verdict(psi: float, pvalue: float) -> str:
    """Verdict akhir = terburuk dari verdict PSI (Tier 1) dan verdict
    p-value (Tier 2) -- pola sama ``aggregate_verdict`` M2.4."""
    if psi >= PSI_STOP_THRESHOLD or pvalue < PVALUE_STOP_THRESHOLD:
        return "stop"
    if psi >= PSI_FLAG_THRESHOLD or pvalue < PVALUE_FLAG_THRESHOLD:
        return "flag"
    return "pass"


def verdict_to_value(verdict: str) -> int:
    """Encode verdict jadi angka utk gauge Prometheus (2=pass,1=flag,0=stop)."""
    return 2 - VERDICT_ORDER[verdict]
