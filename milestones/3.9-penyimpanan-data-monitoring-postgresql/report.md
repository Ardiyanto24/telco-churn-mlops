# Report — Milestone 3.9: Penyimpanan Data Monitoring di PostgreSQL

## Ringkasan

Milestone 3.9 SELESAI — realisasi Bagian 8.3 dokumen arsitektur ("Dua Dashboard, Satu Sumber Data Monitoring"): PostgreSQL kini benar-benar jadi sumber utama data yang direpresentasikan dashboard Grafana, bukan Prometheus di-query langsung. Tabel generik BARU `monitoring.metrics_snapshot` (keputusan eksplisit user, bukan rekomendasi awal yang mengusulkan skema per-pilar) menampung snapshot periodik (1 menit) seluruh 12 metrik dari 3 pilar observability. Komponen baru `metrics_aggregator.py` (pod always-on, arsitektur KEBALIKAN dari 2 exporter existing — membaca Prometheus, bukan diskrape olehnya) mengisi tabel ini tanpa menyentuh `pipeline_health_exporter.py`/`drift_exporter.py` sama sekali. Seluruh 10 panel data dashboard `churn-monitoring-m35` (M3.5/3.6/3.8) dimigrasi ke datasource PostgreSQL baru, diverifikasi cocok persis dengan Prometheus — termasuk verifikasi UTUH 30 seri drift (bukan sampel) di checkpoint terakhir.

Alerting (M3.7/M3.8) SENGAJA TIDAK disentuh — tetap query Prometheus langsung (evaluasi cepat, gauge real-time), dikonfirmasi tidak terdampak di setiap checkpoint migrasi panel.

## Kriteria Keberhasilan vs Bukti

| KK | Kriteria | Bukti |
|---|---|---|
| **KK1** | "Nilai agregasi di tabel PostgreSQL, saat dibandingkan dengan nilai mentah di Prometheus untuk periode yang sama, menunjukkan hasil agregasi yang benar (bukan sekadar tersalin, tapi teragregasi sesuai definisi yang dipilih)." | 3 metrik representatif (1 per pilar) dibandingkan pada `time=` PERSIS sama dengan `computed_at` Postgres: `api_latency_p95_seconds` (0.095=0.095), `quality_gate_verdict` (2.0=2.0), `drift_psi` untuk `tenure` (0.0248433684374498=0.0248433684374498, match exact). Definisi agregasi didokumentasikan eksplisit per tipe metrik (statistik nyata utk kontinu, sampling sadar 1 menit utk diskrit) -- lihat `decisions.md` Keputusan #2. |
| **KK2** | "Dashboard Grafana yang sudah dikonfigurasi membaca dari PostgreSQL (bukan Prometheus langsung) menampilkan data yang sama benarnya dengan sebelum perpindahan sumber." | Diverifikasi PER PILAR (Checkpoint 6/7/8), total 10 panel data: pilar infra (Request Rate/Latency/Error Rate -- match presisi tinggi), pilar pipeline health (Status/Durasi Run, Verdict Gerbang Kualitas 5 source_table, Staleness -- match, selisih staleness ~68 detik dijelaskan sebagai metrik terus-bertambah bukan bug), pilar drift (checkpoint TERAKHIR, verifikasi TERKETAT -- seluruh 30 seri/29 fitur+1 output, 0 mismatch, 0 baris hilang). |
| **KK3** | "Job agregasi berjalan terjadwal dan konsisten, tanpa celah waktu yang membuat data di PostgreSQL basi dibanding kondisi nyata." | Diamati ~13,4 menit berjalan -- 13 siklus, gap antar-siklus konsisten 65,9-68,2 detik (nominal 60 detik + overhead wajar), tanpa outlier/lompatan besar. Job menulis TANPA SYARAT tiap siklus (keputusan sadar, `decisions.md` Keputusan #3) -- freshness mudah diverifikasi langsung via `max(computed_at)`. |

## Keputusan Final

Lihat [`decisions.md`](./decisions.md) -- kesepakatan skema generik (dipilih user, BERBEDA dari rekomendasi awal saya yang mengusulkan reuse tabel existing per-pilar), 6 keputusan teknis turunan, volume baris nyata terukur (~150.000/hari, dasar KT-11).

## Perubahan dari Plan Awal

Tidak ada penyimpangan pada scope teknis -- seluruh 9 checkpoint (38 task) diselesaikan sesuai urutan plan yang disetujui. Satu insiden operasional kecil ditemukan+diperbaiki dalam Checkpoint 2: dependency `requests` (dipakai `metrics_aggregator.py` untuk query HTTP Prometheus) ternyata belum terdeklarasi eksplisit di `pyproject.toml` (baru terpasang transitif) -- ditambahkan eksplisit (`requests==2.34.2`) sebelum lanjut ke Docker image, konsisten prinsip "satu sumber kebenaran versi" M1.2.

Teknik SQL untuk panel drift (JOIN 3 subquery `DISTINCT ON`) yang diantisipasi berisiko butuh beberapa percobaan di plan (Task 32, dialokasikan scope M) ternyata BERHASIL di percobaan pertama -- tidak perlu iterasi teknik alternatif.

## Keterbatasan dan Item Terbuka

- **Volume baris tinggi** (~150.000/hari, ~9,8 GB/tahun ekstrapolasi) -- konsekuensi langsung skema generik (drift menyumbang ~72% baris, data yang SEBENARNYA sudah ada di `drift.drift_check_results` M3.6, disalin ulang). Retensi/pruning SENGAJA belum dibangun -- dicatat KT-11 (`docs/keputusan-tertunda.md`) dengan angka nyata sebagai dasar peninjauan ulang, bukan diabaikan.
- **Alerting (M3.7/M3.8) tetap di Prometheus, TIDAK ikut pindah ke PostgreSQL** -- keputusan sadar (di luar cakupan M3.9, Bagian 8.3 bicara soal dashboard bukan alerting), dikonfirmasi tidak terdampak migrasi di setiap checkpoint.
- **Job `metrics_aggregator.py` sendiri TIDAK punya alerting/monitoring** -- kalau pod ini down, tidak ada notifikasi otomatis (beda dari drift/pipeline health yang sudah punya alert M3.7/M3.8). Di luar cakupan eksplisit M3.9 (fokus penyimpanan, bukan alerting), bisa diperluas nanti kalau dibutuhkan.
- **Staleness (`predictions_staleness_seconds`) adalah "staleness dari staleness"** -- nilai gauge Prometheus (dihitung `pipeline_health_exporter.py` dari `now() - max(predicted_at)`) di-snapshot lagi tiap 1 menit, jadi nilai di Postgres SELALU sedikit lebih basi dari kondisi live (dibuktikan diskrepansi ~68 detik saat verifikasi KK2 Checkpoint 7) -- konsekuensi desain uniform (semua metrik dari Prometheus), bukan bug, tapi perlu dipahami pembaca dashboard nanti.
- **`_test_gate_70a3b9f7`** -- source_table probe baru ditemukan di data gerbang kualitas saat verifikasi Checkpoint 7, tidak dikenali sesi ini, di luar cakupan M3.9 untuk diinvestigasi (murni observasi, tidak mempengaruhi korektnes verifikasi).

## Follow-up

- M3.10 (API Publik dan Dashboard Monitoring Publik): `monitoring.metrics_snapshot` siap jadi sumber -- skema generik (keputusan user M3.9) diproyeksikan mempermudah desain endpoint API publik seragam. Role/kredensial API publik WAJIB terpisah dari `monitoring_metrics_reader`/`monitoring_metrics_writer` (forced eksplisit oleh teks sumber M3.10 sendiri).
- KT-11 (retensi) perlu ditinjau ulang begitu ada pemicu nyata (kuota storage, query lambat, atau evaluasi sadar saat M3.10) -- 3 opsi teknis sudah dicatat sebagai referensi (DELETE periodik, partisi tabel, downsampling).
- Pertimbangkan menambah alerting dasar untuk `metrics_aggregator.py` sendiri (mis. staleness `monitoring.metrics_snapshot` seperti pola `predictions_last_write_age_seconds`) kalau kebutuhan observability-untuk-observability muncul nyata.
