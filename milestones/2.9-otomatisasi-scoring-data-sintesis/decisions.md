# Decisions — Milestone 2.9: Otomatisasi Scoring Data Sintesis

## Konteks

Milestone ini TIDAK dideskripsikan eksplisit di `docs/02-implementation-plan/mlops-02-pipeline-orchestration.md` — perluasan cakupan yang diminta user secara sadar, dipicu pertanyaan "kenapa sistem belum bisa auto-predict ketika ada data sintesis baru masuk". Analisis sesi sebelumnya menemukan 4 blocker independen (SOURCE_TABLE hardcoded, role tanpa izin baca, tidak ada jadwal berguna, tidak ada mekanisme event) plus satu blocker terpisah (KD-1, Prefect Managed + LightGBM, sudah diatasi di milestone berjalan sebelum ini lewat `.github/workflows/batch-scoring.yml`). Milestone 2.9 menyelesaikan 3 blocker yang tersisa.

Dua keputusan dikonfirmasi user via `AskUserQuestion` sebelum plan ditulis:
1. Mekanisme trigger: event-driven (Postgres `pg_net` → GitHub `repository_dispatch`) vs polling (GitHub Actions cron). User memilih **event-driven**.
2. Skema identitas prediksi sintesis: extend `predictions.batch_predictions` (kolom `customer_key` nullable) vs tabel terpisah. User memilih **extend tabel existing**.

## Keputusan Teknis

### 1. Trigger: Postgres trigger + `pg_net` → GitHub `repository_dispatch` (event-driven, bukan polling)

**Keputusan:** Trigger SQL `AFTER INSERT OR UPDATE ON synthetic_generation_runs FOR EACH ROW WHEN (NEW.status = 'completed')` (`infra/sql/2.9_synthetic_trigger.sql`) memanggil `net.http_post()` ke `POST https://api.github.com/repos/Ardiyanto24/telco-churn-mlops/dispatches` dengan `event_type=synthetic-data-arrived` dan `client_payload={generation_id, inserted_count}`. GitHub Actions punya workflow baru (`synthetic-auto-scoring.yml`) bertrigger `on: repository_dispatch`.

**Kenapa:** Dikonfirmasi user (`AskUserQuestion`). Nyaris real-time (diverifikasi: HTTP 204 dalam <1 detik, run GitHub Actions muncul otomatis dalam hitungan detik — lihat `logs.md` Checkpoint 3), tidak perlu proses yang di-host 24/7 (`pg_net` async dari dalam Postgres yang sudah ada, `supabase_vault` juga sudah terinstall).

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Polling GitHub Actions cron** (mengecek `synthetic_generation_runs` tiap N menit) — lebih sederhana, reuse persis pola `batch-scoring.yml` (KD-1), tapi DITOLAK user: latensi sampai interval berikutnya bertentangan dengan tujuan eksplisit "auto predict ketika data masuk", bukan "dalam N menit setelah data masuk".

### 2. Skema prediksi: extend `predictions.batch_predictions` (bukan tabel terpisah)

**Keputusan:** `infra/sql/2.9_batch_predictions_synthetic_columns.sql` — `customer_id` jadi nullable, tambah `customer_key uuid NULL`, tambah `generation_id uuid NULL`, tambah CHECK `batch_predictions_exactly_one_identity` (`(customer_id IS NOT NULL AND customer_key IS NULL) OR (customer_id IS NULL AND customer_key IS NOT NULL)`), index baru di `customer_key` dan `generation_id`.

**Kenapa:** Dikonfirmasi user (`AskUserQuestion`). Satu tabel prediksi tetap satu sumber kebenaran hasil (kolom `source_table` yang sudah ada membedakan asal baris) — konsisten prinsip proyek ini. Migrasi murni additive — diverifikasi 1.193.488 baris existing tidak tersentuh (lihat `logs.md` Checkpoint 1).

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Tabel baru `predictions.synthetic_predictions`** — tidak mengubah constraint tabel existing sama sekali, tapi DITOLAK user: memecah hasil prediksi jadi 2 tabel, konsumen (dashboard M3.x nanti) harus UNION keduanya, precedent "satu sumber kebenaran per jenis data" jadi tidak konsisten.

### 3. Kredensial baca `telco_customers_synthetic`: extend role `batch_reader` existing, bukan role baru

**Keputusan:** `infra/sql/2.9_synthetic_reader_grant.sql` — `GRANT SELECT` ke `batch_reader` (role existing M2.5) atas `telco_customers_synthetic` dan `synthetic_generation_runs`, plus RLS policy eksplisit per tabel (RLS aktif tanpa policy pada kedua tabel dikonfirmasi lewat query `pg_class.relrowsecurity` sebelum eksekusi — pola sama M2.5 Keputusan #5).

**Kenapa:** Pola akses identik (baca-saja data mentah pelanggan untuk scoring) — `batch_reader` sudah tepat secara semantik, cuma dibatasi Fase 1 M1.6 yang sekarang sengaja diperluas SEBAGIAN (lihat `docs/keputusan-tertunda.md` KT-1, update 2026-08-13). Menghindari proliferasi role least-privilege tanpa perbedaan pola akses nyata.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Role baru `synthetic_reader` terpisah** — lebih ketat secara isolasi, tapi TIDAK dipilih: menambah 1 secret baru untuk dikelola tanpa manfaat isolasi berarti pada skala proyek ini.

### 4. GitHub PAT untuk `repository_dispatch`: disimpan di Supabase Vault, bukan GitHub Secrets

**Keputusan:** PAT fine-grained (scoped HANYA ke repo `telco-churn-mlops`, permission `Contents: Read and write`) dibuat user secara manual di GitHub, disimpan via `vault.create_secret(pat_value, 'github_repository_dispatch_pat')`, dibaca fungsi trigger lewat `vault.decrypted_secrets`.

**Kenapa:** Forced oleh arah panggilan — trigger dipanggil DARI Postgres (bukan dari GitHub Actions), GitHub Secrets (cuma terbaca di runner GitHub Actions) tidak relevan di titik ini. `supabase_vault` sudah terinstall persis untuk kasus ini. Tidak ada alternatif dipertimbangkan karena forced by arsitektur — PAT juga TIDAK PERNAH ditulis ke chat/commit, hanya lewat `.env` lokal (gitignored) lalu dibaca programatik ke Vault.

### 5. Filter "data baru": `generation_id` dibawa lewat `client_payload`, bukan state table terpisah

**Keputusan:** `client_payload.generation_id` diteruskan sebagai parameter eksplisit ke `batch_scoring_flow(source_table="telco_customers_synthetic", generation_id=...)`. `extract_raw_data`/`_extract_from_synthetic` memfilter `WHERE generation_id = %(generation_id)s`.

**Kenapa:** Trigger fire PERSIS satu kali per `generation_id` selesai — event tahu identitas presis apa yang baru. Melacak state "sudah diproses" terpisah menambah kompleksitas dan risiko drift tanpa manfaat nyata dibanding percaya pada identitas yang sudah dibawa event itu sendiri.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Tabel state `predictions.synthetic_scoring_state`** (last processed generation_id) — lebih robust kalau event PERNAH hilang, tapi DITOLAK sebagai over-engineering: mitigasi termurah kalau event hilang adalah re-trigger manual (`BATCH_GENERATION_ID` eksplisit sudah didukung `__main__` block `batch_scoring.py` secara gratis, lihat Keputusan #7), bukan membangun state-tracking permanen di muka.

### 6. Workflow GitHub Actions terpisah (`synthetic-auto-scoring.yml`), bukan extend `batch-scoring.yml`

**Keputusan:** File workflow BARU `.github/workflows/synthetic-auto-scoring.yml` dengan trigger `on: repository_dispatch`, bukan menambah trigger kedua ke `batch-scoring.yml` (yang tetap `workflow_dispatch`-only untuk `telco_customers_source`, TIDAK diubah sama sekali di milestone ini).

**Kenapa:** Kredensial dasar sama (role `batch_reader` yang sama, sudah diperluas), tapi sumber trigger berbeda (`repository_dispatch` vs `workflow_dispatch`) dan env var yang relevan berbeda (`BATCH_SOURCE_TABLE`/`BATCH_GENERATION_ID` vs `BATCH_SCORING_LIMIT`). Dua file kecil dengan satu tanggung jawab jelas lebih mudah diaudit dibanding satu file dengan logic kondisional — tetap satu sumber kebenaran LOGIC (`batch_scoring_flow()` yang sama dipanggil keduanya via `python -m orchestration.flows.batch_scoring`), cuma beda konfigurasi trigger/env di level YAML.

### 7. Parameterisasi `batch_scoring.py`: satu flow menerima `source_table`+`generation_id`, bukan flow terpisah

**Keputusan:** `batch_scoring_flow(limit=None, source_table=SOURCE_TABLE, generation_id=None)` — `extract_raw_data`/`run_quality_gate_task`/`score_batch`/`write_predictions` bercabang secara internal sesuai `source_table`, bukan duplikasi flow. `score_batch` mendeteksi kolom identitas (`id` vs `customer_key`) dari DataFrame; `write_predictions` backward-compatible dengan DataFrame yang HANYA punya kolom `customer_id` (dipakai test existing M2.5).

**Kenapa:** Satu sumber kebenaran orchestration logic (prinsip proyek ini) — duplikasi flow untuk 2 source table akan mengulang 4 task yang identik strukturnya, cuma beda query/identitas. Backward-compatibility WAJIB karena `orchestration/flows/batch_scoring.py` sudah dipakai produksi sejak M2.5 (KD-1 baru saja memverifikasi jalur `telco_customers_source` bekerja lewat GitHub Actions) — dibuktikan `pytest tests/ -q` penuh 0 regresi (lihat `logs.md` Checkpoint 2).

**Bug ditemukan+diperbaiki saat implementasi:** `NUMERIC_COLUMNS`/`CATEGORICAL_COLUMNS` (module constant, PascalCase, cocok `telco_customers_source` SEBELUM rename) menyebabkan `KeyError: 'MonthlyCharges'` saat dipakai terhadap DataFrame `telco_customers_synthetic` yang SUDAH snake_case sejak extract (ditemukan lewat test integration pertama, bukan asumsi). Diperbaiki dengan `_quality_gate_columns(source_table)` yang memetakan nama kolom sesuai konvensi masing-masing tabel.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Flow Prefect terpisah untuk synthetic** (mis. `synthetic_scoring_flow()`) — tidak dipertimbangkan serius: menduplikasi 4 task yang secara struktural identik (extract→gate→score→write), melanggar prinsip satu sumber kebenaran logic orchestration.

## Catatan: Verifikasi yang Dilakukan Sebelum Implementasi (Bukan Asumsi)

Sebelum menulis plan, diverifikasi langsung ke database live (bukan dari dokumentasi lama):
- `telco_customers_synthetic` sudah berisi 1.000 baris real, kolom `customer_key` sudah ada (kontradiksi `docs/keputusan-tertunda.md` KT-4 versi lama).
- `column_mapping.py` docstring mengonfirmasi snake_case MENGIKUTI `telco_customers_synthetic` (bukan sebaliknya).
- `quality/gate.py`/`baseline.py` sudah source_table-agnostic sejak M2.4, cold-start (0 riwayat) ditafsirkan "belum cukup data" bukan anomali.
- `pg_net` TERSEDIA (versi 0.20.4) tapi belum terinstall; `supabase_vault` sudah terinstall dengan `create_secret`/`decrypted_secrets`.
- `batch_reader` dikonfirmasi `permission denied` untuk kedua tabel synthetic sebelum grant diterapkan.
