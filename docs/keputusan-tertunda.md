# Keputusan Tertunda — Backlog Project-Wide

File ini mencatat keputusan yang identifikasinya sudah muncul saat pengerjaan suatu milestone, tapi belum saatnya diputuskan (butuh konteks/dependency yang belum tersedia, atau bukan wewenang milestone yang sedang berjalan). Setiap entri dihapus/dipindah ke `milestones/<id>-<slug>/decisions.md` begitu benar-benar diputuskan pada milestone yang relevan.

---

## KT-1 — Tabel mana yang jadi kontrak skema data mentah resmi: `telco_customers_source` vs `telco_customers_synthetic`

**Muncul saat:** Milestone 1.1 (audit notebook), verifikasi Supabase — lihat `docs/03-notebook-audit/notebook-audit.md` Ambiguitas G.10.

**Konteks:** Supabase punya 2 tabel yang merepresentasikan pelanggan secara semantik sama tapi beda konvensi nama kolom — `telco_customers_source` (PascalCase, 594.194 baris statis, byte-identik dengan data training) dan `telco_customers_synthetic` (snake_case, 0 baris, tujuan data generator near-real-time yang sengaja belum diaktifkan user).

**Kenapa belum diputuskan sekarang:** Milestone 1.1 sifatnya audit read-only terhadap notebook (dan verifikasi lanjutannya ke Supabase), bukan tempat mengunci kontrak skema — itu wewenang Milestone 1.3 (`docs/02-implementation-plan/mlops-01-productionization.md`). Keputusan ini juga berdampak ke desain Milestone 1.6 (kontrak skema sumber data) dan kapan generator akhirnya diaktifkan (belum ada tanggal).

**Pemicu peninjauan:** Saat Milestone 1.3 (Skema dan Validasi Data Input) mulai dikerjakan — atau lebih awal jika user memutuskan mengaktifkan data generator sebelum itu.

**Opsi yang sudah terlihat dari audit (bukan rekomendasi final):** (a) modul transformasi menerima kedua konvensi nama kolom via mapping eksplisit; (b) buat VIEW di Supabase yang menyatukan kedua tabel ke satu skema kanonik; (c) `telco_customers_source` dianggap deprecated begitu generator aktif, hanya `telco_customers_synthetic` yang dipakai production seterusnya.

---

## KT-2 — Apakah baris pelanggan di Supabase di-update in-place seiring waktu, atau selalu snapshot baru per kejadian

**Muncul saat:** Milestone 1.1, verifikasi Supabase — lihat `notebook-audit.md` G.3.

**Konteks:** Klasifikasi seluruh 29 fitur model sebagai INSTANT (Bagian C `notebook-audit.md`) berasumsi setiap baris adalah current-state pelanggan yang tinggal dibaca. Ini terbukti benar untuk data training statis, dan diperkuat oleh fakta tidak ada tabel log/riwayat lain di Supabase (Bagian H.1) — tapi belum terkonfirmasi apakah kolom seperti `tenure` di `telco_customers_synthetic` akan terus di-update pada baris yang sama (row tetap, tenure bertambah tiap bulan) atau setiap snapshot menghasilkan baris `synthetic_id` baru (row baru, tidak pernah diperbarui).

**Kenapa belum diputuskan sekarang:** Generator belum pernah dijalankan (0 baris di `telco_customers_synthetic`/`synthetic_generation_runs`) — perilaku sesungguhnya belum bisa diobservasi, hanya bisa ditanyakan ke pemilik sistem generator (user).

**Pemicu peninjauan:** Sebelum Milestone 1.6 (kontrak skema sumber data) ditutup, atau saat generator pertama kali diaktifkan/diuji — mana pun lebih dulu.

---

## KT-3 — Versi library yang dikunci untuk `requirements.txt`/`pyproject.toml` Milestone 1.2

**Muncul saat:** Milestone 1.1, audit dependency — lihat `notebook-audit.md` Bagian F, Ambiguitas G.2.

**Konteks:** Tidak ada satu pun `__version__`/`pip freeze` di ketujuh notebook Data Scientist. Versi pandas/scikit-learn/xgboost/lightgbm/imbalanced-learn/optuna/shap yang benar-benar dipakai saat training tidak tercatat di mana pun.

**Update Milestone 1.2 (2026-08-11) — scikit-learn TERJAWAB tanpa sengaja:** saat memuat `artifacs/proprocessor/preprocessor.joblib` asli (`joblib.load`), sklearn memunculkan `InconsistentVersionWarning` yang menyebutkan eksplisit **artifact di-fit dengan scikit-learn 1.6.1**. Ini bukti konkret (bukan tebakan) — `pyproject.toml` Milestone 1.2 sudah memakai `scikit-learn>=1.2` sebagai batas bawah (dari bukti `sparse_output=` di kode notebook); begitu Milestone 1.2 mengunci versi final (Checkpoint 6), gunakan `scikit-learn==1.6.1` persis, bukan versi terkini sembarang. Versi pandas/numpy/xgboost/lightgbm/imbalanced-learn/optuna/shap yang lain **masih belum terjawab** — `model_final.joblib` (VotingClassifier dari xgboost+lightgbm) mungkin bisa diperiksa serupa saat Milestone 1.5 (inference service) memuatnya nanti.

**Kenapa belum diputuskan sekarang (untuk sisa library selain scikit-learn):** Butuh klarifikasi Data Scientist (environment Kaggle yang dipakai, atau `pip freeze` dari sesi training asli) sebelum bisa dikunci dengan percaya diri — menebak versi berisiko training-serving skew (prinsip Bagian 2 dokumen arsitektur).

**Pemicu peninjauan:** Sebelum Milestone 1.2 mengunci dependency final (scikit-learn sudah bisa dikunci sekarang, sisanya tetap provisional). Sebelum Milestone 1.5 memuat `model_final.joblib`, ulangi teknik serupa (baca `InconsistentVersionWarning`/introspeksi pickle) untuk menjawab versi xgboost/lightgbm.
