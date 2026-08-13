-- Milestone 2.9 -- perluas akses baca role batch_reader ke telco_customers_synthetic
-- + synthetic_generation_runs. Lihat milestones/2.9-otomatisasi-scoring-data-sintesis/decisions.md
-- Keputusan #3.
--
-- Role batch_reader SUDAH ada (dibuat infra/sql/2.5_batch_scoring_roles.sql) --
-- file ini HANYA menambah GRANT, tidak membuat role baru. Fase 1 kontrak
-- dua-fase M1.6 sengaja membatasi batch_reader cuma ke telco_customers_source;
-- file ini membuka Fase 2 SEBAGIAN (baca saja, telco_customers_source TIDAK
-- dipensiunkan -- lihat docs/keputusan-tertunda.md KT-1).

GRANT SELECT ON public.telco_customers_synthetic TO batch_reader;
GRANT SELECT ON public.synthetic_generation_runs TO batch_reader;

-- Sama seperti telco_customers_source (M2.5 Keputusan #5): RLS aktif tanpa
-- policy = deny-all untuk role non-owner, GRANT SELECT saja TIDAK CUKUP.
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
      WHERE tablename = 'telco_customers_synthetic' AND policyname = 'batch_reader_select'
    ) THEN
      CREATE POLICY batch_reader_select ON public.telco_customers_synthetic
        FOR SELECT TO batch_reader USING (true);
    END IF;
  END IF;
END
$$;

DO $$
BEGIN
  IF EXISTS (
    SELECT FROM pg_tables
    WHERE schemaname = 'public' AND tablename = 'synthetic_generation_runs'
  ) AND (
    SELECT relrowsecurity FROM pg_class
    WHERE relname = 'synthetic_generation_runs' AND relnamespace = 'public'::regnamespace
  ) THEN
    IF NOT EXISTS (
      SELECT FROM pg_policies
      WHERE tablename = 'synthetic_generation_runs' AND policyname = 'batch_reader_select'
    ) THEN
      CREATE POLICY batch_reader_select ON public.synthetic_generation_runs
        FOR SELECT TO batch_reader USING (true);
    END IF;
  END IF;
END
$$;

-- Scoped ketat: batch_reader tetap TIDAK bisa tulis apa pun (SELECT-only,
-- sama seperti telco_customers_source), TIDAK bisa baca schema mlflow/quality.
