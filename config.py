# ============================================================
# config.py — Central Configuration
# ALL hardcoded values live here only. Never in other files.
# ============================================================

from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent
ARTIFACTS_DIR = BASE_DIR / "artifacts"
ARTIFACTS_DIR.mkdir(exist_ok=True)

MODEL_PATH     = ARTIFACTS_DIR / "lr_model.joblib"
SCALER_PATH    = ARTIFACTS_DIR / "scaler.joblib"
ENCODERS_PATH  = ARTIFACTS_DIR / "label_encoders.joblib"
THRESHOLD_PATH = ARTIFACTS_DIR / "threshold.joblib"

# MPC exported weights path (used by mpc/export_weights.py)
MPC_WEIGHTS_PATH = BASE_DIR / "mpc" / "Player-Data" / "lr_weights.txt"

# ── API ───────────────────────────────────────────────────────
API_HOST    = "0.0.0.0"
API_PORT    = 8000
API_TITLE   = "UPI Fraud Detection Service"
API_VERSION = "1.0.0"

# ── Training ──────────────────────────────────────────────────
DATASET_SIZE = 50_000
FRAUD_RATIO  = 0.05
TEST_SIZE    = 0.20
RANDOM_STATE = 42

# ── Logistic Regression ───────────────────────────────────────
LR_C            = 0.1
LR_MAX_ITER     = 1000
LR_SOLVER       = "lbfgs"
LR_CLASS_WEIGHT = "balanced"

# ── Business Rules ────────────────────────────────────────────
LARGE_TXN_THRESHOLD     = 50_000
NEW_ACCOUNT_DAYS        = 30
HIGH_VELOCITY_TXN       = 50
FAILED_ATTEMPT_RISK_MIN = 3
DEVICE_CHANGE_RISK_MIN  = 2

# ── Risk Score Bands ──────────────────────────────────────────
RISK_BANDS = {
    "CRITICAL": (75, 100),
    "HIGH":     (50, 74),
    "MEDIUM":   (25, 49),
    "LOW":      (0,  24),
}
RISK_ACTIONS = {
    "CRITICAL": "BLOCK",
    "HIGH":     "REVIEW",
    "MEDIUM":   "MONITOR",
    "LOW":      "ALLOW",
}

# ── Allowed Values for Validation ─────────────────────────────
UPI_APPS = ["GPay", "PhonePe", "Paytm", "BHIM", "Amazon Pay", "WhatsApp Pay"]
BANKS    = ["SBI", "HDFC", "ICICI", "Axis", "Kotak", "PNB", "Canara", "BOB"]
MERCHANT_CATEGORIES = [
    "Grocery", "Food", "Travel", "Shopping",
    "Bill", "Transfer", "Entertainment", "Medical"
]
STATES = [
    "Maharashtra", "Delhi", "Karnataka", "Tamil Nadu", "West Bengal",
    "Telangana", "Gujarat", "Rajasthan", "UP", "MP"
]
IP_COUNTRIES = ["India", "Foreign"]

# ── MP-SPDZ Settings ──────────────────────────────────────────
# Epochs and batch size for SGDLogistic inside MPC
MPC_EPOCHS     = 20
MPC_BATCH_SIZE = 2

# ── Logging ───────────────────────────────────────────────────
LOG_LEVEL  = "INFO"
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"