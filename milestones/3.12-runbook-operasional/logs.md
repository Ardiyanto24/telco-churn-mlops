# Logs — Milestone 3.12: Runbook Operasional

## Checkpoint 1 — Keputusan Terdokumentasi

Ditulis `decisions.md` awal (6 Keputusan Desain + keputusan user cakupan KK2 4 skenario) sebelum implementasi apa pun — commit `7500e33 docs(milestone-3.12): checkpoint 1 - keputusan awal`.

## Checkpoint 2 — Draf Runbook (6 Entri Skenario)

Ditulis `docs/07-runbook-operasional/runbook-operasional.md` — kerangka+header, 6 entri (Drift Terdeteksi; DAG Batch Gagal/Gerbang Kualitas Data Stop dua sub-kasus; Real-Time API Down/Lambat; Rollback Model; Rollback Deployment K8s; Dashboard/API Publik Bermasalah), tabel navigasi cepat berbasis gejala. Format konsisten Gejala→Diagnosis→Langkah Respons→Verifikasi Selesai→Rujukan di tiap entri. Commit `622190c docs(milestone-3.12): checkpoint 2 - draf runbook 6 skenario`.

## Checkpoint 3 — Simulasi 1: Gerbang Kualitas Data Stop

Rancangan ditulis+commit SEBELUM eksekusi (`fc5c9fa`, bukti timestamp urutan rancangan→eksekusi). Eksekusi: `run_gate()` langsung dengan DataFrame >10% NULL, `source_table="_verification_probe_m312"`, `record_history=True`.

**Hasil nyata:** `verdict='stop'` (run_id 1304) langsung tanpa baseline historis (jalur ambang NULL absolut, `NULL_STOP_THRESHOLD=0.10`). Baris tercatat `quality.gate_run_history` (`run_at` 2026-08-15 23:50:32 UTC). Alert Grafana `QualityGateStop` Firing pukul 23:51:20 UTC (48 detik kemudian, status `active` dikonfirmasi Grafana Alertmanager API dengan kredensial `GF_SECURITY_ADMIN_PASSWORD` dari `monitoring-secrets`). Webhook `pipeline-webhook-receiver` (webhook.site) menerima payload `status:"firing"` pukul 23:51:56 UTC.

Runbook Task 4 (entri "2b") diikuti persis — query SQL berhasil first-try, TAPI ditemukan 1 gap: env var koneksi (`QUALITY_GATE_DB_URL`) tidak disebutkan eksplisit. Diperbaiki di tempat.

**Audit:** 4/5 MATCH sempurna, 1 MATCH dengan deviasi kecil (langsung diperbaiki). Commit audit `aa6fcab`, commit perbaikan runbook `dfc3a57`.

## Checkpoint 4 — Simulasi 2: Rollback Model

Kondisi awal dicek: `resolve_alias_version("champion")` = versi 1. Registry punya 5 versi (1-5). Rancangan ditulis+commit sebelum eksekusi (`c0caee5`) — target rollback versi 5.

**Eksekusi:** `set_active_alias("5", alias="champion")` → `resolve_alias_version("champion")` = "5" (segera, tanpa error). SEGERA di-restore: `set_active_alias("1", alias="champion")` → kembali "1". Window champion menunjuk versi 5 di produksi: hitungan detik.

Runbook Task 6 (entri "4") diikuti persis — command Python persis seperti tertulis, berhasil first-try tanpa modifikasi.

**Audit:** 4/4 MATCH sempurna, nol deviasi. Cakupan sengaja tidak menguji ulang independen refresh loop real-time API ~30-42 detik (M3.4) — window promosi diminimalkan demi keamanan operasional, bersandar verifikasi M3.4 sebelumnya. Commit audit `6865fdf`.

## Checkpoint 5 — Simulasi 3: Real-Time API Down/Lambat

**Kondisi awal ditemukan (sebelum rancangan dikunci):** HPA (M3.11, masih aktif) baru scale-up ke 3 replica akibat CPU util 266%/70% — noise lingkungan tidak terkait simulasi ini (karakteristik KD-3). Dicatat di rancangan sebagai "diterima apa adanya". Rancangan ditulis+commit sebelum eksekusi (`614d3d0`).

**Eksekusi:** `kubectl set env deployment/churn-api -n churn-prediction MLFLOW_TRACKING_URI="postgresql://invalid-host-m312:5432/mlflow"`.

**Insiden operasional ditemukan+diperbaiki di tengah jalan:** Rolling update mencoba membuat pod ke-4 (`maxSurge:1` di atas 3 replica existing) — stuck `Pending`, `FailedScheduling: Insufficient memory` (4 pod × 400Mi requests melebihi memori node saat itu). Diperbaiki `kubectl scale deployment/churn-api --replicas=1` (membebaskan memori) — pod baru berhasil schedule setelahnya.

**Temuan signifikan (deviasi dari rancangan):** Diuji langsung via `kubectl port-forward pod/<pod-baru> 8001:8000` (BUKAN lewat Service `localhost` — curl ke Service tetap 200 selama pod lama masih Ready, tidak representatif untuk pod spesifik). Hasil: `/healthz` pod baru mengembalikan `000` (connection refused) SELAMA seluruh window pengamatan (~3 menit, 17× startup probe gagal) — BUKAN 200 seperti diasumsikan rancangan (yang menggeneralisasi dari pola M3.2 "host unreachable tapi valid"). Log pod: `psycopg2.OperationalError: could not translate host name "invalid-host-m312"` + retry backoff eksponensial (3.1s→6.3s→12.7s→25.5s→51.1s), persis pola M3.11 CP2.

**Restore:** `kubectl set env deployment/churn-api -n churn-prediction MLFLOW_TRACKING_URI-` — pod rusak `Terminating`, pod lama (`thvdt`) tidak pernah diganti (hash kembali sama seperti semula). `curl /healthz`+`/readyz` via Service 200 segera.

**Audit:** 2/5 MATCH penuh, 1 MATCH sebagian, 2 DEVIASI signifikan ditemukan dan diperbaiki di runbook (pembedaan pola healthz DNS-gagal vs unreachable-valid; instruksi port-forward untuk diagnosis pod spesifik). Commit audit `e0cb64f`, commit perbaikan runbook `839d5d9`.

## Checkpoint 6 — Simulasi 4: Drift Terdeteksi

Kondisi awal dicek: cluster stabil 1 pod, HPA 10-25%/70%. Rancangan ditulis+commit sebelum eksekusi (`4d521f8`) — target awal fitur `tenure`.

**Insiden metodologi ditemukan+diperbaiki DI TENGAH eksekusi:** Override pertama (`tenure`, sesuai rancangan) menghasilkan verdict `stop` (PSI 8.68) — TAPI query histori `quality.gate_run_history`-setara untuk drift (`drift.drift_check_results`) menunjukkan `tenure` SUDAH verdict `stop` terus-menerus sejak 2026-08-14 (drift produksi asli, persis temuan M3.6 report soal `service_count`/`tenure`). Alert `startsAt` (00:02:20Z) TERBUKTI lebih awal dari eksekusi saya (`computed_at` 00:11:48Z) — bukti konklusif alert BUKAN dipicu simulasi ini.

**Koreksi:** Dicari fitur dengan verdict TERKINI `pass` (query `DISTINCT ON` seluruh 30 fitur) — `tc_residual` dipilih (PSI 0.027, `pass`). Override diulang: transisi bersih `pass` (00:11:48) → `stop` PSI 8.29 (00:15:58). Alert Firing `startsAt` 00:17:20Z (1m22s kemudian, genuinely baru). Webhook diterima 00:19:18Z (1m58s kemudian) — payload berisi ARRAY `alerts[]` dengan 3 fitur sekaligus (`service_count`, `tc_residual`, `tenure`, grouped by alertname, M3.7/M3.8 `group_by:["alertname"]`) — temuan tambahan bernilai, operator harus scan array bukan asumsi 1 payload = 1 fitur.

**Restore:** `compute_drift.py --mode current` (tanpa override) → verdict `tc_residual` kembali `pass` (00:23:41). Alert tidak lagi muncul di daftar aktif Grafana Alertmanager API (resolved) — notifikasi webhook "resolved" spesifik tidak tertangkap dalam window pengamatan (~2 menit), status Alertmanager API dipakai sebagai bukti otoritatif.

Runbook Task 3 (entri "1") diikuti persis — ditemukan gap sama kelas Checkpoint 3/5 (env var `DRIFT_READER_DB_URL` tidak disebutkan) + gap baru (payload multi-fitur tidak diperingatkan).

**Audit:** 5/6 MATCH (1 dengan insiden metodologi diperbaiki di tengah jalan, 1 dengan temuan tambahan), 1 deviasi kecil diperbaiki. Commit audit `8555197`, commit perbaikan runbook `b81f6fa`.

## Checkpoint 7 — Penutupan Dokumentasi (dan Proyek)

Verifikasi akhir: cluster stabil 1 pod `1/1 Ready`, HPA `10%/70%`, `champion` = versi 1 (dikonfirmasi tidak berubah permanen dari seluruh rangkaian simulasi), `/healthz`+`/readyz` 200. `decisions.md` diperbarui dengan ringkasan tabel hasil audit 4 simulasi. `logs.md` (file ini), `report.md`, dan update `CLAUDE.md` (lokal) menyelesaikan milestone TERAKHIR proyek ini.
