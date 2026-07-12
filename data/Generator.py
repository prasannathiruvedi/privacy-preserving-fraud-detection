# ============================================================
# data/generator.py — Synthetic UPI Dataset Generator
# Responsibility: Generate training data ONLY.
# Never called at API runtime.
# ============================================================

import logging
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd

from config import (
    BANKS, DATASET_SIZE, FRAUD_RATIO, MERCHANT_CATEGORIES,
    RANDOM_STATE, STATES, UPI_APPS,
)

logger = logging.getLogger(__name__)


class UPIDataGenerator:
    """
    Generates realistic synthetic UPI transaction data.
    Used ONLY during training — never at runtime.
    """

    def __init__(self, n: int = DATASET_SIZE, fraud_ratio: float = FRAUD_RATIO):
        self.n = n
        self.fraud_ratio = fraud_ratio
        np.random.seed(RANDOM_STATE)
        random.seed(RANDOM_STATE)
        logger.info(f"UPIDataGenerator init: n={n}, fraud_ratio={fraud_ratio}")

    def _base_fields(self, n: int) -> dict:
        start = datetime(2023, 1, 1)
        timestamps = [
            start + timedelta(seconds=random.randint(0, 365 * 86400))
            for _ in range(n)
        ]
        return {
            "timestamp":         timestamps,
            "hour":              [t.hour for t in timestamps],
            "sender_upi_app":    random.choices(UPI_APPS, k=n),
            "receiver_upi_app":  random.choices(UPI_APPS, k=n),
            "sender_bank":       random.choices(BANKS, k=n),
            "receiver_bank":     random.choices(BANKS, k=n),
            "merchant_category": random.choices(MERCHANT_CATEGORIES, k=n),
            "sender_state":      random.choices(STATES, k=n),
            "receiver_state":    random.choices(STATES, k=n),
        }

    def _generate_legit(self, n: int) -> pd.DataFrame:
        base = self._base_fields(n)
        return pd.DataFrame({
            **base,
            "transaction_id":            [f"TXN{i:07d}" for i in range(n)],
            "amount":                    np.random.lognormal(7.5, 1.2, n).clip(1, 100_000),
            "sender_account_age_days":   np.random.randint(180, 3650, n),
            "receiver_account_age_days": np.random.randint(180, 3650, n),
            "sender_txn_count_7d":       np.random.poisson(12, n),
            "receiver_txn_count_7d":     np.random.poisson(15, n),
            "sender_avg_amount_30d":     np.random.lognormal(7.5, 0.8, n),
            "is_new_device":             np.random.choice([0, 1], n, p=[0.95, 0.05]),
            "is_new_beneficiary":        np.random.choice([0, 1], n, p=[0.80, 0.20]),
            "failed_attempts_24h":       np.random.choice([0, 1, 2], n, p=[0.90, 0.08, 0.02]),
            "ip_country":                np.random.choice(["India"] * 4 + ["Foreign"], n),
            "device_change_30d":         np.random.choice([0, 1, 2], n, p=[0.85, 0.12, 0.03]),
            "is_fraud": 0,
        })

    def _generate_fraud(self, n: int) -> pd.DataFrame:
        per = n // 5
        patterns = [
            # 1. Account Takeover
            {
                "amount": np.random.uniform(50000, 100000, per),
                "sender_account_age_days": np.random.randint(1, 30, per),
                "receiver_account_age_days": np.random.randint(1, 10, per),
                "sender_txn_count_7d": np.random.randint(0, 3, per),
                "receiver_txn_count_7d": np.random.randint(0, 2, per),
                "sender_avg_amount_30d": np.random.uniform(500, 1000, per),
                "is_new_device": 1, "is_new_beneficiary": 1,
                "failed_attempts_24h": np.random.randint(3, 10, per),
                "ip_country": np.random.choice(["Foreign", "Foreign", "India"], per),
                "device_change_30d": np.random.randint(2, 5, per),
            },
            # 2. Phishing
            {
                "amount": np.random.uniform(10000, 50000, per),
                "sender_account_age_days": np.random.randint(365, 2000, per),
                "receiver_account_age_days": np.random.randint(1, 15, per),
                "sender_txn_count_7d": np.random.randint(5, 20, per),
                "receiver_txn_count_7d": np.random.randint(0, 3, per),
                "sender_avg_amount_30d": np.random.uniform(1000, 5000, per),
                "is_new_device": np.random.choice([0, 1], per, p=[0.4, 0.6]),
                "is_new_beneficiary": 1,
                "failed_attempts_24h": np.random.randint(0, 2, per),
                "ip_country": "India",
                "device_change_30d": np.random.randint(0, 2, per),
            },
            # 3. Rapid Small Transactions
            {
                "amount": np.random.uniform(1, 500, per),
                "sender_account_age_days": np.random.randint(1, 60, per),
                "receiver_account_age_days": np.random.randint(1, 30, per),
                "sender_txn_count_7d": np.random.randint(50, 200, per),
                "receiver_txn_count_7d": np.random.randint(30, 100, per),
                "sender_avg_amount_30d": np.random.uniform(100, 500, per),
                "is_new_device": np.random.choice([0, 1], per, p=[0.5, 0.5]),
                "is_new_beneficiary": np.random.choice([0, 1], per, p=[0.3, 0.7]),
                "failed_attempts_24h": np.random.randint(0, 3, per),
                "ip_country": "India",
                "device_change_30d": np.random.randint(0, 3, per),
            },
            # 4. Unusual Hours
            {
                "amount": np.random.uniform(5000, 80000, per),
                "sender_account_age_days": np.random.randint(30, 365, per),
                "receiver_account_age_days": np.random.randint(1, 30, per),
                "sender_txn_count_7d": np.random.randint(2, 10, per),
                "receiver_txn_count_7d": np.random.randint(0, 5, per),
                "sender_avg_amount_30d": np.random.uniform(500, 3000, per),
                "is_new_device": np.random.choice([0, 1], per, p=[0.5, 0.5]),
                "is_new_beneficiary": np.random.choice([0, 1], per, p=[0.4, 0.6]),
                "failed_attempts_24h": np.random.randint(1, 4, per),
                "ip_country": np.random.choice(["India", "Foreign"], per, p=[0.6, 0.4]),
                "device_change_30d": np.random.randint(1, 4, per),
            },
            # 5. New Device + Large Amount
            {
                "amount": np.random.uniform(30000, 100000, per),
                "sender_account_age_days": np.random.randint(60, 1000, per),
                "receiver_account_age_days": np.random.randint(1, 20, per),
                "sender_txn_count_7d": np.random.randint(1, 5, per),
                "receiver_txn_count_7d": np.random.randint(0, 3, per),
                "sender_avg_amount_30d": np.random.uniform(500, 2000, per),
                "is_new_device": 1, "is_new_beneficiary": 1,
                "failed_attempts_24h": np.random.randint(2, 8, per),
                "ip_country": np.random.choice(["India", "Foreign"], per, p=[0.5, 0.5]),
                "device_change_30d": np.random.randint(2, 6, per),
            },
        ]
        rows = []
        for p in patterns:
            base = self._base_fields(per)
            rows.append(pd.DataFrame({**base, **p}))

        df = pd.concat(rows, ignore_index=True)
        df["is_fraud"] = 1
        df["transaction_id"] = [f"FRD{i:07d}" for i in range(len(df))]
        return df

    def generate(self) -> pd.DataFrame:
        n_fraud = int(self.n * self.fraud_ratio)
        n_legit = self.n - n_fraud
        df = pd.concat(
            [self._generate_legit(n_legit), self._generate_fraud(n_fraud)],
            ignore_index=True,
        )
        df = df.sample(frac=1, random_state=RANDOM_STATE).reset_index(drop=True)
        logger.info(
            f"Dataset ready: {len(df):,} rows | "
            f"Fraud: {df['is_fraud'].sum():,} ({df['is_fraud'].mean()*100:.1f}%)"
        )
        return df