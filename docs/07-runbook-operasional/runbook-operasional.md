# Runbook Operasional — Telco Customer Churn Prediction MLOps

**Apa ini:** Panduan praktis "kalau terjadi X, langkah apa yang diambil" untuk skenario kegagalan umum di seluruh sistem ini. **Bukan dokumen arsitektur baru** — tiap entri merujuk balik ke milestone/dokumen sumber untuk detail teknis lengkap (rasional desain, bukti verifikasi, kode). Disusun Milestone 3.12, SETELAH seluruh mekanisme yang dirujuknya (observability, alerting, rollback) benar-benar berjalan dan sudah diuji nyata — bukan prosedur hipotetis.

**Cara pakai saat insiden:** Cari gejala di tabel navigasi cepat di bawah, lompat ke section terkait, ikuti langkah bernomor secara berurutan. Tiap entri punya format konsisten: **Gejala** (apa yang teramati) → **Diagnosis** (cara memastikan penyebab) → **Langkah Respons** (bernomor, tindakan konkret) → **Verifikasi Selesai** (cara tahu insiden benar-benar tertangani) → **Rujukan** (milestone/dokumen untuk detail lengkap).

**Siapa yang perlu tahu:** Proyek ini solo — operator/pemilik sistem (Anda) berperan semua posisi (pola sama M3.7). Tidak ada eskalasi ke tim terpisah.

## Tabel Navigasi Cepat

Cari gejala yang paling mendekati apa yang teramati, lompat langsung ke section-nya — tidak perlu baca semua entri.

| Gejala | Lompat ke |
|---|---|
| Webhook/alert `DriftThresholdExceeded`, panel drift Grafana menunjukkan fitur "stop" | [1. Drift Terdeteksi](#1-drift-terdeteksi) |
| Webhook/alert `PipelineBatchFailed`, flow run Prefect berstatus Failed | [2a. DAG Batch Gagal](#2a-prefect-flow-run-failed-infrakode-bukan-data) |
| Webhook/alert `QualityGateStop`, run Completed tapi tidak ada baris baru di `predictions.batch_predictions` | [2b. Gerbang Kualitas Data Stop](#2b-gerbang-kualitas-data-verdict-stop-data-bukan-infra) |
| `POST /predict` tidak merespons/timeout/error, pod `churn-api` tidak `1/1 Ready` | [3. Real-Time API Down/Lambat](#3-real-time-api-downlambat) |
| Model versi baru menunjukkan prediksi tidak masuk akal setelah promosi | [4. Rollback Mendesak — Versi Model](#4-rollback-mendesak--versi-model) |
| Deploy image/config baru macet, pod baru stuck `0/1 Ready` | [5. Rollback Mendesak — Deployment Kubernetes](#5-rollback-mendesak--deployment-kubernetes) |
| API publik/dashboard publik down, data tidak konsisten, rate-limit salah alarm | [6. Dashboard/API Publik Bermasalah](#6-dashboardapi-publik-bermasalah) |

## Daftar Isi

1. [Drift Terdeteksi](#1-drift-terdeteksi)
2. [DAG Batch Gagal / Gerbang Kualitas Data Stop](#2-dag-batch-gagal--gerbang-kualitas-data-stop)
3. [Real-Time API Down/Lambat](#3-real-time-api-downlambat)
4. [Rollback Mendesak — Versi Model](#4-rollback-mendesak--versi-model)
5. [Rollback Mendesak — Deployment Kubernetes](#5-rollback-mendesak--deployment-kubernetes)
6. [Dashboard/API Publik Bermasalah](#6-dashboardapi-publik-bermasalah)

---

## 1. Drift Terdeteksi

**Gejala:** Notifikasi webhook masuk dari Grafana Alerting (alert `DriftThresholdExceeded`), ATAU panel drift di dashboard Grafana (`churn-monitoring-m35`) menunjukkan fitur berstatus "stop".

**Diagnosis:**
1. Buka payload webhook (kanal `drift-webhook-receiver`, M3.7) — cek field `alertname`, `labels.feature_name`, `status` (`firing`/`resolved`).
2. Query langsung `drift.drift_check_results` (atau panel Grafana yang sama) untuk fitur yang disebut: `SELECT feature_name, psi, p_value, verdict, computed_at FROM drift.drift_check_results WHERE feature_name = '<nama_fitur>' ORDER BY computed_at DESC LIMIT 1;` — verdict `stop` berarti PSI ≥0.25 ATAU p-value <0.01 (dua tier, M3.6 Keputusan #1: keduanya dihitung sekaligus, saling melengkapi — cek KEDUA kolom, jangan cuma satu).
3. Pastikan ini bukan cuma satu fitur "flag" (PSI 0.1-0.25, ambang lebih longgar) — alert Grafana HANYA menyala untuk verdict `stop`.

**Langkah Respons:**
1. Catat fitur mana yang terdampak dan sejak kapan (`computed_at` beberapa siklus terakhir — cek tren, bukan cuma titik terakhir).
2. **Keputusan retraining TETAP MANUAL** (Bagian 5.3 dokumen arsitektur, di luar cakupan sistem ini) — sistem ini TIDAK memicu retraining otomatis. Evaluasi konteks: apakah pergeseran data legitimate (mis. perubahan pola pelanggan nyata) atau anomali data sumber (mis. bug generator sintesis, M2.9).
3. Kalau retraining diputuskan perlu: itu di luar cakupan sistem MLOps ini sepenuhnya (training adalah pekerjaan Data Scientist terpisah, `notebook-audit.md`) — model baru hasil retraining masuk lewat jalur promosi normal (Milestone 2.8: `scripts/verify_before_promotion.py` lalu `set_active_alias()`, lihat [Entri 4](#4-rollback-mendesak--versi-model) untuk mekanisme alias yang sama dipakai promosi).
4. Kalau anomali data sumber: perbaiki di sumbernya (generator/`telco_customers_synthetic`), TIDAK perlu aksi di sisi sistem MLOps ini.

**Verifikasi Selesai:** Siklus drift-monitoring berikutnya (`.github/workflows/drift-monitoring.yml`, event-driven tiap generation baru M2.9/M3.6) menunjukkan verdict kembali `pass`/`flag` untuk fitur yang tadinya `stop`; alert Grafana berubah status `resolved` di webhook.

**Rujukan:** M3.6 (`milestones/3.6-monitoring-drift-kualitas-model/`, mekanisme PSI/KS-test dua tier), M3.7 (`milestones/3.7-jalur-notifikasi-retraining/`, alerting+webhook), M3.9 Checkpoint 8 (migrasi panel drift ke PostgreSQL).

---

## 2. DAG Batch Gagal / Gerbang Kualitas Data Stop

Dua sub-kasus BERBEDA — bedakan dulu sebelum ambil langkah, root cause dan respons keduanya berbeda.

### 2a. Prefect Flow Run FAILED (infra/kode, bukan data)

**Gejala:** Notifikasi webhook alert `PipelineBatchFailed` (M3.8), ATAU flow run `milestone-2-5-batch-scoring` berstatus `Failed` di Prefect UI/API, ATAU panel status pipeline di dashboard Grafana menunjukkan "Failed".

**Diagnosis:**
1. Buka Prefect Cloud UI (workspace `ardi/default`) atau `prefect flow-run ls --flow-name milestone-2-5-batch-scoring` — cari run terbaru berstatus Failed, lihat traceback error di log run tersebut.
2. Bedakan penyebab: (a) error kode/dependency (mis. koneksi Postgres/MLflow gagal, `libgomp.so.1` hilang jika kebetulan jalan di Prefect Managed — KD-1), (b) `source_table` tidak valid/tidak ada, (c) resource habis (jarang, tergantung runner).
3. Cek `predictions.batch_predictions` TIDAK bertambah baris dari run yang gagal (M2.5 Keputusan #1: all-or-nothing, rollback penuh kalau gagal di tengah — kegagalan TIDAK meninggalkan data setengah jadi).

**Langkah Respons:**
1. Kalau error kode/dependency: perbaiki root cause (rujuk `docs/keterbatasan-diterima.md` KD-1 kalau terkait Prefect Managed+LightGBM — solusi yang sudah terbukti: jalankan lewat `.github/workflows/batch-scoring.yml` `workflow_dispatch`, BUKAN lewat Managed work pool).
2. Kalau `source_table` invalid: perbaiki parameter run berikutnya (`source_table` default `telco_customers_source`, atau `telco_customers_synthetic` + `generation_id` untuk jalur event-driven M2.9).
3. Trigger ulang run manual (`workflow_dispatch` GitHub Actions ATAU Prefect deployment run) SETELAH root cause diperbaiki — JANGAN retry tanpa diagnosis (bisa gagal ulang dengan cara sama).
4. Kalau tidak mendesak: tunggu run terjadwal berikutnya (event-driven M2.9 untuk `telco_customers_synthetic`, manual untuk `telco_customers_source`).

**Verifikasi Selesai:** Flow run berikutnya berstatus `Completed`, alert `PipelineBatchFailed` `resolved`, baris baru muncul di `predictions.batch_predictions` dengan `predicted_at` terbaru.

### 2b. Gerbang Kualitas Data Verdict Stop (data, bukan infra)

**Gejala:** Notifikasi webhook alert `QualityGateStop` (M3.8), ATAU flow run Prefect berstatus `Completed` TAPI tidak ada baris baru di `predictions.batch_predictions` (gerbang M2.4 menghentikan scoring SEBELUM tahap tulis).

**Diagnosis:**
1. Query `quality.gate_run_history`: `SELECT source_table, verdict, run_at FROM quality.gate_run_history WHERE source_table = '<source_table>' ORDER BY run_at DESC LIMIT 5;` — verdict `stop` berarti deviasi persentase (NULL rate atau distribusi kategorikal) melewati ambang stop dibanding baseline (M2.4). Koneksi: env var `QUALITY_GATE_DB_URL` (dari `.env` lokal, role least-privilege `quality_gate`, M2.4).
2. Bandingkan run yang stop dengan histori 5 run sebelumnya — deviasi mendadak (mis. NULL rate melonjak) mengindikasikan masalah di sumber data (generator/koneksi), bukan bug kode gerbang itu sendiri (gerbang M2.4 SUDAH diverifikasi bekerja benar berulang kali sejak M2.4-3.11).
3. **Peringatan M2.6**: baseline gerbang bisa tercemar oleh run skala kecil/uji coba (root cause sama pernah terjadi M2.6/M2.8) — cek apakah verdict stop ini genuinely karena data source bermasalah, atau baseline yang perlu dikalibrasi ulang.

**Langkah Respons:**
1. Investigasi sumber data (`telco_customers_source`/`telco_customers_synthetic`) — cek langsung lewat query untuk kolom yang NULL rate-nya melonjak.
2. Kalau data source memang bermasalah: perbaiki di sumbernya (generator, di luar cakupan sistem MLOps ini) sebelum run berikutnya.
3. Kalau baseline perlu dikalibrasi ulang (bukan data source yang salah, tapi ambang yang terlalu ketat/tercemar run kecil): pertimbangkan re-run `scripts/*` pembuat baseline (M2.4) — TAPI ini keputusan yang perlu pertimbangan (mengubah ambang deteksi), bukan tindakan otomatis.
4. Gerbang STOP secara desain BERHASIL mencegah scoring atas data buruk — verdict stop itu sendiri BUKAN kegagalan sistem, itu sistem bekerja seperti dirancang (M2.4).

**Verifikasi Selesai:** Run berikutnya (setelah root cause data diperbaiki) verdict `pass`/`flag`, alert `QualityGateStop` `resolved`, baris baru tertulis ke `predictions.batch_predictions`.

**Rujukan:** `docs/02-implementation-plan/mlops-02-pipeline-orchestration.md` (mekanisme DAG), M2.4 (`milestones/2.4-gerbang-kualitas-data-harian/`, gerbang), M2.5 (`milestones/2.5-batch-scoring-dag/`, all-or-nothing), M2.9 (`milestones/2.9-otomatisasi-scoring-data-sintesis/`, event-driven), M3.8 (`milestones/3.8-dashboard-alerting-terpadu/`, alert rules), `docs/keterbatasan-diterima.md` KD-1.

---

## 3. Real-Time API Down/Lambat

**Gejala:** `POST /predict` tidak merespons/timeout/error, ATAU `kubectl get pods -n churn-prediction` menunjukkan pod `churn-api` tidak `1/1 Ready`, ATAU dashboard menunjukkan error rate/latency naik drastis.

**Diagnosis — LANGKAH PERTAMA selalu bedakan liveness vs readiness (beda makna, M3.3 Keputusan #3):**
1. `kubectl get pods -n churn-prediction` — cek kolom `READY` (`1/1` vs `0/1`) dan `RESTARTS`.
2. `curl http://localhost/healthz` — proses HIDUP atau tidak (livenessProbe, restart trigger kalau gagal 3x berturut, `periodSeconds:15`).
3. `curl http://localhost/readyz` — model SIAP dipakai atau tidak (readinessProbe, keluar dari trafik Service kalau gagal, TIDAK restart, `periodSeconds:5`).
4. **Kombinasi gejala menentukan diagnosis:**
   - `healthz` 200, `readyz` non-200: model/registry MLflow tidak reachable — proses hidup tapi belum/tidak bisa melayani. Cek `kubectl logs -n churn-prediction <pod>` untuk pesan retry backoff MLflow (`psycopg2.OperationalError`/`SQLAlchemy engine could not be created`, pola M3.2/3.11 CP2) — normalnya self-heal dalam ~100 detik (M3.2 KK3) KECUALI host benar-benar tidak valid (retry backoff eksponensial TANPA BATAS, M3.11 CP2).
   - Pod `0/1 Ready` DAN `RESTARTS` bertambah: livenessProbe gagal 3x berturut — Kubernetes SUDAH me-restart otomatis (self-healing bekerja seperti dirancang), cek apakah pulih sendiri setelah restart (~85-140 detik, pola M3.11 CP4).
   - Error rate/latency naik pada beban KONKUREN TINGGI (bukan API down total): **KD-3** (`docs/keterbatasan-diterima.md`) — real-time API memproses request secara efektif single-worker, CPU puncak tidak naik proporsional dengan konkurensi. Ini BUKAN selalu berarti resource K8s kurang — cek `kubectl top pod -n churn-prediction` dulu (kalau CPU jauh di bawah `limits.cpu` 1500m tapi tetap lambat/error, itu KD-3, bukan resource sizing).
5. `kubectl describe pod <pod> -n churn-prediction` — cek Events untuk pesan probe failure persis.

**Langkah Respons:**
1. Kalau self-heal dalam progress (retry backoff MLflow belum habis waktu, ATAU pod baru saja di-restart livenessProbe): TUNGGU, pantau `/healthz`+`/readyz` tiap ~30 detik — JANGAN intervensi manual prematur.
2. Kalau root cause adalah config salah (mis. `MLFLOW_TRACKING_URI` di Secret `churn-api-secrets` rusak): perbaiki Secret, `kubectl rollout restart deployment/churn-api -n churn-prediction` ATAU tunggu restart otomatis berikutnya.
3. Kalau root cause adalah deployment/image baru yang gagal (bukan config existing): lihat [Entri 5 — Rollback Deployment](#5-rollback-mendesak--deployment-kubernetes).
4. Kalau root cause adalah beban konkuren tinggi (KD-3): tidak ada perbaikan cepat sisi K8s — root cause di kode API (M3.2, di luar cakupan runbook operasional ini untuk diperbaiki saat insiden). Mitigasi sementara: kurangi beban konkuren pemanggil kalau memungkinkan.

**Verifikasi Selesai:** `curl /healthz` dan `/readyz` keduanya 200, `kubectl get pods` `1/1 Ready`, request `/predict` normal kembali (uji manual 1 request).

**Rujukan:** M3.2 (`milestones/3.2-real-time-inference-api/`, kontrak error terstruktur), M3.3 (`milestones/3.3-deployment-kubernetes/`, probe design), M3.4 (`milestones/3.4-deteksi-versi-model-aktif/`, refresh tanpa restart), M3.11 (`milestones/3.11-rollback-deployment-resource-sizing/`, KD-3).

---

## 4. Rollback Mendesak — Versi Model

**PENTING: berbeda TEGAS dari [Entri 5 — Rollback Deployment](#5-rollback-mendesak--deployment-kubernetes).** Rollback versi model = ganti penanda alias di MLflow registry, dipicu MODEL bermasalah (prediksi tidak masuk akal, drift parah tidak tertangani, dst). Rollback deployment = `kubectl rollout undo`, dipicu KODE/CONTAINER gagal health check. Jangan tertukar — cek dulu APA yang bermasalah (model vs deployment) sebelum pilih entri.

**Gejala:** Model versi baru yang baru dipromosikan menunjukkan perilaku tidak diharapkan (prediksi tidak masuk akal, hasil `verify_before_promotion.py` ternyata terlewat/salah dibaca, atau masalah ditemukan setelah promosi).

**Diagnosis:**
1. Konfirmasi versi `champion` AKTIF saat ini: jalankan `resolve_alias_version("champion")` (`src/churn_prediction/inference/registry.py`) — atau via Python: `from churn_prediction.inference.registry import resolve_alias_version; resolve_alias_version("champion")`.
2. Identifikasi versi TARGET rollback (versi yang sebelumnya terbukti bekerja baik) — cek riwayat versi di MLflow UI/registry, atau `milestones/2.8-.../report.md` dan `milestones/3.4-.../report.md` untuk riwayat versi yang pernah diverifikasi.
3. Pastikan root cause memang MODEL (bukan kode API/deployment) — kalau ragu, cek [Entri 3](#3-real-time-api-downlambat) dulu untuk pastikan API/pod sehat secara infra.

**Langkah Respons:**
1. Jalankan `set_active_alias(<versi_target>, alias="champion")` (`src/churn_prediction/inference/registry.py`) — SATU baris kode, TIDAK perlu redeploy/rebuild container (M2.1 prinsip: rollback = ganti penanda versi aktif di registry, Bagian 5.2 arsitektur).
2. Verifikasi `resolve_alias_version("champion")` mengembalikan versi target yang baru.
3. Tunggu real-time API pod mendeteksi perubahan lewat background refresh loop (`MODEL_REFRESH_INTERVAL_SECONDS`, ~30 detik, M3.4) — TIDAK perlu restart pod manual.
4. Batch scoring (`batch_scoring_flow()`) otomatis pakai versi baru di run BERIKUTNYA tanpa perlu ubah kode (M2.8/M3.4).

**Verifikasi Selesai:** `resolve_alias_version("champion")` mengembalikan versi target; real-time API `/predict` (setelah ~30-42 detik, M3.4) menghasilkan prediksi dari model versi baru (cek `model_version` di response/lineage); batch run berikutnya mencatat `model_version` baru di `predictions.batch_predictions`.

**Rujukan:** M2.1 (`milestones/2.1-fondasi-orchestrator-model-registry/`, konsep alias), M2.8 (`milestones/2.8-validasi-artifact-promosi-rollback/`, validasi sebelum promosi + uji rollback nyata), M3.4 (`milestones/3.4-deteksi-versi-model-aktif/`, deteksi tanpa restart, timing ~42 detik promosi/~10 detik rollback).

---

## 5. Rollback Mendesak — Deployment Kubernetes

**PENTING: berbeda TEGAS dari [Entri 4 — Rollback Model](#4-rollback-mendesak--versi-model).** Dipicu KODE/CONTAINER baru gagal health check (bukan model bermasalah) — mis. setelah `docker build` image baru + `kubectl apply` deployment baru.

**Gejala:** Setelah deploy image/config baru, `kubectl rollout status deployment/churn-api -n churn-prediction` tidak selesai/timeout, ATAU `kubectl get pods -n churn-prediction` menunjukkan pod baru stuck `0/1 Ready` sementara pod lama (kalau masih ada) tetap `1/1 Running`.

**Diagnosis:**
1. `kubectl rollout status deployment/churn-api -n churn-prediction --timeout=60s` — timeout/tidak selesai mengonfirmasi rollout macet.
2. `kubectl get pods -n churn-prediction` dan `kubectl get rs -n churn-prediction` — cek ada 2 ReplicaSet aktif (lama `READY:1`, baru `READY:0`) — INI NORMAL SEMENTARA (`maxUnavailable:0`, M3.11 Keputusan #3, pod lama TIDAK diturunkan sampai pod baru Ready, zero-downtime inheren).
3. `kubectl describe pod <pod-baru> -n churn-prediction` — cek Events untuk pesan probe failure persis (mis. `connection refused` = port belum terbuka, `context deadline exceeded` = proses hidup tapi lambat merespons).
4. `kubectl logs <pod-baru> -n churn-prediction` — cari traceback/error spesifik (crash saat startup, dependency hilang, config salah).

**Langkah Respons:**
1. **Trafik TIDAK terganggu selama diagnosis** (pod lama masih melayani penuh, M3.11 KK1 — downtime nol dibuktikan empiris) — tidak perlu buru-buru, tapi ReplicaSet rusak tetap memakan resource sampai dibersihkan.
2. `kubectl rollout undo deployment/churn-api -n churn-prediction` — mengembalikan ke revisi sebelumnya, membersihkan ReplicaSet rusak.
3. `kubectl rollout status deployment/churn-api -n churn-prediction` — pastikan sukses (selesai cepat, TIDAK timeout).
4. `kubectl rollout history deployment/churn-api -n churn-prediction` — cek revisi tercatat (anotasi `kubernetes.io/change-cause` kalau diisi saat deploy, praktik baik untuk audit trail).
5. Perbaiki root cause di image/config SEBELUM re-deploy — JANGAN re-apply manifest yang sama tanpa perbaikan (bakal macet sama lagi).

**Verifikasi Selesai:** `kubectl get pods -n churn-prediction` cuma 1 pod (versi sehat) `1/1 Running`; `kubectl get rs` — ReplicaSet rusak `DESIRED:0`; `curl /healthz` dan `/readyz` 200.

**Rujukan:** M3.11 (`milestones/3.11-rollback-deployment-resource-sizing/`, `strategy`/`revisionHistoryLimit` eksplisit, simulasi terkontrol dengan bukti downtime nol).

---

## 6. Dashboard/API Publik Bermasalah

> **Keterbatasan pengujian**: entri ini BELUM dapat drill "down" khusus di M3.12 (beda dari 4 entri lain yang semua diuji ulang lewat simulasi terkontrol M3.12) — hanya berbasis mekanisme yang sudah terverifikasi M3.10 (kredensial+rate-limit) plus pengetahuan operasional platform pihak ketiga. Perlakukan langkah di bawah sebagai titik awal diagnosis, bukan prosedur yang sudah teruji end-to-end sekuat entri lain.

**Gejala:** API publik (`https://telco-churn-public-api.telco-churn-ardiyanto.workers.dev`) tidak merespons/error, ATAU dashboard publik (`https://public-dashboard-puce.vercel.app`) menampilkan data kosong/error, ATAU data dashboard publik tidak konsisten dengan Grafana internal, ATAU pengunjung sah kena rate-limit (429) padahal wajar.

**Diagnosis:**
1. **API publik down/error**: cek `curl https://telco-churn-public-api.telco-churn-ardiyanto.workers.dev/api/health` — response `{"status":"ok","db":{"ok":1}}` berarti Worker+Hyperdrive+Postgres sehat. Kalau gagal, cek Cloudflare dashboard (status Worker, log real-time via `wrangler tail` dari dalam `public-api/`) untuk error runtime.
2. **Dashboard publik error/kosong**: cek Vercel dashboard (status deployment `public-dashboard/`) — kemungkinan build/deploy gagal, atau `NEXT_PUBLIC_API_BASE_URL` salah/API publik sendiri down (diagnosis poin 1 dulu).
3. **Data tidak konsisten vs Grafana internal**: KEDUANYA baca `monitoring.metrics_snapshot` yang SAMA (M3.9/3.10 prinsip satu sumber kebenaran) — perbedaan HANYA boleh dari lag waktu snapshot (M3.9 siklus ~1 menit), BUKAN sumber data beda. Kalau selisih signifikan/persisten, cek role `monitoring_public_reader` (M3.10) masih attached+tidak revoked, dan cek `metrics_aggregator.py` (M3.9, pod always-on) masih berjalan (`kubectl get pods -n monitoring`).
4. **Rate-limit salah alarm**: cek `PUBLIC_API_RATE_LIMITER` konfigurasi (`public-api/wrangler.jsonc`, 60 request/menit/IP) — kalau pengunjung sah kena 429 di trafik wajar, kemungkinan banyak pengunjung di belakang NAT/IP sama (per-IP, bukan per-sesi), pertimbangkan menaikkan ambang (provisional, KT terkait rate limit M3.10).

**Langkah Respons:**
1. API publik down karena Worker crash/error: cek log (`wrangler tail`), perbaiki kode, `wrangler deploy` ulang dari `public-api/` (repo TERPISAH dari `deployment-mlops`, `git init` sendiri — cek riwayat commit DI DALAM folder itu).
2. API publik down karena Hyperdrive/Postgres tidak reachable: cek koneksi Supabase langsung (`db.<ref>.supabase.co`, IPv6-only, M3.10) belum berubah/down dari sisi Supabase.
3. Dashboard publik gagal build/deploy: cek log build Vercel, perbaiki, `vercel --prod` ulang dari `public-dashboard/` (repo terpisah juga).
4. Role `monitoring_public_reader` ter-revoke tidak sengaja: `infra/sql/3.10_monitoring_public_role.sql` berisi definisi ulang role — jalankan ulang untuk restore GRANT.

**Verifikasi Selesai:** `curl /api/health` 200 dengan `db.ok:1`; dashboard publik diakses browser menampilkan data terkini; 5 titik data dashboard publik vs Grafana internal cocok (pola verifikasi M3.10 KK3).

**Rujukan:** M3.9 (`milestones/3.9-penyimpanan-data-monitoring-postgresql/`, sumber data tunggal), M3.10 (`milestones/3.10-api-publik-dashboard-monitoring/`, Cloudflare Worker+Hyperdrive+Vercel, rate limiting, role `monitoring_public_reader` — **CATATAN STRUKTUR PENTING**: kode `public-api/`/`public-dashboard/` di repo git TERPISAH, bukan `deployment-mlops`).

