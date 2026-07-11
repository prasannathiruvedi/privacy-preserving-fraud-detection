import uuid
import time
import asyncio
import hashlib
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("orchestrator")

app = FastAPI(title="Fraud Orchestrator")

# ---------------------------------------------------------------------------
# Config — participant endpoints (Module 2 services)
# ---------------------------------------------------------------------------

PARTICIPANTS = {
    "SBI": "http://localhost:8001",
    "HDFC": "http://localhost:8002",
    "NPCI": "http://localhost:8003",
}

DECISION_THRESHOLD = 0.7  # placeholder until decision engine is specced separately


# ---------------------------------------------------------------------------
# Session Manager
# ---------------------------------------------------------------------------

class SessionState(str, Enum):
    CREATED = "CREATED"
    PREPARING = "PREPARING"
    READY = "READY"
    COMPUTING = "COMPUTING"
    DECIDED = "DECIDED"
    FAILED = "FAILED"


class ParticipantState(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    FAILED = "FAILED"


@dataclass
class Session:
    session_id: str
    txn_id: str
    state: SessionState = SessionState.CREATED
    participant_status: dict[str, ParticipantState] = field(default_factory=dict)
    risk: Optional[float] = None
    decision: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    error: Optional[str] = None


class SessionManager:
    """In-memory session store. Swap for Redis if you need multi-instance later."""

    def __init__(self):
        self._sessions: dict[str, Session] = {}

    def create(self, txn_id: str) -> Session:
        session_id = f"SESSION-{uuid.uuid4().hex[:8].upper()}"
        session = Session(session_id=session_id, txn_id=txn_id)
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> Session:
        session = self._sessions.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session

    def update_state(self, session_id: str, state: SessionState):
        session = self._sessions[session_id]
        session.state = state
        logger.info(f"Session {session_id} -> {state}")


session_manager = SessionManager()


# ---------------------------------------------------------------------------
# Participant Manager
# ---------------------------------------------------------------------------

class ParticipantManager:
    """Fans out /prepare calls to each institution and collects READY acks."""

    def __init__(self, participants: dict[str, str], timeout: float = 5.0):
        self.participants = participants
        self.timeout = timeout

    async def _prepare_one(self, client: httpx.AsyncClient, session: Session,
                            txn_id: str, name: str, base_url: str):
        try:
            resp = await client.post(
                f"{base_url}/prepare",
                json={"txn_id": txn_id, "session_id": session.session_id},
            )
            resp.raise_for_status()
            body = resp.json()
            status_str = body.get("status", "READY")
            session.participant_status[name] = ParticipantState(status_str)
        except Exception as exc:
            logger.warning(f"Participant {name} failed to prepare: {exc}")
            session.participant_status[name] = ParticipantState.FAILED

    async def prepare_all(self, session: Session, txn_id: str) -> bool:
        session_manager.update_state(session.session_id, SessionState.PREPARING)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # Run all participant /prepare calls concurrently instead of
            # sequentially — SBI/HDFC/NPCI don't depend on each other.
            await asyncio.gather(*[
                self._prepare_one(client, session, txn_id, name, base_url)
                for name, base_url in self.participants.items()
            ])

        all_ready = all(
            status == ParticipantState.READY
            for status in session.participant_status.values()
        )
        session_manager.update_state(
            session.session_id,
            SessionState.READY if all_ready else SessionState.FAILED,
        )
        return all_ready


participant_manager = ParticipantManager(PARTICIPANTS)


# ---------------------------------------------------------------------------
# MPC Client
# ---------------------------------------------------------------------------

class MPCClient:
    """
    Wraps the call into the MP-SPDZ computation layer (Module 6).
    Each party runs its own process with private inputs; this client
    is responsible for kicking that off and collecting the output risk score.
    """

    async def trigger_mpc(self, session: Session) -> float:
        session_manager.update_state(session.session_id, SessionState.COMPUTING)
        # TODO: replace with real MP-SPDZ subprocess orchestration.
        # This should launch/signal each party's process (SBI, HDFC, NPCI)
        # and block until the output share is reconstructed into a risk score.
        risk = await self._run_mpc_stub(session)
        return risk

    async def _run_mpc_stub(self, session: Session) -> float:
        # Deterministic stub: same txn_id always produces the same risk score,
        # so runs are reproducible while Module 6 isn't wired in yet.
        digest = hashlib.sha256(session.txn_id.encode()).hexdigest()
        return round((int(digest[:8], 16) % 10000) / 10000, 4)


mpc_client = MPCClient()


# ---------------------------------------------------------------------------
# Result Handler / Decision Engine
# ---------------------------------------------------------------------------

class ResultHandler:
    def decide(self, risk: float) -> str:
        return "REJECT" if risk >= DECISION_THRESHOLD else "APPROVE"

    def finalize(self, session: Session, risk: float) -> dict:
        session.risk = risk
        session.decision = self.decide(risk)
        session_manager.update_state(session.session_id, SessionState.DECIDED)
        return {
            "session_id": session.session_id,
            "risk": session.risk,
            "decision": session.decision,
        }


result_handler = ResultHandler()


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

class EvaluateRequest(BaseModel):
    txn_id: str


class EvaluateResponse(BaseModel):
    session_id: str
    risk: float
    decision: str


@app.post("/evaluate", response_model=EvaluateResponse)
async def evaluate(req: EvaluateRequest):
    session = session_manager.create(req.txn_id)
    logger.info(f"Created session {session.session_id} for txn {req.txn_id}")

    ready = await participant_manager.prepare_all(session, req.txn_id)
    if not ready:
        session.error = "One or more participants failed to reach READY state"
        raise HTTPException(status_code=502, detail=session.error)

    risk = await mpc_client.trigger_mpc(session)
    result = result_handler.finalize(session, risk)

    logger.info(f"Session {session.session_id} decided: {result}")
    return result


@app.get("/session/{session_id}")
async def get_session(session_id: str):
    session = session_manager.get(session_id)
    return {
        "session_id": session.session_id,
        "txn_id": session.txn_id,
        "state": session.state,
        "participant_status": session.participant_status,
        "risk": session.risk,
        "decision": session.decision,
        "error": session.error,
    }