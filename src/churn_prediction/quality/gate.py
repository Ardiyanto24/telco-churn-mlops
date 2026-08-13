"""Orkestrasi gerbang kualitas data harian -- Milestone 2.4.

`run_gate()` menghitung statistik hari ini dari DataFrame yang diberikan,
membaca baseline rolling (`baseline.py`), menjalankan seluruh check
(`checks.py`), menulis hasil run, lalu mengembalikan verdict akhir bertingkat.

Sengaja TIDAK mengasumsikan konvensi nama kolom (PascalCase
`telco_customers_source` vs snake_case `telco_customers_synthetic`) --
pemanggil menyediakan daftar kolom eksplisit, mengikuti pola normalisasi
kolom yang sudah dipakai `milestones/1.6-kontrak-skema-sumber-data/
decisions.md` Keputusan #1 (titik baca data yang me-normalisasi, bukan modul
bersama ini).
"""

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from . import baseline as baseline_store
from .checks import (
    CheckResult,
    aggregate_verdict,
    check_category_distribution,
    check_null_proportion,
    check_volume,
)


@dataclass
class GateResult:
    verdict: str  # "pass" | "flag" | "stop"
    checks: list = field(default_factory=list)  # list[CheckResult]
    run_id: Optional[int] = None


def _compute_null_proportions(df: pd.DataFrame, columns: list) -> dict:
    return {col: float(df[col].isna().mean()) for col in columns}


def _compute_category_distributions(df: pd.DataFrame, categorical_columns: list) -> dict:
    return {
        col: {str(k): float(v) for k, v in df[col].value_counts(normalize=True, dropna=True).to_dict().items()}
        for col in categorical_columns
    }


def _average_baseline_category_distributions(baseline_rows: list, categorical_columns: list) -> dict:
    n = len(baseline_rows)
    averaged = {}
    for column in categorical_columns:
        totals: dict = {}
        for row in baseline_rows:
            dist = (row.get("category_distributions") or {}).get(column, {})
            for category, prop in dist.items():
                totals[category] = totals.get(category, 0.0) + prop
        averaged[column] = {category: total / n for category, total in totals.items()}
    return averaged


def run_gate(
    df: pd.DataFrame,
    source_table: str,
    numeric_columns: list,
    categorical_columns: list,
    connection_string: Optional[str] = None,
    n_runs: int = 7,
    record_history: bool = True,
) -> GateResult:
    """Jalankan gerbang kualitas data untuk `df` (satu batch/hari data mentah).

    `numeric_columns`/`categorical_columns`: kolom yang dicek NULL-nya
    (gabungan keduanya); `categorical_columns` juga dicek pergeseran
    distribusinya. Rekomendasi: 18 kolom input fitur model (lihat
    milestones/2.2-klasifikasi-fitur-feature-store/decisions.md), bukan
    seluruh kolom mentah.

    `record_history`: default True (perilaku DAG M2.5 tidak berubah -- tiap
    run ikut membentuk baseline rolling). Set False untuk pemanggil yang
    HANYA ingin verdict tanpa menulis riwayat -- mis. gerbang CI Milestone
    2.7, yang jalan tiap push dan TIDAK boleh mencemari baseline yang
    dipakai DAG produksi (root cause pencemaran berulang M2.5/M2.6, lihat
    milestones/2.7-cicd-verifikasi-parity/decisions.md).
    """
    all_columns = list(numeric_columns) + list(categorical_columns)
    today_row_count = len(df)
    today_nulls = _compute_null_proportions(df, all_columns)
    today_dist = _compute_category_distributions(df, categorical_columns)

    baseline_rows = baseline_store.read_recent_baseline(
        source_table, n_runs=n_runs, connection_string=connection_string
    )
    baseline_counts = [row["row_count"] for row in baseline_rows] if baseline_rows else None
    baseline_dist = (
        _average_baseline_category_distributions(baseline_rows, categorical_columns)
        if baseline_rows
        else None
    )

    results: list = [
        check_volume(today_row_count, baseline_counts),
        check_null_proportion(today_nulls),
        check_category_distribution(today_dist, baseline_dist),
    ]
    verdict = aggregate_verdict(results)

    run_id = None
    if record_history:
        run_id = baseline_store.record_run(
            source_table=source_table,
            row_count=today_row_count,
            null_proportions=today_nulls,
            category_distributions=today_dist,
            verdict=verdict,
            details={"checks": [r.__dict__ for r in results]},
            connection_string=connection_string,
        )

    return GateResult(verdict=verdict, checks=results, run_id=run_id)
