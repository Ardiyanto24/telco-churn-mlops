# Logs — Milestone 3.5: Monitoring Infra dan Pipeline Health

## Checkpoint 1 — Instrumentasi Metrik Infra API

Ditambah `prometheus-fastapi-instrumentator==8.1.0` ke `pyproject.toml`, wiring `Instrumentator().instrument(app).expose(app, endpoint="/metrics")` di `src/churn_prediction/api/app.py` (module scope, sebelum `lifespan` menerima trafik).

**Test tertulis lalu ditemukan flaky di suite penuh:** `test_metrics_reflects_real_request_counts_by_status_code` awalnya menegaskan nilai ABSOLUT counter (mis. `status="2xx"} 1.0`) — lolos saat dijalankan sendirian, GAGAL saat dijalankan bersama test lain di `tests/api/test_app.py` (180 passed, 1 failed di run penuh `pytest tests/ -q -m "not integration"`). Penyebab: `prometheus_client.REGISTRY` bersifat GLOBAL sepanjang proses pytest — test lain di file yang sama (mis. `test_predict_invalid_request_rejected_422_before_model_called`, dipanggil 5x parametrize) ikut menaikkan counter `/predict` status `4xx` sebelum test ini jalan. Diperbaiki: assertion diganti jadi DELTA (`REGISTRY.get_sample_value(...)` sebelum vs sesudah), robust terhadap urutan eksekusi test. Re-run penuh: **171 passed, 0 failed** (144.26s).

Build image `churn-inference:m3.5`, verifikasi lokal (`docker run`, curl `/metrics` setelah 3 request valid + 2 invalid) — histogram/counter cocok PERSIS: `status="2xx"} 3.0`, `status="4xx"} 2.0`, `http_request_duration_seconds_count{handler="/predict"} 5.0`.

**Selesai, commit:** `fbea039` (feat).

## Checkpoint 2 — Exporter Status Pipeline Batch

`infra/sql/3.5_monitoring_reader_role.sql` dijalankan lewat `psycopg2` (skrip scratchpad, pola sama M2.1/M2.4) terhadap Supabase sungguhan. **Insiden kecil ditemukan+diperbaiki SEGERA**: perintah `echo ... >> .env` pertama menempel tanpa newline ke baris terakhir file (`GITHUB_REPOSITORY_DISPATCH_PAT` tidak diakhiri `\n`), menghasilkan `.env` korup (nilai `MONITORING_READER_DB_URL` menyambung ke nilai PAT GitHub, mengubah keduanya jadi satu string tidak valid). Terdeteksi langsung (dibaca ulang isi `.env`), diperbaiki dengan menulis ulang kedua baris terpisah + newline eksplisit. Diverifikasi ulang lewat `python-dotenv`: `GITHUB_REPOSITORY_DISPATCH_PAT` panjang 93 karakter, tidak mengandung `"MONITORING"`, seluruh 7 kredensial existing lain tetap terbaca. Tidak ada dampak ke sistem produksi (murni file lokal, gitignored, belum pernah dipakai proses lain di jendela waktu ini).

**Verifikasi role nyata** (skrip scratchpad terhadap Supabase): `monitoring_reader` BISA `SELECT` `quality.gate_run_history` (20 baris) dan `predictions.batch_predictions` (1.194.488 baris); TERBUKTI DITOLAK `InsufficientPrivilege` untuk `INSERT quality.gate_run_history`, `SELECT public.telco_customers_source`, dan `SELECT` schema `mlflow`.

**Eksplorasi API Prefect** (belum pernah dipakai proyek ini): `prefect.client.orchestration.get_client()` async, `client.read_flow_runs(flow_filter=FlowFilter(name=FlowFilterName(any_=[...])), sort=FlowRunSort.END_TIME_DESC, limit=1)` — percobaan pertama pakai `FlowRunFilter(flow_id=...)` GAGAL (`extra_forbidden`, field itu tidak ada di skema `FlowRunFilter` versi ini); diperbaiki dengan filter langsung lewat parameter `flow_filter` pada `read_flow_runs()` (satu panggilan API, bukan dua). Diverifikasi nyata terhadap Prefect Cloud: run terakhir `milestone-2-5-batch-scoring` = `COMPLETED`, durasi 4.272673s.

`orchestration/monitoring/pipeline_health_exporter.py` ditulis: `get_latest_flow_run()` (async, Prefect), `get_quality_gate_status()`/`get_write_staleness()` (sync, SQL langsung, `GROUP BY source_table` dinamis), `refresh_once()` (wiring gauge, try/except terisolasi per sinyal), `run_forever()` (loop + `start_http_server`). Dijalankan langsung terhadap DB nyata sebelum test ditulis: `get_quality_gate_status()` mengembalikan `{'_provision_probe': 'pass', 'telco_customers_synthetic': 'pass'}` — `_provision_probe` adalah baris riwayat dari verifikasi milestone lampau (bukan source_table produksi nyata), dicatat sebagai observasi, TIDAK mempengaruhi desain (query dinamis menangani apa pun yang ada di tabel, bukan hardcode daftar tabel).

9 unit test ditulis (`tests/orchestration/test_pipeline_health_exporter.py`), mock Prefect client + mock DB engine — **9 passed**.

Image `pipeline-health-exporter:m3.5` dibuild (`infra/docker/exporter.Dockerfile`, install 4 dependency langsung tanpa `pip install` package `churn_prediction`) — **534MB vs churn-inference 1.63GB** (~3x lebih kecil). `docker run` lokal + curl `/metrics`: nilai custom metric cocok PERSIS hasil verifikasi manual sebelumnya.

**Selesai, commit:** `c319ff7` (feat).

## Checkpoint 3 — Deploy Prometheus + Exporter ke Kubernetes

Namespace `monitoring` dibuat. `infra/k8s/monitoring/prometheus-{configmap,pvc,deployment,service}.yaml` di-apply — pod `Running`, PVC `Bound` (StorageClass `hostpath`), config Prometheus ter-parsing tanpa error (`fsGroup: 65534` diset preventif untuk PVC hostpath default `root:root`, terbukti perlu — tanpa ini Prometheus akan gagal tulis TSDB).

Secret `monitoring-secrets` dibuat manual (`kubectl create secret generic`, nilai dibaca dari `.env` via `python-dotenv` lalu di-passing langsung ke `subprocess` — TIDAK ditulis ke file plaintext perantara).

**Bug ditemukan+diperbaiki (signifikan)**: `pipeline-health-exporter` deployment pertama `CrashLoopBackOff` (`RESTARTS: 1` dalam <20 detik). `kubectl logs --previous` mengungkap `ValueError: invalid literal for int() with base 10: 'tcp://10.110.140.133:9100'` saat parsing `PIPELINE_HEALTH_EXPORTER_PORT`. Root cause: Kubernetes otomatis inject env var Docker-links-style dari nama Service (`pipeline-health-exporter` → `PIPELINE_HEALTH_EXPORTER_PORT=tcp://...`) ke SETIAP pod di namespace yang sama — bentrok PERSIS dengan nama variabel yang dipilih sendiri untuk port listen HTTP exporter. Diperbaiki: rename ke `EXPORTER_HTTP_PORT` (lihat `decisions.md`). Setelah rebuild image + `kubectl rollout restart`: pod `Running 1/1`, 0 restart.

**Catatan verifikasi (bukan bug, transient)**: percobaan `curl` pertama ke exporter via `kubectl port-forward` sempat "Connection refused" meski `kubectl exec ... cat /proc/net/tcp` mengonfirmasi proses SUDAH listen di port 9100 (state `0A`=LISTEN, address `00000000:238C`=`0.0.0.0:9100`) — ternyata race dari proses `kubectl port-forward` lama yang masih menggantung di background dari percobaan sebelumnya. Diperbaiki: `pkill -f port-forward` sebelum retry, langsung berhasil.

Image `churn-api` di-bump ke `churn-inference:m3.5` di `infra/k8s/deployment.yaml`, `kubectl apply` + `rollout status` sukses. Parity diverifikasi ulang (`scripts/api_parity_check.py --api-url http://localhost --limit 20`): `churn_probability allclose(rtol=1e-6): True (diff maksimum: 4.44e-16)`, `churn_label`/`model_version` exact match — KK1+KK4 M3.2 tetap terjaga di image baru.

Trafik campuran nyata digenerate (15 valid + 5 invalid) ke `churn-api` via Service K8s. Prometheus `/api/v1/targets`: ketiga target (`churn-api`, `pipeline-health-exporter`, `prometheus` self-scrape) `health: up`. PromQL nyata: `sum(increase(http_requests_total{handler="/predict"}[10m])) by (status)` — nilai `2xx`/`4xx` awalnya tidak lengkap muncul karena timing scrape (`scrape_interval: 15s`, query dijalankan sebelum siklus scrape berikutnya) — diperbaiki dengan menunggu 16 detik lalu query counter RAW (bukan `increase()`) langsung: `2xx=35` (15 manual + 20 dari `api_parity_check.py` sebelumnya), `4xx=5` — cocok PERSIS trafik yang digenerate.

**Selesai, commit:** `a252404` (feat).

## Checkpoint 4 — Deploy Grafana, Verifikasi KK End-to-End, Penutupan

`infra/k8s/monitoring/grafana-datasource-configmap.yaml` (Prometheus, `uid: prometheus` eksplisit supaya dashboard bisa referensi tetap) + `grafana-dashboard-configmap.yaml` (2 ConfigMap: provider + dashboard JSON 9 panel) ditulis, nama metric disamakan PERSIS dengan yang sudah terverifikasi Checkpoint 3.

Secret `monitoring-secrets` di-patch (`kubectl patch --type=json`) menambah key `GF_SECURITY_ADMIN_PASSWORD` tanpa menghapus 3 key existing. `infra/k8s/monitoring/grafana-{deployment,service}.yaml` di-apply — pod `Running`, Service `LoadBalancer` auto-map ke `localhost:3000` (pola sama `churn-api` M3.3).

Verifikasi via `curl -u admin:... http://localhost:3000/api/...`: `/api/health` OK, `/api/datasources` menunjukkan datasource `Prometheus` ter-provision (`uid: prometheus`, `isDefault: true`), `/api/search` menunjukkan dashboard `churn-monitoring-m35` ter-provision, `/api/dashboards/uid/churn-monitoring-m35` mengonfirmasi seluruh 9 panel termuat.

Trafik tambahan digenerate (25 valid + 8 invalid) untuk memastikan dashboard punya data segar yang cukup untuk `histogram_quantile`. PromQL langsung: p95 latency `/predict` = `0.098s`, error rate = `24.24%` (8/33 request terbaru).

**Verifikasi visual KK1+KK2 (browser sungguhan, login admin)**: dashboard dibuka di `http://localhost:3000/d/churn-monitoring-m35` — screenshot mengonfirmasi panel "Request Rate /predict" (garis 2xx hijau, 4xx kuning), "Latency p50/p95/p99" (garis naik sesuai skala waktu), "Error Rate /predict (5m)" menampilkan **24.2%** (cocok PERSIS PromQL manual). Scroll ke bagian "Pipeline Batch Health": stat panel "Status Run Terakhir" menampilkan **"Completed"** (value mapping numerik→teks bekerja, 1.0→"Completed" hijau), "Durasi Run Terakhir" menampilkan **"4.27 s"**. Dua panel table (verdict gerbang kualitas, staleness tulis-balik) dikonfirmasi lewat query langsung ke Grafana datasource proxy (`/api/datasources/proxy/uid/prometheus/api/v1/query`, jalur query PERSIS yang dipakai panel table) — `quality_gate_last_verdict` mengembalikan 2 seri (`_provision_probe`, `telco_customers_synthetic`, keduanya verdict `pass`/nilai `2`), `predictions_last_write_age_seconds` mengembalikan 2 seri (`telco_customers_source`≈78310s, `telco_customers_synthetic`≈75158s) — seluruhnya cocok data nyata Postgres.

**KK1 M3.5 TERPENUHI**: p95 latency dan error rate terjawab dari dashboard tanpa query manual ke log mentah.
**KK2 M3.5 TERPENUHI**: status+durasi run batch terakhir terlihat di dashboard yang sama tanpa membuka Prefect Cloud UI.

**Selesai, commit:** `1e16a91` (feat), lalu commit dokumentasi penutupan (`decisions.md`/`logs.md`/`report.md`) di commit terpisah.
