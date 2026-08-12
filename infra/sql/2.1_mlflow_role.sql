-- Milestone 2.1 -- provisioning role least-privilege untuk MLflow backend store.
-- Lihat milestones/2.1-fondasi-orchestrator-model-registry/decisions.md Keputusan #4.
--
-- Jalankan sebagai role yang punya privilege CREATEROLE (mis. role default Supabase
-- `postgres`). Password TIDAK di-hardcode di file ini -- substitusi lewat psql -v:
--   psql "$SUPABASE_DB_URL" -v mlflow_password="$MLFLOW_REGISTRY_PASSWORD" \
--     -f infra/sql/2.1_mlflow_role.sql

CREATE SCHEMA IF NOT EXISTS mlflow;

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mlflow_registry') THEN
    EXECUTE format('CREATE ROLE mlflow_registry WITH LOGIN PASSWORD %L', :'mlflow_password');
  END IF;
END
$$;

GRANT CONNECT ON DATABASE postgres TO mlflow_registry;
GRANT USAGE, CREATE ON SCHEMA mlflow TO mlflow_registry;

-- MLflow (via SQLAlchemy/Alembic) membuat tabel registry-nya sendiri saat pertama
-- connect -- search_path default diarahkan ke schema mlflow supaya CREATE TABLE
-- tanpa qualifier eksplisit tetap landing di sana, bukan public.
ALTER ROLE mlflow_registry SET search_path = mlflow, public;

-- Scoped ke schema mlflow SAJA -- role ini sengaja TIDAK diberi grant apa pun ke
-- schema public / tabel data mentah (telco_customers_source, telco_customers_synthetic,
-- synthetic_generation_runs) sesuai prinsip least-privilege CLAUDE.md.
