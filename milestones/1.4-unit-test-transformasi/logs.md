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
