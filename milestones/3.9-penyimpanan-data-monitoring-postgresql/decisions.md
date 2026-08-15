# Decisions — Milestone 3.9: Penyimpanan Data Monitoring di PostgreSQL

## Konteks

`docs/02-implementation-plan/mlops-03-deployment-observability.md` baris 187-205, forced oleh Bagian 8.3 dokumen arsitektur ("Dua Dashboard, Satu Sumber Data Monitoring"): PostgreSQL harus jadi sumber UTAMA data monitoring yang direpresentasikan di dashboard — bukan sekadar salinan Prometheus, dan bukan Prometheus di-query langsung oleh satu dashboard sementara yang lain dari PostgreSQL. Fondasi wajib sebelum M3.10 (API publik + dashboard web custom).

Eksplorasi awal (sebelum plan ditulis) menemukan drift (M3.6, `drift.drift_check_results`) dan sebagian pipeline health (gerbang kualitas M2.4, staleness M2.5) SUDAH punya tabel PostgreSQL asli — hanya diekspos ke Prometheus lewat exporter M3.5/M3.6 untuk kebutuhan dashboard+alerting. Satu-satunya data yang benar-benar cuma hidup di Prometheus (latency/throughput/error-rate real-time API) atau di sistem eksternal (status/durasi flow Prefect Cloud) adalah sub-himpunan kecil.

## Kesepakatan User (`AskUserQuestion`, 1 putaran, 4 pertanyaan sebelum plan ditulis)

1. **Skema tabel:** SATU tabel generik `monitoring.metrics_snapshot` untuk SEMUA metrik dari ketiga pilar — BUKAN pendekatan per-metrik/reuse tabel existing yang direkomendasikan. Drift dan pipeline-health (yang groundtruth-nya sudah di Postgres) tetap DISALIN ULANG ke skema seragam ini. Alasan user: API publik (M3.10) jadi lebih seragam (1 query generik, bukan 3 skema berbeda per pilar).
2. **Arsitektur job:** Pod always-on + loop poll internal — konsisten pola `pipeline_health_exporter.py`/`drift_exporter.py` existing.
3. **Frekuensi:** 1 menit.
4. **Retensi:** Belum perlu sekarang — dicatat sebagai KT-11 (`docs/keputusan-tertunda.md`).

## Keputusan Teknis

### 1. Skema generik `monitoring.metrics_snapshot` (bukan per-pilar)

**Keputusan:** Satu tabel `(id, metric_name, value, labels jsonb, computed_at)` menampung seluruh metrik 3 pilar.

**Kenapa:** Pilihan eksplisit user (lihat kesepakatan #1 di atas) — API publik M3.10 diproyeksikan lebih sederhana dibangun di atas satu skema generik ketimbang menggabungkan 3 skema berbeda per pilar.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Per-metrik/reuse tabel existing** (drift→`drift.drift_check_results` langsung, pipeline-health→`quality.gate_run_history`+`predictions.batch_predictions` langsung, HANYA infra/API dapat tabel baru) — INI REKOMENDASI SAYA, DITOLAK user. Argumen saya: menghindari duplikasi data yang sudah ada di Postgres, blast radius kredensial API publik lebih presisi per-pilar. Argumen user (yang menang): keseragaman skema lebih penting untuk kemudahan pengembangan API publik M3.10 ke depan, trade-off duplikasi data diterima sadar.

**Implikasi turunan:** Karena skema generik dipilih, dan karena SEMUA metrik (termasuk drift/pipeline-health) SUDAH terekspos seragam sebagai gauge Prometheus lewat exporter M3.5/M3.6, desain job agregasi jadi SEDERHANA — cukup baca SERAGAM dari Prometheus untuk seluruh 3 pilar (tidak perlu bicara ke Prefect Cloud API atau query langsung tabel Postgres lain). Pendekatan per-pilar campuran yang sempat dipertimbangkan di awal riset TIDAK dipakai.

### 2. Definisi "agregasi" per tipe metrik (memenuhi KK1 "bukan sekadar tersalin")

**Keputusan:** Metrik kontinu (latency/throughput/error-rate API) = agregasi statistik NYATA dari histogram/counter Prometheus per siklus (`histogram_quantile`, `rate()`), persis definisi panel dashboard existing. Metrik diskrit/gauge (verdict drift, verdict gerbang kualitas, status flow, staleness) = SAMPLING/snapshot sadar tiap 1 menit dari nilai gauge saat itu — downsampling terjadwal yang disengaja, BUKAN penyalinan tiap scrape mentah 15 detik.

**Kenapa:** KK1 eksplisit menuntut "bukan sekadar tersalin, tapi teragregasi sesuai definisi yang dipilih" — untuk metrik gauge (nilai diskrit, bukan distribusi), "agregasi" yang bermakna adalah keputusan SADAR tentang frekuensi sampling (1 menit, bukan tiap scrape), bukan operasi statistik seperti p95. Metodologi ini didokumentasikan eksplisit supaya jelas bedanya dengan "menyalin".

**Tidak ada alternatif dipertimbangkan** — definisi ini derivasi langsung dari sifat data (kontinu vs diskrit), bukan pilihan desain yang punya opsi lain bermakna.

### 3. Job MENULIS SETIAP SIKLUS tanpa syarat (bukan hanya saat nilai berubah)

**Keputusan:** `metrics_aggregator.py` menulis baris baru tiap siklus poll (60 detik) untuk SETIAP metric spec, TIDAK membandingkan dengan nilai siklus sebelumnya untuk skip penulisan kalau tidak berubah.

**Kenapa:** KK3 ("job agregasi berjalan terjadwal dan konsisten, TANPA CELAH WAKTU yang membuat data basi") jauh lebih mudah diverifikasi dengan pola tulis-selalu — `max(computed_at)` selalu segar, gap antar baris konsisten ~60 detik bisa dibuktikan langsung via query. Pola tulis-hanya-saat-berubah (change-based) akan membuat absennya baris baru AMBIGU (job down ATAU nilai memang belum berubah) — mengaburkan pembuktian KK3.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Tulis hanya saat nilai berubah** — DITOLAK: menghemat volume baris, TAPI mengorbankan kemudahan verifikasi KK3 (freshness/no-gap jadi tidak provable secara langsung), trade-off tidak sepadan mengingat retensi sudah sengaja ditunda (Keputusan #6) sehingga volume baris bukan masalah mendesak.

### 4. Komponen baru tunggal `metrics_aggregator.py` — TIDAK menyentuh 2 exporter existing

**Keputusan:** Satu komponen baru, pure WRITER (baca Prometheus via HTTP client, tulis Postgres) — `pipeline_health_exporter.py`/`drift_exporter.py` TIDAK diubah sama sekali, tetap dipakai apa adanya oleh alerting M3.7/M3.8.

**Kenapa:** Konsisten prinsip "M3.x tidak mengubah pekerjaan milestone lain yang sudah selesai" yang berlaku sejak M3.6 (drift_exporter tidak sentuh pipeline_health_exporter) dan M3.7/M3.8 (alerting tidak sentuh dashboard/exporter). Mengubah exporter existing untuk kebutuhan M3.9 akan menambah risiko ke mekanisme alerting yang sudah terverifikasi tanpa keperluan nyata (job baru bisa 100% independen).

**Tidak ada alternatif dipertimbangkan secara eksplisit ke user** — konsisten pola berulang, tidak perlu opsi lain dipertimbangkan.

### 5. Role Postgres baru: `monitoring_metrics_writer` + `monitoring_metrics_reader`

**Keputusan:** 2 role baru, TERPISAH dari `monitoring_reader` (M3.5, dipakai `pipeline_health_exporter.py`, scope `quality`+`predictions`) — bukan role lama yang diperluas.

**Kenapa:** Pola "satu role per pola akses" konsisten M2.1/M2.4/M2.5/M2.9/M3.5/M3.6 — `monitoring_metrics_writer` (dipakai `metrics_aggregator.py`, akses tulis) dan `monitoring_reader` (dipakai `pipeline_health_exporter.py`, akses baca tabel lain) punya pola akses yang BEDA TOTAL (tabel beda, arah beda), walau nama mirip. Menyatukan keduanya akan melanggar prinsip least-privilege (exporter M3.5 tidak butuh akses tulis `monitoring.metrics_snapshot`, aggregator M3.9 tidak butuh akses baca `quality`/`predictions`).

**Manfaat samping dari skema generik (Keputusan #1):** `monitoring_metrics_reader` (dipakai Grafana) HANYA perlu akses SATU tabel (`monitoring.metrics_snapshot`) untuk seluruh dashboard — TIDAK perlu akses `drift.drift_check_results`/`quality.gate_run_history`/`predictions.batch_predictions` langsung sama sekali. Blast radius kredensial Grafana lebih sempit dari sebelumnya (efek samping positif dari keputusan skema yang tadinya saya nilai sebagai trade-off).

### 6. K8s: Deployment SAJA, tanpa Service

**Keputusan:** `metrics-aggregator-deployment.yaml` hanya berisi Deployment — TIDAK ada Service/port terekspos.

**Kenapa:** Berbeda dari `drift-exporter`/`pipeline-health-exporter` (yang punya Service karena DISCRAPE Prometheus, perlu port `:9100`/`:9101` dapat dijangkau), `metrics_aggregator.py` adalah pure background worker yang MEMBACA dari Prometheus sebagai client — tidak ada yang perlu memanggil/men-scrape pod ini dari luar. Menambah Service yang tidak dipakai adalah kompleksitas tanpa manfaat.

**Tidak ada alternatif dipertimbangkan** — forced by arah data (writer, bukan target scrape).

## Kriteria Keberhasilan vs Bukti

**KK1** ("Nilai agregasi di tabel PostgreSQL, saat dibandingkan dengan nilai mentah di Prometheus untuk periode yang sama, menunjukkan hasil agregasi yang benar"): 3 metrik representatif (satu per pilar) dibandingkan LANGSUNG — `api_latency_p95_seconds` (Postgres 0.095 vs Prometheus 0.095, MATCH), `quality_gate_verdict` untuk `telco_customers_synthetic` (2.0 vs 2.0, MATCH), `drift_psi` untuk `tenure` (0.0248433684374498 vs 0.0248433684374498, MATCH exact) — query Prometheus dijalankan dengan parameter `time=` PERSIS sama dengan `computed_at` baris Postgres, PromQL identik `METRIC_SPECS`. Lihat `logs.md` Checkpoint 4.

**KK2** ("Dashboard Grafana yang sudah dikonfigurasi membaca dari PostgreSQL... menampilkan data yang sama benarnya dengan sebelum perpindahan sumber"): diverifikasi PER PILAR di 3 checkpoint terpisah (Checkpoint 6/7/8) — seluruh 10 panel data (dari 13 panel total, 3 sisanya row header tanpa datasource) dibandingkan nilai Postgres vs Prometheus live pada query yang sama. Pilar drift (checkpoint terakhir, verifikasi terketat) diverifikasi UTUH seluruh 30 seri (29 fitur + `churn_probability`), bukan sampel — 0 mismatch. Lihat `logs.md` Checkpoint 6-8.

**KK3** ("Job agregasi berjalan terjadwal dan konsisten, tanpa celah waktu"): 13 siklus dalam ~13,4 menit, gap antar-siklus konsisten 65,9-68,2 detik (nominal 60 detik + overhead query 12 metric spec, wajar), tanpa outlier/lompatan besar. Lihat `logs.md` Checkpoint 4.

## Volume Baris Nyata (Bukan Estimasi)

Diukur langsung dari `monitoring.metrics_snapshot` setelah seluruh checkpoint implementasi selesai: 2.595 baris dalam ~25 siklus (~25 menit), 472 kB. Ekstrapolasi **~150.000 baris/hari (~27 MB/hari, ~9,8 GB/tahun)** — dominasi drift (~72% baris, konsekuensi langsung Keputusan #1: skema generik menyalin ulang data drift yang sebenarnya sudah ada di `drift.drift_check_results` M3.6). Angka ini jadi dasar KT-11 (`docs/keputusan-tertunda.md`) — retensi sengaja ditunda, TAPI didokumentasikan dengan angka nyata (bukan asumsi "volume kecil" seperti dugaan awal saat `AskUserQuestion` retensi diajukan) supaya keputusan peninjauan ulang nanti punya dasar konkret.
