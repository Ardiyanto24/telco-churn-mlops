# Report — Milestone 3.7: Jalur Notifikasi Retraining ke Data Scientist

## Ringkasan

Milestone 3.7 SELESAI — notifikasi otomatis kini terkirim saat drift (M3.6) melewati ambang batas "stop", lewat Grafana Alerting (reuse penuh infrastruktur Prometheus+Grafana M3.5/M3.6, TANPA kode Python baru sama sekali). Kanal saat ini adalah webhook generik ke endpoint uji (webhook.site) — user sedang membangun web chat simulasi tim terpisah (di luar cakupan proyek ini) sebagai tujuan akhir; desain sengaja dibuat agar mengganti tujuan URL nanti cukup 1 perubahan Secret, tanpa bongkar kode/manifest.

Satu bug signifikan ditemukan+diperbaiki saat verifikasi: encoding `feature_drift_verdict` (0=stop, dari M3.6) bertentangan dengan konvensi default Grafana alerting (nonzero=alerting) — rule ter-provisioning bersih tapi tidak pernah fire sampai ditambah expression Threshold eksplisit. Setelah fix, mekanisme LANGSUNG bekerja dari data produksi ASLI (bukan cuma simulasi) — notifikasi otomatis terkirim untuk `service_count`/`tenure` yang memang sudah berstatus "stop" sejak M3.6.

## Kriteria Keberhasilan vs Bukti

| KK | Kriteria | Bukti |
|---|---|---|
| **KK1** | "Simulasi drift melewati ambang batas berhasil memicu notifikasi ke kanal yang disepakati, dengan informasi cukup bagi tim DS untuk memahami tanpa bertanya balik." | Ganda: (a) notifikasi OTOMATIS dari data produksi asli (`service_count`/`tenure`) terkirim tanpa intervensi begitu provisioning aktif; (b) uji coba terkontrol eksplisit (`compute_drift.py --override-current`, 2 fitur digeser ekstrem) memicu `[FIRING:4]` (2 baru + 2 asli), lalu setelah restore, `[FIRING:2, RESOLVED:2]` — TEPAT 2 fitur yang direstore berstatus resolved, 2 fitur asli tetap firing. Payload lengkap: `feature_name`, `startsAt`/`endsAt`, deskripsi konteks pembanding baseline vs data terkini, link dashboard, penegasan retraining manual. |
| **KK2** | "Tim Data Scientist mengonfirmasi jalur dan format notifikasi dapat dipakai sebagai dasar keputusan retraining." | User (berperan sebagai "tim DS", proyek solo) dikonfirmasi eksplisit lewat `AskUserQuestion` setelah ditunjukkan payload notifikasi nyata — jawaban: "Ya, cukup jelas". |

## Keputusan Final

Lihat [`decisions.md`](./decisions.md) — kesepakatan tertulis (Bagian 5.3: kanal, informasi, ekspektasi manual) + 6 keputusan teknis, termasuk 1 kendala teknis (bug encoding verdict vs konvensi Grafana) ditemukan+dipecahkan dengan root-cause lengkap.

## Perubahan dari Plan Awal

Satu penyimpangan signifikan dari rencana: alert rule versi PERTAMA (Task 4 di plan, `condition: A` langsung ke query mentah) ternyata TIDAK BEKERJA sama sekali meski ter-provisioning tanpa error — baru ketahuan lewat verifikasi Task 7 (polling berulang, rule tetap "inactive" padahal data Prometheus jelas ada). Investigasi via `/api/ds/query` (isolasi query dari mesin alerting) menemukan root cause (konvensi nonzero=alerting Grafana vs encoding verdict M3.6) dan fix (expression Threshold) diterapkan LANGSUNG di checkpoint yang sama — bukan ditunda, karena tanpa fix ini seluruh milestone tidak punya bukti fungsional apa pun.

Verifikasi Checkpoint 2 (resolved state) memakan waktu lebih lama dari perkiraan (~5 menit, bukan langsung) — ditemukan konsisten dengan `group_interval` default Alertmanager Grafana yang tidak dikonfigurasi eksplisit di provisioning ini. Dicatat sebagai observasi, bukan bug (perilaku ini WAJAR/diharapkan untuk sistem alerting production-grade — mencegah notifikasi flapping).

## Keterbatasan dan Item Terbuka

- **Tujuan webhook masih endpoint uji (webhook.site), bukan tujuan produksi** — KT-10 (`docs/keputusan-tertunda.md`) baru, ditunda sampai web chat user (di luar cakupan proyek ini) selesai dibangun.
- **`group_interval` Alertmanager memakai default Grafana** (tidak dikonfigurasi eksplisit) — resolved notification bisa tertunda beberapa menit dibanding waktu resolve sesungguhnya. Provisional, bisa disesuaikan (`group_interval` custom di notification policy) kalau responsivitas lebih cepat dibutuhkan nanti.
- **PSI/p-value mentah TIDAK inline di pesan notifikasi** — perlu klik link dashboard untuk detail lengkap. Keputusan sadar (Keputusan #4 `decisions.md`) demi kesederhanaan provisioning, dikonfirmasi cukup oleh user (KK2).
- **`repeat_interval: 4h` adalah angka provisional** (bukan literatur formal) — bisa disesuaikan kalau pola trafik drift nyata (frekuensi generator sintetis, M2.9) berubah signifikan.
- **Notifikasi hanya untuk verdict "stop", bukan "flag"** — konsisten semantik M3.6, tapi berarti sinyal "waspada dini" (flag) tidak pernah sampai ke kanal notifikasi, cuma terlihat di dashboard (M3.6).

## Follow-up

- Begitu web chat user selesai dibangun: ganti `DRIFT_NOTIFICATION_WEBHOOK_URL` di Secret `monitoring-secrets`, verifikasi ulang KK1 terhadap tujuan baru (KT-10).
- M3.8 (Dashboard dan Alerting Terpadu): panel M3.5/M3.6 dan alerting M3.7 sudah berjalan di infrastruktur yang SAMA — M3.8 kemungkinan besar murni konsolidasi tata letak, bukan membangun ulang.
- Pertimbangkan `group_interval` custom kalau kebutuhan notifikasi resolved yang lebih cepat muncul nyata.
