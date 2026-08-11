# Keputusan — Milestone 1.2: Modularisasi Preprocessing dan Feature Engineering

**Catatan proses:** Draf plan pertama milestone ini sempat membuat beberapa asumsi tanpa bertanya ke user terlebih dahulu — antara lain mengasumsikan tidak ada artifact asli dari Kaggle (`preprocessor.joblib`/`model_final.joblib`), mengasumsikan konvensi kolom PascalCase, dan mengunci versi dependency di awal. User mengoreksi ini secara eksplisit sebelum eksekusi dimulai. Enam keputusan di bawah adalah hasil klarifikasi ulang, bukan asumsi sepihak.

## 1. Konvensi kolom: snake_case (`telco_customers_synthetic`)

**Keputusan:** Modul `transform` menerima DataFrame dengan nama kolom **snake_case** (`gender`, `senior_citizen`, `total_charges`, `multiple_lines`, dst — sesuai skema `telco_customers_synthetic`, `docs/03-notebook-audit/notebook-audit.md` Bagian H.3), BUKAN PascalCase seperti notebook asli/`telco_customers_source`.

**Kenapa:** User secara eksplisit memilih ini — bukan rekomendasi saya (saya merekomendasikan PascalCase karena satu-satunya yang punya data nyata untuk diuji sekarang, tapi user punya konteks arah jangka panjang sistem yang tidak saya miliki). Konsekuensi yang harus dikelola sadar: `telco_customers_synthetic` masih 0 baris (generator belum aktif) — tidak ada data snake_case nyata untuk diuji langsung, sehingga strategi verifikasi Checkpoint 5 memakai data `telco_customers_source` (PascalCase, 594.194 baris nyata) yang di-*rename* ke snake_case sebelum diproses. Ini menutup KT-1 (`docs/keputusan-tertunda.md`) sebagai keputusan Milestone 1.2 — formal Milestone 1.6 (kesepakatan jalur komunikasi perubahan skema, dst) tetap menyusul terpisah.

## 2. Dependency: tidak dikunci di awal — dibangun dulu, dikunci di akhir setelah teruji

**Keputusan:** `pyproject.toml` awal memakai constraint terbuka — hanya batas bawah yang punya bukti (`scikit-learn>=1.2`), sisanya (`pandas`, `numpy`, `joblib`) tanpa batas atas. Versi eksak dikunci di Checkpoint 6 (task terakhir), setelah seluruh test lulus di environment kerja nyata, berdasarkan `pip freeze` dari venv yang terbukti jalan.

**Kenapa:** User eksplisit: "dependency mungkin baru bisa dikunci setelah seluruh pipeline dibangun dan dilakukan testing". Tidak ada bukti versi asli DS di manapun di 7 notebook (KT-3) — mengunci angka spesifik di awal cuma tebakan yang bisa langsung salah begitu ada kebutuhan baru saat integrasi ke Milestone 1.5/2.x. `scikit-learn>=1.2` tetap dipasang sejak awal sebagai batas bawah karena itu bukti konkret dari kode notebook sendiri (cell 11 memakai `OneHotEncoder(sparse_output=False, ...)` — parameter `sparse_output` baru ada di sklearn ≥1.2, menggantikan `sparse` yang deprecated) — bukan tebakan, jadi aman dikunci lebih dini sebagai batas bawah saja (bukan pin eksak).

## 3. Cakupan modul: preprocessing/feature engineering saja, TIDAK termasuk `DataSplitter`

**Keputusan:** Port `StructuralEncoder`, `FeatureEngineer`, `ColumnDropper`, `BinaryEncoder`, `OHEWrapper`, `ScalerWrapper`, `PreprocessingPipeline` (cell 7-13 `tccp-preprocessing-v2.ipynb`) satu-satu, nama kolom internal disesuaikan snake_case (Keputusan #1). `DataSplitter` (cell 14) **tidak** diport, dan **tidak dibutuhkan** untuk verifikasi (lihat Keputusan #4).

**Kenapa:** Split train/val/test adalah kebutuhan *training* (di luar cakupan sistem ini per `CLAUDE.md`), bukan kebutuhan jalur *serving* — batch DAG (Orang #2) dan real-time API (Orang #3) tidak pernah perlu men-split ulang data yang datang, mereka hanya transform data baru. Rencana awal sempat memakai `DataSplitter` untuk reproduksi fit demi verifikasi — tidak lagi perlu karena sekarang ada artifact `preprocessor.joblib` asli untuk dipakai langsung.

## 4. Verifikasi KK2: "graft" parameter fitted dari `preprocessor.joblib` asli — bukan reproduksi fit

**Keputusan:** Ekstrak parameter fitted langsung dari `artifacs/proprocessor/preprocessor.joblib` asli (`StandardScaler.mean_`/`.scale_`, `OneHotEncoder.categories_`, dst) dan suntikkan langsung ke instance transformer kita (skip `fit()`, langsung `transform()`). Verifikasi: ambil baris nyata dari `telco_customers_source` (Supabase) → jalankan tanpa diubah (PascalCase) lewat `preprocessor.joblib` asli (ground truth) → jalankan versi di-rename snake_case lewat modul kita yang sudah di-graft → bandingkan nilai per fitur.

**Kenapa:** Ini bukti KK2 yang jauh lebih kuat dan sederhana daripada reproduksi split+fit dari nol (rencana awal, rawan gagal kalau replikasi `DataSplitter` ada perbedaan halus). Grafting valid karena `StandardScaler`/`OneHotEncoder` menyimpan parameter fitted berbasis **urutan posisi kolom saat fit**, bukan nama kolom — jadi nama kolom snake_case kita tidak masalah selama urutan kolom yang diproses tiap step sama persis dengan urutan asli notebook. **Risiko yang dikelola saat eksekusi:** `joblib.load()` pada file yang class-nya didefinisikan di kernel Kaggle (`__main__`) sering gagal di environment lain karena pickle butuh resolusi class by-module-path — ditangani dengan shim `sys.modules` kalau load langsung gagal, didokumentasikan di `logs.md` apa pun hasilnya (bukan diasumsikan mulus).

## 5. Struktur package: `src/churn_prediction/transform/`, `pyproject.toml` + `setuptools`

**Keputusan:** Package `churn_prediction` di `src/churn_prediction/`, sub-modul `transform/`. `pyproject.toml` (PEP 621, build-backend `setuptools`).

**Kenapa:** Dikonfirmasi langsung oleh user. Nama generik supaya bisa diperluas Milestone 1.3 (`churn_prediction.schema`) dan 1.5 (`churn_prediction.inference`) di namespace yang sama. `setuptools` dipilih atas `hatchling`/`poetry` karena paling minim-kejutan saat di-containerize nanti (Milestone 3.1). `src/`-layout mencegah `pip install -e .` diam-diam mengimpor dari cwd yang belum ter-install benar — relevan untuk KK3 (modul harus bisa dipanggil dari environment terpisah).

## 6. Folder `artifacs/` (gitignored) untuk artifact asli DS

**Keputusan:** User sudah menaruh `artifacs/model/model_final.joblib` dan `artifacs/proprocessor/preprocessor.joblib` di root repo `deployment-mlops`. Ditambahkan `artifacs/` ke `.gitignore`. Tidak pernah di-commit.

**Kenapa:** File model binary tidak boleh masuk git (bukan kode, membengkakkan repo, dan bukan cara resmi mengelola versi model — itu tugas MLflow registry di Milestone 2.1). Penamaan folder/file (`artifacs/`, `proprocessor/` — bukan `artifacts/`/`preprocessor/`) diikuti apa adanya seperti yang sudah dibuat user, tidak diminta rename. `.gitignore` disentuh secara sengaja untuk task ini (mencegah kebocoran file besar/model ke git history) — berbeda dari sesi-sesi lain di mana `.gitignore` sengaja tidak disentuh karena bukan bagian task saat itu.

## Catatan batas eksplorasi

Saat mencari lokasi file artifact, sempat tidak sengaja mengeksplorasi folder sibling di luar `deployment-mlops` (`../deployment/`, `../data-generator/`). User menegaskan pengerjaan milestone ini **tidak boleh keluar dari folder `deployment-mlops`** — folder-folder itu di luar cakupan project ini dan tidak dirujuk lagi di keputusan atau task manapun pada milestone ini.
