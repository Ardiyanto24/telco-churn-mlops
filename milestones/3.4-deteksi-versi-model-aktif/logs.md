# Logs — Milestone 3.4: Deteksi Versi Model Aktif Tanpa Restart Penuh

## Checkpoint 1 — Mekanisme refresh (kode) + test

`pytest tests/api/ -v` → 15/15 lulus (4 test baru `_refresh_once`). `pytest tests/ -q` penuh → `201 passed, 359 warnings in 195.69s`. Regresi nol.

**Commit:** `bd8ff8f` — `feat(milestone-3.4): checkpoint 1 - mekanisme deteksi versi model tanpa restart`

## Checkpoint 2 — Deploy + verifikasi KK1/KK2 (kronologi investigasi bug lengkap)

**Build+deploy awal:** `docker build -t churn-inference:m3.4 .` sukses. Update `infra/k8s/deployment.yaml` image tag, `kubectl apply`. Pod baru `churn-api-59b57f785f-l6t82` `1/1 Running`, `RESTARTS: 0`, dicatat sebagai baseline.

**Percobaan pertama KK1 — GAGAL, gejala membingungkan:**
```
promote_active_alias.py 2 champion  (04:01:51 selesai)
poll /readyz tiap 2 detik selama 60+ detik -> TETAP model_version:1
```
Log pod menunjukkan warning `pyarrow mismatch` berulang tiap ~34 detik (menandakan reload DICOBA), tapi `/readyz` tidak pernah berubah.

**Investigasi bertahap (membuktikan/membantah hipotesis satu per satu):**
1. `resolve_alias_version()` host langsung 2x berturut — HASIL: `2`, `2`, konsisten benar. Bukan bug fungsi ini.
2. `kubectl exec` proses baru DI DALAM pod yang sama — HASIL: benar melihat `2`. Bukan masalah DNS/network container.
3. Reader loop panjang (`asyncio.to_thread`, host) 20 siklus, alias diubah dari proses TERPISAH di tengah — HASIL: reader mendeteksi perubahan dengan benar (t+15s). Bukan masalah caching koneksi jangka panjang.
4. Replika PERSIS logika `_refresh_once` (host, loop async) — HASIL: mendeteksi perubahan dengan benar di cycle pertama setelah alias diubah. Logika kode BENAR.
5. Replika yang sama via `kubectl exec` di DALAM container pod — HASIL: juga benar.

Kesimpulan sementara: logika `_refresh_once` TERBUKTI benar di semua isolasi — bug pasti ada di TEMPAT LAIN yang belum diuji (kombinasi resolve+load di proses uvicorn ASLI).

**Celah ditemukan: exception tertelan tanpa logging.** Ditambah `logger.warning`/`logger.info` eksplisit di `_refresh_once()` (lihat commit `feat` Checkpoint 2). Rebuild+redeploy (`kubectl rollout restart`).

**Log pod BARU mengungkap akar masalah:**
```
Gagal reload model alias 'champion' ke versi 2: FileNotFoundError(2, 'No such file or directory')
```
Pod baru ini bahkan GAGAL STARTUP (model champion=2 rusak saat itu) — `/readyz` 503, TAPI TIDAK crash (sesuai desain Keputusan #5 M3.2/#3 M3.4).

**Reproduksi presisi via container Linux terpisah:**
```
kubectl exec -n churn-prediction deploy/churn-api -- python -c "load_model_by_version('2')"
FileNotFoundError: [Errno 2] No such file or directory: '/tmp/tmpkpe28st4/artifacts\\bundle.joblib'
```
Backslash literal dalam path — root cause lintas-platform Windows→Linux.

**Registrasi kandidat baru untuk isolasi (versi 3, kode SAAT INI termasuk `.as_posix()` M2.5):**
```
scripts/register_candidate_model.py -> version 3
kubectl exec ... load_model_by_version('3') -> FileNotFoundError SAMA PERSIS
```
Membuktikan bug MASIH AKTIF di kode saat ini, bukan cuma artifact lama versi 2.

**Perbandingan manifest `MLmodel` byte-per-byte (S3, `boto3` langsung), versi 1 (bekerja) vs versi 3 (gagal):**
```yaml
# versi 1 (BEKERJA):
path: artifacts/bundle.joblib
uri: C:\Users\LENOVO\AppData\Local\Temp\tmpe2tkpaeg\bundle.joblib

# versi 3 (GAGAL):
path: artifacts\bundle.joblib
uri: C:/Users/LENOVO/AppData/Local/Temp/tmphdmsq6v1/bundle.joblib
```
`.as_posix()` (M2.5) memengaruhi `uri` (benar, forward-slash) TAPI TIDAK memengaruhi `path` (backslash, SALAH) — field yang BENAR-BENAR dipakai saat load.

**Percobaan `str(bundle_path)` (kembali ke pola pra-M2.5) — GAGAL DENGAN CARA BERBEDA:**
```
version 4 registered
kubectl exec ... load_model_by_version('4') -> mlflow.exceptions.MlflowException: No such artifact: ''
```
Mengonfirmasi `str(bundle_path)` BUKAN solusi.

**Root cause PERSIS ditemukan** — `.venv/Lib/site-packages/mlflow/pyfunc/model.py` baris ~1158:
```python
saved_artifact_subpath = os.path.join(saved_artifacts_dir_subpath, relative_path)
```
Kode INTERNAL MLflow (bukan kode proyek ini) -- `os.path.join` di Windows SELALU backslash, terlepas dari format source path caller.

**Fix diterapkan** (`_fix_windows_artifact_paths()`, `registry.py`) — registrasi ulang:
```
scripts/register_candidate_model.py -> version 5
kubectl exec ... load_model_by_version('5') -> Exit 137 (OOM killed, resource limit pod 768Mi bentrok proses exec tambahan)
```
Pod utama ikut ter-restart 1x akibat OOM ini (efek samping tidak disengaja) — dicatat, baseline diulang bersih setelahnya.

**Verifikasi fix via container Linux TERPISAH (bukan exec di pod produksi):**
```
docker run --rm -e MLFLOW_TRACKING_URI=... churn-inference:m3.4 python -c "load_model_by_version('5')"
version 5 OK di container Linux terpisah: <class 'mlflow.pyfunc.PyFuncModel'>
```

**Regresi ditemukan+diperbaiki:** `pytest tests/ -q` pertama setelah fix → 8 failed + 4 errors (fix pertama tidak mengecek skema S3, memaksa boto3 untuk SEMUA registrasi termasuk test suite SQLite lokal). Ditambah pengecekan `artifact_uri.startswith("s3://")` sebelum menjalankan fix. Re-run → `201 passed, 359 warnings in 462.94s` (dan re-run lebih cepat berikutnya `215.19s` setelah cache warm).

**Pemulihan state registry**: `champion` sempat menunjuk versi 2 (rusak) selama debugging — dikembalikan ke versi 1:
```
promote_active_alias.py 1 champion -> "Alias 'champion' -> churn_prediction_model version 1"
```

**Rebuild final + redeploy bersih:**
```
docker build -t churn-inference:m3.4 .  (dengan fix registry.py + logging app.py)
kubectl rollout restart deployment/churn-api -n churn-prediction
```
Pod baru `churn-api-6bc9d7f57-q7hn5`, `1/1 Running`, `RESTARTS: 0` — baseline bersih final.

**Verifikasi KK1 NYATA (baseline bersih):**
```
BEFORE: {"status":"ready","model_version":1}
promote_active_alias.py 5 champion  -- selesai 04:18:10.625Z
poll /readyz tiap 2s...
DETECTED model_version:5 at 04:18:52.243Z  (~42 detik setelah promosi)
kubectl get pods -> churn-api-6bc9d7f57-q7hn5, RESTARTS: 0 (SAMA, tidak restart)
```

**Verifikasi KK2 NYATA (rollback, pod SAMA berkelanjutan):**
```
promote_active_alias.py 1 champion  -- selesai 04:19:23.229Z
poll /readyz...
DETECTED model_version:1 at 04:19:33.343Z  (~10 detik -- siklus polling kebetulan sudah dekat)
kubectl get pods -> churn-api-6bc9d7f57-q7hn5, RESTARTS: 0 (SAMA sepanjang KEDUA uji coba)
```

**Verifikasi state akhir registry:**
```
champion -> 1
challenger -> 5
```
Bersih — konsisten kondisi sebelum milestone dimulai (`champion=1`), `challenger` menunjuk kandidat kerja hasil fix (bukan artifact rusak).

**Commit:**
- `f477836` — `fix(inference): perbaiki path artifact backslash MLmodel manifest (Windows->Linux)`
- `1c3151e` — `feat(milestone-3.4): checkpoint 2 - deploy ulang dan verifikasi KK1/KK2 nyata`
