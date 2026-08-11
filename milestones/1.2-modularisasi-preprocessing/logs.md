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
