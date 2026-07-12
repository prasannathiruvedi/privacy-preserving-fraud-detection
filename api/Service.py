# ============================================================
# api/service.py — Fraud Service Layer
# Responsibility: Orchestrate predictor + explanation engine.
# API calls this. API never touches model directly.
#
# Flow:
#   API → FraudService → FeatureEngineer → FraudPredictor → LR Model
#                      → ExplanationEngine → Response
# ============================================================

import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from model.predictor import FraudPredictor
from utils.explanation import (
    build_explanation,
    build_feature_risk_breakdown,
    get_action,
    get_emoji,
    get_risk_level,
)

logger = logging.getLogger(__name__)


class FraudService:
    """
    Service layer between FastAPI and ML model.
    API is fully independent of ML implementation details.
    """

    def __init__(self):
        self._predictor = FraudPredictor()

    def startup(self):
        """Load model artifacts once at API startup."""
        logger.info("FraudService: loading model artifacts...")
        self._predictor.load()
        logger.info("FraudService: ready to serve predictions.")

    def analyse(self, txn: dict) -> dict:
        """
        Full fraud analysis for one validated transaction.

        Args:
            txn: Validated transaction dict from FastAPI schema.

        Returns:
            Complete fraud analysis result dict.
        """
        logger.info(
            f"Analysing | amount=₹{txn.get('amount')} | "
            f"{txn.get('sender_bank')} → {txn.get('receiver_bank')}"
        )

        # 1. Raw probability from LR model
        proba      = self._predictor.predict_proba(txn)
        score      = round(proba * 100, 2)

        # 2. Business decision
        risk_level = get_risk_level(score)
        action     = get_action(risk_level)
        emoji      = get_emoji(action)

        # 3. Top contributing features (LR coeff × feature value)
        top_factors = self._predictor.get_top_features(txn, top_n=5)

        # 4. Human-readable explanation
        explanation = build_explanation(txn, score, risk_level)

        # 5. Per-category risk breakdown for UI
        feature_risks = build_feature_risk_breakdown(txn)

        logger.info(f"Result | score={score} | {risk_level} | {action}")

        return {
            "fraud_score":      score,
            "risk_level":       risk_level,
            "action":           action,
            "emoji":            emoji,
            "top_risk_factors": top_factors,
            "feature_risks":    feature_risks,
            "explanation":      explanation,
            "timestamp":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def analyse_batch(self, transactions: list) -> list:
        """Analyse a list of validated transaction dicts."""
        logger.info(f"Batch: {len(transactions)} transactions")
        results = [self.analyse(txn) for txn in transactions]
        flagged = sum(1 for r in results if r["action"] in ["BLOCK", "REVIEW"])
        logger.info(f"Batch done | Flagged: {flagged}/{len(results)}")
        return results

    @property
    def is_ready(self) -> bool:
        return self._predictor.is_loaded

    @property
    def threshold(self) -> float:
        return self._predictor.threshold if self._predictor.is_loaded else 0.0  