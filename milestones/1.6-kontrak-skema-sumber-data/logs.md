# Logs — Milestone 1.6: Kontrak Skema dengan Sumber Data

## Checkpoint 0 — Keputusan + scaffold

**Mulai:** 2026-08-12.

Tiga pertanyaan diajukan lewat AskUserQuestion sebelum plan ditulis (KT-1: tabel mana jadi kontrak resmi; KT-2: semantik update generator; jalur komunikasi perubahan skema). Untuk KT-2 dan jalur komunikasi, user minta rekomendasi standar industri secara eksplisit alih-alih menjawab langsung — rekomendasi (append-only snapshot/SCD Type 2 untuk KT-2; data contract versioned dengan CHANGELOG untuk jalur komunikasi) dijelaskan detail ke user lewat dua putaran percakapan (user awalnya minta klarifikasi lebih lanjut untuk Q1/Q2 sebelum menjawab), lalu dikonfirmasi eksplisit lewat AskUserQuestion kedua. Detail lengkap 5 Keputusan Teknis di `decisions.md`.

Folder `docs/04-schema-contract/` dibuat (kosong, diisi Checkpoint 2-3).

**File disentuh:** `milestones/1.6-kontrak-skema-sumber-data/decisions.md` (baru), `docs/04-schema-contract/` (folder baru, kosong).
