import asyncio
import os
import sys
from typing import Dict

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import httpx
from fastapi import FastAPI, HTTPException

from decision_engine.engine import decide
from shared.constants import PARTICIPANT_PORTS, SessionStatus
from shared.models import EvaluateRequest, EvaluateResponse, SessionRecord
from shared.utils import generate_session_id, log

try:
    from mpc_integration.main import compute_risk
except ImportError:
    compute_risk = None

app = FastAPI(title="Fraud Orchestrator")

PARTICIPANT_URLS = {name.value: f"http://localhost:{port}" for name, port in PARTICIPANT_PORTS.items()}
SESSIONS: Dict[str, SessionRecord] = {}


@app.post("/evaluate", response_model=EvaluateResponse)
async def evaluate(req: EvaluateRequest):
    session_id = generate_session_id()
    session = SessionRecord(session_id=session_id, txn_id=req.txn_id, status=SessionStatus.CREATED)
    SESSIONS[session_id] = session
    log("ORCHESTRATOR", f"Created {session_id} for {req.txn_id}")

    session.status = SessionStatus.AWAITING_PARTICIPANTS
    async with httpx.AsyncClient(timeout=15) as client:
        responses = await asyncio.gather(
            *[
                client.post(f"{url}/prepare", json={"txn_id": req.txn_id, "session_id": session_id})
                for url in PARTICIPANT_URLS.values()
            ],
            return_exceptions=True,
        )

    for name, resp in zip(PARTICIPANT_URLS.keys(), responses):
        if isinstance(resp, Exception) or resp.status_code != 200:
            session.status = SessionStatus.FAILED
            raise HTTPException(status_code=502, detail=f"{name} failed to prepare for {req.txn_id}")
        session.participant_features[name] = resp.json()["features"]

    session.status = SessionStatus.READY

    session.status = SessionStatus.COMPUTING
    try:
        if compute_risk is None:
            raise NotImplementedError
        risk = compute_risk(session.participant_features)
    except NotImplementedError:
        log("ORCHESTRATOR", "Module 4 (MPC) not implemented yet — falling back to risk=None")
        risk = None

    session.risk = risk
    session.decision = decide(risk)
    session.status = SessionStatus.COMPLETED

    log("ORCHESTRATOR", f"{session_id} completed: risk={session.risk} decision={session.decision}")

    return EvaluateResponse(
        session_id=session_id,
        txn_id=req.txn_id,
        risk=session.risk,
        decision=session.decision.value,
    )


@app.get("/session/{session_id}", response_model=SessionRecord)
def get_session(session_id: str):
    session = SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.get("/sessions")
def list_sessions():
    return list(SESSIONS.values())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8010)
