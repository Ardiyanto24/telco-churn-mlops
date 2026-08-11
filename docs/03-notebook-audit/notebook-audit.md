# Audit Notebook — Milestone 1.1 (Productionization)

**Status:** Final — dasar acuan Milestone 1.2 (modularisasi) dan Milestone 1.3 (skema/validasi), serta Milestone 2.2 (desain feature store, Orang #2).

**Ringkasan satu paragraf:** Model churn yang diserahkan Data Scientist adalah `voting_ensemble` (soft-voting terbobot dari LightGBM+class_weight, XGBoost+class_weight, XGBoost+SMOTE dengan bobot `[5,3,1]`), dilatih di atas 29 fitur numerik hasil pipeline preprocessing yang terdokumentasi sangat eksplisit di `tccp-preprocessing-v2.ipynb` (setiap langkah merujuk ke "Insight N" dari dokumen keputusan EDA eksternal). Model menghasilkan **probabilitas** (bukan label langsung) dan production **wajib** menerapkan threshold `0.6238` (bukan 0.5) untuk konversi ke label biner. Temuan paling penting untuk arsitektur sistem: **seluruh 29 fitur final, dan seluruh 21 kolom mentah sumbernya, adalah fitur INSTANT** — tidak ditemukan satu pun fitur yang butuh agregasi lintas baris/waktu/pelanggan lain di manapun dalam 7 notebook ini (lihat Bagian C dan catatan penting di bawah).

---

## Daftar Isi

- [A. Skema Data Mentah](#a-skema-data-mentah)
- [B. Urutan Operasi Preprocessing](#b-urutan-operasi-preprocessing)
- [C. Inventaris Fitur — Klasifikasi Seketika vs Historis](#c-inventaris-fitur--klasifikasi-seketika-vs-historis)
- [D. Kontrak Model (output, threshold, artifact)](#d-kontrak-model-output-threshold-artifact)
- [E. Cross-Check Notebook Sekunder](#e-cross-check-notebook-sekunder)
- [F. Dependency Library](#f-dependency-library)
- [G. Daftar Ambiguitas untuk Data Scientist](#g-daftar-ambiguitas-untuk-data-scientist)

---

## A. Skema Data Mentah

**Sumber:** `tccp-eda.ipynb` (Fase 1, Insight 1-6) dan `tccp-preprocessing-v2.ipynb` (cell 17) — kedua notebook memuat `DATA_PATH` yang identik dan menghasilkan skema yang identik (cross-check Task 2: tidak ada konflik kolom/dtype).

- **Sumber data:** `/kaggle/input/competitions/playground-series-s6e3/train.csv` (Kaggle Playground Series S6E3 — dataset kompetisi, skema menyerupai dataset klasik IBM Telco Customer Churn tapi **bukan** dataset yang sama; lihat Ambiguitas G.1).
- **Shape:** 594.194 baris × 21 kolom.
- **Missing value:** 0 di seluruh kolom (dikonfirmasi dua kali — `df.isnull().sum()` di EDA Insight 3, dan pengecekan whitespace/kosong khusus `TotalCharges` di preprocessing cell 17 → 0 baris kosong).
- **Duplikat:** 0 baris (EDA Insight 4, termasuk & tanpa kolom `id`).
- **Konsistensi nilai kategorikal:** 0 whitespace tersembunyi, 0 nilai di luar skema yang diharapkan (EDA Insight 6, divalidasi terhadap daftar `EXPECTED_VALUES` eksplisit).
- **Target:** `Churn` — nilai mentah `'Yes'`/`'No'`. Distribusi: No=460.377 (77.48%), Yes=133.817 (22.52%). Imbalance ratio 3.44x (kategori "Moderat").
- **Identifier:** `id` — int64, 594.194 nilai unik (1:1 dengan jumlah baris) → primary key kandidat, di-drop sebelum training (tidak prediktif).
- **Tidak ada kolom timestamp/tanggal** di dataset ini — seluruh baris adalah snapshot current-state per pelanggan, bukan log kejadian/transaksi historis.

### Tabel kolom mentah (21 kolom)

| Kolom | dtype | Nilai unik (contoh/lengkap) | Catatan semantik |
|---|---|---|---|
| `id` | int64 | 594.194 unik | Identifier, di-drop |
| `gender` | object | Female, Male | Di-drop di preprocessing (lihat B) |
| `SeniorCitizen` | int64 | 0, 1 | Sudah numerik dari sumber, tidak di-encode ulang |
| `Partner` | object | No, Yes | Binary |
| `Dependents` | object | No, Yes | Binary |
| `tenure` | int64 | 1-72 (bulan) | Numerik kontinu (integer bulan) |
| `PhoneService` | object | No, Yes | Binary |
| `MultipleLines` | object | No, No phone service, Yes | Structural dependency ke `PhoneService` |
| `InternetService` | object | DSL, Fiber optic, No | Nominal 3 kategori → OHE |
| `OnlineSecurity` | object | No, No internet service, Yes | Structural dependency ke `InternetService`, addon |
| `OnlineBackup` | object | No, No internet service, Yes | Structural, addon |
| `DeviceProtection` | object | No, No internet service, Yes | Structural, addon |
| `TechSupport` | object | No, No internet service, Yes | Structural, addon |
| `StreamingTV` | object | No, No internet service, Yes | Structural, addon |
| `StreamingMovies` | object | No, No internet service, Yes | Structural, addon |
| `Contract` | object | Month-to-month, One year, Two year | Nominal 3 kategori → OHE |
| `PaperlessBilling` | object | No, Yes | Binary |
| `PaymentMethod` | object | Bank transfer (automatic), Credit card (automatic), Electronic check, Mailed check | Nominal 4 kategori → OHE |
| `MonthlyCharges` | float64 | 1921 nilai unik | Numerik kontinu, di-scale |
| `TotalCharges` | float64 | 31910 nilai unik | Di-drop setelah dipakai feature engineering (lihat B, C) |
| `Churn` | object | No, Yes | **Target** |

---

## B. Urutan Operasi Preprocessing

**Sumber tunggal:** `tccp-preprocessing-v2.ipynb`. Pipeline ditulis sebagai chain sklearn-compatible (`BaseEstimator`+`TransformerMixin`), diagram alur tertulis eksplisit di cell markdown pertama notebook — urutan logis di bawah ini mengikuti urutan eksekusi nyata (`PreprocessingPipeline._steps`, cell 13), bukan cuma urutan sel.

1. **Load data mentah** — `pd.read_csv(DATA_PATH)` → 594.194×21 (cell 17).
2. **Encode target** — `y_raw = (Churn == 'Yes').astype(int)`; `X_raw` = seluruh kolom kecuali `Churn` (cell 19).
3. **Stratified split** (SEBELUM fit preprocessor — mencegah data leakage) — `DataSplitter`, `test_size=0.15`, lalu `val_size` disesuaikan `0.15/(1-0.15)` dari sisa trainval, `stratify=y`, `random_state=42` (cell 20). Hasil: Train 415.935 (70.0%), Val 89.129 (15.0%), Test 89.130 (15.0%), proporsi churn ~22.5% konsisten di ketiga split.
4. **Fit `PreprocessingPipeline` HANYA pada `X_train_raw`**, lalu `.transform()` dipanggil terpisah untuk val dan test (cell 22-23). Di dalam pipeline, urutan step (`PreprocessingPipeline._steps`, cell 13, ditandai eksplisit "KRITIS — tidak boleh diubah"):
   1. **`FeatureEngineer`** — buat 6 fitur baru SEBELUM `TotalCharges`/`PaymentMethod` di-drop/di-encode (lihat detail formula di Bagian C): `tc_residual`, `monthly_to_total_ratio`, `tenure_group`, `is_auto_payment`, `service_count`, `has_any_addon`.
   2. **`ColumnDropper`** — drop `id`, `gender`, `TotalCharges` (alasan drop: lihat Bagian G — bukan ambiguitas, sudah didokumentasikan sebagai keputusan EDA Insight 1/25/30/45/64).
   3. **`StructuralEncoder`** — map kolom addon (`OnlineSecurity`, `OnlineBackup`, `DeviceProtection`, `TechSupport`, `StreamingTV`, `StreamingMovies`) + `MultipleLines`: `'Yes'→1`, `'No'→0`, `'No internet service'/'No phone service'→-1`. HARUS sebelum `BinaryEncoder` agar `'No'` biasa tidak tertimpa.
   4. **`BinaryEncoder`** — `Partner`, `Dependents`, `PhoneService`, `PaperlessBilling`: `Yes→1`, `No→0`.
   5. **`OHEWrapper`** — One-Hot Encode `Contract`, `InternetService`, `PaymentMethod`, `tenure_group` (kolom terakhir ini hasil dari step 1). `sklearn.OneHotEncoder(drop='first', sparse_output=False, handle_unknown='ignore', dtype=float64)`, **fit hanya pada train**.
   6. **`ScalerWrapper`** — `StandardScaler` (fit hanya pada train) untuk `tenure`, `MonthlyCharges`, `tc_residual`, `monthly_to_total_ratio`. Kolom binary/OHE/discrete sengaja TIDAK di-scale.
5. **Validasi otomatis** (cell 25) — 7 assertion terprogram (kolom drop hilang, fitur baru ada, jumlah dummy `tenure_group`/`Contract` benar, `SeniorCitizen` tetap ada, `tenure` ter-scale mean≈0, `tc_residual` tidak mayoritas nol) — seluruhnya LULUS pada run yang terekam.
6. **Simpan artifact** (cell 29-30): `preprocessor.joblib` (objek `PreprocessingPipeline` hasil fit, lengkap) dan `splits.joblib` (dict berisi `X_train/X_val/X_test` sebagai numpy array, `y_train/y_val/y_test`, `feature_names` — list 29 nama kolom, `imbalance_ratio`, `random_seed`).

Tidak ditemukan sel mati/dieksekusi ulang di luar urutan pada notebook ini — seluruh 33 cell linear dan konsisten dengan diagram alur yang dituliskan penulis di cell pertama.

---

## C. Inventaris Fitur — Klasifikasi Seketika vs Historis

**Total fitur output: 29** (dikonfirmasi 2 kali: `X_train_proc.shape[1]==29` di cell 22, dan breakdown per kelompok di cell 27).

> **Catatan klasifikasi (berlaku untuk seluruh tabel di bawah):** Dataset ini adalah snapshot satu-baris-per-pelanggan — tidak ada kolom timestamp/log kejadian di raw schema (Bagian A), dan setiap notebook (EDA s/d XAI gate) hanya pernah memproses satu baris pada satu waktu tanpa `groupby`/agregasi lintas pelanggan atau lintas waktu. Oleh karena itu **seluruh 21 kolom mentah dan 29 fitur turunan berikut diklasifikasikan INSTANT** — dapat dihitung murni dari satu baris data yang tersedia langsung pada saat itu. Tidak ditemukan satu pun fitur yang secara definisi butuh melihat rekam jejak lebih dari satu baris/periode. Implikasi ini dibahas di Ambiguitas G.3 karena bertentangan dengan asumsi default dokumen arsitektur (kombinasi fitur seketika+historis) — **perlu konfirmasi eksplisit ke pemilik sumber data** apakah field seperti `tenure` di PostgreSQL production benar-benar berupa nilai current-state yang sudah dipelihara sistem lain (instant, tinggal dibaca), atau perlu diturunkan dari log kejadian (historis, butuh agregasi) — lihat G.3.

### C.1 Numerik kontinu (di-scale StandardScaler) — 4 fitur

| Fitur final | Formula / derivasi | Kolom mentah input | Klasifikasi |
|---|---|---|---|
| `tenure` | Tidak diubah (hanya di-scale) | `tenure` | INSTANT |
| `MonthlyCharges` | Tidak diubah (hanya di-scale) | `MonthlyCharges` | INSTANT |
| `tc_residual` | `TotalCharges - (tenure × MonthlyCharges)` — residual non-linear, dihitung SEBELUM `TotalCharges` di-drop | `TotalCharges`, `tenure`, `MonthlyCharges` | INSTANT |
| `monthly_to_total_ratio` | `MonthlyCharges / TotalCharges_safe`, dengan `TotalCharges==0` diganti `NaN` sebelum pembagian lalu hasil `NaN` di-`fillna(1.0)` | `MonthlyCharges`, `TotalCharges` | INSTANT |

### C.2 Binary 0/1 — 7 fitur

| Fitur final | Formula / derivasi | Kolom mentah input | Klasifikasi |
|---|---|---|---|
| `SeniorCitizen` | Tidak diubah (sudah 0/1 dari sumber) | `SeniorCitizen` | INSTANT |
| `Partner` | `Yes→1, No→0` | `Partner` | INSTANT |
| `Dependents` | `Yes→1, No→0` | `Dependents` | INSTANT |
| `PhoneService` | `Yes→1, No→0` | `PhoneService` | INSTANT |
| `PaperlessBilling` | `Yes→1, No→0` | `PaperlessBilling` | INSTANT |
| `is_auto_payment` | `1` jika `PaymentMethod` ∈ `{'Bank transfer (automatic)', 'Credit card (automatic)'}` else `0`, dihitung SEBELUM `PaymentMethod` di-OHE | `PaymentMethod` | INSTANT |
| `has_any_addon` | `1` jika `service_count > 0` else `0` | turunan dari `service_count` (lihat C.3) | INSTANT |

### C.3 Integer diskret — 1 fitur

| Fitur final | Formula / derivasi | Kolom mentah input | Klasifikasi |
|---|---|---|---|
| `service_count` | Hitung berapa dari 6 kolom addon (`OnlineSecurity`, `OnlineBackup`, `DeviceProtection`, `TechSupport`, `StreamingTV`, `StreamingMovies`) bernilai persis `'Yes'` per baris (kondisional — `'No internet service'` TIDAK dihitung, dianggap constraint struktural bukan pilihan `No`) | 6 kolom addon di atas | INSTANT |

### C.4 Structural (-1/0/1) — 7 fitur (dipertahankan, bukan di-OHE)

| Fitur final | Formula / derivasi | Kolom mentah input | Klasifikasi |
|---|---|---|---|
| `OnlineSecurity`, `OnlineBackup`, `DeviceProtection`, `TechSupport`, `StreamingTV`, `StreamingMovies` | `Yes→1, No→0, 'No internet service'→-1` | Kolom itu sendiri | INSTANT |
| `MultipleLines` | `Yes→1, No→0, 'No phone service'→-1` | `MultipleLines` | INSTANT |

### C.5 One-Hot Encoded — 10 fitur

| Fitur final | Kategori asal (baseline yang di-drop) | Kolom mentah input | Klasifikasi |
|---|---|---|---|
| `Contract_One year`, `Contract_Two year` | dari `Contract` (baseline: Month-to-month) | `Contract` | INSTANT |
| `InternetService_Fiber optic`, `InternetService_No` | dari `InternetService` (baseline: DSL) | `InternetService` | INSTANT |
| `PaymentMethod_Credit card (automatic)`, `PaymentMethod_Electronic check`, `PaymentMethod_Mailed check` | dari `PaymentMethod` (baseline: Bank transfer (automatic)) | `PaymentMethod` | INSTANT |
| `tenure_group_G2_2_18`, `tenure_group_G3_18_44`, `tenure_group_G4_44_72` | dari `tenure_group` (baseline: G1_0_2), binning data-driven `pd.cut(tenure, bins=[0,2,18,44,72], labels=['G1_0_2','G2_2_18','G3_18_44','G4_44_72'], include_lowest=True)` | `tenure` (via `tenure_group` turunan) | INSTANT |

**Total: 4+7+1+7+10 = 29 ✓** (cocok dengan `X_train_proc.shape[1]==29` di notebook).

---

## D. Kontrak Model (output, threshold, artifact)

Sumber: `tccp-evaluation.ipynb` (final), `tccp-hyperparameter-tuning.ipynb` (model), `tccp-preprocessing-v2.ipynb` (preprocessor).

- **Tipe output model:** **probabilitas kontinu** — `model.predict_proba(X)[:, 1]` (kelas positif = churn). **Bukan** label langsung, **bukan** multi-kelas (binary strictly, confirmed implisit dari seluruh kode, tidak ada pernyataan eksplisit dari DS — lihat G.7).
- **Model final:** `voting_ensemble` — soft-voting `VotingClassifier` dari 3 model **tuned** (bukan versi baseline): `lightgbm__class_weight`, `xgboost__class_weight`, `xgboost__smote`, dengan bobot `[5, 3, 1]` (hasil Optuna weight-search terpisah, 30 trial). **Catatan:** baseline notebook (`tccp-modeling-baseline-v2.ipynb`) juga menghasilkan objek bernama "voting_ensemble" tapi itu ensemble BERBEDA (XGB+LGBM+**RandomForest**, unweighted/equal-weight) — yang jadi `model_final.joblib` adalah versi dari notebook tuning, bukan baseline. Lihat G.9.
- **Threshold klasifikasi produksi:** **`0.6238`** (F1-optimal dari PR curve, dengan recall floor 0.60 — lihat `ThresholdCalibrator`, `tccp-evaluation.ipynb`). **Bukan** 0.5. `y_pred = (y_prob >= 0.6238).astype(int)`.
- **Metrik performa final** (val set, n=89.129, churn rate 22.52%): PR-AUC 0.7525, ROC-AUC 0.9155, F1 0.7025, Recall 0.7820, Precision 0.6377.
- **Artifact final:**
  - `model_final.joblib` — objek `VotingClassifier` terfit, siap `predict_proba`.
  - `model_final_meta.json` — berisi `best_model` (key), `threshold`, dan seluruh metrik.
  - `preprocessor.joblib` (dari `tccp-preprocessing-v2.ipynb`) — objek `PreprocessingPipeline` custom (chain 6 transformer sklearn-compatible), **bukan** `ColumnTransformer` standar. **Penting untuk Milestone 1.2:** unpickle `joblib.load()` butuh definisi class (`StructuralEncoder`, `FeatureEngineer`, `ColumnDropper`, `BinaryEncoder`, `OHEWrapper`, `ScalerWrapper`, `PreprocessingPipeline`) tersedia di environment yang me-load — modul produksi paling aman **mereplikasi definisi class ini langsung** (source lengkap ada di Bagian B/cell 7-14 `tccp-preprocessing-v2.ipynb`) daripada bergantung pada unpickle artifact lintas environment.

---

## E. Cross-Check Notebook Sekunder

Kelima notebook berikut dikonfirmasi **tidak mengulang logika transformasi** — semuanya memuat `splits.joblib` (data sudah 29 kolom numerik) dan tidak melakukan operasi df-level baru di luar yang sudah didokumentasikan Bagian B-C.

| Notebook | Peran | Konfirmasi |
|---|---|---|
| `tccp-modeling-baseline-v2.ipynb` | Baseline 8 model individual (XGBoost/LightGBM/RandomForest/LogisticRegression × class_weight/SMOTE) + voting ensemble (XGB+LGBM+RF) | Load `splits.joblib` langsung, tidak ada transformasi df baru. SMOTE diterapkan hanya di `X_train` (train-only, val/test tidak disentuh) — teknik resampling untuk training, bukan feature engineering. |
| `tccp-hyperparameter-tuning.ipynb` | Tuning Optuna (100 trial/model, `TPESampler(seed=42)`) untuk LightGBM/XGBoost/LogisticRegression × class_weight/SMOTE, plus weighted voting ensemble (30 trial) | Load `splits.joblib` yang sama. SMOTE per-fold CV (3-fold `StratifiedKFold`), bukan transformasi fitur baru. |
| `tccp-evaluation.ipynb` | Evaluasi final 7 kandidat (6 tuned + voting), pilih terbaik, kalibrasi threshold, export `model_final.joblib` | Load `splits.joblib` + hasil tuning + hasil XAI gate 2 (`passed_models`). Tidak ada transformasi fitur baru. |
| `tccp-xai-gate-1.ipynb` | Gate kualitas SHAP awal (D1-D4: Relevance/Directionality/Magnitude/Consistency) — semua 6 kandidat lulus, semua masuk "Jalur 1" (100 trial tuning) | Load `splits.joblib`. Nama fitur di top-10 SHAP konsisten dengan 29 fitur final. |
| `tccp-xai-gate-2.ipynb` | Gate kualitas SHAP final (D1-D4 didefinisikan ULANG berbeda dari gate 1: SHAP overlap/PI overlap/garbage-feature/direction check) — 7/7 (6 tuned + ensemble) lulus | Load `splits.joblib`. **Nama fitur `MultipleLines` muncul sebagai kolom bare (bukan `MultipleLines_...`)** di top-10 SHAP — cocok 1:1 dengan Bagian C.4, mengonfirmasi `MultipleLines` memang TIDAK di-OHE. |

**Catatan D1-D4 berbeda makna:** `tccp-xai-gate-1.ipynb` dan `tccp-xai-gate-2.ipynb` sama-sama memakai label "D1"-"D4" tapi untuk dimensi pengukuran yang berbeda (Gate 1: Relevance/Directionality/Magnitude/Consistency; Gate 2: SHAP overlap/PI overlap/garbage-check/direction-check). Ini tidak memengaruhi Milestone 1.1-1.6, tapi dicatat di sini agar dokumentasi lanjutan tidak mencampur keduanya.

---

## F. Dependency Library

**Tidak ditemukan satu pun `__version__` print, `pip freeze`, atau `pip show` di ketujuh notebook.** Seluruh instalasi memakai `!pip install <lib> --quiet` tanpa version pin.

| Library | Dipakai di | Versi tercatat di notebook |
|---|---|---|
| pandas, numpy | Semua notebook | Tidak ditemukan |
| scikit-learn (`StandardScaler`, `OneHotEncoder`, `train_test_split`, model linear/ensemble, metrics) | preprocessing, baseline, tuning, evaluation | Tidak ditemukan |
| `missingno` | eda | Tidak ditemukan |
| `imbalanced-learn` (SMOTE) | preprocessing (install saja, tidak dipakai di situ), baseline, tuning | Tidak ditemukan |
| `xgboost` | baseline, tuning, evaluation, xai-gate-2 | Tidak ditemukan |
| `lightgbm` | baseline, tuning, evaluation, xai-gate-2 | Tidak ditemukan |
| `optuna` | tuning | Tidak ditemukan |
| `shap` | xai-gate-1, xai-gate-2 | Tidak ditemukan |
| `wandb` | baseline, tuning, evaluation, xai-gate-1, xai-gate-2 | **0.25.0** (satu-satunya versi yang muncul — dari log sinkronisasi wandb sendiri, bukan print yang disengaja penulis notebook) |
| `joblib` | preprocessing, baseline, tuning, evaluation | Tidak ditemukan |

**Status: GAP — perlu klarifikasi Data Scientist** (lihat G.2). Tidak ada cukup informasi di ketujuh notebook untuk mengunci `requirements.txt`/`pyproject.toml` yang presisi sesuai environment training, sesuai prinsip reproducibility Bagian 6.2 dokumen arsitektur.

---

## G. Daftar Ambiguitas untuk Data Scientist

Setiap item merujuk temuan sumbernya. Tidak diputuskan sepihak di sini — didaftarkan sebagai pertanyaan terbuka sesuai batas implementasi CLAUDE.md.

**G.1 — Identitas sumber data mentah.** Dataset yang dipakai adalah `/kaggle/input/competitions/playground-series-s6e3/train.csv` (Kaggle Playground Series S6E3, 594.194 baris), bukan dataset IBM Telco Customer Churn klasik (~7.043 baris) meski skema kolomnya identik/mirip. *(Sumber: Bagian A, `tccp-eda.ipynb` cell 5, `tccp-preprocessing-v2.ipynb` cell 5.)* **Pertanyaan:** apakah PostgreSQL production nanti benar-benar memiliki skema kolom yang identik dengan dataset kompetisi ini, atau dataset ini hanya proxy pelatihan dan skema production sesungguhnya berbeda? Ini menentukan validitas Milestone 1.6 (kontrak skema sumber data) dan harus dikonfirmasi sebelum Milestone 1.2 dimulai.

**G.2 — Versi library tidak tercatat di manapun.** *(Sumber: Bagian F.)* **Pertanyaan:** environment Kaggle apa (image/tanggal) yang dipakai saat training, atau bisakah DS menyediakan `pip freeze` dari sesi training aslinya? Tanpa ini, Milestone 1.2 (penguncian dependency) harus menebak versi kompatibel dan berisiko training-serving skew jika tebakan salah (prinsip Bagian 2 dokumen arsitektur).

**G.3 — Seluruh fitur terklasifikasi INSTANT — tidak ada fitur historis/agregat ditemukan.** *(Sumber: Bagian C, catatan klasifikasi.)* Dataset training adalah snapshot satu-baris-per-pelanggan tanpa log kejadian. **Pertanyaan kritis untuk Orang #2:** di PostgreSQL production, apakah kolom seperti `tenure` (dan seluruh kolom lain) tersedia sebagai *current-state field* yang sudah dipelihara sistem sumber (sehingga betul-betul instant, tinggal dibaca satu baris), atau perlu diturunkan dari tabel log/transaksi (sehingga jadi historis, butuh feature store)? Jawaban ini menentukan apakah Milestone 2.2 (desain feature store) punya pekerjaan substansial atau nyaris kosong — dampaknya besar terhadap desain Bagian 2 dokumen arsitektur (feature store precomputed) dan **wajib dikonfirmasi sebelum Milestone 1.6/2.2 dimulai**.

**G.4 — `MultipleLines` di `ParentFeatureMapper.OHE_PARENTS` (`tccp-xai-gate-1.ipynb`).** *(Sumber: Bagian E.)* `MultipleLines` didaftarkan sebagai OHE-parent tapi tidak pernah menghasilkan kolom `MultipleLines_...` — dikonfirmasi lewat cross-check Bagian E bahwa ini adalah *no-op* (fungsi `to_parent` hanya match prefix, tidak pernah cocok, fallback ke nama asli). **Bukan bug fungsional**, hanya inkonsistensi dokumentasi di notebook eksplorasi — tidak memblokir Milestone 1.2, dicatat untuk kelengkapan.

**G.5 — Nilai literal hyperparameter hasil tuning tidak tercetak inline.** *(Sumber: `tccp-hyperparameter-tuning.ipynb`, hanya delta PR-AUC yang tercetak, nilai `best_params_<key>.json` tidak terlihat isinya dari notebook.)* **Tidak memblokir** Milestone 1.2/1.5 karena `model_final.joblib` sudah membawa model dengan parameter yang sudah fit — dicatat untuk kelengkapan jika suatu saat perlu retrain/reproduce dari nol.

**G.6 — Baseline artifact naming mismatch di `tccp-evaluation.ipynb`.** *(Sumber: `tccp-evaluation.ipynb` mencari `best_baseline.joblib`/`baseline_<key>.joblib`/`base_model.joblib`, sementara `tccp-modeling-baseline-v2.ipynb` menyimpan sebagai `<model>__<balance>.joblib` — tanpa prefix `baseline_`.) Akibatnya perbandingan delta pre/post-tuning di evaluation notebook silently skipped (`baseline_result = None`).** Tidak memengaruhi jalur produksi (baseline notebook bukan dependency Milestone 1.2+), dicatat untuk kelengkapan/awareness DS saja.

**G.7 — Tidak ada pernyataan eksplisit "model ini binary-only" dari DS.** *(Sumber: Bagian D — disimpulkan implisit dari `predict_proba(...)[:, 1]` di seluruh notebook, tidak pernah dinyatakan sebagai keputusan desain.)* Tidak memblokir kerja (perilaku kode konsisten binary di semua tempat), tapi baik diminta konfirmasi tertulis DS untuk kontrak skema respons Milestone 1.3/3.2.

**G.8 — `imbalanced-learn` di-install di `tccp-preprocessing-v2.ipynb` tapi tidak dipakai di situ.** *(Sumber: `tccp-preprocessing-v2.ipynb` cell 2 install `imbalanced-learn`, tapi SMOTE baru benar-benar dipakai di `tccp-modeling-baseline-v2.ipynb`/`tccp-hyperparameter-tuning.ipynb`.)* Kemungkinan sisa dari template/versi sebelumnya. Tidak berdampak (install idempotent, tidak ada efek samping), dicatat untuk kelengkapan.

**G.9 — Dua objek "voting ensemble" berbeda dengan nama sama di dua notebook.** *(Sumber: Bagian D.)* `tccp-modeling-baseline-v2.ipynb` menghasilkan `voting_ensemble__<balance>.joblib` (XGB+LGBM+**RandomForest**, equal-weight) — berbeda dari `tuned_voting_ensemble.joblib` di `tccp-hyperparameter-tuning.ipynb` (LGBM_cw+XGB_cw+XGB_smote, weighted `[5,3,1]`). **Yang jadi `model_final.joblib` adalah versi tuning**, bukan baseline. Tidak memblokir kerja (sudah jelas mana yang final), dicatat agar tidak tertukar saat Milestone 1.5 (inference service package) merujuk model.
