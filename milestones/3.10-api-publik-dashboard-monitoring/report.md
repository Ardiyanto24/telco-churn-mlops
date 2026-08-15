# Report — Milestone 3.10: API Publik dan Dashboard Monitoring Publik

## Ringkasan

Milestone 3.10 SELESAI — realisasi penuh Bagian 8.3 dokumen arsitektur ("Dua Dashboard, Satu Sumber Data Monitoring"). API publik read-only (`telco-churn-public-api`, Cloudflare Worker + Hyperdrive) dan dashboard web custom (`telco-churn-public-dashboard`, Next.js di Vercel) kini live di internet publik, keduanya membaca `monitoring.metrics_snapshot` (M3.9) lewat role Postgres `monitoring_public_reader` yang TERPISAH dari kredensial internal.

Berbeda dari real-time inference API (M3.3, KD-2 — sengaja lokal karena teks sumbernya sendiri mengizinkan "lingkungan uji"), M3.10 secara eksplisit menuntut aksesibilitas publik sungguhan — riset nyata (WebSearch) mengonfirmasi API publik ini (murni baca Postgres, tanpa model ML) layak dihosting always-on gratis, dan Cloudflare Workers dipilih atas Supabase PostgREST karena satu alasan konkret: Rate Limiting API binding native yang langsung memenuhi KK4, sementara PostgREST TERBUKTI (pengakuan GitHub discussion resmi Supabase) tidak punya kapabilitas itu.

**Dua repo baru dibuat** (`public-api/`, `public-dashboard/`, keduanya subfolder `deployment-mlops` tapi git independen+gitignored, sesuai keputusan eksplisit user) — kode aktual TIDAK hidup di `deployment-mlops`, tapi dokumentasi keputusan/riwayat/hasil TETAP di sini sebagai satu-satunya sumber kebenaran MLOps proyek ini.

## Kriteria Keberhasilan vs Bukti

| KK | Kriteria | Bukti |
|---|---|---|
| **KK1** | "Endpoint API dapat diakses publik (tanpa login) dan mengembalikan data yang konsisten dengan tabel monitoring di PostgreSQL." | `https://telco-churn-public-api.telco-churn-ardiyanto.workers.dev` dan `https://public-dashboard-puce.vercel.app` -- KEDUANYA diverifikasi reachable dari luar. API: `curl` -> `{"status":"ok","db":{"ok":1}}` HTTP 200 dari URL publik asli (bukan localhost). Dashboard: diakses via `Claude_Browser` tool sungguhan (bukan asumsi), `get_page_text` mengonfirmasi ketiga section render dengan data nyata TANPA login/VPN/kredensial apa pun. |
| **KK2** | "Kredensial API publik terbukti TIDAK BISA mengakses tabel di luar whitelist monitoring." | Role `monitoring_public_reader` diverifikasi POSITIF+NEGATIF terhadap Supabase sungguhan (SELECT `monitoring.metrics_snapshot` berhasil; 7 target lain -- `predictions`/`quality`/`drift`/`public`/`mlflow` -- DITOLAK; INSERT ke tabel yang boleh dibaca pun DITOLAK). Audit kode + uji coba negatif LIVE terhadap API (injeksi SQL via parameter `minutes`, path traversal) -- semua aman, tidak ada jalur eksploitasi. Pertahanan berlapis: bahkan kalau ada bug aplikasi, role DB sendiri fisik terbatas ke 1 tabel. |
| **KK3** | "Dashboard publik dan dashboard internal (Grafana), dibandingkan berdampingan untuk periode yang sama, menunjukkan data yang konsisten." | 5 titik data dibandingkan LANGSUNG (SQL Grafana vs response dashboard publik, periode sama): verdict gerbang kualitas 5 source_table, jumlah fitur STOP, jumlah fitur FLAG, status run terakhir, durasi run terakhir -- **SEMUA cocok persis**. Konsisten by design (tabel sumber sama, kredensial berbeda). |
| **KK4** | "Rate limiting per IP pada API publik terbukti aktif saat diuji coba terkontrol." | 80 request nyata dari 1 IP ke `/api/health` -> 61 sukses (200), 19 kena 429 (body terstruktur `{"error":"rate_limited",...}`). Ditunggu 65 detik (lewat window 60 detik) -> request berhasil lagi (200) -- membuktikan mekanisme window waktu genuine, BUKAN blokir permanen. |

## Keputusan Final

Lihat [`decisions.md`](./decisions.md) -- kesepakatan hosting (riset nyata, Cloudflare dipilih atas Supabase PostgREST karena satu alasan konkret: rate limiting native), cakupan konten (3 pilar penuh, keputusan user), struktur 2 repo terpisah, 8 keputusan teknis turunan termasuk temuan IPv6-only Supabase direct connection yang sukses diverifikasi lewat deployment sungguhan.

## Perubahan dari Plan Awal

Tidak ada penyimpangan pada scope -- seluruh 9 checkpoint diselesaikan sesuai urutan plan yang disetujui, TAPI beberapa kendala teknis tak terduga ditemukan+dipecahkan di tempat (bukan ditunda):

1. **`create-cloudflare`/`create-next-app` dengan flag `--git` TIDAK membuat repo independen** ketika dijalankan di dalam repo `deployment-mlops` yang sudah ada -- diperbaiki manual (`git init` eksplisit) di KEDUA repo baru, dikonfirmasi independen sebelum commit pertama.
2. **`db.<project-ref>.supabase.co` (direct connection Hyperdrive) ternyata IPv6-only** -- tidak bisa diverifikasi dari mesin lokal sama sekali, keputusan diambil untuk tetap lanjut berdasar hipotesis (jaringan Cloudflare native IPv6) dan diverifikasi lewat deployment sungguhan -- hipotesis TERBUKTI BENAR, fallback pooler yang diantisipasi plan TIDAK diperlukan.
3. **`wrangler deploy` pertama gagal** -- account belum pernah punya subdomain `workers.dev`, tidak ada opsi CLI non-interaktif -- diselesaikan via Cloudflare API langsung (`PUT /accounts/{id}/workers/subdomain`).
4. **`JSON.stringify(NaN) === null`** -- endpoint `/api/metrics/infra` sempat menampilkan `value:null` utk latency saat tidak ada trafik `/predict` terkini (Prometheus `histogram_quantile()` legitimately NaN) -- diinvestigasi tuntas, dikonfirmasi BUKAN bug (perilaku JS standar + data asli memang NaN bukan NULL), diverifikasi ulang dengan trafik segar menghasilkan nilai numerik benar.
5. **`vi.restoreAllMocks()` di test ternyata ikut me-reset mock modul `pg.Client`** (bukan cuma spy yang dimaksud) -- diperbaiki dengan cleanup yang lebih terarah (`mockRestore()` per-spy, bukan blanket restore).

## Keterbatasan dan Item Terbuka

- **Rate limit 60/menit adalah angka PROVISIONAL** (belum ada SLA formal/pola trafik nyata) -- pola sama threshold lain proyek ini, bisa disesuaikan kalau trafik nyata muncul.
- **Kode `public-api/`/`public-dashboard/` TIDAK ter-track di repo `deployment-mlops`** -- keputusan sadar user (2 repo terpisah), tapi berarti riwayat git detail komponen ini (commit-per-commit) TIDAK terlihat dari `deployment-mlops` -- hanya ringkasan di `logs.md`/`decisions.md` milestone ini. `CLAUDE.md` (lokal) diupdate eksplisit dengan lokasi+struktur supaya sesi mendatang tidak kebingungan.
- **Kedua repo baru BELUM punya remote GitHub** (keputusan eksplisit user -- git init lokal dulu, push/remote menyusul instruksi terpisah).
- **TypeScript adalah stack baru khusus komponen ini** -- satu-satunya bagian proyek yang bukan Python, konsekuensi diterima sadar dari pemilihan Cloudflare Workers.
- **Dashboard publik tidak punya halaman "penjelasan"/dokumentasi kontekstual** (mis. apa itu PSI, apa arti verdict) -- murni menampilkan angka mentah mirror dashboard internal, sesuai scope "cakupan sama dengan dashboard internal" yang diminta user, tidak ditambah fitur di luar itu.
- **Tidak ada monitoring/alerting untuk API publik dan dashboard publik itu sendiri** -- kalau Worker/Vercel deployment down, tidak ada notifikasi otomatis (beda dari komponen internal yang sudah punya alerting M3.7/M3.8). Di luar cakupan eksplisit M3.10.

## Follow-up

- M3.11 (Rollback Deployment dan Resource Sizing): fokus pada Kubernetes internal (real-time API M3.2-3.4) -- TIDAK otomatis mencakup `public-api`/`public-dashboard` (platform berbeda, Cloudflare Workers/Vercel punya mekanisme rollback native sendiri via `wrangler rollback`/Vercel deployment history, belum dieksplorasi di milestone ini).
- Kalau kebutuhan nyata muncul: remote GitHub untuk `public-api`/`public-dashboard`, monitoring/alerting utk komponen ini sendiri, penyesuaian rate limit berdasar trafik nyata.
- M3.12 (Runbook Operasional): perlu merujuk balik skenario "dashboard/API publik bermasalah" ke milestone ini.
