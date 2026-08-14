# Decisions — Milestone 3.2: Real-Time Inference API

## Konteks

Milestone titik integrasi inti pertama jalur real-time (Orang #3) — membangun `POST /predict` di atas image M3.1, memakai `churn_prediction.inference.predictor.predict_active()` (M2.1/M2.5) dan skema request `ChurnPredictionRequest` (M1.3) apa adanya.

Tidak ada keputusan yang memerlukan `AskUserQuestion` untuk milestone ini — seluruh keputusan di bawah forced/derived oleh precedent mengikat (M1.3, M2.2, M2.5, jadwal M3.3/M3.4) atau delegasi eksplisit wewenang dari dokumen arsitektur sendiri.

## KONFLIK DOKUMEN vs IMPLEMENTASI — Feature Store

`docs/02-implementation-plan/mlops-03-deployment-observability.md` Milestone 3.2 dan `docs/01-architecture/rancangan-arsitektur-mlops-platform.md` Bagian 3.3/5.4 (BELUM diperbarui sejak M2.2/2.3) masih menyebut API ini harus "mengambil fitur historis dari feature store di PostgreSQL". **Milestone 2.2 (SELESAI) sudah memutuskan final**: "Milestone 2.2 TIDAK menghasilkan skema tabel feature store apa pun... seluruh 29 fitur final berklasifikasi INSTANT" (`milestones/2.2-klasifikasi-fitur-feature-store/decisions.md`) — dikonfirmasi ulang sesi ini: tidak ada tabel `feature_store` di `infra/sql/` maupun database manapun, dan M2.3 (job refresh feature store) ditutup N/A sebagai konsekuensi langsung.

Ini preseden MENGIKAT — API M3.2 mengambil SELURUH fitur dari payload request SAJA, tidak ada langkah "ambil fitur dari feature store" sama sekali. Dicatat di sini sebagai deviasi terdokumentasi dari teks sumber, bukan diam-diam diabaikan.

## Keputusan Teknis

### 1. Framework: FastAPI + Uvicorn

**Keputusan:** `fastapi==0.141.1`, `uvicorn==0.52.3` dipin eksplisit sebagai dependency inti `pyproject.toml`.

**Kenapa:** Keduanya SUDAH wajib terpasang lewat `mlflow-skinny`/`prefect` (dependency inti tanpa marker `extra`) — dikonfirmasi via `pip show fastapi` (`Required-by: mlflow-skinny, prefect`). Memilih framework lain menambah dependency baru sepenuhnya redundan. FastAPI juga otomatis menghasilkan dokumentasi OpenAPI (`/docs`) dari `ChurnPredictionRequest` yang sudah ada.

**Opsi yang Dipertimbangkan tapi Ditolak:** Flask/lainnya — DITOLAK: redundan dengan yang sudah wajib ada di image, tanpa manfaat dokumentasi otomatis.

### 2. Fitur HANYA dari payload request — TIDAK ada langkah "ambil dari feature store"

**Keputusan:** Handler `/predict` mengonversi `ChurnPredictionRequest` langsung ke DataFrame satu baris, tanpa query tambahan.

**Kenapa:** Forced oleh preseden M2.2 (lihat "KONFLIK DOKUMEN vs IMPLEMENTASI" di atas).

**Opsi yang Dipertimbangkan tapi Ditolak:** Membangun feature store sekarang supaya cocok literal dengan teks dokumen sumber — DITOLAK: membuka ulang keputusan M2.2 yang sudah final dengan bukti kuat (cross-check 0 gap `raw-schema-contract.md`) tanpa temuan baru yang membenarkannya.

### 3. Model dimuat SEKALI saat startup (cached), `predict_active()` diperluas parameter opsional

**Keputusan:** FastAPI `lifespan` memuat model via `registry.load_active_model()`+`resolve_alias_version()` SEKALI saat proses start, simpan di `app.state`. `predictor.py::predict_active()` diperluas parameter opsional `model=None, resolved_version=None` — kalau diberikan, skip pemanggilan registry internal. Backward compatible: `predict_active(df)` (M2.5 batch) tidak berubah perilaku.

**Kenapa:** (a) performa — reload artifact dari S3 Supabase Storage di SETIAP request akan membuat API "real-time" lambat tidak wajar; (b) forced jadwal milestone — M3.4 ("Deteksi Versi Model Aktif Tanpa Restart Penuh") eksplisit dijadwalkan TERPISAH, jadi restart untuk pick up versi baru adalah keterbatasan SAH M3.2.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- Panggil `predict_active(df)` apa adanya (reload tiap request) — DITOLAK: latensi tinggi tak wajar untuk API real-time.
- Fungsi baru terpisah di `api/` yang menduplikasi validate→predict→attach-lineage — DITOLAK: memecah satu sumber kebenaran orkestrasi request→response; parameter opsional backward-compatible (pola sama M2.9 `batch_scoring_flow`) sudah cukup.

**Verifikasi:** `pytest tests/ -q` penuh 192/192 lulus setelah perubahan — regresi nol terhadap M1.5/M2.5/M2.7/M2.8/M2.9 (lihat `logs.md` Checkpoint 1).

### 4. Endpoint tunggal `POST /predict`, satu entity per request

**Keputusan:** Satu route, menerima SATU `ChurnPredictionRequest` per panggilan.

**Kenapa:** Cocok semantik "real-time" (satu pelanggan dievaluasi live). Scoring banyak baris sekaligus sudah wewenang jalur batch (M2.5).

**Opsi yang Dipertimbangkan tapi Ditolak:** endpoint menerima list/array — DITOLAK: di luar cakupan KK manapun M3.2.

### 5. Startup gagal memuat model → app TETAP hidup, `/predict` balas 503 terstruktur

**Keputusan:** Kegagalan `load_active_model()`/`resolve_alias_version()` saat startup ditangkap — `app.state.model=None`, `app.state.load_error=<pesan>`. `/predict` mengecek `state.model is None` → 503 JSON terstruktur.

**Kenapa:** Forced oleh KK3 (error harus bisa dibedakan dari prediksi valid, bukan proses mati). Konsisten pola readiness Kubernetes M3.3 (proses tetap hidup untuk diprobe).

**Opsi yang Dipertimbangkan tapi Ditolak:** biarkan exception mematikan proses (crash-loop) — DITOLAK: caller cuma dapat "connection refused", tidak informatif.

**Verifikasi NYATA (bukan cuma mock):** container dijalankan dengan `MLFLOW_TRACKING_URI` sengaja rusak (host tidak ada) — startup selesai (~100 detik, retry backoff internal MLflow — lihat `logs.md`), app tetap hidup, `/predict` membalas `503 {"error":{"code":"model_unavailable",...}}`.

### 6. TIDAK membangun endpoint `/health`/readiness formal di M3.2

**Keputusan:** Berhenti di `/predict` + startup-load-check internal.

**Kenapa:** "Health check (readiness dan liveness) yang mencerminkan kesiapan model" adalah Output EKSPLISIT Milestone 3.3.

**Opsi yang Dipertimbangkan tapi Ditolak:** tambah `/health` sekarang — DITOLAK: menebak bentuk yang akan digali eksplisit M3.3.

### 7. Kontrak error: 422 native FastAPI/Pydantic, JSON envelope custom untuk 503/500

**Keputusan:** Request tidak valid → 422 bawaan FastAPI (`{"detail": [...]}`). Kegagalan model/internal → envelope `{"error": {"code": "model_unavailable"|"internal_error", "message": "..."}}`, 503/500.

**Kenapa:** Bagian 8.1/10 dokumen arsitektur eksplisit menyerahkan detail ini ke Orang #3.

**Opsi yang Dipertimbangkan tapi Ditolak:** satu bentuk error custom untuk semua kegagalan (termasuk override 422) — DITOLAK: menduplikasi kerja FastAPI yang sudah benar.

### 8. TIDAK menambahkan field ID/correlation ke `ChurnPredictionRequest`

**Keputusan:** Request body tetap 19 field asli, tanpa `request_id`/field korelasi.

**Kenapa:** M1.3 menyerahkan keputusan ini ke M3.2, tapi tidak ada KK M3.2 yang mensyaratkannya. Observability/tracing adalah scope M3.5. Menambah field nanti tidak breaking.

**Opsi yang Dipertimbangkan tapi Ditolak:** tambah `request_id: Optional[str]` sekarang untuk jaga-jaga — DITOLAK: spekulatif, tidak ada KK yang membutuhkan.

### 9. Verifikasi KK1 memakai baris `predictions.batch_predictions` EXISTING sebagai ground truth

**Keputusan:** `scripts/api_parity_check.py` membaca sampel `predictions.batch_predictions` (M2.5, `source_table='telco_customers_source'`, `model_version` = versi champion AKTIF saat ini), fetch fitur mentah baris yang sama, kirim ke API, bandingkan.

**Kenapa:** Ground truth sudah ada, deterministik untuk versi model yang sama.

**Opsi yang Dipertimbangkan tapi Ditolak:** re-run batch baru — DITOLAK: kerja berlebih tanpa manfaat tambahan.

**Catatan implementasi:** filter eksplisit `model_version = <versi aktif>` diperlukan karena `predictions.batch_predictions` berisi baris dari berbagai run/versi (termasuk sisa uji rollback M2.8) — tanpa filter ini, perbandingan bisa salah simpul (baris lama vs versi aktif sekarang secara SAH beda angka).

### 10. Bug ditemukan+diperbaiki: `ChurnPyfuncModel.predict()` sensitif urutan kolom (silent wrong prediction)

**Ditemukan saat:** Checkpoint 2, verifikasi KK1 pertama kali GAGAL (`churn_probability` diff maksimum 0.36 — bukan floating-point noise) padahal `predict_active()` dipanggil langsung (bukan lewat API) dengan data yang SAMA memberi hasil BENAR.

**Root cause (dibuktikan, bukan diasumsikan):** `preprocessor.joblib`/`model_final.joblib` asli DS di-fit TANPA nama fitur (numpy array polos — dikonfirmasi `UserWarning` sklearn "fitted without feature names" yang muncul konsisten sejak M1.5). `PreprocessingPipeline.transform()` (M1.2) melestarikan urutan kolom INPUT ke urutan kolom OUTPUT — tiap step transformasi benar secara NILAI per-nama kolom, tapi urutan akhir 29 kolom `transformed` bergantung urutan 19 kolom `model_input`. `VotingClassifier` (LightGBM+XGBoost) lalu membaca `transformed` secara POSISIONAL saat `predict_proba()`, bukan berdasar nama kolom pandas — dibuktikan lewat perbandingan langsung: `pipeline.transform(df_urutan_SQL)` vs `pipeline.transform(df_urutan_pydantic)` menghasilkan NILAI identik per-nama-kolom tapi URUTAN KOLOM OUTPUT berbeda.

Dipicu Milestone 3.2 karena `ChurnPredictionRequest.model_dump()` (dibangun dari `constants.py`: `CATEGORICAL_COLUMNS` lalu `NUMERIC_RANGES`, jadi `tenure`/`monthly_charges`/`total_charges` di AKHIR) menghasilkan urutan kolom BERBEDA dari query SQL batch (`RAW_PASCAL_TO_SNAKE.keys()`, `tenure` di TENGAH, mengikuti urutan dataset asli) — dua urutan yang SAMA-SAMA "benar" secara nama/nilai kolom, tapi cuma satu yang kebetulan cocok urutan fit asli.

**Dampak:** Ini BUKAN bug spesifik M3.2 — laten sejak M1.2/M1.5, mempengaruhi SIAPA PUN yang memanggil `predict()`/`predict_active()` dengan DataFrame yang nama kolomnya benar tapi urutannya beda dari urutan dataset asli. Jalur batch (M2.5) tidak pernah terdampak murni karena SELALU kebetulan memakai urutan SQL/`RAW_PASCAL_TO_SNAKE` yang benar — bukan karena ada proteksi eksplisit.

**Fix:** `ChurnPyfuncModel.predict()` (`src/churn_prediction/inference/pyfunc_model.py`) me-reorder `model_input` ke urutan kanonik (`RAW_PASCAL_TO_SNAKE.values()`, sama seperti kolom `telco_customers_synthetic`) SEBELUM masuk `self._pipeline.transform()`. Titik perbaikan TUNGGAL yang melindungi SEMUA pemanggil (batch, real-time API, konsumen masa depan) — bukan ditambal di tiap caller (konsisten prinsip satu sumber kebenaran).

**Verifikasi:**
- Fix efektif LANGSUNG terhadap model `champion` versi 1 yang SUDAH teregistrasi, TANPA re-registrasi — MLflow me-load ulang class `ChurnPyfuncModel` dari package `churn_prediction` yang terinstal saat model dimuat (`load_context()` membangun ulang state dari `context.artifacts["bundle"]`, bukan membekukan method code saat registrasi), dibuktikan lewat pemanggilan `predict_active()` langsung terhadap registry produksi.
- `pytest tests/ -q` penuh: 192/192 tetap lulus (regresi nol — fix murni protektif, seluruh pemanggil existing kebetulan sudah pakai urutan kanonik).
- `scripts/api_parity_check.py` terhadap container sungguhan: 20 baris DAN 100 baris sampel, seluruhnya match (diff maksimum ~5×10⁻¹⁶, level floating-point noise) — lihat `logs.md`.
- **Test regresi permanen ditambahkan** (follow-up, sesi sama): `tests/inference/test_pyfunc_model.py::test_predict_invariant_to_input_column_order` (urutan `reversed()`) dan `::test_predict_matches_regardless_of_request_schema_field_order` (urutan PERSIS `ChurnPredictionRequest.model_dump()` yang memicu bug asli). Bukti negatif eksplisit: baris reorder dinonaktifkan sementara → kedua test GAGAL → dikembalikan → `pytest tests/ -q` penuh 194/194 lulus.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- Reorder di level caller (`api/app.py`, sebelum memanggil `predict_active()`) — DITOLAK: hanya melindungi jalur M3.2, tidak melindungi konsumen lain (mis. kalau kelak ada consumer ketiga yang memanggil `predict()`/`predict_active()` langsung dengan urutan berbeda) — perbaikan di `ChurnPyfuncModel.predict()` melindungi SEMUA jalur sekaligus karena semua panggilan model akhirnya lewat titik ini.
- Reorder di `RawDataSchema.validate()` (pandera) — DIPERTIMBANGKAN tapi DITOLAK: pandera adalah lapisan VALIDASI (memvalidasi kehadiran/tipe/rentang), bukan tempat semestinya logika "urutan kanonik untuk model" hidup — mencampur tanggung jawab; `ChurnPyfuncModel.predict()` (titik masuk MODEL) adalah lokasi yang lebih tepat secara konseptual DAN melindungi konsumen yang mungkin memanggil `mlflow.pyfunc.load_model()` langsung tanpa lewat `predict()`/`predict_active()` sama sekali.
