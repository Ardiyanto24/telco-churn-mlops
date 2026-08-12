# Logs — Milestone 2.2: Klasifikasi Fitur ke Desain Feature Store

## Checkpoint 1 — Verifikasi ulang + keputusan tertulis

**Mulai:** 2026-08-13.

**Sebelum plan ditulis:** temuan awal disampaikan ke user (notebook-audit.md Bagian C/G.3/H.1 -- seluruh 29 fitur INSTANT). User meminta penjelasan lebih detail dua kali sebelum memutuskan: (1) apa itu "INSTANT" secara konkret, (2) apa sebenarnya yang ingin dibangun Milestone 2.2 dari awal (analogi "kulkas"/precompute dijelaskan). Setelah penjelasan, user memilih: tutup sebagai temuan terdokumentasi, tidak membangun tabel feature store apa pun.

**Task 1 (cross-check):** 18 kolom mentah yang benar-benar dipakai sebagai input 29 fitur final (dikumpulkan dari tabel C.1-C.5 notebook-audit.md: `tenure`, `MonthlyCharges`, `TotalCharges`, `SeniorCitizen`, `Partner`, `Dependents`, `PhoneService`, `PaperlessBilling`, `PaymentMethod`, `OnlineSecurity`, `OnlineBackup`, `DeviceProtection`, `TechSupport`, `StreamingTV`, `StreamingMovies`, `MultipleLines`, `Contract`, `InternetService`) dicocokkan terhadap `docs/04-schema-contract/raw-schema-contract.md` Bagian 2.1/2.2 (sumber terbaru, hasil verifikasi struktur tabel real Supabase Milestone 1.6 -- hari yang sama). **Hasil:** seluruh 18 kolom ada langsung sebagai kolom current-state di KEDUA tabel (`telco_customers_source`, `telco_customers_synthetic`). 0 gap. (Catatan: `gender` dan `Churn` — 2 dari 20 kolom bisnis — tidak dipakai sebagai input fitur; `Churn` adalah target model, `gender` tidak dipakai sebagai predictor.)

**Task 2:** `milestones/2.2-klasifikasi-fitur-feature-store/decisions.md` ditulis — keputusan final + opsi ditolak (bangun kosong forward-looking) + trigger peninjauan ulang.

**Selesai, commit:** `79e9a29` (docs).

## Checkpoint 2 — Dokumentasi penutupan & serah terima

**Task 3:** Status ambiguitas **G.3** di `docs/03-notebook-audit/notebook-audit.md` diperbarui dari "DIPERKUAT, BELUM 100% TERTUTUP" jadi "TERTUTUP (Milestone 2.2)" — mengikuti pola persis G.1. Sub-pertanyaan lama G.3 (update in-place vs snapshot) dicatat sudah terjawab Milestone 1.6 (KT-2), bukan diklaim baru dijawab di sini.
