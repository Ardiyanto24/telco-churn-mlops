# Log — Milestone 1.2: Modularisasi Preprocessing dan Feature Engineering

**Tanggal kerja:** 2026-08-11

## Mulai kerja

- Draf plan pertama sempat berasumsi tanpa bertanya (ketiadaan artifact asli, konvensi kolom PascalCase, versi dependency dikunci di awal). Dikoreksi user via klarifikasi eksplisit sebelum eksekusi.
- Klarifikasi: user punya `preprocessor.joblib` + `model_final.joblib` asli (tidak punya `splits.joblib`/`best_params_*.json`); user memilih konvensi kolom snake_case (`telco_customers_synthetic`) meski direkomendasikan sebaliknya; user minta dependency dikunci belakangan setelah pipeline teruji; user konfirmasi struktur `src/churn_prediction/` + setuptools.
- User menaruh artifact di `artifacs/model/model_final.joblib` (~25.5 MB) dan `artifacs/proprocessor/preprocessor.joblib` (~4.7 KB) di root repo `deployment-mlops` (penamaan folder apa adanya, bukan `artifacts/`/`preprocessor/`).
- Sempat tidak sengaja mengeksplorasi folder sibling di luar `deployment-mlops` (`../deployment/`, `../data-generator/`) saat mencari file artifact — user menegaskan pengerjaan tidak boleh keluar dari folder ini. Dihentikan, tidak dirujuk lagi.
- Plan direvisi total (strategi verifikasi KK2 dari "reproduksi split+fit via Supabase" jadi "graft parameter dari artifact asli"; urutan checkpoint diubah supaya `decisions.md` ditulis di awal, bukan akhir) dan disetujui user via `ExitPlanMode`.

## Checkpoint 0 — Keputusan + gitignore artifact

- **Task 0a:** `decisions.md` ditulis lengkap (6 keputusan + catatan proses asumsi yang dikoreksi + catatan batas eksplorasi) SEBELUM kode apa pun ditulis, sesuai arahan eksplisit user ("langkah pertama yang seharusnya anda lakukan adalah menuliskan decisions.md").
- **Task 0b:** `artifacs/` ditambahkan ke `.gitignore`. Diverifikasi `git status --short` — `artifacs/` tidak lagi muncul sebagai untracked, hanya `milestones/1.2-modularisasi-preprocessing/` (folder kerja milestone ini) dan `.gitignore` (edit) yang tersisa.
- Commit: `7aa4b99` "feat(milestone-1.2): checkpoint 0 - keputusan teknis + gitignore artifact".

## Checkpoint 1 — Scaffold package & dependency

- **Task 1:** `pyproject.toml` ditulis — `churn_prediction`, backend `setuptools`, dependency terbuka (`scikit-learn>=1.2` batas bawah saja, `pandas`/`numpy`/`joblib` tanpa batas), `dev=["pytest>=8.0"]`.
- **Task 2:** `src/churn_prediction/{__init__.py, transform/{__init__.py, constants.py}}` dibuat. Konstanta di-port dari `tccp-preprocessing-v2.ipynb` cell 5 dengan nama kolom snake_case (Keputusan #1), urutan tiap list dijaga persis sama posisi dengan versi asli (kritis untuk grafting Checkpoint 5). `DROP_COLS` tidak menyertakan `id` (tidak ada di skema `telco_customers_synthetic`).
- Venv baru `.venv/` dibuat khusus repo ini (ditambahkan ke `.gitignore` bersama `__pycache__/`, `*.egg-info/`, `build/`). `pip install -e ".[dev]"` berhasil tanpa error. Verifikasi import dari venv: `from churn_prediction.transform import constants` — `constants.OHE_COLS` dan `constants.DROP_COLS` tercetak sesuai ekspektasi. Bukti KK3 parsial (modul bisa diinstal & diimpor dari luar konteks dev).
- Commit: `8c80c59` "feat(milestone-1.2): checkpoint 1 - scaffold package churn_prediction".

## Checkpoint 2 — Transformer: structural + feature engineering + drop

- **Task 3 (`StructuralEncoder`):** port 1:1 cell 7. 3 unit test (map 4 nilai, kolom tidak diminta diabaikan, seluruh `STRUCTURAL_COLS` dari constants) — 3/3 lulus.
- **Task 4 (`FeatureEngineer`):** port 1:1 cell 8, 6 fitur turunan. 14 unit test termasuk kasus tepi (`total_charges=0` fallback ratio `1.0`; 9 titik batas bin `tenure_group`; seluruh addon `'No internet service'` → `service_count=0`) PLUS baris nyata `id=0` (`notebook-audit.md` H.2) — `tc_residual` dan `monthly_to_total_ratio` dicek `pytest.approx` terhadap perhitungan manual formula, cocok persis. `is_auto_payment` dikonfirmasi `0` untuk `'Mailed check'` dan `1` untuk kedua metode otomatis — 14/14 lulus.
- **Task 5 (`ColumnDropper`):** port 1:1 cell 9. 3 unit test (drop normal, kolom hilang tidak error, default dari constants) — 3/3 lulus.
- Total suite `tests/transform/`: 20/20 lulus (`pytest tests/transform/ -v`).
- Commit: `f55f8fb` "feat(milestone-1.2): checkpoint 2 - StructuralEncoder, FeatureEngineer, ColumnDropper".

## Checkpoint 3 — Transformer: encoding + scaling

- **Task 6 (`BinaryEncoder`):** port 1:1 cell 10. 2 unit test — 2/2 lulus.
- **Task 7 (`OHEWrapper`):** port 1:1 cell 11 (`drop='first'`, `sparse_output=False`, `handle_unknown='ignore'`, `dtype=np.float64`). 3 unit test: nama+jumlah dummy dicek terhadap kombinasi kategori sample (drop_first membuang kategori pertama alfabetis, dikonfirmasi manual sesuai `notebook-audit.md` C.5), kategori tak dikenal saat transform tidak melempar exception (hanya `UserWarning` — perilaku yang diharapkan, dikonfirmasi bukan kegagalan). 3/3 lulus.
- **Task 8 (`ScalerWrapper`):** port 1:1 cell 12. 2 unit test — mean≈0/std≈1 pada kolom target setelah fit_transform, kolom binary tidak tersentuh. 2/2 lulus.
- Total suite `tests/transform/`: 27/27 lulus.
- Commit: `c0c87c6` "feat(milestone-1.2): checkpoint 3 - BinaryEncoder, OHEWrapper, ScalerWrapper".

## Checkpoint 4 — Orkestrasi pipeline + KK1 (statelessness)

- **Task 9 (`PreprocessingPipeline`):** port 1:1 cell 13, orkestrasi 6 step urutan kritis. Test end-to-end dengan DataFrame buatan tangan 4 baris (mencakup seluruh kategori Contract/InternetService/PaymentMethod dan seluruh 4 grup `tenure_group`) — output persis `(4, 29)`, `set(columns)` cocok 100% dengan 29 nama fitur `notebook-audit.md` Bagian C. `transform()` pada baris baru setelah `fit()` juga diverifikasi. 2/2 lulus.
- **Task 10 (KK1 statelessness):** dua uji — (a) `transform()` dipanggil 3x pada input identik → `pd.testing.assert_frame_equal` ketiganya sama persis; (b) `fit_transform` pada dua DataFrame independen berurutan (df_a hanya grup tenure G1/G2, df_b hanya G3/G4) → `scaler_wrapper_._scaler.mean_` berubah total antar fit, dan kategori OHE hasil fit kedua (`ohe_wrapper_._encoder.categories_`) TIDAK mengandung `"Month-to-month"` (kategori yang hanya ada di df_a) — bukti konkret parameter fit ter-overwrite bersih, bukan terakumulasi/gabungan. 2/2 lulus.
- Total suite `tests/transform/`: 31/31 lulus.
- Commit: `f0b8a78` "feat(milestone-1.2): checkpoint 4 - PreprocessingPipeline + bukti KK1".

## Checkpoint 5 — Verifikasi KK2: parity terhadap artifact asli + data real Supabase

- **Task 11 (load `preprocessor.joblib`):** `joblib.load()` langsung GAGAL (`AttributeError: Can't get attribute 'PreprocessingPipeline' on <module '__main__'>`) — sesuai dugaan, class asli didefinisikan di kernel Kaggle. Shim `sys.modules['__main__'].<Class> = <kelas kita>` BERHASIL memuat objek.
  - **Temuan penting #1:** pesan `InconsistentVersionWarning` dari sklearn saat load mengungkap **scikit-learn 1.6.1** adalah versi yang dipakai DS saat fit artifact ini — bukti konkret pertama untuk KT-3 (versi library training), didapat tidak sengaja dari proses debugging, bukan dicari sengaja.
  - **Temuan penting #2 (bug metodologi, ditemukan & diperbaiki saat eksekusi):** shim ke class PRODUKSI kita (`churn_prediction.transform.*`, snake_case) ternyata SALAH — `joblib.load()` hanya memulihkan atribut instance (`__dict__`), BUKAN kode method. Begitu di-unpickle ke class kita, `.transform()` yang jalan adalah KODE KITA (mengecek `'total_charges' in X.columns`), dievaluasi terhadap DataFrame PascalCase asli (`'TotalCharges'`) — kondisi selalu False, fitur seperti `monthly_to_total_ratio`/`is_auto_payment` diam-diam tidak pernah dibuat (tanpa error, tanpa warning). Diperbaiki dengan membuat `tests/transform/_notebook_reference.py` — transkripsi literal PascalCase notebook asli (test-only, bukan bagian `src/`) — dan shim diarahkan ke situ untuk load+ground-truth, bukan ke class produksi.
- **Task 12 (graft + bandingkan):** parameter fitted (`_scaler`, `_encoder`) di-`copy.deepcopy()` dari objek referensi ke instance `PreprocessingPipeline` produksi kita, `feature_names_in_` dihapus dari salinan (sklearn modern validasi nama kolom ketat — grafting ini sengaja posisi-based sesuai Keputusan #4, bukan nama-based). 1500 baris nyata diambil dari `telco_customers_source` (Supabase, `ORDER BY id LIMIT 1500` — otomatis mencakup id=0,1,2). Dijalankan lewat referensi (PascalCase, ground truth) dan modul kita (snake_case, di-graft) — dibandingkan `np.allclose` per salah satu dari 29 fitur via pemetaan eksplisit `OUTPUT_COLUMN_MAP`. **Hasil: seluruh 29 fitur x 1500 baris identik (dalam toleransi floating point).**
- Total suite `tests/`: 32/32 lulus (`pytest tests/ -v`), termasuk test integrasi Supabase.
- Commit: `e8b23bf` "feat(milestone-1.2): checkpoint 5 - verifikasi KK2 terhadap artifact asli".

## Checkpoint 6 — Kunci dependency + Dokumentasi + Penutupan

- **Task 13:** `scikit-learn` dikunci `==1.6.1` PERSIS (bukan tebakan — dikonfirmasi Checkpoint 5) — diinstal ulang menggantikan versi terkini yang kebetulan terpasang (1.9.0), seluruh 32 test dijalankan ulang dan tetap lulus (dan `InconsistentVersionWarning` yang sebelumnya muncul saat load artifact HILANG — bukti tambahan versi sudah cocok). `pandas`, `numpy`, `joblib`, `pytest`, `psycopg2-binary` dikunci ke versi yang terbukti jalan (`pip freeze`) tapi tetap ditandai provisional (KT-3 belum tertutup untuk keempatnya). Diverifikasi ulang di venv BARU (`.venv2`, dihapus setelah verifikasi) — `pip install -e ".[dev]"` + 32/32 test lulus.
- **Task 14:** Review docstring — seluruh 7 class (`StructuralEncoder`, `FeatureEngineer`, `ColumnDropper`, `BinaryEncoder`, `OHEWrapper`, `ScalerWrapper`, `PreprocessingPipeline`) sudah punya docstring lengkap sejak ditulis di checkpoint masing-masing (428-1612 karakter, mencakup input/output/fitur yang diproduksi). `transform/__init__.py` (sebelumnya kosong) diisi docstring modul merangkum kontrak keseluruhan + catatan `DataSplitter` sengaja tidak diport.
- **Task 15:** `report.md` ditulis — KK1-KK3 dipetakan ke bukti test konkret, keterbatasan (KT-1/2/3, ketiadaan `splits.joblib`) dinyatakan eksplisit, follow-up dicatat untuk Milestone 1.3/1.5.
- Commit: `3d99efe` "feat(milestone-1.2): checkpoint 6 (final) - kunci dependency, docstring, report".

## Penutupan Milestone

Milestone 1.2 selesai — 7 checkpoint, 15 task, 6 commit (satu per checkpoint sesuai plan), 32/32 test lulus termasuk verifikasi KK2 terhadap artifact asli DS dan 1500 baris data nyata Supabase. Push tidak dilakukan — menunggu instruksi eksplisit user sesuai `CLAUDE.md`.
