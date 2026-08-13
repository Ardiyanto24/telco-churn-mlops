# Report — Milestone 3.2: Real-Time Inference API

## Ringkasan

Milestone 3.2 SELESAI — titik integrasi inti pertama jalur real-time (Orang #3). `POST /predict` dibangun di atas image M3.1, memakai `predict_active()` (M2.1/M2.5) dan `ChurnPredictionRequest` (M1.3) apa adanya. Fitur diambil HANYA dari payload request (M2.2: seluruh 29 fitur INSTANT, tidak ada feature store — deviasi terdokumentasi dari teks `mlops-03-deployment-observability.md`/arsitektur Bagian 3.3/5.4 yang belum diperbarui sejak M2.2/2.3, lihat `decisions.md`).

**Temuan terpenting milestone ini bukan soal API itu sendiri, tapi bug korektnes laten di pipeline inferensi** yang baru terungkap saat verifikasi parity: `ChurnPyfuncModel.predict()` sensitif terhadap URUTAN kolom DataFrame (bukan cuma nama) karena preprocessor+model asli DS di-fit tanpa nama fitur — dua DataFrame dengan nama+nilai kolom identik tapi urutan beda menghasilkan prediksi BERBEDA secara diam-diam (delta hingga 0.36, tanpa error apa pun). Root-cause ditemukan, diperbaiki di titik tunggal (`pyfunc_model.py`, melindungi SEMUA pemanggil), dan diverifikasi efektif LANGSUNG terhadap model champion yang sudah teregistrasi tanpa perlu re-registrasi. Lihat `decisions.md` Keputusan #10 dan `logs.md` untuk kronologi lengkap.

## Kriteria Keberhasilan vs Bukti

| KK | Kriteria | Bukti |
|---|---|---|
| **KK1** | "Request valid... prediksi identik dengan hasil batch (M2.5)... verifikasi parity end-to-end pada jalur nyata." | `scripts/api_parity_check.py` terhadap container sungguhan (bukan TestClient), ground truth `predictions.batch_predictions` (M2.5). 20 DAN 100 baris sampel: `churn_probability` allclose(rtol=1e-6) True, diff maksimum ~5×10⁻¹⁶ (floating-point noise), `churn_label` exact match 100%. **Baru lolos setelah fix bug urutan kolom** (percobaan pertama: diff 0.36, FAIL). |
| **KK2** | "Request tidak valid... ditolak dengan error terstruktur yang jelas, bukan diteruskan ke model." | `tests/api/test_app.py`: 5 kasus invalid (rentang, kategori, tipe, field hilang) → 422, dibuktikan `predict_active()` TIDAK PERNAH dipanggil (spy). |
| **KK3** | "Simulasi feature store tidak terjangkau atau model gagal dimuat... error yang bisa dibedakan jelas dari prediksi valid." | Uji coba terkontrol NYATA: container dengan `MLFLOW_TRACKING_URI` sengaja rusak — startup selesai (~100 detik, retry backoff MLflow, app TIDAK crash), `/predict` → `503 {"error":{"code":"model_unavailable",...}}`. |
| **KK4** | "Response API... menyertakan versi model dan waktu prediksi yang benar dan konsisten dengan versi aktif saat itu di registry." | Termasuk dalam bukti KK1 — `model_version` response API cocok 100% dengan versi champion aktif (`resolve_alias_version()`) di seluruh sampel; `predicted_at` ISO8601 valid. |

## Keputusan Final

Lihat [`decisions.md`](./decisions.md) — 9 keputusan desain (seluruhnya forced/derived, tidak ada yang perlu `AskUserQuestion`) + 1 bug ditemukan+diperbaiki (Keputusan #10, root-cause+fix+verifikasi lengkap) + 1 konflik dokumen vs implementasi (feature store, diselesaikan via preseden M2.2).

## Perubahan dari Plan Awal

**Satu penyimpangan signifikan dari plan**: bug korektnes urutan kolom (Keputusan #10) TIDAK diantisipasi di plan — Checkpoint 2 Task 7 (verifikasi KK1) awalnya diperkirakan murni "jalankan container, bandingkan, PASS" tapi percobaan pertama GAGAL dengan diskrepansi besar (bukan floating-point noise). Ini memicu investigasi root-cause di luar scope file yang direncanakan ("Tidak disentuh" plan awal menyebut `pyfunc_model.py` eksplisit) — perbaikan diterapkan LANGSUNG (bukan ditunda/dilaporkan sebagai blocker) karena: (a) bug ini nyata mempengaruhi korektnes prediksi produksi, bukan cuma verifikasi M3.2; (b) fix minimal dan surgical (5 baris inti); (c) diverifikasi regresi nol terhadap seluruh test suite sebelum lanjut. Selain penyimpangan ini, seluruh 3 checkpoint dan 11 task lain dieksekusi sesuai urutan yang direncanakan.

## Keterbatasan dan Item Terbuka

- **Restart diperlukan untuk pick up versi model baru** — model dimuat sekali saat startup (Keputusan #3), demi performa. Promosi/rollback alias `champion` di registry baru diikuti API setelah restart container. Refresh-tanpa-restart adalah scope Milestone 3.4 (dijadwalkan terpisah), BELUM dibangun di sini.
- **Belum ada endpoint `/health`/readiness formal** — wewenang Milestone 3.3 (Keputusan #6). Verifikasi "container siap" versi M3.2 pakai retry TCP-connect biasa.
- **Belum di-deploy ke Kubernetes** — image cuma diverifikasi build+run lokal (`docker run -p`), sesuai cakupan M3.1/M3.2. Push ke container registry dan deployment K8s adalah Milestone 3.3.
- **Startup dengan registry tidak terjangkau lambat (~100 detik)** — bukan bug kode kami, melainkan retry-with-backoff internal `mlflow.store.db.utils` yang tidak dikonfigurasi ulang di sini. Dicatat sebagai karakteristik yang perlu diperhitungkan M3.3 (readiness probe timeout/threshold).
- **Warning dependency mismatch `pyarrow`** saat model loading (`mlflow.utils.requirements_utils`) — non-fatal, model tetap termuat+prediksi valid (pola sama versi mismatch KT-3 M1.5). Tidak diperbaiki di sini, bukan kriteria keberhasilan manapun.
- **Bug urutan kolom (Keputusan #10) hanya diuji untuk KASUS yang ditemukan** (dua urutan spesifik: SQL vs pydantic) — TIDAK ada test eksplisit baru yang memverifikasi properti umum "SEMUA permutasi urutan kolom menghasilkan hasil sama" (mis. lewat `hypothesis`/property-based testing). Fix diyakini benar berdasarkan pemahaman root-cause (reorder eksplisit ke urutan tetap SEBELUM pipeline), bukan diverifikasi exhaustif untuk semua 19! kemungkinan urutan.
- **Tidak ada test regresi permanen untuk bug Keputusan #10** ditambahkan ke `tests/inference/` — verifikasi dilakukan ad-hoc (script debug sesi ini, tidak disimpan sebagai test). Follow-up: pertimbangkan menambah test permanen (`tests/inference/test_pyfunc_model.py`) yang secara eksplisit menguji dua urutan kolom berbeda menghasilkan hasil identik, supaya regresi bug ini terdeteksi otomatis di masa depan.

## Follow-up

- Tambah test permanen untuk bug Keputusan #10 (lihat di atas) — kandidat kuat untuk sesi berikutnya, murah dan mencegah regresi diam-diam.
- M3.3 (Deployment ke Kubernetes): push image ke registry, `/health`/readiness formal, resource sizing awal, perhitungkan latensi startup MLflow retry-backoff untuk timeout probe.
- M3.4 (Deteksi Versi Model Aktif Tanpa Restart Penuh): bangun mekanisme refresh berkala di atas fondasi `app.state.model`/`registry.resolve_alias_version()` yang sudah ada di sini.
- M3.5 (Monitoring): `request_id`/correlation field (Keputusan #8, ditunda bukan ditolak permanen) relevan dievaluasi ulang di sini kalau kebutuhan tracing jadi nyata.
