# Report — Milestone 2.8: Validasi Artifact, Promosi, dan Rollback Versi Model

## Ringkasan

Milestone 2.8 memasang dua gerbang validasi (Bagian 5.5 dokumen arsitektur) di depan mekanisme registry/alias yang sudah dibangun Milestone 2.1 — bukan membangun mekanisme dari nol. Alias `challenger` (dicadangkan eksplisit sejak M2.1) dan script CLI `register_production_model.py`/`promote_active_alias.py` (juga sudah ada) langsung dipakai ulang.

Karena tidak boleh training model baru (`CLAUDE.md`), kandidat versi uji dibuat dari model+preprocessor SAMA dengan threshold berbeda (0.5 uji vs 0.6238 produksi) — pola yang sudah dipakai test M1.5, dikonfirmasi user sebagai pendekatan yang dipilih. Seluruh verifikasi (sanity check reject, verifikasi-sebelum-promosi, promosi, rollback) dijalankan SUNGGUHAN terhadap registry dan DAG produksi (bukan mock/simulasi) — registry berakhir di state benar (`champion`=versi 1) sebelum milestone ditutup.

## Kriteria Keberhasilan vs Bukti

| KK | Kriteria | Bukti |
|---|---|---|
| **KK1** | Artifact sengaja dirusak (mis. NaN) ditolak sanity check, tidak sampai jadi kandidat versi terregistrasi. | **DIPENUHI.** `sanity_check_bundle()` dipasang di dalam `register_model()`. Uji coba terkontrol (`test_register_model_rejects_broken_bundle_before_mlflow_called`): bundle model NaN palsu → `ValueError` ter-raise, `mlflow.pyfunc.log_model()` TIDAK PERNAH terpanggil (dibuktikan spy). |
| **KK2** | Simulasi promosi diikuti run DAG berikutnya memakai versi baru, tanpa intervensi manual di luar langkah promosi. | **DIPENUHI, uji coba terkontrol run nyata.** `promote_active_alias.py 2 champion` → `batch_scoring_flow(limit=50)` nyata → `predictions.batch_predictions` (query langsung) menunjukkan `model_version='2'` untuk 50 baris baru — TANPA satu baris kode `batch_scoring.py` diubah. |
| **KK3** | Simulasi rollback mengembalikan DAG ke versi sebelumnya, jauh lebih cepat dari hipotesis redeploy penuh. | **DIPENUHI, uji coba terkontrol run nyata.** `promote_active_alias.py 1 champion` → `batch_scoring_flow(limit=50)` nyata → `model_version='1'` kembali. Kecepatan: hitungan detik (1 perintah CLI + 1 run DAG), bukan hipotesis redeploy image/container. |
| **KK4** | Orang #3 mengonfirmasi mekanisme deteksi versi aktif sisi real-time API bekerja sesuai konvensi sama. | **DI LUAR CAKUPAN M2.8** — teks KK sumber sendiri eksplisit menjadwalkan ini "bersama Milestone terkait di M3.x". Dicatat sebagai follow-up (lihat di bawah), bukan diklaim terpenuhi sekarang. |

`pytest tests/ -q` penuh: **182 passed** (178 setelah Checkpoint 1 + 4 unit test `verify_before_promotion` Checkpoint 2), 0 gagal.

## Keputusan Final

Lihat [`decisions.md`](./decisions.md) — 7 keputusan: (1) sanity check di dalam `register_model()` bukan cuma script pemanggil, (2) input uji sanity check sintetis bukan data production, (3) kandidat uji threshold beda (dikonfirmasi user), (4) kriteria verifikasi-sebelum-promosi pola+tanpa-error provisional (dikonfirmasi user), (5) hasil verifikasi nyata (delta 6.30pp, PASS), (6) uji coba terkontrol dijalankan terhadap registry produksi sungguhan bukan tracking URI terisolasi, (7) KK4 eksplisit di luar cakupan M2.8. Semua dengan "Opsi yang Dipertimbangkan tapi Ditolak".

## Perubahan dari Plan Awal

- **Cakupan kerja jauh lebih kecil dari perkiraan awal plan** — riset sebelum plan menemukan sebagian besar mekanisme (alias `challenger`, script promosi) SUDAH ADA sejak M2.1, tinggal dipasangi gerbang validasi. Plan sendiri sudah mencerminkan temuan ini sebelum implementasi dimulai (bukan penyimpangan di tengah jalan) — dicatat di sini sebagai konfirmasi bahwa estimasi awal (sebelum riset) akan jauh lebih besar dari kenyataan.
- Tidak ada bug/temuan tak terduga selama implementasi (berbeda dari M2.5-2.7 yang masing-masing menemukan beberapa bug nyata) — kemungkinan karena scope-nya murni menambah gerbang DI ATAS mekanisme yang sudah matang dan teruji (M2.1/M2.5), bukan membangun infrastruktur baru dari nol.
- Selebihnya, seluruh 4 checkpoint dan struktur task dieksekusi sesuai urutan yang direncanakan.

## Keterbatasan dan Item Terbuka

- **Ambang provisional 20 poin persentase** (verifikasi-sebelum-promosi) belum dikalibrasi dari riwayat data production yang banyak (`telco_customers_source` masih 1 snapshot statis) — sama pola provisional M2.4, revisit trigger: setelah generator aktif dan ada riwayat run production nyata untuk kalibrasi.
- **Versi 2 (`challenger`, threshold 0.5) tetap ada di registry** sebagai riwayat kandidat uji — TIDAK dihapus (MLflow tidak dirancang untuk hapus versi dengan mudah, dan menyimpannya sebagai bukti verifikasi milestone ini konsisten prinsip "jangan hapus sejarah"). Dicatat jelas statusnya di `model-registry-contract.md` Bagian 7 (BUKAN rekomendasi produksi).
- **KK4 (real-time API) menunggu M3.x** sepenuhnya, sesuai jadwal yang sudah ditetapkan dokumen sumber sendiri.

## Follow-up

- **Milestone 3.x (Real-time API)** — WAJIB mengikuti konvensi alias yang sama persis (`champion`/`challenger`, `load_active_model()`) untuk mendeteksi versi aktif — jangan bangun mekanisme deteksi terpisah. Perlu konfirmasi silang (KK4) begitu real-time API mulai dibangun.
- **Ambang verifikasi-sebelum-promosi (20pp)** perlu dikalibrasi ulang begitu ada riwayat data production nyata (bukan snapshot statis) — dicatat di decisions.md Keputusan #4.
- Ini menuntaskan SELURUH jalur Orang #2 (`mlops-02-pipeline-orchestration.md`, Milestone 2.1-2.8). Pekerjaan berikutnya di proyek ini sepenuhnya berada di jalur Orang #3 (`mlops-03-deployment-observability.md`, M3.x), yang belum dimulai.
