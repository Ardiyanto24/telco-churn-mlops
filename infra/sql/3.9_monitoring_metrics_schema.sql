-- Milestone 3.9 -- skema tabel generik penyimpanan data monitoring di
-- PostgreSQL (Bagian 8.3 dokumen arsitektur, "Dua Dashboard, Satu Sumber
-- Data Monitoring"). Satu tabel `monitoring.metrics_snapshot` menampung
-- SEMUA metrik dari ketiga pilar observability (infra/API, drift, pipeline
-- health) -- keputusan user (bukan rekomendasi awal, yang mengusulkan
-- skema per-pilar/reuse tabel existing). Lihat
-- milestones/3.9-penyimpanan-data-monitoring-postgresql/decisions.md
-- Keputusan #1.
--
-- Jalankan sebagai role yang punya privilege CREATEROLE (mis. role default
-- Supabase `postgres`). Password TIDAK di-hardcode -- substitusi lewat
-- parameter runtime (pola sama infra/sql/2.1_mlflow_role.sql dst).

CREATE SCHEMA IF NOT EXISTS monitoring;

-- Pola (metric_name, value, labels jsonb, computed_at) -- generik lintas 3
-- pilar tanpa schema churn tiap kali ada metrik baru. `labels` menampung
-- dimensi seperti feature_name/source_table/flow_name/status, persis label
-- Prometheus asalnya (orchestration/monitoring/metrics_aggregator.py
-- Checkpoint 2 yang mengisi tabel ini).
CREATE TABLE IF NOT EXISTS monitoring.metrics_snapshot (
    id           bigserial PRIMARY KEY,
    metric_name  text NOT NULL,
    value        double precision NOT NULL,
    labels       jsonb NOT NULL DEFAULT '{}',
    computed_at  timestamptz NOT NULL DEFAULT now()
);

-- Pola query utama: "N baris terbaru untuk metric_name tertentu" (Grafana
-- panel, Checkpoint 6-8) -- index ini cukup, TIDAK pakai GIN index di
-- `labels` (skala query rendah, filter utama selalu lewat metric_name dulu).
CREATE INDEX IF NOT EXISTS idx_metrics_snapshot_name_computed_at
    ON monitoring.metrics_snapshot (metric_name, computed_at DESC);

-- ── monitoring_metrics_writer -- dipakai orchestration/monitoring/
-- metrics_aggregator.py (K8s, Checkpoint 3) ─────────────────────────────
-- INSERT+SELECT ke metrics_snapshot SAJA. Nama SENGAJA beda dari
-- monitoring_reader (M3.5, dipakai pipeline_health_exporter.py, scope
-- quality+predictions) -- pola akses beda total (menulis vs membaca, tabel
-- beda), bukan role yang sama diperluas. Satu role per pola akses,
-- konsisten M2.1/M2.4/M2.5/M2.9/M3.5/M3.6.
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'monitoring_metrics_writer') THEN
    EXECUTE format('CREATE ROLE monitoring_metrics_writer WITH LOGIN PASSWORD %L', :'monitoring_metrics_writer_password');
  END IF;
END
$$;

GRANT CONNECT ON DATABASE postgres TO monitoring_metrics_writer;
GRANT USAGE ON SCHEMA monitoring TO monitoring_metrics_writer;
GRANT SELECT, INSERT ON monitoring.metrics_snapshot TO monitoring_metrics_writer;
GRANT USAGE ON SEQUENCE monitoring.metrics_snapshot_id_seq TO monitoring_metrics_writer;

-- ── monitoring_metrics_reader -- dipakai datasource PostgreSQL Grafana
-- (Checkpoint 5) ─────────────────────────────────────────────────────────
-- SELECT-only ke metrics_snapshot SAJA. Dengan skema generik, Grafana HANYA
-- perlu akses ke SATU tabel ini untuk seluruh dashboard -- TIDAK perlu akses
-- drift.drift_check_results/quality.gate_run_history/predictions.batch_predictions
-- langsung sama sekali, blast radius kredensial Grafana lebih sempit dari
-- exporter-exporter existing.
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'monitoring_metrics_reader') THEN
    EXECUTE format('CREATE ROLE monitoring_metrics_reader WITH LOGIN PASSWORD %L', :'monitoring_metrics_reader_password');
  END IF;
END
$$;

GRANT CONNECT ON DATABASE postgres TO monitoring_metrics_reader;
GRANT USAGE ON SCHEMA monitoring TO monitoring_metrics_reader;
GRANT SELECT ON monitoring.metrics_snapshot TO monitoring_metrics_reader;

-- Scoped ketat: monitoring_metrics_reader TIDAK bisa INSERT/UPDATE/DELETE,
-- TIDAK bisa baca schema lain manapun (mlflow/quality/predictions/drift/
-- public). monitoring_metrics_writer TIDAK bisa baca schema lain manapun
-- juga (tidak butuh -- metrics_aggregator.py sumber datanya Prometheus,
-- bukan query Postgres). Satu role per pola akses, konsisten seluruh
-- proyek.
