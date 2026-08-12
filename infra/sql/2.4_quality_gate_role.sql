-- Milestone 2.4 -- provisioning role least-privilege + tabel riwayat baseline
-- untuk Gerbang Kualitas Data Harian.
-- Lihat milestones/2.4-gerbang-kualitas-data-harian/decisions.md.
--
-- Jalankan sebagai role yang punya privilege CREATEROLE (mis. role default
-- Supabase `postgres`). Password TIDAK di-hardcode di file ini -- substitusi
-- lewat parameter runtime (pola sama infra/sql/2.1_mlflow_role.sql).

CREATE SCHEMA IF NOT EXISTS quality;

CREATE TABLE IF NOT EXISTS quality.gate_run_history (
    id                      bigserial PRIMARY KEY,
    run_at                  timestamptz NOT NULL DEFAULT now(),
    source_table            text NOT NULL,
    row_count               bigint NOT NULL,
    null_proportions        jsonb NOT NULL,
    category_distributions  jsonb NOT NULL,
    verdict                 text NOT NULL CHECK (verdict IN ('pass', 'flag', 'stop')),
    details                 jsonb
);

CREATE INDEX IF NOT EXISTS idx_gate_run_history_source_run_at
    ON quality.gate_run_history (source_table, run_at DESC);

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'quality_gate') THEN
    EXECUTE format('CREATE ROLE quality_gate WITH LOGIN PASSWORD %L', :'quality_gate_password');
  END IF;
END
$$;

GRANT CONNECT ON DATABASE postgres TO quality_gate;
GRANT USAGE ON SCHEMA quality TO quality_gate;
GRANT SELECT, INSERT ON quality.gate_run_history TO quality_gate;
GRANT USAGE ON SEQUENCE quality.gate_run_history_id_seq TO quality_gate;

-- Scoped ke schema quality SAJA -- role ini sengaja TIDAK diberi grant apa pun
-- ke schema public / tabel data mentah (telco_customers_source,
-- telco_customers_synthetic, synthetic_generation_runs), maupun ke schema
-- mlflow (Milestone 2.1) -- satu role per pola akses, bukan reuse.
