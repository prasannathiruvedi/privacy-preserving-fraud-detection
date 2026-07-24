# ============================================================
# api/service.py — Fraud Service Layer
# Responsibility: Orchestrate predictor + explanation.
# API calls this. API does NOT touch model directly.
# ============================================================

import logging
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from model.predictor import FraudPredictor
from utils.explanation import (
    build_explanation,
    build_feature_risk_breakdown,
    get_action,
    get_risk_emoji,
    get_risk_level,
)

logger = logging.getLogger(__name__)


class FraudService:
    """
    Service layer between API and ML model.
    API → FraudService → FeatureEngineer → Predictor → Model
    """

    def __init__(self):
        self._predictor = FraudPredictor()

    def startup(self):
        """Load model artifacts at service startup."""
        logger.info("FraudService starting up...")
        self._predictor.load()
        logger.info("FraudService ready.")

    def analyse(self, txn: dict) -> dict:
        """
        Full fraud analysis for a single validated transaction.

        Args:
            txn: Validated transaction dict (from API schema)

        Returns:
            Complete fraud analysis result dict
        """
        logger.info(f"Analysing transaction | amount=₹{txn.get('amount')} | "
                    f"sender={txn.get('sender_bank')} | receiver={txn.get('receiver_bank')}")

        # Get raw probability from model
        proba       = self._predictor.predict_proba(txn)
        score       = round(proba * 100, 2)
        risk_level  = get_risk_level(score)
        action      = get_action(risk_level)
        emoji       = get_risk_emoji(action)

        # Get top contributing features
        top_factors = self._predictor.get_feature_contributions(txn)

        # Generate explanation (decoupled from model)
        explanation = build_explanation(txn, score, risk_level)

        # Generate risk breakdown for UI
        feature_risks = build_feature_risk_breakdown(txn)

        logger.info(f"Result | score={score} | risk={risk_level} | action={action}")

        return {
            "fraud_score":       score,
            "risk_level":        risk_level,
            "action":            action,
            "emoji":             emoji,
            "top_risk_factors":  top_factors,
            "feature_risks":     feature_risks,
            "explanation":       explanation,
            "timestamp":         datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def analyse_batch(self, transactions: list[dict]) -> list[dict]:
        """
        Analyse a list of transactions.

        Args:
            transactions: List of validated transaction dicts

        Returns:
            List of fraud analysis results
        """
        logger.info(f"Batch analysis: {len(transactions)} transactions")
        results = [self.analyse(txn) for txn in transactions]
        logger.info(f"Batch complete | Flagged: {sum(1 for r in results if r['action'] in ['BLOCK','REVIEW'])}")
        return results

    @property
    def is_ready(self) -> bool:
        return self._predictor.is_loaded