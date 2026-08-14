# Decisions — Milestone 3.6: Monitoring Drift dan Kualitas Model

## Konteks

Dokumen arsitektur (Bagian 10) menandai threshold drift sebagai "digali bersama Orang #1 dan Orang #3, setelah baseline data training tersedia" — bukan keputusan sepihak. Karena proyek ini solo, "kerja sama" itu terwujud lewat `AskUserQuestion` langsung ke user (dua putaran, dengan penjelasan detail + contoh numerik dari data nyata proyek sebelum keputusan final), bukan diasumsikan.

## Keputusan Teknis

### 1. Metodologi drift dua tingkat: PSI (Tier 1) + KS-test/Chi-square (Tier 2), dihitung sekaligus tiap siklus

**Keputusan:** Setiap fitur (29 fitur model + output prediksi) dihitung DUA metrik sekaligus tiap siklus komputasi: PSI (Population Stability Index, heuristik cepat, satu rumus untuk numerik+kategorikal) DAN uji statistik formal (KS-test untuk 4 fitur numerik + output, Chi-square untuk 25 fitur kategorikal/binary/structural/one-hot) — bukan PSI dulu lalu Tier 2 cuma kalau PSI flag.

**Kenapa:** Ide dua-tingkat ini datang dari user sendiri. Setelah penjelasan detail dengan contoh numerik (fitur `Contract`: PSI=0.093 "belum signifikan" vs pergeseran mentah 15 poin persentase yang kelihatan besar), user memilih PSI+KS/Chi-square (bukan perluasan gaya M2.4) sebagai metodologi, dan "selalu berbarengan" (bukan Tier 2 cuma trigger kalau Tier 1 flag) sebagai jadwal — alasan user: skala data proyek ini (ribuan baris, bukan big data) membuat penghematan komputasi dari eskalasi bertingkat tidak signifikan, sementara menampilkan KEDUA sinyal berdampingan di dashboard lebih informatif.

**Bukti nyata (data produksi sungguhan, bukan simulasi) dari nilai yang ditemukan menegaskan alasan dua-tingkat ini genuinely bermanfaat**: run pertama `compute_drift.py --mode current` (baseline 594rb baris vs 1.000 baris `telco_customers_synthetic`) menemukan `service_count` dan `tenure` verdict **"stop" dari p-value** (p≈0.0000, sample size besar membuat p-value sangat sensitif) MESKI PSI keduanya rendah (0.067 dan 0.025, jauh di bawah ambang flag 0.1) — pola klasik "signifikan secara statistik, tidak signifikan secara praktis" yang HANYA bisa ditangkap dengan menjalankan kedua tier bersamaan, bukan cuma satu.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Perluasan gaya M2.4** (reuse `check_category_distribution` untuk 16 fitur diskret + fungsi baru deviasi rata-rata untuk 4 numerik+output) — DITOLAK oleh user setelah dijelaskan trade-off: 2 metodologi terpisah dengan 2 set threshold, dan deviasi rata-rata TIDAK menangkap perubahan variance/bentuk distribusi (mis. distribusi jadi bimodal tapi rata-rata sama).
- **Tier 2 hanya trigger kalau Tier 1 PSI sudah flag** (eskalasi bertingkat, pola "cheap screen dulu") — DITOLAK: penghematan komputasi tidak signifikan di skala data proyek ini, menambah kompleksitas state (perlu tahu fitur mana yang "sedang diselidiki") tanpa manfaat sepadan.

### 2. Cakupan jalur: BATCH SAJA sekarang, real-time didefer (KT-9)

**Keputusan:** Baseline dari `telco_customers_source`, data "sekarang" dari `telco_customers_synthetic`, output dari `predictions.batch_predictions` — TIDAK menyentuh real-time API sama sekali.

**Kenapa:** Real-time API (M3.2-3.4) tidak punya persistence payload/prediksi (cuma dikembalikan di response HTTP lalu hilang) — menambahnya sekarang berarti write path baru ke `/predict` demi kebutuhan monitoring yang belum ada konsumennya. Konsisten pola established KT-5 (verdict latensi)/KT-7 (parity CI penuh)/KT-8 (deployment always-on) — SEMUA menunda pekerjaan real-time-spesifik sampai ada pemanggil eksternal nyata. Trafik real-time API sejauh ini murni verifikasi manual (puluhan-ratusan request per sesi test M3.2-3.5) — drift monitoring atas sample sekecil ini tidak bermakna (noise, bukan sinyal produksi nyata).

**Opsi yang Dipertimbangkan tapi Ditolak:** Bangun kedua jalur sekarang (tambah persistence baru ke real-time API) — DITOLAK user secara eksplisit ("batch saja sekarang, untuk real time ditunda"), dicatat sebagai KT-9 (`docs/keputusan-tertunda.md`) dengan trigger peninjauan: pemanggil eksternal nyata muncul.

### 3. Komputasi statistik (PSI+KS/Chi2) terjadi di GitHub Actions, BUKAN di exporter K8s

**Keputusan:** `scripts/compute_drift.py` (butuh `PreprocessingPipeline` fitted + scipy) dijalankan di GitHub Actions (`ubuntu-latest`); `orchestration/monitoring/drift_exporter.py` (K8s, selalu nyala) HANYA baca tabel hasil jadi `drift.drift_check_results`.

**Kenapa:** Unpickle bundle MLflow (dibutuhkan untuk transform fitur) TIDAK BISA dihindari butuh lightgbm/xgboost/mlflow-skinny importable — pickle mendeserialisasi seluruh object graph sekaligus, tidak bisa parsial. `ubuntu-latest` SUDAH terbukti aman untuk lightgbm (KD-1, dipakai `batch-scoring.yml`/`synthetic-auto-scoring.yml`). Exporter K8s (selalu nyala, lebih terekspos ke jaringan) tetap LEAN (621MB vs `churn-inference` 1.63GB) — pola sama gerbang kualitas M2.4/exporter M3.5 (compute di pipeline, exporter cuma re-publish state terakhir).

**Tidak ada alternatif dipertimbangkan** — forced by keterbatasan teknis pickle (bukan pilihan desain bebas).

### 4. Exporter drift TERPISAH dari `pipeline_health_exporter.py`

**Keputusan:** `drift_exporter.py` adalah proses, image, Deployment, dan Service K8s yang BERBEDA dari exporter M3.5.

**Kenapa:** Konsisten catatan forward-compat M3.5 sendiri (`milestones/3.5-.../decisions.md` Keputusan #1: "M3.6 tinggal tambah exporter drift BARU") — juga selaras 3 pilar observability terpisah di Bagian 8 dokumen arsitektur (infra/operational vs data&model drift vs pipeline health, sifat berbeda: satu bicara "apakah service hidup", satu lagi bicara "apakah data/model masih benar").

**Opsi yang Dipertimbangkan tapi Ditolak:** Extend `pipeline_health_exporter.py` dengan gauge drift tambahan (satu proses, satu image) — DITOLAK: setelah desain akhir (exporter drift ternyata SAMA-SAMA lean, cuma baca tabel), argumen "beda dependency profile" yang tadinya jadi alasan utama pemisahan tidak sekuat awal, TAPI pemisahan pilar observability (bukan cuma soal dependency) tetap berlaku dan sudah jadi preseden tercatat M3.5 — mengubahnya sekarang berarti kontradiksi dengan catatan forward-compat yang sudah dibuat sadar.

### 5. Trigger event-driven via `workflow_run`, TIDAK mengubah `synthetic-auto-scoring.yml`

**Keputusan:** `.github/workflows/drift-monitoring.yml` listener `workflow_run` ke workflow `synthetic-auto-scoring` (M2.9) yang SUDAH ADA — file M2.9 itu sendiri sama sekali tidak disentuh.

**Kenapa:** Prinsip yang sama dipertahankan M3.5 (exporter membaca dari luar tanpa menyentuh kode pipeline Orang #2) — M3.6 murni observasional. `workflow_run` di GitHub Actions bekerja terlepas dari apa yang memicu workflow SUMBER (di sini `repository_dispatch` dari trigger Postgres M2.9) selama workflow file-nya ada di branch default — diverifikasi nyata bekerja (Task 10: trigger manual `workflow_dispatch` sukses menulis 30 baris baru).

**Tidak ada alternatif dipertimbangkan** — forced by prinsip "M3.x tidak mengubah kode Orang #2" yang sudah konsisten dipegang sejak M3.5.

### 6. Baseline: sample acak 10.000 baris, format panjang, dihitung SEKALI

**Keputusan:** `drift.baseline_sample(feature_name, value)` — 10.000 baris acak dari `telco_customers_source` (594.194 baris, byte-identik data training per `notebook-audit.md` Bagian H.2), ditransformasi+diskor SEKALI (`scripts/compute_drift.py --mode baseline`), TIDAK dihitung ulang otomatis.

**Kenapa:** "Baseline data training" adalah referensi TETAP secara definisi (bukan rolling window seperti baseline M2.4) — dihitung ulang tiap siklus tidak masuk akal dan boros (594rb baris full scan tiap poll). 10.000 baris cukup besar untuk KS-test/Chi-square bermakna (bukan angka arbitrer — literatur uji statistik dua-sampel umumnya sudah stabil di ribuan sampel) tanpa overhead menyimpan 594rb baris penuh (~17,4 juta baris kalau semua fitur×semua baris, terlalu besar untuk kebutuhan ini). Format panjang (`feature_name`+`value`, bukan 29 kolom lebar) menghindari schema churn kalau fitur model berubah di masa depan (retrain, fitur baru/dihapus) — tabel tidak perlu `ALTER TABLE`, cukup `feature_name` baru muncul di baris.

**Opsi yang Dipertimbangkan tapi Ditolak:** Simpan seluruh 594.194 baris sebagai baseline (populasi penuh, bukan sample) — DITOLAK: overhead penyimpanan besar tanpa manfaat statistik sepadan (KS-test/Chi-square/PSI semua konvergen dengan sample size jauh lebih kecil dari populasi penuh), memperlambat query baseline tiap siklus komputasi current-window.

### 7. Baseline output prediksi dihitung dengan model versi AKTIF saat baseline dihitung

**Keputusan:** `predict_active()` (alias `champion`, versi manapun yang aktif SAAT script `--mode baseline` dijalankan) dipakai untuk skor `churn_probability` baseline — bukan versi model tertentu yang dikunci permanen.

**Kenapa:** Ini satu-satunya cara mendapatkan distribusi prediksi baseline yang genuinely comparable dengan cara model AKTIF akan memprediksi data baru — skor dari model versi lama (kalau ada) tidak relevan untuk membandingkan "apakah PREDIKSI MODEL SEKARANG mulai bergeser".

**Keterbatasan diterima:** Kalau `champion` berganti versi (M2.8, promosi/rollback) SETELAH baseline dihitung, baseline output jadi "stale" relatif model baru — perbandingan drift output selanjutnya akan mencampur "perubahan data" dengan "perubahan model" (confounded), bukan murni mengukur drift data. Dicatat eksplisit di `report.md`, TIDAK diselesaikan sekarang (di luar cakupan M3.6 — butuh mekanisme re-trigger baseline otomatis saat alias berganti, kandidat follow-up).

**Tidak ada alternatif dipertimbangkan** — forced by tujuan baseline (representasi model YANG SEDANG DIPAKAI, bukan model historis).

### 8. Dua role Postgres baru: `drift_writer` (scripts, GitHub Actions) dan `drift_reader` (exporter, K8s)

**Keputusan:** `drift_writer` — SELECT `telco_customers_source`+`telco_customers_synthetic`+`predictions.batch_predictions`, SELECT+INSERT `drift.baseline_sample`+`drift.drift_check_results`. `drift_reader` — SELECT-only `drift.drift_check_results` SAJA.

**Kenapa:** Pola "satu role per pola akses" konsisten sejak M2.1/M2.4/M2.5/M2.9/M3.5. `drift_reader` sengaja dibuat TIDAK BISA melihat `drift.baseline_sample` (data baris-level, granular) maupun tabel produksi manapun — komponen yang selalu nyala dan lebih terekspos (K8s Service, dijangkau Prometheus terus-menerus) diberi akses paling sempit yang mungkin, cuma tabel hasil agregat.

**Opsi yang Dipertimbangkan tapi Ditolak:** Satu role tunggal untuk keduanya (`drift_writer` dipakai juga oleh exporter) — DITOLAK: melanggar least-privilege, exporter K8s tidak butuh SELECT ke data pelanggan mentah sama sekali untuk fungsinya (cuma butuh hasil agregat), memberi akses lebih dari yang dibutuhkan tanpa alasan.

### 9. Verdict gabungan = terburuk dari verdict PSI dan verdict p-value

**Keputusan:** `combined_verdict(psi, pvalue)` — "stop" kalau SALAH SATU tier bilang stop, "flag" kalau salah satu bilang flag (dan tidak ada yang stop), "pass" kalau keduanya pass. Threshold PSI: <0.1 pass, 0.1-0.25 flag, ≥0.25 stop (konvensi industri credit-scoring/MLOps, dipakai luas). Threshold p-value: ≥0.05 pass, 0.01-0.05 flag, <0.01 stop (konvensi signifikansi statistik α standar).

**Kenapa:** Konsekuensi langsung dari Keputusan #1 (dua tier dihitung sekaligus) — perlu SATU sinyal ringkas untuk panel status (mis. pewarnaan dashboard), sementara kedua angka mentah (PSI, p-value) tetap ditampilkan berdampingan di tabel untuk analisis lebih dalam (bukan disembunyikan di balik verdict gabungan saja). Pola "terburuk yang menang" sama dengan `aggregate_verdict` M2.4.

**Tidak ada alternatif dipertimbangkan** — forced oleh kebutuhan satu sinyal ringkas dari dua metrik yang sudah diputuskan Keputusan #1.

### 10. Panel drift ditambah ke dashboard Grafana yang SUDAH ADA (bukan dashboard baru)

**Keputusan:** 4 panel baru (2 stat "Jumlah Fitur STOP/FLAG", 1 tabel PSI+p-value+verdict, 1 row header) ditambahkan ke `churn-monitoring-m35` (dashboard M3.5), bukan dashboard terpisah.

**Kenapa:** Sesuai forward-compat M3.5 yang sudah dicatat sadar sejak awal ("M3.6 tinggal tambah panel baru di Grafana yang sama").

**Tidak ada alternatif dipertimbangkan** — sudah diputuskan sejak M3.5, bukan keputusan baru M3.6.

### 11. Uji coba terkontrol (KK1) pakai pola "ubah-verifikasi-kembalikan", BUKAN kolom `is_simulated` permanen

**Keputusan:** `scripts/compute_drift.py --mode current --override-current <json>` menerima nilai current-window buatan (BUKAN menulis ke `telco_customers_synthetic`), menulis hasil drift EKSTREM ke `drift.drift_check_results`, diverifikasi, lalu dijalankan ULANG TANPA override untuk restore nilai asli.

**Kenapa:** Dicek eksplisit — proyek ini TIDAK PERNAH memakai kolom `is_simulated` permanen di manapun (`infra/sql/*.sql`). Pola "ubah-verifikasi-kembalikan" konsisten M3.4 (negative-proof: nonaktifkan fix, buktikan gagal persis seperti diprediksi, aktifkan lagi).

**Opsi yang Dipertimbangkan tapi Ditolak:** Kolom `is_simulated BOOLEAN` di `drift.drift_check_results`, baris uji coba ditandai lalu difilter di query exporter — DITOLAK: menambah kompleksitas schema+query permanen (WHERE `is_simulated=false` di setiap query) untuk kebutuhan verifikasi satu kali yang sudah cukup diselesaikan lewat pola revert manual yang sudah terbukti dipakai proyek ini (M3.4).

## Kendala Teknis Ditemukan+Dipecahkan: Akses `PreprocessingPipeline` Fitted dari Model Teregistrasi

**Ditemukan saat:** Checkpoint 2, sebelum menulis `scripts/compute_drift.py`.

**Masalah:** Tidak ada API publik untuk mendapatkan fitur TRANSFORMED (29 kolom) dari model teregistrasi — `predict_active()`/`ChurnPyfuncModel.predict()` cuma mengembalikan HASIL AKHIR (churn_probability dst), bukan nilai di tengah pipeline. Bundle `{"pipeline","model","threshold"}` (M1.5) tidak bisa di-unpickle SEBAGIAN — pickle mendeserialisasi seluruh object graph sekaligus (butuh lightgbm/xgboost importable meski cuma mau pakai `pipeline`).

**Solusi:** `registry.load_active_pipeline()` — reuse 100% `load_active_model()` (SATU jalur loading, tidak reimplementasi), expose `_model_impl.python_model._pipeline` (atribut internal `ChurnPyfuncModel` yang sudah dimuat). Diverifikasi nyata: `.transform(df)` menghasilkan 29 kolom identik dengan `bundle["pipeline"].transform(df)` langsung (`np.testing.assert_allclose`, `tests/inference/test_registry.py`).

**Titik rapuh dicatat eksplisit:** bergantung struktur internal MLflow (`PyFuncModel._model_impl.python_model`, bukan API publik terdokumentasi) — perlu dicek ulang kalau `mlflow-skinny` di-upgrade dari `3.15.1` (versi dipin proyek ini).

**Opsi yang Dipertimbangkan tapi Ditolak:**
- Load `preprocessor.joblib` langsung dari `artifacs/proprocessor/` (lokal) — DITOLAK: direktori `artifacs/` gitignored, tidak ada di GitHub Actions (dibutuhkan untuk `compute_drift.py --mode current` yang jalan di CI), tidak portable.
- Extend `ChurnPyfuncModel.predict()` untuk optional mengembalikan fitur transformed juga — DITOLAK: mengubah kontrak API produksi inti (M1.5/M3.2, dipakai real-time API+batch DAG) demi kebutuhan monitoring, risiko regresi tidak sepadan dibanding accessor baru yang aditif murni.
