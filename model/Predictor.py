# ============================================================
# model/predictor.py — Inference Only
# Responsibility: Load saved artifacts → predict probability.
# No training. No data generation. No business logic.
# ============================================================

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import joblib
import numpy as np
import pandas as pd

from config import ENCODERS_PATH, MODEL_PATH, SCALER_PATH, THRESHOLD_PATH
from features.engineer import FeatureEngineer

logger = logging.getLogger(__name__)


class FraudPredictor:
    """
    Loads trained LR artifacts and predicts fraud probability.
    Returns raw probability only.
    All business logic (risk band, action) is in service.py.
    """

    def __init__(self):
        self._model        = None
        self._fe           = None
        self._threshold    = None
        self._feature_cols = None
        self._loaded       = False

    def load(self) -> "FraudPredictor":
        """Load all artifacts saved by model/train.py."""
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Model artifact not found at {MODEL_PATH}.\n"
                "Run:  python model/train.py"
            )

        self._model = joblib.load(MODEL_PATH)
        scaler      = joblib.load(SCALER_PATH)
        encoders    = joblib.load(ENCODERS_PATH)
        meta        = joblib.load(THRESHOLD_PATH)

        self._threshold    = meta["threshold"]
        self._feature_cols = meta["feature_cols"]

        # Rebuild FeatureEngineer with persisted scaler + encoders
        self._fe = FeatureEngineer()
        self._fe.scaler         = scaler
        self._fe.label_encoders = encoders

        self._loaded = True
        logger.info(
            f"FraudPredictor loaded | "
            f"threshold={self._threshold:.4f} | "
            f"features={len(self._feature_cols)}"
        )
        return self

    def predict_proba(self, txn: dict) -> float:
        """
        Predict fraud probability for one validated transaction.

        Args:
            txn: dict with all 18 required transaction fields

        Returns:
            float: probability of fraud (0.0 – 1.0)
        """
        self._assert_loaded()
        df = pd.DataFrame([txn])
        X, _ = self._fe.transform(df, fit=False)
        proba = float(self._model.predict_proba(X)[0][1])
        return proba

    def get_top_features(self, txn: dict, top_n: int = 5) -> list:
        """
        Return top N feature names by |coefficient × scaled_value|.
        Used by explanation engine.
        """
        self._assert_loaded()
        df = pd.DataFrame([txn])
        X, cols = self._fe.transform(df, fit=False)
        coef = self._model.coef_[0]
        contributions = np.abs(coef * X[0])
        top_idx = np.argsort(contributions)[::-1][:top_n]
        return [cols[i] for i in top_idx]

    def _assert_loaded(self):
        if not self._loaded:
            raise RuntimeError("FraudPredictor not loaded. Call .load() first.")

    @property
    def threshold(self) -> float:
        return self._threshold

    @property
    def is_loaded(self) -> bool:
        return self._loaded