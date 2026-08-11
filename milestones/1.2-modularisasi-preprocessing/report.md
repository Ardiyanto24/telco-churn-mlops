# Report — Milestone 1.2: Modularisasi Preprocessing dan Feature Engineering

## Ringkasan

Milestone 1.2 selesai. Logika preprocessing/feature engineering dari `tccp-preprocessing-v2.ipynb` (cell 7-13) sudah di-port 1:1 menjadi package Python terinstal (`churn_prediction.transform`, `src/churn_prediction/transform/`), dengan 32 test otomatis (`tests/transform/`) yang seluruhnya lulus — termasuk verifikasi langsung terhadap artifact `preprocessor.joblib` asli Data Scientist dan 1500 baris data nyata dari Supabase. Draf plan pertama milestone ini sempat membuat beberapa asumsi tanpa bertanya ke user (ketiadaan artifact, konvensi kolom, strategi dependency) — dikoreksi sebelum eksekusi dimulai (lihat `decisions.md`).

## Kontrak Sumber vs Bukti (KK1-KK3)

| KK | Kriteria | Bukti |
|---|---|---|
| **KK1** | Fungsi, dipanggil berulang dengan input sama, menghasilkan output identik — tidak ada dependency ke urutan pemanggilan/state sebelumnya. | `tests/transform/test_pipeline.py::test_kk1_repeated_transform_calls_are_identical` (3x `transform()` pada input identik → `pd.testing.assert_frame_equal` semua sama) dan `test_kk1_fit_does_not_accumulate_state_across_calls` (`fit_transform` dua data independen berurutan → `scaler_wrapper_._scaler.mean_` berubah total, kategori OHE fit kedua tidak mengandung kategori yang hanya ada di data pertama — parameter ter-overwrite bersih, bukan terakumulasi). |
| **KK2** | Hasil transformasi modul ini terhadap sampel data SAMA dengan hasil notebook asli — dibandingkan langsung, bukan diasumsikan cocok. | `tests/transform/test_parity_real_artifact.py::test_kk2_parity_against_real_artifact_on_supabase_data` — parameter fitted (`StandardScaler`, `OneHotEncoder`) di-graft dari `artifacs/proprocessor/preprocessor.joblib` ASLI, dijalankan terhadap 1500 baris nyata dari `telco_customers_source` (Supabase, termasuk wajib id=0,1,2), dibandingkan `np.allclose` terhadap ground truth (referensi PascalCase literal notebook) untuk seluruh 29 fitur — **100% identik dalam toleransi floating point**. Ini bukti terkuat yang mungkin didapat mengingat `splits.joblib`/`best_params_*.json` asli tidak tersedia (lihat Keterbatasan). |
| **KK3** | Modul dapat diimpor & dipanggil independen, tanpa perlu menjalankan notebook/bagian sistem lain. | `pip install -e .` dan `pip install -e ".[dev]"` berhasil di 3 venv terpisah sepanjang milestone ini (`.venv` awal, `.venv2` verifikasi final dependency-lock, keduanya bersih tanpa sisa dari sesi lain) — `import churn_prediction.transform...` berhasil tanpa menjalankan notebook apa pun. |

## Keputusan Final

Lihat [`decisions.md`](./decisions.md) — 6 keputusan: (1) konvensi kolom snake_case (dipilih user, bukan rekomendasi saya), (2) dependency dikunci belakangan setelah teruji, (3) `DataSplitter` di luar cakupan modul, (4) strategi grafting parameter untuk KK2, (5) struktur package `src/churn_prediction/`, (6) folder `artifacs/` gitignored. Catatan proses eksplisit tentang asumsi draf pertama yang dikoreksi user turut dicantumkan.

## Perubahan dari Plan Awal

- **Draf plan pertama** (sebelum eksekusi) berasumsi tanpa bertanya: tidak ada artifact asli, konvensi kolom PascalCase, dependency dikunci di awal. Dikoreksi total oleh user via klarifikasi sebelum implementasi — lihat `decisions.md` catatan proses.
- **Strategi verifikasi KK2 direvisi saat eksekusi Checkpoint 5**: rencana awal (reproduksi split+fit dari nol via Supabase) digantikan sepenuhnya oleh grafting parameter dari artifact asli begitu user mengonfirmasi punya `preprocessor.joblib` — bukti yang jauh lebih kuat.
- **Bug metodologi ditemukan & diperbaiki saat eksekusi Task 11**: shim awal mengarahkan unpickle ke class produksi (snake_case) — ternyata SALAH, karena `joblib.load()` hanya memulihkan `__dict__`, bukan kode method, sehingga `.transform()` yang jalan adalah kode kita dievaluasi terhadap kolom PascalCase (kondisi selalu False, fitur seperti `monthly_to_total_ratio` diam-diam tidak pernah terbentuk, TANPA error). Diperbaiki dengan `tests/transform/_notebook_reference.py` — transkripsi literal PascalCase notebook asli, test-only, dipakai sebagai target shim yang benar untuk mendapat ground truth.
- **Temuan sampingan:** proses debugging Task 11 mengungkap `InconsistentVersionWarning` yang menyebutkan eksplisit scikit-learn 1.6.1 sebagai versi training asli DS — menjawab sebagian KT-3 tanpa sengaja dicari.
- **Struktur commit per checkpoint** (7 checkpoint, 1 commit tiap checkpoint) diikuti sesuai plan — beda dari Milestone 1.1 yang sempat menyimpang jadi 1 commit tunggal.

## Keterbatasan dan Item Terbuka

- **KT-1 (konvensi kolom) — TERTUTUP untuk Milestone 1.2**, tapi kesepakatan formal Milestone 1.6 (jalur komunikasi perubahan skema dengan pemilik sumber data) belum dilakukan — modul ini menargetkan snake_case (`telco_customers_synthetic`) atas keputusan eksplisit user, tapi tabel itu sendiri masih 0 baris (generator belum aktif) sehingga verifikasi KK2 memakai `telco_customers_source` (PascalCase) yang di-rename, bukan data snake_case asli.
- **KT-2 (update in-place vs snapshot baru)** — masih terbuka, tidak terpengaruh milestone ini.
- **KT-3 (versi dependency)** — scikit-learn TERJAWAB (`1.6.1`, dikunci persis). pandas/numpy/joblib/pytest/psycopg2-binary MASIH provisional (dikunci ke versi yang terbukti jalan di environment ini, bukan versi training asli DS yang tetap tidak tercatat).
- **`splits.joblib`/`best_params_*.json` tidak tersedia** — verifikasi KK2 memakai grafting parameter (bukti kuat), tapi tidak bisa membandingkan langsung terhadap array `X_train_proc`/`X_val_proc` asli DS byte-per-byte karena artifact itu tidak ada. Grafting terhadap `preprocessor.joblib` + data Supabase byte-identik dinilai bukti setara.
- **`DataSplitter` sengaja tidak diport** — bukan keterbatasan, keputusan sadar (Keputusan #3) karena split adalah kebutuhan training, bukan serving.

## Follow-up

- Sebelum Milestone 1.3 (skema/validasi data input) mengunci kontrak final, pastikan referensi ke konvensi kolom (Keputusan #1 milestone ini) konsisten dipakai.
- Saat Milestone 1.5 (inference service package) memuat `model_final.joblib`, ulangi teknik "baca `InconsistentVersionWarning`/introspeksi pickle" (terbukti berhasil di sini) untuk menjawab versi xgboost/lightgbm — update KT-3 lagi.
- KT-1 (Milestone 1.6 formal), KT-2, dan sisa KT-3 tetap perlu ditutup sebelum sistem production penuh berjalan — lihat `docs/keputusan-tertunda.md`.
