# ============================================================
# features/engineer.py — Feature Engineering
# Responsibility: Transform raw transactions into feature vectors.
# Model-agnostic. Works with LR, XGBoost, or any model.
# ============================================================

import logging
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder, StandardScaler

from config import (
    LARGE_TXN_THRESHOLD, NEW_ACCOUNT_DAYS,
    HIGH_VELOCITY_TXN, FAILED_ATTEMPT_RISK_MIN,
    DEVICE_CHANGE_RISK_MIN
)

logger = logging.getLogger(__name__)

# Categorical columns to label-encode
CAT_COLS = [
    "sender_upi_app", "receiver_upi_app", "sender_bank",
    "receiver_bank", "merchant_category", "sender_state",
    "receiver_state", "ip_country"
]

FEATURE_COLUMNS = [
    "hour", "day_of_week", "is_weekend", "is_night",
    "log_amount", "amount_vs_avg_ratio", "is_large_txn", "is_round_amount",
    "sender_account_age_days", "receiver_account_age_days",
    "is_new_sender_acc", "is_new_receiver_acc", "account_age_diff",
    "sender_txn_count_7d", "receiver_txn_count_7d",
    "txn_velocity_ratio", "high_sender_velocity", "sender_avg_amount_30d",
    "is_new_device", "is_new_beneficiary",
    "failed_attempts_24h", "failed_attempt_risk",
    "device_change_30d", "device_change_risk",
    "cross_state", "foreign_ip", "multi_risk_flag",
    "sender_upi_app", "receiver_upi_app", "sender_bank", "receiver_bank",
    "merchant_category", "sender_state", "receiver_state", "ip_country",
]


class FeatureEngineer:
    """
    Stateful feature transformer.
    Call fit=True during training, fit=False during inference.
    Reusable across any ML model.
    """

    def __init__(self):
        self.label_encoders: dict[str, LabelEncoder] = {}
        self.scaler = StandardScaler()
        logger.debug("FeatureEngineer initialized")

    def transform(self, df: pd.DataFrame, fit: bool = False) -> np.ndarray:
        """
        Transform raw transaction DataFrame into scaled feature matrix.

        Args:
            df:  Raw transaction DataFrame
            fit: True during training, False during inference

        Returns:
            np.ndarray of shape (n_samples, n_features)
        """
        df = self._build_features(df.copy())
        cols = [c for c in FEATURE_COLUMNS if c in df.columns]
        X = df[cols].fillna(0)

        if fit:
            logger.info("Fitting scaler on training data")
            return self.scaler.fit_transform(X), cols
        else:
            return self.scaler.transform(X), cols

    def _build_features(self, df: pd.DataFrame) -> pd.DataFrame:
        # ── Time features ────────────────────────────────────
        if "timestamp" not in df.columns:
            df["timestamp"] = datetime.now()
        df["hour"]        = pd.to_datetime(df["timestamp"]).dt.hour
        df["day_of_week"] = pd.to_datetime(df["timestamp"]).dt.dayofweek
        df["is_weekend"]  = df["day_of_week"].isin([5, 6]).astype(int)
        df["is_night"]    = df["hour"].apply(lambda h: 1 if h < 6 or h > 22 else 0)

        # ── Amount features ──────────────────────────────────
        df["log_amount"]          = np.log1p(df["amount"])
        df["amount_vs_avg_ratio"] = df["amount"] / (df["sender_avg_amount_30d"] + 1)
        df["is_large_txn"]        = (df["amount"] > LARGE_TXN_THRESHOLD).astype(int)
        df["is_round_amount"]     = (df["amount"] % 1000 == 0).astype(int)

        # ── Account age features ─────────────────────────────
        df["is_new_sender_acc"]   = (df["sender_account_age_days"] < NEW_ACCOUNT_DAYS).astype(int)
        df["is_new_receiver_acc"] = (df["receiver_account_age_days"] < NEW_ACCOUNT_DAYS).astype(int)
        df["account_age_diff"]    = abs(df["sender_account_age_days"] - df["receiver_account_age_days"])

        # ── Velocity features ────────────────────────────────
        df["txn_velocity_ratio"]   = df["sender_txn_count_7d"] / (df["receiver_txn_count_7d"] + 1)
        df["high_sender_velocity"] = (df["sender_txn_count_7d"] > HIGH_VELOCITY_TXN).astype(int)

        # ── Risk flag features ───────────────────────────────
        df["cross_state"]         = (df["sender_state"] != df["receiver_state"]).astype(int)
        df["foreign_ip"]          = (df["ip_country"] != "India").astype(int)
        df["multi_risk_flag"]     = (
            df["is_new_device"] + df["is_new_beneficiary"] +
            df["foreign_ip"] + df["is_new_sender_acc"] + df["is_new_receiver_acc"]
        )
        df["failed_attempt_risk"] = (df["failed_attempts_24h"] >= FAILED_ATTEMPT_RISK_MIN).astype(int)
        df["device_change_risk"]  = (df["device_change_30d"] >= DEVICE_CHANGE_RISK_MIN).astype(int)

        # ── Categorical encoding ─────────────────────────────
        df = self._encode_categoricals(df)
        return df

    def _encode_categoricals(self, df: pd.DataFrame) -> pd.DataFrame:
        for col in CAT_COLS:
            if col not in df.columns:
                continue
            if col not in self.label_encoders:
                le = LabelEncoder()
                df[col] = le.fit_transform(df[col].astype(str))
                self.label_encoders[col] = le
            else:
                le = self.label_encoders[col]
                df[col] = df[col].astype(str).map(
                    lambda x: le.transform([x])[0] if x in le.classes_ else -1
                )
        return df