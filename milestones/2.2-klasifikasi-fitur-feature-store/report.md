# Report — Milestone 2.2: Klasifikasi Fitur ke Desain Feature Store

## Ringkasan

Milestone 2.2 selesai — dengan hasil berbeda dari deskripsi asli `mlops-02-pipeline-orchestration.md` ("terjemahkan fitur historis M1.1 jadi skema tabel feature store"). Sebelum breakdown ditulis, ditemukan bahwa **seluruh 29 fitur final model berklasifikasi INSTANT** (`docs/03-notebook-audit/notebook-audit.md` Bagian C) — tidak ada satu pun fitur yang butuh dihitung di muka dari riwayat lintas-baris/waktu. Temuan ini sudah diantisipasi audit M1.1 sendiri (Ambiguitas G.3, status "belum 100% tertutup", eksplisit menyerahkan keputusannya ke Milestone 2.2). Setelah penjelasan bertahap ke user (apa itu fitur INSTANT vs historis, apa yang sebenarnya ingin dibangun M2.2), user memutuskan: **tutup sebagai temuan terdokumentasi, tidak membangun tabel feature store PostgreSQL apa pun sekarang.**

Milestone ini menghasilkan **keputusan formal berbasis bukti**, bukan skema tabel — konsisten prinsip "jangan bangun untuk kebutuhan hipotetis" (CLAUDE.md) dan pola M1.1/M1.6 (audit/kontrak sebagai deliverable, bukan selalu kode/infra).

## Kriteria Keberhasilan vs Bukti (Diadaptasi dari Dokumen Sumber)

| KK | Kriteria (diadaptasi) | Bukti |
|---|---|---|
| **KK1** | Setiap 1 dari 29 fitur final dicek ulang terhadap sumber terkini, dikonfirmasi tidak ada yang historis/agregat dan terlewat dari audit awal — 0 gap. | Cross-check independen: 18 kolom mentah yang benar-benar dipakai sebagai input 29 fitur final (dari tabel klasifikasi C.1-C.5) dicocokkan terhadap `docs/04-schema-contract/raw-schema-contract.md` Bagian 2 (sumber PALING BARU, hasil verifikasi struktur tabel real Supabase Milestone 1.6, hari yang sama). **Hasil: seluruh 18 kolom ada langsung sebagai kolom current-state** di `telco_customers_source` maupun `telco_customers_synthetic` — 0 gap, memperkuat kesimpulan G.3/H.1 dengan sumber lebih baru, bukan sekadar mengulang klaim lama. |
| **KK2** | Temuan dibagikan dan dikonfirmasi dipahami calon pemilik real-time API (simulasi Orang #3), termasuk dampaknya ke desain M3.x. | Dikonfirmasi eksplisit lewat `AskUserQuestion` — **"Ya, jelas -- KK2 terpenuhi"** — user memahami real-time API tidak perlu mekanisme baca feature store terpisah untuk model versi sekarang. |

## Keputusan Final

Lihat [`decisions.md`](./decisions.md) — 2 keputusan: (1) tidak membangun feature store untuk model versi sekarang (menutup Ambiguitas G.3 `notebook-audit.md`), dengan opsi "bangun kosong forward-looking" ditolak eksplisit; (2) trigger peninjauan ulang dicatat (retraining dengan fitur historis, atau kebutuhan dashboard monitoring M3.x).

`docs/03-notebook-audit/notebook-audit.md` Ambiguitas G.3 diperbarui statusnya jadi TERTUTUP, mengikuti pola G.1 — termasuk mencatat bahwa sub-pertanyaan lama G.3 (semantik update in-place vs snapshot) sebenarnya sudah terjawab Milestone 1.6 (KT-2), bukan baru dijawab di sini.

## Perubahan dari Plan Awal

- **Scope milestone jauh lebih kecil dari deskripsi asli** — bukan penyimpangan, tapi hasil sah proses milestone itu sendiri: G.3 (`notebook-audit.md`) sejak M1.1 sudah eksplisit menyerahkan keputusan "bangun feature store atau tidak" ke titik ini. Plan disesuaikan SEBELUM ditulis (lewat klarifikasi bertahap ke user), bukan ditemukan di tengah eksekusi seperti beberapa temuan Milestone 2.1.
- Tidak ada perubahan lain dari plan yang disetujui — kedua checkpoint dieksekusi sesuai urutan.

## Keterbatasan dan Item Terbuka

- **Keputusan ini terikat pada model versi sekarang (versi 1, alias `champion` — lihat `docs/05-model-registry-contract/`)** — bukan keputusan permanen. Trigger peninjauan ulang sudah dicatat eksplisit di `decisions.md`.
- **Dampak ke desain M3.x (real-time API) belum diuji secara implementasi** — baru dikonfirmasi dipahami secara konsep (KK2). Desain konkret bagaimana API mengambil fitur (dari payload request vs lookup baris DB) tetap keputusan M3.x sendiri, di luar cakupan M2.2.
- Tidak ada dampak ke `docs/keputusan-tertunda.md` (KT-1/2/3/4) — keempatnya tidak berubah status oleh milestone ini.

## Follow-up

- Milestone 2.3 (Job Refresh Feature Store) — **perlu ditinjau ulang relevansinya** mengingat M2.2 menyimpulkan tidak ada feature store untuk fitur model yang perlu di-refresh. Kemungkinan M2.3 perlu di-scope-ulang atau dilewati untuk model versi sekarang, sama seperti M2.2 — direkomendasikan dibahas eksplisit dengan user sebelum mulai, bukan diasumsikan tetap berjalan seperti dideskripsikan asli.
- Milestone 2.4 (Gerbang Kualitas Data Harian) dan M2.5 (Batch Scoring DAG) TIDAK terdampak — keduanya tidak bergantung pada keberadaan feature store fitur model.
