"""Pure check functions untuk gerbang kualitas data harian -- Milestone 2.4.

Metodologi: persentase deviasi sederhana dari baseline rolling (BUKAN
z-score/uji statistik formal -- dicatat sebagai opsi upgrade masa depan,
lihat milestones/2.4-gerbang-kualitas-data-harian/decisions.md Keputusan #1).
Perilaku bertingkat: pelanggaran parah -> ``stop``, ringan -> ``flag``,
normal -> ``pass`` (Keputusan #1).

Setiap fungsi murni: menerima angka/dict yang sudah dihitung pemanggil,
TIDAK melakukan query database sendiri -- pemisahan I/O vs logika untuk
testability (lihat `gate.py` untuk orkestrasi + I/O).
"""

from dataclasses import dataclass, field
from typing import Optional

# ── Ambang batas (persentase deviasi) ───────────────────────────────────────
# Dikonfirmasi user: metodologi deviasi sederhana, bertingkat stop/flag.
VOLUME_FLAG_THRESHOLD = 0.20  # 20% deviasi dari rata-rata baseline
VOLUME_STOP_THRESHOLD = 0.50  # 50% deviasi dari rata-rata baseline

NULL_FLAG_THRESHOLD = 0.01  # >1% NULL pada kolom yang historisnya ~0%
NULL_STOP_THRESHOLD = 0.10  # >10% NULL

CATEGORY_FLAG_THRESHOLD = 0.10  # pergeseran proporsi kategori >10 poin persentase
CATEGORY_STOP_THRESHOLD = 0.30  # >30 poin persentase

VERDICT_ORDER = {"pass": 0, "flag": 1, "stop": 2}


@dataclass
class CheckResult:
    check: str
    verdict: str  # "pass" | "flag" | "stop"
    message: str
    metric: dict = field(default_factory=dict)


def check_volume(today_count: int, baseline_counts: Optional[list]) -> CheckResult:
    """Bandingkan volume baris hari ini terhadap rata-rata baseline rolling.

    ``baseline_counts`` ``None``/kosong (riwayat <3 run) -> ``pass`` dengan
    catatan "baseline belum cukup data", BUKAN anomali.
    """
    if not baseline_counts:
        return CheckResult(
            check="volume",
            verdict="pass",
            message="Baseline belum cukup data (<3 run) -- check dilewati.",
            metric={"today_count": today_count},
        )

    baseline_mean = sum(baseline_counts) / len(baseline_counts)
    if baseline_mean == 0:
        deviation = 0.0
    else:
        deviation = abs(today_count - baseline_mean) / baseline_mean

    metric = {"today_count": today_count, "baseline_mean": baseline_mean, "deviation": deviation}

    if deviation >= VOLUME_STOP_THRESHOLD:
        return CheckResult("volume", "stop", f"Volume menyimpang {deviation:.1%} dari baseline -- di atas ambang stop ({VOLUME_STOP_THRESHOLD:.0%}).", metric)
    if deviation >= VOLUME_FLAG_THRESHOLD:
        return CheckResult("volume", "flag", f"Volume menyimpang {deviation:.1%} dari baseline -- di atas ambang flag ({VOLUME_FLAG_THRESHOLD:.0%}).", metric)
    return CheckResult("volume", "pass", f"Volume dalam batas wajar (deviasi {deviation:.1%}).", metric)


def check_null_proportion(today_nulls: dict) -> CheckResult:
    """Periksa proporsi NULL per kolom terhadap ambang absolut (kolom fitur
    model historisnya ~0% NULL -- lihat notebook-audit.md Bagian H.2/
    milestones/2.2-klasifikasi-fitur-feature-store/decisions.md).
    """
    violations = {col: prop for col, prop in today_nulls.items() if prop >= NULL_FLAG_THRESHOLD}
    metric = {"today_nulls": today_nulls, "violations": violations}

    if not violations:
        return CheckResult("null_proportion", "pass", "Tidak ada kolom dengan proporsi NULL di atas ambang.", metric)

    worst = max(violations.values())
    if worst >= NULL_STOP_THRESHOLD:
        return CheckResult(
            "null_proportion", "stop",
            f"Kolom {list(violations)} punya proporsi NULL hingga {worst:.1%} -- di atas ambang stop ({NULL_STOP_THRESHOLD:.0%}).",
            metric,
        )
    return CheckResult(
        "null_proportion", "flag",
        f"Kolom {list(violations)} punya proporsi NULL hingga {worst:.1%} -- di atas ambang flag ({NULL_FLAG_THRESHOLD:.0%}).",
        metric,
    )


def check_category_distribution(today_dist: dict, baseline_dist: Optional[dict]) -> CheckResult:
    """Bandingkan distribusi proporsi kategori (per kolom kategorikal) hari ini
    terhadap rata-rata baseline rolling.

    ``baseline_dist`` ``None`` (riwayat <3 run) -> ``pass``, sama seperti
    `check_volume`.
    """
    if not baseline_dist:
        return CheckResult(
            check="category_distribution",
            verdict="pass",
            message="Baseline belum cukup data (<3 run) -- check dilewati.",
            metric={"today_dist": today_dist},
        )

    violations = {}
    for column, today_categories in today_dist.items():
        baseline_categories = baseline_dist.get(column, {})
        for category, today_prop in today_categories.items():
            baseline_prop = baseline_categories.get(category, 0.0)
            shift = abs(today_prop - baseline_prop)
            if shift >= CATEGORY_FLAG_THRESHOLD:
                violations[f"{column}.{category}"] = shift

    metric = {"today_dist": today_dist, "baseline_dist": baseline_dist, "violations": violations}

    if not violations:
        return CheckResult("category_distribution", "pass", "Distribusi kategori dalam batas wajar.", metric)

    worst = max(violations.values())
    if worst >= CATEGORY_STOP_THRESHOLD:
        return CheckResult(
            "category_distribution", "stop",
            f"Pergeseran distribusi kategori hingga {worst:.1%} poin ({list(violations)}) -- di atas ambang stop ({CATEGORY_STOP_THRESHOLD:.0%}).",
            metric,
        )
    return CheckResult(
        "category_distribution", "flag",
        f"Pergeseran distribusi kategori hingga {worst:.1%} poin ({list(violations)}) -- di atas ambang flag ({CATEGORY_FLAG_THRESHOLD:.0%}).",
        metric,
    )


def aggregate_verdict(results: list) -> str:
    """Verdict akhir = yang paling parah di antara seluruh check (stop > flag > pass)."""
    if not results:
        return "pass"
    return max((r.verdict for r in results), key=lambda v: VERDICT_ORDER[v])
