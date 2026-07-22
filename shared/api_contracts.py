"""
Central reference for the request/response contract each service exposes.
The actual Pydantic models live in shared.models — this file exists so the
full set of API shapes can be read in one place instead of hunting through
every service, and so the project report has one source to point at.
"""
from shared.models import (
    PaymentRequest,
    PaymentResponse,
    TransactionMessage,
    TransactionAck,
    PrepareRequest,
    PrepareResponse,
    StatusResponse,
    EvaluateRequest,
    EvaluateResponse,
    SessionRecord,
)

GATEWAY_ENDPOINTS = {
    "POST /payment": (PaymentRequest, EvaluateResponse),
}

PARTICIPANT_ENDPOINTS = {
    "POST /transaction": (TransactionMessage, TransactionAck),
    "POST /prepare": (PrepareRequest, PrepareResponse),
    "GET /status": (None, StatusResponse),
}

ORCHESTRATOR_ENDPOINTS = {
    "POST /evaluate": (EvaluateRequest, EvaluateResponse),
    "GET /session/{session_id}": (None, SessionRecord),
    "GET /sessions": (None, "list[SessionRecord]"),
}
