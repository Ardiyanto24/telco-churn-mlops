# Logs — Milestone 3.10: API Publik dan Dashboard Monitoring Publik

## Riset Sebelum Plan Ditulis

`AskUserQuestion` putaran 1: hosting genuinely public/cloud dipilih (bukan lokal K8s pola KD-2), cakupan konten publik SEMUA 3 pilar (identik dashboard internal).

Riset web nyata (`WebSearch`) sebelum putaran 2: Cloudflare Workers Free (100rb request/hari) + Hyperdrive Free (100rb query/hari, connect Postgres existing) + Rate Limiting API binding NATIVE gratis (langsung penuhi KK4) vs Supabase PostgREST auto-API yang TERKONFIRMASI (GitHub discussion resmi Supabase) TIDAK punya rate limiting bawaan.

`AskUserQuestion` putaran 2: Cloudflare Workers+Hyperdrive dipilih (konsekuensi TypeScript, stack baru khusus komponen ini). Frontend: Next.js, deploy Vercel (bukan Cloudflare Pages yang saya usulkan). Struktur: 2 repo BARU (`public-api/`, `public-dashboard/`) sebagai subfolder `deployment-mlops` tapi git terpisah+gitignored. Remote GitHub: git init lokal dulu saja, push/remote menyusul instruksi terpisah.

**Insiden kecil saat riset (bukan tindakan disengaja)**: pengecekan `wrangler whoami`/`vercel whoami` (murni cek status auth) -- `wrangler` mengonfirmasi belum login, tapi `vercel whoami` MEMICU flow OAuth device otomatis (perilaku bawaan CLI saat belum ada kredensial tersimpan) dan BERHASIL login sebagai `ardiyanto24042002-7951`. Dilaporkan transparan ke user di plan -- bukan login yang saya picu sengaja, murni efek samping command pengecekan status.

## Checkpoint 1 — Role PostgreSQL Publik (Terpisah dari M3.9)

`infra/sql/3.10_monitoring_public_role.sql` ditulis -- role `monitoring_public_reader`, SELECT-only `monitoring.metrics_snapshot` SAJA. Role TERPISAH FISIK dari `monitoring_metrics_reader` (M3.9) meski scope SELECT identik -- forced eksplisit teks sumber M3.10 ("bukan memakai kredensial yang sama dengan mekanisme internal M3.9").

Dijalankan ke Supabase (skrip scratchpad `psycopg2`, pola sama M3.9). **Verifikasi POSITIF+NEGATIF lengkap terhadap Supabase sungguhan**:
- POSITIF: `SELECT monitoring.metrics_snapshot` BERHASIL (count=6268, tabel terus bertambah dari `metrics_aggregator.py` M3.9 yang masih jalan).
- NEGATIF (7 target di luar whitelist, SEMUA ditolak `InsufficientPrivilege`): `predictions.batch_predictions`, `quality.gate_run_history`, `drift.baseline_sample`, `drift.drift_check_results`, `public.telco_customers_source`, `public.telco_customers_synthetic`, schema `mlflow`.
- NEGATIF tambahan: INSERT ke `monitoring.metrics_snapshot` (tabel yang DIA BOLEH baca) juga ditolak -- role BENAR-BENAR SELECT-only, tidak ada privilege tulis sama sekali.

Ini fondasi bukti KK2 M3.10 ("Kredensial API publik terbukti tidak bisa mengakses tabel di luar whitelist") -- role paling ketat scope-nya di seluruh proyek ini (komponen paling terekspos, tanpa autentikasi apa pun di depannya).

Kredensial (`MONITORING_PUBLIC_READER_DB_URL`, format pooler standar proyek ini) ditambahkan ke `.env` -- format DIREK Supabase (dibutuhkan Hyperdrive, Keputusan Desain #2) akan diturunkan terpisah saat konfigurasi Hyperdrive (Checkpoint 2).

**Selesai, commit:** `2cbf13f` (feat, `deployment-mlops`).

## Checkpoint 2 — Scaffold `public-api/` (Cloudflare Worker + Hyperdrive)

`.gitignore` (`deployment-mlops`) diupdate -- `public-api/`+`public-dashboard/` ditambahkan.

`wrangler login` -- flow OAuth browser BERHASIL (email `ardiyanto24042002@gmail.com`, account ID `1e67cc4290dfdca4719a4c8d9228cb31`).

`npx create-cloudflare@latest public-api --type=hello-world --lang=ts --git -y` -- scaffold berhasil. **Temuan**: flag `--git` TIDAK membuat repo independen (mendeteksi sudah di dalam repo `deployment-mlops`, tidak init `.git` baru) -- diperbaiki manual (`git init` eksplisit di dalam `public-api/`), dikonfirmasi `git status` dari dalam `public-api/` sekarang pakai `.git` sendiri (bukan `../` relatif ke `deployment-mlops`). Commit awal repo baru: `fdd1f25`.

`wrangler hyperdrive create telco-churn-public-monitoring --connection-string=...` -- config Hyperdrive dibuat (`d212ae4223bf4e9cbb1d06627aec6382`), pakai connection string DIREK Supabase (`db.jabqxkitslnlqxiiarmb.supabase.co:5432`, role `monitoring_public_reader`) sesuai rekomendasi resmi Cloudflare (`WebFetch` dokumentasi Hyperdrive+Supabase: "should use the Direct connection connection string rather than the pooled connection strings").

**Temuan teknis signifikan**: `nslookup db.jabqxkitslnlqxiiarmb.supabase.co` mengonfirmasi host ini **IPv6-only** (hanya AAAA record, TIDAK ADA A/IPv4 record) -- percobaan koneksi psycopg2 LANGSUNG dari mesin lokal GAGAL (`could not translate host name`, resolver lokal tidak reach IPv6). Ini TIDAK BISA diverifikasi dari mesin lokal sama sekali -- keputusan diambil untuk tetap lanjut (Cloudflare punya jaringan IPv6 native) dan memverifikasi lewat deployment sungguhan, bukan asumsi.

Binding `hyperdrive` ditambahkan manual ke `wrangler.jsonc` (wrangler tidak auto-tambah di context non-interaktif) + `compatibility_flags: ["nodejs_compat"]` (wajib untuk Hyperdrive). `wrangler types` dijalankan ulang. Nama Worker diubah ke `telco-churn-public-api` (konsisten penamaan plan).

`npm install pg`+`@types/pg` (driver resmi direkomendasikan Cloudflare Hyperdrive docs, bukan Supabase JS client). `npm audit` melaporkan 7 kerentanan -- SEMUA di dev-dependency tooling (`esbuild`/`miniflare`/`undici`, dipakai `wrangler dev`/`vitest-pool-workers` lokal), TIDAK ADA di `pg` driver produksi -- tidak blocking, dicatat transparan.

`GET /api/health` ditulis (`SELECT 1` via Hyperdrive binding). `wrangler deploy` PERTAMA GAGAL -- account belum pernah punya subdomain `workers.dev` terdaftar (wajib sekali per akun), tidak ada opsi CLI non-interaktif untuk ini. **Diselesaikan via Cloudflare API langsung** (`PUT /accounts/{id}/workers/subdomain`, pakai OAuth token tersimpan `wrangler login`) -- subdomain `telco-churn-ardiyanto` terdaftar. `wrangler deploy` KEDUA BERHASIL: `https://telco-churn-public-api.telco-churn-ardiyanto.workers.dev`.

**Verifikasi nyata dari luar**: `curl` PERTAMA gagal (`schannel: SEC_E_ILLEGAL_MESSAGE` -- TLS handshake, kemungkinan besar propagasi DNS/sertifikat subdomain baru belum selesai). Ditunggu 30 detik, `curl` KEDUA BERHASIL: `{"status":"ok","db":{"ok":1}}`, HTTP 200 -- **membuktikan koneksi Hyperdrive->Supabase IPv6-only BEKERJA dari jaringan Cloudflare** (fallback pooler yang diantisipasi plan TIDAK diperlukan), DAN Worker genuinely reachable dari internet publik (bukan localhost/cluster lokal) -- fondasi pertama KK1 M3.10.

**Selesai, commit `public-api`:** `fc947ab` (feat).

## Checkpoint 3 — Endpoint API Publik (3 Pilar)

`src/db.ts` (helper generik `fetchLatest`/`fetchHistory` ke `monitoring.metrics_snapshot`) + `src/routes.ts` (3 handler, mirror 3 pilar dashboard internal) ditulis SEKALIGUS (saling terkait erat, satu unit koheren) -- reshape data dilakukan di TypeScript, BUKAN SQL JOIN/DISTINCT ON kompleks seperti panel Grafana M3.9 (lebih natural untuk konsumen JSON API dibanding panel SQL langsung).

`tsc --noEmit` bersih tanpa error. 11 test vitest ditulis (`db.ts`+`pg` di-mock PENUH -- verifikasi DB/jaringan sungguhan sudah dilakukan lewat deployment live, bukan tanggung jawab unit test). **Kendala teknis ditemukan+dipecahkan**: `vitest-pool-workers` WAJIB ada local connection string utk binding Hyperdrive walau `db.ts` di-mock (inisialisasi binding terjadi SEBELUM kode test jalan) -- diperbaiki dengan dummy connection string (`postgres://fake:fake@localhost:5432/fake`, TIDAK PERNAH benar-benar dipakai) di `vitest.config.mts`. **Seluruh 11 test PASS**.

`wrangler deploy` -- ketiga endpoint diuji dari luar terhadap data Postgres NYATA. `/api/metrics/pipeline` dan `/api/metrics/drift` langsung benar. `/api/metrics/infra` awalnya menampilkan `value:null` untuk latency -- **diinvestigasi, BUKAN bug**: `JSON.stringify(NaN)` di JavaScript menghasilkan literal `null` (NaN tidak punya representasi JSON) -- nilai asli di Postgres adalah `NaN` (BUKAN SQL NULL, kolom `value` tetap `NOT NULL` sesuai skema M3.9), berasal dari `histogram_quantile()` Prometheus yang legitimately mengembalikan NaN saat tidak ada trafik `/predict` terkini dalam window `rate()` 5 menit -- diteruskan apa adanya lewat seluruh pipeline (`metrics_aggregator.py` M3.9 -> Postgres -> Worker -> JSON), BUKAN cacat baru.

**Verifikasi ulang dengan trafik segar** (reuse skrip scratchpad generator, 20 valid+5 invalid ke `/predict`, ditunggu 1 siklus poll ~65 detik): `/api/metrics/infra` sekarang mengembalikan nilai numerik NYATA -- `request_rate_per_second` (2xx=0.070/4xx=0.018), `latency_p50=0.052`/`p95=0.099`/`p99=1`, `error_rate_percent=20` -- **pola magnitude PERSIS konsisten** dengan verifikasi Grafana M3.9 Checkpoint 6 (traffic generator yang sama).

**Selesai, commit `public-api`:** `3ba90e0` (feat).

## Checkpoint 4 — Rate Limiting (KK4)

Riset spesifikasi eksak (`WebFetch` dokumentasi resmi, sesuai prinsip "retrieval over pre-training" skill `wrangler`) -- binding `ratelimits` di `wrangler.jsonc`, field `simple.limit`+`simple.period` (`period` WAJIB 10 atau 60, batasan platform bukan pilihan bebas -- 60 dipilih, pas dengan Keputusan Desain #5 plan "60 request/menit").

Middleware ditambah di `index.ts` -- diterapkan ke SELURUH endpoint (termasuk `/api/health`), kunci `CF-Connecting-IP` (IP klien asli di belakang proxy Cloudflare, tidak bisa dipalsukan lewat header request biasa). 3 test baru (spy `env.PUBLIC_API_RATE_LIMITER.limit`, jalur sukses+gagal+verifikasi key) -- **14/14 test PASS**.

`wrangler deploy` -- binding terkonfirmasi aktif (`env.PUBLIC_API_RATE_LIMITER (60 requests/60s)`).

**Verifikasi KK4 NYATA (uji coba terkontrol sungguhan, bukan simulasi)**: 80 request cepat berturut-turut ke `/api/health` dari 1 IP -- **61 berhasil (200), 19 kena 429** (body terstruktur `{"error":"rate_limited",...}`). Ditunggu 65 detik (lewat window), dicek ulang -- request BERHASIL LAGI (200), membuktikan mekanisme window waktu genuine, BUKAN blokir permanen per IP.

**Selesai, commit `public-api`:** `ad42a2a` (feat).

## Checkpoint 5 — Verifikasi Keamanan Kredensial (KK2)

Audit kode: seluruh 3 titik `client.query()` di `public-api/src/*.ts` menggunakan SQL TETAP (fixed text) + parameter bind (`$1`/`$2`, BUKAN string interpolation) -- `metricNames` SELALU salah satu dari 3 array tetap (`INFRA_METRICS`/`PIPELINE_METRICS`/`DRIFT_METRICS`), tidak pernah berasal dari input user. Parameter `minutes` (satu-satunya input user yang mengalir ke SQL) melalui `Number(...)`+`Math.trunc`+`clamp [1,360]` di `fetchHistory()` SEBELUM dipakai sebagai bind parameter -- tidak ada jalur string SQL mentah dari request ke database.

**Verifikasi NYATA (uji coba negatif langsung ke API live, bukan cuma baca kode)**:
- Percobaan "injeksi" via `?minutes=1); DROP TABLE monitoring.metrics_snapshot;--` -- `Number()` parsing gagal (NaN) -> fallback ke default 60 menit, response 200 NORMAL, TIDAK ADA error/crash/kebocoran data.
- Percobaan path traversal (`/api/metrics/../../predictions/batch_predictions`) dan tebakan nama tabel langsung sebagai path (`/predictions.batch_predictions`) -- KEDUANYA `404 not_found` (router hanya kenal 4 path tetap).

Dikombinasikan dengan verifikasi role Postgres level-database (Checkpoint 1 -- `monitoring_public_reader` SECARA FISIK tidak bisa SELECT tabel lain apa pun, terlepas dari bug aplikasi manapun), ini PERTAHANAN BERLAPIS: bahkan kalau ada celah aplikasi yang tidak ditemukan, kredensial DB sendiri sudah membatasi blast radius ke SATU tabel.

**Selesai** -- tidak ada file berubah (murni verifikasi), digabung commit checkpoint berikutnya.

## Checkpoint 6 — Scaffold `public-dashboard/` (Next.js)

`npx create-next-app@latest public-dashboard --ts --app --tailwind --eslint --disable-git --use-npm -y` -- scaffold berhasil (0 kerentanan npm audit). `--disable-git` dipakai eksplisit (belajar dari temuan `create-cloudflare` Checkpoint 2 -- scaffolder cenderung skip git init kalau mendeteksi sudah di dalam repo lain) -- `git init` manual dijalankan, dikonfirmasi independen dari `deployment-mlops`. Commit awal: `693ddb1`.

`vercel --yes` -- deploy pertama BERHASIL langsung (Vercel auto-link project baru `public-dashboard` di akun `ardiyanto24042002-7951`, target production langsung -- tidak perlu `--prod` terpisah utk deploy pertama kali). URL: `https://public-dashboard-puce.vercel.app`. **Diverifikasi reachable dari luar**: `curl` -> HTTP 200.

**Selesai, commit `public-dashboard`:** `693ddb1` (feat).

## Checkpoint 7 — Halaman Dashboard (3 Pilar, Konsumsi API Publik)

`lib/api.ts` (tipe TypeScript + fetch helper `cache:"no-store"` -- selalu data segar, konsisten prinsip "bukan data basi" M3.9), `lib/useLivePoll.ts` (hook polling 30 detik, SELARAS `refresh:"30s"` dashboard internal Grafana -- dashboard publik terasa "hidup" sama seperti internal, bukan snapshot statis).

3 komponen (`InfraSection`/`PipelineSection`/`DriftSection`) mirror PERSIS 3 row dashboard internal -- value mapping (status flow, verdict gerbang kualitas, verdict drift) pakai encoding SAMA (`2=pass/1=flag/0=stop` dst) yang konsisten dipakai seluruh `deployment-mlops` sejak M3.5-3.9. `app/page.tsx` menggabungkan ketiganya jadi satu halaman (mirror struktur dashboard internal 1-halaman-3-row).

`NEXT_PUBLIC_API_BASE_URL` diset lokal (`.env.local`, gitignored) DAN di Vercel production env (`vercel env add`). Build (`next build`) + `tsc --noEmit` BERSIH tanpa error.

`vercel --prod` -- deploy sukses ke `https://public-dashboard-puce.vercel.app`.

**Verifikasi NYATA lewat browser sungguhan** (`Claude_Browser` tool, `get_page_text` -- bukan asumsi/curl JSON mentah): KETIGA section render dengan DATA NYATA -- Pipeline Batch Health menampilkan "Completed"/"4.00 s", gerbang kualitas 5 source_table SEMUA "pass", staleness dalam format jam terbaca manusia. Data & Model Drift menampilkan **SELURUH 30 baris fitur** dengan psi/p_value/verdict -- `tenure`+`service_count` BENAR menunjukkan "stop" (cocok temuan asli M3.6), `monthly_charges`+`multiple_lines` "flag". Real-Time API menampilkan "—" utk latency (traffic generator M3.10 Checkpoint 3 sudah lewat window 5 menit lagi saat verifikasi ini -- BUKAN bug, perilaku sama seperti temuan `NaN`/null sebelumnya, endpoint SUDAH terbukti benar dgn data segar di Checkpoint 3).

Screenshot visual GAGAL diambil (`computer` tool -- "Browser pane is not displayed", keterbatasan tool yang SAMA persis ditemukan sesi M3.6/M3.9 sebelumnya) -- `get_page_text` (ekstraksi DOM sungguhan, bukan asumsi) dipakai sebagai bukti pengganti yang setara validitasnya.

**Selesai, commit `public-dashboard`:** `0aacc36` (feat).

## Checkpoint 8 — Verifikasi KK1+KK3 End-to-End

**KK1**: sudah terbukti eksplisit di Checkpoint 7 (`Claude_Browser` tool mengakses `https://public-dashboard-puce.vercel.app` -- URL publik ASLI, tanpa localhost/VPN/kredensial/login apa pun, menampilkan data nyata).

**KK3**: dashboard publik (data yang baru diambil Checkpoint 7) dibandingkan LANGSUNG dengan query SQL persis yang dipakai panel Grafana internal (`postgres-monitoring` datasource, M3.9) untuk PERIODE SAMA:
- Verdict gerbang kualitas per source_table: Grafana `{_provision_probe:2, _test_gate_70a3b9f7:2, _verification_probe_m38:2, telco_customers_source:2, telco_customers_synthetic:2}` -- **PERSIS SAMA** dgn dashboard publik (semua "pass").
- Jumlah fitur drift STOP: Grafana `2` -- **SAMA** dgn dashboard publik.
- Jumlah fitur drift FLAG: Grafana `2` -- **SAMA** dgn dashboard publik.
- Status run terakhir: Grafana `1` (Completed) -- **SAMA** dgn dashboard publik.
- Durasi run terakhir: Grafana `4.000845` -- **SAMA** dgn dashboard publik (`4.00 s`, dibulatkan tampilan).

**Konsisten by design** -- kedua dashboard membaca tabel PERSIS SAMA (`monitoring.metrics_snapshot`, M3.9) lewat jalur kredensial BERBEDA (Grafana via `monitoring_metrics_reader`/M3.9, publik via `monitoring_public_reader`/M3.10 Checkpoint 1 -> Hyperdrive) -- konsistensi ini MEMBUKTIKAN kedua role membaca data yang sama tanpa distorsi, bukan kebetulan.

**Selesai** -- tidak ada file berubah (murni verifikasi).
