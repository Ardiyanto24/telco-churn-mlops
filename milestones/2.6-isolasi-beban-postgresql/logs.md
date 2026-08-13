# Logs — Milestone 2.6: Isolasi Beban terhadap PostgreSQL

## Checkpoint 1 — Fondasi: harness simulasi dua consumer

**Mulai:** 2026-08-13.

**Task 1-3:** `orchestration/load_test/concurrent_readers.py` ditulis — `simulate_mlflow_alias_reads()` (reuse `registry.resolve_alias_version()`), `simulate_dashboard_aggregate_reads()` (query agregat via koneksi `batch_writer`), `summarize_latencies()` (p50/p95/min/max/n). Sample disimpan sebagai `{"t": epoch, "latency_ms": ...}` (bukan cuma angka mentah) supaya bisa dikorelasikan ke fase flow nanti (Checkpoint 3).

**Task 4 (smoke test, 10 detik tiap consumer):**
```
Consumer A: n=5, p50=299.4ms, p95=3807.7ms (satu cold-start outlier), min=292.6ms, max=3807.7ms
Consumer B: n=7, p50=186.9ms, p95=2553.0ms (satu cold-start outlier), min=185.2ms, max=2553.0ms
```
Tidak ada exception, jumlah sample masuk akal untuk interval 1s. **Temuan:** panggilan pertama tiap consumer jauh lebih lambat (~2.5-3.8s) — cold-start koneksi/client, wajar dan konsisten di run berikutnya (lihat Checkpoint 2). Tidak mempengaruhi p95 pada window pengukuran yang lebih panjang (≥60 sample) karena cuma 1 dari banyak sample.

**Selesai, commit:** (dicatat di Checkpoint 5).

## Checkpoint 2 — Baseline terisolasi

**Task 5-6:** Kedua consumer dijalankan BERSAMAAN (`ThreadPoolExecutor`, 2 worker) selama 90 detik, interval 1 detik, TANPA `batch_scoring_flow()` berjalan.

**Hasil baseline:**
```json
{
  "consumer_a_mlflow_alias":       {"n": 66, "p50": 299.4, "p95": 535.1, "min": 286.8, "max": 3828.7},
  "consumer_b_dashboard_aggregate": {"n": 76, "p50": 186.5, "p95": 195.6, "min": 183.4, "max": 264.3}
}
```
Consumer A p95 masih terpengaruh satu cold-start outlier (3828.7ms) karena `n=66` relatif kecil — dicatat sebagai keterbatasan pengukuran kecil, bukan mempengaruhi kesimpulan utama (lihat Checkpoint 3, p95 concurrent run dengan `n=307` jauh lebih stabil).

## Checkpoint 3 — Beban bersamaan (skala penuh) dan analisis korelasi

**Task 7 (validasi wiring, sampel 2.000 baris):** `batch_scoring_flow(limit=2000)` dijalankan SUNGGUHAN (bukan `.fn()`) bersamaan kedua consumer. Flow selesai 17,9 detik, `rows_written=2000`. Consumer A n=11 (p50=295.6ms), Consumer B n=15 (p50=199.9ms) — wiring `stop_event` berfungsi, kedua thread berhenti bersih saat flow selesai. **Verifikasi lolos**, lanjut ke run skala penuh.

**Task 8 (run skala penuh, PERCOBAAN PERTAMA) — GAGAL, dua bug ditemukan:**

1. Flow gagal cepat (~35 detik dari mulai, BUKAN macet): gerbang kualitas data M2.4 STOP pada percobaan ke-3 (setelah 2 retry) — `"Volume menyimpang 149.2% dari baseline -- di atas ambang stop (50%)."` (percobaan retry sebelumnya: 44464.5% dan 297.3% — makin membaik tiap retry karena tiap percobaan menambah entri 594.194-baris baru ke baseline, tapi belum cukup menutupi 3 entri lama 1.000-2.000 baris yang mendominasi rata-rata). **Root cause: IDENTIK dengan temuan M2.5** — `quality.gate_run_history` untuk `telco_customers_source` berisi campuran skala (2x 1.000 baris sisa Managed trigger M2.5, 1x 2.000 baris dari Task 7 milestone ini barusan) yang membuat run 594.194-baris terlihat sebagai anomali volume ekstrem terhadap baseline yang didominasi entri kecil.
2. **Bug baru, ditemukan sesudahnya:** script pengukuran (`run_concurrent_fullscale.py`) HANG selama 25+ menit (dilaporkan user) meski flow-nya sendiri sudah gagal dalam hitungan detik. **Diagnosis:** `batch_scoring_flow()` raise exception (dari poin 1) SEBELUM baris `stop_event.set()` tereksekusi — kedua consumer thread (dipanggil tanpa `duration_s`, hanya `stop_event`) berputar TANPA HENTI, dan `ThreadPoolExecutor.__exit__` (context manager) menunggu (`shutdown(wait=True)`) thread yang tidak pernah berhenti itu selamanya. **Diperbaiki:** panggilan `batch_scoring_flow()` dibungkus `try/finally`, `stop_event.set()` dipindah ke blok `finally` supaya SELALU tereksekusi terlepas flow sukses atau gagal.

**Perbaikan diterapkan:**
- Baseline `quality.gate_run_history` untuk `telco_customers_source` direset (`DELETE ... WHERE source_table='telco_customers_source'`, 6 baris terhapus — 3 entri kecil + 3 entri 594.194-baris verdict `stop` dari percobaan gagal) via role admin (`SUPABASE_DB_URL`), pola identik fix M2.5.
- Script diperbaiki (`try/finally` untuk `stop_event.set()`).

**Task 8 (run skala penuh, PERCOBAAN KEDUA setelah perbaikan) — BERHASIL BERSIH:**

```
Flow: rows_written=594194, batch_run_id=cd40c4a5-7a97-4fed-a294-ecaf44d9f330
Durasi total: 414,2 detik (~6 menit 54 detik)
```

Fase (dari timestamp log Prefect, epoch presisi):
| Fase | Durasi | Catatan |
|---|---|---|
| extract | 17,7s | Jauh lebih cepat dari baseline M2.5 (~45s) — variasi run-to-run, dicatat sebagai temuan, bukan angka final tetap |
| quality_gate | 1,5s | PASS (baseline baru terbentuk dari run bersih ini sendiri) |
| score | 145,7s (~2m26s) | Juga lebih cepat dari M2.5 (~4m25s) |
| write | 244,3s (~4m04s) | Konsisten dengan M2.5 (~4m01s) — fase paling stabil antar run |

**Task 9 (delta concurrent vs baseline, keseluruhan run):**
```
Consumer A p50: baseline=299.4ms concurrent=298.6ms delta=-0.2%
Consumer A p95: baseline=535.1ms concurrent=483.0ms delta=-9.7%
Consumer B p50: baseline=186.5ms concurrent=208.9ms delta=+12.0%
Consumer B p95: baseline=195.6ms concurrent=607.4ms delta=+210.5%
```

**Task 10 (korelasi per fase):**
```
Consumer A (mlflow alias) -- per fase:
  extract         (17.7s):  n=10,  p50=353.3ms, p95=1436.4ms
  quality_gate     (1.5s):  n=1,   p50=321.9ms
  score          (145.7s):  n=108, p50=311.8ms, p95=431.6ms
  write          (244.3s):  n=186, p50=295.0ms, p95=395.9ms

Consumer B (dashboard aggregate) -- per fase:
  extract         (17.7s):  n=13,  p50=235.7ms, p95=319.8ms
  quality_gate     (1.5s):  n=1,   p50=190.7ms
  score          (145.7s):  n=119, p50=192.9ms, p95=424.9ms
  write          (244.3s):  n=187, p50=216.3ms, p95=766.5ms, max=1308.0ms
```

**Interpretasi:** Consumer A stabil di semua fase (tidak ada fase yang menonjol). Consumer B jelas memuncak di fase `write` (p95 766.5ms, hampir 4x baseline keseluruhan 195.6ms) dengan peningkatan lebih ringan di fase `score` (p95 424.9ms, penyebab pasti tidak diverifikasi lebih lanjut — flow tidak menyentuh `predictions.batch_predictions` selama fase `score`, kemungkinan tekanan resource Postgres/pooler bersama yang lebih umum, bukan kontensi tabel spesifik). Korelasi fase `extract` (17.7s) juga menunjukkan p95 Consumer A sempat naik (1436.4ms, n kecil=10) — kemungkinan besar cuma satu sample cold-start kebetulan jatuh di jendela pendek ini, bukan pola sistematis (tidak berulang di fase lain yang lebih panjang).

## Checkpoint 4 — Analisis mitigasi dan keputusan tertunda

**Task 11-12:** Dievaluasi: index pada `model_version` (Consumer B) tidak menyasar akar masalah (kontensi write-lock, bukan query plan) dan tidak ada manfaat terukur (1 nilai distinct saat ini). Commit bertahap pada `write_predictions` adalah mitigasi paling menyasar akar masalah tapi trade-off nontrivial terhadap keputusan M2.5 (all-or-nothing). **Keputusan: TIDAK menerapkan mitigasi tambahan sekarang** — didokumentasikan lengkap di decisions.md Keputusan #5.

**Task 13:** KT-5 (verdict KK1 ditunda) dan KT-6 (commit bertahap `write_predictions`, kandidat mitigasi masa depan) ditulis lengkap ke `docs/keputusan-tertunda.md`.

**Selesai, commit:** (dicatat di Checkpoint 5).

## Checkpoint 5 — Verifikasi akhir dan dokumentasi

**Verifikasi "tidak ada regresi" (`pytest tests/ -q` penuh) — bug KETIGA ditemukan+diperbaiki:**

Run pertama: `168 passed, 2 errors` — 2 test di `tests/orchestration/test_batch_scoring.py` (M2.5) gagal `RuntimeError: BATCH_READER_DB_URL tidak diset di environment/.env`. **Diagnosis:** `_load_env_var()` di file test itu membaca `.env` untuk cek skip-condition + variabel lokal modul, TAPI TIDAK PERNAH menulis balik ke `os.environ` — kode yang dites (`batch_scoring.py`, baca `os.environ.get(...)` langsung) cuma kebetulan bekerja di shell yang sudah punya var ini di level OS di luar `.env`; shell yang dipakai verifikasi milestone ini tidak punya. **Fix pertama (parsial, kurang):** tambah `os.environ.setdefault()` untuk 3 var yang dirujuk file test itu — TERNYATA masih gagal dengan error BEDA (`QUALITY_GATE_DB_URL tidak diset`), karena flow butuh var lain (`QUALITY_GATE_DB_URL`, `MLFLOW_TRACKING_URI`, kredensial S3) yang test file itu sendiri tidak pernah merujuknya. **Fix tuntas:** `_load_dotenv_into_environ()` baru, memuat SELURUH `.env` ke `os.environ` sekali di level modul (pola sama `deploy_batch_scoring.py::_load_env()`).

**Verifikasi ulang setelah fix:** `tests/orchestration/test_batch_scoring.py -q` → 4 passed. `pytest tests/ -q` penuh → **170 passed** (sama seperti M2.5, tidak ada test baru ditambah milestone ini — harness M2.6 sengaja bukan pytest, lihat decisions.md Keputusan #3).

**Selesai, commit:** lihat pesan commit git untuk hash final.
