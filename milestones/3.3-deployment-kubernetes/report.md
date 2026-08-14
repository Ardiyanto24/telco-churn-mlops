# Report — Milestone 3.3: Deployment ke Kubernetes

## Ringkasan

Milestone 3.3 SELESAI — real-time API (M3.1/M3.2) di-deploy ke Kubernetes lokal (Docker Desktop). Target Kubernetes (lokal vs cloud always-on) diklarifikasi eksplisit dengan user di awal milestone — riset Oracle Cloud Always Free (opsi termurah untuk always-on) menemukan platform tersebut baru saja memotong kuota gratisnya 50% tanpa pengumuman, risiko keandalan nyata untuk kebutuhan yang belum genuinely diperlukan sekarang (real-time API belum punya pemanggil eksternal, dan tujuan "auto-predict tanpa nyalain komputer" user sudah terpenuhi jalur berbeda sejak M2.9). Keputusan dan konteksnya dicatat di `docs/keputusan-tertunda.md` (KT-8) dan `docs/keterbatasan-diterima.md` (KD-2) sesuai instruksi eksplisit user, selain `decisions.md` milestone ini.

Dibangun: `/healthz` (liveness) + `/readyz` (readiness) — follow-up eksplisit M3.2 yang menyerahkan ini ke M3.3 — dan manifest K8s (`infra/k8s/`: namespace, Deployment dengan startup/liveness/readiness probe + resource request/limit berbasis observasi nyata, Service `LoadBalancer`).

## Kriteria Keberhasilan vs Bukti

| KK | Kriteria | Bukti |
|---|---|---|
| **KK1** | "Service berhasil berjalan di Kubernetes dan merespons request dengan hasil yang konsisten dengan Milestone 3.2." | Pod `1/1 Running`, Service `LoadBalancer` dengan `EXTERNAL-IP: localhost` (bekerja bersih tanpa tooling tambahan). `scripts/api_parity_check.py` (reuse M3.2) terhadap `http://localhost` — `churn_probability` allclose True (diff maksimum ~4×10⁻¹⁶), `churn_label`/`model_version` exact match, identik hasil M3.2. Akses langsung `curl` dari host ke `/healthz`/`/readyz`/`/predict` sukses. |
| **KK2** | "Simulasi model belum termuat... menyebabkan readiness check gagal — service tidak menerima trafik sebelum benar-benar siap." | Deployment temporer `MLFLOW_TRACKING_URI` sengaja rusak — `startupProbe` gagal (`connection refused`) selama startup lambat TANPA membunuh pod (`RESTARTS: 0`); setelah port terbuka, `readinessProbe` gagal (503) — pod `Running` `0/1 Ready` (BUKAN `CrashLoopBackOff`). `kubectl get endpoints` mengonfirmasi pod TIDAK masuk daftar endpoint Service (dibandingkan pod sehat yang endpoint-nya terisi) — trafik nyata tidak diarahkan kesana. |
| **KK3** | "Resource request/limit awal terdokumentasi beserta dasar penentuannya." | `docker stats` nyata: idle ~364MiB/~0.2% CPU, puncak 50 request paralel ~387MiB/~102% CPU. Angka final (`requests` cpu 200m/memory 400Mi, `limits` cpu 1500m/memory 768Mi) berbasis angka ini dengan margin terdokumentasi, BUKAN tebakan/template umum — lihat `logs.md` Checkpoint 3. |

## Keputusan Final

Lihat [`decisions.md`](./decisions.md) — 8 keputusan. Satu (target Kubernetes) dikonfirmasi eksplisit user via `AskUserQuestion` dua putaran + riset web; sisanya forced/derived (K8s best practice standar untuk pemisahan health check, bukti empiris M3.2 untuk startup probe, observasi nyata untuk resource sizing) atau delegasi wewenang implementasi.

## Perubahan dari Plan Awal

Tidak ada penyimpangan struktural — seluruh 3 checkpoint dan 12 task dieksekusi sesuai urutan yang direncanakan. Satu asumsi plan terverifikasi BENAR secara empiris tanpa perlu fallback: `Service type: LoadBalancer` bekerja bersih di Docker Desktop Kubernetes (langsung `EXTERNAL-IP: localhost`) sejak percobaan pertama, tidak perlu fallback `NodePort` yang sudah diantisipasi di plan.

## Keterbatasan dan Item Terbuka

- **Real-time API HANYA reachable selama komputer user menyala dan cluster dijalankan manual** — bukan service production 24/7. Ini keterbatasan yang SENGAJA diterima (lihat `docs/keterbatasan-diterima.md` KD-2), sesuai kriteria sumber M3.3 sendiri yang mengizinkan "lingkungan uji yang merepresentasikan konsumen real-time" (bukan mewajibkan uptime produksi).
- **Belum ada monitoring/alerting terpasang untuk cluster ini** — wewenang Milestone 3.5.
- **Belum ada mekanisme rollback deployment formal** (mis. `kubectl rollout undo` terverifikasi eksplisit) — wewenang Milestone 3.11.
- **`metrics-server` tidak terinstal** — resource sizing berbasis `docker stats` (proxy container yang sama, bukan `kubectl top`), sengaja dianggap cukup untuk "estimasi awal" (KK3 sumber eksplisit menyebut ini, penyempurnaan berbasis beban nyata adalah Milestone 3.7).
- **Deployment/Secret dibuat imperatif** (`kubectl create secret ... | kubectl apply -f -`) bukan lewat mekanisme templating (Helm/Kustomize) — cukup untuk skala solo-project single-environment ini, konsisten prinsip anti-overengineering proyek ini.
- **Belum ada test regresi otomatis untuk manifest K8s** (mis. validasi skema YAML di CI) — verifikasi milestone ini seluruhnya manual/interaktif (`kubectl apply`+observasi), konsisten pola M3.1/M3.2.

## Follow-up

- M3.4 (Deteksi Versi Model Aktif Tanpa Restart Penuh): mekanisme refresh model di dalam pod yang sudah berjalan — saat ini restart (`kubectl rollout restart`) tetap satu-satunya cara pick up versi model baru, konsisten keterbatasan M3.2.
- M3.5 (Monitoring): manifest `infra/k8s/` ini jadi target instrumentasi (metrics endpoint, log aggregation).
- M3.11 (Rollback Deployment dan Resource Sizing): penyesuaian resource request/limit berdasar beban produksi nyata (bukan observasi sintetis milestone ini), plus mekanisme rollback deployment formal.
- KT-8/KD-2 (`docs/keputusan-tertunda.md`/`docs/keterbatasan-diterima.md`): evaluasi ulang target Kubernetes always-on kalau ada kebutuhan pemanggil eksternal nyata atau kondisi free-tier cloud lebih stabil.
