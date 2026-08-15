# Logs — Milestone 3.8: Dashboard dan Alerting Terpadu

## Checkpoint 1 — Konsolidasi Dashboard + Konfirmasi KK1/KK2

Eksplorasi awal mengonfirmasi dashboard SUDAH struktural tunggal (`churn-monitoring-m35`) sejak M3.6 -- 3 row (Real-Time API, Pipeline Batch Health, Data & Model Drift) sudah tampil di satu tempat. Jadi Checkpoint 1 murni poles judul + verifikasi KK1/KK2, bukan bangun ulang.

`infra/k8s/monitoring/grafana-dashboard-configmap.yaml`: judul diubah dari `"Churn Prediction -- Infra & Pipeline Health (M3.5)"` jadi `"Churn Prediction -- Unified Monitoring (Infra, Pipeline, Drift)"` -- `uid` TETAP `churn-monitoring-m35`.

`kubectl apply` diterapkan, TAPI perubahan tidak langsung terbaca dari `/api/dashboards/uid/churn-monitoring-m35` (masih judul lama) -- delay sinkronisasi ConfigMap volume mount ke kubelet (bukan bug, perilaku Kubernetes standar). Diatasi dengan `kubectl rollout restart deployment/grafana` (pola sama M3.7 untuk perubahan provisioning) -- setelah restart (~10 detik ready), judul baru terkonfirmasi via API.

**Verifikasi KK1 (bukan data basi):** Query `up` via datasource-proxy Prometheus menunjukkan timestamp `1786761938`, dibandingkan `date +%s` host `1786761946` -- delta 8 detik, membuktikan dashboard membaca data LIVE, bukan cache/statis. `refresh: 30s` dan `time: now-6h to now` dikonfirmasi tetap ada di JSON dashboard setelah restart.

**Verifikasi KK2 (konfirmasi Orang #1/Orang #2):** Data panel nyata ditarik langsung dari datasource-proxy sebelum bertanya (bukan simulasi):
- Row drift (Orang #1): `count(feature_drift_verdict==0)`=2 (STOP), `count(feature_drift_verdict==1)`=2 (FLAG).
- Row pipeline batch health (Orang #2): `pipeline_flow_last_status{flow_name="milestone-2-5-batch-scoring"}`=1 (Completed); `quality_gate_last_verdict` menunjukkan 2 source_table (`_provision_probe`=2/pass, `telco_customers_synthetic`=2/pass -- `telco_customers_source` TIDAK muncul di gauge terkini, belum ada run gate baru untuk tabel itu sejak terakhir, bukan bug -- gauge memang hanya menampilkan `source_table` yang punya baris terbaru); `predictions_last_write_age_seconds` ~142.067s (`telco_customers_source`, ~39,5 jam) dan ~138.914s (`telco_customers_synthetic`, ~38,6 jam).

User dikonfirmasi via `AskUserQuestion` (2 pertanyaan terpisah, berperan Orang #1 lalu Orang #2) -- KEDUANYA jawab "Ya, cukup mewakili".

**Selesai, commit:** `b74caed` (feat).

## Checkpoint 2 — Perluasan Alerting (Pipeline & Infra Health)

Token webhook.site BARU dibuat (`POST https://webhook.site/token`) -- URL `https://webhook.site/6b6bf87e-6fd7-474a-993a-732fe0df4582`, TERPISAH dari punya drift M3.7 (`.../43011751-...`). Diuji ping dulu sebelum dipakai, berfungsi.

Key `PIPELINE_NOTIFICATION_WEBHOOK_URL` ditambahkan ke Secret `monitoring-secrets` (`kubectl patch`).

`grafana-alerting-configmap.yaml` di-extend (file yang sama dgn M3.7, bukan file baru): contact point `pipeline-webhook`, grup rule baru `pipeline-infra-health` (2 rule: `PipelineBatchFailed`, `QualityGateStop`, keduanya pola 2-step raw+threshold SEJAK AWAL -- tidak menunggu ditemukan ulang lewat trial-error seperti M3.7), route baru di `policies.yaml` (match `alert_category=pipeline_infra_failure` -> `pipeline-webhook`, `repeat_interval: 1h`).

`kubectl apply` + `kubectl rollout restart deployment/grafana` -- pod ready ~18 detik, TIDAK ada error di log (`kubectl logs -l app=grafana | grep -i error` kosong).

Verifikasi lengkap via API Grafana:
- `/api/v1/provisioning/contact-points`: 2 contact point (`drift-webhook`, `pipeline-webhook`), keduanya `provenance:"file"`, URL ter-expand benar dari `$__env{}` (bukan literal string) -- `pipeline-webhook` -> `https://webhook.site/6b6bf87e-...`.
- `/api/v1/provisioning/alert-rules`: 3 rule total (`DriftThresholdExceeded` dari M3.7 + `PipelineBatchFailed` + `QualityGateStop` baru), `condition:"B"` semua (pola 2-step konsisten), `folderUID` berbeda antara `drift-retraining` dan `pipeline-infra-health` (2 grup terpisah).
- `/api/v1/provisioning/policies`: 2 route (`drift_retraining`->4h, `pipeline_infra_failure`->1h).
- `/api/prometheus/grafana/api/v1/rules`: `"health":"ok"` untuk KETIGA rule -- evaluasi berjalan tanpa error PromQL/expression.

**Selesai, commit:** `bf95ee9` (feat).

## Checkpoint 3 — Verifikasi KK3 (Simulasi Kegagalan Nyata)

**Baseline sebelum trigger:** `quality.gate_run_history` 23 baris (max `run_at` 2026-08-14 14:36 UTC), `predictions.batch_predictions` 1.194.488 baris (max `predicted_at` 2026-08-13 12:10 UTC).

**Trigger DAG batch gagal:** `python -m orchestration.flows.batch_scoring` dengan `BATCH_SOURCE_TABLE=nonexistent_table_verification_m38` -- Prefect mencatat run `airborne-guan` **FAILED** (40 detik, 3x retry `extract_raw_data` lalu `psycopg2.errors.UndefinedTable`), TEPAT sebelum tahap gerbang kualitas/tulis-balik. Setelah ~90 detik (siklus exporter 30s + evaluasi rule 1m), `pipeline_flow_last_status`=0 terkonfirmasi di Prometheus, rule `PipelineBatchFailed` berstatus `Alerting` (`activeAt` 02:55:30Z), webhook pipeline/infra BARU menerima notifikasi nyata (`receiver:"pipeline-webhook"`, `status:"firing"`, label `failure_type:"batch_dag_failed"`).

**Trigger gerbang kualitas stop (probe terisolasi):** `run_gate()` dipanggil LANGSUNG (bukan lewat flow) dengan DataFrame sintetis 50 baris, kolom `tenure` 52% NULL, `source_table="_verification_probe_m38"`, `record_history=True`. Verdict **stop** terkonfirmasi (`null_proportion` 52% > ambang stop 10%; `volume`/`category_distribution` PASS krn "baseline belum cukup data" -- run pertama label ini). Rule `QualityGateStop` firing (`activeAt` 02:57:30Z) HANYA untuk `source_table=_verification_probe_m38` (`_provision_probe`/`telco_customers_synthetic` tetap pass=2) -- webhook menerima notifikasi KEDUA dengan konteks berbeda (`failure_type:"quality_gate_stop"`).

**Verifikasi isolasi (tidak ada dampak produksi):** setelah kedua trigger, `quality.gate_run_history` 23->24 baris, SATU-SATUNYA baris baru berlabel `_verification_probe_m38` (query eksplisit per source_table 10 menit terakhir). `predictions.batch_predictions` TETAP 1.194.488 baris -- run FAILED gagal sebelum tahap tulis-balik apa pun.

**Insiden ditemukan (bukan bug kode, murni operasional):** saat mencoba restore (jalankan run sukses skala penuh, default `telco_customers_source`), ditemukan 2 flow run TAMBAHAN yang sudah berstatus **CRASHED** (`teal-auk` mulai 02:58:58Z durasi ~9 menit, `taupe-beagle` mulai 03:04:03Z durasi ~13 menit) yang TIDAK dipicu lewat sesi ini secara sadar. Diinvestigasi sistematis: (a) `gh run list` untuk `batch-scoring.yml`/`synthetic-auto-scoring.yml` -- run terakhir 2026-08-13, BUKAN dari GitHub Actions; (b) user dikonfirmasi eksplisit TIDAK menjalankan apa pun di terminal; (c) `client.read_deployments()` -- deployment `milestone-2-5-batch-scoring-deployment` punya `schedules: []` (tidak ada cron aktif, konsisten status CLAUDE.md), hanya `milestone-2-1-smoke-test-deployment` (flow BEDA) yang punya cron; (d) `tasklist`/`Get-Process python` -- 4 proses `python.exe` lokal ditemukan TAPI start time (08:34 lokal) jauh sebelum kedua run misterius (09:58/10:04 lokal), tidak match. Metadata Prefect (`created_by`) menunjukkan KEDUA run pakai identitas API key yang SAMA dengan run milik sesi ini, dan `state message` KEDUANYA "State changed by Automation" (mekanisme bawaan Prefect Cloud yang otomatis menandai run CRASHED setelah heartbeat hilang -- ini menjelaskan BAGAIMANA statusnya jadi CRASHED, bukan SIAPA yang memulainya). **Root cause pasti tidak berhasil dipastikan** -- hipotesis paling mungkin: `timeout 90` di lingkungan Git Bash/Windows tidak benar-benar mematikan proses `python.exe` yang sedang menjalankan query skala penuh (594.194 baris, durasi wajar ~9-13 menit cocok riwayat M2.5), meninggalkan proses orphan yang terus jalan sampai heartbeat Prefect hilang.

**Dampak diverifikasi NOL:** `predictions.batch_predictions` count dicek ULANG setelah insiden -- TETAP 1.194.488 baris, tidak ada baris baru dari ketiga run (termasuk `purple-squid`, upaya restore skala penuh milik sesi ini sendiri yang bernasib sama, RUNNING tanpa akhir). Konsisten desain all-or-nothing `write_predictions` (KK2 M2.5, satu transaksi, TIDAK ada commit parsial) -- run yang crash SEBELUM commit akhir mustahil meninggalkan data.

**Mitigasi:** `purple-squid` (orphan run milik sesi ini) dibatalkan bersih via `client.set_flow_run_state(..., state=Cancelled())`. Restore diulang dengan `BATCH_SCORING_LIMIT=50` (pola sama `batch-scoring.yml` CI) -- run `cerulean-turtle` **Completed** bersih dalam ~17 detik (50 baris ditulis), menghindari ketidakstabilan run skala penuh yang teramati.

**Docker Desktop ditemukan MATI (lagi)** saat menunggu verifikasi resolve -- pola sama insiden M3.6/M3.7 (kali ketiga dalam rentang M3.6-3.8). Selang waktu nyata antara trigger dan penemuan ini ternyata jauh lebih lama dari perkiraan (pod monitoring menunjukkan `RESTARTS ... 6h1m ago` setelah cluster kembali normal) -- kemungkinan besar KOMPUTER SEMPAT SLEEP/HIBERNATE beberapa jam di antara sesi kerja, yang juga menjelaskan secara masuk akal insiden `teal-auk`/`taupe-beagle` sebelumnya (koneksi jaringan aktif terputus paksa saat sleep, konsisten pola "State changed by Automation" -- heartbeat hilang). Di-restart via PowerShell `Start-Process "Docker Desktop.exe"`, seluruh pod monitoring kembali `Running` tanpa kehilangan data (PVC Prometheus + Postgres eksternal tidak terpengaruh).

**Efek samping ditemukan saat restore:** `purple-squid` (run orphan) dibatalkan (`Cancelled`) SETELAH `cerulean-turtle` (run restore pertama) sudah `Completed` -- karena `pipeline_health_exporter.get_latest_flow_run()` memilih run TERBARU berdasar `end_time` TANPA mempedulikan urutan pembatalan manual, `Cancelled` yang endtime-nya lebih baru "mengalahkan" `Completed` yang lebih dulu, sehingga `pipeline_flow_last_status` balik ke 0 lagi. **Bukan bug logika exporter** (perilaku "run terbaru menang" memang benar untuk kasus normal) -- murni akibat urutan operasi manual sesi ini. **Fix:** jalankan restore SEKALI LAGI (`bald-cormorant`, `BATCH_SCORING_LIMIT=50`, Completed ~21 detik) SETELAH pembatalan `purple-squid` selesai, supaya run Completed benar-benar jadi yang paling akhir.

**Temuan sesaat (bukan bug, transient propagation delay):** query `quality_gate_last_verdict` sempat menunjukkan SEMUA 4 source_table (termasuk `telco_customers_source`/`telco_customers_synthetic` PRODUKSI) berstatus verdict=stop bersamaan -- awalnya dikira kontaminasi baseline produksi oleh run restore skala kecil (kekhawatiran nyata: run 50 baris vs baseline historis ~594.194 baris seharusnya memicu `check_volume` STOP). Diinvestigasi via `quality.gate_run_history` langsung: baris restore (`id=1262`, `telco_customers_source`, 50 baris) verdict-nya ternyata **PASS**, alasan check volume/distribusi "Baseline belum cukup data (<3 run) -- check dilewati" (riwayat `telco_customers_source` di tabel ini sendiri belum genap 3 baris) -- BUKAN kontaminasi. Re-query beberapa detik kemudian (setelah siklus exporter+Prometheus lengkap) mengonfirmasi SEMUA 4 source_table verdict=2 (pass) -- tampilan "stop serentak" sebelumnya murni snapshot transisi (data lama vs baru tumpang tindih sesaat), bukan kondisi nyata.

**Resolusi akhir dikonfirmasi via Python (bukan grep, karena JSON nested tidak reliable diparse regex):** `PipelineBatchFailed` rule.state=`inactive`, instance state=`Normal` (`endsAt` 10:19:10Z). `QualityGateStop` rule.state=`inactive`, SEMUA 4 instance (`_provision_probe`/`telco_customers_source`/`telco_customers_synthetic`/`_verification_probe_m38`) state=`Normal`. Probe `_verification_probe_m38` DIRESOLVE SENGAJA (bukan dibiarkan stop selamanya seperti draft awal) -- `run_gate()` dipanggil ulang dengan data bersih (0% NULL), verdict pass tertulis (`run_id=1263`), supaya kanal `pipeline-webhook` tidak firing permanen dari artefak uji coba.

Notifikasi **resolved** dikonfirmasi tiba di webhook.site pukul 10:23:59 UTC untuk KEDUA rule -- payload `"status":"resolved"` eksplisit, label lengkap sama seperti notifikasi firing (`failure_type`/`source_table`/`flow_name` sesuai masing-masing). KK3 (simulasi kegagalan -> alert jelas titik akar -> kanal terpisah -> resolve terverifikasi) TUNTAS end-to-end untuk kedua sinyal baru.

**Selesai, commit:** (digabung Checkpoint 4).
