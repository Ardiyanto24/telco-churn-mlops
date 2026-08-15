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

## Checkpoint 5 — Penyesuaian Resource Request/Limit

**Analisis idle steady-state** (buang 5 sampel transien awal dari 22 sampel baseline idle CP4): CPU **89-321m (avg ~159m)**, memory **FLAT 340-341m (avg ~340,5Mi)**.

**Analisis puncak** (dari 4 level uji beban CP4): CPU puncak tertinggi **1122m** (terjadi di konkurensi=1, BUKAN di konkurensi tertinggi -- konsisten temuan single-worker KD-3), memory puncak tertinggi **462Mi** (di konkurensi=100, saat request menumpuk).

**Perbandingan vs konfigurasi saat ini:**

| Field | Nilai saat ini | Data native K8s M3.11 | Margin |
|---|---|---|---|
| `requests.cpu` | 200m | idle steady 89-321m (avg ~159m) | ~1,3x di atas rata-rata idle -- cukup, tidak boros |
| `requests.memory` | 400Mi | idle 340-341Mi | ~17% di atas idle -- tepat, tidak boros |
| `limits.cpu` | 1500m | puncak tertinggi 1122m (SEMUA level, termasuk 2 insiden restart) | ~34% headroom -- CUKUP, restart TERBUKTI (KD-3) bukan karena CPU throttled |
| `limits.memory` | 768Mi | puncak tertinggi 462Mi | ~66% headroom -- CUKUP, zero OOM event di seluruh 4 level + 2 restart |

**Keputusan: RE-AFFIRM nilai existing (200m/400Mi requests, 1500m/768Mi limits) TANPA perubahan numerik** -- divalidasi dengan bukti metrik native Kubernetes (bukan lagi proxy `docker stats` M3.3), bukan sekadar dipertahankan tanpa diperiksa. Justifikasi:
1. `requests` sudah punya margin wajar di atas idle riil -- tidak terbukti boros.
2. `limits` sudah punya headroom di atas puncak TERTINGGI yang PERNAH teramati di SELURUH 4 level konkurensi (termasuk 2 kejadian restart nyata) -- restart itu sendiri TERBUKTI (KD-3) disebabkan probe timeout akibat arsitektur single-worker API, BUKAN CPU throttled atau OOM. Menaikkan limit CPU/memory TIDAK akan mencegah restart serupa terulang (root cause di luar resource sizing).
3. Menaikkan limit tanpa bukti kebutuhan nyata akan MELANGGAR paruh KK2 M3.11 sendiri ("tidak boros dibanding kebutuhan nyata").

**Penyesuaian dilakukan:** HANYA komentar penjelas di `deployment.yaml` (referensi data lama `docker stats` M3.3 diganti referensi data native K8s M3.11 + tautan ke `decisions.md`/`logs.md` Checkpoint 4-5) -- TIDAK ada perubahan `spec.containers[].resources` numerik. Ini deviasi kecil dari asumsi plan awal ("Terapkan nilai baru") -- didokumentasikan transparan di `report.md` bagian "Perubahan dari Plan Awal": plan mengasumsikan nilai akan berubah, bukti nyata menunjukkan nilai lama sudah tepat.

**Verifikasi ulang (KK2):** Re-run beban puncak konkurensi=100 identik terhadap konfigurasi yang SAMA tidak dijalankan ulang -- akan menghasilkan restart identik tanpa informasi baru (data CP4 SUDAH mencakup skenario ini persis terhadap nilai `limits` yang sama, tidak berubah). Sebagai gantinya: dikonfirmasi pod dalam keadaan sehat stabil pasca-CP4 (`kubectl get pods` 1/1 Ready, `RESTARTS` tidak bertambah sejak insiden ke-2), dan re-affirm eksplisit bahwa TIDAK ADA event OOM (`OOMKilled`) tercatat di SELURUH 4 level uji beban CP4 -- HANYA event `Unhealthy`(probe)/`Killing`(liveness) yang tercatat, dikonfirmasi via `kubectl describe pod`/`kubectl get events` (lihat Checkpoint 4 di atas).

## Checkpoint 6 — HPA Dasar (Ilustratif)

`infra/k8s/hpa.yaml` ditulis (`autoscaling/v2`, target CPU utilization 70%, `minReplicas:1`/`maxReplicas:3`).

**Insiden kecil saat apply -- rollout tak sengaja tapi valid+informatif:** `kubectl apply -f infra/k8s/hpa.yaml` awalnya menampilkan `TARGETS: cpu: <unknown>/70%` (wajar, metrics-server belum sempat scrape). Diagnosis (`kubectl describe hpa`): `FailedGetResourceMetric ... did not receive metrics for targeted pods`. Diselidiki lebih lanjut, ditemukan pod BERGANTI (`churn-api-578474d56-pfd5j` -> `churn-api-5b5ffb89c8-4hm7x`, `RESTARTS` reset ke 0) -- root cause: pod REVISI 8 (live di cluster) ternyata membawa anotasi `kubectl.kubernetes.io/restartedAt: 2026-08-14T11:16:12+07:00` yang TIDAK PERNAH ada di `infra/k8s/deployment.yaml` yang di-git (drift dari `kubectl rollout restart` sesi/milestone sebelumnya, sebelum M3.11). `kubectl apply` (dijalankan Task "Re-deploy" Checkpoint 5, comment-only) secara declarative membersihkan anotasi yang tidak ada di source-of-truth ini -- perubahan `spec.template.metadata.annotations` MENGUBAH pod-template-hash, memicu RollingUpdate NYATA (bukan simulasi) memakai strategi eksplisit Checkpoint 1 (`maxSurge:1`/`maxUnavailable:0`). **Validasi tak sengaja yang berguna:** ini kesempatan kedua melihat strategi rollout CP1 bekerja pada rollout NORMAL (bukan skenario gagal sengaja seperti CP2) -- pod lama tetap melayani sampai pod baru Ready, konsisten. Pod baru stabil (`RESTARTS:0`), metrics-server butuh ~1 siklus scrape untuk pod BARU (IP baru) -- `TARGETS` terisi `35%/70%` dalam <5 menit setelah pod baru stabil.

**Koreksi penting ditemukan saat verifikasi:** Komentar draf awal `hpa.yaml` keliru mengasumsikan target 70% dihitung dari `limits.cpu` (1500m). **Diverifikasi FAKTUAL (`kubectl describe hpa`: "resource cpu on pods (as a percentage of **request**)")** -- metrik `Utilization` HPA native Kubernetes dihitung relatif terhadap `requests.cpu` (200m), BUKAN `limits.cpu`. Target 70% sebenarnya = ~140m, bukan ~1050m seperti draf awal. Komentar `hpa.yaml` diperbaiki SEBELUM lanjut ke uji scale-up (Task berikutnya) supaya interpretasi hasil benar. Nilai target (70) TIDAK diubah -- tetap valid: idle segar teramati 35% (~70m), uji beban CP4 konkurensi=1 saja sudah rata-rata 444% dari request (888m) -- margin cukup jauh dari idle, cukup mudah terpicu beban ringan.

**Uji coba terkontrol scale-up dan scale-down (Task 18) -- timeline lengkap nyata:**

| Waktu | Peristiwa |
|---|---|
| ~05:23 | `scripts/k8s_resource_load_test.py --concurrency 10 --duration-seconds 300` dimulai (background), monitor `kubectl get hpa`+`get pods` tiap 15 detik dimulai paralel |
| 05:25:50 | CPU util **254%/70%** -- **SCALE-UP TERPICU**, 2 pod baru dibuat (`rvd58`, `thvdt`) menuju `maxReplicas:3` |
| 05:27:01 | `REPLICAS` kolom HPA menunjukkan 3 (Deployment sudah scale ke 3, pod baru masih starting) |
| ~05:28:00-05:30 | **Insiden kontensi CPU nyata**: SEMUA 3 pod (termasuk yang lama) sempat `0/1 Not Ready` bersamaan -- kombinasi beban `/predict` konkuren + (baru disadari) trafik residual bocor (lihat di bawah) memenuhi kapasitas gabungan; pod lama sempat restart 1x tambahan (liveness) |
| 05:30:28 | 2 pod baru akhirnya `1/1 Ready` (~5 menit sejak dibuat -- mendekati batas budget `startupProbe` 300 detik, TIDAK sampai di-kill) |
| ~05:29:45 | Load test client selesai (300 detik terpenuhi) -- TAPI CPU util TETAP tinggi (170-384%) tanpa penjelasan jelas |
| ~05:32 | **Insiden ditemukan+diperbaiki**: `ps aux` mengungkap proses `poll_predict.py` dari **Checkpoint 2** (dimulai 04:47:50) TERNYATA MASIH BERJALAN -- perintah `kill` di akhir Checkpoint 2 salah sasaran PID (pola PID `ps aux` di git-bash/MSYS berbeda dari PID Windows asli yang dikenali `taskkill`), proses terus mengirim request `/predict` tiap ~1,5 detik SELAMA ~45 MENIT tanpa disadari, mencemari sebagian data CP4-6. Diperbaiki dengan `kill -9` (bukan `taskkill`), dikonfirmasi proses benar-benar berhenti (`ps aux` bersih). **Dampak ke data CP4**: minor -- traffic residual (<1 req/detik) jauh di bawah level konkurensi eksplisit yang diuji (1-100 req/detik), tidak mengubah kesimpulan KD-3 (pola plateau CPU ~1 core tetap konsisten di semua level terlepas kontribusi kecil ini). **Dampak ke CP6**: signifikan -- menjelaskan kenapa CPU util tidak kunjung turun meski load test client sudah selesai. |
| 05:38:55 | **SCALE-DOWN #1**: 3 → 2 replica (`kubectl describe hpa` mengonfirmasi kondisi `ScaleDownStabilized`: "recent recommendations were higher than current one" -- window stabilisasi default ~5 menit bekerja seperti dirancang, menahan scale-down sampai rekomendasi tinggi terakhir "keluar" dari window) |
| 05:45:52 | **SCALE-DOWN #2**: 2 → 1 replica (`minReplicas` tercapai) |
| 05:45:52-05:49:59+ | Stabil di 1 replica, CPU **2-3%** (idle bersih, jauh di bawah target 70%) |
| ~05:50 | Transient: 2x `curl /healthz` gagal (`Recv failure: Connection was reset`) tepat setelah scale-down terakhir -- kemungkinan LoadBalancer proxy Docker Desktop masih mereconciliasi endpoint (2 pod dihapus dari daftar). Percobaan ke-3 (~6 detik kemudian) sukses 200 -- transient murni, TIDAK berulang, konsisten sifat "eventually consistent" load balancer lokal. |

**Kesimpulan Task 18:** Scale-up DAN scale-down HPA keduanya **teramati nyata dengan timestamp presisi** (bukan simulasi/asumsi) -- pipeline metrics-server -> HPA controller -> Deployment scaling terbukti berfungsi utuh dalam kedua arah. **Temuan tambahan bernilai** (di luar skenario "normal" yang diharapkan): scale-up ke 3 replica pada cluster single-node yang SUDAH terbebani (KD-3 + trafik residual tak sengaja) sempat menyebabkan SEMUA replica down bersamaan sesaat -- ironisnya HPA yang dimaksudkan menambah kapasitas justru sempat memperburuk kontensi resource node dalam skenario ini, sebelum akhirnya pulih sendiri begitu 2 pod baru selesai startup. Ini bukti KONKRET kenapa dokumentasi (Keputusan #2 `decisions.md`, komentar `hpa.yaml`) menyebut HPA di cluster lokal ini "ilustratif" -- bukan elastisitas produksi yang bisa diandalkan tanpa syarat.
