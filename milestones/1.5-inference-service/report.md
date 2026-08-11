# Report — Milestone 1.5: Inference Service Package

## Ringkasan

Milestone 1.5 selesai. `churn_prediction.inference` membungkus transform (M1.2) + model + threshold sebagai satu paket dengan API publik tunggal `predict(df, model_version) -> DataFrame`, dimuat dari MLflow Model Registry berdasarkan versi (bukan path file statis). Lima keputusan desain genuinely-terbuka diklarifikasi ke user sebelum plan ditulis (MLflow lokal vs server, registrasi resmi vs uji, kontrak output/input, bundling pyfunc) — lihat `decisions.md`. Selama eksekusi ditemukan 4 gap teknis konkret (bukan diasumsikan mulus): `mlflow` penuh bentrok `pandas==3.0.5`, backend filesystem MLflow deprecated, `model_final.joblib` butuh `lightgbm`/`xgboost` yang belum pernah terinstal, dan `mlflow-skinny` diam-diam butuh `sqlalchemy`/`alembic` untuk backend SQLite — seluruhnya diselesaikan dan diverifikasi ulang, bukan ditambal lalu diasumsikan beres. Total akhir: **136 test lulus**, KK2 diverifikasi pada 1000 baris data real Supabase, KK1 diverifikasi dari DUA venv terpisah (satu di antaranya menemukan gap `sqlalchemy`/`alembic`).

## Kontrak Sumber vs Bukti (KK1-KK3)

| KK | Kriteria | Bukti |
|---|---|---|
| **KK1** | Package dapat diinstal & dipanggil dari luar konteks pengembangan (venv terpisah) tanpa mengubah kode internal. | Checkpoint 5 — venv terpisah pertama menemukan gap nyata (`sqlalchemy`/`alembic` hilang dari dependency `mlflow-skinny`, `UnsupportedModelRegistryStoreURIException`); diperbaiki di `pyproject.toml`, lalu diverifikasi ULANG dari venv KEDUA yang benar-benar bersih (`pip install <repo>` saja, tanpa instalasi manual tambahan) — `predict()` berhasil pada 2 baris fixture tanpa satu baris `src/` pun diubah. Venv keduanya dihapus setelah verifikasi (tidak permanen, sesuai plan). |
| **KK2** | Pemanggilan dengan data uji identik menghasilkan output identik dengan hasil notebook asli (verifikasi end-to-end). | `tests/inference/test_e2e_parity.py` — ground truth `preprocessor.joblib`+`model_final.joblib` asli dimuat LANGSUNG (tanpa bundle/MLflow), dibandingkan terhadap `predict()` publik (lewat bundle+MLflow) pada 1000 baris real `telco_customers_source` (Supabase), termasuk baris id=0,1,2 wajib. `churn_probability` `np.allclose` (rtol 1e-6) dan `churn_label` identik 100% baris. |
| **KK3** | Mekanisme pemuatan model dari MLflow registry berdasarkan versi diuji dengan >1 versi, hasil sesuai versi yang diminta. | `tests/inference/test_registry.py::test_load_by_version_returns_version_appropriate_results` — versi 1 (bundle sungguhan, threshold 0.6238) vs versi 2 uji (model SAMA, threshold 0.5) diregistrasi ke store yang sama, dimuat terpisah lewat `load_model_by_version("1")`/`("2")` pada baris id=2 (probability ~0.566, sengaja di antara kedua threshold): probability identik, `churn_label` BERBEDA (0 vs 1) — bukti mekanisme genuinely version-aware. |
| *(tambahan)* | Dokumentasi cara pakai Orang #2/#3. | `src/churn_prediction/inference/__init__.py` — docstring modul: instalasi, kontrak input-output (tabel 4 kolom output), contoh pemanggilan, batas eksplisit "MLflow di sini lokal/uji M1.5, registrasi resmi tetap M2.1". |

## Keputusan Final

Lihat [`decisions.md`](./decisions.md) — 10 keputusan total: 6 dari klarifikasi awal (5 pertanyaan dijawab user sebelum plan ditulis: MLflow lokal file-based, registrasi ditunda M2.1, output label+probability+lineage, input DataFrame saja, bundle pyfunc tunggal, sentralisasi artifact loading) + 4 keputusan turunan yang dipaksa temuan teknis konkret selama eksekusi (backend SQLite bukan filesystem, `mlflow-skinny` bukan `mlflow` penuh, tambah `lightgbm`/`xgboost`, tambah `sqlalchemy`/`alembic`).

## Perubahan dari Plan Awal

- **4 keputusan turunan tak terduga** (Keputusan #7-#10) — plan awal hanya mengantisipasi 6 keputusan dari klarifikasi. Semuanya lahir dari kegagalan konkret saat eksekusi (bukan diantisipasi di muka), didokumentasikan lengkap dengan bukti (pesan error, hasil smoke test) di `decisions.md`/`logs.md` — bukan ditambal diam-diam.
- **Checkpoint 5 dikerjakan dalam urutan terbalik dari plan** (KK2 lebih dulu, baru KK1) — tidak mengubah hasil, cuma urutan eksekusi praktis.
- **KK1 diverifikasi DUA KALI** (bukan sekali seperti dibayangkan plan) — percobaan pertama gagal dan gagalnya sendiri jadi bukti berharga (menemukan gap `sqlalchemy`/`alembic`), verifikasi kedua (setelah perbaikan) yang jadi bukti final KK1 lulus.
- Tidak ada revisi cakupan besar seperti M1.2 — seluruh 5 pertanyaan klarifikasi dijawab lebih dulu sebelum plan ditulis, konsisten pola M1.3/M1.4.

## Keterbatasan dan Item Terbuka

- **MLflow di sini LOKAL/uji milik M1.5 (`sqlite:///mlruns.db`), BUKAN registry resmi produksi.** Registrasi versi 1 dalam test suite ini bersifat pembuktian mekanisme, bukan "versi awal produksi" — itu tetap tanggung jawab eksplisit Milestone 2.1 (`mlops-02-pipeline-orchestration.md`), yang akan menyediakan server MLflow sungguhan dan konvensi versi aktif. Konsumen (Orang #2/#3) cukup mengarahkan `MLFLOW_TRACKING_URI` ke server itu nanti — kontrak `predict()` tidak berubah.
- **Versi `lightgbm`/`xgboost` training asli DS masih belum terkonfirmasi** (KT-3, `docs/keputusan-tertunda.md` — TIDAK ditutup untuk keduanya). Warning versi lama muncul saat load `model_final.joblib` tapi `predict_proba()` tetap menghasilkan output valid — diterima sebagai provisional, bukan diverifikasi cocok persis dengan environment training.
- **KK3 hanya mencakup 1 pasang versi uji** (bukan variasi model/threshold yang lebih luas) — cukup untuk membuktikan mekanisme load-by-version bekerja sesuai definisi KK, tidak dimaksudkan sebagai uji beban/skala.
- **`telco_customers_synthetic` masih 0 baris** — verifikasi KK2 memakai `telco_customers_source` sebagai proxy data real (pola sama M1.2/M1.3), bukan tabel target produksi sesungguhnya.
- Push ke GitHub belum dilakukan (ditanyakan eksplisit ke user, konsisten `CLAUDE.md`).

## Follow-up

- Milestone 2.1 (Orang #2) akan menyiapkan MLflow registry RESMI dan meregistrasi `model_final.joblib` sebagai versi produksi awal — bisa memakai ulang `registry.build_bundle()`/`register_model()` dari milestone ini (fungsinya sudah generik, tidak hardcode ke tracking URI lokal).
- Saat DS mengonfirmasi versi `lightgbm`/`xgboost`/`pandas`/`numpy` training asli (KT-3), bandingkan terhadap versi provisional yang dikunci di sini.
- Milestone 1.6 (kontrak skema sumber data) dan sisa KT-1/KT-2 tidak terpengaruh milestone ini.
