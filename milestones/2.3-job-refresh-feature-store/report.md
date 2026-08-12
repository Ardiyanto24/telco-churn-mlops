# Report — Milestone 2.3: Job Refresh Feature Store

## Ringkasan

Milestone 2.3 selesai — ditutup sebagai **N/A untuk model versi sekarang**, konsekuensi langsung Milestone 2.2. Deskripsi asli M2.3 (`mlops-02-pipeline-orchestration.md`) eksplisit bergantung pada "skema Milestone 2.2"; karena M2.2 menyimpulkan tidak ada skema feature store (seluruh 29 fitur INSTANT), tidak ada yang perlu di-refresh. User membuka sesi dengan sudah menyadari ketergantungan ini sebelum breakdown diminta — dikonfirmasi lewat pengecekan langsung teks dokumen, bukan diasumsikan.

Milestone ini TIDAK mengulang cross-check M2.2 — cukup merujuk buktinya, konsisten prinsip menghindari duplikasi verifikasi yang sudah tuntas.

## Kriteria Keberhasilan vs Bukti (Diadaptasi dari Dokumen Sumber)

| KK Asli | Status Diadaptasi | Bukti |
|---|---|---|
| Feature store ter-refresh terjadwal, nilai cocok perhitungan manual. | N/A, didokumentasikan lengkap. | `decisions.md` merujuk langsung `milestones/2.2-klasifikasi-fitur-feature-store/decisions.md` Keputusan #1 — tidak ada tabel feature store untuk direfresh. |
| Pembacaan bersamaan saat refresh tidak error/data setengah-refresh. | N/A — tidak ada refresh job untuk diuji. | Dicatat eksplisit sebagai kondisi "belum relevan" di `decisions.md`, bukan dihilangkan diam-diam dari laporan. |
| Refresh berikutnya reflect perubahan data mentah. | N/A dengan alasan sama. | Trigger kapan ini relevan lagi dicatat eksplisit (2 kondisi, lihat Keputusan Final). |

## Keputusan Final

Lihat [`decisions.md`](./decisions.md) — 2 keputusan: (1) M2.3 ditutup N/A, opsi "bangun minimal forward-looking" ditolak (alasan sama M2.2); (2) dua trigger peninjauan ulang dicatat TERPISAH karena beda konsep — retraining dengan fitur historis (sama M2.2, memicu peninjauan ulang M2.2+M2.3 sekaligus), vs aktivasi generator (Fase 2 KT-1) yang bisa memicu kebutuhan materialisasi "baris terbaru per pelanggan" (bukan feature store, bergantung KT-4 selesai duluan).

## Perubahan dari Plan Awal

Tidak ada — plan sudah disesuaikan ke scope N/A sebelum ditulis (user sudah membawa kesadaran ketergantungan M2.2→M2.3 di awal sesi), bukan ditemukan di tengah eksekusi.

## Keterbatasan dan Item Terbuka

- Trigger #2 (materialisasi latest-row) bergantung KT-4 (`docs/keputusan-tertunda.md` — kolom `customer_key` belum ada di `telco_customers_synthetic`) yang harus selesai lebih dulu. Ini BUKAN diselesaikan di M2.3, cuma dicatat sebagai dependency untuk kondisi pemicu masa depan.
- Tidak ada dampak ke KT-1/KT-2/KT-3/KT-4 — keempatnya tidak berubah status oleh milestone ini, cuma dirujuk sebagai bukti/konteks.

## Follow-up

- **Milestone 2.4 (Gerbang Kualitas Data Harian) dan M2.5 (Batch Scoring DAG) TIDAK terdampak** — keduanya memvalidasi/memproses data mentah langsung, tidak bergantung pada keberadaan feature store fitur model. Aman dikerjakan berikutnya sesuai deskripsi asli, tanpa penyesuaian scope seperti M2.2/M2.3.
- **Milestone 2.6 (Isolasi Beban PostgreSQL)** perlu diingat kelak: karakteristik beban yang tadinya diasumsikan mencakup "job refresh feature store" (M2.3) sekarang cuma mencakup batch scoring DAG (M2.5) — baseline beban akan lebih sederhana dari deskripsi asli dokumen.
