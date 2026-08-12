# Logs — Milestone 2.4: Gerbang Kualitas Data Harian

## Checkpoint 1 — Provisioning riwayat baseline

**Mulai:** 2026-08-13.

Sebelum plan ditulis, dicek kondisi data nyata: `SELECT count(DISTINCT imported_at) FROM telco_customers_source` → 1 (bulk-load sekali, bukan data harian), `telco_customers_synthetic` masih 0 baris. Dua pertanyaan diajukan ke user (metodologi ambang batas, perilaku gagal) — dijawab deviasi sederhana (dengan catatan upgrade masa depan tetap dibuka) dan bertingkat stop/flag.

**Task 1:** `infra/sql/2.4_quality_gate_role.sql` disiapkan (schema `quality`, tabel `quality.gate_run_history` append-only, role `quality_gate`). Konfirmasi eksplisit diminta sebelum eksekusi — dikonfirmasi. Dijalankan lewat `psycopg2` (skrip scratchpad, pola sama M2.1). **Verifikasi:** role `quality_gate` terbukti BISA insert ke `quality.gate_run_history`, terbukti TIDAK BISA baca `telco_customers_source` maupun schema `mlflow` (`InsufficientPrivilege` pada percobaan akses keduanya).

**Task 2:** `src/churn_prediction/quality/baseline.py` ditulis (`record_run()`/`read_recent_baseline()`). Sanity check manual terhadap DB sungguhan (insert 1 baris, baca balik → `None` karena <3 run) sebelum unit test formal.

**Task 3:** `tests/quality/test_baseline.py` ditulis — 4 test round-trip terhadap `quality.gate_run_history` sungguhan (insert; baseline <3 run → `None`; baseline ≥3 run → list terurut, jsonb round-trip dict tetap dict; batas `n_runs` dihormati). **Verifikasi:** `pytest tests/quality/test_baseline.py -v` → **4 passed**.

**Selesai, commit:** `9d704f6` (feat).

## Checkpoint 2 — Logika pemeriksaan (pure functions)

**Task 4:** `src/churn_prediction/quality/checks.py` ditulis — 3 pure function (`check_volume`, `check_null_proportion`, `check_category_distribution`) + `aggregate_verdict()`. Ambang batas dikodifikasi sebagai konstanta modul (lihat `decisions.md` Keputusan #1).

**Task 5:** `src/churn_prediction/quality/gate.py` ditulis — `run_gate()` mengorkestrasi hitung stats dari DataFrame, baca baseline, jalankan checks, tulis hasil run. Sengaja tidak hardcode konvensi nama kolom (pola normalisasi M1.6).

**Task 6:** Test ditulis dan dijalankan bertahap:
- `tests/quality/test_checks.py` (16 test murni, tanpa DB) — seluruh kombinasi threshold (pass/flag/stop untuk volume, NULL, distribusi kategori) + `aggregate_verdict`. **Verifikasi:** `pytest tests/quality/test_checks.py -v` → **16 passed**.
- `tests/quality/test_gate.py` (5 test integrasi, terhadap `quality.gate_run_history` sungguhan) — skenario KK asli milestone: (a) data normal → `pass`; (b) volume disuntik anjlok 90% → `stop`; (c) NULL disuntik naik 15% pada kolom fitur → `stop`; (d) distribusi kategori digeser 15 poin → `flag` (bukan `stop`, membuktikan perilaku bertingkat benar-benar bekerja, bukan cuma stop/pass biner); (e) baseline kosong (<3 run) → `pass` dengan catatan "belum cukup data", bukan false-flag. **Verifikasi:** `pytest tests/quality/test_gate.py -v` → **5 passed**.

`pytest tests/ -q` penuh → **163 passed** (138 sebelumnya + 4 + 16 + 5), tidak ada regresi.

**Selesai, commit:** `c2ce6d6` (feat).

## Checkpoint 3 — Dokumentasi & penutupan

**Task 7-10:** `decisions.md` (keterbatasan data statis dicatat eksplisit, bukan disembunyikan), `logs.md` (file ini), `report.md`, dan status `CLAUDE.md`/`AGENT.md` ditulis.
