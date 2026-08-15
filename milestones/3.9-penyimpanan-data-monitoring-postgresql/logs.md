# Logs — Milestone 3.9: Penyimpanan Data Monitoring di PostgreSQL

## Checkpoint 1 — Skema PostgreSQL: Tabel Generik + 2 Role Baru

`infra/sql/3.9_monitoring_metrics_schema.sql` ditulis — `CREATE SCHEMA monitoring` (belum pernah ada skema miliknya sendiri sebelumnya, walau nama role `monitoring_reader` M3.5 sudah menyinggungnya), tabel `monitoring.metrics_snapshot` (`id`, `metric_name`, `value` double precision, `labels` jsonb, `computed_at`), index `(metric_name, computed_at DESC)`. Role `monitoring_metrics_writer` (INSERT+SELECT, dipakai `metrics_aggregator.py` Checkpoint 2-3) dan `monitoring_metrics_reader` (SELECT-only, dipakai datasource Grafana Checkpoint 5) ditambahkan ke file SQL yang sama.

Dijalankan terhadap Supabase sungguhan lewat skrip scratchpad `psycopg2` (pola sama M2.1/M2.4/M3.5/M3.6) — password 2 role di-generate random (`secrets.token_urlsafe`), substitusi placeholder `:'xxx_password'` di teks SQL sebelum `cur.execute()` (psycopg2 tidak paham sintaks variabel psql `:'var'`, substitusi dilakukan di sisi Python).

**Insiden kecil saat verifikasi**: percobaan pertama connect pakai role baru GAGAL (`FATAL: (ENOIDENTIFIER) no tenant identifier provided`) — asumsi awal format username pooler Supabase salah (`current_user` di sisi server cuma balikin nama role polos, BUKAN format `<role>.<project_ref>` yang dibutuhkan pooler saat CONNECT). Diperbaiki dengan membaca project ref langsung dari username `SUPABASE_DB_URL`/`DRIFT_WRITER_DB_URL` existing (`jabqxkitslnlqxiiarmb`) — pattern `<role>.<project_ref>` dikonfirmasi konsisten dengan seluruh role lain di proyek ini.

**Verifikasi scope lengkap (positif+negatif) terhadap Supabase sungguhan**:
- `monitoring_metrics_writer`: BISA INSERT+SELECT `monitoring.metrics_snapshot` (baris probe `_provision_probe_m39` ditulis+dibaca sukses); TERBUKTI DITOLAK (`InsufficientPrivilege`) untuk SELECT schema `quality` (sengaja dicoba sebagai representasi "tidak boleh baca schema lain manapun").
- `monitoring_metrics_reader`: BISA SELECT `monitoring.metrics_snapshot`; TERBUKTI DITOLAK (`InsufficientPrivilege`) untuk INSERT ke tabel yang sama.
- Baris probe dibersihkan (`DELETE`) setelah verifikasi via role admin.

Kredensial baru (`MONITORING_METRICS_WRITER_DB_URL`/`MONITORING_METRICS_READER_DB_URL`) ditambahkan ke `.env` — dicek dulu baris terakhir file berakhir newline (pelajaran insiden M3.5) sebelum append, aman.

**Selesai, commit:** `a2cf8fd` (feat).

## Checkpoint 2 — `metrics_aggregator.py`: Logika Inti + Test

`orchestration/monitoring/metrics_aggregator.py` ditulis — `METRIC_SPECS` (12 entri: 5 infra/API + 4 pipeline health + 3 drift, PromQL SENGAJA disalin PERSIS dari panel `grafana-dashboard-configmap.yaml` existing supaya perbandingan KK1 nanti apple-to-apple), `query_prometheus()` (HTTP GET `/api/v1/query`, parse `data.result[]`), `_filter_label_keys()` (sisakan hanya label relevan per spec, buang `instance`/`job` bawaan Prometheus), `write_snapshot_rows()` (INSERT batch ke `monitoring.metrics_snapshot`, `computed_at` default DB-side supaya seluruh baris satu siklus dapat timestamp konsisten), `refresh_once()` (iterasi `METRIC_SPECS`, isolasi try/except PER SPEC -- pola sama `pipeline_health_exporter.py`/`drift_exporter.py`), `run_forever()` (loop 60 detik, env var override).

Berbeda arsitektur dari 2 exporter existing: komponen ini MEMBACA dari Prometheus (client HTTP `requests`), BUKAN mengekspos `/metrics` untuk discrape -- arah data terbalik, konsisten Keputusan Desain #3 plan.

`tests/orchestration/test_metrics_aggregator.py` ditulis -- 12 test (parsing multi-series+single-value+empty-result+error-status Prometheus, filter label, INSERT batch benar, isolasi kegagalan per metric spec). **Seluruh 12 test PASS di percobaan pertama** (`pytest tests/orchestration/test_metrics_aggregator.py -v`, 0.65s).

Full suite dijalankan (`pytest --ignore=tests/api/test_app.py`, dikecualikan karena gap dependency lokal PRE-EXISTING TIDAK TERKAIT -- `prometheus_fastapi_instrumentator` terdeklarasi di `pyproject.toml` M3.5 tapi tidak terinstall di venv lokal saat ini, tidak disentuh milestone ini) -- **233 test PASS, 0 regresi**.

**Selesai, commit:** `f6d6d30` (feat).

## Checkpoint 3 — Docker Image + Deployment K8s

`requests` ternyata belum terdeklarasi eksplisit di `pyproject.toml` (baru terpakai transitif sejak Checkpoint 2) -- ditambahkan (`requests==2.34.2`, versi resolve venv lokal), konsisten prinsip "satu sumber kebenaran versi" M1.2.

`infra/docker/metrics-aggregator.Dockerfile` ditulis -- `python:3.13-slim`, HANYA `requests`+`sqlalchemy`+`psycopg2-binary` (TANPA `prometheus_client` -- komponen ini tidak expose `/metrics`). TIDAK ada `EXPOSE`/`PYTHONPATH` (tidak import `churn_prediction` sama sekali).

`docker build` sukses. **Ukuran final 244MB** -- dikonfirmasi jauh lebih kecil dari `drift-exporter:m3.6` (621MB) dan `pipeline-health-exporter:m3.5` (534MB), membuktikan klaim "paling lean" di antara 3 komponen monitoring.

`infra/k8s/monitoring/metrics-aggregator-deployment.yaml` -- Deployment SAJA (TANPA Service, pure background worker, tidak ada yang men-scrape/memanggil pod ini dari luar -- beda arsitektur dari 2 exporter existing). `envFrom: monitoring-secrets`.

Key `MONITORING_METRICS_WRITER_DB_URL` ditambahkan ke Secret `monitoring-secrets` (`kubectl patch`).

`kubectl apply` -- pod `Running` dalam hitungan detik. Log siklus pertama mengonfirmasi SEMUA 12 metric spec diproses: 5 metrik infra/API menulis 0 baris (WAJAR -- belum ada trafik `/predict` baru-baru ini dalam window `rate()` 5 menit, BUKAN error), `pipeline_flow_status`/`pipeline_flow_duration_seconds` 1 baris, `quality_gate_verdict` 5 baris, `predictions_staleness_seconds` 2 baris, `drift_psi`/`drift_pvalue`/`drift_verdict` **30 baris masing-masing** (BUKAN 29 seperti dugaan awal -- diinvestigasi via query Prometheus langsung, ternyata BENAR: 29 fitur input + 1 `churn_probability` output prediksi, sesuai desain M3.6 sendiri yang memang memantau distribusi OUTPUT juga, bukan cuma input -- bukan anomali).

Diverifikasi lewat role `monitoring_metrics_reader` LANGSUNG (bukan admin) -- siklus pertama: 99 baris, 7 metric_name (5 infra/API kosong tidak masuk hitungan). Ditunggu >1 menit, dicek ulang: 297 baris, 21 distinct `computed_at` (= 3 siklus x 7 metric_name aktif) -- membuktikan loop `run_forever()` BENAR terus berjalan konsisten ~60 detik, bukan one-shot.

**Selesai, commit:** `1cd6e9c` (feat).

## Checkpoint 4 — Verifikasi KK1+KK3 (Agregasi Benar, Tanpa Celah Waktu)

Trafik nyata digenerate ke `/predict` (skrip scratchpad, reuse pola `scripts/api_parity_check.py` -- fetch baris asli `telco_customers_source`, bangun payload via `RAW_PASCAL_TO_SNAKE`) -- **20 request valid + 5 invalid (payload kosong)** terkirim sukses.

**Verifikasi KK1**: ditunggu 1 siklus poll (~65 detik) supaya trafik baru terekam Prometheus, lalu 3 metrik representatif (1 per pilar) dibandingkan LANGSUNG -- Postgres (`monitoring_metrics_reader`, baris terbaru) vs Prometheus (`time=` PERSIS `computed_at` baris Postgres, PromQL identik `METRIC_SPECS`):
- `api_latency_p95_seconds`: Postgres `0.095` vs Prometheus `0.095` -- **MATCH**.
- `quality_gate_verdict` (`source_table=telco_customers_synthetic`): Postgres `2.0` vs Prometheus `2.0` -- **MATCH**.
- `drift_psi` (`feature_name=tenure`): Postgres `0.0248433684374498` vs Prometheus `0.0248433684374498` -- **MATCH exact** (floating point identik, bukan cuma toleransi).

**Verifikasi KK3**: diamati ~13,4 menit (804 detik) berjalan -- 13 siklus tercatat (`count(DISTINCT computed_at)` utk `drift_psi`). Analisis gap (`LAG() OVER (ORDER BY computed_at)`): 377 gap "0" (antar-baris DALAM satu siklus yang sama -- 30 fitur ditulis via satu batch INSERT, `now()` DB-side hampir identik, WAJAR bukan anomali), 12 gap ANTAR-siklus konsisten **65,9-68,2 detik** (nominal 60 detik + overhead query 12 metric spec ke Prometheus + tulis Postgres, ~6-8 detik -- WAJAR, bukan celah). TIDAK ADA outlier/lompatan besar (mis. beberapa menit) yang mengindikasikan siklus terlewat.

**Selesai** -- tidak ada file berubah (murni verifikasi), digabung commit Checkpoint 5.

## Checkpoint 5 — Grafana Datasource PostgreSQL Baru

4 key kredensial (`GRAFANA_POSTGRES_MONITORING_HOST`/`_DATABASE`/`_USER`/`_PASSWORD`, role `monitoring_metrics_reader`) ditambahkan ke Secret `monitoring-secrets`.

`grafana-datasource-configmap.yaml` di-extend (file yang sama dgn M3.5, bukan file baru) -- datasource kedua `type: postgres`, `uid: postgres-monitoring`, `url`/`database`/`user`/`secureJsonData.password` via `$__env{}` (pola sama alerting M3.7), `jsonData.sslmode: require` (Supabase mewajibkan SSL).

`kubectl apply` + restart Grafana -- pod ready dalam hitungan detik. `$__env{}` DIKONFIRMASI ter-expand benar via `/api/datasources` (url/user/database nilai ASLI, bukan literal `$__env{...}}` -- verifikasi empiris, bukan asumsi, konsisten pola M3.7).

Test koneksi (`POST /api/datasources/2/health`): `{"message":"Database Connection OK","status":"OK"}`. Query manual lewat `/api/ds/query` (`SELECT count(*) FROM monitoring.metrics_snapshot`) BERHASIL, mengembalikan `1545` (jumlah baris terkini, konsisten pertumbuhan data sejak Checkpoint 3-4).

**Selesai, commit:** `1097945` (feat).

## Checkpoint 6 — Migrasi Panel Dashboard: Real-Time API (Pilar Infra)

3 panel row "Real-Time API -- Infra" dimigrasi dari Prometheus ke `postgres-monitoring`: "Request Rate /predict (per status)" (SQL `labels->>'status' AS metric`, format `time_series`), "Latency p50/p95/p99" (SQL `CASE metric_name ... END AS metric` supaya legend tetap "p50"/"p95"/"p99", bukan nama metric_name mentah), "Error Rate /predict (5m)" (SQL `ORDER BY computed_at DESC LIMIT 1`, format `table`).

`kubectl apply` + restart Grafana. Trafik segar digenerate lagi (20 valid + 5 invalid) supaya ada data pembanding, ditunggu 1 siklus poll (~65 detik).

**Verifikasi KK2** (query panel PERSIS via `/api/ds/query` dgn SQL yang sama persis ada di panel, dibandingkan query Prometheus live pada saat bersamaan):
- Error Rate: Postgres `20` vs Prometheus `20.0` -- **MATCH**.
- Latency: Postgres `{p50: 0.0520833333333333, p95: 0.0989583333333333, p99: 1}` vs Prometheus live `p50=0.05208333333333334, p95=0.09895833333333331, p99=1.0` -- **MATCH** (p99=1.0 konsisten kedua sumber, kemungkinan batas bucket histogram default instrumentator, bukan anomali).
- Request Rate per status: Postgres `{2xx: 0.0701929252550635, 4xx: 0.0175482313137659}` vs Prometheus `{2xx: 0.07019292525506354, 4xx: 0.017548231313765886}` -- **MATCH** (presisi floating-point identik).

**Verifikasi tambahan (mitigasi risiko plan)**: `/api/v1/provisioning/alert-rules` dicek ulang -- ketiga rule (`DriftThresholdExceeded`/`PipelineBatchFailed`/`QualityGateStop`, M3.7/M3.8) MASIH mengacu `datasourceUid: prometheus` di refId A, TIDAK ikut berubah oleh migrasi panel dashboard (file berbeda, `grafana-alerting-configmap.yaml` vs `grafana-dashboard-configmap.yaml`, sesuai desain).

**Selesai, commit:** `8e88735` (feat).

## Checkpoint 7 — Migrasi Panel Dashboard: Pipeline Batch Health

4 panel row "Pipeline Batch Health" dimigrasi: "Status Run Terakhir"/"Durasi Run Terakhir" (SQL `labels->>'flow_name' = '...'`, `ORDER BY computed_at DESC LIMIT 1`, format `table`), "Verdict Gerbang Kualitas Data Terakhir"/"Staleness Tulis-Balik" (SQL `DISTINCT ON (labels->>'source_table')` -- baris terbaru per source_table, pola sama `DISTINCT ON` yang sudah dipakai `pipeline_health_exporter.py`/`baseline.py` sejak M2.4/M3.5).

`kubectl apply` + restart Grafana.

**Verifikasi KK2**: keempat panel dibandingkan Postgres vs Prometheus live --
- Status Run Terakhir: `1` vs `1.0` -- **MATCH**.
- Durasi Run Terakhir: `4.000845` vs `4.000845` -- **MATCH exact**.
- Verdict Gerbang Kualitas: SEMUA 5 source_table (`_provision_probe`/`_test_gate_70a3b9f7`/`_verification_probe_m38`/`telco_customers_source`/`telco_customers_synthetic`) cocok `2` vs `2.0` -- **MATCH** (`_test_gate_70a3b9f7` artefak probe baru yang tidak dikenali sesi ini, di luar cakupan M3.9, dicatat sebagai observasi bukan gap).
- Staleness Tulis-Balik: `telco_customers_source` `3703.29` (Postgres) vs `3771.32` (Prometheus live) -- selisih ~68 detik, `telco_customers_synthetic` `169781.93` vs `169849.95` -- selisih ~68 detik juga. **Selisih KONSISTEN dgn 1 siklus poll berlalu** (metrik ini terus bertambah seiring waktu -- `now() - max(predicted_at)` -- baris Postgres adalah snapshot BEBERAPA DETIK lebih lama dari query Prometheus live yang dijalankan setelahnya, BUKAN mismatch/bug).

**Selesai, commit:** `d8b4276` (feat).

## Checkpoint 8 — Migrasi Panel Dashboard: Drift dan Kualitas Model

3 panel row "Data & Model Drift" dimigrasi -- panel TERAKHIR, sekaligus PALING KOMPLEKS (per risiko yang diantisipasi plan). "Jumlah Fitur Verdict STOP/FLAG" (SQL `count(*)` atas subquery `DISTINCT ON` baris terbaru per fitur difilter `value=0`/`value=1` -- lebih SEDERHANA dari PromQL asli, `count(*)` alami balikin 0 untuk set kosong, tidak perlu trik `OR on() vector(0)`). "PSI+p-value+Verdict per Fitur" (SQL 3-way JOIN atas 3 subquery `DISTINCT ON` per `metric_name`+`feature_name` -- teknik yang berhasil di percobaan PERTAMA, tidak perlu iterasi teknik alternatif seperti diantisipasi risiko plan).

`kubectl apply` + restart Grafana.

**Verifikasi KK2 -- SELURUH 30 baris (29 fitur input + `churn_probability` output), BUKAN sampel** (checkpoint terakhir, verifikasi paling ketat sesuai plan):
- Jumlah Fitur STOP: Postgres `2` vs Prometheus `2` -- **MATCH**.
- Jumlah Fitur FLAG: Postgres `2` vs Prometheus `2` -- **MATCH**.
- Tabel PSI+p-value+Verdict: **SEMUA 30 baris cocok PERSIS** (psi/p_value/verdict, toleransi `1e-9`) -- tidak ada satu pun mismatch, tidak ada baris hilang di kedua arah (Postgres->Prometheus dan Prometheus->Postgres dicek).

**Audit menyeluruh dashboard** (setelah SELURUH 8 checkpoint migrasi selesai): `/api/dashboards/uid/churn-monitoring-m35` dicek panel-per-panel -- seluruh **10 panel data** (di luar 3 row header yang memang tidak punya datasource) sudah `datasource.type: postgres`, **0 panel tersisa di Prometheus**. Migrasi dashboard 100% tuntas.

**Selesai, commit:** (menyusul).
