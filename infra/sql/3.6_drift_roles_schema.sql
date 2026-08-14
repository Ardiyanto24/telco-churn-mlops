-- Milestone 3.6 -- schema+tabel monitoring drift, 2 role least-privilege
-- terpisah (pola "satu role per pola akses" M2.1/M2.4/M2.5/M2.9/M3.5).
-- Lihat milestones/3.6-monitoring-drift-kualitas-model/decisions.md
-- Keputusan #6.
--
-- Jalankan sebagai role yang punya privilege CREATEROLE (mis. role default
-- Supabase `postgres`). Password TIDAK di-hardcode -- substitusi lewat
-- parameter runtime (pola sama infra/sql/2.1_mlflow_role.sql dst).

CREATE SCHEMA IF NOT EXISTS drift;

-- Baseline: sample TETAP dari telco_customers_source (dihitung SEKALI,
-- scripts/compute_drift.py --mode baseline), format panjang (feature_name+
-- value per baris) -- menghindari schema churn kalau fitur model berubah.
CREATE TABLE IF NOT EXISTS drift.baseline_sample (
    id            bigserial PRIMARY KEY,
    feature_name  text NOT NULL,
    value         double precision NOT NULL,
    computed_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_baseline_sample_feature_name
    ON drift.baseline_sample (feature_name);

-- Hasil perbandingan PSI (Tier 1) + KS-test/Chi-square (Tier 2) per fitur,
-- ditulis berkala oleh scripts/compute_drift.py --mode current (dipicu
-- workflow_run setelah synthetic-auto-scoring selesai).
CREATE TABLE IF NOT EXISTS drift.drift_check_results (
    id                    bigserial PRIMARY KEY,
    feature_name          text NOT NULL,
    feature_type          text NOT NULL CHECK (feature_type IN ('numeric', 'categorical')),
    psi                   double precision NOT NULL,
    statistical_test      text NOT NULL CHECK (statistical_test IN ('ks', 'chi2')),
    p_value               double precision NOT NULL,
    verdict               text NOT NULL CHECK (verdict IN ('pass', 'flag', 'stop')),
    sample_size_current   bigint NOT NULL,
    computed_at           timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_drift_check_results_feature_computed_at
    ON drift.drift_check_results (feature_name, computed_at DESC);

-- ── drift_writer -- dipakai scripts/compute_drift.py (GitHub Actions) ──────
-- Baca 3 tabel sumber (baseline dari telco_customers_source, current window
-- dari telco_customers_synthetic + predictions.batch_predictions), tulis
-- kedua tabel drift.
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'drift_writer') THEN
    EXECUTE format('CREATE ROLE drift_writer WITH LOGIN PASSWORD %L', :'drift_writer_password');
  END IF;
END
$$;

GRANT CONNECT ON DATABASE postgres TO drift_writer;
GRANT USAGE ON SCHEMA public TO drift_writer;
GRANT SELECT ON public.telco_customers_source TO drift_writer;
GRANT SELECT ON public.telco_customers_synthetic TO drift_writer;

-- telco_customers_source/synthetic punya RLS aktif tanpa policy (default
-- Supabase table editor) -- GRANT SELECT saja TIDAK CUKUP, sama seperti
-- batch_reader (infra/sql/2.5_batch_scoring_roles.sql,
-- 2.9_synthetic_reader_grant.sql). Policy eksplisit wajib:
DO $$
BEGIN
  IF EXISTS (
    SELECT FROM pg_tables
    WHERE schemaname = 'public' AND tablename = 'telco_customers_source'
  ) AND (
    SELECT relrowsecurity FROM pg_class
    WHERE relname = 'telco_customers_source' AND relnamespace = 'public'::regnamespace
  ) THEN
    IF NOT EXISTS (
      SELECT FROM pg_policies
      WHERE tablename = 'telco_customers_source' AND policyname = 'drift_writer_select'
    ) THEN
      CREATE POLICY drift_writer_select ON public.telco_customers_source
        FOR SELECT TO drift_writer USING (true);
    END IF;
  END IF;
END
$$;

DO $$
BEGIN
  IF EXISTS (
    SELECT FROM pg_tables
    WHERE schemaname = 'public' AND tablename = 'telco_customers_synthetic'
  ) AND (
    SELECT relrowsecurity FROM pg_class
    WHERE relname = 'telco_customers_synthetic' AND relnamespace = 'public'::regnamespace
  ) THEN
    IF NOT EXISTS (
      SELECT FROM pg_policies
      WHERE tablename = 'telco_customers_synthetic' AND policyname = 'drift_writer_select'
    ) THEN
      CREATE POLICY drift_writer_select ON public.telco_customers_synthetic
        FOR SELECT TO drift_writer USING (true);
    END IF;
  END IF;
END
$$;

GRANT USAGE ON SCHEMA predictions TO drift_writer;
GRANT SELECT ON predictions.batch_predictions TO drift_writer;

GRANT USAGE ON SCHEMA drift TO drift_writer;
GRANT SELECT, INSERT ON drift.baseline_sample TO drift_writer;
GRANT SELECT, INSERT ON drift.drift_check_results TO drift_writer;
GRANT USAGE ON SEQUENCE drift.baseline_sample_id_seq TO drift_writer;
GRANT USAGE ON SEQUENCE drift.drift_check_results_id_seq TO drift_writer;

-- ── drift_reader -- dipakai orchestration/monitoring/drift_exporter.py (K8s) ─
-- SELECT-only ke drift.drift_check_results SAJA -- exporter yang selalu
-- nyala dan lebih terekspos TIDAK BISA melihat data pelanggan sama sekali
-- (beda dari drift_writer yang perlu akses tabel mentah).
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'drift_reader') THEN
    EXECUTE format('CREATE ROLE drift_reader WITH LOGIN PASSWORD %L', :'drift_reader_password');
  END IF;
END
$$;

GRANT CONNECT ON DATABASE postgres TO drift_reader;
GRANT USAGE ON SCHEMA drift TO drift_reader;
GRANT SELECT ON drift.drift_check_results TO drift_reader;

-- Scoped ketat: drift_reader TIDAK bisa baca drift.baseline_sample (data
-- baris-level, lebih sensitif) maupun tabel lain manapun. drift_writer
-- TIDAK bisa baca schema mlflow/quality/monitoring. Satu role per pola
-- akses, konsisten M2.1/M2.4/M2.5/M2.9/M3.5.
