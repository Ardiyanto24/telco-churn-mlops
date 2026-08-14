# Logs — Milestone 3.3: Deployment ke Kubernetes

## Pra-Checkpoint — Klarifikasi target Kubernetes

`docker desktop kubernetes status` awal sesi → `State: disabled`. `docker desktop enable --help`/`docker desktop kubernetes --help` dicek — tidak ada jalur CLI untuk mengaktifkan (cuma `images`/`reset-cluster`/`status`), sehingga aktivasi WAJIB lewat Settings GUI (USER ACTION).

Riset web (`WebSearch`+`WebFetch`) Oracle Cloud Always Free:
- Kuota saat ini: 2 OCPU + 12GB RAM (VM.Standard.A1.Flex, ARM Ampere).
- Oracle memotong kuota dari 4 OCPU/24GB ke 2 OCPU/12GB efektif 15 Juni 2026, TANPA pengumuman resmi (blog/email) — pengguna baru tahu setelah instance dimatikan otomatis.
- Instance melebihi kuota baru sedang dihapus otomatis (~18 Agustus 2026, dekat tanggal sesi ini).
- Sumber: [InfoQ](https://www.infoq.com/news/2026/07/oracle-cloud-free-tier-limits/), [Oracle Docs Always Free Resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm).

User dikonfirmasi (`AskUserQuestion` dua putaran): pakai Docker Desktop Kubernetes lokal, catat opsi always-on sebagai KT + KD.

## Checkpoint 1 — Health check endpoints

`pytest tests/api/ -v` → 11/11 lulus (5 test baru: `/healthz` selalu 200 termasuk saat model gagal dimuat; `/readyz` 200 golden path + 503 mock startup gagal).

`pytest tests/ -q` penuh → `197 passed, 359 warnings in 208.07s`. Regresi nol.

**Commit:** `eb7b1ec` — `feat(milestone-3.3): checkpoint 1 - health check endpoints /healthz dan /readyz`

## Checkpoint 2 — Manifest K8s, deploy, verifikasi KK1+KK2

**Aktivasi Kubernetes** (user action) dikonfirmasi via `docker desktop kubernetes status`:
```
State:              running
Started At:         2026-08-14 09:13:12...
```
`kubectl get nodes` → `docker-desktop   Ready   control-plane   ...`, context otomatis `docker-desktop`.

**Build image:** `docker build -t churn-inference:m3.3 .` — sukses.

**Deploy:**
```
kubectl create namespace churn-prediction  # via dry-run|apply
kubectl create secret generic churn-api-secrets -n churn-prediction --from-literal=... # via dry-run|apply, nilai dari .env, tidak dicetak
kubectl apply -f infra/k8s/deployment.yaml -f infra/k8s/service.yaml
```
→ `deployment.apps/churn-api created`, `service/churn-api created`.

**Status awal:** `kubectl get pods -n churn-prediction` → `0/1 Running` (masih startup). `kubectl get svc` → `EXTERNAL-IP: localhost`, `80:31477/TCP` — LoadBalancer Docker Desktop bekerja bersih TANPA tooling tambahan, dikonfirmasi empiris (Keputusan #7).

**Setelah startup selesai** (~50 detik total termasuk model load): `kubectl get pods` → `1/1 Running`. Log pod: `Application startup complete`, lalu probe `GET /healthz 200`, `GET /readyz 200` tercatat.

**Verifikasi akses dari luar cluster:**
```
curl http://localhost/healthz  -> {"status":"ok"}
curl http://localhost/readyz   -> {"status":"ready","model_version":1}
curl -X POST http://localhost/predict -d '{...}' -> {"churn_probability":0.039...,"churn_label":0,"model_version":"1","predicted_at":"..."}
```

**Verifikasi KK1 (parity):**
```
python scripts/api_parity_check.py --api-url http://localhost --limit 20
Versi champion aktif saat ini: 1
Ground truth: 20 baris (model_version=1)
churn_probability allclose(rtol=1e-6): True (diff maksimum: 4.440892098500626e-16)
churn_label exact match: True
model_version match: True
KK1+KK4 PASS: parity API real-time vs batch (M2.5) terbukti.
```
Identik dengan hasil M3.2 (`docker run` biasa) — membuktikan deployment K8s tidak mengubah perilaku.

**Uji coba terkontrol KK2 — readiness gagal nyata:**
Deployment+Service temporer (`deployment-broken-test.yaml`, scratchpad, TIDAK dicommit) dengan `MLFLOW_TRACKING_URI` sengaja rusak (`postgresql://invalid_user:wrong@host-tidak-ada.invalid:5432/postgres`).

```
kubectl apply -f deployment-broken-test.yaml
```

Event pod (`kubectl describe pod`):
```
Warning  Unhealthy  (x11 over 2m17s)  Startup probe failed: ... connect: connection refused
Warning  Unhealthy  (x6 over 27s)     Readiness probe failed: HTTP probe failed with statuscode: 503
```
`kubectl get pods` → `churn-api-broken-test-...   0/1   Running   0   2m27s` — **Running, BUKAN CrashLoopBackOff, RESTARTS: 0** (startupProbe berhasil mencegah livenessProbe membunuh pod prematur selama startup lambat legitimate).

`kubectl get endpoints`:
```
churn-api-broken-test   ENDPOINTS: (kosong)
churn-api               ENDPOINTS: 10.1.0.10:8000
```
Terbukti nyata: pod tidak sehat DIKELUARKAN dari daftar endpoint Service (trafik tidak diarahkan kesana), dibandingkan langsung dengan pod sehat.

Cleanup: `kubectl delete -f deployment-broken-test.yaml` — deployment+service temporer dihapus.

**Commit:** `1323844` — `feat(milestone-3.3): checkpoint 2 - manifest K8s dan verifikasi KK1/KK2 nyata`

## Checkpoint 3 — Resource sizing + dokumentasi penutupan

**Observasi baseline idle:**
```
docker stats --no-stream | grep churn-api
k8s_churn-api_...   0.24%   364.1MiB / 1GiB   35.56%
```

**Observasi puncak** (50 request `/predict` PARALEL, `docker stats` disampling tiap 1 detik selama burst):
```
93.33%   382.3MiB
101.84%  385.9MiB   <- puncak CPU (~1 core penuh)
0.78%    386.6MiB
0.23%    386.6MiB   <- memori stabil, tidak ada indikasi leak
```

**Angka final** (`infra/k8s/deployment.yaml`): `requests` cpu `200m`/memory `400Mi`; `limits` cpu `1500m`/memory `768Mi`.

**Re-apply + verifikasi:**
```
kubectl apply -f infra/k8s/deployment.yaml
kubectl get pods -n churn-prediction -l app=churn-api
churn-api-55bdf6dbc6-hb7h2   1/1   Running   0   51s   (pod baru, rolling update)
churn-api-56b9f46d4-clwg6    Terminating                (pod lama)
```
Resource pod baru dikonfirmasi: `{"limits":{"cpu":"1500m","memory":"768Mi"},"requests":{"cpu":"200m","memory":"400Mi"}}`.

`docs/keputusan-tertunda.md` KT-8 dan `docs/keterbatasan-diterima.md` KD-2 ditulis (instruksi eksplisit user) — kutip riset Oracle Cloud di atas.
