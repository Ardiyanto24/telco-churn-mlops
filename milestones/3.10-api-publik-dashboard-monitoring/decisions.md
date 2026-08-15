# Decisions — Milestone 3.10: API Publik dan Dashboard Monitoring Publik

## Konteks

`docs/02-implementation-plan/mlops-03-deployment-observability.md` baris 207-226, forced oleh Bagian 8.3 dokumen arsitektur: sistem butuh API read-only publik yang membaca `monitoring.metrics_snapshot` (M3.9) dengan scope dibatasi ketat, plus dashboard web custom yang mengonsumsinya — ditujukan portofolio, dapat diakses siapa pun tanpa login. Beda dari real-time API internal (M3.3, KD-2 — sengaja lokal saja karena teks sumbernya sendiri mengizinkan "lingkungan uji"), M3.10 eksplisit menuntut aksesibilitas publik sungguhan tanpa pengecualian semacam itu.

## Kesepakatan User (2 putaran `AskUserQuestion`, termasuk riset web nyata di antara keduanya)

**Putaran 1:**
1. Hosting genuinely public/cloud (BUKAN lokal K8s pola KD-2) — API publik ini cuma baca Postgres, tanpa model ML berat, jadi always-on cloud gratis genuinely layak.
2. Cakupan konten publik: SEMUA 3 pilar (Real-Time API, Pipeline Batch Health, Data & Model Drift) — user eksplisit: "dashboard internal dan dashboard eksternal sebenarnya menampilkan hal yang sama".

**Riset (WebSearch, sebelum putaran 2)**: Cloudflare Workers Free (100rb request/hari) + Hyperdrive Free (100rb query/hari) + Rate Limiting API binding NATIVE gratis vs Supabase PostgREST auto-API yang TERKONFIRMASI (GitHub discussion resmi Supabase) TIDAK punya rate limiting bawaan.

**Putaran 2:**
3. Platform backend: Cloudflare Workers + Hyperdrive (konsekuensi diterima sadar: TypeScript, satu-satunya komponen proyek ini beda bahasa dari Python).
4. Platform frontend: Next.js, deploy Vercel (BUKAN Cloudflare Pages yang direkomendasikan — pilihan user sendiri).
5. Struktur: 2 repo BARU (`public-api/`, `public-dashboard/`) sebagai subfolder `deployment-mlops` tapi git terpisah+gitignored.
6. Remote GitHub: git init lokal dulu saja, push/remote menyusul instruksi terpisah.

## Keputusan Teknis

### 1. Role Postgres BARU `monitoring_public_reader` (terpisah dari M3.9)

**Keputusan:** Role baru, scope SELECT-only `monitoring.metrics_snapshot` SAJA — identik scope `monitoring_metrics_reader` (M3.9) tapi kredensial FISIK terpisah.

**Kenapa:** Forced eksplisit teks sumber M3.10 ("Role/kredensial PostgreSQL khusus untuk API ini... bukan memakai kredensial yang sama dengan mekanisme internal Milestone 3.9"). Komponen paling terekspos di seluruh proyek (API publik tanpa autentikasi apa pun) — blast radius kredensial harus paling sempit dan bisa dicabut independen tanpa mematikan datasource Grafana internal.

**Diverifikasi nyata (positif+negatif)** terhadap Supabase sungguhan: SELECT `monitoring.metrics_snapshot` berhasil; 7 target di luar whitelist (predictions/quality/drift/public/mlflow) DITOLAK; INSERT ke tabel yang boleh dibaca pun DITOLAK.

**Tidak ada alternatif dipertimbangkan** — forced by teks sumber, bukan pilihan desain.

### 2. Cloudflare Workers + Hyperdrive dipilih ketimbang Supabase PostgREST

**Keputusan:** Backend API publik dibangun sebagai Cloudflare Worker (TypeScript), membaca Postgres lewat Hyperdrive binding.

**Kenapa:** Riset nyata (bukan asumsi) mengonfirmasi Cloudflare Workers punya Rate Limiting API binding NATIVE gratis yang LANGSUNG memenuhi KK4 tanpa kode custom kompleks — Supabase PostgREST (auto-API zero-kode, alternatif yang lebih sederhana dari sisi bahasa/konsistensi Python) TERBUKTI tidak punya rate limiting bawaan (celah fitur yang diakui Supabase sendiri di GitHub discussion resmi mereka), butuh workaround manual (proxy tambahan/function Postgres custom) yang justru menambah kompleksitas infrastruktur.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Supabase PostgREST auto-API** — DITOLAK: gap rate limiting adalah blocker langsung terhadap KK4 M3.10 yang eksplisit, workaround manual lebih kompleks daripada mengadopsi platform lain yang sudah punya kapabilitas itu native.
- **Kubernetes lokal (pola KD-2)** — DITOLAK user secara eksplisit: bertentangan dengan intent literal M3.10 ("diakses publik tanpa login" — bukan "lingkungan uji" seperti izin eksplisit M3.3), dan API ini cukup ringan (tanpa ML) sehingga tidak ada alasan teknis kuat untuk membatasi diri ke hosting lokal seperti real-time inference API.
- **VPS/serverless lain (Vercel Functions, Render, Railway)** — TIDAK diriset detail karena Cloudflare Workers sudah memenuhi seluruh kebutuhan (gratis, rate limiting native, Hyperdrive siap pakai utk Postgres existing) tanpa perlu perbandingan lebih jauh.

### 3. Koneksi Hyperdrive->Supabase pakai DIREK (bukan pooler), ternyata IPv6-only

**Keputusan:** Connection string Hyperdrive pakai `db.<project-ref>.supabase.co:5432` (direct), BUKAN `aws-0-....pooler.supabase.com` yang dipakai SEMUA role lain proyek ini.

**Kenapa:** Rekomendasi resmi dokumentasi Cloudflare Hyperdrive+Supabase (`WebFetch` langsung ke halaman docs) — Hyperdrive sendiri sudah jadi connection pooler, menumpuk pooler Supabase di atasnya kontraproduktif.

**Temuan teknis signifikan (ditemukan saat implementasi, bukan diantisipasi di plan)**: `nslookup db.jabqxkitslnlqxiiarmb.supabase.co` mengonfirmasi host ini **IPv6-only** (hanya AAAA record, TIDAK ADA A/IPv4 record) — koneksi psycopg2 LANGSUNG dari mesin lokal GAGAL total (`could not translate host name`), TIDAK BISA diverifikasi dari mesin lokal sama sekali. Keputusan diambil untuk tetap lanjut (hipotesis: Cloudflare punya jaringan IPv6 native) dan memverifikasi lewat deployment sungguhan. **Hipotesis TERBUKTI BENAR** — `wrangler deploy` + `curl` dari luar mengonfirmasi `{"status":"ok","db":{"ok":1}}`, koneksi Hyperdrive->Supabase IPv6-only BEKERJA dari jaringan Cloudflare.

**Opsi yang Dipertimbangkan tapi Ditolak (fallback yang TIDAK JADI dipakai):** Connection string pooler (IPv4, sudah terbukti reachable dari mana saja) — DITOLAK karena tidak diperlukan (direct connection terbukti bekerja), tapi tetap didokumentasikan sebagai fallback yang sudah dipertimbangkan sejak plan kalau IPv6-only ternyata tidak reachable dari Cloudflare juga.

### 4. Kontrak API: reshape di TypeScript, bukan SQL JOIN/DISTINCT ON kompleks

**Keputusan:** `src/db.ts` cuma 2 query generik (`fetchLatest`/`fetchHistory`, `DISTINCT ON (metric_name, labels)`) — reshape ke bentuk JSON per pilar dilakukan di `src/routes.ts` (TypeScript), BUKAN mereplikasi SQL 3-way JOIN yang dipakai panel drift Grafana (M3.9 Checkpoint 8).

**Kenapa:** API JSON adalah konsumen yang berbeda dari panel SQL Grafana (yang butuh output tabular langsung siap tampil) — untuk konsumen JSON, reshape di kode aplikasi lebih natural dan mudah dibaca daripada SQL kompleks. Query PromQL/metric_name yang dipakai tetap PERSIS sama dengan `metrics_aggregator.py` (M3.9) supaya data yang direpresentasikan tetap konsisten sumbernya.

**Tidak ada alternatif dipertimbangkan secara eksplisit** — pilihan teknis natural mengikuti bentuk konsumen data (JSON API vs SQL panel), bukan trade-off yang perlu opsi lain.

### 5. CORS terbuka (`Access-Control-Allow-Origin: *`)

**Keputusan:** Seluruh endpoint mengizinkan origin apa pun.

**Kenapa:** API publik read-only tanpa autentikasi/kredensial apa pun yang bisa disalahgunakan lintas-origin — beda dari API berkredensial yang butuh allowlist ketat. Membatasi origin tidak menambah keamanan nyata di sini (siapa pun tetap bisa memanggil API langsung via curl/script, bukan cuma browser), cuma akan mempersulit dashboard publik (Vercel, domain berbeda dari Worker) tanpa manfaat.

**Tidak ada alternatif dipertimbangkan** — forced by sifat "publik tanpa login" API ini sendiri.

### 6. Rate limit: 60 request/menit per IP (native Cloudflare binding)

**Keputusan:** `simple.limit=60`, `simple.period=60` (detik) — `period` WAJIB 10 atau 60 (batasan platform Cloudflare, bukan pilihan bebas), kunci `CF-Connecting-IP`.

**Kenapa:** 60/menit PROVISIONAL (belum ada SLA formal/pola trafik nyata) — cukup longgar utk dashboard polling wajar (refresh 30 detik = 2 req/menit per pengunjung x beberapa endpoint), cukup ketat mencegah scraping agresif. `CF-Connecting-IP` dipilih (bukan header lain) karena ini IP klien ASLI di belakang proxy Cloudflare, tidak bisa dipalsukan lewat header request biasa.

**Diverifikasi NYATA (uji coba terkontrol sungguhan)**: 80 request cepat ke `/api/health` dari 1 IP -> 61 berhasil (200), 19 kena 429 (body terstruktur). Ditunggu 65 detik (lewat window) -> request berhasil lagi (200) -- membuktikan window waktu genuine, bukan blokir permanen.

**Tidak ada alternatif dipertimbangkan untuk angka ambang batas** — provisional, pola sama threshold lain proyek ini (mis. `repeat_interval` M3.7/M3.8) yang tidak melalui `AskUserQuestion` terpisah.

### 7. Dashboard publik: client-side polling 30 detik (bukan server-side render sekali)

**Keputusan:** `useLivePoll` hook (client component, `setInterval` 30 detik) untuk ketiga section, `fetch(..., {cache:"no-store"})` di setiap panggilan.

**Kenapa:** Selaras `refresh:"30s"` dashboard internal Grafana (M3.5) -- dashboard publik terasa "hidup" (update otomatis tanpa reload halaman) sama seperti internal, konsisten prinsip "bukan data basi" yang berulang di proyek ini (M3.9 KK1/KK3).

**Tidak ada alternatif dipertimbangkan secara eksplisit** -- turunan langsung dari keinginan menyamai perilaku dashboard internal yang sudah established.

### 8. `workers.dev` subdomain diregistrasi via Cloudflare API langsung (bukan CLI interaktif)

**Konteks (insiden teknis, bukan keputusan desain):** `wrangler deploy` pertama GAGAL -- account belum pernah punya subdomain `workers.dev` terdaftar (wajib sekali per akun), wrangler menawarkan prompt interaktif yang fallback ke "no" di context non-interaktif, tanpa command CLI alternatif.

**Solusi:** `PUT /accounts/{id}/workers/subdomain` langsung via Cloudflare API (pakai OAuth token yang sudah tersimpan dari `wrangler login`), subdomain `telco-churn-ardiyanto` dipilih. Ini operasi satu-kali per akun, tidak sensitif (nama subdomain gampang diganti lewat dashboard kalau perlu), risiko rendah.

**Tidak ada alternatif dipertimbangkan** -- satu-satunya jalan non-interaktif yang tersedia untuk operasi account-level ini.

## Kriteria Keberhasilan vs Bukti

**KK1** ("Endpoint API dapat diakses publik dan mengembalikan data konsisten dengan tabel monitoring PostgreSQL"): `https://telco-churn-public-api.telco-churn-ardiyanto.workers.dev` dan `https://public-dashboard-puce.vercel.app` -- keduanya diverifikasi reachable dari luar (curl + browser sungguhan via `Claude_Browser` tool), data cocok Postgres. Lihat `logs.md` Checkpoint 2-3, 7-8.

**KK2** ("Kredensial API publik terbukti tidak bisa mengakses tabel di luar whitelist"): role `monitoring_public_reader` diverifikasi positif+negatif (Checkpoint 1) + audit kode+uji coba negatif live (Checkpoint 5, injeksi SQL via parameter + path traversal, semua aman). Lihat `logs.md` Checkpoint 1, 5.

**KK3** ("Dashboard publik dan internal, dibandingkan berdampingan periode sama, menunjukkan data konsisten"): 5 titik data dibandingkan LANGSUNG (verdict gerbang kualitas x5 source_table, stop/flag count, status/durasi run) -- SEMUA cocok persis. Lihat `logs.md` Checkpoint 8.

**KK4** ("Rate limiting per IP terbukti aktif saat diuji coba terkontrol"): 80 request nyata -> 61 sukses/19 kena 429, window reset dikonfirmasi. Lihat `logs.md` Checkpoint 4.
