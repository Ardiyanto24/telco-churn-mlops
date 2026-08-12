-- Milestone 2.5 -- provisioning role least-privilege + tabel hasil prediksi
-- batch scoring.
-- Lihat milestones/2.5-batch-scoring-dag/decisions.md.
--
-- Jalankan sebagai role yang punya privilege CREATEROLE (mis. role default
-- Supabase `postgres`). Password TIDAK di-hardcode di file ini -- substitusi
-- lewat parameter runtime (pola sama infra/sql/2.1_mlflow_role.sql,
-- infra/sql/2.4_quality_gate_role.sql).

CREATE SCHEMA IF NOT EXISTS predictions;

CREATE TABLE IF NOT EXISTS predictions.batch_predictions (
    id                  bigserial PRIMARY KEY,
    customer_id         bigint NOT NULL,
    churn_probability   double precision NOT NULL,
    churn_label         smallint NOT NULL CHECK (churn_label IN (0, 1)),
    model_name          text NOT NULL,
    model_version       text NOT NULL,
    model_alias         text NOT NULL,
    source_table        text NOT NULL,
    predicted_at        timestamptz NOT NULL,
    batch_run_id        uuid NOT NULL,
    flow_run_id         text
);

CREATE INDEX IF NOT EXISTS idx_batch_predictions_customer_predicted_at
    ON predictions.batch_predictions (customer_id, predicted_at DESC);
CREATE INDEX IF NOT EXISTS idx_batch_predictions_batch_run_id
    ON predictions.batch_predictions (batch_run_id);

-- Role baca-saja untuk extract data mentah -- SELECT ke telco_customers_source
-- SAJA, tidak menyentuh telco_customers_synthetic/synthetic_generation_runs
-- (Fase 1 kontrak dua-fase M1.6, hanya source yang aktif dibaca sekarang).
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'batch_reader') THEN
    EXECUTE format('CREATE ROLE batch_reader WITH LOGIN PASSWORD %L', :'batch_reader_password');
  END IF;
END
$$;

GRANT CONNECT ON DATABASE postgres TO batch_reader;
GRANT USAGE ON SCHEMA public TO batch_reader;
GRANT SELECT ON public.telco_customers_source TO batch_reader;

-- PENTING: telco_customers_source punya Row Level Security AKTIF tanpa
-- policy apa pun (default Supabase table editor) -- GRANT SELECT saja TIDAK
-- CUKUP, RLS tanpa policy menolak SEMUA baris untuk role non-owner (baru
-- ditemukan saat verifikasi Checkpoint 1, lihat
-- milestones/2.5-batch-scoring-dag/decisions.md). Policy eksplisit wajib:
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT FROM pg_policies
    WHERE tablename = 'telco_customers_source' AND policyname = 'batch_reader_select'
  ) THEN
    CREATE POLICY batch_reader_select ON public.telco_customers_source
      FOR SELECT TO batch_reader USING (true);
  END IF;
END
$$;

-- Role tulis-saja untuk hasil prediksi -- SELECT+INSERT ke
-- predictions.batch_predictions SAJA (append-only, sama pola quality_gate
-- M2.4: tanpa UPDATE/DELETE).
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'batch_writer') THEN
    EXECUTE format('CREATE ROLE batch_writer WITH LOGIN PASSWORD %L', :'batch_writer_password');
  END IF;
END
$$;

GRANT CONNECT ON DATABASE postgres TO batch_writer;
GRANT USAGE ON SCHEMA predictions TO batch_writer;
GRANT SELECT, INSERT ON predictions.batch_predictions TO batch_writer;
GRANT USAGE ON SEQUENCE predictions.batch_predictions_id_seq TO batch_writer;

-- Scoped ketat: batch_reader TIDAK bisa tulis apa pun, TIDAK bisa baca schema
-- mlflow/quality. batch_writer TIDAK bisa baca telco_customers_source maupun
-- schema mlflow/quality. Satu role per pola akses, konsisten M2.1/M2.4.
