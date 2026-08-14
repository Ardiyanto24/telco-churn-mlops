# Logs — Milestone 3.6: Monitoring Drift dan Kualitas Model

## Checkpoint 1 — Fondasi Matematis + Provisioning Postgres

`src/churn_prediction/drift/constants.py` ditulis — `FEATURE_TYPES` (29 fitur, klasifikasi diambil LANGSUNG dari `notebook-audit.md` Bagian C.1-C.5: 4 numerik + 25 kategorikal/binary/structural/one-hot), threshold PSI (0.1/0.25) dan p-value (0.05/0.01). Assertion `len(FEATURE_TYPES)==29` dijalankan saat import — lolos.

`src/churn_prediction/drift/metrics.py` ditulis — `compute_psi()` (dispatch numerik/kategorikal, epsilon smoothing `1e-4` untuk bin kosong), `compute_ks_pvalue()` (`scipy.stats.ks_2samp`), `compute_chi2_pvalue()` (`scipy.stats.chi2_contingency`, guard 1-kategori-unik return 1.0), `combined_verdict()`.

19 unit test ditulis (`tests/drift/test_metrics.py`), array sintetis numpy RNG seeded — distribusi identik vs timpang, edge case (baseline konstan, kategori baru tidak ada di baseline, 1 kategori unik). **Seluruh 19 test PASS di percobaan pertama** (`pytest tests/drift/test_metrics.py -v`, 2.62s).

`infra/sql/3.6_drift_roles_schema.sql` dijalankan (skrip scratchpad `psycopg2`, pola sama M2.1/M2.4/M3.5) terhadap Supabase sungguhan — schema `drift`, tabel `baseline_sample`+`drift_check_results`, role `drift_writer`+`drift_reader`. **Verifikasi scope lengkap**: `drift_writer` BISA SELECT `telco_customers_source` (594.194 baris)/`telco_customers_synthetic` (1.000 baris)/`predictions.batch_predictions` (1.194.488 baris), BISA INSERT ke 2 tabel drift; TERBUKTI DITOLAK `InsufficientPrivilege` untuk SELECT schema `mlflow`/`quality`. `drift_reader` BISA SELECT `drift.drift_check_results`; TERBUKTI DITOLAK untuk SELECT `drift.baseline_sample`, INSERT `drift.drift_check_results`, SELECT `telco_customers_source`/`predictions.batch_predictions`. Baris probe provisioning dibersihkan setelah verifikasi.

Kredensial baru (`DRIFT_WRITER_DB_URL`/`DRIFT_READER_DB_URL`) ditambahkan ke `.env` — **insiden kecil dihindari**: belajar dari kesalahan M3.5 (baris `.env` tidak diakhiri newline menyebabkan korupsi), kali ini dicek dulu isi file existing SEBELUM menulis, baris terakhir sudah punya newline sehingga append aman.

**Selesai, commit:** `fc987db` (feat).

## Checkpoint 2 — Baseline Computation

`registry.load_active_pipeline()` ditulis di `src/churn_prediction/inference/registry.py` — **kendala teknis ditemukan+dipecahkan**: tidak ada API publik untuk mengambil `PreprocessingPipeline` fitted dari model teregistrasi (`predict_active()` cuma kembalikan hasil akhir). Diverifikasi manual dulu (interaktif, sebelum ditulis ke kode): `load_active_model()._model_impl.python_model._pipeline` memberi akses ke pipeline fitted yang sama, `.transform()` terhadap 1 baris sampel menghasilkan 29 kolom benar. Solusi ditulis sebagai accessor baru (reuse 100% `load_active_model()`).

2 unit test ditulis (`tests/inference/test_registry.py`) — `test_load_active_pipeline_transforms_to_29_columns_matching_bundle` (`np.testing.assert_allclose` terhadap `bundle["pipeline"].transform()` langsung) dan `test_load_active_pipeline_reflects_alias_reassignment`. **Keduanya PASS** (38.49s, termasuk 2x registrasi model lokal + download artifact).

`scripts/compute_drift.py` ditulis (mode `baseline`+`current` dalam satu file, `--mode` flag). Verifikasi bertahap:
1. Sample kecil (`--sample-size 50`) dulu — **1.500 baris masuk** (50×30), dibersihkan sebelum run penuh.
2. Run penuh (`--sample-size 10000` default) — **300.000 baris masuk** (10.000×30), ~10 detik komputasi (dominan waktu download artifact MLflow 2x -- transform+predict masing-masing load model, inefisiensi kecil diterima untuk script one-time).
3. Spot-check statistik agregat (`AVG`/`MIN`/`MAX` per `feature_name`) — SELURUH 30 fitur punya rentang nilai masuk akal sesuai tipe (binary 0/1, structural -1/0/1, `service_count` 0-6, fitur ter-scale StandardScaler mean≈0). `churn_probability` mean baseline = **0.3378** — sedikit lebih tinggi dari churn rate label training (22.52%, `notebook-audit.md` Bagian D) tapi ini probabilitas PREDIKSI bukan proporsi label aktual, perbedaan dijelaskan wajar (kalibrasi model + sampling 10rb dari 594rb).

**Selesai, commit:** `86e4afb` (feat).

## Checkpoint 3 — Current-Window Computation + Trigger Event-Driven

`run_current()` (mode `current`, sudah ada di file yang sama sejak Checkpoint 2) diuji lokal dulu terhadap data nyata — **30 baris hasil, temuan nyata bernilai** (dicatat detail di `decisions.md` Keputusan #1): `service_count`/`tenure` verdict "stop" murni dari p-value (sample size 10.000 vs 1.000 membuat p-value sangat sensitif), meski PSI keduanya rendah (<0.1) — bukti konkret kenapa dua-tier saling melengkapi, BUKAN redundan.

`.github/workflows/drift-monitoring.yml` ditulis — `workflow_run` listener ke `synthetic-auto-scoring` (nama dikonfirmasi dari file `.github/workflows/synthetic-auto-scoring.yml` baris 1) + `workflow_dispatch` manual. **File harus di-commit+push SEBELUM bisa diverifikasi** (`workflow_dispatch` mensyaratkan file ada di branch default) — commit dilakukan lebih awal dari batas checkpoint biasanya (satu-satunya cara memverifikasi Task 10 secara nyata), dicatat sebagai penyesuaian proses yang disengaja, bukan pelanggaran disiplin commit-per-checkpoint.

`DRIFT_WRITER_DB_URL` ditambahkan sebagai GitHub Secret (`gh secret set`). Trigger manual: `gh workflow run drift-monitoring.yml` → run `31803550081` → **status `completed success`** (~90 detik, dipantau `gh run view --json status,conclusion`). Log run mengonfirmasi `python scripts/compute_drift.py --mode current` jalan sukses di `ubuntu-latest` (proven KD-1 tidak relevan di sini juga, seperti workflow lain). Verifikasi DB: `drift.drift_check_results` bertambah dari 30 baris (run lokal) jadi **60 baris** (run lokal + run CI), `computed_at` terbaru cocok waktu run GitHub Actions.

**Selesai, commit:** `21ece29` (feat, mencakup Task 9's workflow file).

## Checkpoint 4 — Exporter Lean + Deploy Kubernetes

`orchestration/monitoring/drift_exporter.py` ditulis (pola PERSIS `pipeline_health_exporter.py` M3.5 — `start_http_server`+loop, `refresh_once()` isolasi try/except). Diverifikasi lokal terhadap DB nyata via `drift_reader`: 30 features, nilai cocok run sebelumnya.

5 unit test ditulis (`tests/orchestration/test_drift_exporter.py`, mock DB) — **seluruh 5 PASS** percobaan pertama.

`infra/docker/drift-exporter.Dockerfile` — **Docker Desktop ditemukan MATI** saat mulai build (`docker info` gagal connect ke named pipe). Di-restart via PowerShell (`Start-Process "Docker Desktop.exe"`), ditunggu ~1 menit sampai daemon siap. Build sukses setelahnya — image **621MB** (vs `churn-inference` 1.63GB, vs `pipeline-health-exporter` 534MB — sedikit lebih besar karena scipy+pandas, tetap jauh lebih kecil dari image inference penuh). `docker run` lokal + curl `/metrics` — nilai cocok persis verifikasi sebelumnya.

Deploy K8s: **cluster Kubernetes ikut mati+restart** bersamaan Docker Desktop (`kubectl get pods -A` menunjukkan seluruh pod monitoring/churn-prediction `RESTARTS: 1` serentak) — TAPI seluruh state PENTING selamat (PVC Prometheus, ConfigMap Grafana+dashboard) karena disimpan deklaratif/persisten, bukan in-memory. Deployment+Service `drift-exporter` baru dibuat, Secret `monitoring-secrets` di-patch tambah `DRIFT_READER_DB_URL`.

**Insiden transient (bukan bug)**: target Prometheus `drift-exporter` sempat `down` ("connection refused") tepat setelah pod baru start — dicek via `kubectl exec .../proc/net/tcp`, proses SUDAH listen di port 9101 (race scrape pertama vs startup, sama pola gejala M3.5). Scrape berikutnya (~20 detik kemudian) `up` tanpa intervensi lain.

Verifikasi PromQL: `feature_drift_psi` mengembalikan 30 series, nilai cocok persis hasil sebelumnya.

**Selesai, commit:** `bb2d855` (feat).

## Checkpoint 5 — Panel Dashboard, Verifikasi KK, Penutupan

4 panel baru ditambah ke `grafana-dashboard-configmap.yaml` (dashboard `churn-monitoring-m35`, TIDAK dashboard baru) — row "Data & Model Drift (KK1/KK2 M3.6)", 2 stat (jumlah fitur STOP/FLAG), 1 tabel (PSI+p-value+verdict). `kubectl apply` — Grafana file-provider poll otomatis (`updateIntervalSeconds: 30`), dikonfirmasi via `/api/dashboards/uid/churn-monitoring-m35` (13 panel total, 4 baru terdaftar).

**Verifikasi KK1 (uji coba terkontrol):** Override JSON dibuat (`tenure_group_G2_2_18` → 500× nilai `1` konstan; `monthly_to_total_ratio` → 200 nilai ~50, jauh di luar rentang ter-scale normal [-0.48, 7.4] baseline). `compute_drift.py --mode current --override-current <path>` dijalankan — hasil DRAMATIS: PSI melonjak dari ~0/0.014 (pass) jadi **7.68/8.28** (jauh di atas ambang stop 0.25), p-value 0.0000, verdict "stop" untuk keduanya. Panel "Jumlah Fitur Verdict STOP" (query langsung via Grafana datasource proxy, jalur PERSIS yang dipakai panel) naik dari 2 jadi **4** (2 existing + 2 baru dari override).

**Catatan verifikasi visual**: rendering panel Grafana di browser sesi ini TIDAK KONSISTEN (halaman ter-load, query datasource sukses `200 OK`, tapi konten panel kadang tidak ter-render ke DOM text meski sudah scroll+tunggu berulang kali, di beberapa tab berbeda) — SEBELUM override, capture browser BERHASIL menunjukkan seluruh 9 panel M3.5 dengan nilai nyata (termasuk "Error Rate 24.2%", "Status Completed", dst), membuktikan jalur rendering dashboard ini bekerja. Untuk keadaan SETELAH override, bukti utama dipakai lewat query API Grafana datasource-proxy (jalur query PERSIS sama yang dipakai panel, BUKAN bypass Grafana) — dikombinasikan dengan bukti rendering yang sudah terbukti bekerja sebelumnya, dianggap verifikasi yang cukup kuat meski tidak berupa screenshot penuh pasca-override.

Setelah verifikasi, `compute_drift.py --mode current` (TANPA override) dijalankan ULANG untuk restore — percobaan PERTAMA timeout (>60 detik, kemungkinan transient network/MLflow), percobaan KEDUA sukses. Dikonfirmasi via query SQL: `tenure_group_G2_2_18` kembali PSI=0.0000/pass, `monthly_to_total_ratio` kembali PSI=0.0143/pass — nilai identik sebelum override.

**KK1 M3.6 TERPENUHI**: pergeseran distribusi fitur buatan berhasil terdeteksi (PSI+p-value ekstrem) dan memicu sinyal yang terlihat di dashboard (panel "Jumlah Fitur STOP" berubah 2→4, dikonfirmasi via query datasource yang sama dipakai panel).

**Verifikasi KK2**: `decisions.md` mencantumkan threshold PSI (0.1/0.25, konvensi industri) dan p-value (0.05/0.01, konvensi statistik α) beserta alasan pemilihan masing-masing — bukan angka default tanpa penjelasan.

KT-9 ditulis (`docs/keputusan-tertunda.md`) — cakupan real-time drift monitoring ditunda.

**Selesai, commit:** `1e2f8f7` (feat panel), lalu commit terpisah untuk `decisions.md`/`logs.md`/`report.md`/KT-9 (docs).
