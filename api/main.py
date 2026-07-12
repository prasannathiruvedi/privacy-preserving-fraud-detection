# ============================================================
# api/main.py — FastAPI Application
# Responsibility: HTTP layer only.
#   1. Validate all 18 inputs strictly (no silent defaults)
#   2. Call FraudService
#   3. Return structured response
#
# Run:
#   cd AI_MODEL
#   python model/train.py        ← run once first
#   python api/main.py           ← then start API
#   Visit: http://localhost:8000/docs
# ============================================================

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from api.service import FraudService
from config import (
    API_HOST, API_PORT, API_TITLE, API_VERSION,
    BANKS, IP_COUNTRIES, LOG_FORMAT, LOG_LEVEL,
    MERCHANT_CATEGORIES, STATES, UPI_APPS,
)

logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger(__name__)

# ── Singleton service ─────────────────────────────────────────
fraud_service = FraudService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("API starting — loading model artifacts...")
    fraud_service.startup()
    logger.info("API ready.")
    yield
    logger.info("API shutting down.")


app = FastAPI(
    title=API_TITLE,
    version=API_VERSION,
    description=(
        "UPI Fraud Detection Service — Logistic Regression Model.\n\n"
        "**All 18 fields are required.** Missing fields return HTTP 422.\n"
        "No silent default injection."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Input Schema — ALL 18 fields required ─────────────────────

class TransactionRequest(BaseModel):
    """
    UPI transaction payload.
    Every field is REQUIRED. Missing fields → HTTP 422 with clear error.
    """
    # Amount
    amount: float = Field(..., gt=0, description="Transaction amount in ₹ (must be > 0)")

    # UPI Apps
    sender_upi_app:   str = Field(..., description=f"One of: {UPI_APPS}")
    receiver_upi_app: str = Field(..., description=f"One of: {UPI_APPS}")

    # Banks
    sender_bank:   str = Field(..., description=f"One of: {BANKS}")
    receiver_bank: str = Field(..., description=f"One of: {BANKS}")

    # Category
    merchant_category: str = Field(..., description=f"One of: {MERCHANT_CATEGORIES}")

    # States
    sender_state:   str = Field(..., description=f"One of: {STATES}")
    receiver_state: str = Field(..., description=f"One of: {STATES}")

    # IP
    ip_country: str = Field(..., description="India or Foreign")

    # Account ages
    sender_account_age_days:   float = Field(..., ge=0, description="Sender account age in days")
    receiver_account_age_days: float = Field(..., ge=0, description="Receiver account age in days")

    # Transaction counts
    sender_txn_count_7d:   float = Field(..., ge=0, description="Sender txns in last 7 days")
    receiver_txn_count_7d: float = Field(..., ge=0, description="Receiver txns in last 7 days")

    # Average amount
    sender_avg_amount_30d: float = Field(..., ge=0, description="Sender avg amount last 30 days ₹")

    # Risk flags
    is_new_device:      int = Field(..., ge=0, le=1, description="1=new device, 0=known device")
    is_new_beneficiary: int = Field(..., ge=0, le=1, description="1=new beneficiary, 0=known")

    # Attempt history
    failed_attempts_24h: float = Field(..., ge=0, description="Failed UPI attempts in 24h")
    device_change_30d:   float = Field(..., ge=0, description="Device changes in last 30 days")

    # ── Validators ──────────────────────────────────────────────
    @field_validator("sender_upi_app", "receiver_upi_app")
    @classmethod
    def validate_upi(cls, v):
        if v not in UPI_APPS:
            raise ValueError(f"'{v}' is not a valid UPI app. Allowed: {UPI_APPS}")
        return v

    @field_validator("sender_bank", "receiver_bank")
    @classmethod
    def validate_bank(cls, v):
        if v not in BANKS:
            raise ValueError(f"'{v}' is not a valid bank. Allowed: {BANKS}")
        return v

    @field_validator("merchant_category")
    @classmethod
    def validate_category(cls, v):
        if v not in MERCHANT_CATEGORIES:
            raise ValueError(f"'{v}' is not a valid category. Allowed: {MERCHANT_CATEGORIES}")
        return v

    @field_validator("sender_state", "receiver_state")
    @classmethod
    def validate_state(cls, v):
        if v not in STATES:
            raise ValueError(f"'{v}' is not a valid state. Allowed: {STATES}")
        return v

    @field_validator("ip_country")
    @classmethod
    def validate_ip(cls, v):
        if v not in IP_COUNTRIES:
            raise ValueError(f"'{v}' is not valid. Allowed: {IP_COUNTRIES}")
        return v


class BatchRequest(BaseModel):
    transactions: list[TransactionRequest] = Field(
        ..., min_length=1, max_length=1000,
        description="List of 1–1000 transactions"
    )


# ── Response Schemas ─────────────────────────────────────────

class FraudResult(BaseModel):
    fraud_score:       float
    risk_level:        str
    action:            str
    emoji:             str
    top_risk_factors:  list[str]
    feature_risks:     dict[str, float]
    explanation:       str
    timestamp:         str


class PredictResponse(BaseModel):
    status: str
    result: FraudResult


class BatchResponse(BaseModel):
    status:  str
    count:   int
    results: list[FraudResult]


class HealthResponse(BaseModel):
    status:    str
    model:     str
    version:   str
    ready:     bool
    threshold: float


# ── Endpoints ────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health():
    """Check API and model status."""
    return HealthResponse(
        status    = "ok" if fraud_service.is_ready else "loading",
        model     = "Logistic Regression",
        version   = API_VERSION,
        ready     = fraud_service.is_ready,
        threshold = fraud_service.threshold,
    )


@app.post("/predict", response_model=PredictResponse, tags=["Prediction"])
async def predict(request: TransactionRequest):
    """
    Analyse a single UPI transaction for fraud.

    All 18 fields required. Missing field → HTTP 422 with field name + reason.
    """
    if not fraud_service.is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model not ready. Please retry in a moment.",
        )
    try:
        result = fraud_service.analyse(request.model_dump())
        return PredictResponse(status="success", result=FraudResult(**result))
    except Exception as e:
        logger.error(f"/predict error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/batch", response_model=BatchResponse, tags=["Prediction"])
async def batch(request: BatchRequest):
    """
    Analyse up to 1000 UPI transactions in one call.
    All fields required for each transaction.
    """
    if not fraud_service.is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model not ready. Please retry in a moment.",
        )
    try:
        txns    = [t.model_dump() for t in request.transactions]
        results = fraud_service.analyse_batch(txns)
        return BatchResponse(
            status  = "success",
            count   = len(results),
            results = [FraudResult(**r) for r in results],
        )
    except Exception as e:
        logger.error(f"/batch error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ── Entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host=API_HOST, port=API_PORT, reload=False)