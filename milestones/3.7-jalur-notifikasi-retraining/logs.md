# Logs — Milestone 3.7: Jalur Notifikasi Retraining ke Data Scientist

## Checkpoint 1 — Provisioning Grafana Alerting

Token webhook.site dibuat (`POST https://webhook.site/token`, tanpa login) — URL `https://webhook.site/43011751-671e-43c9-9d63-2f70e245a94e`. Diuji langsung (`POST` ping + `GET .../requests`) sebelum dipakai — berfungsi.

Key `DRIFT_NOTIFICATION_WEBHOOK_URL` ditambahkan ke Secret `monitoring-secrets` (`kubectl patch`).

**Docker Desktop ditemukan MATI (lagi)** saat mulai kerja checkpoint ini — `kubectl get pods` gagal connect ke API server. Di-restart via PowerShell (`Start-Process "Docker Desktop.exe"`), cluster kembali normal dalam ~1-2 menit, seluruh pod monitoring (`drift-exporter`, `grafana`, `pipeline-health-exporter`, `prometheus`) tetap `Running` dengan age lama (12-17 jam) TANPA restart kali ini — beda dari insiden M3.6 (semua pod restart serentak) — kemungkinan Docker Desktop kali ini shutdown lebih "bersih".

`infra/k8s/monitoring/grafana-alerting-configmap.yaml` ditulis — contact point (`webhook`, `$__env{DRIFT_NOTIFICATION_WEBHOOK_URL}`), alert rule (`expr: feature_drift_verdict == 0`, `condition: A` langsung), notification policy (route `alert_category=drift_retraining`). `grafana-deployment.yaml` diupdate (volume mount `alerting`).

`kubectl apply` + restart Grafana — provisioning ter-load TANPA error di log. Verifikasi API: `/api/v1/provisioning/contact-points` mengonfirmasi `$__env{}` BERHASIL ter-expand jadi URL asli (bukan literal string) — risiko yang dicatat di plan TERBUKTI aman.

**Bug ditemukan+diperbaiki**: rule ter-provisioning bersih, TAPI status tetap "inactive" 0 instance meski dicek berulang (polling ~2.5 menit) — padahal query manual ke Prometheus (`feature_drift_verdict{feature_name=~"service_count|tenure"}`) mengonfirmasi NYATA ada 2 series dengan value=0 (verdict stop, temuan asli M3.6). Diinvestigasi lewat `/api/ds/query` (menjalankan query PERSIS seperti rule) — query itu sendiri BENAR mengembalikan 2 series. Root cause ditemukan: Grafana alerting, kalau `condition` menunjuk LANGSUNG ke query mentah tanpa expression Threshold, mengevaluasi truthy berdasar NILAI (nonzero=alerting) — nilai `0` (stop, verdict paling parah) dianggap "tidak alerting", bertentangan langsung dengan encoding `feature_drift_verdict` (`2=pass/1=flag/0=stop`).

**Fix**: tambah expression `threshold` (refId B, `A < 1`, `datasourceUid: __expr__`), `condition: B`. Diverifikasi ulang lewat `/api/ds/query` MANUAL dulu (test isolasi expression sebelum apply ke rule) — hasil PERSIS benar: `service_count`→1 (true), `tenure`→1, 28 fitur lain→0. `kubectl apply` + restart Grafana lagi.

Setelah fix, rule LANGSUNG `firing` (dalam <1 menit, tanpa perlu trigger manual apa pun) — `service_count`+`tenure` state `Alerting`, 28 fitur lain `Normal` (dikonfirmasi per-instance via `/api/prometheus/grafana/api/v1/rules`). Webhook.site mengonfirmasi notifikasi NYATA sudah terkirim OTOMATIS dari data produksi asli (bukan simulasi) — payload lengkap (`feature_name`, `startsAt`, deskripsi konteks pembanding, link dashboard, penegasan retraining manual).

**Selesai, commit:** `51c2671` (feat).

## Checkpoint 2 — Verifikasi KK1 (Uji Coba Terkontrol)

`compute_drift.py --mode current --override-current` dijalankan (reuse file override M3.6, `tenure_group_G2_2_18`+`monthly_to_total_ratio` digeser ekstrem). Setelah polling ~2.5 menit (siklus scrape `drift_exporter` 30s + evaluasi rule 1m + delay Alertmanager grouping), webhook.site menerima request KETIGA: `[FIRING:4]` — 2 fitur asli (`service_count`/`tenure`) + 2 fitur baru dari override, SEMUA status `firing`.

`compute_drift.py --mode current` (tanpa override) dijalankan untuk restore. Rule state (`/api/prometheus/...`) LANGSUNG mengonfirmasi cuma `service_count`/`tenure` tersisa `Alerting`, 2 fitur ter-restore kembali `Normal` — TAPI notifikasi "resolved" webhook BELUM masuk sampai ~5 menit kemudian (polling total ~5 menit sebelum request KEEMPAT muncul) — konsisten `group_interval` default Alertmanager Grafana (tidak dikonfigurasi eksplisit di provisioning ini, jadi pakai default) yang menahan update grup sebelum dikirim ulang.

Request KEEMPAT dikonfirmasi: `[FIRING:2, RESOLVED:2]` — `monthly_to_total_ratio`+`tenure_group_G2_2_18` status `resolved` dengan `endsAt` terisi, `service_count`+`tenure` TETAP `firing` (`endsAt` kosong). Bukti definitif Grafana melacak state PER-FITUR secara independen, bukan broadcast status grup yang sama untuk semua.

**Selesai** — tidak ada file berubah di checkpoint ini (murni verifikasi), digabung commit Checkpoint 3.

## Checkpoint 3 — Dokumentasi dan Penutupan

KT-10 ditulis (`docs/keputusan-tertunda.md`) — tujuan akhir webhook (web chat user, di luar cakupan proyek ini) ditunda sampai web chat itu selesai dibangun.

`decisions.md` ditulis — kesepakatan tertulis (Bagian 5.3) + 6 keputusan teknis, termasuk kronologi lengkap bug Threshold expression.
