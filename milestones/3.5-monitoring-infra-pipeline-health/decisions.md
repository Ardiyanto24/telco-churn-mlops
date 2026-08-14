# Decisions — Milestone 3.5: Monitoring Infra dan Pipeline Health

## Konteks

Dokumen arsitektur (Bagian 10, `docs/01-architecture/rancangan-arsitektur-mlops-platform.md`) sengaja membiarkan "monitoring stack konkret" terbuka. Ini keputusan pertama Milestone 3.5 yang genuinely terbuka, berdampak material (jadi fondasi M3.6-3.9), dan mahal diubah — diajukan ke user lewat `AskUserQuestion` SEBELUM plan ditulis, sesuai workflow wajib proyek. Keputusan lain di bawah adalah turunan dari keputusan stack ini plus preseden proyek yang sudah konsisten sejak M2.1/M2.4/M2.5/M2.9.

## Keputusan Teknis

### 1. Monitoring stack: Prometheus + Grafana self-host di Kubernetes lokal

**Keputusan:** Prometheus (scrape metrik API + exporter kustom status pipeline) dan Grafana (dashboard) di-deploy sebagai Deployment tambahan di cluster Docker Desktop Kubernetes yang sama dengan real-time API (M3.3), namespace terpisah `monitoring`.

**Kenapa:** Diajukan ke user lewat `AskUserQuestion` dua putaran. Putaran pertama menyajikan 3 opsi (self-host lokal, Grafana Cloud free tier, custom tanpa Prometheus/Grafana); user eksplisit minta dicek dulu forward-compatibility terhadap M3.6-3.12 sebelum memutuskan. Setelah membaca ulang teks sumber M3.6-3.12 secara penuh, ditemukan bukti kuat forward-compat:
- M3.9 (`mlops-03-deployment-observability.md` baris 190) eksplisit menyebut Prometheus sebagai *"sumber metrik asal"* untuk agregasi periodik ke PostgreSQL — mengasumsikan Prometheus SUDAH berdiri sejak sebelumnya, bukan dibangun baru di M3.9.
- M3.9 (baris 198) juga menyebut Grafana "diarahkan" membaca dari PostgreSQL (bukan "dibangun") — mengasumsikan Grafana+dashboard SUDAH ada sejak sebelumnya.
- M3.8 "menyatukan hasil M3.5+M3.6 ke dalam satu dashboard" — paling natural kalau dashboard itu sudah berdiri sejak M3.5, tinggal ditambah panel drift (M3.6).
- M3.6 (drift) dan M3.7 (alerting) paling mudah dibangun di atas Prometheus+Grafana yang sudah ada (exporter drift baru discrape Prometheus yang sama; Grafana alerting/Alertmanager untuk notifikasi).

User memilih opsi ini dengan eksplisit pada putaran kedua setelah analisis di atas disajikan.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Grafana Cloud free tier (managed)** — DITOLAK: metrik "pipeline health" tetap berhenti mengalir begitu komputer/cluster lokal mati (sumber datanya tetap lokal) — dashboard yang "kelihatan hidup" tapi datanya basi berisiko menyesatkan. Juga menambah akun+API key eksternal baru yang perlu dikelola sebagai secret tambahan tanpa manfaat konkret dibanding self-host.
- **Custom ringan tanpa Prometheus/Grafana** (endpoint `/metrics-summary` in-memory + skrip polling + HTML statis) — DITOLAK: bertentangan langsung dengan Bagian 8.3 arsitektur yang SUDAH fix Grafana sebagai tool dashboard internal (bukan pilihan bebas), tidak punya "riwayat" sungguhan (agregasi in-memory hilang tiap restart — melanggar KK1 M3.5 sendiri: "tersimpan sebagai riwayat, bukan snapshot sesaat"), dan tidak kompatibel dengan asumsi M3.9 soal "sumber metrik asal Prometheus" — akan perlu dibongkar ulang total di M3.8/3.9.

### 2. Namespace Kubernetes terpisah `monitoring`

**Keputusan:** Prometheus, Grafana, dan `pipeline-health-exporter` di-deploy ke namespace `monitoring`, terpisah dari `churn-prediction` (M3.3, workload serving).

**Kenapa:** Pemisahan standar infra observability vs workload serving (pola umum `kube-prometheus-stack`), memudahkan teardown/redeploy komponen monitoring tanpa menyentuh Deployment API produksi.

**Opsi yang Dipertimbangkan tapi Ditolak:** Reuse namespace `churn-prediction` — DITOLAK: mencampur concern operasional yang berbeda sifat, mempersulit `kubectl get pods -n churn-prediction` tetap mencerminkan workload serving murni.

### 3. Instrumentasi API pakai `prometheus-fastapi-instrumentator`

**Keputusan:** `Instrumentator().instrument(app).expose(app, endpoint="/metrics")` — satu baris wiring di `src/churn_prediction/api/app.py`.

**Kenapa:** Menghasilkan histogram latency (`http_request_duration_seconds`, dengan buckets siap pakai untuk `histogram_quantile`) + counter request/error per status code (`http_requests_total`, label `status` sudah dikelompokkan `2xx`/`4xx`/`5xx`) langsung sesuai kebutuhan KK1 M3.5, tanpa custom code tambahan yang rawan salah hitung.

**Opsi yang Dipertimbangkan tapi Ditolak:** Instrumentasi manual pakai `prometheus_client` langsung (middleware custom hitung durasi+status) — DITOLAK: reimplementasi logic yang sudah matang dan banyak dipakai di ekosistem FastAPI, tanpa manfaat tambahan untuk kebutuhan proyek ini.

### 4. Exporter pipeline health adalah image Docker TERPISAH dan LEAN

**Keputusan:** `orchestration/monitoring/pipeline_health_exporter.py` di-package ke image Docker sendiri (`infra/docker/exporter.Dockerfile`) — install `prometheus_client`+`prefect`+`sqlalchemy`+`psycopg2-binary` langsung, BUKAN `pip install` package `churn_prediction` (yang membawa lightgbm/xgboost/mlflow-skinny/scikit-learn).

**Kenapa:** Exporter tidak pernah memuat model — deps-nya jauh lebih sempit dari inference service. Terbukti nyata: image exporter 534MB vs `churn-inference` 1.63GB (~3x lebih kecil, didominasi dependency GPU tidak terpakai yang sudah dicatat M3.1).

**Opsi yang Dipertimbangkan tapi Ditolak:** Reuse image `churn-inference` dengan entrypoint berbeda — DITOLAK: membawa dependency ML yang sama sekali tidak relevan untuk komponen yang murni polling status, memperlambat build+startup tanpa manfaat.

### 5. Role Postgres baru `monitoring_reader` (SELECT-only)

**Keputusan:** Role baru, GRANT SELECT-only ke `quality.gate_run_history` + `predictions.batch_predictions` (`infra/sql/3.5_monitoring_reader_role.sql`).

**Kenapa:** Pola "satu role per pola akses" konsisten dipakai tiap milestone sejak M2.1 (`mlflow_registry`)/M2.4 (`quality_gate`)/M2.5 (`batch_reader`/`batch_writer`)/M2.9. Role existing (`batch_writer`/`quality_gate`) scope-nya beda (masing-masing punya INSERT yang tidak dibutuhkan exporter, dan `batch_writer` tidak bisa baca `quality.gate_run_history`).

**Opsi yang Dipertimbangkan tapi Ditolak:** Reuse `batch_writer` atau `quality_gate` — DITOLAK: melanggar least-privilege (exporter cuma butuh SELECT, kedua role existing punya INSERT), dan tidak ada satu role existing yang punya akses ke KEDUA tabel yang dibutuhkan sekaligus.

### 6. Dashboard Grafana di-provision deklaratif (ConfigMap)

**Keputusan:** Datasource Prometheus dan dashboard JSON (`infra/k8s/monitoring/grafana-datasource-configmap.yaml`, `grafana-dashboard-configmap.yaml`) di-mount ke path provisioning standar Grafana (`/etc/grafana/provisioning/`), bukan dikonfigurasi manual lewat UI.

**Kenapa:** Reproducible lintas restart/redeploy pod (Grafana pakai SQLite in-pod tanpa PVC untuk state UI — dashboard hasil klik manual akan HILANG tiap pod restart), konsisten pola manifest-driven `infra/k8s/` yang sudah dipakai sejak M3.3.

**Opsi yang Dipertimbangkan tapi Ditolak:** Konfigurasi manual lewat Grafana UI setelah deploy — DITOLAK: tidak reproducible, hilang tiap pod restart kecuali ditambah PVC terpisah untuk state Grafana (kompleksitas tambahan tidak sepadan dibanding provisioning file yang sudah standar didukung Grafana).

### 7. Prometheus TSDB pakai PVC (bukan `emptyDir`)

**Keputusan:** `infra/k8s/monitoring/prometheus-pvc.yaml` (2Gi, StorageClass default Docker Desktop `hostpath`), di-mount ke `/prometheus`.

**Kenapa:** KK1 M3.5 eksplisit minta metrik "tersimpan sebagai riwayat, bukan hanya snapshot sesaat" — `emptyDir` hilang tiap pod restart, PVC bertahan.

**Keterbatasan diterima (bukan KD baru — konsekuensi turunan KD-2 yang sudah ada):** riwayat tetap hilang kalau cluster di-reset total (`docker desktop --factory-reset` dsb, bukan cuma pod restart) — konsisten sifat lingkungan lokal yang sudah diterima KD-2 (`docs/keterbatasan-diterima.md`).

**Opsi yang Dipertimbangkan tapi Ditolak:** `emptyDir` — DITOLAK: melanggar KK1 secara langsung (bukan riwayat, cuma snapshot sesaat yang hilang tiap restart).

### 8. Flow Prefect yang dipoll: `milestone-2-5-batch-scoring` (satu-satunya)

**Keputusan:** Exporter memfilter Prefect Cloud REST API dengan nama flow persis `milestone-2-5-batch-scoring`.

**Kenapa:** Dikonfirmasi dari kode (`orchestration/flows/batch_scoring.py` baris 266) — satu-satunya flow, sudah diparameterisasi M2.9 untuk kedua `source_table` (`telco_customers_source` dan `telco_customers_synthetic`), jadi satu flow ini mencakup seluruh jalur batch scoring yang ada.

**Tidak ada alternatif dipertimbangkan** — forced by kondisi kode aktual (cuma ada satu flow terdaftar).

### 9. `orchestration/flows/batch_scoring.py` dan `src/churn_prediction/inference/registry.py` TIDAK disentuh

**Keputusan:** Exporter membaca status pipeline murni dari LUAR (Prefect REST API + query Postgres langsung) — tidak menambah instrumentasi apa pun ke dalam kode pipeline itu sendiri.

**Kenapa:** Konsisten prinsip "M3.5 murni observasional" — real-time API (M3.2/3.4) sudah menetapkan pola yang sama (membaca `registry.py` tanpa mengubahnya). Mengubah kode pipeline batch demi kebutuhan monitoring akan mencampur concern yang seharusnya terpisah (M2.5 milik Orang #2, M3.5 milik Orang #3).

**Tidak ada alternatif dipertimbangkan** — forced by prinsip arsitektur "satu sumber kebenaran" dan pembagian kepemilikan pekerjaan (Bagian 4 dokumen arsitektur).

### 10. "Status refresh feature store" gugur dari scope (forced M2.2)

**Keputusan:** Salah satu dari 3 sinyal pipeline health yang diminta teks sumber M3.5 ("status DAG, status refresh feature store, status tulis-balik ke PostgreSQL") — "status refresh feature store" — TIDAK diimplementasikan.

**Kenapa:** M2.2 (`milestones/2.2-klasifikasi-fitur-feature-store/decisions.md`) sudah final: seluruh 29 fitur model berklasifikasi INSTANT, TIDAK ada feature store PostgreSQL yang dibangun. Tidak ada job refresh untuk dipantau statusnya — bukan diabaikan diam-diam, tapi konsekuensi langsung keputusan M2.2 yang sudah final sebelum M3.5 dimulai.

**Tidak ada alternatif dipertimbangkan** — forced by keputusan M2.2 yang sudah final.

## Bug Ditemukan+Diperbaiki: Kubernetes Docker-links env var collision

**Ditemukan saat:** Checkpoint 3, verifikasi deploy `pipeline-health-exporter` ke K8s — pod `CrashLoopBackOff`.

**Root cause:** Kubernetes otomatis inject environment variable Docker-links-style ke SETIAP pod di namespace yang sama, berdasar nama tiap Service yang sudah ada (pola `<SERVICE_NAME>_PORT=tcp://<cluster-ip>:<port>`, huruf besar underscore). Service exporter ini bernama `pipeline-health-exporter` (expose port 9100) → Kubernetes inject `PIPELINE_HEALTH_EXPORTER_PORT=tcp://10.110.140.133:9100` — string ini BENTROK PERSIS dengan nama environment variable yang dipilih sendiri untuk port listen HTTP exporter (`PIPELINE_HEALTH_EXPORTER_PORT`, dimaksudkan sebagai integer `9100`). `int(os.environ.get(...))` gagal parsing string `tcp://...`, exception di level modul (sebelum `try/except` mana pun sempat jalan), container exit segera setelah start.

**Fix:** Rename variabel jadi `EXPORTER_HTTP_PORT` — nama yang tidak menyerupai pola `<service-name>_PORT` mana pun di namespace `monitoring`.

**Verifikasi:** Setelah rename + rebuild image + `kubectl rollout restart`, pod `Running 1/1`, `/metrics` menyajikan seluruh gauge dengan nilai yang cocok persis hasil verifikasi manual sebelumnya (status=1.0/Completed, durasi=4.272673s).

**Opsi yang Dipertimbangkan tapi Ditolak:** Set eksplisit `EXPORTER_HTTP_PORT`/`PIPELINE_HEALTH_EXPORTER_PORT` sebagai env var literal di Deployment manifest (menimpa nilai yang di-inject Kubernetes) — DITOLAK: rename lebih robust dan tidak bergantung urutan precedence env var (Kubernetes tidak menjamin container-defined env selalu menang atas Service-injected env dalam semua kasus), serta menghindari kebingungan pembaca kode di masa depan yang melihat nama variabel menyerupai pola auto-inject.

**Relevan untuk milestone masa depan:** Pola ini akan berulang untuk exporter/service K8s BARU apa pun — hindari nama environment variable yang menyerupai `<NAMA-SERVICE-DALAM-HURUF-BESAR>_PORT`/`_SERVICE_HOST`/`_SERVICE_PORT`.
