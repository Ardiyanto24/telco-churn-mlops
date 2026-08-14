# Decisions — Milestone 3.4: Deteksi Versi Model Aktif Tanpa Restart Penuh

## Konteks

Menghilangkan keterbatasan yang sengaja diterima sejak M3.2: model dimuat sekali saat startup, restart manual diperlukan untuk pick up versi `champion` baru. Tidak ada keputusan yang memerlukan `AskUserQuestion` — mekanisme (polling) forced oleh temuan arsitektural (webhook MLflow tidak viable), sisanya pilihan implementasi berdampak rendah/mudah diubah.

**Catatan penting**: milestone ini juga menemukan+memperbaiki SATU bug produksi besar (bug backslash artifact path, Keputusan #6) yang TIDAK direncanakan di plan awal — ditemukan saat verifikasi KK1/KK2 gagal berulang kali dengan gejala membingungkan, di-root-cause sampai ke baris kode internal MLflow itu sendiri.

## Keputusan Teknis

### 1. Mekanisme: polling berkala (`asyncio` background task), BUKAN webhook

**Keputusan:** Background task `asyncio` mengecek `resolve_alias_version()` tiap 30 detik (`MODEL_REFRESH_INTERVAL_SECONDS`), reload model penuh HANYA kalau versi berubah.

**Kenapa:** Forced — dikonfirmasi lewat pembacaan source `mlflow-skinny` terinstal: webhook memang ADA implementasinya (bukan eksklusif Databricks), TAPI titik pemicu pengiriman untuk event alias berubah HANYA di-wire ke `mlflow/server/handlers.py` (dipanggil proses `mlflow server` menerima REST request) — `SqlAlchemyStore.set_registered_model_alias()` (dipakai `registry.py` lewat direct-Postgres, M2.1 Keputusan #2, TANPA proses `mlflow server`) tidak pernah memanggil `deliver_webhook`. Cek versi dulu (murah) sebelum reload penuh (mahal, fetch S3) — hemat resource.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- Webhook — DITOLAK: tidak viable secara arsitektural, butuh proses `mlflow server` yang sengaja ditiadakan M2.1.
- Reload penuh tiap interval tanpa cek versi dulu — DITOLAK: boros fetch S3 tanpa manfaat.

### 2. State `app.state` digabung jadi satu objek immutable (`LoadedModel`), di-swap atomik

**Keputusan:** `model`/`model_version`/`load_error` (3 atribut terpisah M3.2/M3.3) digabung jadi `dataclass(frozen=True) LoadedModel`, di-assign sebagai satu objek baru tiap refresh.

**Kenapa:** Forced by race condition baru — CPython GIL menjamin assignment satu reference atomik, TIDAK menjamin atomisitas kalau 3 atribut ditulis terpisah. Tanpa ini, request bisa dapat `model` baru tapi `model_version` lama (lineage salah, diam-diam).

**Opsi yang Dipertimbangkan tapi Ditolak:** `threading.Lock`/`asyncio.Lock` eksplisit — DITOLAK: menambah kompleksitas untuk masalah yang lebih sederhana selesai lewat immutable object + atomic reference swap.

### 3. `_refresh_once()` dipakai bersama startup DAN periodic refresh

**Keputusan:** Satu fungsi `_refresh_once(app)` dipanggil baik saat `lifespan` startup MAUPUN tiap iterasi `_refresh_loop()` — TIDAK diduplikasi. Refresh gagal TAPI model lama masih ada → model lama TETAP dipakai (TIDAK downgrade ke `None`) — beda dari kegagalan startup pertama kali (M3.2 Keputusan #5, dipertahankan).

**Kenapa:** Satu sumber kebenaran loading logic.

**Verifikasi tak terduga (bukti kuat)**: pod yang STARTUP-nya gagal (karena champion sempat menunjuk artifact rusak, lihat Keputusan #6) berhasil SELF-HEAL otomatis lewat mekanisme yang SAMA begitu champion dikembalikan ke versi yang bisa dimuat — TANPA restart pod (`RESTARTS: 0` sepanjang proses) — bukti nyata `_refresh_once()` bekerja identik untuk kasus "startup gagal lalu pulih" dan "model gagal dimuat lalu ganti versi", persis seperti didesain.

### 4. Interval polling: 30 detik (default), via env var `MODEL_REFRESH_INTERVAL_SECONDS`

**Keputusan:** Default 30 detik.

**Kenapa:** Tidak ada SLA formal (KT-5). 30 detik cukup cepat, tidak boros query Postgres.

**Verifikasi nyata:** KK1 terdeteksi ~42 detik (interval 30s + waktu reload), KK2 ~10 detik (kebetulan siklus polling sudah dekat) — keduanya dalam rentang wajar.

### 5. `asyncio.to_thread()` untuk panggilan registry blocking

**Keputusan:** `registry.resolve_alias_version()`/`load_active_model()` dipanggil lewat `await asyncio.to_thread(...)`.

**Kenapa:** Forced — tanpa ini, panggilan blocking (I/O Postgres+S3) memblokir event loop, menunda dispatch request `/predict` lain.

### 6. Bug ditemukan+diperbaiki: artifact path backslash MLmodel manifest (Windows→Linux)

**Ditemukan saat:** Checkpoint 2, verifikasi KK1 GAGAL berulang — `/readyz` tidak pernah berubah versi meski registry sudah dipromosikan, TANPA error terlihat (exception tertelan tanpa logging — celah desain yang JUGA diperbaiki, lihat commit `feat` Checkpoint 2).

**Investigasi (kronologi, lihat `logs.md` untuk detail lengkap):**
1. Dugaan awal: caching koneksi database jangka panjang — DIBANTAH lewat reproduksi terisolasi (sync loop, `asyncio.to_thread` loop, `kubectl exec` proses baru) — SEMUA berhasil melihat perubahan versi dengan benar.
2. Ditambah logging eksplisit (celah nyata: exception di `_refresh_once()` sebelumnya tertelan tanpa jejak) — mengungkap pesan `FileNotFoundError` saat reload.
3. Root cause DITEMUKAN: `context.artifacts["bundle"]` path resolve ke `/tmp/xxx/artifacts\bundle.joblib` (backslash literal) — dibandingkan manifest `MLmodel` byte-per-byte (S3, `boto3` langsung) antara versi 1 (bekerja, field `path: artifacts/bundle.joblib`) vs versi 3 (kandidat baru, gagal, field `path: artifacts\bundle.joblib`).
4. Root cause PERSIS: `mlflow/pyfunc/model.py` baris ~1158 (kode INTERNAL MLflow, bukan kode proyek ini) memakai `os.path.join(saved_artifacts_dir_subpath, relative_path)` untuk membangun field `path` — di Windows `os.path.join` SELALU menghasilkan backslash, TERLEPAS dari apakah source path (`bundle_path.as_posix()` vs `str(bundle_path)`, mitigasi M2.5) posix atau native.

**Kesimpulan penting:** mitigasi Milestone 2.5 (`bundle_path.as_posix()`) TERNYATA menyasar variabel yang SALAH — memengaruhi field `uri` (informational, tidak dipakai saat load), BUKAN field `path` (yang benar-benar dipakai `context.artifacts[key]` saat `load_context()`). Bug lintas-platform Windows→Linux TIDAK PERNAH benar-benar tertutup sejak M2.5 — versi 1 (champion produksi) cuma kebetulan/historis benar (alasan pasti tidak diketahui, mungkin versi mlflow-skinny atau proses registrasi berbeda saat itu), BUKAN karena mitigasi M2.5 bekerja.

**Fix:** `_fix_windows_artifact_paths()` (`registry.py`) — post-process manifest `MLmodel` di S3 SETELAH `log_model()` selesai, normalisasi backslash jadi forward-slash pada field `path`. Dicek dulu `artifact_uri` run (skema `s3://`) sebelum dijalankan — HANYA berlaku untuk registry produksi (S3), di-skip aman untuk test suite yang sengaja pakai tracking URI SQLite lokal (register+load selalu di OS yang sama, bug ini tidak pernah relevan di sana).

**Verifikasi:**
- Percobaan PERTAMA (skip-check belum ada): fix diterapkan, versi 3 diverifikasi TETAP gagal (fix ditulis sebelum sadar perlu skip-check S3) — bukan kegagalan fix itu sendiri, tapi karena versi 3 diregistrasi SEBELUM fix commit ke source tree.
- Versi 4 (percobaan `str(bundle_path)` tanpa `.as_posix()`) — GAGAL dengan cara BERBEDA (`MlflowException: No such artifact`) — dikonfirmasi `str(bundle_path)` BUKAN solusi, source path tetap `.as_posix()`.
- Versi 5 (registrasi ulang dengan fix `_fix_windows_artifact_paths()` AKTIF) — berhasil dimuat dari container Linux TERPISAH (`docker run`, bukan `kubectl exec` di pod produksi — lihat catatan resource di bawah).
- `pytest tests/ -q` PERTAMA setelah fix: 8 gagal + 4 error (fix pertama TIDAK mengecek `artifact_uri`, memaksa S3 untuk SEMUA registrasi termasuk test suite yang pakai SQLite lokal) — diperbaiki dengan pengecekan skema `s3://`, lalu 201/201 lulus.

**Dampak operasional ditemukan selama investigasi**: alias `champion` PRODUKSI sempat tanpa sengaja menunjuk versi 2 (artifact rusak) selama proses debugging (dipromosikan berulang kali untuk reproduksi) — DIKEMBALIKAN ke versi 1 dan diverifikasi ulang SEBELUM commit fix. Ini murni akibat proses debugging sesi ini, TIDAK ada dampak ke pemanggil produksi nyata (tidak ada trafik nyata selama jendela waktu ini).

**Opsi yang Dipertimbangkan tapi Ditolak:**
- Registrasi dari Linux (bukan Windows) untuk menghindari bug ini sepenuhnya — DITOLAK: tidak ada environment Linux yang tersedia untuk registrasi rutin di proyek solo ini, mengubah kebiasaan kerja jauh lebih mahal daripada fix post-process yang sudah terbukti bekerja.
- `str(bundle_path)` (mengembalikan ke pola sebelum M2.5) untuk source path — DITOLAK: dibuktikan GAGAL DENGAN CARA BERBEDA (versi 4), bukan solusi.

## Catatan Operasional: `kubectl exec` untuk debugging OOM-killed pod

Selama investigasi, `kubectl exec` yang menjalankan proses Python tambahan (load model penuh) DI DALAM pod produksi (resource limit 768Mi, M3.3) memicu OOM kill (exit 137) dan **1 restart pod tidak disengaja**. Verifikasi KK1/KK2 final (Checkpoint 2) sengaja diulang dari baseline pod BERSIH (`RESTARTS: 0`) setelah insiden ini, memakai container Linux TERPISAH (`docker run`, di luar resource limit K8s) untuk kebutuhan debugging berikutnya -- bukan `kubectl exec` di pod produksi.
