# Logs — Milestone 3.11: Rollback Deployment dan Resource Sizing

## Checkpoint 1 — Keputusan Terdokumentasi + Rollback: Konfigurasi Eksplisit

- Ditulis `decisions.md` awal (6 Keputusan Desain + 2 keputusan `AskUserQuestion`) sebelum implementasi apapun dimulai — commit `a041019 docs(milestone-3.11): checkpoint 1 - keputusan awal`.
- Edit `infra/k8s/deployment.yaml`: tambah `spec.strategy.rollingUpdate.{maxSurge:1, maxUnavailable:0}`, `spec.revisionHistoryLimit:10`, perbaiki komentar salah rujuk "M3.7" jadi "M3.11" pada blok resources.
- `kubectl apply -f infra/k8s/deployment.yaml` — dikonfirmasi config-only change (field Deployment-level, bukan Pod-template) TIDAK memicu rollout baru: pod `churn-api-578474d56-pfd5j` tetap sama (AGE 36h, RESTARTS 5 tidak bertambah) sebelum dan sesudah apply.
- `kubectl rollout history` mencatat baseline revisi 1-6 (semua `<none>` CHANGE-CAUSE — tidak ada anotasi historis dari milestone sebelumnya).
- `curl http://localhost/healthz` dan `/readyz` keduanya 200 — baseline sehat dikonfirmasi sebelum simulasi kegagalan Checkpoint 2.
- Commit `2d1f02f feat(milestone-3.11): checkpoint 1 - strategi rollout eksplisit`.

## Checkpoint 2 — Rollback: Simulasi Terkontrol + Verifikasi KK1

**Kondisi mesin saat uji coba:** 2026-08-16 ~04:47-04:50 WIB, Docker Desktop Kubernetes single-node lokal, tidak ada beban lain yang diketahui berjalan bersamaan.

- Disiapkan `deployment-broken.yaml` (scratchpad) — salinan manifest dengan `env: MLFLOW_TRACKING_URI=postgresql://invalid-host-m311:5432/mlflow` (override eksplisit di atas `envFrom` Secret asli, TIDAK mengubah Secret), anotasi `kubernetes.io/change-cause` di pod template.
- Dimulai loop polling `POST /predict` (payload valid, reuse `_valid_payload()` dari `tests/api/test_app.py`) tiap ~1.5 detik ke `http://localhost/predict`, berjalan di background (`poll_predict.py`) selama seluruh window Checkpoint 2.
- `kubectl apply -f deployment-broken.yaml` — `kubectl rollout status --timeout=60s` **timeout, tidak selesai** (bukti rollout macet), pesan: `1 old replicas are pending termination`.
- `kubectl get pods`: pod lama `churn-api-578474d56-pfd5j` tetap `1/1 Running`; pod baru `churn-api-849fcccd5-47gh8` stuck `0/1 Running` (BUKAN crash-loop).
- `kubectl get rs`: 2 ReplicaSet aktif — lama `DESIRED:1 CURRENT:1 READY:1`, baru `DESIRED:1 CURRENT:1 READY:0`.
- `kubectl describe pod churn-api-849fcccd5-47gh8`: event `Warning Unhealthy ... Startup probe failed: dial tcp ...: connect: connection refused` berulang — port belum terbuka.
- `kubectl logs churn-api-849fcccd5-47gh8`: konfirmasi root cause — `psycopg2.OperationalError: could not translate host name "invalid-host-m311" to address: Temporary failure in name resolution`, retry backoff eksponensial internal MLflow (6.3s → 12.7s → 25.5s → 51.1s), konsisten pola M3.2 KK3 (bedanya di sini host TIDAK PERNAH bisa resolve DNS sama sekali, bukan sekadar unreachable — jadi app akan retry TANPA BATAS, tidak seperti M3.2 di mana host valid tapi service down yang akhirnya membuka port setelah ~100 detik).
- Dipantau ~2,5 menit — kondisi stabil macet aman: pod lama terus melayani, pod baru terus gagal readiness, TIDAK ada dampak ke trafik.
- `kubectl rollout undo deployment/churn-api -n churn-prediction` → `deployment.apps/churn-api rolled back`.
- `kubectl rollout status --timeout=60s` → **sukses cepat**.
- `kubectl get rs`: ReplicaSet rusak (`849fcccd5`) `DESIRED:0`, pod-nya `Terminating`.
- `kubectl rollout history`: revisi 7 tercatat dengan `CHANGE-CAUSE` = anotasi simulasi (legible), revisi 8 = hasil undo.
- `curl /healthz` dan `/readyz` kembali 200 setelah rollback.
- **Bukti downtime (KK1):** log polling `poll_predict.py` — **121 baris total, 120 status 200, HANYA 1 non-200** (satu `ReadTimeout` di baris PERTAMA, SEBELUM deployment rusak diterapkan sama sekali — cold-start request setelah idle, bukan efek simulasi/rollback). Sepanjang seluruh window deployment rusak (~2,5 menit) DAN window rollback, **0 request gagal**.

**Kesimpulan KK1:** Simulasi deployment gagal health check berhasil di-rollback ke versi sebelumnya dengan downtime **nol** (bukan sekadar minimal) — dibuktikan dengan log request kontinu nyata, bukan asumsi teoretis. Downtime nol ini terjadi karena kombinasi `maxUnavailable:0` (Checkpoint 1, mencegah pod lama diturunkan sebelum pod baru Ready) — rollback (`kubectl rollout undo`) berperan membersihkan status `progressing=False` dan ReplicaSet rusak yang menganggur, bukan mencegah downtime itu sendiri (downtime sudah dicegah oleh strategi rollout).
