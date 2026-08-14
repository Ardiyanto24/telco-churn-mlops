# Report — Milestone 3.5: Monitoring Infra dan Pipeline Health

## Ringkasan

Milestone 3.5 SELESAI — real-time API (M3.2-3.4) sekarang terinstrumentasi metrik Prometheus (latency, throughput, error rate), dan status pipeline batch (M2.5/M2.9) dikonsolidasikan lewat exporter kustom (status flow Prefect, verdict gerbang kualitas data M2.4, staleness tulis-balik) — keduanya tersaji di satu dashboard Grafana yang di-provision deklaratif di cluster Kubernetes lokal (M3.3).

Monitoring stack (Prometheus + Grafana self-host) dipilih lewat `AskUserQuestion` dua putaran, eksplisit dicek forward-compatibility-nya terhadap seluruh sisa jalur M3.6-3.12 sebelum diputuskan — bukan tebakan. Satu bug produksi ditemukan+diperbaiki saat verifikasi Checkpoint 3: Kubernetes otomatis inject environment variable dari nama Service yang bentrok dengan nama variabel port exporter sendiri, menyebabkan `CrashLoopBackOff`.

## Kriteria Keberhasilan vs Bukti

| KK | Kriteria | Bukti |
|---|---|---|
| **KK1** | "Untuk real-time API, tim bisa menjawab 'berapa latency p95 hari ini' dan 'berapa persen request gagal' tanpa query manual ke log mentah." | Trafik nyata digenerate (25 valid + 8 invalid ke `/predict`), dashboard Grafana (`http://localhost:3000/d/churn-monitoring-m35`) dibuka di browser sungguhan: panel "Error Rate /predict (5m)" menampilkan **24.2%**, cocok PERSIS PromQL manual (`100 * sum(rate(http_requests_total{status=~"4xx\|5xx"}[5m])) / sum(rate(http_requests_total[5m]))` = `24.242...`). Panel "Latency p50/p95/p99" menampilkan garis histogram_quantile real-time. |
| **KK2** | "Untuk pipeline batch, status run terakhir (berhasil/gagal, durasi) terlihat di tempat yang sama tanpa membuka orchestrator Orang #2 secara langsung." | Panel "Status Run Terakhir -- milestone-2-5-batch-scoring" menampilkan **"Completed"** (value mapping numerik→teks), "Durasi Run Terakhir" menampilkan **"4.27 s"** — keduanya dari exporter yang polling Prefect Cloud REST API, TANPA membuka Prefect Cloud UI. Verdict gerbang kualitas data + staleness tulis-balik per `source_table` dikonfirmasi lewat query langsung ke Grafana datasource proxy (jalur query PERSIS yang dipakai panel table), cocok data Postgres nyata. |

## Keputusan Final

Lihat [`decisions.md`](./decisions.md) — 10 keputusan (1 genuinely terbuka via `AskUserQuestion` dengan analisis forward-compatibility M3.6-3.12, 9 turunan dari preseden proyek) + 1 bug ditemukan+diperbaiki saat verifikasi (Kubernetes env var collision).

## Perubahan dari Plan Awal

Tidak ada penyimpangan besar dari plan — seluruh 4 checkpoint (instrumentasi API → exporter pipeline health → deploy Prometheus+exporter → deploy Grafana+verifikasi) berjalan sesuai urutan yang direncanakan. Dua insiden minor ditemukan+diperbaiki DI DALAM checkpoint yang sama tempat mereka muncul (bukan menunda ke checkpoint berikutnya):

1. **Checkpoint 1**: test `/metrics` awalnya flaky (assertion nilai absolut counter, gagal saat dijalankan bersama test lain karena `prometheus_client.REGISTRY` global) — diperbaiki jadi assertion delta sebelum lanjut ke Checkpoint 2.
2. **Checkpoint 3**: exporter `CrashLoopBackOff` karena Kubernetes Docker-links env var collision (lihat `decisions.md`) — diperbaiki (rename variabel) sebelum lanjut ke Checkpoint 4.

Satu insiden operasional kecil (bukan bug kode): perintah `echo >> .env` pertama merusak baris terakhir file karena tidak ada newline penutup — terdeteksi dan diperbaiki segera, tidak ada dampak ke kredensial produksi (lihat `logs.md` Checkpoint 2).

## Keterbatasan dan Item Terbuka

- **Dashboard Grafana + Prometheus hanya reachable selama komputer user menyala DAN Docker Desktop Kubernetes dijalankan manual** — bukan monitoring 24/7. Ini konsisten KD-2 (`docs/keterbatasan-diterima.md`) yang sudah diterima sejak M3.3 untuk real-time API, sekarang berlaku juga untuk stack monitoringnya.
- **Riwayat metrik Prometheus (PVC) bertahan lintas restart pod, TAPI hilang kalau cluster Docker Desktop di-reset total** (bukan sekadar restart) — keterbatasan diterima, konsekuensi turunan KD-2, bukan KD baru.
- **Retensi default Prometheus (15 hari) dan interval scrape (15 detik) belum disesuaikan berdasar kebutuhan nyata** — estimasi awal wajar untuk skala proyek ini, bisa ditinjau ulang di M3.9 (penyimpanan monitoring PostgreSQL) kalau kebutuhan retensi lebih panjang muncul.
- **Belum ada alerting** — di luar cakupan M3.5 (sumber eksplisit menempatkan alerting di M3.7/3.8). Dashboard ini murni observasional (lihat data, bukan diberi tahu proaktif saat ada masalah).
- **`_provision_probe` muncul sebagai `source_table` di panel "Verdict Gerbang Kualitas Data"** — baris riwayat dari verifikasi milestone lampau (bukan source_table produksi nyata: `telco_customers_source`/`telco_customers_synthetic`). Tidak mempengaruhi korektnes (query dinamis menangani apa pun yang ada di tabel), tapi kosmetik dashboard bisa sedikit membingungkan sampai baris lampau itu dibersihkan (di luar cakupan M3.5 — punya `quality.gate_run_history` adalah milik M2.4).
- **"Status refresh feature store"** (salah satu dari 3 sinyal yang diminta teks sumber) TIDAK diimplementasikan — forced oleh M2.2 (tidak ada feature store yang dibangun). Dicatat eksplisit di `decisions.md` Keputusan #10, bukan gap yang terlewat.

## Follow-up

- M3.6 (drift monitoring): exporter drift baru bisa mengikuti pola persis `pipeline_health_exporter.py` (polling berkala + gauge Prometheus), discrape Prometheus yang sama, panel baru ditambah ke dashboard `churn-monitoring-m35` yang sudah ada — bukan dashboard baru.
- M3.7 (alerting): Grafana alerting/Alertmanager bisa langsung dikonfigurasi di atas datasource Prometheus yang sudah ada.
- M3.9 (penyimpanan monitoring PostgreSQL): job agregasi periodik Prometheus→PostgreSQL bisa dibangun sekarang Prometheus sudah punya data riil untuk diagregasi; Grafana tinggal diarahkan ulang ke datasource PostgreSQL untuk panel yang relevan.
- Pertimbangkan membersihkan baris `_provision_probe` di `quality.gate_run_history` (milik M2.4, di luar cakupan M3.5) supaya dashboard tidak menampilkan source_table yang membingungkan.
- Retensi/interval Prometheus bisa ditinjau ulang berdasar kebutuhan nyata begitu ada pengalaman operasional lebih panjang.
