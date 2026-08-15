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

## Checkpoint 3 — Pemasangan `metrics-server`

- `kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml` — pod `metrics-server-859586b6b5-sw8df` terbuat, status `0/1 Running` bertahan.
- `kubectl logs -n kube-system deployment/metrics-server` mengonfirmasi ISU TLS DIKENAL LUAS Docker Desktop K8s (diprediksi eksplisit di plan): `tls: failed to verify certificate: x509: cannot validate certificate for 192.168.65.3 because it doesn't contain any IP SANs` — sertifikat kubelet self-signed tidak menyertakan IP node sebagai SAN.
- Fix: `kubectl patch deployment metrics-server -n kube-system --type=json -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'` — command persis didokumentasikan di `infra/k8s/metrics-server-patch.yaml` untuk reproducibility.
- `kubectl rollout status deployment/metrics-server -n kube-system` → sukses setelah patch.
- Verifikasi: `kubectl top nodes` → `docker-desktop 4068m 33% 1883Mi 71%`. `kubectl top pods -n churn-prediction` → `churn-api-578474d56-pfd5j 128m 341Mi` — angka NATIVE Kubernetes (bukan proxy `docker stats`), memory (341Mi) mendekati kisaran idle lama M3.3 (~364MiB) sebagai sanity check kasar; CPU (128m) sedikit di atas catatan lama M3.3 (~0.2%), kemungkinan residual dari rangkaian rollout/rollback Checkpoint 2 yang baru selesai — akan diverifikasi ulang dengan baseline idle bersih di Checkpoint 4.

## Checkpoint 4 — Uji Beban Terkontrol dengan Metrik Native K8s

`scripts/k8s_resource_load_test.py` ditulis dan diverifikasi smoke test bersih (concurrency=1/10 detik, 72 request, 0 error) sebelum dipakai skala penuh. Seluruh CSV mentah tersimpan di `milestones/3.11-rollback-deployment-resource-sizing/raw-data/`.

**Baseline idle** (120 detik, tanpa trafik): memory FLAT ~340-341Mi sepanjang window. CPU sampel pertama 683m (residual transient dari smoke test sebelumnya yang baru selesai), turun dan stabil ke **~89-142m** untuk mayoritas window — dipakai sebagai idle steady-state.

**Uji beban bertingkat (masing-masing 60 detik, jeda ~30 detik antar level):**

| Konkurensi | Request total | Error | Error % | Latency p50/p95 (ms) | CPU puncak/rata (m) | Memory puncak/rata (Mi) | Insiden |
|---|---|---|---|---|---|---|---|
| 1 | 456 | 0 | 0% | 115 / 245 | 1122 / 888 | 341 / 341 | - |
| 10 | 2292 | 2187 | 95,4% | 36 / 1351 | 1062 / 764 | 359 / 349 | Readiness+liveness probe timeout (`context deadline exceeded`), TANPA restart |
| 50 | 7680 | 7659 | 99,7% | 208 / 593 | 1012 / 658 | 367 / 361 | **Restart nyata** (`RESTARTS 5→6`) -- liveness probe gagal 3x berturut, pod di-kill+recreate Kubernetes, pulih otomatis ~85 detik |
| 100 | 6576 | 6576 | 100% | 557 / 2181 | 1089 / 720 | 462 / 451 | **Restart nyata kedua** (`RESTARTS 6→7`), pulih otomatis ~85 detik |

**Temuan kunci (signifikan, di luar dugaan awal):** CPU puncak **KONSISTEN di kisaran ~1,0-1,12 core (1012-1122m) di SEMUA level konkurensi 1-100** -- TIDAK naik proporsional dengan jumlah request paralel. Ini bukti kuat bahwa real-time API (M3.2) memproses request secara efektif SATU PER SATU (single-worker/blocking event loop terhadap kerja inference yang CPU-bound), bukan benar-benar paralel di dalam satu pod -- request tambahan mengantre alih-alih menambah pemakaian CPU. Akibatnya:
- **Limit CPU (1500m) SUDAH punya headroom memadai** terhadap puncak nyata yang pernah teramati (1122m) -- bukan sumber restart/error.
- **Root cause restart & error rate tinggi BUKAN kekurangan resource K8s** -- pod di-restart karena `/healthz`/`/readyz` tidak sempat dijawab tepat waktu ketika worker tunggal sibuk memproses antrean request yang menumpuk, BUKAN karena CPU throttled/OOM oleh cgroup.
- Memory naik terlihat jelas cuma di level 100 (peak 462Mi, dari baseline ~341Mi) -- kemungkinan buffer request yang mengantre di worker tunggal, TAPI masih jauh di bawah limit 768Mi (headroom ~40%).
- **Kedua restart adalah self-healing Kubernetes yang bekerja SEPERTI DIRANCANG** (livenessProbe M3.2/M3.3 Keputusan #3 -- restart proses yang macet) -- pulih otomatis ~85 detik tiap kali (konsisten pola M3.2 KK3 ~100 detik retry MLflow), TANPA intervensi manual, TANPA kehilangan data.

**Implikasi untuk cakupan M3.11:** Karakteristik arsitektur single-worker ini adalah properti kode real-time API (M3.2), BUKAN sesuatu yang bisa diperbaiki lewat penyesuaian `resources.requests`/`limits` K8s (di luar cakupan M3.11 -- lihat "Batas Implementasi Saat Ini" CLAUDE.md, mengubah desain concurrency API adalah scope M3.2). Dicatat sebagai keterbatasan diterima baru (KD-3, `docs/keterbatasan-diterima.md`) -- lihat `decisions.md` untuk detail lengkap.
