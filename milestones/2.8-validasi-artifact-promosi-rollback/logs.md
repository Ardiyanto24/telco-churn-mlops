# Logs — Milestone 2.8: Validasi Artifact, Promosi, dan Rollback Versi Model

## Riset Sebelum Plan Ditulis

`docs/05-model-registry-contract/model-registry-contract.md` (M2.1) dibaca ulang — ditemukan alias `challenger` sudah dicadangkan eksplisit, dan `scripts/register_production_model.py`/`scripts/promote_active_alias.py` sudah ada, keduanya menyebut eksplisit dipakai lagi "sebelum M2.8". Ini mengubah cakupan kerja secara signifikan (mekanisme alias TIDAK perlu dibangun ulang).

## Checkpoint 1 — Sanity check artifact

**Task 1-2:** `src/churn_prediction/inference/artifact_validation.py` ditulis — `sanity_check_bundle()` menjalankan bundle lewat `ChurnPyfuncModel.predict()` sungguhan (reuse, bukan implementasi ulang) terhadap 3 baris input uji sintetis. Diwire ke dalam `register_model()` (`registry.py`) — `ValueError` sebelum `log_model()` kalau gagal.

**Task 3:** `tests/inference/test_artifact_validation.py` — 5 test (bundle valid asli PASS; bundle NaN, out-of-range, dan crash — masing-masing FAIL spesifik). Lokal: `pytest tests/inference/test_artifact_validation.py -v` → 5 passed.

**Task 4:** `tests/inference/test_registry.py` ditambah `test_register_model_rejects_broken_bundle_before_mlflow_called` — spy `mlflow.pyfunc.log_model`, verifikasi TIDAK PERNAH terpanggil untuk bundle rusak. Lokal: 6 passed (5 lama + 1 baru).

**Task 5 (regresi):** `pytest tests/ -q` penuh → **178 passed** (172 M2.7 + 6 baru), 0 gagal — gerbang baru tidak merusak registrasi bundle valid yang sudah ada.

**Selesai, commit:** `e7540c9` (feat, milestone-2.8 checkpoint 1).

## Checkpoint 2 — Verifikasi sebelum promosi

**Task 6:** `scripts/register_candidate_model.py` ditulis — registrasi model+preprocessor sama, threshold 0.5, tag `challenger`.

**Task 7:** `scripts/verify_before_promotion.py` ditulis — pull sampel real (`batch_reader`), bandingkan `load_model_by_version(challenger)` vs `load_active_model(champion)`, verdict pass/flag berdasar delta churn_rate (ambang 20pp).

**Task 8 (dijalankan sungguhan):**
```
python scripts/register_candidate_model.py
  -> Registered churn_prediction_model version 2 (KANDIDAT UJI, threshold=0.5)
  -> Alias 'challenger' -> version 2
  -> (alias 'champion' TIDAK diubah)

python scripts/verify_before_promotion.py
  -> Kandidat: versi 2 (alias 'challenger')
  -> Sampel: 1000 baris dari telco_customers_source
  -> Champion churn_rate: 31.20%
  -> Candidate churn_rate: 37.50%
  -> Delta: 6.30 poin persentase (ambang provisional: 20.0pp)
  -> Verdict: PASS
```

**Task 9:** `tests/scripts/test_verify_before_promotion.py` — 4 test logika (exception, NaN, delta kecil→pass, delta besar→flag), semua di-mock (tanpa DB). Lokal: 4 passed.

**Selesai, commit:** `380ee2f` (feat, milestone-2.8 checkpoint 2).

## Checkpoint 3 — Promosi, rollback, verifikasi DAG otomatis

**Cek prasyarat:** `quality.gate_run_history` untuk `telco_customers_source` = 0 baris (di bawah `MIN_RUNS_FOR_BASELINE=3`) — aman dari risiko pencemaran baseline yang sudah 2x terjadi sebelumnya (M2.5, M2.6).

**Task 10 (uji coba terkontrol promosi):**
```
python scripts/promote_active_alias.py 2 champion
  -> Alias 'champion' -> churn_prediction_model version 2

batch_scoring_flow(limit=50) [run nyata]
  -> Scored 50 baris, model_version=2
  -> batch_run_id=381ccc54-6539-49e4-8461-bcc19832f71b

Query langsung predictions.batch_predictions WHERE batch_run_id=...:
  model_version='2', model_alias='champion', count=50,
  avg_proba=0.319367251771666, sum_label=12
```
DAG otomatis memakai versi baru TANPA satu baris kode `batch_scoring.py` diubah — bukti langsung dari query, bukan cuma baca log Prefect.

**Task 11 (uji coba terkontrol rollback):**
```
python scripts/promote_active_alias.py 1 champion
  -> Alias 'champion' -> churn_prediction_model version 1

batch_scoring_flow(limit=50) [run nyata]
  -> Scored 50 baris, model_version=1
  -> batch_run_id=8983c78e-5b96-4ed4-a33b-c8c76afbbfd0

Query langsung predictions.batch_predictions WHERE batch_run_id=...:
  model_version='1', model_alias='champion', count=50,
  avg_proba=0.319367251771666, sum_label=10
```
`churn_probability` (avg_proba) IDENTIK di kedua run (0.319367251771666, 50 baris sama, `ORDER BY id LIMIT 50` deterministik) — bukti model weights benar-benar sama, cuma threshold beda. `churn_label` (sum_label) beda 12 vs 10 — konsisten threshold 0.5 vs 0.6238 lebih ketat.

**Verifikasi final state registry:**
```
Aliases: {'challenger': 2, 'champion': 1}
```
`champion` kembali ke versi 1 (state produksi benar) sebelum lanjut dokumentasi.

**Task 12:** `docs/05-model-registry-contract/model-registry-contract.md` diperbarui — Bagian 5/6 (prosedur formal 5 langkah), Bagian 3 (makna alias `challenger` diperjelas), Bagian 7 (Riwayat Versi, versi 2 ditambahkan dengan status jelas).

**Verifikasi regresi akhir:** `pytest tests/ -q` penuh → **182 passed** (178 + 4 baru).

**Selesai, commit:** `1594dbf` (docs, milestone-2.8 checkpoint 3).

## Checkpoint 4 — Dokumentasi dan penutupan

Tidak ada temuan/bug baru di checkpoint ini — murni penulisan decisions.md/logs.md/report.md dan update status proyek.
