from enum import Enum


class SessionStatus(str, Enum):
    CREATED = "CREATED"
    AWAITING_PARTICIPANTS = "AWAITING_PARTICIPANTS"
    READY = "READY"
    COMPUTING = "COMPUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Decision(str, Enum):
    APPROVE = "APPROVE"
    REVIEW = "REVIEW"
    REJECT = "REJECT"


class ParticipantName(str, Enum):
    SBI = "SBI"
    HDFC = "HDFC"
    NPCI = "NPCI"


PARTICIPANT_PORTS = {
    ParticipantName.SBI: 8001,
    ParticipantName.HDFC: 8002,
    ParticipantName.NPCI: 8003,
}

GATEWAY_PORT = 8000
ORCHESTRATOR_PORT = 8010
DASHBOARD_PORT = 8020

# Decision thresholds — tune once real risk scores are flowing from Module 4
RISK_THRESHOLD_REJECT = 0.85
RISK_THRESHOLD_REVIEW = 0.5
