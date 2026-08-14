-- Milestone 3.5 -- role least-privilege untuk exporter status pipeline batch
-- (orchestration/monitoring/pipeline_health_exporter.py).
-- Lihat milestones/3.5-monitoring-infra-pipeline-health/decisions.md Keputusan #4.
--
-- Jalankan sebagai role yang punya privilege CREATEROLE (mis. role default
-- Supabase `postgres`). Password TIDAK di-hardcode di file ini -- substitusi
-- lewat parameter runtime (pola sama infra/sql/2.1_mlflow_role.sql,
-- infra/sql/2.4_quality_gate_role.sql, infra/sql/2.5_batch_scoring_roles.sql).

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'monitoring_reader') THEN
    EXECUTE format('CREATE ROLE monitoring_reader WITH LOGIN PASSWORD %L', :'monitoring_reader_password');
  END IF;
END
$$;

GRANT CONNECT ON DATABASE postgres TO monitoring_reader;

GRANT USAGE ON SCHEMA quality TO monitoring_reader;
GRANT SELECT ON quality.gate_run_history TO monitoring_reader;

GRANT USAGE ON SCHEMA predictions TO monitoring_reader;
GRANT SELECT ON predictions.batch_predictions TO monitoring_reader;

-- Kedua tabel dibuat via SQL langsung (bukan Supabase table editor di schema
-- public), jadi TIDAK punya Row Level Security aktif -- beda dari
-- telco_customers_source/telco_customers_synthetic (lihat
-- infra/sql/2.5_batch_scoring_roles.sql, infra/sql/2.9_synthetic_reader_grant.sql)
-- yang butuh policy eksplisit tambahan. GRANT SELECT saja sudah cukup di sini.

-- Scoped ketat: monitoring_reader HANYA SELECT ke 2 tabel di atas -- TIDAK
-- bisa INSERT/UPDATE/DELETE (beda dari batch_writer/quality_gate yang punya
-- INSERT), TIDAK bisa baca schema mlflow atau tabel public (telco_customers_*).
-- Satu role per pola akses, konsisten M2.1/M2.4/M2.5/M2.9.
