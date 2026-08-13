# Report — Milestone 2.7: CI/CD dan Verifikasi Parity Otomatis

## Ringkasan

Milestone 2.7 membangun 4 gerbang CI/CD wajib (Bagian 6.1 dokumen arsitektur) di atas `.github/workflows/test.yml` — tapi menemukan lebih dulu bahwa workflow ini sudah gagal di **setiap push** sejak repo terhubung ke GitHub (M1.6), akibat mismatch versi Python yang tidak pernah ketahuan. Sebelum satu pun gerbang baru bisa berarti, fondasi CI yang rusak ini diperbaiki lebih dulu (Checkpoint 1).

Sepanjang milestone, **empat bug nyata ditemukan dan diperbaiki** — semuanya lewat verifikasi run CI sungguhan (`gh run watch`/`gh run view --log`), bukan diasumsikan dari baca kode: mismatch versi Python, `orchestration/` tidak importable lewat bare `pytest`, kuirk cache MLflow client lintas tracking-URI, dan satu secret GitHub yang sempat terlewat provisioning. Dua uji coba terkontrol (branch sekali-pakai, tidak menyentuh `main`) membuktikan gerbang benar-benar bekerja: kode transformasi yang sengaja dirusak menghentikan pipeline SEBELUM gerbang integrasi sempat jalan; jalur batch yang sengaja dibuat menyimpang dari `predict_active()` terdeteksi spesifik oleh test parity.

## Kriteria Keberhasilan vs Bukti

| KK | Kriteria | Bukti |
|---|---|---|
| **KK1** | Perubahan kode yang sengaja merusak modul transformasi menyebabkan CI gagal di gerbang unit test, sebelum sempat ke gerbang berikutnya. | **DIPENUHI, uji coba terkontrol run nyata.** Branch `ci-test-broken-transform` (BinaryEncoder dirusak) → run `31670969575`: `unit-tests` GAGAL, `integration-tests` **tidak pernah jalan** (0 detik, `needs:` menghentikan pipeline). |
| **KK2** | Perubahan yang membuat jalur batch vs real-time (disimulasikan) berbeda output terdeteksi test parity dan menggagalkan pipeline. | **DIPENUHI, uji coba terkontrol run nyata.** Branch `ci-test-broken-parity` (`score_batch` disimpangkan dari `predict_active()`) → run `31671095111`: `integration-tests` GAGAL spesifik `AssertionError` pada `test_batch_predictions_match_direct_predict_active_call`. |
| **KK3** | Orang #3 bisa mengintegrasikan gerbang deployment-nya tanpa infrastruktur CI terpisah. | **DIPENUHI.** Konvensi `needs: [unit-tests, quality-data-check, integration-tests]` didokumentasikan sebagai komentar di `test.yml` — job nyata untuk M3.x sendiri sengaja TIDAK dibuat (belum ada yang digerbangi, lihat decisions.md Keputusan #9). |

`pytest tests/ -q` lokal: **172 passed** (170 M2.6 + 2 test `record_history` baru). CI sungguhan (GitHub Actions, run `31671748392`): **3 job hijau** (`unit-tests`, `quality-data-check`, `integration-tests`) — 158 test passed lintas job, 12 skipped (artifact-gated, expected).

## Keputusan Final

Lihat [`decisions.md`](./decisions.md) — 9 keputusan: (1) lanjutkan GitHub Actions, (2-3) dua bug CI lama diperbaiki (Python version, pythonpath), (4) desain split marker integration vs artifact-gated, (5) bug kuirk cache MLflow + fix isolasi proses, (6) Gate 2 otomatis non-recording, (7) Gate 3 reuse test M2.5 existing, (8) provisioning 10+1 secret (1 sempat terlewat), (9) Gate 4 dokumentasi saja. Plus catatan keterbatasan (3 modul test artifact-gated selamanya skip di CI, relevan M2.8).

## Perubahan dari Plan Awal

- **Checkpoint 1 butuh DUA fix, bukan satu** — plan mengantisipasi mismatch Python version; bug `orchestration/` tidak importable (pythonpath) baru ketahuan SETELAH fix pertama berhasil melewati instalasi dependency. Tidak diantisipasi plan, ditemukan+diperbaiki di tempat.
- **KD-1 (libgomp) TERNYATA TIDAK muncul di GitHub Actions** — plan menyiapkan langkah mitigasi (`apt-get install libgomp1`) untuk skenario ini, TIDAK diperlukan (VM penuh GitHub Actions beda dari container minimal Prefect Managed). Langkah mitigasi tetap didokumentasikan di `test.yml`/decisions.md untuk referensi kalau situasi berubah.
- **Bug kuirk MLflow client TIDAK diantisipasi plan sama sekali** — ditemukan murni dari verifikasi lokal sebelum push (2 test error tak terduga saat menjalankan marker split), didiagnosis lewat biseksi + repro minimal, diperbaiki dengan desain isolasi proses (2 langkah pytest terpisah) sebelum sempat mempengaruhi CI sungguhan.
- **1 secret (`MLFLOW_S3_ENDPOINT_URL`) terlewat saat provisioning** — ketahuan dari kegagalan run CI sungguhan pertama setelah secret di-set, bukan dari review manual daftar. Diperbaiki cepat (`gh run rerun --failed`, tanpa commit baru).
- Selebihnya, seluruh 5 checkpoint dan struktur task dieksekusi sesuai urutan yang direncanakan.

## Keterbatasan dan Item Terbuka

- **3 modul test (`test_registry.py`, `test_predictor.py`, `test_pyfunc_model.py`) SELAMANYA skip di CI** — bergantung `artifacs/` (gitignored), tidak akan pernah ada di checkout CI. Bukan bug M2.7 (kondisi sudah ada sejak M1.5). **Relevan untuk Milestone 2.8**: mekanisme sanity-check artifact perlu memikirkan ulang bagaimana artifact tersedia di lingkungan otomatis, bukan mengandalkan file lokal developer.
- **Parity CI penuh vs real-time API SUNGGUHAN belum ada** (KT-7, `docs/keputusan-tertunda.md`) — test M2.5 yang diaktifkan adalah proxy terbaik yang tersedia sekarang, bukan pengganti verifikasi terhadap service M3.x yang benar-benar dideploy.
- **Kuirk cache MLflow client** (Keputusan #5) adalah temuan tentang library `mlflow-skinny`, bukan kode kita — relevan untuk siapa pun menambah test integrasi baru di masa depan yang mencampur tracking URI SQLite sementara dengan registry Postgres real dalam proses yang sama; solusi diterapkan (isolasi proses), tapi pola ini perlu diingat kalau `tests/orchestration/` atau file serupa berkembang.

## Follow-up

- **Milestone 2.8 (Promosi/Rollback)** — WAJIB baca temuan artifact-gated test (di atas) sebelum merancang sanity-check artifact otomatis; WAJIB re-verifikasi mitigasi path MLflow (`.as_posix()`, M2.5 Keputusan #6) setiap registrasi versi baru, konsisten catatan M2.5/M2.6.
- **Milestone 3.x (Real-time API)** — WAJIB baca KT-7 sebelum menganggap parity sudah terverifikasi penuh; ikuti konvensi `needs:` yang didokumentasikan di `test.yml` untuk menambah gerbang deployment sendiri ke pipeline yang sama.
