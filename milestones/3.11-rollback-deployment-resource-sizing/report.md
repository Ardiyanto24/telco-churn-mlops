# Report — Milestone 3.11: Rollback Deployment dan Resource Sizing

## Ringkasan

Milestone 3.11 SELESAI — dua kemampuan terpisah dibangun di atas Deployment `churn-api` (M3.2/M3.3): (1) rollback deployment Kubernetes untuk kode/container baru yang gagal health check, terpisah eksplisit dari rollback versi model (M3.4/2.8, level MLflow registry); (2) peninjauan resource request/limit dengan bukti metrik native Kubernetes (bukan lagi proxy `docker stats` M3.3), plus HPA dasar ilustratif atas permintaan eksplisit user.

Riset sebelum plan ditulis menemukan konflik dokumen-vs-implementasi yang material: teks sumber M3.11 mengasumsikan M3.5 sudah punya data historis CPU/memory level pod, padahal monitoring M3.5-3.9 hanya pernah menangkap metrik level aplikasi/pipeline/drift — nol metrik resource. `metrics-server` (prasyarat `kubectl top` dan HPA) baru dipasang di milestone ini.

Uji beban terkontrol (Checkpoint 4) menghasilkan temuan signifikan di luar dugaan: CPU puncak pod **konsisten di kisaran ~1,0-1,12 core di SEMUA level konkurensi 1-100** — bukti real-time API (M3.2) memproses request secara efektif single-worker, bukan paralel. Ini memicu 2 restart nyata (self-healing bekerja seperti dirancang) dan dicatat sebagai keterbatasan diterima baru **KD-3**. Uji HPA (Checkpoint 6) mendemonstrasikan siklus scale-up/scale-down penuh dengan timestamp nyata, termasuk temuan tak terduga: scale-up ke 3 replica pada node yang sudah terbebani sempat membuat SEMUA pod Not Ready bersamaan — bukti konkret kenapa HPA di cluster lokal ini bersifat ilustratif.

## Kriteria Keberhasilan vs Bukti

| KK | Kriteria | Bukti |
|---|---|---|
| **KK1** | "Simulasi deployment baru yang gagal health check berhasil di-rollback ke versi deployment sebelumnya, dengan downtime yang minimal." | Simulasi terkontrol (`MLFLOW_TRACKING_URI` invalid, pola tervalidasi M3.2/3.3/3.4): rollout macet aman (`maxUnavailable:0` mencegah pod lama diturunkan), `kubectl rollout undo` membersihkan ReplicaSet rusak dan mengembalikan status sehat. **Bukti downtime**: log polling `/predict` kontinu nyata — 121 request, 120 status 200, HANYA 1 non-200 (cold-start SEBELUM simulasi dimulai). Downtime selama window kegagalan+rollback = **NOL**, bukan sekadar minimal. `kubectl rollout history`/`get rs`/`describe pod` mengonfirmasi tiap tahap. |
| **KK2** | "Resource request/limit yang disesuaikan terbukti tidak menyebabkan service throttled/OOM pada beban puncak yang teramati, sekaligus tidak boros dibanding kebutuhan nyata." | `metrics-server` dipasang, uji beban bertingkat (1/10/50/100 konkurensi, `kubectl top` native) menghasilkan idle steady-state 89-321m CPU/340-341Mi, puncak tertinggi 1122m CPU/462Mi di SELURUH level. Nilai `requests`/`limits` existing (200m/400Mi, 1500m/768Mi) **RE-AFFIRMED** dengan bukti baru: `requests` margin ~1,3x di atas idle (tidak boros), `limits` headroom ~34%/~66% di atas puncak tertinggi (CUKUP). Dua restart yang teramati (konkurensi 50 & 100) **TERBUKTI (`kubectl get events`/`describe pod`) BUKAN** disebabkan CPU throttled/OOM — nol event `OOMKilled` di seluruh 4 level — melainkan probe timeout akibat karakteristik single-worker API (KD-3, di luar cakupan resource sizing K8s). |

## Keputusan Final

Lihat [`decisions.md`](./decisions.md) — 7 keputusan: basis resource sizing (metrics-server + uji beban native, dipilih user sesuai rekomendasi), cakupan HPA (dibangun ilustratif — user memilih BERBEDA dari rekomendasi saya yang menyarankan skip/tunda), strategy/revisionHistoryLimit eksplisit, metode simulasi kegagalan (reuse pola tervalidasi), skrip uji beban baru, KT-12 baru, dan temuan Checkpoint 4 dicatat sebagai KD-3 (bukan diperbaiki, di luar cakupan). Setiap entri memuat "Opsi yang Dipertimbangkan tapi Ditolak".

## Perubahan dari Plan Awal

1. **Resource request/limit TIDAK diubah secara numerik** — plan awal berasumsi Checkpoint 5 akan "menerapkan nilai baru", tapi bukti native K8s menunjukkan nilai existing (M3.3) SUDAH tepat. Deviasi: hanya komentar `deployment.yaml` diperbarui referensi datanya, penyesuaian numerik dilewati dengan justifikasi eksplisit (menaikkan tanpa bukti kebutuhan akan melanggar paruh "tidak boros" KK2 sendiri).
2. **Re-run beban puncak identik di Checkpoint 5 dilewati** — karena konfigurasi tidak berubah, mengulang uji beban level 100 akan menghasilkan hasil identik tanpa informasi baru; data Checkpoint 4 dipakai langsung sebagai bukti KK2.
3. **Temuan tak terduga signifikan menghasilkan dokumen baru di luar rencana**: `docs/keterbatasan-diterima.md` KD-3 (karakteristik single-worker real-time API) — tidak direncanakan sebelum implementasi, murni konsekuensi hasil uji beban nyata.
4. **Insiden operasional ditemukan+diperbaiki selama verifikasi** (bukan bug rencana): (a) `kubectl apply` comment-only tak sengaja membersihkan anotasi `restartedAt` yang drift dari sesi sebelumnya, memicu rolling update nyata di tengah Checkpoint 5 — validasi tambahan yang berguna (bukan direncanakan, tapi terbukti bermanfaat); (b) proses `poll_predict.py` dari Checkpoint 2 gagal ter-kill (`kill` salah sasaran PID di lingkungan git-bash/MSYS) dan berjalan ~45 menit tanpa disadari, sempat mengaburkan interpretasi hasil Checkpoint 6 sebelum ditemukan dan diperbaiki (`kill -9`).
5. **Komentar `hpa.yaml` dikoreksi 2x selama implementasi** (bukan kesalahan rencana, ditemukan+diperbaiki saat verifikasi sebelum finalisasi): target Utilization ternyata dihitung dari `requests.cpu` bukan `limits.cpu`; kapasitas node ternyata ~12 core bukan ~4 core (salah baca `kubectl top nodes`).

## Keterbatasan dan Item Terbuka

- **HPA bersifat ILUSTRATIF, bukan elastisitas produksi andal** — dibuktikan konkret: scale-up ke 3 replica pada cluster single-node yang sudah terbebani sempat membuat SEMUA pod Not Ready bersamaan sebelum pulih sendiri. Dibangun atas permintaan eksplisit user (berbeda dari rekomendasi saya), threshold provisional — dicatat KT-12 (`docs/keputusan-tertunda.md`).
- **KD-3 (karakteristik single-worker real-time API) TIDAK diperbaiki** — di luar cakupan M3.11 (itu scope kode API, M3.2). Root cause: kemungkinan satu worker Uvicorn/proses tanpa `run_in_threadpool` untuk inference sinkron CPU-bound, memblokir event loop. Berdampak nyata pada konkurensi ≥10: error rate tinggi, restart terpicu pada ≥50.
- **Resource sizing berbasis beban TERKONTROL, bukan trafik produksi nyata** — belum ada pemanggil eksternal real-time API (konsisten KD-2/KT-8/KT-9). Dicatat KT-12 sebagai pemicu kalibrasi ulang begitu trafik nyata muncul.
- **`revisionHistoryLimit:10`/`maxSurge:1`/`maxUnavailable:0` baru dibuat eksplisit di M3.11** — sebelumnya implisit default K8s sejak M3.3, tidak terdokumentasikan sebagai keputusan sadar.
- **Node docker-desktop punya kapasitas CPU jauh lebih tinggi (~12 core) dari yang diasumsikan draf awal (~4 core)** — tidak mengubah keputusan `maxReplicas:3` karena instabilitas yang teramati bukan disebabkan kapasitas node (lihat KD-3).

## Follow-up

- M3.12 (Runbook Operasional): rujuk balik skenario "deployment gagal health check → rollback" (Checkpoint 2) dan referensi KD-3 untuk skenario "real-time API lambat/error tinggi di beban konkuren" bila relevan.
- Kalau kebutuhan nyata muncul: evaluasi ulang arsitektur concurrency real-time API (KD-3, scope M3.2) begitu ada pemanggil eksternal nyata; kalibrasi ulang threshold HPA/resource sizing (KT-12) dengan data trafik produksi asli.
