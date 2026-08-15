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

**Update 2026-08-13 (Milestone 2.9) — Fase 2 SEBAGIAN dimulai, BUKAN cutover penuh:** Generator ternyata sudah pernah dijalankan user (di luar sesi manapun yang tercatat) — `telco_customers_synthetic` berisi data nyata sejak sebelum M2.9 mulai. M2.9 menambahkan kemampuan `batch_scoring_flow()` men-scoring `telco_customers_synthetic` secara OTOMATIS (event-driven, trigger Postgres+`pg_net`+GitHub `repository_dispatch`, lihat `milestones/2.9-otomatisasi-scoring-data-sintesis/decisions.md`) begitu generator menghasilkan generation baru berstatus `completed`. **Ini BUKAN penutupan penuh kontrak dua-fase KT-1** — `telco_customers_source` TIDAK dipensiunkan (`batch_scoring_flow()` tanpa parameter eksplisit masih default ke `telco_customers_source`, dipakai jalur manual `batch-scoring.yml`/KD-1), dan opsi (a)/(b)/(c) di atas belum diputuskan/dikerjakan (M2.9 memilih pola berbeda: SATU flow yang menerima parameter `source_table`, bukan salah satu dari 3 opsi di atas — lihat `milestones/2.9-otomatisasi-scoring-data-sintesis/decisions.md` Keputusan #5/#6). Keputusan "kapan/apakah `telco_customers_source` benar-benar dipensiunkan" tetap terbuka.

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

**Update 2026-08-13 (Milestone 2.9) — KT-4 DITUTUP, `customer_key` sudah ada dan dipakai sukses:** Saat mengerjakan Milestone 2.9 (otomatisasi scoring data sintesis), diverifikasi ulang lewat query `information_schema` langsung: `telco_customers_synthetic` **SUDAH** punya kolom `customer_key` (uuid, terisi tiap baris) — gap yang dicatat entri ini sebagai "belum ada" ternyata sudah diatasi user secara independen (di luar sesi/milestone manapun yang tercatat, ditemukan sudah ada saat M2.9 mulai). Kolom ini dipakai sebagai identitas utama baris bersumber `telco_customers_synthetic` di `predictions.batch_predictions` (kolom baru `customer_key`, lihat `milestones/2.9-otomatisasi-scoring-data-sintesis/decisions.md` Keputusan #2), diverifikasi bekerja benar lewat uji coba terkontrol skala penuh (1.000 baris) dan uji coba event-driven end-to-end. **Bentuk pasti `customer_key`** (bagaimana user men-generate-nya, apakah stabil lintas kejadian generator berikutnya untuk "pelanggan simulasi" yang sama) TIDAK diverifikasi ulang di M2.9 — di luar cakupan milestone ini, cukup diverifikasi bahwa kolom ADA dan uuid-nya unik+konsisten untuk generation_id yang sudah diproses.

**Catatan tambahan (2026-08-13) — kolom `churn` SENGAJA DIPERTAHANKAN, bukan dihapus:** Saat koordinasi soal `customer_key` di atas, ditemukan juga bahwa `telco_customers_synthetic` (dan `telco_customers_source`) punya kolom `churn`/`Churn` — hasil akhir yang secara desain terlihat aneh ada di tabel pelanggan yang BARU disimulasikan (statusnya harusnya belum diketahui, itu justru yang mau diprediksi sistem ini). Diverifikasi TIDAK berdampak ke pipeline ini sama sekali — `churn` sudah dikecualikan eksplisit dari kontrak 19 kolom fitur sejak Milestone 1.3 (`src/churn_prediction/schema/raw_schema.py`, `column_mapping.py::RAW_PASCAL_TO_SNAKE`), tidak pernah di-SELECT atau dipakai model. User memutuskan **TIDAK meminta kolom ini dihapus dari skema generator** — dipertahankan sengaja sebagai **ground truth untuk evaluasi model di masa depan** (mis. drift/performance monitoring Milestone 3.x, membandingkan prediksi vs hasil sebenarnya begitu waktu berjalan). Pertanyaan APAKAH generator harus mengisi kolom ini dengan nilai pasti untuk pelanggan yang baru disimulasikan (vs mengosongkannya sampai status sebenarnya diketahui) tetap murni keputusan desain generator, di luar cakupan sistem ini — tidak diputuskan di sini.

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

---

## KT-8 — Deployment real-time API ke Kubernetes VM/cloud always-on (bukan Docker Desktop lokal)

**Muncul saat:** Milestone 3.3, sebelum plan ditulis (`AskUserQuestion` dua putaran ke user).

**Konteks:** Milestone 3.3 (`mlops-03-deployment-observability.md`) meminta real-time API (M3.2) di-deploy ke Kubernetes, tanpa mengunci target konkret (dokumen arsitektur Bagian 10 sengaja membiarkan ini terbuka). User awalnya mengira tujuan "auto predict saat data sintesis baru masuk tanpa perlu menghidupkan komputer" bergantung pada keputusan ini -- diklarifikasi TIDAK: tujuan itu sudah terpenuhi sejak Milestone 2.9 (trigger Postgres `pg_net` -> GitHub `repository_dispatch` -> GitHub Actions, sepenuhnya cloud-based, TIDAK melibatkan Kubernetes sama sekali). Real-time API (dipanggil sinkron per-kejadian oleh pemanggil eksternal) adalah use case BERBEDA dari batch auto-scoring.

User diberi 2 opsi: (a) Docker Desktop Kubernetes lokal -- gratis, zero setup baru, TAPI API cuma reachable selama komputer user menyala; (b) hosting always-on di luar komputer user -- opsi termurah yang diriset adalah VPS gratis (Oracle Cloud Always Free) menjalankan k3s.

**Riset Oracle Cloud Always Free (2026-08-14):** Kuota compute saat ini 2 OCPU + 12GB RAM (VM ARM Ampere A1) -- SECARA TEKNIS cukup untuk k3s + API ini (image 1.63GB, kebutuhan RAM runtime jauh di bawah 12GB, dikonfirmasi observasi `docker stats` M3.3 Checkpoint 3: idle ~364MiB, puncak beban ~387MiB). TAPI Oracle **diam-diam memotong kuota ini separuh** (dari 4 OCPU/24GB) pertengahan Juni 2026 TANPA pengumuman resmi -- pengguna baru tahu setelah instance mereka mati sendiri; instance yang melebihi kuota baru SEDANG dihapus otomatis (per artikel InfoQ Juli 2026, proses berjalan sekitar 18 Agustus 2026). Risiko tambahan: Oracle Always Free berbasis ARM, sedangkan image Docker proyek ini dibangun x86_64 -- kompatibilitas arm64 (lightgbm/xgboost/dst) belum pernah diverifikasi.

**Keputusan untuk sekarang:** Pakai (a) Docker Desktop Kubernetes lokal (lihat `milestones/3.3-deployment-kubernetes/decisions.md` Keputusan #1, dan `docs/keterbatasan-diterima.md` KD-2 untuk penjelasan lengkap kenapa ini diterima).

**Kenapa belum diputuskan permanen sekarang:** (1) Tujuan asli user tidak bergantung pilihan ini (sudah terpenuhi M2.9); (2) real-time API belum punya pemanggil eksternal nyata yang butuh uptime 24/7 -- investasi hosting always-on belum punya manfaat konkret; (3) opsi termurah (Oracle Cloud) punya riwayat ketidakstabilan kuota yang baru saja terjadi, butuh waktu untuk terbukti stabil kembali sebelum dipercaya untuk kebutuhan produksi; (4) kompleksitas tambahan (setup VM, jaringan/firewall, verifikasi ulang image arm64) untuk user yang mengaku belum familiar Kubernetes tidak sepadan tanpa kebutuhan konkret sekarang.

**Pemicu peninjauan:** (a) Ada kebutuhan konkret real-time API diakses pemanggil eksternal sungguhan (bukan portofolio/demo semata) -- ATAU (b) kondisi kuota Always Free Oracle Cloud (atau alternatif setara) terbukti stabil kembali dalam jangka waktu wajar (mis. tidak ada perubahan mendadak lagi selama beberapa bulan) -- ATAU (c) user secara eksplisit ingin evaluasi ulang meski belum ada pemicu (a)/(b).

**Opsi yang sudah dieksplorasi (bukan keputusan final, referensi untuk peninjauan nanti):** VPS gratis (Oracle Cloud Always Free + k3s) -- opsi termurah teridentifikasi; cloud-managed K8s berbayar (GKE/EKS/AKS) -- lebih stabil/matang tapi biaya berkelanjutan tanpa kebutuhan konkret saat ini.

**Referensi riset:** [Oracle Quietly Halves Free Tier Ampere A1 Compute Limits — InfoQ](https://www.infoq.com/news/2026/07/oracle-cloud-free-tier-limits/), [Always Free Resources — Oracle Docs](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm).

---

## KT-9 — Cakupan monitoring drift untuk jalur real-time API (belum dibangun)

**Muncul saat:** Milestone 3.6, sebelum plan ditulis (`AskUserQuestion` ke user, setelah opsi "batch saja" vs "kedua jalur sekarang" disajikan dengan trade-off).

**Konteks:** Output Milestone 3.6 (`mlops-03-deployment-observability.md` baris 139-142) minta pemantauan distribusi fitur input dan output prediksi "dari kedua jalur -- batch dan real-time". Real-time API (M3.2-3.4) TIDAK menyimpan payload request/hasil prediksi ke mana pun (cuma dikembalikan di response HTTP lalu hilang) -- beda dari jalur batch yang punya `predictions.batch_predictions` (M2.5/M2.9) sebagai sumber data historis siap pakai. Menambah cakupan real-time berarti menambah persistence baru (tabel + write path) ke `src/churn_prediction/api/app.py`, murni untuk kebutuhan monitoring, belum ada pemanggil eksternal nyata yang butuh datanya.

**Keputusan untuk sekarang:** M3.6 dibangun HANYA untuk jalur batch — `telco_customers_source` (baseline data training, byte-identik dikonfirmasi `notebook-audit.md` Bagian H.2) dibandingkan `telco_customers_synthetic` (data "sekarang") untuk input, `predictions.batch_predictions` untuk output. Lihat `milestones/3.6-monitoring-drift-kualitas-model/decisions.md` Keputusan #2.

**Kenapa belum diputuskan sekarang:** (1) Konsisten pola yang SUDAH established di KT-5 (verdict latensi real-time API), KT-7 (parity CI penuh terhadap real-time API), dan KT-8 (deployment always-on real-time API) — SEMUA menunda pekerjaan spesifik-real-time sampai ada pemanggil eksternal nyata, alasan yang sama persis berlaku di sini; (2) trafik yang ADA terhadap real-time API sejauh ini murni verifikasi manual (M3.2-3.5, puluhan-ratusan request per sesi test) — drift monitoring atas sample sekecil dan tidak representatif ini tidak bermakna, cuma akan menghasilkan noise atau kesimpulan "tidak ada drift" yang menyesatkan (bukan karena benar-benar tidak ada drift, tapi karena tidak ada trafik produksi nyata untuk diukur); (3) menambah write path baru ke `/predict` (request handler yang sudah teruji ketat sejak M3.2-3.4) demi kebutuhan monitoring yang belum ada konsumennya adalah risiko yang tidak sepadan sekarang.

**Pemicu peninjauan:** Real-time API punya pemanggil eksternal nyata (bukan portofolio/demo/verifikasi manual semata) — trigger yang SAMA dengan KT-5/7/8, konsisten satu payung kondisi "real-time API mulai dipakai sungguhan".

**Referensi:** `milestones/3.6-monitoring-drift-kualitas-model/decisions.md` Keputusan #2, `docs/keputusan-tertunda.md` KT-5/KT-7/KT-8 (pola sama).

---

## KT-10 — Tujuan akhir webhook notifikasi retraining (web chat simulasi tim, di luar cakupan proyek)

**Muncul saat:** Milestone 3.7, sebelum plan ditulis (`AskUserQuestion` dua putaran ke user).

**Konteks:** Milestone 3.7 minta jalur notifikasi konkret ke "tim Data Scientist" saat drift (M3.6) melewati ambang batas (Bagian 5.3 dokumen arsitektur, forced). User menyampaikan sedang membangun **web chat terpisah** (satu layar bisa menampilkan banyak "posisi"/peran, simulasi tim) yang akan jadi tujuan akhir notifikasi ini — TAPI web chat itu sendiri **di luar cakupan proyek `deployment-mlops` ini** (proyek frontend terpisah, belum dibangun saat M3.7 dikerjakan).

**Keputusan untuk sekarang:** Contact point webhook Grafana (`infra/k8s/monitoring/grafana-alerting-configmap.yaml`) diarahkan ke [webhook.site](https://webhook.site) (endpoint uji sementara, gratis, tanpa login) — dipakai HANYA untuk memverifikasi mekanisme end-to-end (KK1 M3.7, lihat `milestones/3.7-jalur-notifikasi-retraining/logs.md`), BUKAN tujuan produksi. URL dikonfigurasi lewat Secret K8s (`DRIFT_NOTIFICATION_WEBHOOK_URL`, `$__env{}` templating di provisioning YAML) — sengaja TIDAK hardcode ke file yang dicommit, supaya mengganti tujuan URL nanti (ke API web chat asli) cukup 1 `kubectl patch` + restart Grafana, tanpa ubah kode/manifest.

**Kenapa belum diputuskan sekarang:** Web chat tujuan akhir belum dibangun (proyek terpisah, timeline di luar kendali/kendali proyek ini) — mengarahkan webhook ke sana sekarang tidak mungkin secara teknis (URL/endpoint belum ada). Payload webhook Grafana (JSON generik, `alerts[]` dengan `labels`/`annotations`/`status`/`startsAt`/`endsAt`) sudah didesain generik dan terdokumentasi (`milestones/3.7-.../decisions.md`) supaya siap dikonsumsi begitu web chat punya endpoint penerima.

**Pemicu peninjauan:** Web chat user selesai dibangun dan punya endpoint/API yang bisa menerima webhook — saat itu, cukup ganti nilai `DRIFT_NOTIFICATION_WEBHOOK_URL` di Secret `monitoring-secrets` (namespace `monitoring`) ke URL endpoint web chat yang sesungguhnya, verifikasi ulang KK1 M3.7 terhadap tujuan baru.

**Referensi:** `milestones/3.7-jalur-notifikasi-retraining/decisions.md`, `infra/k8s/monitoring/grafana-alerting-configmap.yaml`.
