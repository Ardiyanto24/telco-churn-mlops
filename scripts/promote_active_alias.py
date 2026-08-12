"""Tandai versi model sebagai "versi aktif" (alias MLflow) -- Milestone 2.1.

Dipakai lagi (bukan sekali-jalan) setiap kali versi aktif berganti -- mis.
promosi versi kandidat baru atau rollback (Milestone 2.8). Tidak mendefinisikan
ulang logika alias, cuma memanggil `set_active_alias()` dari
`churn_prediction.inference.registry` (satu sumber kebenaran).

Usage: python scripts/promote_active_alias.py <version> [alias]
"""

import sys

from churn_prediction.inference import constants
from churn_prediction.inference.registry import set_active_alias


def main():
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <version> [alias]", file=sys.stderr)
        sys.exit(1)
    version = sys.argv[1]
    alias = sys.argv[2] if len(sys.argv) > 2 else constants.ACTIVE_ALIAS

    set_active_alias(version, alias=alias)
    print(f"Alias '{alias}' -> {constants.MODEL_NAME} version {version}")


if __name__ == "__main__":
    main()
