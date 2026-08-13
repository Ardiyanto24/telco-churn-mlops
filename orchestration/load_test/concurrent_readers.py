"""Harness pengukuran latensi -- Milestone 2.6, Checkpoint 1.

Simulasikan dua konsumen baca gaya real-time API yang benar-benar akan ada
menurut keputusan arsitektur final (M2.2: tidak ada feature store, seluruh
29 fitur INSTANT, dihitung dari payload bukan dibaca dari tabel) -- lihat
milestones/2.6-isolasi-beban-postgresql/decisions.md.

Consumer A (resolusi alias model): memanggil ``registry.resolve_alias_version()``
langsung -- REUSE fungsi nyata M2.5, bukan raw SQL baru (satu sumber
kebenaran). Ini satu-satunya jejak baca Postgres yang pasti dipakai
real-time API nanti (schema ``mlflow``).

Consumer B (agregat gaya dashboard monitoring): proxy untuk konsumen M3.x
lain yang relevan -- ``predictions.batch_predictions`` ditulis dalam SATU
transaksi panjang oleh ``write_predictions`` M2.5. Belum ada role dashboard
sungguhan (M3.x belum mulai) -- reuse koneksi ``batch_writer`` untuk
keperluan pengukuran sementara ini SAJA, bukan pola akses production baru.

Bukan modul ``churn_prediction`` (bukan logika transformasi/inference) dan
BUKAN pytest permanen -- alat ukur sekali pakai untuk milestone ini.
"""

import statistics
import time
from typing import Callable, List, Optional

import psycopg2

from churn_prediction.inference import registry

_DASHBOARD_AGGREGATE_SQL = """
    SELECT model_version, count(*), avg(churn_probability)
    FROM predictions.batch_predictions
    GROUP BY model_version
"""


def _timed_loop(query_fn: Callable[[], None], duration_s: float, interval_s: float) -> List[float]:
    """Jalankan ``query_fn`` berulang selama ``duration_s`` detik, jeda
    ``interval_s`` antar panggilan, kembalikan list latency (ms)."""
    latencies = []
    deadline = time.monotonic() + duration_s
    while time.monotonic() < deadline:
        start = time.perf_counter()
        query_fn()
        latencies.append((time.perf_counter() - start) * 1000.0)
        time.sleep(interval_s)
    return latencies


def simulate_mlflow_alias_reads(
    duration_s: float,
    interval_s: float = 1.0,
    alias: str = "champion",
    tracking_uri: Optional[str] = None,
) -> List[float]:
    """Consumer A -- resolusi alias versi model berulang."""

    def _query():
        registry.resolve_alias_version(alias=alias, tracking_uri=tracking_uri)

    return _timed_loop(_query, duration_s, interval_s)


def simulate_dashboard_aggregate_reads(
    duration_s: float,
    connection_string: str,
    interval_s: float = 1.0,
) -> List[float]:
    """Consumer B -- query agregat gaya dashboard monitoring berulang, satu
    koneksi dipakai sepanjang durasi (meniru service yang persist, bukan
    reconnect tiap query)."""
    conn = psycopg2.connect(connection_string)
    conn.autocommit = True
    try:
        def _query():
            with conn.cursor() as cur:
                cur.execute(_DASHBOARD_AGGREGATE_SQL)
                cur.fetchall()

        return _timed_loop(_query, duration_s, interval_s)
    finally:
        conn.close()


def summarize_latencies(samples: List[float]) -> dict:
    """Ringkas list latency (ms) jadi p50/p95/min/max/n."""
    if not samples:
        return {"n": 0, "p50": None, "p95": None, "min": None, "max": None}
    ordered = sorted(samples)
    n = len(ordered)
    p95_index = min(int(round(0.95 * (n - 1))), n - 1)
    return {
        "n": n,
        "p50": statistics.median(ordered),
        "p95": ordered[p95_index],
        "min": ordered[0],
        "max": ordered[-1],
    }
