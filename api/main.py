# ============================================================
# api/main.py — FastAPI Application
# Responsibility: HTTP layer only.
# Validates input → calls FraudService → returns response.
# ============================================================

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator, model_validator

from api.service import FraudService
from config import (
    API_TITLE, API_VERSION, API_HOST, API_PORT,
    UPI_APPS, BANKS, MERCHANT_CATEGORIES, STATES, IP_COUNTRIES,
    LOG_FORMAT, LOG_LEVEL,
)

# ── Logging ──────────────────────────────────────────────────
logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger(__name__)

# ── Service (singleton) ───────────────────────────────────────
fraud_service = FraudService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model once at startup."""
    logger.info("API starting — loading model artifacts...")
    fraud_service.startup()
    logger.info("API ready to serve requests.")
    yield
    logger.info("API shutting down.")


# ── FastAPI App ───────────────────────────────────────────────
app = FastAPI(
    title=API_TITLE,
    version=API_VERSION,
    description="UPI Fraud Detection — Logistic Regression Model",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Input Schema (strict validation — no silent defaults) ─────

class TransactionRequest(BaseModel):
    """
    All fields are REQUIRED.
    No silent defaults — missing fields return validation error.
    """
    amount:                    float  = Field(..., gt=0, description="Transaction amount in ₹")
    sender_upi_app:            str    = Field(..., description="Sender UPI application")
    receiver_upi_app:          str    = Field(..., description="Receiver UPI application")
    sender_bank:               str    = Field(..., description="Sender's bank")
    receiver_bank:             str    = Field(..., description="Receiver's bank")
    merchant_category:         str    = Field(..., description="Transaction category")
    sender_state:              str    = Field(..., description="Sender's state")
    receiver_state:            str    = Field(..., description="Receiver's state")
    ip_country:                str    = Field(..., description="Country of login IP")
    sender_account_age_days:   float  = Field(..., ge=0, description="Sender account age in days")
    receiver_account_age_days: float  = Field(..., ge=0, description="Receiver account age in days")
    sender_txn_count_7d:       float  = Field(..., ge=0, description="Sender transactions in last 7 days")
    receiver_txn_count_7d:     float  = Field(..., ge=0, description="Receiver transactions in last 7 days")
    sender_avg_amount_30d:     float  = Field(..., ge=0, description="Sender's average amount in last 30 days")
    is_new_device:             int    = Field(..., ge=0, le=1, description="1 if new device, else 0")
    is_new_beneficiary:        int    = Field(..., ge=0, le=1, description="1 if new beneficiary, else 0")
    failed_attempts_24h:       float  = Field(..., ge=0, description="Failed UPI attempts in last 24h")
    device_change_30d:         float  = Field(..., ge=0, description="Number of device changes in 30 days")

    @field_validator("sender_upi_app", "receiver_upi_app")
    @classmethod
    def validate_upi_app(cls, v):
        if v not in UPI_APPS:
            raise ValueError(f"Invalid UPI app '{v}'. Must be one of: {UPI_APPS}")
        return v

    @field_validator("sender_bank", "receiver_bank")
    @classmethod
    def validate_bank(cls, v):
        if v not in BANKS:
            raise ValueError(f"Invalid bank '{v}'. Must be one of: {BANKS}")
        return v

    @field_validator("merchant_category")
    @classmethod
    def validate_category(cls, v):
        if v not in MERCHANT_CATEGORIES:
            raise ValueError(f"Invalid category '{v}'. Must be one of: {MERCHANT_CATEGORIES}")
        return v

    @field_validator("sender_state", "receiver_state")
    @classmethod
    def validate_state(cls, v):
        if v not in STATES:
            raise ValueError(f"Invalid state '{v}'. Must be one of: {STATES}")
        return v

    @field_validator("ip_country")
    @classmethod
    def validate_ip_country(cls, v):
        if v not in IP_COUNTRIES:
            raise ValueError(f"Invalid ip_country '{v}'. Must be one of: {IP_COUNTRIES}")
        return v


class BatchRequest(BaseModel):
    transactions: list[TransactionRequest] = Field(..., min_length=1, max_length=1000)


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
    status:  str
    result:  FraudResult


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
    from model.predictor import FraudPredictor
    return HealthResponse(
        status    = "ok" if fraud_service.is_ready else "loading",
        model     = "Logistic Regression",
        version   = API_VERSION,
        ready     = fraud_service.is_ready,
        threshold = fraud_service._predictor.threshold if fraud_service.is_ready else 0.0,
    )


@app.post("/predict", response_model=PredictResponse, tags=["Prediction"])
async def predict(request: TransactionRequest):
    """
    Analyse a single UPI transaction for fraud.

    All 18 fields are required. Missing fields are rejected
    with a descriptive validation error — no silent defaults.
    """
    if not fraud_service.is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model not loaded yet. Please retry shortly.",
        )
    try:
        result = fraud_service.analyse(request.model_dump())
        return PredictResponse(status="success", result=FraudResult(**result))
    except Exception as e:
        logger.error(f"Prediction error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/batch", response_model=BatchResponse, tags=["Prediction"])
async def batch(request: BatchRequest):
    """
    Analyse multiple UPI transactions in one call.
    Maximum 1000 transactions per request.
    """
    if not fraud_service.is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model not loaded yet. Please retry shortly.",
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
        logger.error(f"Batch error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ── Entry Point ───────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host=API_HOST, port=API_PORT, reload=False)