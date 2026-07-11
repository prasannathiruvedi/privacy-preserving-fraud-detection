from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

from shared.constants import Decision, SessionStatus


# ---- Gateway (Module 1) ----

class PaymentRequest(BaseModel):
    from_account: str
    to_account: str
    amount: float
    timestamp: str
    device_id: str
    merchant: str


class PaymentResponse(BaseModel):
    txn_id: str


# ---- Participant Nodes (Module 2) ----

class TransactionMessage(BaseModel):
    txn_id: str
    from_account: str
    to_account: str
    amount: float
    timestamp: str
    device_id: str
    merchant: str


class TransactionAck(BaseModel):
    txn_id: str
    institution: str
    received: bool = True


class PrepareRequest(BaseModel):
    txn_id: str
    session_id: str


class PrepareResponse(BaseModel):
    txn_id: str
    institution: str
    ready: bool
    features: Dict[str, Any]


class StatusResponse(BaseModel):
    txn_id: str
    institution: str
    status: str


# ---- Orchestrator (Module 3) ----

class EvaluateRequest(BaseModel):
    txn_id: str


class EvaluateResponse(BaseModel):
    session_id: str
    txn_id: str
    risk: Optional[float] = None
    decision: str


class SessionRecord(BaseModel):
    session_id: str
    txn_id: str
    status: SessionStatus
    risk: Optional[float] = None
    decision: Optional[Decision] = None
    participant_features: Dict[str, Any] = Field(default_factory=dict)
