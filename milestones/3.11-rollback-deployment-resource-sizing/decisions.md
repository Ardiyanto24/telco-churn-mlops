# Keputusan — Milestone 3.11: Rollback Deployment dan Resource Sizing

> **Catatan status**: file ini ditulis di **Checkpoint 1** (bukan ditunda ke checkpoint penutup) begitu seluruh keputusan final tersedia — sebelum implementasi dimulai, sesuai koreksi eksplisit user terhadap pola milestone sebelumnya. Bagian yang menunggu angka konkret hasil implementasi ditandai `[DIISI CHECKPOINT 7]` dan akan dilengkapi di Checkpoint 7 tanpa menulis ulang keputusan dari nol.

## Konteks Singkat

`docs/02-implementation-plan/mlops-03-deployment-observability.md` baris 229-243 meminta dua kemampuan: (1) rollback deployment Kubernetes untuk kode/container baru yang gagal health check — terpisah dari rollback versi model (M3.4/2.8, level MLflow registry, Bagian 5.2/6.1 dokumen arsitektur); (2) peninjauan resource request/limit (M3.3) berdasar beban nyata yang sudah teramati lewat monitoring (M3.5), plus autoscaling dasar bila relevan.

**Temuan riset sebelum plan ditulis (konflik dokumen-vs-implementasi):** teks sumber mengasumsikan M3.5 sudah punya data historis CPU/memory level pod. Diverifikasi lewat grep menyeluruh `infra/`, `milestones/`, `docs/` — **tidak ada satupun metrik pod-level (cAdvisor/kube-state-metrics/metrics-server) yang pernah di-scrape**. Prometheus M3.5 hanya menangkap metrik level aplikasi (`prometheus-fastapi-instrumentator`), pipeline health, dan drift — 12 metrik M3.9, nol soal resource. Satu-satunya data resource yang pernah ada: `docker stats` sekali-pakai M3.3 (idle ~364MiB/~0.2% CPU, puncak ~387MiB/~102% CPU @ 50 request paralel sintetis) — >setahun lalu, bukan metrik native Kubernetes (`metrics-server` sengaja tidak dipasang M3.3, tanggung jawab dilempar ke "M3.5/M3.7" yang ternyata tidak pernah mengambilnya).

---

## Keputusan #1 — Basis Resource Sizing: Pasang `metrics-server` + Uji Beban Terkontrol Baru

**Keputusan final:** Pasang `metrics-server` di cluster, jalankan uji beban terkontrol BARU memakai `kubectl top` (metrik native Kubernetes), BUKAN melanjutkan proxy `docker stats` lama. Hasil tetap didokumentasikan transparan sebagai beban terkontrol/sintetis — bukan trafik produksi organik, karena belum ada pemanggil eksternal nyata terhadap real-time API ini (konsisten KD-2/KT-8/KT-9). Kalibrasi ulang dicatat sebagai keputusan tertunda baru (KT-12, lihat `docs/keputusan-tertunda.md`) untuk ditinjau begitu trafik nyata muncul.

**Alasan:** Data `docker stats` M3.3 adalah proxy container-level (Docker Desktop VM), bukan metrik native Kubernetes (cgroup pod sesungguhnya, dilihat lewat `metrics.k8s.io` API) — akurasinya lebih rendah untuk keputusan `resources.requests`/`limits` yang dievaluasi scheduler K8s sendiri. Memasang `metrics-server` sekaligus jadi prasyarat teknis untuk HPA (Keputusan #2) yang butuh API yang sama.

**Bukti:** Eksplorasi (`Explore` agent) mengonfirmasi eksplisit: `metrics-server` tidak pernah terpasang (M3.3 decisions.md baris 53: "instalasi khusus untuk observasi sekali pakai adalah scope creep"), tidak ada job Prometheus manapun yang scrape metrik pod-level, `kubectl top` akan gagal hari ini.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Pakai data `docker stats` M3.3 yang sudah ada tanpa observasi baru** — lebih cepat, tapi datanya usang (>setahun), diukur dari container Docker (bukan pod K8s sesungguhnya — konteks resource isolation berbeda: `docker stats` mengukur container tunggal di Docker Desktop VM, bukan cgroup yang benar-benar dikenakan `resources.limits` Kubernetes), dan tidak establish jalur `metrics-server` yang toh dibutuhkan untuk Keputusan #2 (HPA). Ditolak karena tujuan M3.11 eksplisit "meninjau ulang" resource sizing — mengulang data lama tanpa observasi baru tidak memenuhi maksud itu.

---

## Keputusan #2 — Cakupan Autoscaling: Bangun HPA Dasar (Ilustratif)

**Keputusan final:** Bangun `HorizontalPodAutoscaler` (`autoscaling/v2`) dasar — **user secara eksplisit memilih BERBEDA dari rekomendasi saya** (rekomendasi: skip/tunda sebagai keputusan tertunda, konsisten pola KT-5/7/8/9/11). HPA dibangun untuk kelengkapan portofolio/demonstrasi kapabilitas, dengan ambang batas provisional yang didokumentasikan eksplisit sebagai ILUSTRATIF — bukan hasil kalibrasi trafik nyata, dan tidak diklaim sebagai elastisitas produksi sungguhan.

**Alasan (dari user, bukan rekomendasi saya):** Nilai demonstrasi kapabilitas Kubernetes dianggap lebih penting daripada menunggu trafik nyata yang mungkin tidak pernah datang untuk proyek portofolio ini — konsisten dengan teks sumber M3.11 sendiri yang menyebut "konfigurasi autoscaling dasar" sebagai output eksplisit (meski dengan syarat kondisional "jika pola trafik menunjukkan kebutuhan itu").

**Batasan yang tetap didokumentasikan jujur:** Cluster Docker Desktop lokal bersifat single-node (KD-2) — menambah replica HPA TIDAK menambah kapasitas riil di luar satu mesin fisik yang sama; ini demonstrasi mekanisme, bukan elastisitas produksi.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Skip, catat sebagai keputusan tertunda (REKOMENDASI SAYA)** — konsisten pola established proyek ini (KT-5/7/8/9/11): tidak membangun mekanisme berdasar angka tebakan tanpa pola trafik nyata untuk dijadikan acuan. **Ditolak oleh user** — lihat alasan di atas. Dicatat di sini secara eksplisit karena CLAUDE.md mewajibkan pencatatan rejected alternatives termasuk saat user memilih berbeda dari rekomendasi AI.

---

## Keputusan #3 — `strategy` dan `revisionHistoryLimit` Dibuat Eksplisit (Turunan)

**Keputusan final:** `infra/k8s/deployment.yaml` mendapat `spec.strategy.rollingUpdate.{maxSurge:1, maxUnavailable:0}` dan `spec.revisionHistoryLimit:10` eksplisit — nilai SAMA PERSIS dengan default implisit Kubernetes saat ini untuk `replicas:1`.

**Alasan:** Sebelum M3.11, kedua field ini TIDAK di-set sama sekali di manifest — kapabilitas rollback yang jadi kriteria keberhasilan milestone ini secara diam-diam bergantung pada default K8s yang tidak pernah didokumentasikan sebagai keputusan sadar. Membuatnya eksplisit adalah prasyarat auditability, bukan perubahan perilaku.

**Tidak ada alternatif dipertimbangkan** — forced by kebutuhan dokumentasi eksplisit; nilai yang dipilih sudah identik default K8s yang terbukti benar (zero-downtime RollingUpdate untuk `replicas:1`), tidak ada trade-off nyata untuk dieksplorasi.

---

## Keputusan #4 — Metode Simulasi "Deployment Gagal Health Check": Reuse Pola `MLFLOW_TRACKING_URI` Rusak

**Keputusan final:** Simulasi kegagalan deployment memakai teknik yang sudah tervalidasi berulang di M3.2/M3.3/M3.4 — env var `MLFLOW_TRACKING_URI` diarahkan ke URI tidak valid, membuat `/readyz` pod baru gagal terus-menerus (readiness check gagal, bukan crash/OOM).

**Insight arsitektural yang ditemukan (bukan cuma langkah teknis):** Dengan `maxUnavailable:0` (Keputusan #3), pod lama TIDAK PERNAH diturunkan sampai pod baru Ready — rollout otomatis "macet aman" (zero-downtime inheren dari strategi RollingUpdate itu sendiri), TAPI Deployment tetap berstatus `progressing=False` tidak sehat (ReplicaSet rusak nganggur memakan resource) sampai `kubectl rollout undo` dijalankan untuk membersihkannya. Rollback di sini BUKAN mekanisme yang mencegah downtime (downtime sudah dicegah oleh `maxUnavailable:0`) — perannya adalah membersihkan status tidak sehat dan mengembalikan kapasitas resource yang terpakai ReplicaSet rusak.

**Tidak ada alternatif dipertimbangkan** — pola controlled-failure ini sudah tervalidasi berulang kali di milestone sebelumnya (M3.2 KK3, M3.3 Checkpoint negatif, M3.4 uji promosi/rollback), konsisten dipakai lagi untuk hasil yang bisa dipercaya.

---

## Keputusan #5 — Skrip Uji Beban Baru: `scripts/k8s_resource_load_test.py`

**Keputusan final:** Skrip baru ditulis khusus untuk generate beban HTTP konkuren sustained ke `/predict` sambil sampling `kubectl top pod` paralel — dipakai untuk Checkpoint 4 (resource sizing) MAUPUN Checkpoint 6 (memicu scale-up HPA), satu skrip dengan parameter concurrency berbeda.

**Alasan:** Skrip existing (`scripts/container_smoke_test.py`, `scripts/api_parity_check.py`) fokus ke korektnes/parity (bandingkan output, bukan generate beban), bukan generator beban HTTP konkuren yang bisa disustain untuk observasi resource.

**Tidak ada alternatif dipertimbangkan** — tidak ada tooling beban existing di repo yang cocok tanpa modifikasi signifikan (`orchestration/load_test/concurrent_readers.py` M2.6 targetnya query Postgres langsung, bukan HTTP `/predict`).

---

## Keputusan #6 — `docs/keputusan-tertunda.md` Dapat Entri Baru KT-12

**Keputusan final:** Kalibrasi resource sizing + HPA berbasis beban terkontrol/sintetis (bukan trafik produksi nyata) dicatat sebagai KT-12 — pemicu peninjauan konsisten pola KT-8/9 (trafik eksternal nyata muncul).

**Alasan:** Konsisten pola established sangat kuat di proyek ini (minimal 4 preseden: KT-5, KT-7, KT-8, KT-9) — setiap kali "keputusan berbasis trafik nyata" diminta tapi trafik nyata belum ada, dicatat sebagai keputusan tertunda alih-alih menebak SLA/ambang batas permanen.

**Tidak ada alternatif dipertimbangkan** — pola dokumentasi ini sudah standar proyek, bukan keputusan baru yang perlu dieksplorasi ulang.

---

## Keputusan #7 — Temuan Checkpoint 4 Dicatat sebagai KD-3 (Bukan Diperbaiki di M3.11)

**Temuan:** Uji beban bertingkat (1/10/50/100 konkurensi, lihat `logs.md` Checkpoint 4) menemukan CPU puncak pod KONSISTEN di kisaran ~1,0-1,12 core di SEMUA level — bukti real-time API (M3.2) memproses request secara efektif single-worker, bukan paralel. Pada konkurensi ≥10, ini menyebabkan error rate tinggi dan 2x restart nyata (liveness probe timeout, pulih otomatis ~85 detik tiap kali).

**Keputusan final:** Dicatat sebagai keterbatasan diterima BARU — **KD-3** (`docs/keterbatasan-diterima.md`) — BUKAN diperbaiki di M3.11. Root cause ada di level kode/arsitektur concurrency real-time API (M3.2), bukan resource sizing K8s (cakupan M3.11) — bukti kuat: CPU puncak TIDAK PERNAH mendekati limit 1500m di level manapun, jadi menaikkan limit CPU tidak akan menyelesaikan akar masalah.

**Alasan:** Mengubah arsitektur concurrency API (mis. tambah worker Uvicorn, pindahkan inference ke thread pool) adalah perubahan kode signifikan di luar cakupan M3.11 (`CLAUDE.md` "Batas Implementasi Saat Ini") — dan belum ada pemanggil eksternal nyata dengan pola trafik konkuren tinggi yang dirugikan (konsisten KD-2/KT-8/KT-9/KT-12).

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Perbaiki arsitektur concurrency API sekarang** (mis. edit `src/churn_prediction/api/app.py` menambah worker/thread pool) — ditolak: di luar cakupan M3.11 yang eksplisit soal rollback deployment K8s dan resource sizing, bukan redesign API real-time (itu M3.2). Mengubahnya tanpa perluasan cakupan eksplisit dari user melanggar batas implementasi proyek ini.
- **Naikkan resource limit CPU jauh lebih tinggi** dengan harapan memperbaiki stabilitas — ditolak berdasar BUKTI (CPU puncak tidak pernah mendekati limit saat ini di level manapun) bahwa ini tidak akan menyelesaikan akar masalah, cuma membuang resource tanpa manfaat nyata (bertentangan prinsip "tidak boros" KK2 M3.11 sendiri).

**Tidak ada alternatif dipertimbangkan untuk cara mendokumentasikannya** — pola `docs/keterbatasan-diterima.md` sudah standar proyek untuk temuan sekelas ini (preseden KD-1/KD-2).

---

## Nilai Konkret Hasil Implementasi

`[DIISI CHECKPOINT 7]` — akan berisi:
- Nilai final `resources.requests`/`resources.limits` (Checkpoint 5) beserta angka `kubectl top` idle/puncak yang jadi dasarnya.
- Threshold HPA final (`averageUtilization`, `minReplicas`/`maxReplicas`) beserta rasionalnya terhadap limit CPU baru.
- Detail patch `metrics-server` (Checkpoint 3) kalau isu TLS Docker Desktop K8s muncul.
- Hasil observasi scale-up/scale-down HPA (Checkpoint 6) — timestamp dan angka nyata, atau diagnosis kalau tidak teramati.
