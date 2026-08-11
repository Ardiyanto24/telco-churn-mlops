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
