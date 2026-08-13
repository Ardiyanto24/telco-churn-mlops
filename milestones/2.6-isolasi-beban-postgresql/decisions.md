# Decisions — Milestone 2.6: Isolasi Beban terhadap PostgreSQL

## Klarifikasi Sebelum Plan Disusun

Dua keputusan dikonfirmasi user sebelum plan ditulis:

1. **Proxy simulasi "baca bergaya real-time API"**: real-time API (M3.x) belum dibangun dan tidak ada feature store (M2.2, DITUTUP — seluruh 29 fitur INSTANT). User memilih simulasi **dua consumer**: Consumer A (resolusi alias model, reuse `registry.resolve_alias_version()` — bukan raw SQL baru) dan Consumer B (query agregat gaya dashboard monitoring ke `predictions.batch_predictions`) — bukan opsi yang lebih sempit (hanya Consumer A) atau opsi generik (point-lookup ke `telco_customers_source`, yang menurut arsitektur final tidak akan pernah benar-benar dipakai real-time API).
2. **Verdict KK1 ("latensi wajar atau tidak") TIDAK diimplementasikan sebagai gerbang pass/fail** — user eksplisit: *"beri catatan untuk KK1 ini belum bisa diimplementasikan karena belum ada real time API sungguhan. catat di keputusan tertunda."* Milestone tetap membangun harness dan mengambil angka nyata, tapi verdict formal ditunda (lihat KT-5).

## Temuan Konflik Dokumen (Dicatat, Tidak Diubah)

`docs/02-implementation-plan/mlops-03-deployment-observability.md` baris 63 mendeskripsikan real-time API mengambil fitur dari "payload + feature store" — ini stale terhadap keputusan M2.2 (DITUTUP) yang memutuskan tidak ada feature store sama sekali. Bukan wewenang milestone ini mengubah dokumen M3.x; dicatat sebagai catatan serah terima di report.md.

## Keputusan Teknis

### 1. Proxy dua consumer, bukan feature store atau `telco_customers_source`

**Keputusan:** Consumer A memanggil `registry.resolve_alias_version()` langsung (reuse fungsi nyata M2.5/M2.1 — satu sumber kebenaran, bukan raw SQL baru); Consumer B menjalankan `SELECT model_version, count(*), avg(churn_probability) FROM predictions.batch_predictions GROUP BY model_version` berulang.

**Kenapa:** Dikonfirmasi user (lihat Klarifikasi #1). Consumer A adalah satu-satunya jejak baca Postgres yang **pasti** dipakai real-time API nanti menurut keputusan arsitektur final saat ini (tidak ada feature store). Consumer B mewakili konsumen M3.x lain yang relevan (dashboard monitoring, Bagian 8.3 dokumen arsitektur) dan secara spesifik menguji tabel yang ditulis `write_predictions` M2.5 dalam satu transaksi panjang — titik kontensi paling mungkin.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Hanya Consumer A (resolusi alias saja)** — DITOLAK user: lingkup lebih sempit, tidak menyentuh risiko kontensi pada `predictions.batch_predictions` yang ditulis `write_predictions` M2.5 dalam satu transaksi panjang — risiko ini kemudian TERBUKTI nyata (lihat Keputusan #4).
- **Point-lookup generik ke `telco_customers_source`** — DITOLAK user: menguji skenario yang menurut keputusan final saat ini (M2.2, tidak ada feature store) tidak akan pernah benar-benar terjadi di real-time API.

### 2. Reuse kredensial role yang sudah ada, tidak membuat role Postgres baru

**Keputusan:** Consumer A pakai `MLFLOW_TRACKING_URI`/role `mlflow_registry` (M2.1) lewat `resolve_alias_version()`; Consumer B pakai koneksi `batch_writer` (M2.5, sudah punya SELECT ke `predictions.batch_predictions`).

**Kenapa:** Ini simulasi/pengukuran sementara untuk milestone ini, bukan pola akses production baru — desain role akses real-time API sungguhan adalah wewenang M3.x, membuat role baru sekarang hanya untuk alat ukur sekali pakai adalah overhead infrastruktur yang tidak perlu.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Buat role Postgres baru khusus simulasi** (mis. `realtime_api_proxy_readonly`) — tidak dipertimbangkan serius: menambah state permanen (role, grant) untuk kebutuhan yang secara desain sementara/sekali-pakai, drift risk kalau lupa dibersihkan.

### 3. Harness sekali-pakai (`orchestration/load_test/`), bukan modul package atau pytest permanen

**Keputusan:** `concurrent_readers.py` ditulis sebagai kode ops di `orchestration/load_test/`, bukan `churn_prediction` package, dan diverifikasi lewat smoke test manual (dicatat di logs.md) — bukan pytest yang jadi bagian regresi CI permanen.

**Kenapa:** Bukan logika transformasi/inference (tidak melanggar "satu sumber kebenaran" karena justru REUSE `resolve_alias_version()`, bukan reimplementasi). Ini alat ukur/benchmark untuk mengambil bukti milestone ini — properti yang diuji (latensi relatif terhadap beban) bukan properti korektnes fungsional yang perlu terus diregresi-test tiap commit, beda karakter dari `tests/orchestration/test_batch_scoring.py` (M2.5) yang menguji properti korektnes (parity, lineage, rollback) yang WAJIB tetap benar selamanya.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Tulis sebagai pytest permanen di `tests/`** — tidak dipertimbangkan serius: hasil ukur latensi sangat bergantung kondisi jaringan/beban saat run (terbukti dari temuan run-to-run variance, lihat logs.md), pytest yang gagal karena noise jaringan (bukan regresi kode) akan jadi flaky test yang justru mengurangi kepercayaan pada test suite.

### 4. Temuan nyata: Consumer B (dashboard aggregate) terdegradasi signifikan selama fase `write`, Consumer A tidak

**Keputusan (temuan, bukan pilihan):** Pengukuran skala penuh (594.194 baris, run bersih setelah baseline gate direset — lihat Keputusan #6) menunjukkan:
- Consumer A: delta dalam rentang noise (p50 -0.2%, p95 -9.7% dibanding baseline terisolasi) — TIDAK ada degradasi berarti, konsisten di semua fase flow.
- Consumer B: delta signifikan (p50 +12.0%, p95 **+210.5%** dibanding baseline) — terkonsentrasi jelas di fase `write` (p95 fase write: 766.5ms vs baseline keseluruhan 195.6ms), juga terlihat lebih ringan di fase `score` (p95 424.9ms).

**Kenapa:** `write_predictions` (M2.5) menulis 594.194 baris dalam SATU transaksi Postgres panjang (~4 menit, fase terlama flow) ke tabel `predictions.batch_predictions` — tabel yang SAMA PERSIS dibaca Consumer B. Consumer A membaca schema `mlflow` yang nyaris tidak disentuh flow batch (hanya sekali di awal `score_batch`). Korelasi fase yang jelas (bukan degradasi merata di semua fase) memperkuat bahwa penyebabnya adalah kontensi tabel spesifik, bukan beban Postgres generik.

**Opsi yang Dipertimbangkan tapi Ditolak:** Tidak ada alternatif dipertimbangkan — ini temuan pengukuran, bukan pilihan desain.

### 5. Tidak menerapkan mitigasi tambahan sekarang — didukung bukti, bukan default

**Keputusan:** TIDAK ada index baru, TIDAK mengubah `write_predictions` jadi commit bertahap, TIDAK menambah connection pooling baru (Supavisor sudah ada sejak M2.1) diterapkan pada milestone ini. Kandidat mitigasi paling menyasar akar masalah (commit bertahap, bukan satu transaksi) dicatat sebagai keputusan tertunda baru (KT-6, `docs/keputusan-tertunda.md`).

**Kenapa:** Index pada `model_version` (satu-satunya kolom `GROUP BY` Consumer B) TIDAK relevan dengan akar masalah yang ditemukan — masalahnya kontensi lock/IO selama transaksi tulis panjang, bukan query plan yang buruk (lagipula saat ini cuma ada 1 nilai `model_version` distinct, index tidak akan menunjukkan manfaat terukur). Mengubah `write_predictions` ke commit bertahap adalah trade-off nontrivial terhadap jaminan all-or-nothing yang jadi keputusan sadar M2.5 (demi konsistensi data, KK2 M2.5) — mengubahnya sekarang berarti menukar jaminan korektnes yang sudah terbukti demi kontensi yang baru terbukti berdampak di kondisi lab/simulasi (belum ada trafik nyata generator/real-time API yang benar-benar dirugikan). Konsisten teks KK2 sumber milestone ini: "dipilih berdasarkan hasil analisis, bukan diterapkan seluruhnya secara default" — analisis mengarah ke "belum perlu sekarang", bukan ke mitigasi spesifik yang murah-risiko.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Tambah index pada `model_version`** — DITOLAK: tidak menyasar akar masalah (kontensi tulis, bukan query plan); tidak ada manfaat terukur pada skala data sekarang (1 nilai distinct).
- **Ubah `write_predictions` ke commit bertahap sekarang** — DITOLAK untuk saat ini (dicatat KT-6, bukan ditutup permanen): trade-off nontrivial terhadap keputusan M2.5 yang sudah final, belum ada trafik nyata yang dirugikan untuk membenarkan perubahan sekarang.
- **Read replica** — tidak dieksplorasi lebih jauh: kelayakan tier Supabase belum diverifikasi, dan tidak proporsional untuk mengatasi kontensi yang baru terbukti di kondisi simulasi/lab, bukan produksi nyata.

### 6. Verdict KK1 ditunda ke KT-5 — bukan disimpulkan pass/fail

**Keputusan:** Data mentah (baseline vs bersamaan, delta, korelasi fase) didokumentasikan lengkap sebagai bukti, TAPI kesimpulan "apakah ini wajar untuk real-time API" TIDAK dinyatakan sebagai pass/fail formal milestone ini.

**Kenapa:** Dikonfirmasi user eksplisit (lihat Klarifikasi #2) — menetapkan ambang batas tanpa SLA nyata (real-time API belum dibangun) berarti menebak, dilarang eksplisit oleh `CLAUDE.md`/`AGENT.md` Bagian "Batas Implementasi Saat Ini". Lihat KT-5 (`docs/keputusan-tertunda.md`) untuk detail lengkap dan pemicu peninjauan.

**Opsi yang Dipertimbangkan tapi Ditolak:** Tiga metodologi ambang batas diajukan ke user (deviasi relatif provisional pola M2.4, deskriptif tanpa gerbang, ambang absolut provisional) — SEMUANYA ditolak user demi opsi keempat yang lebih fundamental: menunda verdict sepenuhnya sebagai keputusan tertunda, bukan memilih salah satu metodologi threshold.

### 7. Dua bug operasional ditemukan+diperbaiki selama Checkpoint 3 (bukan hasil pengukuran, tapi mempengaruhi caranya diperoleh)

**Keputusan:** (a) Script pengukuran skala penuh awalnya deadlock (thread consumer tanpa `duration_s` berputar tanpa henti kalau `batch_scoring_flow()` raise exception sebelum `stop_event.set()` tercapai) — diperbaiki dengan `try/finally` menjamin `stop_event.set()` selalu tereksekusi. (b) Gerbang kualitas data STOP pada percobaan pertama run skala penuh — baseline `quality.gate_run_history` untuk `telco_customers_source` tercemar LAGI oleh run kecil (2 entri sisa 1.000-baris dari M2.5 + 1 entri 2.000-baris dari validasi Task 7 milestone ini sendiri) — root cause IDENTIK dengan temuan M2.5, diperbaiki dengan reset yang sama (`DELETE FROM quality.gate_run_history WHERE source_table='telco_customers_source'`).

**Kenapa:** (a) murni bug logika di kode pengukuran sekali-pakai milestone ini (bukan di package/DAG produksi) — tidak masuk `docs/keterbatasan-diterima.md` karena diperbaiki, bukan diterima. (b) mengonfirmasi bahwa perbaikan M2.5 terhadap masalah ini adalah **reset data satu kali**, BUKAN perubahan desain permanen — masalahnya bisa (dan terbukti) berulang setiap kali ada run skala kecil (termasuk validasi milestone lain) sebelum run skala besar berikutnya. Ini pola operasional berulang yang layak dicatat sebagai peringatan eksplisit untuk milestone mendatang (M2.7 CI/CD, M2.8), BUKAN keterbatasan yang diterima (ada fix konkret, cuma perlu diterapkan ulang tiap kali terjadi) — dicatat di report.md sebagai follow-up peringatan, bukan `docs/keterbatasan-diterima.md`.

**Opsi yang Dipertimbangkan tapi Ditolak:** Tidak ada alternatif dipertimbangkan untuk (a) — bug logika langsung, satu fix jelas. Untuk (b): **desain ulang baseline gerbang kualitas data supaya tidak sensitif skala campuran (mis. baseline terpisah per rentang skala)** — TIDAK dipertimbangkan serius sebagai bagian milestone ini: perubahan desain modul `quality` (M2.4) di luar cakupan M2.6, dan reset manual sudah terbukti cukup sebagai mitigasi operasional untuk sekarang.

### 8. Bug ketiga ditemukan+diperbaiki: `tests/orchestration/test_batch_scoring.py` (M2.5) tidak benar-benar memuat `.env` ke `os.environ`

**Keputusan:** `_load_env_var()` di test file M2.5 itu membaca `.env` untuk menentukan skip-condition dan variabel lokal modul (`SUPABASE_DB_URL`, dst.), TAPI TIDAK PERNAH menulis balik ke `os.environ` — kode yang benar-benar dites (`orchestration/flows/batch_scoring.py`, `src/churn_prediction/quality/baseline.py`, baca `os.environ.get(...)` langsung) cuma kebetulan bekerja di shell yang SUDAH punya var ini di level OS di luar `.env`. Diperbaiki: `_load_dotenv_into_environ()` baru, dipanggil sekali di level modul, memuat SELURUH `.env` ke `os.environ` lewat `setdefault` (pola sama `orchestration/deploy_batch_scoring.py::_load_env()`) — bukan cuma 3 var yang test file ini rujuk langsung.

**Kenapa:** Ditemukan saat verifikasi "tidak ada regresi" M2.6 (`pytest tests/ -q` penuh) di shell yang TIDAK punya var-var ini di level OS — 2 dari 4 test M2.5 di file ini gagal (`RuntimeError: BATCH_READER_DB_URL tidak diset`, lalu setelah fix pertama parsial: `QUALITY_GATE_DB_URL tidak diset`). Ini bug MURNI di file test M2.5, bukan diperkenalkan milestone ini — tapi diperbaiki sekarang karena ditemukan saat verifikasi milestone ini dan langsung memblokir kepercayaan pada full suite. Fix pertama (hanya menambah `setdefault` untuk 3 var yang sudah dirujuk) TERBUKTI kurang — flow butuh var lain (`QUALITY_GATE_DB_URL`, `MLFLOW_TRACKING_URI`, kredensial S3) yang test file ini sendiri tidak pernah merujuknya secara eksplisit; solusi tuntas adalah muat SELURUH `.env`, bukan var per var.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Tambah `os.environ.setdefault()` var demi var seiring ditemukan** — DICOBA DULU, ditolak setelah terbukti tidak tuntas (`QUALITY_GATE_DB_URL` masih gagal setelah fix pertama) — pendekatan reaktif yang hanya menutup gejala satu per satu, bukan akar masalah (test file harus menyediakan environment LENGKAP untuk kode yang dites, bukan subset yang kebetulan ia rujuk sendiri).
- **Biarkan, catat sebagai keterbatasan diterima** — DITOLAK: ada fix konkret sederhana yang menutup akar masalah (reuse pola `_load_env()` yang sudah ada), bukan kasus yang layak `docs/keterbatasan-diterima.md`.
