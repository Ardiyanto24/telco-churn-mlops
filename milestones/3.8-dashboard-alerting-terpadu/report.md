# Report — Milestone 3.8: Dashboard dan Alerting Terpadu

## Ringkasan

Milestone 3.8 SELESAI. Eksplorasi awal menemukan dashboard SUDAH struktural tunggal sejak M3.6 (panel drift ditambah ke dashboard `churn-monitoring-m35` yang sama, bukan dashboard baru) -- jadi cakupan pekerjaan nyata lebih sempit dari kelihatannya: poles judul dashboard + konfirmasi eksplisit metrik (Checkpoint 1), PERLUAS mekanisme alerting M3.7 (bukan bangun dari nol) ke 2 pilar M3.5 yang belum ada alert-nya (Checkpoint 2), dan verifikasi lewat simulasi kegagalan nyata (Checkpoint 3).

Dua alert rule baru (`PipelineBatchFailed`, `QualityGateStop`) ditambahkan ke `grafana-alerting-configmap.yaml` (M3.7) yang sudah ada, routing ke kanal `pipeline-webhook` yang TERPISAH dari drift (M3.7) -- sesuai pilihan eksplisit user supaya pemisahan kanal per pilar bisa diverifikasi sungguhan, bukan cuma label. Kedua rule memakai pola 2-step (raw query + expression threshold) SEJAK AWAL, reuse langsung fix bug truthy-value yang ditemukan M3.7 -- tidak perlu ditemukan ulang lewat trial-error.

Verifikasi KK3 memicu insiden operasional nyata (bukan bug kode M3.8): 2 flow run misterius ditemukan CRASHED saat proses restore, kemungkinan besar akibat komputer sempat sleep/hibernate berjam-jam di tengah sesi kerja (memutus koneksi aktif secara paksa) -- diinvestigasi tuntas (GitHub Actions, konfirmasi user, Prefect deployment schedule, proses lokal), dampak dipastikan NOL terhadap data produksi (desain all-or-nothing `write_predictions` M2.5 terbukti berfungsi persis seperti dirancang), lalu dimitigasi dengan restore skala kecil.

## Kriteria Keberhasilan vs Bukti

| KK | Kriteria | Bukti |
|---|---|---|
| **KK1** | "Dashboard dapat diakses tim dan mencerminkan kondisi terkini (bukan data basi)." | Judul dashboard diperbarui (`churn-monitoring-m35`, uid tidak berubah). Query `up` via datasource-proxy Prometheus menunjukkan delta 8 detik dari `date +%s` host -- data LIVE, bukan cache/statis. `refresh:"30s"` dan `time:{"from":"now-6h","to":"now"}` tetap ada setelah perubahan. |
| **KK2** | "Orang #1 dan Orang #2 mengonfirmasi metrik yang relevan dari sisi mereka masing-masing sudah terwakili dengan benar." | Data panel nyata ditarik langsung dari datasource-proxy SEBELUM bertanya (bukan simulasi): row drift (`count(feature_drift_verdict==0/1)`=2/2) untuk Orang #1, row pipeline batch health (status run terakhir, verdict gerbang kualitas per source_table, staleness tulis-balik) untuk Orang #2. User dikonfirmasi eksplisit lewat `AskUserQuestion` (2 pertanyaan terpisah, berperan ganda) -- KEDUANYA menjawab "Ya, cukup mewakili". |
| **KK3** | "Simulasi kegagalan di satu titik (mis. DAG batch gagal) menghasilkan alert yang jelas menunjukkan titik akar tersebut ke kanal yang tepat." | Ganda, dua sinyal berbeda, keduanya jalur NYATA (bukan mock): (a) DAG batch gagal dipicu `source_table` tidak valid -> Prefect FAILED nyata -> alert `PipelineBatchFailed` firing -> webhook `pipeline-webhook` (kanal TERPISAH dari drift) menerima notifikasi dengan `failure_type:"batch_dag_failed"`+nama flow. (b) Gerbang kualitas stop dipicu `run_gate()` langsung dengan data sintetis (>10% NULL) + `source_table` terisolasi (`_verification_probe_m38`) -> alert `QualityGateStop` firing HANYA untuk label probe (2 source_table produksi lain tetap pass, terbukti presisi root-cause) -> webhook yang SAMA menerima notifikasi KEDUA dengan `failure_type:"quality_gate_stop"`+`source_table` berbeda. Setelah restore, KEDUA alert mengirim notifikasi **resolved** eksplisit (`"status":"resolved"`, dikonfirmasi 10:23:59 UTC). |

## Keputusan Final

Lihat [`decisions.md`](./decisions.md) -- kesepakatan cakupan alert dan pemisahan kanal (dipilih user via `AskUserQuestion`), 5 keputusan teknis turunan (reuse struktur file M3.7, pola 2-step wajib, satu channel per pilar, repeat_interval provisional, isolasi uji coba), dan 1 insiden operasional (bukan keputusan desain) didokumentasikan lengkap dengan root-cause investigation.

## Perubahan dari Plan Awal

Tidak ada penyimpangan pada scope teknis (semua 16 task plan diselesaikan sesuai urutan) -- tapi Checkpoint 3 memakan waktu jauh lebih lama dari perkiraan karena 2 insiden operasional beruntun yang perlu diinvestigasi tuntas sebelum lanjut:

1. **2 flow run misterius (`teal-auk`/`taupe-beagle`) CRASHED**, bukan dipicu sadar oleh sesi ini -- diinvestigasi 4 arah (GitHub Actions, konfirmasi user, Prefect deployment schedule, proses lokal Windows) sebelum disimpulkan sebagai insiden operasional lingkungan (kemungkinan besar sleep/hibernate komputer memutus koneksi aktif), BUKAN bug kode. Dampak dipastikan NOL lewat pengecekan `predictions.batch_predictions` sebelum/sesudah (count tidak berubah).
2. **Efek urutan operasi saat restore**: membatalkan run orphan (`purple-squid`) SETELAH run restore pertama (`cerulean-turtle`) selesai ternyata membuat status balik "gagal" lagi, karena `pipeline_health_exporter` memilih run terbaru berdasar `end_time` tanpa membedakan jenis state -- bukan bug exporter, murni urutan operasi manual. Diperbaiki dengan run restore KEDUA (`bald-cormorant`) setelah pembatalan selesai.
3. **Kekhawatiran sesaat kontaminasi baseline produksi** (`quality_gate_last_verdict` sempat menunjukkan `telco_customers_source`/`telco_customers_synthetic` verdict=stop bersamaan) -- diinvestigasi via `quality.gate_run_history` langsung dan terbukti HANYA snapshot transisi (propagation delay exporter+Prometheus), bukan kontaminasi nyata; baris restore sendiri sebenarnya PASS (baseline <3 run, check dilewati).

Kronologi investigasi lengkap ada di `logs.md` -- tidak disembunyikan meski memperlihatkan proses trial-and-error, sesuai prinsip proyek.

## Keterbatasan dan Item Terbuka

- **`repeat_interval: 1h` untuk route pipeline/infra adalah angka provisional** (belum ada SLA formal) -- bisa disesuaikan kalau pola operasional nyata muncul, pola sama `repeat_interval` drift M3.7.
- **Kanal `pipeline-webhook` masih endpoint uji (webhook.site), bukan tujuan produksi** -- sama seperti drift M3.7 (KT-10), menunggu web chat user (di luar cakupan proyek ini) selesai dibangun.
- **Baris probe (`_provision_probe` dari M3.5, `_verification_probe_m38` dari M3.8) tetap ada di `quality.gate_run_history`** sebagai artefak riwayat verifikasi -- tabel didesain append-only (role `quality_gate` sengaja tanpa privilege UPDATE/DELETE, M2.4), TIDAK dihapus. Kedua baris probe sudah diresolve ke verdict pass supaya TIDAK memicu alert permanen, tapi tetap muncul di panel tabel dashboard sebagai baris historis. Task pembersihan/penyaringan tampilan disarankan sebagai task terpisah (di luar cakupan M3.8 -- lihat spawned task).
- **DAG batch gagal dan gerbang kualitas stop berbagi SATU kanal** (`pipeline-webhook`), dibedakan lewat `failure_type` label + isi pesan, bukan kanal fisik terpisah per jenis kegagalan individual -- keputusan sadar mengikuti pembingkaian user (pemisahan PER PILAR M3.5 vs M3.6, bukan per rule).
- **Insiden operasional (flow run misterius) tidak dikejar sampai root cause pasti** -- di luar cakupan M3.8 (bukan bug di kode yang disentuh milestone ini), dampak sudah diverifikasi nol, dicatat transparan di `decisions.md`/`logs.md` untuk referensi kalau berulang di masa depan.

## Follow-up

- M3.9 (Penyimpanan Data Monitoring PostgreSQL): dashboard dan alerting yang sudah terpadu di M3.8 ini jadi kandidat sumber agregasi periodik ke PostgreSQL -- struktur 3 pilar (Real-Time API/Pipeline Batch/Drift) yang sudah jelas mempermudah desain skema tabel monitoring.
- Kalau insiden flow run misterius berulang, investigasi lebih dalam ke perilaku `timeout` di Git Bash/Windows terhadap proses `python.exe` panjang, atau pertimbangkan menjalankan verifikasi skala penuh dari lingkungan yang tidak rentan sleep/hibernate.
- Task pembersihan/penyaringan baris probe di `quality.gate_run_history` (spawned terpisah, task_id `task_19130b9c`) bisa dikerjakan kapan saja, tidak menghalangi milestone berikutnya.
