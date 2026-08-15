# Decisions — Milestone 3.7: Jalur Notifikasi Retraining ke Data Scientist

## Konteks

Bagian 5.3 dokumen arsitektur ("Kontrak Retraining") mensyaratkan jalur notifikasi yang jelas saat drift (M3.6) melewati ambang batas — siapa/apa yang menerima, lewat kanal apa, dan penegasan retraining tetap manual kecuali disepakati lain. Dua putaran `AskUserQuestion` dipakai untuk menggali scope: putaran pertama (pilihan kanal Discord/Telegram/Email) dijawab user dengan konteks baru (sedang membangun web chat simulasi tim terpisah, di luar cakupan proyek ini); putaran kedua (lanjut sekarang vs tunda) dijawab user: lanjut sekarang, bangun mekanisme PENGIRIM notifikasi generik yang mudah diarahkan ulang nanti.

## Kesepakatan Tertulis (Kontrak Retraining, Bagian 5.3)

Ini bagian yang secara harfiah diminta sumber sebagai "kesepakatan tertulis dengan tim Data Scientist" — karena proyek solo, user SENDIRI berperan sebagai "tim Data Scientist" penerima notifikasi, kesepakatan ini adalah hasil `AskUserQuestion` + konfirmasi eksplisit user (bukan diasumsikan sepihak):

- **Kanal:** Webhook HTTP generik (JSON POST), dikirim oleh Grafana Alerting. Tujuan URL saat ini adalah endpoint uji sementara (webhook.site) — lihat KT-10 (`docs/keputusan-tertunda.md`) untuk rencana pengalihan ke web chat user yang sedang dibangun terpisah.
- **Informasi yang disertakan:** nama fitur yang drift (`feature_name`), verdict (selalu "stop" — hanya threshold stop yang memicu notifikasi, bukan flag), waktu mulai (`startsAt`)/waktu selesai kalau resolved (`endsAt`), deskripsi konteks pembanding (baseline data training vs data produksi terkini), link langsung ke dashboard Grafana untuk detail PSI/p-value lengkap, dan penegasan eksplisit bahwa retraining tetap keputusan manual.
- **Ekspektasi tindak lanjut:** SEPENUHNYA MANUAL (lihat Keputusan #1) — notifikasi murni sinyal "perlu ditinjau", bukan trigger otomatis ke pipeline training (yang memang tidak ada/di luar cakupan sistem ini).

## Keputusan Teknis

### 1. Retraining tetap manual (forced, bukan pilihan)

**Keputusan:** Sistem ini TIDAK memicu retraining otomatis dalam bentuk apa pun.

**Kenapa:** Bagian 5.3 dokumen arsitektur eksplisit: sistem "berhenti pada mendeteksi dan memberi sinyal". Training sepenuhnya di luar cakupan sistem ini (CLAUDE.md "Batas Implementasi Saat Ini") — tidak ada pipeline training eksternal dengan API/endpoint yang bisa dipanggil terstruktur dari sistem ini.

**Tidak ada alternatif dipertimbangkan** — forced by scope, bukan pilihan desain.

### 2. Grafana Alerting (webhook contact point) dipilih ketimbang script Python custom

**Keputusan:** Notifikasi dibangun MURNI lewat provisioning Grafana Alerting (contact point + alert rule + notification policy) — TIDAK ada kode Python baru sama sekali.

**Kenapa:** Prometheus+Grafana+`feature_drift_verdict` (dari `drift_exporter`, M3.6) SUDAH ada sejak M3.5/M3.6 — Grafana Alerting reuse 100% infrastruktur itu. Grafana native mengelola state firing/resolved dan `repeat_interval` (anti-spam) TANPA kode custom yang perlu menyimpan state sendiri (mis. "apakah notifikasi untuk fitur X sudah pernah dikirim"). Payload webhook Grafana adalah JSON generik terstruktur (`alerts[]` dengan `labels`/`annotations`/`status`/timestamps) — bukan format spesifik satu platform (beda dari Discord/Telegram/Email contact point yang formatnya terikat platform tsb) — PALING dekat dengan "API generik untuk mengirim notifikasi" yang diminta user, dan paling mudah diadaptasi endpoint penerima ATAupun mana pun nanti.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Script Python custom** (query `drift.drift_check_results`, bandingkan run sekarang vs sebelumnya, POST manual kalau ada verdict baru "stop") — DITOLAK: perlu membangun ULANG state-management (dedup notifikasi berulang) yang Grafana Alerting SUDAH punya gratis; lebih banyak kode untuk dijaga tanpa manfaat tambahan.
- **Discord/Telegram/Email contact point langsung** (dibahas putaran `AskUserQuestion` pertama) — DITOLAK setelah user klarifikasi web chat sendiri belum siap: memilih SATU platform sekarang cuma akan dibongkar lagi begitu web chat siap, sementara webhook generik TIDAK perlu dibongkar (cuma ganti URL).

### 3. URL webhook via Secret K8s + `$__env{}` templating (bukan hardcode di file yang dicommit)

**Keputusan:** `infra/k8s/monitoring/grafana-alerting-configmap.yaml` berisi `url: $__env{DRIFT_NOTIFICATION_WEBHOOK_URL}` — nilai sesungguhnya dari key baru di Secret `monitoring-secrets` (envFrom SUDAH ter-mount ke Grafana sejak M3.5, tidak perlu ubah manifest Deployment selain volume mount baru untuk folder provisioning `alerting`).

**Kenapa:** Konsisten pola kredensial-tidak-dicommit sejak M3.1 (`churn-api-secrets`) dst. Sekaligus PERSIS memenuhi kebutuhan "URL mudah diganti nanti" (Keputusan user) — ganti tujuan webhook cukup `kubectl patch` Secret + restart Grafana, TIDAK perlu ubah/commit file manapun.

**Diverifikasi empiris (bukan diasumsikan dari dokumentasi):** fitur `$__env{}` Grafana provisioning TERBUKTI bekerja di versi `12.3.0` yang dipakai proyek ini — `GET /api/v1/provisioning/contact-points` mengonfirmasi URL ter-expand jadi nilai asli, BUKAN string literal `$__env{...}`.

### 4. Alert rule query tunggal + Threshold expression eksplisit (BUKAN mengandalkan nilai mentah)

**Keputusan:** Alert rule punya 2 data query: refId A (`feature_drift_verdict`, raw instant query) dan refId B (expression tipe `threshold`, `A < 1`, `datasourceUid: __expr__`) — `condition: B`, BUKAN `condition: A` langsung.

**Kenapa (kendala teknis ditemukan+dipecahkan):** Percobaan PERTAMA pakai `condition: A` dengan `expr: feature_drift_verdict == 0` (filter di PromQL langsung) — rule ter-provisioning tanpa error, TAPI TIDAK PERNAH fire meski Prometheus terbukti punya data `feature_drift_verdict=0` nyata (dikonfirmasi query manual). Root cause: Grafana alerting, kalau `condition` menunjuk LANGSUNG ke hasil query mentah (tanpa expression Threshold/Reduce eksplisit), mengevaluasi ALERTING berdasar apakah NILAI hasil query non-zero — nilai `0` dianggap "tidak alerting" (konvensi nonzero=alerting), REGARDLESS bahwa PromQL `== 0` sudah memfilter series yang relevan. Encoding `feature_drift_verdict` (`drift/metrics.py` `verdict_to_value()`: 2=pass/1=flag/**0=stop**) PERSIS bentrok konvensi itu — verdict paling parah (stop, yang justru INGIN memicu notifikasi) punya nilai numerik 0, dianggap Grafana sebagai "aman".

**Fix:** Expression `threshold` (refId B) mengevaluasi `A < 1` secara eksplisit, MENGHASILKAN boolean 1/0 per series TERLEPAS dari nilai asli A — `condition: B` lalu benar mengacu ke hasil boolean itu, bukan nilai mentah verdict.

**Verifikasi:** Setelah fix, rule LANGSUNG firing dari data produksi nyata (2 fitur `service_count`/`tenure`, verdict stop sejak M3.6) — 28 fitur lain (verdict pass/flag, nilai 1-2) dengan BENAR tetap "Normal", dikonfirmasi lewat `/api/prometheus/grafana/api/v1/rules` per-instance state.

**Opsi yang Dipertimbangkan tapi Ditolak:** Ubah encoding `feature_drift_verdict` di `drift/metrics.py` (mis. stop=1 alih-alih 0) supaya cocok konvensi Grafana tanpa perlu expression tambahan — DITOLAK: mengubah kontrak metrik M3.6 yang sudah diverifikasi+dicommit demi kebutuhan alerting M3.7 semata, berisiko memecah panel dashboard M3.6 yang sudah bergantung ke encoding lama (value mapping "2=pass/1=flag/0=stop"). Expression Threshold adalah fix yang terisolasi di M3.7, tidak menyentuh M3.6 sama sekali.

### 5. Notifikasi HANYA untuk verdict "stop" (bukan "flag")

**Keputusan:** `expr: feature_drift_verdict` dgn threshold `< 1` — cuma menangkap verdict=0 (stop). Verdict=1 (flag) TIDAK memicu notifikasi.

**Kenapa:** Konsisten cara `combined_verdict()` M3.6 didesain — "stop" adalah level paling signifikan (PSI≥0.25 ATAU p-value<0.01), level yang benar-benar mengindikasikan tindakan mungkin diperlukan. "Flag" adalah level observasi/waspada (belum tentu actionable) — menotifikasi tiap flag berisiko spam mengingat temuan M3.6 sendiri (p-value sensitif ke sample size, beberapa fitur bisa flag/stop dari efek statistik semata).

**Tidak ada alternatif dipertimbangkan secara eksplisit ke user** — konsisten derivasi langsung dari semantik verdict M3.6 yang sudah final.

### 6. `repeat_interval: 4h` pada notification policy

**Keputusan:** Kalau kondisi "stop" menetap lama (seperti `service_count`/`tenure` yang sudah stop sejak M3.6), Grafana re-notifikasi paling cepat tiap 4 jam — bukan tiap kali `drift-monitoring.yml` (M3.6) jalan (event-driven, bisa lebih sering dari itu).

**Kenapa:** Menghindari spam notifikasi berulang untuk kondisi yang SAMA yang belum berubah — 4 jam dipilih sebagai titik tengah wajar (cukup jarang menghindari kelelahan notifikasi, cukup sering tetap relevan untuk kebutuhan portofolio/demo, bukan literatur formal — angka provisional, bisa disesuaikan kalau pola trafik nyata muncul).

## Kriteria Keberhasilan vs Bukti

**KK1** ("Simulasi drift melewati ambang batas berhasil memicu notifikasi... informasi cukup tanpa perlu bertanya balik"): terbukti GANDA — (a) notifikasi OTOMATIS dari data produksi ASLI (`service_count`/`tenure`, verdict stop sejak M3.6) terkirim tanpa intervensi apa pun begitu provisioning aktif; (b) uji coba terkontrol eksplisit (`compute_drift.py --override-current`, 2 fitur digeser ekstrem) memicu notifikasi BARU (`[FIRING:4]`, 2 fitur tambahan), lalu setelah direstore notifikasi "resolved" terkirim TEPAT untuk 2 fitur yang di-restore (bukan yang masih genuinely stop) — bukti Grafana benar-benar melacak state per-fitur, bukan broadcast sederhana.

**KK2** ("Tim Data Scientist mengonfirmasi jalur dan format notifikasi dapat dipakai sebagai dasar keputusan retraining"): lihat `report.md` — konfirmasi eksplisit user di chat (solo-project equivalent "tim DS").
