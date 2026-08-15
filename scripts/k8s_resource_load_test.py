"""Milestone 3.11 -- uji beban terkontrol terhadap real-time API di Kubernetes.

Skrip existing (`api_parity_check.py`, `container_smoke_test.py`) fokus ke
korektnes/parity, bukan generate beban HTTP konkuren sustained. Skrip ini
mengirim request `/predict` konkuren pada beberapa level, sambil sampling
`kubectl top pod` paralel -- dipakai untuk resource sizing (Checkpoint 4-5)
maupun memicu scale-up HPA (Checkpoint 6). Lihat
milestones/3.11-rollback-deployment-resource-sizing/decisions.md
Keputusan #5.

Contoh pemakaian:
    python scripts/k8s_resource_load_test.py --idle-only --duration-seconds 120
    python scripts/k8s_resource_load_test.py --concurrency 50 --duration-seconds 60
"""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import requests

PAYLOAD = {
    "gender": "Male",
    "senior_citizen": 0,
    "partner": "Yes",
    "dependents": "No",
    "tenure": 29,
    "phone_service": "Yes",
    "multiple_lines": "No",
    "internet_service": "DSL",
    "online_security": "Yes",
    "online_backup": "No",
    "device_protection": "Yes",
    "tech_support": "Yes",
    "streaming_tv": "No",
    "streaming_movies": "No",
    "contract": "One year",
    "paperless_billing": "Yes",
    "payment_method": "Mailed check",
    "monthly_charges": 60.10,
    "total_charges": 1653.85,
}

_CPU_RE = re.compile(r"^(\d+)m?$")
_MEM_RE = re.compile(r"^(\d+)Mi$")


@dataclass
class RequestResult:
    timestamp: float
    status: str
    latency_ms: float


@dataclass
class ResourceSample:
    timestamp: float
    cpu_millicores: int | None
    memory_mi: int | None


def _parse_cpu(raw: str) -> int | None:
    raw = raw.strip()
    if raw.endswith("m"):
        return int(raw[:-1])
    try:
        return int(float(raw) * 1000)
    except ValueError:
        return None


def _parse_memory_mi(raw: str) -> int | None:
    raw = raw.strip()
    m = _MEM_RE.match(raw)
    if m:
        return int(m.group(1))
    if raw.endswith("Gi"):
        return int(float(raw[:-2]) * 1024)
    if raw.endswith("Ki"):
        return int(float(raw[:-2]) / 1024)
    return None


def sample_pod_resources(namespace: str, pod_name_prefix: str) -> ResourceSample | None:
    try:
        out = subprocess.run(
            ["kubectl", "top", "pod", "-n", namespace, "--no-headers"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    for line in out.strip().splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        name, cpu_raw, mem_raw = parts[0], parts[1], parts[2]
        if not name.startswith(pod_name_prefix):
            continue
        return ResourceSample(
            timestamp=time.time(),
            cpu_millicores=_parse_cpu(cpu_raw),
            memory_mi=_parse_memory_mi(mem_raw),
        )
    return None


class Sampler(threading.Thread):
    def __init__(self, namespace: str, pod_name_prefix: str, interval_seconds: float, stop_event: threading.Event):
        super().__init__(daemon=True)
        self.namespace = namespace
        self.pod_name_prefix = pod_name_prefix
        self.interval_seconds = interval_seconds
        self.stop_event = stop_event
        self.samples: list[ResourceSample] = []

    def run(self) -> None:
        while not self.stop_event.is_set():
            sample = sample_pod_resources(self.namespace, self.pod_name_prefix)
            if sample is not None:
                self.samples.append(sample)
            self.stop_event.wait(self.interval_seconds)


def request_worker(target_url: str, stop_event: threading.Event, results: list[RequestResult], lock: threading.Lock) -> None:
    while not stop_event.is_set():
        start = time.time()
        try:
            resp = requests.post(f"{target_url}/predict", json=PAYLOAD, timeout=10)
            status = str(resp.status_code)
        except requests.RequestException as exc:
            status = f"ERROR:{exc.__class__.__name__}"
        latency_ms = (time.time() - start) * 1000
        with lock:
            results.append(RequestResult(timestamp=start, status=status, latency_ms=latency_ms))


def run_level(
    concurrency: int,
    duration_seconds: float,
    target_url: str,
    namespace: str,
    pod_name_prefix: str,
    sample_interval_seconds: float,
) -> tuple[list[RequestResult], list[ResourceSample]]:
    stop_event = threading.Event()
    sampler = Sampler(namespace, pod_name_prefix, sample_interval_seconds, stop_event)
    sampler.start()

    results: list[RequestResult] = []
    lock = threading.Lock()

    if concurrency > 0:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [pool.submit(request_worker, target_url, stop_event, results, lock) for _ in range(concurrency)]
            time.sleep(duration_seconds)
            stop_event.set()
            for f in futures:
                f.result()
    else:
        time.sleep(duration_seconds)
        stop_event.set()

    sampler.join(timeout=5)
    return results, sampler.samples


def summarize(concurrency: int, results: list[RequestResult], samples: list[ResourceSample]) -> dict:
    total = len(results)
    errors = sum(1 for r in results if not r.status.isdigit() or not r.status.startswith("2"))
    latencies = sorted(r.latency_ms for r in results)
    cpu_values = [s.cpu_millicores for s in samples if s.cpu_millicores is not None]
    mem_values = [s.memory_mi for s in samples if s.memory_mi is not None]

    def pct(values: list[float], p: float) -> float:
        if not values:
            return float("nan")
        idx = min(len(values) - 1, int(len(values) * p))
        return values[idx]

    return {
        "concurrency": concurrency,
        "request_total": total,
        "request_errors": errors,
        "latency_p50_ms": pct(latencies, 0.5),
        "latency_p95_ms": pct(latencies, 0.95),
        "cpu_peak_millicores": max(cpu_values) if cpu_values else None,
        "cpu_avg_millicores": sum(cpu_values) / len(cpu_values) if cpu_values else None,
        "memory_peak_mi": max(mem_values) if mem_values else None,
        "memory_avg_mi": sum(mem_values) / len(mem_values) if mem_values else None,
        "sample_count": len(samples),
    }


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concurrency", type=int, default=1, help="Jumlah worker paralel mengirim /predict")
    parser.add_argument("--duration-seconds", type=float, default=60, help="Durasi tiap level uji beban")
    parser.add_argument("--target-url", default="http://localhost", help="Base URL real-time API")
    parser.add_argument("--namespace", default="churn-prediction")
    parser.add_argument("--pod-name-prefix", default="churn-api-")
    parser.add_argument("--sample-interval-seconds", type=float, default=2.0)
    parser.add_argument("--idle-only", action="store_true", help="Sampling saja, tanpa generate beban")
    parser.add_argument("--output-dir", default=".", help="Direktori output CSV")
    parser.add_argument("--output-prefix", default="load_test", help="Prefix nama file CSV")
    args = parser.parse_args()

    concurrency = 0 if args.idle_only else args.concurrency
    print(f"[level] concurrency={concurrency} duration={args.duration_seconds}s target={args.target_url}", file=sys.stderr)

    results, samples = run_level(
        concurrency=concurrency,
        duration_seconds=args.duration_seconds,
        target_url=args.target_url,
        namespace=args.namespace,
        pod_name_prefix=args.pod_name_prefix,
        sample_interval_seconds=args.sample_interval_seconds,
    )

    summary = summarize(concurrency, results, samples)
    print(summary, file=sys.stderr)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"c{concurrency}_{int(time.time())}"

    write_csv(
        out_dir / f"{args.output_prefix}_requests_{suffix}.csv",
        [{"timestamp": r.timestamp, "status": r.status, "latency_ms": r.latency_ms} for r in results],
        ["timestamp", "status", "latency_ms"],
    )
    write_csv(
        out_dir / f"{args.output_prefix}_resources_{suffix}.csv",
        [{"timestamp": s.timestamp, "cpu_millicores": s.cpu_millicores, "memory_mi": s.memory_mi} for s in samples],
        ["timestamp", "cpu_millicores", "memory_mi"],
    )
    write_csv(
        out_dir / f"{args.output_prefix}_summary_{suffix}.csv",
        [summary],
        list(summary.keys()),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
