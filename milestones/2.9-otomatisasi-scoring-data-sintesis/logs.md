# Logs — Milestone 2.9: Otomatisasi Scoring Data Sintesis

## Checkpoint 1 — Fondasi: kredensial, migrasi skema, trigger SQL

**Mulai:** 2026-08-13.

**Task 1-3:** Tiga file SQL ditulis — `infra/sql/2.9_synthetic_reader_grant.sql`, `infra/sql/2.9_batch_predictions_synthetic_columns.sql`, `infra/sql/2.9_synthetic_trigger.sql`. Sebelum menulis Task 1, RLS status kedua tabel synthetic diverifikasi langsung (`pg_class.relrowsecurity`): kedua tabel RLS aktif TANPA policy (deny-all default) — SQL ditulis dengan policy eksplisit dari awal (menghindari pengulangan temuan M2.5).

**Task 4:** User diminta membuat GitHub PAT fine-grained (repo-scoped, `Contents: Read and write`) dan menambahkannya ke `.env` sebagai `GITHUB_REPOSITORY_DISPATCH_PAT` — TIDAK dipaste ke chat. Dikonfirmasi ada lewat `grep -q` (cek key, bukan value).

**Task 5:** Konfirmasi eksplisit diminta ke user sebelum eksekusi terhadap production (mengubah skema + role akses) — dikonfirmasi. Ketiga file SQL dijalankan dalam SATU transaksi (`conn.autocommit=False`, commit di akhir kalau semua sukses). Lalu `vault.create_secret()` dengan PAT dari `.env` (parameterized query, nilai tidak pernah dicetak).

**Verifikasi (query langsung, bukan baca output "OK"):**
- `information_schema.role_table_grants`: `batch_reader` SELECT pada `telco_customers_synthetic` + `synthetic_generation_runs`. ✓
- `pg_policies`: policy `batch_reader_select` ada di kedua tabel. ✓
- `information_schema.columns` `predictions.batch_predictions`: `customer_id` nullable, `customer_key`/`generation_id` (uuid) ada. ✓
- `pg_constraint`: `batch_predictions_exactly_one_identity` ada dengan definisi benar. ✓
- `pg_indexes`: `idx_batch_predictions_customer_key`/`idx_batch_predictions_generation_id` ada. ✓
- `pg_extension`: `pg_net` versi 0.20.4 terinstall. ✓
- `pg_trigger`: `trg_notify_synthetic_generation_completed` ada, `tgenabled='O'` (aktif). ✓
- `vault.secrets`: nama `github_repository_dispatch_pat` ada (nilai TIDAK di-query). ✓
- `predictions.batch_predictions` count: 1.193.488 baris (data existing tidak tersentuh migrasi additive). ✓

**Selesai, commit:** `f0d30b2` (feat).

## Checkpoint 2 — Output 1/KK1: `batch_scoring_flow()` bisa scoring `telco_customers_synthetic`

**Task 6:** `orchestration/flows/batch_scoring.py` diparameterisasi (`source_table`, `generation_id`). `_extract_from_source`/`_extract_from_synthetic` dipisah dari `extract_raw_data` (branch internal). `score_batch` mendeteksi identitas dari kolom DataFrame (`customer_key` in df.columns). `write_predictions` backward-compatible (kolom `customer_key` absen ditangani `getattr(row, "customer_key", None)`).

**Verifikasi impor:** `.venv/Scripts/python.exe -c "import orchestration.flows.batch_scoring"` — OK.

**Verifikasi non-regresi:** `pytest tests/ -q -m "not integration"` → **164 passed**, 0 gagal (baseline sebelum milestone ini juga 164 non-integration). `pytest tests/orchestration -v -m integration` (terhadap Supabase+MLflow real) → **4 passed** (test M2.5 lama, tanpa modifikasi ekspektasi).

**Task 7:** 2 test baru ditulis di `tests/orchestration/test_batch_scoring.py`:
- `test_synthetic_scoring_writes_customer_key_not_customer_id` — fixture `synthetic_flow_result` mencari `generation_id` NYATA berstatus `completed` secara dinamis (bukan hardcode UUID, supaya tidak rapuh), scoring subset kecil (`limit=5`).
- `test_source_path_unaffected_by_synthetic_support` — non-regresi eksplisit: jalur default (`telco_customers_source`) tetap `customer_id` terisi, `customer_key`/`generation_id` NULL.

**Bug ditemukan+diperbaiki saat run test pertama:** `KeyError: 'MonthlyCharges'` di `run_quality_gate_task` — `NUMERIC_COLUMNS`/`CATEGORICAL_COLUMNS` (PascalCase) dipakai langsung terhadap DataFrame `telco_customers_synthetic` yang SUDAH snake_case sejak extract (beda dari `telco_customers_source` yang di-rename BELAKANGAN di `score_batch`). Traceback lengkap dari `run_gate()` → `_compute_null_proportions()` → `df[col]`. **Diperbaiki:** fungsi baru `_quality_gate_columns(source_table)` memetakan nama kolom lewat `RAW_PASCAL_TO_SNAKE` kalau `source_table == SYNTHETIC_TABLE`.

**Re-run setelah perbaikan:** `pytest tests/orchestration -v -m integration` → **6 passed** (4 lama + 2 baru), 0 gagal.

**Task 8 — Uji coba terkontrol KK1 (skala penuh, data real, HASIL DISIMPAN):** `batch_scoring_flow(source_table="telco_customers_synthetic", generation_id="cb62bcaa-f141-4682-a6b5-2d4795d7a48c")` dijalankan SUNGGUHAN (bukan `.fn()`, tracked Prefect Cloud — flow run `prompt-leopard`). **Hasil:** 1.000 baris ditulis, `batch_run_id=64d0892b-ebc3-4d0f-83c0-9688d810df49`. **Verifikasi query langsung:** 0 NULL `customer_key`/`generation_id`/lineage (`model_version`, `flow_run_id`), 0 baris `customer_id` non-NULL (benar, exactly-one-identity). `JOIN` `customer_key` ke `telco_customers_synthetic` untuk `generation_id` yang sama → **1000/1000 baris cocok**. Spot-check jalur `telco_customers_source`: total baris tidak berubah (1.193.488, sama sebelum+sesudah run ini) — membuktikan jalur lama tidak tersentuh.

**Selesai, commit:** `cafff5b` (feat).

## Checkpoint 3 — Output 2/KK2: trigger event-driven end-to-end

**Task 9:** `.github/workflows/synthetic-auto-scoring.yml` ditulis — trigger `on: repository_dispatch: types: [synthetic-data-arrived]`, `runs-on: ubuntu-latest`, `python -m orchestration.flows.batch_scoring` (pola sama `batch-scoring.yml`/KD-1). Commit `63ea91d` (feat).

**Push:** Konfirmasi eksplisit diminta ke user untuk push 3 commit Checkpoint 1-3 ke `origin/main` (dibutuhkan supaya `repository_dispatch` mengenali workflow) — dikonfirmasi, di-push (`3a0df1f..63ea91d`).

**Task 10 — Uji coba terkontrol KK2 (fault-injection NYATA, data test dibersihkan sesudahnya):**
1. Baseline: `gh run list --workflow=synthetic-auto-scoring.yml` → kosong (belum pernah ada run).
2. INSERT terkontrol: 1 baris `telco_customers_synthetic` (nilai realistis dalam domain skema, `customer_key=2243af81-1e55-4128-95a9-30907a8dc4ef`) + 1 baris `synthetic_generation_runs` (`generation_id=6ce13dc0-356c-4145-bd18-5752bf1e0147`, `status='completed'`) — INSERT KEDUA inilah yang memicu trigger `trg_notify_synthetic_generation_completed` secara NYATA (bukan `gh workflow run` manual).
3. **Verifikasi cascade, dalam ~3 detik:** `net._http_response` → `status_code=204` (GitHub API menerima dispatch). `gh run list` → run BARU `in_progress`, `Triggered via repository_dispatch`, event `synthetic-data-arrived` — **muncul OTOMATIS tanpa satu pun perintah manual**.
4. `gh run watch 31700181853` → **SUCCESS, 1m43s**. Log: `Extracted 1 baris dari telco_customers_synthetic` (filter `generation_id` bekerja benar — cuma 1 baris test, bukan 1.000 baris generation lama), gerbang kualitas PASS, `Scored 1 baris`, `Menulis 1 baris prediksi (batch_run_id=d3f819e6-fe6c-4e03-bfb9-8b4d76effc7f)`.
5. **Verifikasi hasil query langsung:** baris di `predictions.batch_predictions` untuk `batch_run_id` tsb → `customer_key`/`generation_id` COCOK PERSIS dengan fixture test yang di-insert (bukan kebetulan/data lama).
6. **Cleanup:** `DELETE` baris test dari `predictions.batch_predictions`, `telco_customers_synthetic`, `synthetic_generation_runs` — 1 baris masing-masing terhapus, dikonfirmasi `rowcount`.

**Selesai** (Task 9 sudah commit `63ea91d`; Task 10 murni verifikasi live, tidak ada perubahan file tambahan untuk di-commit).

## Checkpoint 4 — Dokumentasi

**Task 11:** `docs/keputusan-tertunda.md` diperbarui — KT-4 DITUTUP (catatan "Update 2026-08-13"), KT-1 diberi catatan "Fase 2 SEBAGIAN dimulai, BUKAN cutover penuh" (eksplisit: `telco_customers_source` TIDAK dipensiunkan).

**Task 12:** `milestones/2.9-otomatisasi-scoring-data-sintesis/{decisions,logs,report}.md` ditulis (file ini + `decisions.md` + `report.md`).
