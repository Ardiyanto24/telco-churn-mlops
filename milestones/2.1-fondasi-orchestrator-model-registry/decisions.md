# Decisions — Milestone 2.1: Fondasi Orchestrator dan Model Registry

## Klarifikasi Sebelum Plan Disusun

Enam pertanyaan diajukan ke user sebelum plan ditulis (`docs/01-architecture/rancangan-arsitektur-mlops-platform.md` Bagian 10 eksplisit membiarkan tool orchestrator dan konvensi versi aktif terbuka untuk pemilik pekerjaan). Satu putaran pertama (pilihan awal Airflow + Render/Railway) ternyata tidak feasible secara teknis setelah diriset — diajukan ulang dengan bukti sampai user memilih arah final:

1. **Tool orchestrator:** Dagster direkomendasikan (asset-based, cocok feature store, ringan di Windows). User memilih **Apache Airflow**.
2. **Deploy MLflow registry resmi:** direkomendasikan `mlflow server` venv terpisah + SQLite + artifact lokal. User memilih **`mlflow server` backed Supabase Postgres yang sudah ada**.
3. **Konvensi versi aktif:** direkomendasikan **Model Registry Aliases** — dipilih user langsung (sesuai rekomendasi).
4. **Klarifikasi lanjutan — scope "online":** setelah dicek, Airflow (webserver+scheduler persisten, min. 4GB RAM) tidak muat gratis-permanen di Render (background worker persisten mulai $7/bln, free tier web service tidur saat idle) maupun Railway (tidak ada free tier permanen lagi, cap 0.5GB RAM). User diberi 3 opsi (bayar kecil di Render, self-host VM always-free seperti Oracle Cloud, atau ganti orchestrator) — user memilih **ganti orchestrator ke yang lebih ringan/ramah free tier**.
5. **Orchestrator final:** direkomendasikan **Prefect Cloud (Managed work pool)** vs GitHub Actions terjadwal. User memilih **Prefect Cloud (Managed work pool)**.
6. **Akses MLflow registry:** setelah ditemukan bahwa `mlflow.set_tracking_uri()` bisa connect langsung ke Postgres tanpa proses server (pola sama M1.5), direkomendasikan **direct-access** vs hosting `mlflow server` di Render/Railway. User memilih **direct-access** (sesuai rekomendasi).

## Keputusan Teknis

### 1. Orchestrator: Prefect Cloud, Managed work pool

**Keputusan:** Job terjadwal (feature store refresh M2.3, batch scoring DAG M2.5) dijalankan lewat Prefect Cloud, memakai **Managed work pool** — Prefect yang mengeksekusi compute (bukan kita yang hosting server/worker apa pun). Kode flow disimpan di GitHub repo yang sudah ada (`github.com/Ardiyanto24/telco-churn-mlops`), dideploy dari sana ke Prefect Cloud.

**Kenapa:** Dikonfirmasi user setelah dua putaran riset membuktikan pilihan awal (Airflow di Render/Railway) tidak feasible gratis-permanen. Prefect Managed work pool genuinely gratis (10 jam compute/bulan — cukup untuk skala batch job proyek ini), 100% online (tidak ada infrastruktur yang perlu kita jaga hidup), dan tetap punya DAG/dependency graph, retry, dan UI observability run history — kebutuhan eksplisit M2.4-2.8 (gerbang kualitas data, isolasi kegagalan per task) yang tidak dipenuhi pendekatan cron polos.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Apache Airflow** (pilihan awal user) — DITOLAK setelah riset: Airflow merekomendasikan minimum 4GB RAM dan scheduler wajib jalan sebagai proses persisten 24/7 ([Astronomer: Airflow components](https://www.astronomer.io/docs/learn/airflow-components); [Airflow Scheduler docs](https://airflow.apache.org/docs/apache-airflow/2.5.3/scheduler.html)). Render: background worker persisten (tipe yang cocok untuk scheduler) mulai $7/bulan, bukan gratis; free tier web service tidur saat idle sehingga scheduler tidak bisa terus jalan. Railway: sudah tidak ada free tier permanen (hanya kredit trial $5 sekali, lalu $1/bulan cap 0.5GB RAM — jauh di bawah rekomendasi Airflow), cron job-nya juga tidak didesain untuk scheduler persisten (interval minimum 5 menit, run tidak boleh overlap).
- **Self-host Airflow di VM always-free (mis. Oracle Cloud Free Tier)** — ditawarkan sebagai jalan tengah (tetap Airflow, $0/bulan genuinely permanen, resource cukup), tapi user memilih arah lain (ganti orchestrator) — bukan ditolak karena kekurangan teknis, murni preferensi user untuk directly go dengan opsi yang lebih ringan operasionalnya (tidak perlu provisioning/kelola VM sendiri).
- **Airflow tetap dipakai dengan biaya kecil bulanan di Render (~$7-10/bln)** — jalan tengah lain yang ditawarkan, ditolak user karena tidak lagi 100% gratis, dan menyimpang dari preferensi "online tanpa biaya" yang dinyatakan user.
- **GitHub Actions terjadwal (cron workflow)** — genuinely gratis dan infra paling minim (tanpa akun/tool baru), tapi DITOLAK karena tidak ada DAG/dependency graph atau retry-per-task bawaan (harus diimplementasikan manual di script) dan tidak ada UI observability run history sebaik Prefect — kurang cocok untuk kebutuhan M2.4-2.8 yang eksplisit minta task terpisah dengan dependency jelas dan penanganan kegagalan per task.

### 2. MLflow backend store: direct-access ke Supabase Postgres, tanpa proses `mlflow server`

**Keputusan:** `MLFLOW_TRACKING_URI` diarahkan langsung ke connection string Postgres Supabase (`postgresql://...`, role least-privilege baru — lihat Keputusan #4), diakses langsung oleh tiap consumer (flow Prefect sekarang, nanti real-time API M3.x) lewat `mlflow.set_tracking_uri()` — **tanpa** proses `mlflow server` (REST API + UI) yang perlu di-hosting terus-menerus. MLflow otomatis membuat tabel registry-nya sendiri (`registered_models`, `model_versions`, dst.) di schema Postgres yang ditunjuk saat pertama dipakai (didukung `sqlalchemy`+`alembic` yang sudah ada di dependencies inti sejak M1.5).

**Kenapa:** Pola ini identik dengan mekanisme yang sudah terbukti jalan di M1.5 (`sqlite:///mlruns.db`, akses langsung tanpa server — lihat `milestones/1.5-inference-service/decisions.md` Keputusan #1/#7), tinggal ganti driver SQLAlchemy dari SQLite ke Postgres. Menghindari sepenuhnya masalah hosting server yang sama seperti yang ditemukan untuk Airflow (lihat Keputusan #1) — tidak ada proses yang perlu dijaga hidup 24/7 di platform manapun. Riset ([MLflow tracking docs](https://mlflow.org/docs/2.1.1/tracking.html); [MLflow remote tracking server](https://mlflow.org/docs/latest/ml/tracking/tutorials/remote-server/)) mengonfirmasi tracking URI berbasis SQLAlchemy (termasuk PostgreSQL) didukung langsung dari client tanpa server terpisah untuk operasi backend store (experiments, runs, model registry) — server terpisah hanya wajib kalau butuh REST API/UI terpusat, yang MEMANG bukan kebutuhan sistem ini (MLflow sengaja bukan serving layer, lihat arsitektur Bagian 5.1).

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Hosting `mlflow server` (REST API + UI) di Render/Railway, backed Supabase Postgres** (pilihan awal user di putaran pertama) — DITOLAK setelah ditemukan alternatif direct-access yang lebih sederhana: proses server yang perlu di-hosting terus-menerus akan menghadapi masalah kelayakan yang sama seperti Airflow (biaya kecil bulanan atau keterbatasan free tier), sementara manfaat tambahannya (UI web selalu hidup) relatif kecil untuk skala proyek ini — MLflow secara arsitektur memang tidak dipakai sebagai serving layer di sistem ini (Bagian 5.1 dokumen arsitektur). Browsing experiment/model tetap bisa dilakukan lewat `mlflow ui` lokal on-demand saat perlu.
- **Tetap SQLite lokal (perpanjangan pola M1.5)** — DITOLAK karena tidak bisa diakses lewat network; real-time API di Kubernetes (M3.x) nantinya tidak akan bisa menjangkaunya sama sekali, dan `milestones/1.5-inference-service/decisions.md` Keputusan #1 sendiri sudah eksplisit menyatakan setup ini "bukan setup resmi M2.1".
- **Backend Postgres terpisah/baru** (bukan reuse Supabase yang sudah ada) — tidak dipertimbangkan serius karena akan menambah datastore kedua untuk dikelola tanpa manfaat jelas; Supabase Postgres yang sudah ada cukup untuk beban metadata MLflow yang ringan, selama role least-privilege terpisah dipakai (Keputusan #4) supaya tidak melanggar prinsip isolasi beban Bagian 6.3 dokumen arsitektur.

### 3. Artifact store: Supabase Storage (S3-compatible)

**Keputusan:** File artifact model (`model_final.joblib` yang sudah dibundle jadi pyfunc model) disimpan di Supabase Storage lewat protokol S3-compatible-nya (bucket baru, mis. `mlflow-artifacts`), diakses MLflow lewat `boto3` dengan `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`MLFLOW_S3_ENDPOINT_URL` yang mengarah ke endpoint Supabase Storage.

**Kenapa:** Konsekuensi langsung Keputusan #2 — karena tidak ada proses server/container yang perlu dijaga hidup, tidak ada tempat "lokal" yang masuk akal untuk menyimpan artifact tetap accessible ke semua consumer (flow Prefect sekarang, real-time API M3.x nanti). User eksplisit menyatakan preferensi "online, sebisa mungkin tidak ada bagian yang disimpan di local". Riset ([Supabase: S3-compatible storage](https://supabase.com/blog/s3-compatible-storage); [Supabase S3 compatibility docs](https://supabase.com/docs/guides/storage/s3/compatibility)) mengonfirmasi Supabase Storage mendukung protokol S3 penuh dengan access key/secret key yang bisa di-generate dari dashboard, dan MLflow secara native mendukung artifact store S3-compatible lewat `boto3` tanpa perlu Amazon S3 sungguhan.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Local disk di container mlflow server, diakses lewat proxy HTTP server** — sempat direkomendasikan sebelum Keputusan #2 berubah ke direct-access (tanpa server sama sekali); begitu tidak ada server yang di-hosting, opsi ini otomatis tidak relevan lagi.
- **Shared Docker volume/local disk yang di-mount langsung** — DITOLAK: mengikat setiap consumer di masa depan (termasuk real-time API di Kubernetes M3.x) untuk butuh mount filesystem yang sama, tidak scale ke cluster K8s terpisah, dan bertentangan langsung dengan preferensi eksplisit user untuk tidak menyimpan apa pun secara lokal.

### 4. Kredensial least-privilege terpisah untuk MLflow

**Keputusan:** Role Postgres baru khusus dibuat untuk MLflow (mis. `mlflow_registry`), privilege di-scope hanya ke schema `mlflow` (CREATE/SELECT/INSERT/UPDATE/DELETE) — **tidak** punya akses ke `telco_customers_source`/`telco_customers_synthetic` atau tabel data mentah lain. Access key S3-compatible Supabase Storage juga baru dan terpisah, khusus untuk bucket artifact MLflow.

**Kenapa:** Forced langsung oleh prinsip arsitektur mengikat di `CLAUDE.md`: *"Rahasia tidak boleh di-hardcode atau di-commit. Gunakan kredensial least-privilege yang dipisah menurut pola akses."* Reuse `SUPABASE_DB_URL` yang sudah ada untuk MLflow akan melanggar prinsip ini secara langsung (satu kredensial dipakai untuk dua pola akses yang berbeda — baca data mentah vs baca-tulis metadata registry).

**Opsi yang Dipertimbangkan tapi Ditolak:** Tidak ada alternatif dipertimbangkan — forced by prinsip arsitektur mengikat CLAUDE.md di atas, bukan pilihan desain yang genuinely terbuka.

### 5. Konvensi versi aktif: MLflow Model Registry Aliases

**Keputusan:** "Versi aktif" model didefinisikan lewat **MLflow Model Registry Alias** — alias `champion` menunjuk ke versi `churn_prediction_model` yang dipakai batch DAG dan real-time API saat ini. Alias `challenger` dicadangkan untuk kebutuhan verifikasi-sebelum-promosi di M2.8 (perbandingan versi kandidat vs versi aktif). Dipakai lewat `MlflowClient.set_registered_model_alias()` dan `models:/{name}@{alias}`.

**Kenapa:** Dikonfirmasi user langsung sesuai rekomendasi. Aliases adalah pendekatan yang direkomendasikan MLflow saat ini; Stages (alternatif lama) berstatus deprecated dan akan dihapus di versi mendatang. Aliases juga lebih fleksibel — mendukung beberapa pointer sekaligus (`champion`/`challenger`), pas dengan kebutuhan M2.8.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Legacy Stages (Staging/Production/Archived)** — DITOLAK karena resmi dinyatakan deprecated oleh MLflow dan berisiko dihapus di versi mendatang — proyek ini idealnya merefleksikan praktik terkini, bukan pola yang sudah ditinggalkan upstream-nya sendiri.
- **Tag kustom** (mis. tag `active_version` manual di model) — DITOLAK karena menciptakan ulang mekanisme yang sudah disediakan MLflow secara native lewat Aliases, menambah kode custom untuk dijaga tanpa manfaat tambahan yang jelas.

### 6. Dokumen kontrak "model registry" baru di `docs/05-model-registry-contract/`

**Keputusan:** Konvensi penamaan model, makna alias, dan cara batch/real-time mengambil versi aktif didokumentasikan di `docs/05-model-registry-contract/model-registry-contract.md` (nomor urut `05-` mengikuti `01-architecture`/.../`04-schema-contract` yang sudah ada). `milestones/2.1-fondasi-orchestrator-model-registry/` hanya berisi `decisions.md`/`logs.md`/`report.md`.

**Kenapa:** Mengikuti preseden langsung dari `milestones/1.6-kontrak-skema-sumber-data/decisions.md` Keputusan #5 — dokumen kontrak substantif yang akan dirujuk terus-menerus oleh milestone lain (di sini: M2.2-2.8 dan terutama Orang #3/M3.x) masuk `docs/`, bukan folder milestone yang isinya cuma proses/keputusan spesifik M2.1.

**Opsi yang Dipertimbangkan tapi Ditolak:** Tidak ada alternatif dipertimbangkan — forced by preseden M1.6 Keputusan #5 di atas, konsisten dengan pola yang sudah dipakai proyek ini untuk dokumen kontrak lintas-milestone.
