# Report — Milestone 2.9: Otomatisasi Scoring Data Sintesis

## Ringkasan

Milestone 2.9 SELESAI — sistem sekarang bisa scoring `telco_customers_synthetic` secara otomatis (event-driven) begitu generator menghasilkan generation baru berstatus `completed`, tanpa intervensi manual. Ini bukan bagian resmi dokumen rancangan (`mlops-02-pipeline-orchestration.md`) — perluasan cakupan yang diminta user secara sadar, follow-up langsung dari pertanyaan "kenapa sistem belum bisa auto-predict data sintesis baru" di sesi sebelumnya.

Komponen yang dibangun: 3 file SQL fondasi (grant+RLS, migrasi skema `predictions.batch_predictions`, trigger `pg_net`), parameterisasi `orchestration/flows/batch_scoring.py` (satu flow, dua source table), workflow GitHub Actions baru (`synthetic-auto-scoring.yml`, trigger `repository_dispatch`).

## Kriteria Keberhasilan vs Bukti

| KK | Kriteria | Bukti |
|---|---|---|
| **KK1** | `batch_scoring_flow()` bisa scoring `telco_customers_synthetic`, hasil tertulis dengan `customer_key` terisi benar, TANPA regresi ke path `telco_customers_source`. | Scoring skala penuh (1.000 baris real, `generation_id=cb62bcaa-...`) — 0 NULL `customer_key`/`generation_id`/lineage, 1000/1000 `customer_key` cocok tabel sumber (`JOIN` langsung). Non-regresi: `pytest tests/ -q` penuh 164 passed (non-integration) + 6 passed (integration, 4 lama + 2 baru), 0 gagal. Spot-check: total baris `source_table='telco_customers_source'` tidak berubah sebelum/sesudah run synthetic. |
| **KK2** | Trigger event-driven end-to-end: generation baru selesai otomatis memicu scoring tanpa intervensi manual. | Fault-injection NYATA (INSERT terkontrol ke `synthetic_generation_runs`, BUKAN `gh workflow run` manual) → `net._http_response` HTTP 204 dalam <1 detik → run GitHub Actions muncul OTOMATIS (`gh run list`, `Triggered via repository_dispatch`) dalam hitungan detik → run SUCCESS 1m43s → 1 baris prediksi tertulis dengan `customer_key`/`generation_id` cocok persis fixture test. Cascade utuh dari trigger SQL sampai baris tertulis, tanpa satu pun langkah manual di antaranya. |

## Keputusan Final

Lihat [`decisions.md`](./decisions.md) — 7 keputusan: (1) trigger event-driven `pg_net`+`repository_dispatch` (dikonfirmasi user), (2) extend `predictions.batch_predictions` dengan `customer_key`/`generation_id` nullable (dikonfirmasi user), (3) extend role `batch_reader` existing bukan role baru, (4) PAT disimpan Supabase Vault bukan GitHub Secrets (forced by arah panggilan), (5) `generation_id` dibawa `client_payload` bukan state table terpisah, (6) workflow GitHub Actions terpisah dari `batch-scoring.yml`, (7) parameterisasi satu flow (bukan flow terpisah) untuk kedua source table.

## Perubahan dari Plan Awal

Tidak ada penyimpangan struktural dari plan — seluruh 4 checkpoint dan 12 task dieksekusi sesuai urutan yang direncanakan. Satu bug ditemukan+diperbaiki di tengah jalan (Checkpoint 2): `NUMERIC_COLUMNS`/`CATEGORICAL_COLUMNS` PascalCase menyebabkan `KeyError` terhadap DataFrame synthetic yang sudah snake_case — ini TIDAK diantisipasi eksplisit di plan (plan hanya menyebut "identity-column handling" untuk `score_batch`/`write_predictions`, tidak menyebut gerbang kualitas data), ditemukan lewat test integration pertama (bukan dibiarkan lolos), diperbaiki dengan `_quality_gate_columns()`.

## Keterbatasan dan Item Terbuka

- **Tidak ada retry/alerting otomatis kalau `net.http_post` gagal terkirim** (mis. GitHub API down sesaat, kredensial PAT expired/dicabut) — trigger SQL cuma `RAISE WARNING`/`RAISE LOG`, tidak ada mekanisme retry terjadwal atau notifikasi kalau dispatch gagal. Mitigasi termurah saat ini: re-trigger manual (`BATCH_GENERATION_ID` eksplisit via `gh workflow run` kalau perlu, meski `synthetic-auto-scoring.yml` sengaja tidak diberi `workflow_dispatch` — perlu ditambahkan kalau kebutuhan ini nyata di masa depan).
- **Belum ada test otomatis untuk skenario PAT expired/dicabut atau `pg_net` gagal** — uji coba terkontrol KK2 membuktikan jalur SUKSES, bukan jalur kegagalan trigger itu sendiri (beda dari KK1 M2.5 yang eksplisit menguji rollback+retry).
- **KT-1 (kontrak dua-fase M1.6) TETAP TERBUKA** — milestone ini TIDAK memutuskan kapan/apakah `telco_customers_source` dipensiunkan; `batch_scoring_flow()` tanpa parameter eksplisit masih default ke `telco_customers_source`. Lihat `docs/keputusan-tertunda.md` KT-1 (update 2026-08-13).
- **Bentuk pasti `customer_key`** (bagaimana user men-generate-nya, stabilitasnya lintas generation berikutnya untuk "pelanggan simulasi" yang sama) TIDAK diverifikasi ulang — di luar cakupan milestone ini (lihat `docs/keputusan-tertunda.md` KT-4, update 2026-08-13).
- **Volume generation mendatang belum diuji** — KK1 diverifikasi untuk 1.000 baris (generation existing) dan KK2 untuk 1 baris (fixture test). Generation jauh lebih besar (mis. puluhan ribu baris per run) belum punya data baseline waktu eksekusi nyata di jalur ini (beda dari `telco_customers_source` yang punya baseline 594rb baris dari M2.5).

## Follow-up

- Kalau kebutuhan retry/alerting untuk dispatch gagal jadi nyata (bukan hipotetis), evaluasi tambah tabel log pengiriman + mekanisme retry terjadwal.
- Keputusan cutover penuh KT-1 (mempensiunkan `telco_customers_source`) tetap menunggu momen yang tepat — bukan bagian milestone ini.
- Kalau generation berikutnya jauh lebih besar dari 1.000 baris, ukur waktu eksekusi nyata dan bandingkan terhadap timeout GitHub Actions job (default 6 jam, jauh di atas ekspektasi saat ini) serta timeout `net.http_post` (5000ms, cukup untuk POST awal, tidak relevan ke durasi scoring itu sendiri karena async).
