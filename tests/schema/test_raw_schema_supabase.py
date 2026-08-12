"""Integration test -- validasi RawDataSchema terhadap data nyata Supabase
(`telco_customers_source`, PascalCase, di-rename ke snake_case).

Skip otomatis kalau SUPABASE_DB_URL tidak ada di .env/environment. Pola sama
dengan tests/transform/test_parity_real_artifact.py (Milestone 1.2).
"""

import os
from pathlib import Path

import pandas as pd
import pytest

from churn_prediction.schema.column_mapping import RAW_PASCAL_TO_SNAKE
from churn_prediction.schema.raw_schema import RawDataSchema

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = REPO_ROOT / ".env"


def _load_env_var(name):
    value = os.environ.get(name)
    if value:
        return value
    if not ENV_PATH.exists():
        return None
    with open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == name:
                return v.strip().strip('"').strip("'")
    return None


SUPABASE_DB_URL = _load_env_var("SUPABASE_DB_URL")

pytestmark = pytest.mark.skipif(
    not SUPABASE_DB_URL, reason="butuh SUPABASE_DB_URL (.env atau environment)"
)


def _fetch_real_rows(limit=1500):
    import psycopg2

    conn = psycopg2.connect(SUPABASE_DB_URL, connect_timeout=15)
    cur = conn.cursor()
    cols_sql = ", ".join(f'"{c}"' if c[0].isupper() else c for c in RAW_PASCAL_TO_SNAKE.keys())
    cur.execute(f"SELECT {cols_sql} FROM telco_customers_source ORDER BY id LIMIT %s;", (limit,))
    colnames = [d[0] for d in cur.description]
    rows = cur.fetchall()
    conn.close()

    df = pd.DataFrame(rows, columns=colnames)
    df["MonthlyCharges"] = df["MonthlyCharges"].astype(float)
    df["TotalCharges"] = df["TotalCharges"].astype(float)
    return df


def test_raw_schema_accepts_real_supabase_rows():
    df_pascal = _fetch_real_rows(limit=1500)
    assert len(df_pascal) >= 1000

    df_snake = df_pascal.rename(columns=RAW_PASCAL_TO_SNAKE)
    validated = RawDataSchema.validate(df_snake)
    assert len(validated) == len(df_snake)
