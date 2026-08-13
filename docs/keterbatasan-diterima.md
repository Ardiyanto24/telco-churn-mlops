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
