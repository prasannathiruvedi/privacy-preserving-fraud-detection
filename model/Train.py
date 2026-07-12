# ============================================================
# model/train.py — Training Pipeline
# Responsibility: Train LR model → save artifacts.
# Run ONCE offline. NEVER called by API at runtime.
#
# Usage:
#   cd AI_MODEL
#   python model/train.py
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
    MPC_WEIGHTS_PATH,
)
from data.generator import UPIDataGenerator
from features.engineer import FeatureEngineer

logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


def export_weights_for_mpc(model, feature_cols: list):
    """
    Export trained LR weights as plain text for MP-SPDZ input.
    MP-SPDZ reads weights from Player-Data/lr_weights.txt
    Format: one float per line (bias first, then weights)
    """
    MPC_WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    weights = np.concatenate([model.intercept_, model.coef_[0]])
    with open(MPC_WEIGHTS_PATH, "w") as f:
        for w in weights:
            f.write(f"{w:.10f}\n")
    logger.info(f"✅ MPC weights exported → {MPC_WEIGHTS_PATH} ({len(weights)} values)")

    # Also save feature column names for MPC reference
    cols_path = MPC_WEIGHTS_PATH.parent / "feature_cols.txt"
    with open(cols_path, "w") as f:
        for col in feature_cols:
            f.write(col + "\n")
    logger.info(f"✅ Feature cols saved  → {cols_path}")


def train_and_save():
    logger.info("=" * 60)
    logger.info("  UPI FRAUD — TRAINING PIPELINE (LR + MPC Export)")
    logger.info("=" * 60)

    # ── Step 1: Generate data ──────────────────────────────────
    logger.info("Step 1: Generating training data...")
    df = UPIDataGenerator().generate()

    # ── Step 2: Feature engineering ───────────────────────────
    logger.info("Step 2: Feature engineering...")
    fe = FeatureEngineer()
    X, feature_cols = fe.transform(df, fit=True)
    y = df["is_fraud"].values
    logger.info(f"         Feature matrix: {X.shape}")

    # ── Step 3: Train / test split ────────────────────────────
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, stratify=y, random_state=RANDOM_STATE
    )
    logger.info(f"Step 3: Train={len(X_train):,} | Test={len(X_test):,}")

    # ── Step 4: Train Logistic Regression ────────────────────
    logger.info("Step 4: Training Logistic Regression...")
    model = LogisticRegression(
        C=LR_C,
        class_weight=LR_CLASS_WEIGHT,
        solver=LR_SOLVER,
        max_iter=LR_MAX_ITER,
        random_state=RANDOM_STATE,
    )
    model.fit(X_train, y_train)
    logger.info("         Training complete ✓")

    # ── Step 5: Evaluate ──────────────────────────────────────
    logger.info("Step 5: Evaluating...")
    proba = model.predict_proba(X_test)[:, 1]
    auc   = roc_auc_score(y_test, proba)
    ap    = average_precision_score(y_test, proba)
    p, r, t = precision_recall_curve(y_test, proba)
    f1s   = 2 * p * r / (p + r + 1e-9)
    threshold = float(t[np.argmax(f1s)])
    pred  = (proba >= threshold).astype(int)
    f1    = f1_score(y_test, pred)

    logger.info(f"         ROC-AUC   : {auc:.4f}")
    logger.info(f"         Avg Prec  : {ap:.4f}")
    logger.info(f"         F1 Score  : {f1:.4f}")
    logger.info(f"         Threshold : {threshold:.4f}")
    logger.info("\n" + classification_report(y_test, pred, target_names=["Legit", "Fraud"]))

    # ── Step 6: Save sklearn artifacts ────────────────────────
    logger.info("Step 6: Saving artifacts...")
    joblib.dump(model,             MODEL_PATH)
    joblib.dump(fe.scaler,         SCALER_PATH)
    joblib.dump(fe.label_encoders, ENCODERS_PATH)
    joblib.dump({
        "threshold":    threshold,
        "feature_cols": feature_cols,
        "auc":          auc,
        "f1":           f1,
    }, THRESHOLD_PATH)
    logger.info(f"  ✅ lr_model.joblib        → {MODEL_PATH}")
    logger.info(f"  ✅ scaler.joblib           → {SCALER_PATH}")
    logger.info(f"  ✅ label_encoders.joblib   → {ENCODERS_PATH}")
    logger.info(f"  ✅ threshold.joblib        → {THRESHOLD_PATH}")

    # ── Step 7: Export weights for MP-SPDZ ───────────────────
    logger.info("Step 7: Exporting weights for MP-SPDZ MPC layer...")
    export_weights_for_mpc(model, feature_cols)

    logger.info("=" * 60)
    logger.info("  Training complete. API + MPC ready.")
    logger.info("=" * 60)


if __name__ == "__main__":
    train_and_save()