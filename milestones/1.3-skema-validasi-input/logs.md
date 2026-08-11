# Log — Milestone 1.3: Skema dan Validasi Data Input

**Tanggal kerja:** 2026-08-11

## Mulai kerja

- Sebelum breakdown ditulis, 4 pertanyaan genuinely-terbuka diajukan ke user (target skema batch, library validasi batch, library validasi real-time, konvensi field) — dijawab: tetap `telco_customers_synthetic`, pandera, Pydantic, snake_case identik kolom.
- Plan disusun dan disetujui user via `ExitPlanMode`.

## Checkpoint 0 — Keputusan + scaffold dependency

- **Task 0a:** `decisions.md` ditulis lengkap (4 keputusan + ringkasan klarifikasi) SEBELUM kode apa pun, mengikuti pola tervalidasi Milestone 1.2.
- **Task 0b:** `pandera`/`pydantic` ditambahkan ke `dependencies` inti `pyproject.toml`. `pip install -e ".[dev]"` berhasil — versi terpasang `pandera==0.32.1`, `pydantic==2.13.4`, langsung dipin persis (Keputusan #3, bukan provisional). `src/churn_prediction/schema/__init__.py` dibuat (scaffold kosong). Verifikasi: `import pandera, pydantic, churn_prediction.schema` berhasil.
