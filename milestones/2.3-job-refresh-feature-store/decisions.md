# Decisions — Milestone 2.3: Job Refresh Feature Store

## Klarifikasi Sebelum Plan Disusun

Deskripsi asli `mlops-02-pipeline-orchestration.md` untuk Milestone 2.3: "bangun job terjadwal yang menghitung ulang nilai fitur historis dari data mentah PostgreSQL dan memperbarui feature store **sesuai skema Milestone 2.2**". Ketergantungan ke M2.2 eksplisit tertulis di deskripsi milestone itu sendiri, bukan interpretasi baru.

User membuka sesi ini dengan eksplisit menyebut "milestone ini sebenarnya punya ketergantungan ke milestone 2.2" sebelum breakdown diminta — mengonfirmasi arah yang sama dengan temuan `milestones/2.2-klasifikasi-fitur-feature-store/decisions.md`: karena M2.2 menyimpulkan **tidak ada skema feature store** untuk model versi sekarang (seluruh 29 fitur INSTANT, 0 gap), M2.3 tidak punya apa pun untuk di-refresh. Ditawarkan 2 opsi (tutup sebagai N/A vs bangun minimal forward-looking) — user memilih **tutup sebagai N/A**, sama seperti M2.2.

## Keputusan Teknis

### 1. Milestone 2.3 ditutup sebagai N/A untuk model versi sekarang

**Keputusan:** Tidak ada job refresh feature store yang dibangun. Tidak ada mekanisme swap-table/refresh-aman-dibaca-bersamaan yang diimplementasikan sekarang, karena tidak ada tabel feature store (M2.2) yang perlu mekanisme itu.

**Kenapa:** Konsekuensi logis langsung dari `milestones/2.2-klasifikasi-fitur-feature-store/decisions.md` Keputusan #1 — TIDAK diulang cross-check-nya di sini (sudah tuntas dan terverifikasi di M2.2, hari sebelumnya, terhadap sumber skema paling baru). Merujuk bukti yang sudah ada lebih tepat daripada menduplikasi pekerjaan verifikasi.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Bangun job refresh minimal/kosong forward-looking** — DITOLAK user, alasan sama persis dengan M2.2 Keputusan #1 (kerja tambahan untuk kebutuhan yang belum tentu terjadi, infrastruktur kosong tanpa fungsi tidak bisa diverifikasi bermakna).

### 2. Dua trigger peninjauan ulang, dicatat terpisah karena beda konsep

**Keputusan:**
1. **Trigger #1 (sama dengan M2.2):** Model versi baru hasil retraining memakai fitur historis/agregat yang butuh precompute — memicu peninjauan ulang M2.2 DAN M2.3 sekaligus (keduanya saling terikat).
2. **Trigger #2 (baru, khusus M2.3):** Data generator diaktifkan (Fase 2 kontrak dua-fase — KT-1, `docs/keputusan-tertunda.md`). Begitu `telco_customers_synthetic` mulai diisi dengan pola append-only snapshot (KT-2 — SCD Type 2, banyak baris per pelanggan dari waktu ke waktu), membaca "current state" pelanggan butuh query `SELECT DISTINCT ON (customer_key) ... ORDER BY generated_at DESC` per pelanggan — berpotensi mahal kalau dilakukan on-the-fly di real-time API untuk setiap request. Ini bisa memicu kebutuhan **materialisasi "baris terbaru per pelanggan"** yang di-refresh berkala — MIRIP semangat M2.3 (refresh aman dibaca bersamaan) tapi BEDA TOTAL isinya (bukan agregasi fitur historis, cuma current-state row terbaru). **Bergantung KT-4** (kolom `customer_key` belum ada di `telco_customers_synthetic`) yang harus selesai lebih dulu sebelum materialisasi ini secara teknis mungkin dibangun.

**Kenapa:** Trigger #2 sengaja dipisah dari Trigger #1 supaya tidak tercampur konsepnya — kalau nanti generator diaktifkan tapi model TIDAK pernah pakai fitur historis, yang perlu dibangun bukan "feature store" ala M2.2 melainkan mekanisme materialisasi current-state yang jauh lebih sederhana (tidak ada logika agregasi Orang #1 yang perlu dipanggil ulang, cuma "ambil baris terbaru"). Menyamakan keduanya berisiko salah scope saat trigger benar-benar terjadi.

**Opsi yang Dipertimbangkan tapi Ditolak:** Tidak ada alternatif dipertimbangkan — bagian ini murni pencatatan kondisi pemicu, bukan pilihan desain.
