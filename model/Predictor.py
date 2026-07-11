# ============================================================
# model/predictor.py — Inference Only
# Responsibility: Load saved artifacts, run predictions.
# No training. No data generation. No business logic.
# ============================================================

import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

import joblib
import numpy as np
import pandas as pd

from config import (
    MODEL_PATH, SCALER_PATH, ENCODERS_PATH, THRESHOLD_PATH,
    RISK_BANDS, RISK_ACTIONS,
)
from features.engineer import FeatureEngineer

logger = logging.getLogger(__name__)


class FraudPredictor:
    """
    Loads trained artifacts and produces fraud probability scores.
    Returns raw probability only — no business logic here.
    Business decisions (risk level, action) are in FraudService.
    """

    def __init__(self):
        self._model         = None
        self._scaler        = None
        self._encoders      = None
        self._threshold     = None
        self._feature_cols  = None
        self._fe            = None
        self._loaded        = False

    def load(self) -> "FraudPredictor":
        """Load all saved artifacts from disk."""
        logger.info("Loading model artifacts...")

        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Model not found at {MODEL_PATH}. "
                "Run `python model/train.py` first."
            )

        self._model    = joblib.load(MODEL_PATH)
        self._scaler   = joblib.load(SCALER_PATH)
        self._encoders = joblib.load(ENCODERS_PATH)
        meta           = joblib.load(THRESHOLD_PATH)

        self._threshold    = meta["threshold"]
        self._feature_cols = meta["feature_cols"]

        # Rebuild FeatureEngineer with saved state
        self._fe = FeatureEngineer()
        self._fe.scaler          = self._scaler
        self._fe.label_encoders  = self._encoders

        self._loaded = True
        logger.info(f"Model loaded | Threshold: {self._threshold:.4f} | Features: {len(self._feature_cols)}")
        return self

    def predict_proba(self, txn: dict) -> float:
        """
        Run inference on a single transaction dict.

        Args:
            txn: Validated transaction dictionary

        Returns:
            float: Fraud probability (0.0 – 1.0)
        """
        if not self._loaded:
            raise RuntimeError("Predictor not loaded. Call .load() first.")

        df = pd.DataFrame([txn])
        X, _ = self._fe.transform(df, fit=False)
        proba = self._model.predict_proba(X)[0][1]
        return float(proba)

    def get_feature_contributions(self, txn: dict) -> list[str]:
        """
        Returns top 5 feature names by |coefficient × feature value|.
        Used by explanation engine.
        """
        if not self._loaded:
            raise RuntimeError("Predictor not loaded. Call .load() first.")

        df = pd.DataFrame([txn])
        X, cols = self._fe.transform(df, fit=False)
        coef = self._model.coef_[0]
        contributions = np.abs(coef * X[0])
        top_idx = np.argsort(contributions)[::-1][:5]
        return [cols[i] for i in top_idx]

    @property
    def threshold(self) -> float:
        return self._threshold

    @property
    def is_loaded(self) -> bool:
        return self._loaded