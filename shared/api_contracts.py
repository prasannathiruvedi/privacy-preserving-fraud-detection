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
