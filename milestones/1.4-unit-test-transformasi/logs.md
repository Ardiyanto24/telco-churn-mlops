# Log — Milestone 1.4: Unit Test untuk Modul Transformasi

**Tanggal kerja:** 2026-08-11

## Mulai kerja

- Output milestone ini tumpang tindih literal dengan M1.2/M1.3 (102 test sudah lulus). Ditanyakan ke user: petakan+isi-gap, atau audit ulang dari nol? **User pilih audit ulang dari nol.** CI/CD: GitHub Actions.
- Plan disusun dan disetujui via `ExitPlanMode`.

## Checkpoint 0 — Keputusan + scaffold

- **Task 0a:** `decisions.md` ditulis (4 keputusan) sebelum kode, mengikuti pola tervalidasi M1.2/M1.3.
- **Task 0b:** `pytest-cov` ditambahkan ke `dev` — versi aktual terpasang `7.1.0` (bukan `7.0.0` yang awalnya ditulis sebelum instalasi — dikoreksi ke versi sungguhan, bukan ditebak). `pip install -e ".[dev]"` berhasil. `.github/workflows/` dibuat (placeholder `.gitkeep`, diisi Checkpoint 4).
- Verifikasi: `pytest --cov=churn_prediction tests/ -q` — **102 passed**, coverage total **94%** (215 statement, 12 miss). Rincian per file (baseline sebelum audit manual Checkpoint 1):
  - `binary_encoder.py` 94% (1 miss), `column_dropper.py` **80%** (3 miss — paling rendah), `feature_engineer.py` 94% (2 miss), `ohe_wrapper.py` 89% (3 miss), `pipeline.py` 97% (1 miss), `scaler_wrapper.py` 95% (1 miss), `structural_encoder.py` 93% (1 miss).
  - `schema/*.py` dan `transform/constants.py` — 100% masing-masing.

## Checkpoint 1 — Audit cakupan test dari nol

**Metodologi:** Line coverage saja (94%) ternyata TIDAK CUKUP ketat — bisa menyembunyikan cabang `if` yang baris-nya "tereksekusi" (True) tapi cabang False-nya tidak pernah diuji. Dijalankan ulang dengan `--cov-branch`: **91% branch coverage** (50 cabang, 10 partial). Ini yang jadi dasar audit, bukan angka 94% awal.

### Temuan 1 — `get_feature_names_out()` TIDAK PERNAH DIPANGGIL test manapun, di ke-6 class transform + `PreprocessingPipeline.get_feature_names()`

Method publik (bagian kontrak sklearn-compatible, disebut eksplisit di setiap docstring class) — 0% coverage di:
- `column_dropper.py:34-36` (2 branch: `input_features=None` dan normal)
- `binary_encoder.py:38`
- `structural_encoder.py:49`
- `feature_engineer.py:94`
- `ohe_wrapper.py:75`
- `scaler_wrapper.py:48`
- `pipeline.py:96` (`get_feature_names()`, method publik top-level yang disebut di docstring-nya sendiri sebagai cara mengambil nama fitur output)

**Gap nyata** — bukan cuma angka statistik: kalau salah satu method ini rusak (mis. typo, salah return), tidak ada satu pun test yang akan menangkapnya.

### Temuan 2 — `FeatureEngineer`: 6 cabang defensif "kolom sumber hilang" tidak pernah diuji False

`feature_engineer.py` turun ke 82% branch coverage. Baris 60 (`tc_residual` fallback `0.0`) dan 5 partial-branch lain (63->68, 68->77, 77->81, 82->88, 88->91) — semuanya adalah pengecekan `if <kolom> in X.columns` yang SELALU True di seluruh 14 test `test_feature_engineer.py` (karena semua test pakai `_base_row()` yang selalu lengkap). Skenario "kolom sumber benar-benar hilang dari DataFrame" (bukan cuma nilai NaN) — beda dari kasus yang sudah diuji M1.2 — belum pernah dicoba sama sekali.

### Temuan 3 — `OHEWrapper`/`ScalerWrapper`: skenario "tidak ada kolom target di input" tidak pernah diuji

`ohe_wrapper.py` baris 56 (`ohe_feature_names_ = []`) dan 62 (`if not cols_present_: return X`) — kondisi ketika TIDAK SATU PUN dari `contract`/`internet_service`/`payment_method`/`tenure_group` ada di input. `scaler_wrapper.py` 37->39 dan 43->45 — kondisi serupa untuk kolom numerik target. Kedua kelas ini selalu diuji dengan DataFrame yang punya minimal sebagian kolom target — skenario "kolom target sama sekali tidak ada" belum pernah dicoba.

### Temuan 4 — Celah integrasi skema->transform belum pernah diuji (dugaan awal plan, terkonfirmasi)

`tests/schema/` dan `tests/transform/` diuji seluruhnya TERPISAH. Tidak ada satu test pun yang membuktikan: data yang ditolak `RawDataSchema.validate()` benar-benar tidak pernah sampai diproses `PreprocessingPipeline` (atau, kebalikannya: data yang LOLOS `RawDataSchema` pasti bisa diproses `PreprocessingPipeline` tanpa error tak terduga). Ini gerbang praktis yang akan dipakai batch/real-time nanti (M2.5/M3.2) — belum pernah dibuktikan bekerja sebagai satu rangkaian.

### Task list Checkpoint 2 (hasil audit ini)

1. **Task 2** — tambah test `get_feature_names_out()`/`get_feature_names()` untuk ke-7 method (Temuan 1).
2. **Task 3** — tambah test `FeatureEngineer` dengan kolom sumber benar-benar hilang, per 5 fitur turunan (Temuan 2).
3. **Task 4** — tambah test `OHEWrapper` dan `ScalerWrapper` untuk skenario "tidak ada kolom target di input" (Temuan 3).
4. **Task 5** — test integrasi baru `tests/test_schema_transform_integration.py` (Temuan 4).

Tidak ditemukan gap pada `schema/*.py` (branch coverage 100% di ketiganya) — audit Checkpoint 1 M1.3 sudah cukup ketat untuk modul itu.
- Commit: `52cae53` "feat(milestone-1.4): checkpoint 1 - audit coverage dari nol".

## Checkpoint 2 — Isi gap yang ditemukan Checkpoint 1

- **Task 2** — 7 test `get_feature_names_out()`/`get_feature_names()` ditambahkan (satu per class + pipeline), tersebar ke file test masing-masing yang sudah ada.
- **Task 3** — 5 test baru `test_feature_engineer.py`: kolom sumber (`total_charges`, `tenure`, `payment_method`, 6 kolom addon) BENAR-BENAR DIHAPUS dari DataFrame (bukan cuma null) — konfirmasi fitur turunan terkait tidak dibuat (bukan error, bukan fallback keliru).
- **Task 4** — 2 test baru: `OHEWrapper`/`ScalerWrapper` dengan DataFrame yang sama sekali tidak punya kolom target — konfirmasi keduanya no-op bersih (`pd.testing.assert_frame_equal` input==output).
- **Task 5** — `tests/test_schema_transform_integration.py` (baru, 6 test): `RawDataSchema` lalu `PreprocessingPipeline` sebagai satu rangkaian.
  - **Temuan nyata saat menulis test "data valid" (bukan bug, karakteristik sklearn yang benar):** percobaan pertama pakai 1 baris untuk `fit_transform()` → output cuma 19 kolom (bukan 29) karena `OneHotEncoder(drop='first')` pada 1 kategori/kolom menghapus satu-satunya kategori itu, 0 dummy dihasilkan. Percobaan kedua (3 baris, kategori tidak lengkap) → 27 kolom (2 kategori `tenure_group`/`payment_method` tidak pernah muncul). Diperbaiki dengan fixture 4-baris yang mencakup SEMUA kategori (pola sama `test_pipeline.py`) → 29 kolom penuh. Dicatat sebagai komentar di kode test supaya tidak membingungkan orang lain nanti.
  - Penolakan data invalid dibuktikan dengan `unittest.mock.patch.object` + `spy.assert_not_called()` pada `PreprocessingPipeline.fit_transform` — bukan cuma diasumsikan dari urutan baris kode, tapi dibuktikan method itu benar-benar tidak pernah dipanggil (4 kasus pelanggaran berbeda, semua terbukti).
- Full suite: **123/123 lulus** (21 test baru sejak audit Checkpoint 1). Branch coverage: **100%** (naik dari 91%).
- Commit: `19f9105` "feat(milestone-1.4): checkpoint 2 - isi 4 gap hasil audit, 100% branch coverage".

## Checkpoint 3 — Uji coba terkontrol (KK3)

Metodologi (Keputusan #2): tiap eksperimen — edit sengaja `src/` → jalankan test terkait → catat merah → `Edit` balik ke semula persis → jalankan ulang → catat hijau → `git status --short` untuk konfirmasi tidak ada mutasi tertinggal. Tidak ada satu pun eksperimen yang di-commit.

| # | Fungsi | Mutasi | Test yang gagal | Bukti spesifik |
|---|---|---|---|---|
| 1 | `FeatureEngineer.tc_residual` | `-` -> `+` pada formula | `test_tc_residual_and_ratio_real_row_id0` | `Obtained: 3396.75, Expected: -89.05` — assert `pytest.approx` gagal persis di baris formula |
| 2 | `ScalerWrapper.transform` | hasil scaling dikali 2 | `test_scaled_columns_mean_zero_std_one` DAN `test_kk2_parity_against_real_artifact_on_supabase_data` (M1.2) | Parity terhadap artifact asli ikut gagal — 1500/1500 baris beda di 4 kolom numerik. Bukti tambahan: mutasi kecil di satu fungsi terdeteksi lintas 2 milestone test suite sekaligus. |
| 3 | `OHEWrapper` | `drop="first"` -> `drop=None` | 4 test (`test_dummy_column_names_and_count_match_audit`, `test_fit_transform_produces_29_columns_matching_audit`, `test_get_feature_names_after_fit_transform`, `test_transform_after_fit_on_new_data`) | Jumlah kolom output berubah `29 -> 33` — terdeteksi di level pipeline maupun unit OHEWrapper sendiri |
| 4 | `schema.constants.NUMERIC_RANGES["tenure"]["le"]` | `72` -> `200` (longgarkan constraint) | 4 test (`test_tenure_range_matches_check_constraint`, `test_tenure_above_max_rejected` x2 di raw/request schema, `test_invalid_data_rejected_before_reaching_transform`) | Data `tenure=200` yang seharusnya ditolak kini LOLOS validasi — test integrasi M1.4 Task 5 pun ikut gagal (manifest sebagai `TypeError` dari mock internal karena eksekusi lanjut ke `fit_transform` yang tidak seharusnya tercapai — tetap bukti valid bahwa mutasi terdeteksi, dicatat apa adanya bukan disamarkan jadi assertion yang rapi) |
| 5 | `StructuralEncoder.STRUCTURAL_MAP` | `"No internet service": -1` -> `1` | `test_maps_all_four_values` | Nilai `online_security` baris ke-3 berubah `-1 -> 1`, terdeteksi tepat di baris yang relevan |

**Kesimpulan KK3:** seluruh 5 fungsi berisiko tinggi (formula matematis, encoder kategori, validator skema) terbukti punya test yang benar-benar sensitif terhadap regresi — bukan sekadar ada tapi tidak efektif. Verifikasi akhir: `pytest --cov=churn_prediction --cov-branch tests/ -q` setelah revert terakhir — **123/123 lulus, 100% branch coverage**, `git status --short` kosong (tidak ada mutasi yang tertinggal atau ter-commit tidak sengaja).
- Commit: `e1966d7` "feat(milestone-1.4): checkpoint 3 - uji coba terkontrol KK3".

## Checkpoint 4 — GitHub Actions

- **Task 7:** `.github/workflows/test.yml` — trigger `push`+`pull_request`, Python 3.11, `pip install -e ".[dev]"`, `pytest tests/ -v --cov=churn_prediction --cov-branch --cov-report=term-missing`. Komentar eksplisit soal `SUPABASE_DB_URL` (auto-skip tanpa secret, cara mengaktifkan nanti — Keputusan #3).
- Verifikasi: `yaml.safe_load()` (PyYAML diinstal sementara di `.venv`, tidak ditambahkan ke `pyproject.toml` — cuma alat verifikasi lokal, bukan dependency project) — YAML valid, 1 job (`pytest`), 4 step sesuai urutan yang dimaksud.
- **Keterbatasan eksplisit:** workflow ini BELUM diverifikasi jalan sungguhan di GitHub — repo tidak punya remote sama sekali (`git remote -v` kosong). Validasi yang dilakukan cuma sintaksis lokal, bukan eksekusi nyata di infrastruktur GitHub Actions.
- Full suite re-run pasca-checkpoint: 123/123 lulus (tidak terpengaruh, workflow file tidak menyentuh kode).
- Commit: `36376a1` "feat(milestone-1.4): checkpoint 4 - GitHub Actions workflow".

## Checkpoint 5 (final) — Dokumentasi + Penutupan

- **Task 8:** `report.md` ditulis — KK1-KK3 dipetakan ke bukti konkret (audit Checkpoint 1, gap Checkpoint 2, eksperimen Checkpoint 3, workflow Checkpoint 4), keterbatasan (GitHub Actions belum diverifikasi jalan sungguhan, tidak ada remote) dinyatakan eksplisit.

## Penutupan Milestone

Milestone 1.4 selesai — 6 checkpoint, 8 task, 123/123 test lulus (100% branch coverage, naik dari 91% hasil audit awal), 5 bukti uji coba terkontrol, 1 workflow CI/CD. Push tidak dilakukan — menunggu instruksi eksplisit user sesuai `CLAUDE.md`.
