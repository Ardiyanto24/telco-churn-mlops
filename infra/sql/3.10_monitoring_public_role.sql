-- Milestone 3.10 -- role least-privilege KHUSUS API publik (Bagian 8.3
-- dokumen arsitektur), TERPISAH dari monitoring_metrics_reader (M3.9,
-- dipakai datasource Grafana internal) walau scope SELECT identik --
-- forced eksplisit oleh teks sumber M3.10: "Role/kredensial PostgreSQL
-- khusus untuk API ini... bukan memakai kredensial yang sama dengan
-- mekanisme internal Milestone 3.9". Lihat
-- milestones/3.10-api-publik-dashboard-monitoring/decisions.md.
--
-- Dipakai Cloudflare Worker (public-api/, repo terpisah) lewat Hyperdrive
-- binding -- koneksi DIREK Supabase (bukan pooler), lihat decisions.md
-- Keputusan #2.
--
-- Jalankan sebagai role yang punya privilege CREATEROLE (mis. role default
-- Supabase `postgres`). Password TIDAK di-hardcode -- substitusi lewat
-- parameter runtime (pola sama infra/sql/3.9_monitoring_metrics_schema.sql
-- dst).

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'monitoring_public_reader') THEN
    EXECUTE format('CREATE ROLE monitoring_public_reader WITH LOGIN PASSWORD %L', :'monitoring_public_reader_password');
  END IF;
END
$$;

GRANT CONNECT ON DATABASE postgres TO monitoring_public_reader;
GRANT USAGE ON SCHEMA monitoring TO monitoring_public_reader;
GRANT SELECT ON monitoring.metrics_snapshot TO monitoring_public_reader;

-- Scoped ketat: monitoring_public_reader TIDAK bisa INSERT/UPDATE/DELETE,
-- TIDAK bisa baca schema lain manapun (mlflow/quality/predictions/drift/
-- public) -- ini kredensial yang akan dipegang komponen PALING terekspos
-- di seluruh proyek (API publik tanpa login), jadi blast radius-nya WAJIB
-- paling sempit. Diverifikasi eksplisit (positif+negatif) di
-- milestones/3.10-.../logs.md sebelum dipakai Cloudflare Worker mana pun.
