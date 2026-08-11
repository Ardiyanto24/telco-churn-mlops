# Log — Milestone 1.3: Skema dan Validasi Data Input

**Tanggal kerja:** 2026-08-11

## Mulai kerja

- Sebelum breakdown ditulis, 4 pertanyaan genuinely-terbuka diajukan ke user (target skema batch, library validasi batch, library validasi real-time, konvensi field) — dijawab: tetap `telco_customers_synthetic`, pandera, Pydantic, snake_case identik kolom.
- Plan disusun dan disetujui user via `ExitPlanMode`.

## Checkpoint 0 — Keputusan + scaffold dependency

- **Task 0a:** `decisions.md` ditulis lengkap (4 keputusan + ringkasan klarifikasi) SEBELUM kode apa pun, mengikuti pola tervalidasi Milestone 1.2.
- **Task 0b:** `pandera`/`pydantic` ditambahkan ke `dependencies` inti `pyproject.toml`. `pip install -e ".[dev]"` berhasil — versi terpasang `pandera==0.32.1`, `pydantic==2.13.4`, langsung dipin persis (Keputusan #3, bukan provisional). `src/churn_prediction/schema/__init__.py` dibuat (scaffold kosong). Verifikasi: `import pandera, pydantic, churn_prediction.schema` berhasil.
- Commit: `a5a861d` "feat(milestone-1.3): checkpoint 0 - keputusan teknis + scaffold dependency".

## Checkpoint 1 — Constraint tunggal per kolom

- **Task 1:** `schema/constants.py` ditulis — `CATEGORICAL_COLUMNS` (16 kolom teks/int diskret) dan `NUMERIC_RANGES` (3 kolom numerik: tenure, monthly_charges, total_charges), total `FEATURE_COLUMNS` = 19. `BINARY_COLS`/`ADDON_COLS` di-reuse langsung dari `churn_prediction.transform.constants` (bukan ditulis ulang, sesuai Keputusan #2). 13 unit test membandingkan tiap daftar kategori/rentang satu-satu terhadap `notebook-audit.md` Bagian A (nilai unik EDA) dan Bagian H.3 (CHECK constraint) — 13/13 lulus.
- Commit: `2812bc9` "feat(milestone-1.3): checkpoint 1 - schema/constants.py, sumber tunggal constraint".

## Checkpoint 2 — Skema batch (pandera)

- **Task 2:** `schema/raw_schema.py` dibangun terprogram dari `schema/constants.py` (`pandera.DataFrameSchema`, `strict=False`). 8 unit test: 1 valid + 7 kasus pelanggaran (kolom hilang, tipe salah, `tenure` di atas 72, `tenure=0`, `monthly_charges` negatif, `senior_citizen=2`, kategori `contract="Weekly"` tak dikenal) — seluruhnya `pandera.errors.SchemaError` dengan nama kolom tersebut di pesan (`pytest.raises(..., match=...)`). 8/8 lulus.
- Perbaikan kecil: `import pandera as pa` diganti `import pandera.pandas as pa` (FutureWarning pandera — API top-level akan dihapus, direkomendasikan submodul `.pandas` untuk validasi DataFrame). Tidak ada warning tersisa.
