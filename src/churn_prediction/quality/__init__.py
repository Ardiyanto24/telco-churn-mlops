"""Gerbang kualitas data harian -- Milestone 2.4.

Memeriksa kewajaran data mentah (volume, proporsi NULL, distribusi kategori)
dibanding baseline rolling -- berbeda dari validasi skema (`churn_prediction.schema`,
Milestone 1.3, memeriksa bentuk data) dan dari drift model (Milestone 3.x).

Modul murni (tidak bergantung Prefect) -- dipanggil task DAG (Milestone 2.5)
maupun pipeline CI (Milestone 2.7). Lihat
milestones/2.4-gerbang-kualitas-data-harian/decisions.md.
"""
