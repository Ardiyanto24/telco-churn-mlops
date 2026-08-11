# Logs — Milestone 1.6: Kontrak Skema dengan Sumber Data

## Checkpoint 0 — Keputusan + scaffold

**Mulai:** 2026-08-12.

Tiga pertanyaan diajukan lewat AskUserQuestion sebelum plan ditulis (KT-1: tabel mana jadi kontrak resmi; KT-2: semantik update generator; jalur komunikasi perubahan skema). Untuk KT-2 dan jalur komunikasi, user minta rekomendasi standar industri secara eksplisit alih-alih menjawab langsung — rekomendasi (append-only snapshot/SCD Type 2 untuk KT-2; data contract versioned dengan CHANGELOG untuk jalur komunikasi) dijelaskan detail ke user lewat dua putaran percakapan (user awalnya minta klarifikasi lebih lanjut untuk Q1/Q2 sebelum menjawab), lalu dikonfirmasi eksplisit lewat AskUserQuestion kedua. Detail lengkap 5 Keputusan Teknis di `decisions.md`.

Folder `docs/04-schema-contract/` dibuat (kosong, diisi Checkpoint 2-3).

**File disentuh:** `milestones/1.6-kontrak-skema-sumber-data/decisions.md` (baru), `docs/04-schema-contract/` (folder baru, kosong).

## Checkpoint 1 — Verifikasi ulang struktur tabel sungguhan (KK1)

Query read-only langsung ke Supabase (`information_schema.columns`, `information_schema.table_constraints`, `pg_constraint`) untuk `telco_customers_source`, `telco_customers_synthetic`, `synthetic_generation_runs` — dibandingkan satu-satu terhadap `notebook-audit.md` Bagian H (ditulis 2026-08-11).

**Hasil: TIDAK ADA DRIFT.** Seluruh temuan cocok persis:

- **`telco_customers_source`** — 21 kolom bisnis PascalCase + `id` (bigint, PK, NOT NULL) + `imported_at` (timestamptz, NOT NULL, default `now()`). Semua 21 kolom bisnis nullable di level skema (konsisten M1.1: nullable tapi 0 NULL aktual). Row count: **594.194** (sama persis).
- **`telco_customers_synthetic`** — `synthetic_id` (uuid, PK, NOT NULL), `generation_id` (uuid, NOT NULL, FK → `synthetic_generation_runs.generation_id`), `generated_at` (timestamptz, NOT NULL), + 20 kolom bisnis snake_case, SEMUA NOT NULL (lebih ketat dari source, konsisten M1.1). CHECK constraints cocok persis: `churn IN ('Yes','No')`, `monthly_charges > 0`, `senior_citizen IN (0,1)`, `tenure BETWEEN 1 AND 72`, `total_charges >= 0`. Row count: **0** (masih kosong, generator belum aktif). **Tidak ada kolom identitas pelanggan terpisah dari `synthetic_id`** — mengonfirmasi ulang temuan gap Keputusan #2 (`decisions.md`) lewat query independen, bukan cuma membaca ulang dokumen lama.
- **`synthetic_generation_runs`** — `generation_id` (uuid, PK), `requested_count` (CHECK 1-100000), `inserted_count` (default 0), `seed` (bigint, nullable), `status` (CHECK hanya `'completed'`/`'failed'`), `created_at`/`completed_at`. Row count: **0** (belum pernah jalan).

**Verifikasi:** query dijalankan langsung (bukan asumsi dari dokumen lama) — hasil query disandingkan manual kolom-per-kolom, constraint-per-constraint terhadap `notebook-audit.md` Bagian H.2-H.4. Tidak ditemukan satu pun perbedaan (kolom baru/hilang, tipe berubah, constraint berubah, row count berubah).

**File disentuh:** `milestones/1.6-kontrak-skema-sumber-data/logs.md` (catatan verifikasi ini). Tidak ada file lain (murni query read-only, tidak ada skrip permanen ditambahkan ke repo).

## Checkpoint 2 — Dokumen kontrak skema utama

Ditulis `docs/04-schema-contract/raw-schema-contract.md` (5 bagian): (1) kontrak dua-fase dengan tabel keputusan+konsekuensi eksplisit untuk pemanggil M2.x/M3.x; (2) skema kolom lengkap ketiga tabel (bersumber dari hasil query Checkpoint 1, bukan disalin ulang dari `notebook-audit.md` tanpa verifikasi); (3) semantik ambigu (unit USD/bulan, timezone UTC via `timestamptz`, null handling kedua tabel); (4) semantik update append-only snapshot dengan definisi query "current state" eksplisit + gap `customer_key` dicatat lengkap; (5) placeholder rujukan ke CHANGELOG (diisi Checkpoint 3).

`.gitkeep` di `docs/04-schema-contract/` dihapus (folder sudah berisi konten sungguhan).

**Verifikasi:** setiap kolom di ketiga tabel (21+2 metadata untuk source, 20+3 metadata untuk synthetic, 7 untuk generation_runs) punya baris di dokumen dengan tipe+constraint — dicek lengkap terhadap hasil Checkpoint 1, tidak ada yang terlewat.

**File disentuh:** `docs/04-schema-contract/raw-schema-contract.md` (baru), `docs/04-schema-contract/.gitkeep` (dihapus).

## Checkpoint 3 — CHANGELOG + aturan breaking-change (KK2)

Ditulis `docs/04-schema-contract/CHANGELOG.md`: proses perubahan (git PR + klasifikasi wajib + entry baru di atas), tabel aturan breaking vs non-breaking (7 skenario konkret: kolom dihapus/rename/tipe berubah/constraint diperketat = breaking; kolom baru nullable/constraint dilonggarkan/dokumentasi murni = non-breaking), dan entry pertama "v1 — Kontrak awal (2026-08-12)" merujuk isi Checkpoint 2 lengkap dengan milestone terdampak (dicek: M1.1-1.3, M1.5 SEMUA sudah konsisten kontrak ini, tidak perlu perubahan kode).

Ditambah 1 baris instruksi wajib-baca-CHANGELOG di `raw-schema-contract.md` Bagian 5 (bukan file baru).

**Verifikasi:** format entry + aturan breaking-change dibaca ulang seolah pembaca baru (Orang #2/#3 hipotetis) — jelas tanpa perlu konteks tambahan dari luar dokumen ini sendiri.

**File disentuh:** `docs/04-schema-contract/CHANGELOG.md` (baru), `docs/04-schema-contract/raw-schema-contract.md` (tambah 1 baris di Bagian 5).

## Checkpoint 4 — Tutup KT-1/KT-2, tambah KT-4

`docs/keputusan-tertunda.md` diupdate: KT-1 dan KT-2 ditandai **STATUS: DITUTUP** dengan rujukan ke `milestones/1.6-kontrak-skema-sumber-data/decisions.md` dan `docs/04-schema-contract/raw-schema-contract.md` (entry ASLI tidak dihapus — riwayat konteks/opsi yang pernah dipertimbangkan tetap terlihat, pola sama update parsial KT-3 di M1.2/M1.5).

Ditambah **KT-4 — Kolom identitas pelanggan (`customer_key`) belum ada di skema `telco_customers_synthetic`**: konteks (konsekuensi langsung penutupan KT-2), kenapa belum dikerjakan (migrasi skema + implementasi generator di luar cakupan seluruh sistem ini, butuh koordinasi eksplisit), pemicu peninjauan (sebelum generator diaktifkan, trigger sama dengan Fase 2 KT-1).

**File disentuh:** `docs/keputusan-tertunda.md` (edit: tutup KT-1/KT-2, tambah KT-4).
