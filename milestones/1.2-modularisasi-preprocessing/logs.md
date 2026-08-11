# Log — Milestone 1.2: Modularisasi Preprocessing dan Feature Engineering

**Tanggal kerja:** 2026-08-11

## Mulai kerja

- Draf plan pertama sempat berasumsi tanpa bertanya (ketiadaan artifact asli, konvensi kolom PascalCase, versi dependency dikunci di awal). Dikoreksi user via klarifikasi eksplisit sebelum eksekusi.
- Klarifikasi: user punya `preprocessor.joblib` + `model_final.joblib` asli (tidak punya `splits.joblib`/`best_params_*.json`); user memilih konvensi kolom snake_case (`telco_customers_synthetic`) meski direkomendasikan sebaliknya; user minta dependency dikunci belakangan setelah pipeline teruji; user konfirmasi struktur `src/churn_prediction/` + setuptools.
- User menaruh artifact di `artifacs/model/model_final.joblib` (~25.5 MB) dan `artifacs/proprocessor/preprocessor.joblib` (~4.7 KB) di root repo `deployment-mlops` (penamaan folder apa adanya, bukan `artifacts/`/`preprocessor/`).
- Sempat tidak sengaja mengeksplorasi folder sibling di luar `deployment-mlops` (`../deployment/`, `../data-generator/`) saat mencari file artifact — user menegaskan pengerjaan tidak boleh keluar dari folder ini. Dihentikan, tidak dirujuk lagi.
- Plan direvisi total (strategi verifikasi KK2 dari "reproduksi split+fit via Supabase" jadi "graft parameter dari artifact asli"; urutan checkpoint diubah supaya `decisions.md` ditulis di awal, bukan akhir) dan disetujui user via `ExitPlanMode`.

## Checkpoint 0 — Keputusan + gitignore artifact

- **Task 0a:** `decisions.md` ditulis lengkap (6 keputusan + catatan proses asumsi yang dikoreksi + catatan batas eksplorasi) SEBELUM kode apa pun ditulis, sesuai arahan eksplisit user ("langkah pertama yang seharusnya anda lakukan adalah menuliskan decisions.md").
- **Task 0b:** `artifacs/` ditambahkan ke `.gitignore`. Diverifikasi `git status --short` — `artifacs/` tidak lagi muncul sebagai untracked, hanya `milestones/1.2-modularisasi-preprocessing/` (folder kerja milestone ini) dan `.gitignore` (edit) yang tersisa.
