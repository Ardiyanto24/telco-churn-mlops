# Report — Milestone 2.5: Batch Scoring DAG

## Ringkasan

Milestone 2.5 selesai — milestone terbesar sejauh ini di jalur Orang #2, menghasilkan pipeline batch scoring nyata: `orchestration/flows/batch_scoring.py` (4 task Prefect dengan dependency eksplisit: extract → gerbang kualitas data M2.4 → score → write), tabel hasil `predictions.batch_predictions` (append-only, lineage lengkap), dan perluasan kecil package `churn_prediction` (`predict_active()`, `resolve_alias_version()`, sentralisasi `column_mapping.py`).

Dua keputusan awal dikonfirmasi user (append-only, skala penuh dengan verifikasi terkontrol bukan jadwal rutin). Selama eksekusi ditemukan dan diselesaikan **tiga bug/gap nyata** (RLS Supabase, bug lintas-platform MLflow, kesalahan urutan validasi saat refactor) dan **satu keterbatasan platform yang diterima secara sadar** (Prefect Managed + LightGBM) — semuanya didokumentasikan lengkap, bukan disembunyikan.

## Kriteria Keberhasilan vs Bukti

| KK | Kriteria | Bukti |
|---|---|---|
| **KK1** | DAG berjalan end-to-end terjadwal, prediksi tertulis lengkap lineage. | **Skala penuh (594.194 baris) dibuktikan lewat run lokal** (Task 10): 0 kolom lineage NULL, 594.194 `customer_id` distinct, waktu 551.5 detik (dikoreksi dari estimasi awal 1-2 menit). **Mekanisme "terjadwal via infrastruktur" dibuktikan SEBAGIAN di Prefect Managed**: `extract_raw_data` dan gerbang kualitas data sukses lewat trigger manual ter-track Prefect Cloud; task `score_batch` (LightGBM) gagal karena keterbatasan platform yang diterima (KD-1, `docs/keterbatasan-diterima.md`) — bukan kegagalan mekanisme DAG/dependency-nya sendiri. |
| **KK2** | Kegagalan tersimulasi → retry sesuai konfigurasi, tidak ada data tidak konsisten. | `tests/orchestration/test_batch_scoring.py`: `write_predictions` dengan baris sengaja melanggar CHECK constraint → 0 baris ter-insert (rollback penuh, bukan sebagian). `extract_raw_data` dengan koneksi disimulasikan gagal 2x → sukses di percobaan ke-3 (retry Prefect bekerja). |
| **KK3** | Parity batch vs pemanggilan langsung inference service. | `test_batch_predictions_match_direct_predict_active_call` — `predict_active()` dipanggil langsung vs hasil tersimpan di `predictions.batch_predictions` untuk pelanggan sama, identik (`churn_probability`, `churn_label`, `model_version`). |
| **KK4** | Lineage bisa ditelusuri balik. | `test_lineage_traces_back_to_real_mlflow_version` — `model_version`/`model_alias`/`batch_run_id`/`flow_run_id` pada baris hasil tertelusur balik ke versi MLflow aktif sungguhan dan run Prefect yang menghasilkannya. |

`pytest tests/ -q` penuh: **170 passed** (166 sebelumnya + 4 baru), tidak ada regresi.

## Keputusan Final

Lihat [`decisions.md`](./decisions.md) — 8 keputusan: (1) tabel append-only + role least-privilege baru, (2) skala penuh tanpa jadwal rutin aktif, (3) `predict_active()` dengan `model_version` konkret bukan alias, (4) sentralisasi `column_mapping.py`, (5) RLS Supabase butuh policy eksplisit (temuan+perbaikan), (6) bug lintas-platform path MLflow (temuan+perbaikan, BUKAN keterbatasan diterima — ada mitigasi konkret), (7) Prefect Managed + LightGBM (keterbatasan DITERIMA sadar, dicatat `docs/keterbatasan-diterima.md` KD-1), (8) follow-up 2026-08-13 — KD-1 diatasi untuk kebutuhan run terjadwal lewat GitHub Actions (`batch-scoring.yml`), Managed sendiri tetap terbatas. Plus catatan salah ketik "Milestone 2.6" di dokumen sumber (seharusnya M2.7).

## Perubahan dari Plan Awal

- **Task 11 tidak fully-passed seperti direncanakan** — plan awal mengharapkan satu run Managed `COMPLETED` bersih. Realitanya: 4 kali trigger, 2 bug ditemukan+diperbaiki di tengah jalan (RLS baru relevan di Checkpoint 1 bukan 3, tapi bug path+libgomp murni ditemukan di Task 11 sendiri), dan hasil akhir diterima SEBAGIAN (2 dari 4 task sukses di Managed) dengan keterbatasan didokumentasikan eksplisit — bukan penyimpangan yang disembunyikan, konsisten prinsip "log adalah catatan peristiwa, bukan hasil yang dipoles".
- **Dokumen baru `docs/keterbatasan-diterima.md`** dibuat di tengah milestone atas permintaan eksplisit user — bukan bagian plan awal, tapi keputusan proses yang berlaku project-wide mulai sekarang (dicatat di `CLAUDE.md`/`AGENT.md`).
- Selebihnya, seluruh 4 checkpoint dan struktur task dieksekusi sesuai urutan yang direncanakan.

## Keterbatasan dan Item Terbuka

- **Prefect Managed tidak bisa menjalankan task yang memuat model LightGBM** (`docs/keterbatasan-diterima.md` KD-1) — berdampak ke Milestone 2.6 (kalau ada task serupa), 2.7 (CI/CD, kalau runner-nya Managed-based), dan 2.8 (sanity check artifact yang memuat model). **Update 2026-08-13 (Checkpoint 5):** untuk kebutuhan RUN TERJADWAL/OTOMATIS (bukan Managed itu sendiri, yang tetap terbatas), sudah ada jalur mitigasi terverifikasi — `.github/workflows/batch-scoring.yml` (GitHub Actions, `ubuntu-latest`) menjalankan `batch_scoring_flow()` langsung, terbukti sukses memuat LightGBM (run [31694778869](https://github.com/Ardiyanto24/telco-churn-mlops/actions/runs/31694778869)). Lihat `decisions.md` Keputusan #8.
- **Mitigasi bug path MLflow (`.as_posix()`) belum diverifikasi menutup 100% kasus** — registrasi versi model berikutnya (M2.8) WAJIB diverifikasi ulang lintas-platform, bukan diasumsikan aman selamanya.
- **Waktu run skala penuh (~9.2 menit) jadi baseline nyata pertama** untuk Milestone 2.6 (Isolasi Beban) — jauh dari estimasi awal, harus dipakai sebagai angka nyata bukan tebakan lama.
- **Jadwal rutin produksi belum diaktifkan** — trigger sama seperti M2.3/M2.4 (generator/data harian asli aktif). **Update 2026-08-13:** pemicu ini sebagian sudah terjadi (`telco_customers_synthetic` sudah berisi 1.000 baris dari satu run generator, `synthetic_generation_runs.created_at=2026-08-13 09:57:27 UTC`, di luar sesi manapun yang tercatat) — TAPI `batch_scoring_flow()` masih hardcode membaca `telco_customers_source` (statis, tidak berubah), jadi cutover ke tabel synthetic (KT-1 Fase 2) masih keputusan terbuka terpisah, sengaja BELUM diaktifkan sebagai cron (lihat `decisions.md` Keputusan #8) untuk menghindari prediksi duplikat identik.

## Follow-up

- **Milestone 2.6 (Isolasi Beban terhadap PostgreSQL)** siap dikerjakan dengan baseline nyata dari milestone ini (waktu extract ~45s, score ~4m25s, write ~4m1s untuk 594rb baris) dan M2.3 (N/A, tidak ada beban refresh feature store).
- **Milestone 2.7 (CI/CD)** perlu mempertimbangkan keterbatasan KD-1 saat merancang runner CI — kalau CI juga berbasis Managed/container minimal serupa, gerbang unit test yang memuat model (`test_predictor.py`, dst.) berisiko kena masalah sama.
- **Milestone 2.8** perlu baca `docs/keterbatasan-diterima.md` KD-1 sebelum merancang mekanisme sanity-check artifact otomatis (kalau dijalankan di infra serupa Managed), dan perlu re-verifikasi mitigasi path MLflow (Keputusan #6) setiap registrasi versi baru.
- **Cutover Fase 2 (KT-1)** — belum dikerjakan milestone manapun: `SOURCE_TABLE` di `batch_scoring.py` hardcode `telco_customers_source`, role `batch_reader` tidak punya izin baca `telco_customers_synthetic` (dikonfirmasi `permission denied` saat verifikasi 2026-08-13), dan tidak ada mekanisme event/trigger untuk data baru. KD-1 (jalur eksekusi) sudah tidak jadi blocker untuk cutover ini kalau/ketika diputuskan — 3 blocker lain di atas tetap terbuka.
