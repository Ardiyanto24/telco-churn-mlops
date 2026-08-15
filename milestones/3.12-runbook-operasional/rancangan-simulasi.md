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

**Audit (diisi SETELAH Task 12 selesai):** `[DIISI SETELAH EKSEKUSI]`
