"""Baca/tulis riwayat run gerbang kualitas data ke `quality.gate_run_history`
-- Milestone 2.4.

Tabel + role least-privilege `quality_gate` diprovisioning lewat
`infra/sql/2.4_quality_gate_role.sql` -- lihat
milestones/2.4-gerbang-kualitas-data-harian/decisions.md Keputusan #2.
"""

import os
from typing import Optional

import psycopg2
import psycopg2.extras

# Baseline dari <3 run terlalu noisy untuk dipakai perbandingan bermakna --
# check volume/distribusi di-skip (bukan false-flag) kalau riwayat belum cukup.
# Lihat milestones/2.4-gerbang-kualitas-data-harian/decisions.md Keputusan #1.
MIN_RUNS_FOR_BASELINE = 3


def get_connection_string() -> str:
    """Ambil connection string `quality_gate` dari env var `QUALITY_GATE_DB_URL`.

    Tidak pernah hardcode -- pola sama `constants.get_tracking_uri()` (M1.5).
    """
    uri = os.environ.get("QUALITY_GATE_DB_URL")
    if not uri:
        raise RuntimeError("QUALITY_GATE_DB_URL tidak diset di environment/.env")
    return uri


def record_run(
    source_table: str,
    row_count: int,
    null_proportions: dict,
    category_distributions: dict,
    verdict: str,
    details: Optional[dict] = None,
    connection_string: Optional[str] = None,
) -> int:
    """Tulis satu baris hasil run gerbang kualitas data (append-only -- role
    `quality_gate` sengaja tidak punya privilege UPDATE/DELETE).

    Mengembalikan ``id`` baris yang baru ditulis.
    """
    conn = psycopg2.connect(connection_string or get_connection_string())
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO quality.gate_run_history
                        (source_table, row_count, null_proportions, category_distributions, verdict, details)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id;
                    """,
                    (
                        source_table,
                        row_count,
                        psycopg2.extras.Json(null_proportions),
                        psycopg2.extras.Json(category_distributions),
                        verdict,
                        psycopg2.extras.Json(details) if details is not None else None,
                    ),
                )
                return cur.fetchone()[0]
    finally:
        conn.close()


def read_recent_baseline(
    source_table: str,
    n_runs: int = 7,
    connection_string: Optional[str] = None,
) -> Optional[list]:
    """Baca sampai ``n_runs`` run terakhir untuk ``source_table``, terurut
    dari yang terbaru.

    Mengembalikan ``None`` kalau jumlah run yang tersedia kurang dari
    ``MIN_RUNS_FOR_BASELINE`` -- pemanggil (``gate.py``) menafsirkan ``None``
    sebagai "baseline belum cukup data", BUKAN sebagai anomali.
    """
    conn = psycopg2.connect(connection_string or get_connection_string())
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT run_at, row_count, null_proportions, category_distributions, verdict
                    FROM quality.gate_run_history
                    WHERE source_table = %s
                    ORDER BY run_at DESC
                    LIMIT %s;
                    """,
                    (source_table, n_runs),
                )
                rows = cur.fetchall()
    finally:
        conn.close()

    if len(rows) < MIN_RUNS_FOR_BASELINE:
        return None
    return [dict(row) for row in rows]
