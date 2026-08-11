# CHANGELOG — Kontrak Skema Data Mentah

Jalur komunikasi resmi perubahan skema sumber PostgreSQL/Supabase (Milestone 1.6, `milestones/1.6-kontrak-skema-sumber-data/decisions.md` Keputusan #3). Setiap perubahan pada `raw-schema-contract.md`, atau perubahan sungguhan pada skema tabel Supabase (`telco_customers_source`, `telco_customers_synthetic`, `synthetic_generation_runs`), WAJIB dicatat di sini sebelum/saat commit yang mengubahnya.

**Aturan wajib bagi siapa pun (termasuk sesi kerja masa depan) yang memulai pekerjaan bergantung pada kontrak ini** (Milestone 2.x/3.x, atau kunjungan ulang ke Milestone 1.1-1.3): **baca file ini dari atas ke bawah SEBELUM mulai** — entry paling atas adalah perubahan terbaru. Kalau ada entry BREAKING sejak terakhir kali Anda membaca kontrak ini, kode yang bergantung padanya WAJIB ditinjau ulang sebelum dilanjutkan.

## Proses Perubahan (meniru disiplin tim, meski dikerjakan solo)

1. Perubahan skema (dokumen kontrak ATAU skema database sungguhan) dilakukan lewat git PR yang menyentuh file ini + `raw-schema-contract.md` — riwayat PR jadi jejak "review" formal, bahkan untuk proyek solo (approve sendiri tetap sah, yang penting ada catatan tertulis sebelum merge, bukan commit langsung tanpa jejak).
2. Klasifikasikan perubahan sebagai **BREAKING** atau **NON-BREAKING** (lihat aturan di bawah) — WAJIB dicantumkan di tiap entry, tidak boleh kosong.
3. Sebutkan milestone/modul yang terdampak (mis. "M1.2 transform, M1.3 schema, M1.5 inference" kalau perubahan menyentuh kolom yang dipakai modul-modul itu).
4. Tambah entry BARU di bagian atas (paling baru di atas) — jangan menimpa/menghapus entry lama.

### Klasifikasi Breaking vs Non-Breaking

| Jenis perubahan | Klasifikasi | Alasan |
|---|---|---|
| Kolom dihapus | **BREAKING** | Modul hilir yang membaca kolom itu langsung gagal/salah |
| Kolom di-rename | **BREAKING** | Sama seperti dihapus dari sudut pandang pemanggil lama |
| Tipe data kolom berubah (mis. `text`→`integer`) | **BREAKING** | Berisiko error parsing/validasi di `schema/raw_schema.py` atau `schema/request_schema.py` |
| Constraint diperketat (mis. rentang `tenure` yang tadinya 1-72 jadi 1-60) | **BREAKING** | Data yang tadinya valid bisa jadi ditolak `RawDataSchema`/`request_schema` yang belum diupdate |
| Kolom baru ditambahkan, NULLABLE atau punya default | **NON-BREAKING** | Kode existing yang tidak tahu kolom baru tetap jalan tanpa berubah |
| Constraint dilonggarkan (mis. rentang diperluas) | **NON-BREAKING** | Data yang tadinya valid tetap valid; data baru yang sebelumnya ditolak sekarang diterima — tidak merusak jalur lama |
| Perubahan dokumentasi murni (typo, klarifikasi semantik tanpa mengubah skema sungguhan) | **NON-BREAKING** | Tidak menyentuh skema database |

---

## Entries

### v1 — Kontrak awal (2026-08-12)

**Klasifikasi:** Baseline (bukan breaking/non-breaking — ini titik awal kontrak, tidak ada versi sebelumnya untuk dibandingkan).

**Milestone terdampak:** M1.1 (audit, dirujuk), M1.2 (`transform`, konvensi snake_case tidak berubah), M1.3 (`schema`, `raw_schema.py`/`request_schema.py` sudah konsisten kontrak ini), M1.5 (`inference`, `predict()` sudah memvalidasi lewat `raw_schema`) — seluruhnya SUDAH konsisten kontrak ini per verifikasi Milestone 1.6, tidak perlu perubahan kode.

**Isi:**
- Kontrak dua-fase: `telco_customers_source` (sekarang) → `telco_customers_synthetic` (setelah generator aktif) — menutup KT-1 (`docs/keputusan-tertunda.md`).
- Skema kolom lengkap 3 tabel (`telco_customers_source`, `telco_customers_synthetic`, `synthetic_generation_runs`), diverifikasi langsung terhadap struktur Supabase sungguhan (`milestones/1.6-kontrak-skema-sumber-data/logs.md` Checkpoint 1) — 0 drift dari `notebook-audit.md` Bagian H.
- Semantik ambigu didokumentasikan penuh: unit (USD, bulan), timezone (`timestamptz` = UTC), null handling.
- Semantik update generator: append-only snapshot (SCD Type 2) — menutup KT-2.
- Gap ditemukan: kolom `customer_key` belum ada di `telco_customers_synthetic` — dicatat sebagai KT-4 (`docs/keputusan-tertunda.md`), BUKAN diimplementasikan di versi kontrak ini.

Lihat `docs/04-schema-contract/raw-schema-contract.md` untuk isi lengkap.
