# Decisions — Milestone 2.4: Gerbang Kualitas Data Harian

## Klarifikasi Sebelum Plan Disusun

Dokumen arsitektur (Bagian 10) eksplisit membiarkan ambang batas kewajaran data harian terbuka untuk Orang #2. Dua pertanyaan diajukan ke user sebelum plan ditulis:

1. **Metodologi ambang batas** — pilihan antara persentase deviasi sederhana vs statistik formal (z-score/chi-square). User memilih **deviasi sederhana**, dengan catatan eksplisit: opsi upgrade ke statistik formal tetap dibuka untuk masa depan, bukan ditolak permanen.
2. **Perilaku saat gagal** — pilihan antara bertingkat (stop untuk parah, flag untuk ringan) vs selalu stop. User memilih **bertingkat**, sesuai kata "menghentikan/menandai" (dua kata, bukan satu) di deskripsi asli milestone.

## Keputusan Teknis

### 1. Metodologi: persentase deviasi sederhana dari baseline rolling

**Keputusan:** Seluruh check (`src/churn_prediction/quality/checks.py`) memakai persentase deviasi dari rata-rata baseline (volume, distribusi kategori) atau ambang absolut berbasis bukti (NULL proportion) — bukan z-score/uji statistik formal. Ambang konkret:

| Check | Flag | Stop |
|---|---|---|
| Volume baris | ≥20% deviasi dari rata-rata baseline | ≥50% deviasi |
| Proporsi NULL (kolom fitur) | ≥1% | ≥10% |
| Pergeseran distribusi kategori | ≥10 poin persentase | ≥30 poin persentase |

**Kenapa:** Dikonfirmasi user. Mudah dijelaskan/di-tuning, cocok skala portofolio, tidak butuh dependency statistik baru (`pandas` saja cukup). Ambang NULL absolut (bukan relatif ke baseline) dipilih karena bukti kuat sudah ada: 18 kolom fitur model 100% NULL-free di 594.194 baris nyata (`notebook-audit.md` Bagian H.2) — deviasi absolut dari "seharusnya 0%" lebih bermakna daripada deviasi relatif dari baseline yang sama-sama nol.

**Opsi yang Dipertimbangkan tapi Ditolak (untuk sekarang, bukan permanen):**
- **Berbasis statistik formal (z-score untuk numerik, chi-square untuk kategorikal)** — TIDAK dipilih sekarang: ambang seperti `z>3` kurang intuitif dijelaskan, dan butuh riwayat run lebih banyak supaya estimasi std/distribusi stabil — riwayat yang tersedia sekarang sangat terbatas (lihat Keputusan #3, keterbatasan data). **Dicatat eksplisit sebagai jalur upgrade masa depan** begitu riwayat run cukup banyak dan/atau data harian asli sudah mengalir (bukan penolakan permanen — user secara eksplisit minta opsi ini tetap terbuka).

### 2. Perilaku gagal: bertingkat (stop untuk parah, flag untuk ringan)

**Keputusan:** `aggregate_verdict()` (`checks.py`) mengembalikan verdict akhir = yang paling parah di antara seluruh check (`stop` > `flag` > `pass`). Task DAG (M2.5, belum dibangun) yang memanggil `run_gate()` bertanggung jawab menghentikan run kalau verdict `stop`, atau melanjutkan dengan catatan kalau `flag`.

**Kenapa:** Dikonfirmasi user, sesuai kata "menghentikan/menandai" di deskripsi asli milestone (`mlops-02-pipeline-orchestration.md`) — dua respons berbeda untuk tingkat pelanggaran berbeda, bukan satu perilaku tunggal.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Selalu stop DAG kalau ada pelanggaran apa pun** — DITOLAK user: berisiko false-positive sering menghentikan pipeline untuk deviasi kecil yang sebenarnya wajar, bertentangan dengan KK asli milestone ("kondisi data normal tidak memicu false alert").

### 3. Keterbatasan: verifikasi memakai uji coba terkontrol, bukan data harian asli

**Keputusan:** Seluruh verifikasi (Checkpoint 1-2) memakai kombinasi statistik real `telco_customers_source` (594.194 baris, `tenure` 1-72 rata-rata 36.6, `MonthlyCharges` 18.25-118.75 rata-rata 65.87, 0 NULL) sebagai baseline "wajar", DIKOMBINASIKAN dengan skenario sintetis (volume disuntik turun 90%, NULL disuntik naik 15%, distribusi kategori digeser 15 poin) untuk membuktikan deteksi anomali. Ini BUKAN kompromi darurat — KK asli milestone sendiri eksplisit minta "uji coba terkontrol: menyuntik data uji", bukan mensyaratkan data harian organik.

**Kenapa:** `telco_customers_source` (sumber aktif Fase 1) terverifikasi cuma **1 event loading** (`SELECT count(DISTINCT imported_at)` = 1) — bulk-load sekali, bukan data yang bervariasi hari-ke-hari. `telco_customers_synthetic` (Fase 2) masih 0 baris. Tidak ada cara memvalidasi ambang batas terhadap fluktuasi harian ASLI sekarang — dicatat eksplisit sebagai keterbatasan provisional (pola sama KT-3, `docs/keputusan-tertunda.md`), bukan diklaim tervalidasi penuh.

**Opsi yang Dipertimbangkan tapi Ditolak:** Tidak ada alternatif dipertimbangkan — ini pencatatan kondisi data nyata, bukan pilihan desain.

### 4. Tabel riwayat baseline baru (`quality.gate_run_history`) — beda dari feature store M2.2

**Keputusan:** Tabel baru di schema `quality` (bukan `public`, bukan `mlflow`), append-only (role `quality_gate` cuma SELECT+INSERT, tanpa UPDATE/DELETE), kolom `null_proportions`/`category_distributions`/`details` bertipe `jsonb` untuk fleksibilitas struktur per kolom yang dicek. Role least-privilege terpisah (`quality_gate`), tidak reuse `mlflow_registry` maupun `SUPABASE_DB_URL`.

**Kenapa:** Forced oleh kebutuhan "baseline rolling" (`checks.py` butuh riwayat run sebelumnya untuk dibandingkan — tidak ada cara menghindarinya kalau mau memenuhi KK asli milestone "dibanding baseline historis, rolling bukan angka statis"). Role terpisah forced oleh prinsip least-privilege CLAUDE.md, konsisten preseden M2.1 (`mlflow_registry`). **Ini BUKAN feature store** (M2.2 menyimpulkan feature store fitur model tidak dibutuhkan) — tabel ini menyimpan METRIK KUALITAS DATA (volume, NULL, distribusi), konsep yang sama sekali berbeda dari fitur model, dicatat eksplisit supaya tidak tercampur dengan kesimpulan M2.2.

**Opsi yang Dipertimbangkan tapi Ditolak:** Tidak ada alternatif dipertimbangkan untuk keberadaan tabelnya — forced by kebutuhan rolling baseline. Untuk role: reuse `mlflow_registry`/`SUPABASE_DB_URL` tidak dipertimbangkan serius karena melanggar prinsip least-privilege secara langsung (pola akses berbeda: metrik kualitas data vs registry model vs data mentah).

### 5. Kolom yang dicek: 18 kolom input fitur model (bukan seluruh 21 kolom mentah)

**Keputusan:** `numeric_columns`/`categorical_columns` yang direkomendasikan untuk dipakai pemanggil `run_gate()` adalah 18 kolom mentah yang benar-benar dipakai sebagai input 29 fitur final model — daftar sudah established dan diverifikasi `milestones/2.2-klasifikasi-fitur-feature-store/decisions.md` (bukan diulang di sini). `gate.py` sendiri TIDAK hardcode daftar ini — pemanggil menyediakan eksplisit, mengikuti pola normalisasi kolom M1.6 (modul bersama tidak boleh berasumsi konvensi nama PascalCase/snake_case).

**Kenapa:** Kolom yang tidak dipakai model (`gender`, `Churn`) tidak relevan untuk gerbang kualitas yang tujuannya melindungi scoring — memeriksa kolom yang tidak pernah dibaca scoring cuma menambah noise/false-positive tanpa manfaat.

**Opsi yang Dipertimbangkan tapi Ditolak:** Memeriksa seluruh 21 kolom mentah — tidak dipertimbangkan serius, tidak ada manfaat memeriksa kolom yang tidak memengaruhi output model.
