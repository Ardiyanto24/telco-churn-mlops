# Decisions — Milestone 3.8: Dashboard dan Alerting Terpadu

## Konteks

`docs/02-implementation-plan/mlops-03-deployment-observability.md` baris 168-184 minta menyatukan hasil M3.5 (infra real-time API + pipeline batch health) dan M3.6 (drift & kualitas model) ke satu dashboard yang mencerminkan kesehatan sistem keseluruhan, plus alerting dengan tujuan/kanal jelas per jenis kejadian, dan konfirmasi eksplisit Orang #1 (metrik relevan model)/Orang #2 (metrik relevan orchestration).

Eksplorasi awal (sebelum plan ditulis) menemukan dashboard SUDAH struktural tunggal sejak M3.6 (panel drift ditambah ke dashboard `churn-monitoring-m35` yang sama, bukan dashboard baru) -- jadi cakupan M3.8 jadi lebih sempit dari kelihatannya: poles kecil dashboard + konfirmasi eksplisit, PERLUAS mekanisme alerting M3.7 (bukan bangun dari nol) ke 2 pilar M3.5 yang belum ada alert-nya, dan verifikasi lewat simulasi kegagalan nyata.

## Kesepakatan User (`AskUserQuestion`, 2 putaran sebelum plan ditulis)

1. **Cakupan alert baru:** DAG batch gagal (`pipeline_flow_last_status==0`) DAN Gerbang kualitas data stop (`quality_gate_last_verdict==0`) -- KEDUANYA dipilih user secara eksplisit (bukan kumulatif dari opsi berjenjang, putaran pertama sempat salah dirancang sebagai pilihan tunggal-kumulatif, diperbaiki jadi `multiSelect` independen setelah user bertanya "apakah bisa lebih dari satu pilihan?"). Staleness tulis-balik dan error-rate real-time API TIDAK dipilih.
2. **Pemisahan kanal:** Endpoint webhook.site BARU dan TERPISAH dari punya drift (M3.7) -- dipilih user supaya pemisahan kanal per pilar benar-benar bisa diverifikasi, bukan cuma label.

## Keputusan Teknis

### 1. Cakupan alert dibatasi ke 2 sinyal biner (bukan staleness/error-rate)

**Keputusan:** Hanya `pipeline_flow_last_status==0` (DAG gagal) dan `quality_gate_last_verdict==0` (gerbang stop) yang dapat alert rule baru.

**Kenapa:** User memilih langsung dari 4 opsi yang disajikan (lihat `AskUserQuestion` di atas). Kedua sinyal yang dipilih encoding biner/diskrit (tanpa perlu menebak ambang batas numerik apa pun) -- konsisten prinsip proyek (CLAUDE.md "Batas Implementasi Saat Ini": jangan memilih threshold/SLA yang sengaja dibiarkan terbuka tanpa proses keputusan eksplisit).

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Staleness tulis-balik `predictions_last_write_age_seconds`** -- DITOLAK user: perlu memilih ambang batas jam/menit sendiri tanpa SLA formal manapun, situasi identik KT-5/KT-6 yang sengaja ditunda di milestone lain.
- **Error rate real-time API** -- DITOLAK user dengan alasan sama (ambang batas belum punya SLA formal, KT-5 relevan).

### 2. Extend `grafana-alerting-configmap.yaml` (M3.7) yang sudah ada, bukan ConfigMap baru

**Keputusan:** Contact point, grup rule, dan route baru ditambahkan sebagai entri BARU di 3 blok YAML yang sudah ada (`contactpoints.yaml`/`rules.yaml`/`policies.yaml`), file yang sama persis dengan M3.7.

**Kenapa:** Ketiga blok itu sudah berbentuk array (`contactPoints:`/`groups:`/`policies[].routes:`) -- menambah entri baru adalah operasi natural, tidak perlu ConfigMap/volume mount terpisah. `grafana-deployment.yaml` (volume mount `alerting`) TIDAK perlu diubah sama sekali (sudah ter-mount sejak M3.7).

**Tidak ada alternatif dipertimbangkan** -- konsisten derivasi langsung dari struktur file M3.7 yang sudah final, bukan keputusan baru yang perlu opsi lain.

### 3. Rule baru WAJIB pola 2-step (raw query + expression threshold) SEJAK AWAL

**Keputusan:** `PipelineBatchFailed` dan `QualityGateStop` SAMA-SAMA memakai refId A (raw gauge Prometheus) + refId B (`type: threshold`, `datasourceUid: __expr__`) sejak rule pertama kali ditulis -- BUKAN filter langsung di PromQL dengan `condition` menunjuk ke refId A.

**Kenapa:** M3.7 (Keputusan #4 milestone itu) menemukan bug nyata: Grafana Alerting mengevaluasi ALERTING berdasar NILAI MENTAH non-zero kalau `condition` menunjuk langsung ke hasil query, REGARDLESS filter PromQL yang sudah diterapkan -- nilai `0` (justru kondisi paling parah di kedua metrik M3.5: `pipeline_flow_last_status=0`=Failed/Crashed, `quality_gate_last_verdict=0`=stop) akan dianggap "tidak alerting". Kedua metrik baru di M3.8 PERSIS punya kerentanan yang sama seperti `feature_drift_verdict` M3.6 -- pola fix M3.7 di-reuse LANGSUNG di sini, tidak menunggu ditemukan ulang lewat trial-error.

- `PipelineBatchFailed`: evaluator `within_range` params `[-0.5, 0.5]` -- sengaja ISOLASI nilai `0` (Failed/Crashed) SAJA, TIDAK termasuk `-1` (belum pernah ada run). `-1` sengaja dikecualikan karena tidak ada jadwal cron aktif untuk `milestone-2-5-batch-scoring` (KD-1) -- kalau `-1` ikut ditangkap, rule akan selalu true sebelum run pertama pernah terjadi, menghasilkan alert palsu terus-menerus.
- `QualityGateStop`: evaluator `lt` params `[1]` -- pola PERSIS sama dengan rule drift M3.7 (`quality_gate_last_verdict` encoding identik `feature_drift_verdict`: 2=pass/1=flag/0=stop), reuse langsung tanpa variasi.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Filter langsung di PromQL** (`expr: pipeline_flow_last_status == 0`, `condition: A`) -- DITOLAK: ini PERSIS pola yang gagal di M3.7, sudah terbukti tidak bekerja untuk kasus nilai bermakna `0`.
- **Ubah encoding metrik M3.5** (`pipeline_flow_last_status`/`quality_gate_last_verdict`) supaya `0` bukan nilai "kondisi terburuk" -- DITOLAK: mengubah kontrak metrik M3.5 yang sudah teruji+dipakai dashboard `churn-monitoring-m35` (panel "Status Run Terakhir"/"Verdict Gerbang Kualitas") demi kebutuhan alerting semata, berisiko memecah value mapping panel existing. Sama alasan penolakan opsi serupa di M3.7 Keputusan #4.

### 4. Satu channel/kanal baru `pipeline-webhook` untuk KEDUA rule (bukan 2 channel terpisah lagi)

**Keputusan:** `PipelineBatchFailed` dan `QualityGateStop` berbagi SATU label routing `alert_category: pipeline_infra_failure` -> satu contact point `pipeline-webhook` (endpoint uji BARU, terpisah dari drift M3.7) -- tapi masing-masing punya `failure_type` (`batch_dag_failed`/`quality_gate_stop`) + `summary`/`description` berbeda yang menyebut konteks spesifik (nama flow atau `source_table`).

**Kenapa:** User memilih pemisahan kanal PER PILAR (pipeline & infra vs drift), bukan per jenis kegagalan individual -- 2 sinyal M3.5 yang dipilih (DAG gagal, gerbang kualitas stop) SAMA-SAMA berada di pilar "pipeline & infra health" yang sama (M3.5), beda dari pilar drift (M3.6/M3.7). Payload tetap menunjukkan titik akar spesifik lewat `failure_type`+annotation (memenuhi KK3 "menunjukkan titik akar tersebut") walau landing di kanal fisik yang sama untuk pilar yang sama.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **3 channel terpisah** (drift, DAG-failure, quality-gate) -- DITOLAK: user secara eksplisit membingkai pertanyaan sebagai pemisahan PER PILAR (M3.5 vs M3.6), bukan per rule individual; 3 endpoint uji terpisah menambah overhead pengelolaan tanpa manfaat tambahan pada tahap ini (destination sesungguhnya -- web chat user -- belum ada, KT-10).

### 5. `repeat_interval: 1h` untuk route pipeline/infra (lebih pendek dari drift 4h)

**Keputusan:** Route `pipeline_infra_failure` memakai `repeat_interval: 1h`, dibanding `repeat_interval: 4h` untuk `drift_retraining` (M3.7).

**Kenapa:** Kegagalan infra/pipeline (DAG batch gagal, gerbang kualitas stop) secara operasional lebih mendesak untuk ditinjau ulang dibanding drift model (yang sifatnya lebih ke tren bertahap) -- re-notifikasi lebih sering wajar untuk kategori kegagalan operasional. Angka PROVISIONAL (belum ada SLA formal), pola sama `repeat_interval` drift M3.7 yang juga provisional.

**Tidak ada alternatif dipertimbangkan secara eksplisit ke user** -- keputusan turunan kecil (angka provisional), konsisten pola M3.7 Keputusan #6 yang juga tidak melalui `AskUserQuestion` terpisah untuk angka repeat_interval.

### 6. Uji coba terkontrol KK3 lewat jalur nyata dengan isolasi eksplisit

**Keputusan:** DAG batch gagal dipicu via `source_table` tidak valid (`batch_scoring_flow()` gagal di tahap `extract`, SEBELUM gerbang kualitas/tulis-balik tersentuh). Gerbang kualitas stop dipicu via `run_gate()` dipanggil LANGSUNG (bukan lewat flow) dengan DataFrame sintetis (>10% NULL) dan `source_table="_verification_probe_m38"` -- label yang TERISOLASI dari `telco_customers_source`/`telco_customers_synthetic` produksi.

**Kenapa:** `check_null_proportion` (`checks.py`) TIDAK butuh baseline historis (beda dari `check_volume`/`check_category_distribution` yang butuh >=3 run) -- verdict "stop" bisa dipicu di RUN PERTAMA source_table baru, TANPA pernah menyentuh baseline produksi. Pola label probe (`_verification_probe_m38`) konsisten preseden `_provision_probe` yang sudah muncul di riwayat `quality.gate_run_history` sejak sebelum M3.5 (dicatat sebagai artefak verifikasi yang diterima, lihat `milestones/3.5-.../report.md`).

**Diverifikasi empiris (bukan diasumsikan):** `quality.gate_run_history` untuk `telco_customers_source`/`telco_customers_synthetic` TIDAK bertambah baris sama sekali selama kedua trigger (dicek eksplisit per source_table). `predictions.batch_predictions` TETAP 1.194.488 baris (dicek sebelum+sesudah) -- run FAILED gagal sebelum tahap tulis-balik apa pun.

**Tidak ada alternatif dipertimbangkan** -- pola ini derivasi langsung dari properti `run_gate()`/`check_null_proportion()` yang sudah ada sejak M2.4, dipilih justru KARENA properti itu (tidak butuh baseline) membuat isolasi mungkin tanpa modifikasi kode apa pun.

### 7. Insiden operasional (bukan keputusan desain): 2 flow run misterius saat restore, dimitigasi dengan run skala kecil

**Konteks:** Saat mencoba restore status DAG (Task 12), ditemukan 2 flow run TAMBAHAN (`teal-auk`, `taupe-beagle`) berstatus CRASHED yang tidak dipicu sadar oleh sesi ini maupun dikonfirmasi user. Investigasi (`gh run list`, konfirmasi user, `read_deployments()`, `tasklist`) TIDAK menemukan sumber pasti -- hipotesis paling mungkin: `timeout` di lingkungan Git Bash/Windows tidak mematikan proses `python.exe` skala penuh, meninggalkan proses orphan sampai heartbeat Prefect hilang (mekanisme bawaan "State changed by Automation").

**Dampak diverifikasi NOL** -- `predictions.batch_predictions` count tidak berubah sepanjang insiden (all-or-nothing `write_predictions`, M2.5 KK2). Bukan bug kode; dicatat sebagai insiden operasional lingkungan lokal, bukan keputusan desain -- lihat `logs.md` Checkpoint 3 untuk kronologi investigasi lengkap.

**Mitigasi:** Run orphan milik sesi ini (`purple-squid`) dibatalkan bersih via Prefect API. Restore diulang dengan `BATCH_SCORING_LIMIT=50` (pola sama `batch-scoring.yml` CI, KD-1) -- berhasil Completed bersih ~17 detik, menghindari ketidakstabilan run skala penuh yang teramati di lingkungan ini saat itu.

**Tidak ada alternatif dipertimbangkan** -- ini insiden operasional yang dimitigasi langsung (bukan keputusan desain dengan opsi tertimbang), root cause pasti TIDAK dikejar lebih jauh karena di luar cakupan M3.8 (bukan bug di kode yang disentuh milestone ini) dan dampak sudah diverifikasi nol.

## Kriteria Keberhasilan vs Bukti

**KK1** ("Dashboard dapat diakses tim dan mencerminkan kondisi terkini"): lihat `report.md` -- query `up` live delta 8 detik dari waktu sekarang, `refresh:30s`/`time:now-6h to now` tetap ada setelah judul diubah.

**KK2** ("Orang #1 dan Orang #2 mengonfirmasi metrik relevan sudah terwakili"): lihat `report.md` -- konfirmasi eksplisit user (2x, berperan ganda) dengan data panel nyata ditunjukkan sebelum bertanya.

**KK3** ("Simulasi kegagalan menghasilkan alert yang jelas menunjukkan titik akar ke kanal yang tepat"): lihat `report.md` -- 2 trigger nyata (DAG gagal, gerbang stop), masing-masing menghasilkan notifikasi webhook `pipeline-webhook` (kanal TERPISAH dari drift) dengan `failure_type`+deskripsi berbeda yang jelas menunjuk root cause masing-masing, dikonfirmasi resolve setelah restore.
