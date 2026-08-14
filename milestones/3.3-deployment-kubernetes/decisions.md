# Decisions — Milestone 3.3: Deployment ke Kubernetes

## Konteks

Men-deploy image real-time API (M3.1/M3.2) ke Kubernetes. Satu keputusan fondasional (target Kubernetes) dikonfirmasi eksplisit oleh user via `AskUserQuestion` dua putaran + riset web sebelum plan ditulis — sisanya forced/derived oleh precedent (K8s best practice standar, temuan empiris M3.2) atau delegasi wewenang implementasi.

## Keputusan Teknis

### 1. Target Kubernetes: Docker Desktop Kubernetes lokal

**Keputusan:** Deploy ke cluster Kubernetes lokal Docker Desktop (single-node), bukan cloud-managed K8s.

**Kenapa:** Dikonfirmasi eksplisit user. Tujuan asli user ("auto predict data sintesis tanpa nyalain komputer") sudah terpenuhi Milestone 2.9 (jalur GitHub Actions, cloud-based, tidak terkait Kubernetes). Real-time API belum punya pemanggil eksternal nyata yang butuh uptime 24/7. Riset Oracle Cloud Always Free (opsi always-on termurah): kuota 2 OCPU/12GB cukup teknis, TAPI Oracle diam-diam memotong kuota 50% pertengahan Juni 2026 tanpa pengumuman + sedang aktif menghapus instance melebihi kuota baru — risiko keandalan nyata.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- Cloud-managed K8s berbayar (GKE/EKS/AKS) — DITOLAK: biaya berkelanjutan tanpa kebutuhan konkret, menyimpang dari pola proyek ini yang konsisten tier gratis.
- VPS gratis + k3s (Oracle Cloud Always Free) — DIPERTIMBANGKAN SERIUS, DITOLAK untuk sekarang: riwayat pemotongan kuota diam-diam + risiko kompatibilitas arm64 belum diverifikasi + kompleksitas setup untuk user yang belum familiar Kubernetes.

**Dicatat di:** `docs/keputusan-tertunda.md` KT-8 dan `docs/keterbatasan-diterima.md` KD-2 (instruksi eksplisit user).

### 2. Container registry: TIDAK diperlukan untuk target lokal

**Keputusan:** Image `docker build` lokal dipakai langsung oleh pod K8s (`imagePullPolicy: IfNotPresent`), tanpa push ke registry eksternal.

**Kenapa:** Dikonfirmasi empiris — Docker Desktop Kubernetes berbagi image store yang sama dengan `docker build` lokal (`docker stats` bahkan menampilkan container pod K8s secara langsung, `k8s_churn-api_...`). Push eksternal cuma relevan untuk cluster remote.

**Opsi yang Dipertimbangkan tapi Ditolak:** push preventif ke GHCR sekarang — DITOLAK: kerja tambahan tanpa manfaat untuk target lokal.

### 3. Health check terpisah: `/healthz` (liveness) vs `/readyz` (readiness)

**Keputusan:** `GET /healthz` selalu 200 (liveness, tidak cek model). `GET /readyz` 200/503 berdasar `app.state.model` (readiness, KK2).

**Kenapa:** Liveness gagal → K8s restart pod; readiness gagal → K8s keluarkan pod dari trafik Service (tidak restart). Digabung berarti pod dengan model gagal dimuat (registry down) akan di-restart terus-menerus tanpa pernah membantu.

**Opsi yang Dipertimbangkan tapi Ditolak:** satu endpoint `/health` untuk keduanya — DITOLAK: menciptakan crash-loop tak berguna.

**Verifikasi:** `tests/api/test_app.py` — 11/11 lulus (5 test baru), `pytest tests/ -q` penuh 197/197 lulus, regresi nol.

### 4. `startupProbe` untuk mengakomodasi startup lambat

**Keputusan:** `startupProbe` (httpGet `/healthz`, `periodSeconds: 10`, `failureThreshold: 30`) menunda `livenessProbe`/`readinessProbe` sampai probe pertama sukses.

**Kenapa:** Forced bukti empiris M3.2 — startup gagal-registry butuh ~100 detik (retry backoff MLflow) sebelum port terbuka, app tetap hidup. `livenessProbe` naif berisiko membunuh pod prematur.

**Opsi yang Dipertimbangkan tapi Ditolak:** `initialDelaySeconds` statis besar tanpa `startupProbe` — DITOLAK: kurang presisi dibanding pola retry progresif `startupProbe`.

**Verifikasi NYATA (Checkpoint 2, Task 7):** Deployment temporer `MLFLOW_TRACKING_URI` sengaja rusak — `kubectl describe pod` menunjukkan `startupProbe` gagal (`connection refused`) berulang selama startup, TANPA pod di-restart (`RESTARTS: 0`). Setelah port terbuka, `readinessProbe` gagal (`503`) — pod `Running` tapi `0/1 Ready`, BUKAN `CrashLoopBackOff`. `kubectl get endpoints churn-api-broken-test` kosong (dibandingkan `churn-api` sehat yang terisi `10.1.0.10:8000`) — mengonfirmasi Service TIDAK mengarahkan trafik ke pod tidak sehat.

### 5. Resource request/limit berbasis `docker stats`, bukan `metrics-server` K8s

**Keputusan:** Angka `resources.requests`/`resources.limits` didasarkan pada observasi `docker stats` nyata.

**Kenapa:** Docker Desktop Kubernetes tidak menyertakan `metrics-server` default. Instalasi khusus untuk observasi sekali pakai adalah scope creep (M3.5/M3.7 tanggung jawab monitoring resource berkelanjutan).

**Opsi yang Dipertimbangkan tapi Ditolak:** instal `metrics-server` sekarang — DITOLAK: komponen cluster permanen untuk kebutuhan sekali-observasi.

**Data observasi nyata (Checkpoint 3, Task 8):** Idle: ~364MiB memori, ~0.2-0.8% CPU. Puncak (50 request `/predict` PARALEL): ~387MiB memori (naik tipis, tidak ada indikasi leak), CPU puncak ~101.84% (≈1 core penuh). Angka final: `requests` cpu `200m`/memory `400Mi` (mendekati baseline idle), `limits` cpu `1500m`/memory `768Mi` (headroom ~1.5x CPU puncak, ~2x memori puncak). Diverifikasi: `kubectl apply` ulang, pod `1/1 Running` dengan angka baru (rolling update mulus, RESTARTS 0).

### 6. Kredensial via K8s Secret object, bukan hardcode di manifest

**Keputusan:** `kubectl create secret generic churn-api-secrets --from-literal=...` dari `.env` lokal (manual, TIDAK dicommit). Deployment referensi via `envFrom.secretRef`.

**Kenapa:** Forced prinsip "rahasia tidak boleh di-hardcode atau di-commit" (`CLAUDE.md`).

**Opsi yang Dipertimbangkan tapi Ditolak:** tidak ada alternatif — forced by prinsip keamanan dasar.

### 7. Service type: `LoadBalancer`

**Keputusan:** `infra/k8s/service.yaml` pakai `type: LoadBalancer`.

**Kenapa:** Devex bersih (`http://localhost/...` langsung, port 80).

**Verifikasi empiris:** DIKONFIRMASI bekerja bersih — `kubectl get svc` menunjukkan `EXTERNAL-IP: localhost` segera setelah apply, tanpa tooling tambahan (beda dari minikube). Tidak perlu fallback `NodePort`.

### 8. Namespace terpisah `churn-prediction`

**Keputusan:** Resource K8s milestone ini di-deploy ke namespace `churn-prediction`, bukan `default`.

**Kenapa:** Best practice ringan, biaya nyaris nol.

**Opsi yang Dipertimbangkan tapi Ditolak:** namespace `default` — tidak ditolak keras, cuma dipilih terpisah konsisten pola scoping eksplisit proyek ini.
