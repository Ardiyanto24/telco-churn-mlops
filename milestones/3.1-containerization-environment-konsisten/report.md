# Report — Milestone 3.1: Containerization dan Environment Konsisten

## Ringkasan

Milestone 3.1 SELESAI — milestone pertama jalur Orang #3 (`mlops-03-deployment-observability.md`). `churn_prediction.inference` (M1.5) dibungkus ke Docker image (`python:3.13-slim`), dependency terkunci `pyproject.toml` (M1.2) diinstal identik, dan model dimuat runtime dari MLflow registry produksi (alias `champion`) — bukan dibake ke image, menjaga rollback tetap cukup ganti alias registry (prinsip Bagian 5.2 arsitektur). KD-1 (`docs/keterbatasan-diterima.md`, wheel `lightgbm` tidak membundel `libgomp.so.1`) diantisipasi eksplisit di Dockerfile dan dibuktikan nyata relevan di base image `slim` lewat uji coba negatif terkontrol.

Komponen yang dibangun: `Dockerfile`, `.dockerignore`, `scripts/container_smoke_test.py` (verifikasi parity host vs container). Tidak ada file pipeline/kode produksi existing yang disentuh.

## Kriteria Keberhasilan vs Bukti

| KK | Kriteria | Bukti |
|---|---|---|
| **KK1** | "Container berhasil di-build dan dijalankan, memuat model dari MLflow registry tanpa error versi/dependency." | Build sukses (`docker build`, exit 0, image 1.63GB). Sanity import (`churn_prediction`/`lightgbm`/`xgboost`/`sklearn`/`mlflow`) sukses tanpa error. **Bukti negatif eksplisit**: build ulang tanpa `libgomp1` gagal persis `OSError: libgomp.so.1: cannot open shared object file` — risiko KD-1 dibuktikan nyata di image ini, bukan diasumsikan dari kasus Prefect Managed. Model dimuat SUNGGUHAN dari registry produksi (`docker run --env-file .env`, alias `champion` resolve ke `model_version="1"`) — bukan tracking URI lokal/sementara. Lihat `logs.md` Checkpoint 1-2. |
| **KK2** | "Prediksi terhadap sampel data uji yang sama, dijalankan di dalam container, menghasilkan output identik dengan hasil dari inference service package yang dijalankan langsung... (verifikasi ulang parity di titik containerization, bukan diasumsikan otomatis sama)." | `scripts/container_smoke_test.py` dijalankan di host DAN container pada 1000 baris real `telco_customers_source` yang sama (`ORDER BY id LIMIT 1000`). `churn_probability` `np.allclose(rtol=1e-6)` True (0/1000 baris beda, diff maksimum ~5.5e-17 — level floating-point noise). `churn_label` identik 100% baris. `model_version` sama persis (`"1"`). Lihat `logs.md` Checkpoint 2. |

## Keputusan Final

Lihat [`decisions.md`](./decisions.md) — 6 keputusan, seluruhnya forced/derived (tidak ada yang perlu `AskUserQuestion`, konsisten milestone infrastruktur murni): (1) base image `python:3.13-slim` (match precedent CI), (2) `libgomp1` eksplisit sebelum `pip install` (forced KD-1), (3) model tidak dibake ke image (forced prinsip rollback-via-alias), (4) dependency inti saja (`pip install .`, bukan extras), (5) push registry di luar cakupan (M3.3), (6) verifikasi parity pakai data real 1000 baris (konsisten precedent M1.5/M2.8).

## Perubahan dari Plan Awal

Tidak ada penyimpangan struktural — seluruh 3 checkpoint dan 9 task dieksekusi sesuai urutan yang direncanakan. Satu gap kecil ditemukan+diperbaiki saat eksekusi (bukan diantisipasi eksplisit di plan): `container_smoke_test.py` (mengikuti pola `verify_before_promotion.py`) tidak memanggil `load_dotenv()` otomatis — run host pertama gagal `RuntimeError: BATCH_READER_DB_URL tidak diset` sampai env var di-load manual ke shell (`set -a && source .env`). Ini konsisten pola existing di proyek ini (scripts lain juga tidak auto-load `.env`), bukan bug baru — cuma langkah operasional yang perlu didokumentasikan eksplisit di sini untuk pemakai berikutnya.

## Keterbatasan dan Item Terbuka

- **Image belum dipush ke registry manapun (GHCR/Docker Hub)** — di luar cakupan M3.1 (lihat `decisions.md` Keputusan #5), akan jadi kebutuhan M3.3 (Deployment ke Kubernetes) yang butuh image accessible dari cluster.
- **Belum ada API/server HTTP** — container ini murni membuktikan package+model bisa dimuat konsisten di dalam container, belum melayani request apa pun. Itu cakupan M3.2 (Real-Time Inference API).
- **Ukuran image cukup besar (1.63GB)**, didominasi `nvidia_nccl_cu13` (~252MB, dependency transitif GPU dari `xgboost==3.4.0` meski inferensi ini CPU-only) — tidak diperbaiki di milestone ini (bukan kriteria keberhasilan manapun), dicatat di `decisions.md` sebagai observasi untuk M3.3 kalau waktu pull image di cluster jadi masalah nyata.
- **Verifikasi parity memakai sampel 1000 baris**, bukan skala penuh 594rb baris ala KD-1 M2.5 — cukup untuk membuktikan environment parity (tujuan spesifik KK2 milestone ini), TIDAK dimaksudkan sebagai uji beban/skala produksi.
- **`churn_probability` host vs container tidak bitwise-identik** (diff ~5.5e-17, level floating-point noise, bukan diskrepansi bermakna) — dalam toleransi `rtol=1e-6` yang sama dipakai KK2 M1.5, tidak dianggap kegagalan parity.

## Follow-up

- M3.2 (Real-Time Inference API): bangun service HTTP di atas image ini, menerima request sesuai skema M1.3, panggil `predict_active()` yang sama.
- M3.3 (Deployment ke Kubernetes): putuskan container registry (GHCR/Docker Hub/lainnya — sengaja dibiarkan terbuka dokumen arsitektur Bagian 10) dan pertimbangkan optimasi ukuran image kalau relevan terhadap waktu pull di cluster.
- M3.4 (Deteksi versi aktif tanpa restart): mekanisme `load_active_model()`/`resolve_alias_version()` yang dipakai di sini (alias `champion`, tanpa hardcode versi) sudah jadi fondasi yang tepat — tinggal ditambah mekanisme polling/refresh berkala di sisi service (M3.2/M3.4), bukan reimplementasi ulang.
