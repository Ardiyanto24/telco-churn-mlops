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
- Commit: `1df0acf` "feat(milestone-1.3): checkpoint 2 - schema/raw_schema.py (pandera)".

## Checkpoint 3 — Skema real-time (Pydantic)

- **Task 3:** `schema/request_schema.py` dibangun terprogram dari `schema/constants.py` via `pydantic.create_model()` — `Literal[tuple(categories)]` untuk field kategorikal, `Field(gt=/ge=/le=)` untuk numerik. Verifikasi cepat: `ChurnPredictionRequest.model_fields` menghasilkan tepat 19 field sesuai `FEATURE_COLUMNS`. 8 unit test paralel dengan `test_raw_schema.py` (kasus valid + 7 pelanggaran yang sama persis) — seluruhnya `pydantic.ValidationError` menyebut field yang salah. 8/8 lulus.
- Commit: `7e9b4d4` "feat(milestone-1.3): checkpoint 3 - schema/request_schema.py (Pydantic)".

## Checkpoint 4 — Verifikasi KK2: konsistensi dua skema + dokumentasi pemetaan

- **Task 4:** `tests/schema/test_schema_consistency.py` — pendekatan "behavioral" (uji apakah kedua skema menerima/menolak nilai yang SAMA secara identik, bukan introspeksi struktur internal pandera/pydantic yang rapuh). 40 test: field set identik, valid row diterima keduanya, tiap kategori valid/tak-valid per 16 kolom kategorikal, tiap batas rentang per 3 kolom numerik.
  - **Temuan real (bukan bug test) saat run pertama:** `total_charges=0` (nilai batas `ge=0`, valid secara semantik) DITOLAK `RawDataSchema` (pandera, dtype `int64` vs deklarasi `float64`, `coerce=False`) tapi DITERIMA `ChurnPredictionRequest` (Pydantic otomatis coerce int->float) — inkonsistensi nyata yang justru dirancang untuk ditangkap Task 4 ini. **Diperbaiki:** `coerce=True` ditambahkan ke Column numerik `raw_schema.py` (kolom kategorikal tetap `coerce=False`). Konsekuensi: `test_wrong_type_rejected` di `test_raw_schema.py` disesuaikan menerima `(SchemaError, SchemaErrors)` — pandera melempar `SchemaErrors` (bukan `SchemaError`) untuk kegagalan coercion tipe, kelas exception terpisah tapi sama-sama penolakan yang sah.
  - Setelah fix: 40/40 lulus, total suite `tests/schema/`: 69/69 lulus.
- **Task 5:** Tabel pemetaan 19 field->kolom->tipe->constraint ditulis eksplisit di docstring `schema/__init__.py` (identity mapping tetap didokumentasikan penuh, bukan dilewatkan karena "kebetulan sama nama").
- Commit: `d6baf8b` "feat(milestone-1.3): checkpoint 4 - verifikasi KK2, konsistensi dua skema".

## Checkpoint 5 — Verifikasi terhadap data real Supabase

- **Task 6:** `tests/schema/test_raw_schema_supabase.py` — pola sama M1.2 Checkpoint 5 (ambil 1500 baris `telco_customers_source`, rename PascalCase->snake_case, skip otomatis kalau `SUPABASE_DB_URL` tidak ada). `RawDataSchema.validate()` — seluruh 1500 baris lolos tanpa error (termasuk `coerce=True` yang diperbaiki di Checkpoint 4, terbukti bekerja pada data nyata, bukan cuma kasus buatan tangan). 1/1 lulus.
- Full suite `tests/` (transform + schema): **102/102 lulus**.
