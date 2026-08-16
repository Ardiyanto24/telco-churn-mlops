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

---

## Simulasi 3 — Real-Time API Down/Lambat

**Ditulis:** sebelum Task 20 (eksekusi) dijalankan.

**Kondisi awal (dicek read-only sebelum rancangan ini dikunci):** `kubectl get pods -n churn-prediction` menunjukkan **3 pod** (1 lama `thvdt` AGE 93m, 2 baru `rzwrx`/`xjxfq` AGE 44s, keduanya `0/1 Not Ready`) — HPA (M3.11, masih aktif) baru scale-up ke `maxReplicas:3` akibat CPU util 266%/70%, kemungkinan noise lingkungan tidak terkait simulasi ini (konsisten karakteristik KD-3: CPU bursty meski beban ringan). `curl /healthz`+`/readyz` ke Service (load-balanced) tetap 200 (pod lama masih melayani). Kondisi multi-pod ini DITERIMA APA ADANYA untuk simulasi ini (bukan ditunda menunggu stabil 1 replica) — teknik (`kubectl set env` di level Deployment) mempengaruhi SEMUA pod via rolling update terlepas jumlah replica saat ini.

**Teknik:** `kubectl set env deployment/churn-api -n churn-prediction MLFLOW_TRACKING_URI=<URI tidak valid>` (override sementara di level Deployment, pola sama M3.2/3.3/3.4/M3.11 CP2), amati `/healthz` vs `/readyz`, LALU `kubectl set env deployment/churn-api -n churn-prediction MLFLOW_TRACKING_URI-` (hapus override, kembali ke Secret asli `churn-api-secrets`).

**Ekspektasi hasil terukur (DIKUNCI sebelum eksekusi):**

| # | Ekspektasi | Cara verifikasi |
|---|---|---|
| E1 | Setelah override diterapkan, pod BARU (hasil rolling update) `/healthz` tetap 200 SELAMA `startupProbe` budget belum habis (proses hidup) | `kubectl get pods` + `curl` langsung ke pod baru (port-forward kalau perlu) |
| E2 | `/readyz` pod baru mengembalikan non-200 (model/registry tidak reachable) | `curl` ke `/readyz` |
| E3 | Log pod baru menunjukkan retry backoff MLflow (`psycopg2.OperationalError`/`SQLAlchemy engine could not be created`, pola M3.11 CP2) | `kubectl logs <pod-baru> -n churn-prediction` |
| E4 | Setelah override dihapus (restore Secret asli), `/readyz` kembali 200 dalam waktu wajar (rolling update baru, bukan permanen) | `curl /readyz` berulang sampai 200 |
| E5 | Entri runbook "3. Real-Time API Down/Lambat" bisa diikuti PERSIS untuk membedakan liveness vs readiness tanpa baca kode aplikasi | Diikuti manual Task 20, dicatat kalau ada langkah ambigu/kurang |

**Catatan risiko:** Trafik Service TETAP dilayani pod LAMA yang sehat selama pod baru (dengan config rusak) belum Ready (`maxUnavailable:0`, M3.11 Keputusan #3) — downtime diperkirakan nol/minimal, pola sama M3.11 CP2. Restore dilakukan SEGERA setelah E1-E3 terverifikasi (tidak menunggu retry backoff habis total, yang bisa tak terbatas untuk host benar-benar invalid).

**Audit (diisi SETELAH Task 20 selesai):**

**Insiden operasional selama eksekusi (dicatat transparan):** Sebelum override diterapkan, HPA (M3.11, masih aktif dari milestone sebelumnya) sudah scale-up ke 3 replica akibat noise CPU tidak terkait simulasi ini. Saat override diterapkan (`kubectl set env`), rolling update mencoba membuat pod ke-4 (`maxSurge:1` di atas 3 replica existing) TAPI **stuck `Pending`** — `FailedScheduling: Insufficient memory` (4 pod x 400Mi requests melebihi memori node tersedia saat itu). Diperbaiki dengan `kubectl scale deployment/churn-api --replicas=1` (membebaskan memori) SEBELUM pod baru berhasil schedule — deviasi kecil dari rancangan awal (yang tidak mengantisipasi kontensi memori dari HPA), TAPI konsisten prinsip "diterima apa adanya" yang sudah dicatat di rancangan.

| # | Ekspektasi | Realisasi | Hasil |
|---|---|---|---|
| E1 | `/healthz` pod baru tetap 200 selama startupProbe budget belum habis | **DEVIASI SIGNIFIKAN**: `/healthz` pod baru (`5cbc5df598-7br8g`, diuji langsung via port-forward, BUKAN lewat Service) mengembalikan `000` (connection refused) SELAMA seluruh window pengamatan (~3 menit, 17x startup probe gagal) — port TIDAK PERNAH terbuka. Berbeda dari asumsi rancangan (yang menyamakan dengan pola M3.2 "host unreachable tapi valid" -> app buka port dulu baru gagal readyz). Untuk host yang GAGAL RESOLVE DNS (kasus ini, sama persis M3.11 CP2), retry backoff terjadi SEBELUM Uvicorn mulai listen -- healthz JUGA gagal, bukan cuma readyz. | **DEVIASI — RUNBOOK DIPERBAIKI** |
| E2 | `/readyz` pod baru non-200 | Konsisten dengan E1 -- juga `000` (port belum terbuka sama sekali, readyz tidak relevan lagi karena healthz sendiri sudah gagal) | **MATCH SEBAGIAN** (non-200 benar, tapi bukan karena readyz spesifik gagal -- seluruh port belum terbuka) |
| E3 | Log pod baru menunjukkan retry backoff MLflow | `kubectl logs` menunjukkan PERSIS: `psycopg2.OperationalError: could not translate host name "invalid-host-m312" to address` + retry backoff eksponensial (3.1s -> 6.3s -> 12.7s -> 25.5s -> 51.1s) | **MATCH** |
| E4 | Setelah restore, `/readyz` kembali 200 dalam waktu wajar | `kubectl set env ... MLFLOW_TRACKING_URI-` -> pod rusak `Terminating`, pod LAMA (`thvdt`, tidak pernah diganti -- hash pod template kembali sama seperti semula) tetap `1/1 Ready` sepanjang waktu -- `curl /healthz`+`/readyz` via Service 200 segera setelah restore diverifikasi | **MATCH** |
| E5 | Entri runbook "3" bisa diikuti PERSIS tanpa baca kode aplikasi | **DEVIASI DITEMUKAN**: langkah Diagnosis 2-3 runbook bilang `curl http://localhost/healthz`/`/readyz` -- ini menargetkan Service (load-balanced), yang SELAMA pod lama masih Ready akan SELALU mengembalikan 200 dari pod LAMA, TIDAK PERNAH menunjukkan kegagalan pod BARU secara spesifik. Untuk diagnosis pod baru yang specifically bermasalah, runbook TIDAK menyebutkan perlu `kubectl port-forward pod/<nama-pod-spesifik>` atau `kubectl exec` -- gap nyata, ditemukan lewat pengalaman langsung simulasi ini. | **DEVIASI — RUNBOOK DIPERBAIKI** |

**Perbaikan runbook yang dilakukan:**
1. Diagnosis Real-Time API Down/Lambat ditambah catatan: `curl` ke Service (`localhost`) hanya representatif untuk pod TUNGGAL atau saat SEMUA pod bermasalah -- untuk diagnosis pod spesifik selama rolling update, gunakan `kubectl port-forward pod/<nama-pod> <port-lokal>:8000` lalu `curl localhost:<port-lokal>/healthz`.
2. Poin "healthz 200, readyz non-200: model/registry tidak reachable" diperjelas: ini pola untuk host VALID tapi unreachable (M3.2). Untuk host yang GAGAL RESOLVE DNS sama sekali, healthz JUGA bisa gagal (port belum terbuka) -- kedua pola dibedakan eksplisit.

**Kesimpulan:** 2/5 MATCH penuh, 1 MATCH sebagian, 2 DEVIASI signifikan ditemukan dan LANGSUNG diperbaiki di runbook -- justru pembuktian paling kuat kenapa audit pra-registrasi (rancangan dulu, baru eksekusi) berguna: rancangan yang ditulis dari asumsi (byproduct generalisasi berlebih dari precedent M3.2) TERBUKTI tidak akurat untuk kasus DNS-gagal-total, dan gap followability runbook (Service vs pod spesifik) tidak akan ketemu tanpa benar-benar mengikuti langkah tertulis secara harfiah.

---

## Simulasi 4 — Drift Terdeteksi

**Ditulis:** sebelum Task 23 (eksekusi) dijalankan.

**Kondisi awal (dicek read-only sebelum rancangan ini dikunci):** Cluster stabil 1 pod `1/1 Ready`, HPA `cpu: 25%/70%`, `REPLICAS: 1` (kondisi bersih, tidak ada insiden berjalan dari Checkpoint 5).

**Teknik:** `python scripts/compute_drift.py --mode current --override-current <path-json>` — JSON override berisi `{"tenure": [nilai-nilai ekstrem]}` (fitur numerik, pola M3.6/3.7), memaksa PSI fitur `tenure` melewati ambang stop (≥0.25) dibanding baseline.

**Ekspektasi hasil terukur (DIKUNCI sebelum eksekusi):**

| # | Ekspektasi | Cara verifikasi |
|---|---|---|
| E1 | Fitur `tenure` verdict berubah jadi `stop` (PSI ≥0.25 dan/atau p-value <0.01) | Baca output skrip / query `drift.drift_check_results` |
| E2 | Baris baru tercatat `drift.drift_check_results` untuk `feature_name='tenure'` | Query langsung |
| E3 | Alert `DriftThresholdExceeded` Firing dalam siklus evaluasi Grafana (~1 menit interval, pola M3.12 Checkpoint 3 -- alert QualityGateStop firing ~48 detik) | Grafana Alertmanager API |
| E4 | Webhook `drift-webhook-receiver` (`https://webhook.site/43011751-671e-43c9-9d63-2f70e245a94e`) menerima payload sesuai skema M3.7 | Cek riwayat request webhook.site |
| E5 | Setelah override dihapus/dijalankan ulang mode normal (tanpa `--override-current`), verdict `tenure` kembali `pass`/`flag`, alert berubah status Resolved | Jalankan `compute_drift.py --mode current` tanpa override, cek ulang |
| E6 | Entri runbook "1. Drift Terdeteksi" bisa diikuti tanpa perlu baca `notebook-audit.md`/`decisions.md` M3.6 untuk paham artinya | Diikuti manual Task 24, catat kalau ada langkah ambigu/kurang -- **PERHATIAN KHUSUS** (pelajaran Checkpoint 5): validasi juga apakah instruksi runbook akurat untuk KEDUA jalur verifikasi (Postgres langsung DAN webhook), jangan asumsikan generalisasi dari milestone lain otomatis akurat |

**Catatan risiko:** `compute_drift.py --mode current` menulis PREDIKSI BARU ke `drift.drift_check_results` (bukan `predictions.batch_predictions` -- tidak menyentuh data prediksi produksi), current-window dihitung dari `telco_customers_synthetic` REAL (bukan data buatan seluruhnya, hanya SATU fitur di-override) -- pola SAMA PERSIS M3.6/3.7, sudah terbukti aman berulang kali sebelum ini.

**Audit (diisi SETELAH Task 24 selesai):** `[DIISI SETELAH EKSEKUSI]`
