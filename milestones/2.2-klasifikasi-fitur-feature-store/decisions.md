# Decisions — Milestone 2.2: Klasifikasi Fitur ke Desain Feature Store

## Klarifikasi Sebelum Plan Disusun

Milestone ini awalnya dideskripsikan `mlops-02-pipeline-orchestration.md` sebagai "terjemahkan fitur historis M1.1 jadi skema tabel feature store PostgreSQL". Sebelum plan/breakdown ditulis, temuan berikut disampaikan ke user (dengan penjelasan bertahap — apa itu "INSTANT" vs "historis", lalu apa sebenarnya yang ingin dibangun M2.2 — karena user secara eksplisit meminta penjelasan lebih detail sebelum memutuskan):

- `docs/03-notebook-audit/notebook-audit.md` Bagian C: **seluruh 29 fitur final model berklasifikasi INSTANT** — tidak satu pun butuh agregasi lintas-baris/waktu.
- Bagian G.3 (ambiguitas): status "DIPERKUAT, BELUM 100% TERTUTUP", eksplisit menyatakan dampaknya "tetap seperti dijelaskan semula" ke Milestone 2.2 — artinya audit M1.1 sendiri MENYERAHKAN keputusan ini ke M2.2, bukan sesuatu yang seharusnya sudah diputuskan lebih awal.
- Bagian H.1: seluruh project Supabase cuma berisi 3 tabel (`telco_customers_source`, `telco_customers_synthetic`, `synthetic_generation_runs`) — tidak ada satu pun tabel log/transaksi/riwayat kejadian yang bisa jadi sumber agregasi historis.

→ User memilih: **tutup sebagai temuan terdokumentasi, tidak membangun tabel feature store apa pun sekarang** (dari 2 opsi yang diajukan: tutup vs bangun kosong forward-looking).

## Keputusan Teknis

### 1. Tidak membangun tabel feature store PostgreSQL untuk model versi sekarang — menutup G.3

**Keputusan:** Milestone 2.2 TIDAK menghasilkan skema tabel feature store apa pun. Baik batch DAG (M2.5) maupun real-time API (M3.x) membaca fitur langsung dari satu baris data pelanggan (`telco_customers_source` sekarang, `telco_customers_synthetic` setelah generator aktif, sesuai kontrak dua-fase M1.6) — tanpa lapisan precompute/cache tambahan. Ini BUKAN keputusan "belum sempat dikerjakan", melainkan kesimpulan bahwa untuk model versi sekarang, feature store tidak punya fungsi apa pun untuk diisi.

**Kenapa:** Cross-check independen (dilakukan sebelum keputusan ini ditulis, lihat `logs.md`) mencocokkan 18 kolom mentah yang benar-benar dipakai sebagai input 29 fitur final (dari tabel klasifikasi C.1-C.5 notebook-audit.md) terhadap `docs/04-schema-contract/raw-schema-contract.md` Bagian 2 — sumber PALING BARU (hasil verifikasi struktur tabel real Supabase Milestone 1.6, hari yang sama). Seluruh 18 kolom ada langsung sebagai kolom current-state di KEDUA tabel (`telco_customers_source` dan `telco_customers_synthetic`), tidak ada yang butuh riwayat/agregasi. 0 gap ditemukan — memperkuat (bukan sekadar mengulang) kesimpulan G.3/H.1 audit M1.1 dengan sumber yang lebih baru.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Bangun feature store kosong/minimal sekarang, forward-looking** (buat jaga-jaga kalau nanti dibutuhkan) — DITOLAK user setelah trade-off dijelaskan: kerja tambahan (desain skema, mekanisme refresh, dst) untuk kebutuhan yang belum tentu terjadi, bertentangan dengan prinsip "jangan bangun untuk kebutuhan hipotetis" (CLAUDE.md). Infrastruktur kosong tanpa fungsi juga tidak ada yang bisa diverifikasi/diuji secara bermakna sekarang.

### 2. Trigger peninjauan ulang keputusan ini

**Keputusan:** Keputusan #1 ditinjau ulang (bukan otomatis dibangun ulang) jika salah satu terjadi:
- Model versi baru hasil retraining (di luar cakupan sistem ini, tapi kontrak registrasi versi baru sudah siap menampungnya — `docs/05-model-registry-contract/model-registry-contract.md`, Milestone 2.1) memakai fitur historis/agregat yang butuh precompute.
- Kebutuhan dashboard monitoring (Bagian 8.3 dokumen arsitektur, milik Orang #3/M3.x) muncul untuk agregasi periodik yang terpisah dari fitur model itu sendiri — ini beda konteks dari feature store fitur model, tapi sama-sama berarti tabel agregat PostgreSQL, layak dicatat sebagai kemungkinan pemicu terkait.

**Kenapa:** Supaya keputusan "tidak membangun sekarang" tidak jadi keputusan permanen yang terlupakan — jelas kondisi apa yang membuatnya perlu ditinjau ulang, konsisten pola KT-4 (`docs/keputusan-tertunda.md`) yang juga mencatat trigger eksplisit untuk gap yang sengaja tidak diselesaikan sekarang.

**Opsi yang Dipertimbangkan tapi Ditolak:** Tidak ada alternatif dipertimbangkan — bagian ini murni pencatatan kondisi pemicu, bukan pilihan desain.
