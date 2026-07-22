# ============================================================
# model/train.py — Training Pipeline
# Responsibility: Train model and save artifacts.
# Run ONCE offline. Never called at API runtime.
# ============================================================

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score, classification_report,
    f1_score, precision_recall_curve, roc_auc_score,
)
from sklearn.model_selection import train_test_split

from config import (
    ARTIFACTS_DIR, ENCODERS_PATH, LOG_FORMAT, LOG_LEVEL,
    LR_C, LR_CLASS_WEIGHT, LR_MAX_ITER, LR_SOLVER,
    MODEL_PATH, RANDOM_STATE, SCALER_PATH, TEST_SIZE, THRESHOLD_PATH,
)
from data.generator import UPIDataGenerator
from features.engineer import FeatureEngineer

# ── Logging setup ─────────────────────────────────────────────
logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


def train_and_save():
    logger.info("=" * 55)
    logger.info("  UPI FRAUD — TRAINING PIPELINE")
    logger.info("=" * 55)

    # ── Step 1: Generate training data ────────────────────────
    logger.info("Step 1: Generating training data...")
    generator = UPIDataGenerator()
    df = generator.generate()

    # ── Step 2: Feature engineering ───────────────────────────
    logger.info("Step 2: Engineering features...")
    fe = FeatureEngineer()
    X, feature_cols = fe.transform(df, fit=True)
    y = df["is_fraud"].values
    logger.info(f"Feature matrix shape: {X.shape}")

    # ── Step 3: Train/test split ──────────────────────────────
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, stratify=y, random_state=RANDOM_STATE
    )
    logger.info(f"Train: {len(X_train):,} | Test: {len(X_test):,}")

    # ── Step 4: Train Logistic Regression ────────────────────
    logger.info("Step 3: Training Logistic Regression model...")
    model = LogisticRegression(
        C=LR_C,
        class_weight=LR_CLASS_WEIGHT,
        solver=LR_SOLVER,
        max_iter=LR_MAX_ITER,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)
    logger.info("Training complete.")

    # ── Step 5: Evaluate ──────────────────────────────────────
    logger.info("Step 4: Evaluating model...")
    proba = model.predict_proba(X_test)[:, 1]
    auc   = roc_auc_score(y_test, proba)
    ap    = average_precision_score(y_test, proba)

    # Find optimal threshold using F1
    precisions, recalls, thresholds = precision_recall_curve(y_test, proba)
    f1_scores = 2 * precisions * recalls / (precisions + recalls + 1e-9)
    optimal_threshold = float(thresholds[np.argmax(f1_scores)])
    pred = (proba >= optimal_threshold).astype(int)
    f1   = f1_score(y_test, pred)

    logger.info(f"ROC-AUC          : {auc:.4f}")
    logger.info(f"Avg Precision    : {ap:.4f}")
    logger.info(f"F1 Score         : {f1:.4f}")
    logger.info(f"Optimal Threshold: {optimal_threshold:.4f}")
    logger.info("\n" + classification_report(y_test, pred, target_names=["Legit", "Fraud"]))

    # ── Step 6: Save artifacts ────────────────────────────────
    logger.info("Step 5: Saving model artifacts...")
    joblib.dump(model,                  MODEL_PATH)
    joblib.dump(fe.scaler,              SCALER_PATH)
    joblib.dump(fe.label_encoders,      ENCODERS_PATH)
    joblib.dump({
        "threshold":     optimal_threshold,
        "feature_cols":  feature_cols,
        "auc":           auc,
        "f1":            f1,
    }, THRESHOLD_PATH)

    logger.info(f"✅ model          → {MODEL_PATH}")
    logger.info(f"✅ scaler         → {SCALER_PATH}")
    logger.info(f"✅ label_encoders → {ENCODERS_PATH}")
    logger.info(f"✅ threshold      → {THRESHOLD_PATH}")
    logger.info("Training pipeline complete. API is ready to serve.")


if __name__ == "__main__":
    train_and_save()