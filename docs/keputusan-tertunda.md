# Keputusan Tertunda — Backlog Project-Wide

File ini mencatat keputusan yang identifikasinya sudah muncul saat pengerjaan suatu milestone, tapi belum saatnya diputuskan (butuh konteks/dependency yang belum tersedia, atau bukan wewenang milestone yang sedang berjalan). Setiap entri dihapus/dipindah ke `milestones/<id>-<slug>/decisions.md` begitu benar-benar diputuskan pada milestone yang relevan.

---

## KT-1 — Tabel mana yang jadi kontrak skema data mentah resmi: `telco_customers_source` vs `telco_customers_synthetic`

**STATUS: DITUTUP (Milestone 1.6, 2026-08-12).** Keputusan final: kontrak DUA FASE — `telco_customers_source` dipakai sekarang (pengembangan M2.x/M3.x), `telco_customers_synthetic` jadi kontrak resmi begitu seluruh sistem selesai DAN generator diaktifkan. Lihat `milestones/1.6-kontrak-skema-sumber-data/decisions.md` Keputusan #1 dan `docs/04-schema-contract/raw-schema-contract.md` Bagian 1 untuk detail lengkap+konsekuensi bagi pemanggil.

**Muncul saat:** Milestone 1.1 (audit notebook), verifikasi Supabase — lihat `docs/03-notebook-audit/notebook-audit.md` Ambiguitas G.10.

**Konteks:** Supabase punya 2 tabel yang merepresentasikan pelanggan secara semantik sama tapi beda konvensi nama kolom — `telco_customers_source` (PascalCase, 594.194 baris statis, byte-identik dengan data training) dan `telco_customers_synthetic` (snake_case, 0 baris, tujuan data generator near-real-time yang sengaja belum diaktifkan user).

**Kenapa belum diputuskan sekarang:** Milestone 1.1 sifatnya audit read-only terhadap notebook (dan verifikasi lanjutannya ke Supabase), bukan tempat mengunci kontrak skema — itu wewenang Milestone 1.3 (`docs/02-implementation-plan/mlops-01-productionization.md`). Keputusan ini juga berdampak ke desain Milestone 1.6 (kontrak skema sumber data) dan kapan generator akhirnya diaktifkan (belum ada tanggal).

**Pemicu peninjauan:** Saat Milestone 1.3 (Skema dan Validasi Data Input) mulai dikerjakan — atau lebih awal jika user memutuskan mengaktifkan data generator sebelum itu.

**Opsi yang sudah terlihat dari audit (bukan rekomendasi final):** (a) modul transformasi menerima kedua konvensi nama kolom via mapping eksplisit; (b) buat VIEW di Supabase yang menyatukan kedua tabel ke satu skema kanonik; (c) `telco_customers_source` dianggap deprecated begitu generator aktif, hanya `telco_customers_synthetic` yang dipakai production seterusnya.

---

## KT-2 — Apakah baris pelanggan di Supabase di-update in-place seiring waktu, atau selalu snapshot baru per kejadian

**STATUS: DITUTUP (Milestone 1.6, 2026-08-12).** Keputusan final: **append-only snapshot** (gaya Slowly Changing Dimension Type 2) — direkomendasikan sebagai standar industri (user minta rekomendasi, bukan tahu jawaban pasti), dikonfirmasi tidak berdampak ke model yang sudah dilatih (seluruh 29 fitur final berstatus INSTANT). Menghasilkan temuan gap baru — lihat **KT-4** di bawah. Lihat `milestones/1.6-kontrak-skema-sumber-data/decisions.md` Keputusan #2 dan `docs/04-schema-contract/raw-schema-contract.md` Bagian 4 untuk detail lengkap.

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

**Update Milestone 1.5 (2026-08-11) — xgboost/lightgbm MASIH belum terjawab pasti, tapi sudah PROVISIONAL:** `model_final.joblib` (VotingClassifier: `LGBMClassifier` + 2x `XGBClassifier`) baru pertama kali benar-benar dimuat di M1.5 Checkpoint 2 (M1.2-1.4 hanya pernah memuat `preprocessor.joblib`). Beda dari kasus sklearn, TIDAK ada `InconsistentVersionWarning` dengan nomor versi eksplisit -- yang muncul cuma `UserWarning` generik dari xgboost ("If you are loading a serialized model ... generated by an older version of XGBoost ...") yang mengonfirmasi ADA mismatch versi tapi tidak menyebut versi persis training asli. Model tetap berhasil dimuat dan `predict_proba()` menghasilkan output valid (non-NaN, masuk akal) dengan `lightgbm==4.7.0`/`xgboost==3.4.0` -- dikunci PROVISIONAL (pola sama pandas/numpy) di `pyproject.toml`, lihat `milestones/1.5-inference-service/decisions.md` Keputusan #9. Versi training asli DS untuk xgboost/lightgbm tetap belum terkonfirmasi -- KT-3 TIDAK ditutup untuk keduanya, cuma statusnya berubah dari "belum pernah dicoba dimuat" jadi "sudah dimuat, versi berbeda tapi berfungsi".

---

## KT-4 — Kolom identitas pelanggan (`customer_key`) belum ada di skema `telco_customers_synthetic`

**Muncul saat:** Milestone 1.6, sebagai konsekuensi langsung penutupan KT-2 — lihat `milestones/1.6-kontrak-skema-sumber-data/decisions.md` Keputusan #2 dan `docs/04-schema-contract/raw-schema-contract.md` Bagian 4.

**Konteks:** KT-2 ditutup dengan keputusan desain generator ke depan memakai pola append-only snapshot (SCD Type 2) — tiap kejadian generator menghasilkan baris baru, "current state" per pelanggan = baris terbaru per identitas pelanggan. Tapi skema `telco_customers_synthetic` SAAT INI (diverifikasi ulang Milestone 1.6 Checkpoint 1 lewat query `information_schema` langsung, bukan asumsi dari dokumen lama) **tidak punya kolom identitas pelanggan yang stabil lintas baris** — `synthetic_id` (primary key tabel ini) unik PER BARIS/PER KEJADIAN, bukan per pelanggan. Tanpa kolom tambahan (mis. `customer_key`), query "current state" (`SELECT DISTINCT ON (customer_key) ... ORDER BY generated_at DESC`) tidak bisa dijalankan — pola SCD Type 2 yang disepakati KT-2 tidak bisa diimplementasikan generator dengan benar.

**Kenapa belum diputuskan/dikerjakan sekarang:** Migrasi skema database (menambah kolom ke tabel Supabase) di luar cakupan implementasi Milestone 1.6 (sifatnya observasional+dokumentasi, sama seperti Milestone 1.1) — dan lebih jauh lagi, di luar cakupan seluruh sistem MLOps ini (implementasi generator itu sendiri adalah "given", di luar cakupan per `mlops-01-productionization.md`). Perlu koordinasi dengan pemilik/pembangun sistem generator (di proyek solo ini, user sendiri di peran berbeda) untuk menentukan bentuk `customer_key` yang tepat (mis. hash dari kombinasi atribut, UUID terpisah yang di-generate sekali per "pelanggan simulasi", dst — belum ada opsi yang dieksplorasi, murni gap yang teridentifikasi).

**Pemicu peninjauan:** Sebelum data generator pertama kali diaktifkan/diuji (trigger sama dengan Fase 2 kontrak dua-fase KT-1 — "setelah seluruh sistem MLOps ini selesai dibangun").

---

## KT-5 — Verdict "latensi baca wajar/tidak untuk real-time API" saat batch DAG jalan bersamaan

**Muncul saat:** Milestone 2.6, Checkpoint 3-4 (pengukuran beban PostgreSQL saat `batch_scoring_flow()` jalan skala penuh).

**Konteks:** KK1 Milestone 2.6 (`docs/02-implementation-plan/mlops-02-pipeline-orchestration.md`) meminta bukti "latensi baca bergaya real-time API masih dalam rentang wajar" saat job batch (M2.5) jalan bersamaan. Karena real-time API belum dibangun (M3.x belum mulai) dan tidak ada feature store (M2.2, DITUTUP — seluruh 29 fitur INSTANT), tidak ada SLA nyata atau pola trafik produksi sungguhan yang bisa dijadikan acuan pasti untuk kata "wajar". Milestone 2.6 tetap membangun harness pengukuran (`orchestration/load_test/concurrent_readers.py`) dan mengambil angka nyata — baseline terisolasi vs saat job batch jalan bersamaan, untuk dua proxy consumer (resolusi alias model via `registry.resolve_alias_version()`, dan query agregat gaya dashboard monitoring ke `predictions.batch_predictions`) — tapi TIDAK menyimpulkan verdict pass/fail formal dari angka itu.

**Kenapa belum diputuskan sekarang:** Menetapkan ambang batas (relatif maupun absolut) tanpa SLA nyata berarti menebak — persis pola yang dilarang eksplisit oleh `CLAUDE.md`/`AGENT.md` Bagian "Batas Implementasi Saat Ini" ("jangan memilih... threshold, SLA... yang dokumen arsitektur sengaja biarkan terbuka tanpa mengikuti workflow keputusan"). Real-time API (M3.x) adalah pemilik sah kebutuhan latensi ini begitu benar-benar dibangun dan diukur dengan trafik nyata (bukan simulasi/proxy dari milestone lain).

**Pemicu peninjauan:** M3.x (`mlops-03-deployment-observability.md`) mulai dikerjakan, khususnya saat real-time API punya kontrak latensi/SLA nyata yang bisa dijadikan acuan — atau lebih awal jika trafik konkurensi nyata (generator aktif + real-time API live) membuat pertanyaan ini mendesak sebelum M3.x formal dimulai.

**Data yang sudah tersedia sebagai dasar keputusan nanti:** Angka baseline vs bersamaan (p50/p95 kedua proxy consumer, delta absolut/persentase) dan analisis korelasi fase flow — lihat `milestones/2.6-isolasi-beban-postgresql/logs.md` dan `decisions.md`.

---

## KT-6 — Apakah `write_predictions` perlu diubah dari transaksi tunggal ke commit bertahap

**Muncul saat:** Milestone 2.6, Checkpoint 3 (analisis korelasi fase, hasil pengukuran nyata).

**Konteks:** Pengukuran beban konkuren M2.6 menemukan Consumer B (proxy query agregat gaya dashboard monitoring ke `predictions.batch_predictions`) mengalami degradasi p95 nyata (+210% dibanding baseline terisolasi, dari ~196ms ke ~607ms untuk keseluruhan run, memuncak ~767ms selama fase `write`) yang berkorelasi jelas dan spesifik dengan fase `write_predictions` M2.5 -- task yang menulis 594.194 baris dalam SATU transaksi Postgres panjang (~4 menit) ke tabel yang sama persis dibaca Consumer B. Consumer A (resolusi alias model, schema `mlflow`) TIDAK menunjukkan degradasi berarti (delta dalam rentang noise) -- temuan ini spesifik ke pola akses `predictions.batch_predictions`, bukan beban Postgres secara umum.

Mitigasi paling menyasar akar masalah ini adalah mengubah `write_predictions` dari satu transaksi besar (all-or-nothing) menjadi commit bertahap per-chunk (mis. tiap 10.000-50.000 baris) -- ini akan memperpendek jendela waktu lock/kontensi ditahan, TAPI mengorbankan jaminan all-or-nothing yang jadi keputusan sadar M2.5 (Keputusan #1: rollback penuh kalau gagal di tengah, demi konsistensi data) -- kegagalan di tengah proses commit bertahap bisa meninggalkan sebagian chunk ter-commit, sebagian tidak, yang justru melanggar prinsip "tidak ada data tidak konsisten" (KK2 M2.5).

**Kenapa belum diputuskan sekarang:** Ini trade-off nontrivial terhadap keputusan M2.5 yang sudah final (bukan detail implementasi kecil), dan saat ini **belum ada trafik baca konkuren nyata** yang benar-benar dirugikan (generator belum aktif, real-time API/dashboard M3.x belum dibangun) -- mengubah desain sekarang berarti menukar jaminan korektnes yang sudah terbukti demi mengatasi kontensi yang baru terbukti berdampak di kondisi lab/simulasi, bukan produksi nyata.

**Pemicu peninjauan:** Trafik baca konkuren nyata mulai ada (generator aktif DAN/ATAU real-time API/dashboard M3.x live) DAN degradasi serupa terkonfirmasi berdampak nyata (bukan cuma simulasi) -- saat itu, evaluasi ulang trade-off commit bertahap vs all-or-nothing dengan konteks nyata (mis. mungkin cukup commit di 2-3 chunk besar, bukan banyak chunk kecil, untuk menyeimbangkan keduanya).

**Referensi:** `milestones/2.6-isolasi-beban-postgresql/logs.md` (angka pengukuran lengkap per fase).

---

## KT-7 — Verifikasi parity CI penuh terhadap real-time API SUNGGUHAN

**Muncul saat:** Milestone 2.7, Checkpoint 2 (Gate 3 -- verifikasi parity otomatis).

**Konteks:** KK Milestone 2.7 meminta gerbang CI yang memverifikasi "jalur batch dan real-time (disimulasikan)" menghasilkan output identik. Real-time API (M3.x) belum dibangun sama sekali -- tidak ada jalur kedua sungguhan untuk dibandingkan. Gate 3 M2.7 mengaktifkan test M2.5 yang sudah ada (`tests/orchestration/test_batch_scoring.py::test_batch_predictions_match_direct_predict_active_call`) sebagai gerbang CI sungguhan -- test ini membandingkan hasil DAG batch (tersimpan di DB) vs pemanggilan LANGSUNG `predict_active()`, proxy terbaik yang tersedia SEKARANG (satu-satunya kode "real-time" yang ada). Diverifikasi juga lewat uji coba terkontrol (sengaja membuat `score_batch` menyimpang dari `predict_active()`) -- gerbang terbukti menangkap penyimpangan nyata.

**Kenapa belum diputuskan sekarang:** Test ini TIDAK BISA menangkap bug yang nanti muncul di kode M3.x sendiri (mis. kesalahan pemetaan skema request ke skema data mentah) -- karena kode itu belum ditulis, tidak ada yang bisa dites. Verifikasi parity PENUH (batch vs real-time API yang benar-benar dideploy, menerima request HTTP sungguhan) baru bisa dibangun setelah M3.x punya service yang bisa dipanggil.

**Pemicu peninjauan:** M3.x (`mlops-03-deployment-observability.md`) mulai membangun real-time API sungguhan -- saat itu, gerbang parity CI perlu diperluas untuk memanggil endpoint HTTP sungguhan (bukan cuma `predict_active()` langsung), dan `tests/orchestration/test_batch_scoring.py`'s test parity yang sudah ada bisa jadi dasar/pola, bukan digantikan.

**Referensi:** `milestones/2.7-cicd-verifikasi-parity/decisions.md`, `milestones/2.5-batch-scoring-dag/decisions.md` Keputusan #3 (catatan salah ketik dokumen sumber "verifikasi otomatis dibangun di Milestone 2.6" seharusnya 2.7 -- sudah dikonfirmasi benar M2.7 di milestone ini).
