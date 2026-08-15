# Keterbatasan yang Sengaja Diterima — Backlog Project-Wide

File ini beda dari `docs/keputusan-tertunda.md` (keputusan yang BELUM diambil, menunggu konteks). Isi file ini adalah keputusan yang SUDAH final — sengaja menerima suatu keterbatasan teknis alih-alih memperbaikinya sekarang — karena biaya perbaikan tidak sepadan pada skala proyek ini, atau perbaikannya di luar kendali kita (dependency pihak ketiga, batasan platform).

Tujuan: supaya keterbatasan yang sudah ditemukan dan diterima di satu milestone tidak ditemukan ulang dari nol (dan berpotensi "diperbaiki" secara tidak sengaja atau dianggap bug baru) oleh milestone lain yang bersinggungan dengannya di kemudian hari.

Setiap entri: konteks penemuan, kenapa diterima (bukan diperbaiki), dampak konkret + mitigasi yang sudah ada, dan pemicu peninjauan ulang (kalau ada kondisi yang bisa mengubah kalkulasi ini nanti).

---

## KD-1 — Prefect Managed work pool tidak bisa menjalankan model yang bergantung LightGBM (libgomp.so.1 hilang)

**Muncul saat:** Milestone 2.5, Checkpoint 3 (verifikasi deploy `batch_scoring_flow` ke Prefect Managed work pool).

**Konteks:** `model_final.joblib` adalah `VotingClassifier` berisi `LGBMClassifier` (LightGBM) + 2x `XGBClassifier`. Wheel resmi PyPI `lightgbm` TIDAK membundel `libgomp.so.1` (runtime OpenMP GNU) di dalam wheel-nya sendiri — ini gap packaging yang sudah diketahui upstream dan belum diperbaiki ([microsoft/LightGBM#4484](https://github.com/microsoft/LightGBM/issues/4484)), beda dari beberapa wheel scientific-Python lain yang membundel shared library sejenis lewat `auditwheel`. Image dasar Prefect Managed work pool (`prefecthq/prefect-client:3-latest`) tidak punya `libgomp.so.1` ter-install, dan `job_variables.pip_packages` HANYA menjalankan `pip install` — tidak ada akses `apt-get`/instalasi paket sistem level OS. Akibatnya `score_batch` (task yang memanggil `predict_active()` → memuat model → unpickle `LGBMClassifier`) gagal dengan `OSError: libgomp.so.1: cannot open shared object file`, walau task-task sebelumnya (`extract_raw_data`, gerbang kualitas data M2.4) berhasil sempurna di Managed.

**Kenapa diterima (bukan diperbaiki sekarang):** Tidak ada jalur pip-only yang terbukti reliable untuk menyediakan library sistem ini di Prefect Managed (bukan tebakan — sudah diriset, lihat referensi di bawah). Opsi yang ADA (ganti ke Prefect work pool tipe lain yang butuh worker yang kita host sendiri, mis. `process`/Docker) mengembalikan sebagian masalah hosting yang justru coba dihindari M2.1 (meski lebih ringan karena tidak perlu jalan 24/7, cukup dinyalakan saat perlu trigger run manual) — dipertimbangkan tapi user memilih menerima keterbatasan Managed untuk sekarang, bukan pindah arsitektur lagi.

**Dampak & mitigasi yang sudah ada:**
- Keputusan M2.1 (Prefect Cloud sebagai orchestrator) **tidak dicabut** — Prefect Cloud tetap dipakai untuk scheduling/tracking/UI, dan task NON-LightGBM (`extract_raw_data`, gerbang kualitas data M2.4) TERBUKTI jalan sukses di Managed work pool (lihat `milestones/2.5-batch-scoring-dag/logs.md`).
- Verifikasi end-to-end SKALA PENUH (594.194 baris, termasuk scoring LightGBM) untuk M2.5 dibuktikan lewat **run lokal** (Task 10), bukan Managed — ini yang jadi bukti utama KK1 milestone ini.
- Bucket dampak: **setiap task DAG masa depan yang memuat model ini (LightGBM) TIDAK bisa dijalankan di Managed work pool** — berlaku juga untuk Milestone 2.6 (jika ada task serupa), 2.7 (CI/CD, kalau runner CI-nya juga Managed-based), dan 2.8 (promosi/rollback yang memuat model untuk sanity check).

**Pemicu peninjauan ulang:**
- LightGBM upstream memperbaiki packaging wheel-nya (membundel `libgomp` via `auditwheel`, menutup issue #4484) — cek ulang saat upgrade versi `lightgbm` di masa depan.
- Kebutuhan menjalankan task berbasis LightGBM SECARA TERJADWAL RUTIN (bukan cuma verifikasi manual) muncul nyata — saat itu, evaluasi ulang opsi `process`/Docker work pool yang di-host sendiri (trade-off hosting yang tadinya ditolak M2.1 untuk Airflow perlu dipertimbangkan ulang dengan konteks baru: cakupannya lebih sempit, cuma untuk task scoring, bukan seluruh orchestrator).

**Referensi riset:** [microsoft/LightGBM#4484](https://github.com/microsoft/LightGBM/issues/4484) (wheel tidak PEP 599 compliant), diskusi komunitas mengonfirmasi tidak ada solusi pip-only yang reliable untuk container minimal tanpa akses package manager OS.

**Update 2026-08-13 — mitigasi ditemukan untuk kebutuhan run terjadwal, Managed sendiri TETAP terbatas:** Pemicu peninjauan ulang di atas ("kebutuhan run LightGBM terjadwal rutin muncul nyata") benar-benar terjadi -- lihat `milestones/2.5-batch-scoring-dag/decisions.md` Keputusan #8. Alih-alih opsi `process`/Docker work pool yang di-host sendiri (opsi yang disebut di atas), dipilih jalur BEDA: `.github/workflows/batch-scoring.yml` (workflow_dispatch, `runs-on: ubuntu-latest`) menjalankan `batch_scoring_flow()` LANGSUNG lewat `python -m`, bukan lewat deployment/work pool Prefect sama sekali -- `@flow`/`@task` tetap melapor ke Prefect Cloud lewat `PREFECT_API_KEY`/`PREFECT_API_URL` (dibuktikan: flow run `boisterous-wildcat`, `state=Completed`, terverifikasi lewat Prefect API langsung). Runner `ubuntu-latest` TERBUKTI tidak kena `libgomp.so.1` (sudah lama terbukti tidak masalah di `integration-tests` M2.7, sekarang dikonfirmasi juga untuk `score_batch` sungguhan: 1000 baris ter-scoring+tertulis lengkap lineage, run nyata `batch_run_id=ca721f01-acdd-4dc2-931f-3497242b7137`). **KD-1 ITU SENDIRI TIDAK TERTUTUP** -- Prefect Managed work pool TETAP tidak bisa memuat LightGBM, keterbatasan itu apa adanya; yang berubah adalah sekarang ADA jalur eksekusi terjadwal yang menghindarinya sepenuhnya untuk kebutuhan batch scoring. Relevan untuk milestone lain yang mempertimbangkan Managed untuk task berbasis LightGBM: pertimbangkan pola workflow GitHub Actions ini dulu sebelum mengevaluasi ulang self-hosted work pool.

---

## KD-2 — Real-time API di-deploy ke Kubernetes LOKAL (Docker Desktop), bukan cloud/VM always-on

**Muncul saat:** Milestone 3.3, Checkpoint awal (sebelum plan ditulis, klarifikasi `AskUserQuestion` dua putaran dengan user).

**Konteks:** Milestone 3.3 mensyaratkan real-time API (M3.2) di-deploy ke Kubernetes -- dokumen arsitektur mengunci "Kubernetes" sebagai tool, tapi sengaja membiarkan target konkret terbuka (Bagian 10). User awalnya berasumsi tujuan "auto predict saat data sintesis baru masuk tanpa perlu menghidupkan komputer" bergantung pada pilihan target ini. Diklarifikasi: tujuan itu SUDAH terpenuhi sejak Milestone 2.9 lewat jalur berbeda sepenuhnya (Postgres `pg_net` -> GitHub `repository_dispatch` -> GitHub Actions, cloud-based, TIDAK melibatkan Kubernetes). Real-time API adalah use case terpisah (dipanggil sinkron oleh pemanggil eksternal), belum punya pemanggil eksternal nyata saat ini.

Opsi always-on termurah yang diriset (VPS gratis Oracle Cloud Always Free + k3s) ditemukan punya kuota TEKNIS cukup (2 OCPU/12GB, jauh di atas kebutuhan riil aplikasi ini -- observasi `docker stats` Checkpoint 3 milestone ini: idle ~364MiB, puncak beban ~387MiB) TAPI riwayat pemotongan kuota diam-diam 50% tanpa pengumuman (Juni 2026) dan penghapusan aktif instance melebihi kuota baru (berlangsung sekitar sesi ini, Agustus 2026) -- risiko keandalan nyata, bukan hipotetis.

**Kenapa diterima (bukan diperbaiki dengan hosting always-on sekarang):** (1) Tujuan asli user tidak bergantung pilihan ini -- sudah terpenuhi jalur lain (M2.9); (2) belum ada pemanggil eksternal nyata yang butuh real-time API reachable 24/7 -- investasi hosting always-on belum punya manfaat konkret untuk dibenarkan sekarang; (3) opsi termurah yang tersedia (Oracle Cloud) baru saja terbukti tidak stabil kuotanya -- mempercayakan komponen "harus selalu bisa diandalkan" ke platform yang baru memotong janji "always free"-nya tanpa pemberitahuan adalah risiko yang sengaja dihindari; (4) kompleksitas tambahan (provisioning VM, jaringan/firewall, verifikasi ulang kompatibilitas image arm64 vs image x86_64 existing) untuk user yang mengaku belum familiar Kubernetes tidak sepadan tanpa kebutuhan konkret.

**Dampak & mitigasi yang sudah ada:**
- Real-time API HANYA reachable selama komputer user menyala DAN Docker Desktop Kubernetes dijalankan manual -- BUKAN service production 24/7. Ini SESUAI kriteria sumber M3.3 sendiri yang eksplisit mengizinkan "lingkungan uji yang merepresentasikan konsumen real-time" (bukan mewajibkan uptime produksi).
- Seluruh KK M3.3 (jalan+konsisten M3.2, readiness gagal saat model belum termuat, resource request/limit terdokumentasi) tetap diverifikasi NYATA terhadap cluster K8s sungguhan (`kubectl get pods`/`svc`/`endpoints`) -- keterbatasan ini TIDAK mengurangi validitas bukti milestone ini, cuma membatasi kapan service bisa diakses.
- Manifest (`infra/k8s/`) TIDAK mengunci asumsi lokal secara permanen -- kredensial lewat Secret (bukan hardcode), image lewat tag eksplisit (bukan bergantung path lokal khusus) -- kalau nanti pindah cluster remote, perubahan terbatas pada cara build/push image dan cara membuat Secret, bukan re-desain manifest dari nol.

**Pemicu peninjauan ulang:** Sama dengan KT-8 (`docs/keputusan-tertunda.md`) -- (a) ada kebutuhan konkret pemanggil eksternal nyata; (b) kuota Always Free (Oracle Cloud atau alternatif setara) terbukti stabil kembali; (c) user eksplisit ingin evaluasi ulang.

**Referensi riset:** [Oracle Quietly Halves Free Tier Ampere A1 Compute Limits — InfoQ](https://www.infoq.com/news/2026/07/oracle-cloud-free-tier-limits/), [Always Free Resources — Oracle Docs](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm).

---

## KD-3 — Real-time API (M3.2) memproses request secara efektif single-worker, tidak stabil pada beban konkuren tinggi

**Muncul saat:** Milestone 3.11, Checkpoint 4 (uji beban terkontrol bertingkat dengan `kubectl top` native, dipakai untuk dasar resource sizing).

**Konteks:** Uji beban `/predict` pada 4 level konkurensi (1/10/50/100 request paralel, masing-masing 60 detik) menemukan CPU puncak pod **konsisten di kisaran ~1,0-1,12 core (1012-1122m) di SEMUA level** — tidak naik proporsional dengan jumlah request paralel. Ini bukti kuat real-time API memproses request secara efektif SATU PER SATU (worker/event loop tunggal terhadap kerja inference yang CPU-bound), bukan benar-benar paralel di dalam satu pod. Akibatnya, pada konkurensi ≥10, request tambahan mengantre alih-alih diproses paralel — `/healthz`/`/readyz` tidak sempat dijawab tepat waktu (`context deadline exceeded`), error rate request `/predict` naik drastis (95,4% pada konkurensi 10, 99,7% pada 50, 100% pada 100), dan pada konkurensi 50 DAN 100 memicu restart nyata via `livenessProbe` (Kubernetes betul-betul mem-`Kill` lalu recreate container, pulih otomatis ~85 detik tiap kali, TANPA kehilangan data — self-healing bekerja seperti dirancang M3.2/M3.3 Keputusan #3).

**Kenapa diterima (bukan diperbaiki sekarang):** Root cause adalah desain concurrency di level KODE real-time API (kemungkinan satu worker Uvicorn/proses tanpa `run_in_threadpool` untuk kerja inference sinkron yang CPU-bound, memblokir event loop) — properti API itu sendiri (Milestone 3.2, jalur Orang #3 sebelumnya), BUKAN sesuatu yang bisa diperbaiki lewat penyesuaian `resources.requests`/`resources.limits` Kubernetes yang jadi cakupan M3.11. Mengubah arsitektur concurrency API (mis. menambah worker Uvicorn, memindah inference ke thread pool) adalah perubahan kode signifikan di luar cakupan milestone ini (`CLAUDE.md` "Batas Implementasi Saat Ini" — tidak membangun kapabilitas di luar cakupan tanpa perluasan eksplisit dari user), dan belum ada kebutuhan konkret (belum ada pemanggil eksternal nyata dengan pola trafik konkuren tinggi — konsisten KD-2/KT-8/KT-9/KT-12).

**Dampak & mitigasi yang sudah ada:**
- Bukti eksplisit bahwa `resources.limits.cpu` SAAT INI (1500m) **BUKAN** penyebab restart/error — puncak nyata yang pernah teramati (1122m) masih di bawah limit dengan headroom wajar. Menaikkan limit CPU TIDAK akan memperbaiki masalah ini (root cause bukan CPU throttled/OOM).
- `livenessProbe`/`startupProbe` (M3.2/M3.3) TERBUKTI bekerja benar sebagai jaring pengaman — pod yang macet di-restart otomatis dan pulih tanpa intervensi manual, konsisten desain "restart proses yang macet" (Keputusan #3 M3.3).
- Skala trafik nyata terhadap real-time API sejauh ini (M3.2-3.5 dan M3.11) murni verifikasi manual — belum ada bukti pola trafik produksi konkuren tinggi yang benar-benar dirugikan oleh keterbatasan ini.

**Pemicu peninjauan ulang:** (a) Ada kebutuhan konkret pemanggil eksternal nyata dengan pola trafik konkuren (bukan verifikasi manual) — evaluasi ulang arsitektur concurrency API (M3.2) saat itu; (b) user eksplisit ingin evaluasi ulang meski belum ada pemicu (a) — konsisten pola KD-1/KD-2/KT-8/9/12.

**Referensi:** `milestones/3.11-rollback-deployment-resource-sizing/logs.md` Checkpoint 4 (tabel lengkap 4 level konkurensi + bukti `kubectl get events`/`describe pod`), `milestones/3.11-rollback-deployment-resource-sizing/raw-data/` (CSV mentah).
