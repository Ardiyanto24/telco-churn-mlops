"""Verifikasi sebelum promosi -- gerbang KEDUA Bagian 5.5 dokumen arsitektur,
Milestone 2.8.

Beda dari sanity check (Checkpoint 1, input sintetis, sebelum registrasi):
skrip ini membandingkan versi KANDIDAT (alias `challenger`) vs versi AKTIF
(alias `champion`) pada SAMPEL DATA PRODUCTION REAL yang SAMA. Kandidat
SECARA DESAIN boleh berbeda dari champion (bukan bug seperti parity test
M2.5/M2.7 yang harus identik) -- kriteria di sini soal "apakah kandidat
masuk akal", bukan "apakah kandidat sama persis".

Dua syarat (dikonfirmasi user sebelum implementasi):
  1. WAJIB: tidak ada exception/NaN saat scoring kandidat pada sampel real.
  2. Verdict pass/flag (TIDAK auto-blocking): |churn_rate(challenger) -
     churn_rate(champion)| < ambang PROVISIONAL -- promosi tetap keputusan
     manual sadar (Bagian 5.5: "bukan proses otomatis yang kompleks"),
     bukan gerbang CI yang menggagalkan build.

Ambang 20 poin persentase PROVISIONAL -- lihat
milestones/2.8-validasi-artifact-promosi-rollback/decisions.md untuk
pemicu kalibrasi ulang.
"""

import os
import sys

import pandas as pd
import psycopg2

from churn_prediction.inference.constants import ACTIVE_ALIAS
from churn_prediction.inference.registry import load_active_model, load_model_by_version, resolve_alias_version
from churn_prediction.schema.column_mapping import RAW_PASCAL_TO_SNAKE

SOURCE_TABLE = "telco_customers_source"
CANDIDATE_ALIAS = "challenger"
SAMPLE_SIZE = 1000
CHURN_RATE_DELTA_THRESHOLD_PP = 20.0  # poin persentase, PROVISIONAL


def _get_reader_connection_string() -> str:
    uri = os.environ.get("BATCH_READER_DB_URL")
    if not uri:
        raise RuntimeError("BATCH_READER_DB_URL tidak diset di environment")
    return uri


def _fetch_sample(limit: int) -> pd.DataFrame:
    cols = list(RAW_PASCAL_TO_SNAKE.keys())
    cols_sql = ", ".join(f'"{c}"' if c[0].isupper() else c for c in cols)
    sql = f"SELECT {cols_sql} FROM {SOURCE_TABLE} ORDER BY id LIMIT %s"

    conn = psycopg2.connect(_get_reader_connection_string())
    try:
        return pd.read_sql(sql, conn, params=(limit,))
    finally:
        conn.close()


def verify_before_promotion(df_features: pd.DataFrame, candidate_version: str) -> dict:
    """Kembalikan dict ringkasan verifikasi -- dipisah dari `main()` supaya
    bisa di-unit-test tanpa DB (mock `load_model_by_version`/`load_active_model`)."""
    champion_model = load_active_model(alias=ACTIVE_ALIAS)
    candidate_model = load_model_by_version(candidate_version)

    try:
        candidate_out = candidate_model.predict(df_features)
    except Exception as exc:
        return {"mandatory_passed": False, "error": f"Exception saat scoring kandidat: {exc!r}"}

    if candidate_out["churn_probability"].isna().any():
        return {"mandatory_passed": False, "error": "churn_probability kandidat mengandung NaN pada sampel real"}

    champion_out = champion_model.predict(df_features)

    champion_rate = float(champion_out["churn_label"].mean()) * 100
    candidate_rate = float(candidate_out["churn_label"].mean()) * 100
    delta = abs(candidate_rate - champion_rate)
    verdict = "pass" if delta < CHURN_RATE_DELTA_THRESHOLD_PP else "flag"

    return {
        "mandatory_passed": True,
        "champion_churn_rate_pct": champion_rate,
        "candidate_churn_rate_pct": candidate_rate,
        "delta_pp": delta,
        "threshold_pp": CHURN_RATE_DELTA_THRESHOLD_PP,
        "verdict": verdict,
    }


def main() -> int:
    candidate_version = resolve_alias_version(alias=CANDIDATE_ALIAS)
    print(f"Kandidat: versi {candidate_version} (alias '{CANDIDATE_ALIAS}')")

    df_raw = _fetch_sample(SAMPLE_SIZE)
    df_features = df_raw.rename(columns=RAW_PASCAL_TO_SNAKE)
    print(f"Sampel: {len(df_features)} baris dari {SOURCE_TABLE}")

    result = verify_before_promotion(df_features, candidate_version)

    if not result["mandatory_passed"]:
        print(f"GAGAL (wajib): {result['error']}", file=sys.stderr)
        return 1

    print(f"Champion churn_rate: {result['champion_churn_rate_pct']:.2f}%")
    print(f"Candidate churn_rate: {result['candidate_churn_rate_pct']:.2f}%")
    print(f"Delta: {result['delta_pp']:.2f} poin persentase (ambang provisional: {result['threshold_pp']}pp)")
    print(f"Verdict: {result['verdict'].upper()}")
    print("(verdict TIDAK auto-blocking -- promosi tetap keputusan manual, lihat decisions.md M2.8)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
