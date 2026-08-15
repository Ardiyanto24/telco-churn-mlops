# Rancangan Simulasi — Milestone 3.12

> Setiap section di bawah ditulis SEBELUM eksekusi simulasinya (bukan ditulis mundur/backdated) — dikunci sebagai ekspektasi terukur, lalu diaudit setelah eksekusi selesai (section "Audit" ditambahkan di bawah tiap rancangan, bukan menggantikannya).

## Simulasi 1 — Gerbang Kualitas Data Stop

**Ditulis:** sebelum Task 11 (eksekusi) dijalankan.

**Teknik:** Panggil `run_gate()` (`src/churn_prediction/quality/gate.py`) langsung dengan DataFrame buatan kecil yang punya >10% NULL di salah satu kolom fitur, `source_table="_verification_probe_m312"` (nama probe BARU, terisolasi — belum pernah dipakai sebelumnya, tidak menyentuh baseline `telco_customers_source`/`telco_customers_synthetic` produksi), `record_history=True` (supaya tercatat nyata di `quality.gate_run_history`, pola M3.8). Berdasar kode gate.py/checks.py yang sudah dibaca: `NULL_STOP_THRESHOLD=0.10` adalah ambang ABSOLUT (`check_null_proportion`, TIDAK butuh baseline historis sama sekali untuk trigger stop lewat jalur NULL) — konsisten klaim M3.8 sebelumnya.

**Ekspektasi hasil terukur (DIKUNCI sebelum eksekusi):**

| # | Ekspektasi | Cara verifikasi |
|---|---|---|
| E1 | `GateResult.verdict == "stop"` langsung dari pemanggilan pertama, TANPA perlu baseline historis (jalur NULL check bersifat ambang absolut) | Baca return value `run_gate()` langsung |
| E2 | Baris baru tercatat di `quality.gate_run_history` dengan `source_table='_verification_probe_m312'`, `verdict='stop'` | Query `SELECT source_table, verdict, run_at FROM quality.gate_run_history WHERE source_table='_verification_probe_m312' ORDER BY run_at DESC LIMIT 1;` |
| E3 | Alert Grafana `QualityGateStop` bertransisi ke status Firing dalam siklus evaluasi wajar (≤2 menit, pola M3.8) | Cek query datasource Prometheus/Postgres yang dipakai alert rule, ATAU tunggu payload webhook |
| E4 | Webhook `pipeline-webhook-receiver` (webhook.site, M3.8) menerima payload dengan `status:"firing"`, `alertname:"QualityGateStop"` | Cek riwayat request di webhook.site |
| E5 | Entri runbook "2b. Gerbang Kualitas Data Verdict Stop" (`docs/07-runbook-operasional/runbook-operasional.md`) bisa diikuti PERSIS tanpa perlu buka dokumen lain untuk tahu langkah diagnosis dasar (query `gate_run_history`, cek webhook) | Diikuti manual Task 12, dicatat kalau ada langkah ambigu/kurang |

**Audit (diisi SETELAH Task 12 selesai):**

| # | Ekspektasi | Realisasi | Hasil |
|---|---|---|---|
| E1 | Verdict `stop` langsung tanpa baseline historis | `run_gate()` mengembalikan `verdict='stop'` pada pemanggilan PERTAMA (run_id 1304), check `null_proportion` = "Kolom ['tenure','monthly_charges'] punya proporsi NULL hingga 40.0% -- di atas ambang stop (10%)"; check `volume`/`category_distribution` "Baseline belum cukup data (<3 run) -- check dilewati" (dikonfirmasi jalur ambang absolut, tidak butuh baseline) | **MATCH** |
| E2 | Baris baru `quality.gate_run_history` dengan `source_table`/`verdict` sesuai | Query mengembalikan `(1304, '_verification_probe_m312', 'stop', 2026-08-15 23:50:32 UTC)` | **MATCH** |
| E3 | Alert `QualityGateStop` Firing dalam ≤2 menit | `startsAt: 2026-08-15T23:51:20Z` — 48 detik sejak `run_at`, status Grafana Alertmanager API = `active` | **MATCH** |
| E4 | Webhook `pipeline-webhook-receiver` menerima payload `status:"firing"`, `alertname:"QualityGateStop"` | Request masuk webhook.site pukul 23:51:56 UTC, payload persis `{"receiver":"pipeline-webhook","status":"firing","alerts":[{"status":"firing","labels":{"alert_category":"pipeline_infra_failure","alertname":"QualityGateStop","failure_type":"quality_gate_stop",...` | **MATCH** |
| E5 | Entri runbook "2b" bisa diikuti PERSIS tanpa buka dokumen lain | Query SQL di Diagnosis langkah 1 dijalankan APA ADANYA (substitusi `<source_table>`), berhasil tanpa modifikasi. **DEVIASI KECIL ditemukan**: entri TIDAK menyebutkan env var/cara koneksi Postgres yang dipakai (`QUALITY_GATE_DB_URL`) — pembaca yang belum tahu konvensi proyek ini harus menebak/cari sendiri. Langkah Respons 1-3 (investigasi sumber data) secara desain tidak relevan untuk skenario PROBE buatan ini (bukan insiden data asli) — TIDAK dihitung sebagai gap, itu memang sifat simulasi. Langkah Respons 4 ("gerbang bekerja seperti dirancang") akurat. | **DEVIASI KECIL — DIPERBAIKI** |

**Perbaikan runbook yang dilakukan:** Ditambahkan catatan env var koneksi (`QUALITY_GATE_DB_URL` dari `.env`) di Diagnosis langkah 1 entri "2b" (`docs/07-runbook-operasional/runbook-operasional.md`).

**Kesimpulan:** 4/5 butir ekspektasi MATCH sempurna, 1 butir (E5) MATCH dengan deviasi kecil yang langsung diperbaiki di tempat. Simulasi 1 SELESAI — teknik gerbang kualitas data terisolasi terbukti aman (tidak menyentuh baseline/data produksi), mekanisme end-to-end (gerbang → tabel riwayat → Prometheus exporter → Grafana alert → webhook) terbukti utuh bekerja untuk `source_table` baru sekalipun (dinamis, bukan hardcode).

---

## Simulasi 2 — Rollback Model

**Ditulis:** sebelum Task 16 (eksekusi) dijalankan.

**Kondisi awal (dicek read-only sebelum rancangan ini dikunci):** `resolve_alias_version("champion")` = **versi 1**. Registry punya 5 versi terdaftar (1-5, dicek via `MlflowClient().search_model_versions()`). Versi TARGET rollback sementara: **versi 5** (versi tertinggi/terbaru, jelas valid dan sudah teregistrasi — dipakai HANYA untuk uji mekanisme alias-swap, BUKAN klaim versi 5 "lebih baik").

**Teknik:** `set_active_alias(version, alias="champion")` (`src/churn_prediction/inference/registry.py`) — promosikan alias `champion` ke versi 5, verifikasi, LALU kembalikan ke versi 1 (kondisi awal) sebagai bagian dari task yang SAMA (pola M2.8/M3.4).

**Ekspektasi hasil terukur (DIKUNCI sebelum eksekusi):**

| # | Ekspektasi | Cara verifikasi |
|---|---|---|
| E1 | Setelah `set_active_alias("5", "champion")`, `resolve_alias_version("champion")` mengembalikan `"5"` SEGERA (resolve query langsung ke registry MLflow, bukan cache) | Panggil `resolve_alias_version("champion")` tepat setelah `set_active_alias()` |
| E2 | Setelah `set_active_alias("1", "champion")` (restore), `resolve_alias_version("champion")` kembali ke `"1"` | Panggil ulang `resolve_alias_version("champion")` |
| E3 | Tidak ada error/exception di kedua pemanggilan `set_active_alias()` | Observasi langsung eksekusi |
| E4 | Entri runbook "4. Rollback Mendesak — Versi Model" bisa diikuti PERSIS tanpa ambigu soal command/cara verifikasi | Diikuti manual Task 16, dicatat kalau ada langkah ambigu/kurang |

**Catatan risiko:** Real-time API `churn-api` (kalau pod live sedang berjalan) akan mendeteksi perubahan alias lewat refresh loop ~30 detik (M3.4) — SELAMA window singkat ini (promosi→restore), request `/predict` nyata (kalau ada) akan diproses model versi 5, bukan versi 1. Window ini dijaga seminimal mungkin (restore SEGERA setelah E1 diverifikasi, bukan ditunda).

**Audit (diisi SETELAH Task 16 selesai):**

| # | Ekspektasi | Realisasi | Hasil |
|---|---|---|---|
| E1 | `set_active_alias("5","champion")` -> `resolve_alias_version("champion")` == `"5"` segera | Dijalankan persis, output `setelah promosi: 5` | **MATCH** |
| E2 | `set_active_alias("1","champion")` (restore) -> `resolve_alias_version("champion")` == `"1"` | Dijalankan persis, output `setelah restore: 1` | **MATCH** |
| E3 | Tidak ada error/exception di kedua pemanggilan | Kedua pemanggilan sukses tanpa traceback | **MATCH** |
| E4 | Entri runbook "4" bisa diikuti PERSIS tanpa ambigu | Diagnosis langkah 1 dan Langkah Respons 1-2 diikuti APA ADANYA (command Python persis seperti tertulis), berhasil first-try tanpa modifikasi. TIDAK ada gap ditemukan pada bagian yang diuji. | **MATCH** |

**Catatan cakupan audit (bukan deviasi, keputusan sadar):** "Verifikasi Selesai" runbook entri 4 juga menyebut real-time API mendeteksi perubahan lewat refresh loop ~30-42 detik (M3.4) — bagian ini TIDAK diuji ulang independen di simulasi ini karena alias di-restore SEGERA setelah E1 (dalam hitungan detik, sesuai catatan risiko rancangan di atas) untuk meminimalkan window champion menunjuk ke versi 5 di produksi. Klaim timing ~30-42 detik bersandar pada verifikasi M3.4 sebelumnya (`milestones/3.4-.../report.md`), bukan diverifikasi ulang di sini — trade-off sadar antara kelengkapan audit vs meminimalkan risiko operasional pada milestone penutup ini.

**Kesimpulan:** 4/4 butir ekspektasi terukur MATCH sempurna, nol deviasi, nol perbaikan runbook diperlukan untuk entri ini. Simulasi 2 SELESAI — alias `champion` dikonfirmasi kembali ke versi 1 (state produksi tidak berubah permanen).
