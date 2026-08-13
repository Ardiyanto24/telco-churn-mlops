# Logs — Milestone 3.1: Containerization dan Environment Konsisten

## Checkpoint 1 — Dockerfile, build sukses, sanity import, bukti KD-1

**Setup:** Docker Desktop dikonfirmasi tersedia sebelum plan ditulis (`docker --version` → 29.2.1, `docker info` sukses).

**Build image resmi:**
```
docker build -t churn-inference:m3.1 .
```
Sukses, exit 0. Seluruh dependency `pyproject.toml` (termasuk `lightgbm==4.7.0`, `xgboost==3.4.0`, `mlflow-skinny==3.15.1`) terinstal tanpa konflik resolver — total waktu build ~206s (dominan unduhan `scipy` 35.3MB + `nvidia_nccl_cu13` 252.4MB, dependency transitif `xgboost`).

```
docker images churn-inference:m3.1
```
→ `1.63GB` disk usage, `526MB` content size.

**Sanity import (image resmi, DENGAN libgomp1):**
```
docker run --rm churn-inference:m3.1 python -c "import churn_prediction, lightgbm, xgboost, sklearn, mlflow; print('ok')"
```
→ `ok`. Tidak ada `OSError`.

**Bukti negatif KD-1 (image percobaan, TANPA libgomp1):**
`Dockerfile.no-libgomp-test` dibuat sementara (baris `apt-get install libgomp1` dihapus), build `churn-inference:m3.1-no-libgomp`. Import command yang sama:
```
docker run --rm churn-inference:m3.1-no-libgomp python -c "import churn_prediction, lightgbm, xgboost, sklearn, mlflow; print('ok')"
```
→ GAGAL, exit 1:
```
OSError: libgomp.so.1: cannot open shared object file: No such file or directory
```
(traceback lengkap: `lightgbm/libpath.py` baris 49, `ctypes.cdll.LoadLibrary`). **Persis error yang diprediksi KD-1** (`docs/keterbatasan-diterima.md`) — dibuktikan nyata di base image `python:3.13-slim`, bukan diasumsikan dari kasus Prefect Managed yang beda konteks.

**Cleanup:** `Dockerfile.no-libgomp-test` dihapus, image `churn-inference:m3.1-no-libgomp` di-`docker rmi`. Image resmi `churn-inference:m3.1` diverifikasi ulang sukses import setelah cleanup (`ok`).

**Commit:** `ecb2698` — `feat(milestone-3.1): checkpoint 1 - Dockerfile dan verifikasi import/dependency`

## Checkpoint 2 — Script verifikasi parity, host vs container terhadap registry sungguhan

**Setup host:** venv proyek `.venv/` (Python 3.13.12) dikonfirmasi sudah punya `churn_prediction` terinstal. Kredensial `.env` di-load ke shell (`set -a && source .env && set +a`) — `container_smoke_test.py` (seperti `verify_before_promotion.py`) tidak memanggil `load_dotenv()` otomatis, baru gagal `RuntimeError: BATCH_READER_DB_URL tidak diset` sebelum env di-load manual (dikonfirmasi, bukan diasumsikan langsung jalan).

**Run host (baseline):**
```
./.venv/Scripts/python.exe scripts/container_smoke_test.py > host_output.json
```
→ exit 0. `row_count=1000`, `model_version="1"`. Baris pertama (`id=0,1,2` urutan `ORDER BY id`): `churn_probability` = `[0.0358, 0.00248, 0.5663]` — nilai baris `id=2` (~0.566) cocok persis dengan yang dicatat `milestones/1.5-inference-service/decisions.md` (dipilih sengaja karena berada di antara threshold uji 0.5 dan threshold produksi 0.6238) — sanity check independen bahwa sampel dan model yang dimuat konsisten dengan riwayat proyek.

**Rebuild image** (layer `COPY scripts/` berubah, layer `pip install` tetap cache):
```
docker build -t churn-inference:m3.1 .
```
Sukses, exit 0.

**Run container terhadap MLflow registry produksi sungguhan:**
```
docker run --rm --env-file .env churn-inference:m3.1 python scripts/container_smoke_test.py > container_output.json
```
→ exit 0. `row_count=1000`, `model_version="1"` — container berhasil resolve alias `champion` dan memuat model dari registry Postgres+S3 Supabase (**KK1 penuh terbukti**, bukan cuma sanity import Checkpoint 1).

**Perbandingan numerik (`np.allclose`/`np.array_equal`, `rtol=1e-6`, `atol=1e-8`):**
```
row_count: 1000 (host) vs 1000 (container)
model_version: 1 (host) vs 1 (container)
churn_probability np.allclose(rtol=1e-6): True
churn_probability EXACT bitwise equal: False
churn_probability baris berbeda (toleransi): 0/1000
churn_label exact match: True (0 baris berbeda dari 1000)
max abs diff proba: 5.551115123125783e-17
```
**KK2 terbukti**: 0/1000 baris berbeda dalam toleransi, `churn_label` identik 100%. Diff maksimum (~5.5e-17) berada di level floating-point rounding noise, bukan diskrepansi bermakna — dicatat sebagai temuan di `decisions.md` (bukan dianggap kegagalan parity).

**Commit:** `07d44e4` — `feat(milestone-3.1): checkpoint 2 - script verifikasi parity host vs container`

## Checkpoint 3 — Dokumentasi penutupan

`decisions.md`, `logs.md` (file ini), `report.md` ditulis setelah bukti Checkpoint 1-2 di atas tersedia — bukan ditulis lebih dulu lalu diasumsikan cocok. `CLAUDE.md` "Status Saat Ini" diperbarui menandai M3.1 selesai.
