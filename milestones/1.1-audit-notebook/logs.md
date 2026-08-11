# Log — Milestone 1.1: Audit dan Inventarisasi Notebook

**Tanggal kerja:** 2026-08-11

## Mulai kerja

- Baca konteks proyek penuh: `CLAUDE.md`/`AGENT.md`, `docs/01-architecture/rancangan-arsitektur-mlops-platform.md`, ketiga dokumen implementation plan, `milestone-plan-template.md`. Konfirmasi `milestones/` masih kosong — Milestone 1.1 adalah titik mulai.
- Percobaan eksplorasi awal (sub-agent paralel membaca 7 notebook) dihentikan atas permintaan user; breakdown milestone diulang dari nol memakai skill `/planning-and-task-breakdown`.
- Plan disusun (Context, 3 Keputusan Teknis awal, 14 task dalam 6 checkpoint) dan disetujui user via `ExitPlanMode`.

## Checkpoint 1 — Fondasi: Skema Data Mentah

- **Task 1 (audit `tccp-eda.ipynb`):** notebook di-dump ke teks (script `nb_dump.py`, scratchpad) dan dibaca penuh Fase 1 (Insight 1-6). Temuan: 594.194×21, 0 missing, 0 duplikat, 0 nilai di luar skema, target `Churn` imbalance 3.44x, sumber data `/kaggle/input/competitions/playground-series-s6e3/train.csv`.
- **Task 2 (cross-check skema EDA vs preprocessing):** `df.columns`/`dtypes` dari `tccp-preprocessing-v2.ipynb` cell 17 dibandingkan terhadap Task 1 — identik, tidak ada konflik.
- Kedua task dituliskan ke `notebook-audit.md` Bagian A.

## Checkpoint 2 — Logika Preprocessing & Feature Engineering

- **Task 3-5:** `tccp-preprocessing-v2.ipynb` dibaca penuh (33 cell). Notebook ini merujuk eksplisit ke "Insight N" dari dokumen keputusan EDA eksternal (tidak ada di repo) untuk setiap langkah — memudahkan verifikasi urutan operasi. Diekstrak: urutan pipeline 6-step (`FeatureEngineer`→`ColumnDropper`→`StructuralEncoder`→`BinaryEncoder`→`OHEWrapper`→`ScalerWrapper`), formula eksak tiap fitur turunan, parameter `OneHotEncoder`/`StandardScaler`, logika split (70/15/15 stratified, seed 42).
- Temuan penting: `preprocessor.joblib` **memang ada** (disimpan cell 29) — menjawab pertanyaan terbuka dari eksplorasi awal sebelumnya soal keberadaan file ini.
- Dituliskan ke `notebook-audit.md` Bagian B, D (sebagian).

## Checkpoint 3 — Klasifikasi Fitur

- **Task 6:** Ke-29 fitur final + kolom mentah sumbernya diklasifikasikan berdasarkan formula Task 3-5. Temuan signifikan: seluruh fitur adalah INSTANT (tidak ada agregasi lintas baris/waktu di manapun) — dicatat sebagai Keputusan #4 dan Ambiguitas G.3 karena berdampak besar ke desain feature store Milestone 2.2.
- Dituliskan ke `notebook-audit.md` Bagian C.

## Checkpoint 4 — Cross-Check Notebook Sekunder

- **Task 7:** `tccp-modeling-baseline-v2.ipynb` (34 cell) dibaca — 8 model individual + voting ensemble (XGB+LGBM+RF, equal-weight), load `splits.joblib`, tidak ada transformasi baru.
- **Task 8:** `tccp-hyperparameter-tuning.ipynb` — di-grep untuk konfirmasi referensi `splits.joblib`/SMOTE (tidak dibaca ulang penuh sel-per-sel karena kontennya sudah tervalidasi konsisten lewat grep bertarget dan cross-check nilai numerik terhadap `tccp-evaluation.ipynb`).
- **Task 9:** `tccp-evaluation.ipynb` (35 cell, sebagian dibaca penuh + grep bertarget) — konfirmasi `ThresholdCalibrator` (F1-optimal, recall floor 0.60), ranking final 7 kandidat, model terbaik `voting_ensemble` threshold `0.6238`, artifact `model_final.joblib`+`model_final_meta.json`.
- **Task 10:** `tccp-xai-gate-1.ipynb`/`tccp-xai-gate-2.ipynb` — grep bertarget untuk `MultipleLines`/`OHE_PARENTS`/`feature_names`. Dikonfirmasi `MultipleLines` muncul sebagai kolom bare di top-10 SHAP gate 2 (bukan `MultipleLines_...`) — cocok dengan Bagian C.4, menyelesaikan ambiguitas OHE yang sempat muncul di eksplorasi awal.
- Dituliskan ke `notebook-audit.md` Bagian D (lengkap), E.

## Checkpoint 5 — Dependency & Ambiguitas

- **Task 11:** `grep -n "pip install|__version__|pip show"` dijalankan terhadap ketujuh file dump — tidak ditemukan satu pun version pin atau `__version__` print. Dicatat sebagai gap eksplisit (Bagian F, Ambiguitas G.2).
- **Task 12:** 9 item ambiguitas dikompilasi dari seluruh temuan Task 1-11, masing-masing merujuk bagian sumbernya (`notebook-audit.md` Bagian G).

## Checkpoint 6 — Konsolidasi & Penutupan

- **Task 13:** `notebook-audit.md` difinalisasi — 7 bagian, daftar isi, ringkasan pembuka.
- **Task 14:** `decisions.md` (4 keputusan, termasuk 1 keputusan tambahan soal klasifikasi INSTANT-semua yang muncul selama eksekusi — bukan bagian dari 3 keputusan awal di plan), `logs.md` (file ini), `report.md` ditulis.

## Commit

- Commit checkpoint tunggal (Milestone 1.1 dieksekusi dalam satu sesi kerja tanpa jeda antar-checkpoint yang butuh commit terpisah) — hash dicatat setelah commit dibuat oleh user/di langkah berikutnya sesi ini.
