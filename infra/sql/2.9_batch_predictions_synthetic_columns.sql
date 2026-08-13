-- Milestone 2.9 -- migrasi additive predictions.batch_predictions supaya bisa
-- menyimpan hasil prediksi bersumber telco_customers_synthetic (identitas
-- customer_key uuid), berdampingan dengan baris existing bersumber
-- telco_customers_source (identitas customer_id bigint).
-- Lihat milestones/2.9-otomatisasi-scoring-data-sintesis/decisions.md
-- Keputusan #2.
--
-- Migrasi murni ADDITIVE -- tidak ada data existing yang hilang/berubah,
-- customer_id yang sudah terisi (594rb+ baris source) tetap apa adanya.

ALTER TABLE predictions.batch_predictions
  ALTER COLUMN customer_id DROP NOT NULL;

ALTER TABLE predictions.batch_predictions
  ADD COLUMN IF NOT EXISTS customer_key uuid;

ALTER TABLE predictions.batch_predictions
  ADD COLUMN IF NOT EXISTS generation_id uuid;

-- Exactly-one-identity: tiap baris HARUS py customer_id (sumber source) XOR
-- customer_key (sumber synthetic), tidak boleh keduanya NULL atau keduanya terisi.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT FROM pg_constraint WHERE conname = 'batch_predictions_exactly_one_identity'
  ) THEN
    ALTER TABLE predictions.batch_predictions
      ADD CONSTRAINT batch_predictions_exactly_one_identity
      CHECK (
        (customer_id IS NOT NULL AND customer_key IS NULL) OR
        (customer_id IS NULL AND customer_key IS NOT NULL)
      );
  END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_batch_predictions_customer_key
  ON predictions.batch_predictions (customer_key)
  WHERE customer_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_batch_predictions_generation_id
  ON predictions.batch_predictions (generation_id)
  WHERE generation_id IS NOT NULL;

-- Role batch_writer tidak perlu GRANT tambahan -- sudah SELECT+INSERT penuh
-- ke predictions.batch_predictions (infra/sql/2.5_batch_scoring_roles.sql),
-- kolom baru otomatis tercakup.
