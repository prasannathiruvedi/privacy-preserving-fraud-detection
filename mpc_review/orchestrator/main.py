import asyncio
import os
import sys
from typing import Dict

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import httpx
from fastapi import FastAPI, HTTPException

from decision_engine.engine import decide
from shared.constants import GATEWAY_PORT, PARTICIPANT_PORTS, SessionStatus
from shared.models import EvaluateRequest, EvaluateResponse, SessionRecord
from shared.utils import generate_session_id, log

try:
    from mpc_integration.main import compute_risk
except ImportError:
    compute_risk = None

app = FastAPI(title="Fraud Orchestrator")

PARTICIPANT_URLS = {name.value: f"http://localhost:{port}" for name, port in PARTICIPANT_PORTS.items()}
GATEWAY_URL = f"http://localhost:{GATEWAY_PORT}"
SESSIONS: Dict[str, SessionRecord] = {}


def _build_mpc_inputs(gateway_features: dict, participant_features: Dict[str, dict]) -> dict:
    """
    Reshapes what /prepare (participant role + features) and /features
    (gateway) returned into the {sender, receiver, npci, gateway} shape
    mpc_integration.main.compute_risk() expects. SBI/HDFC swap which of
    "sender"/"receiver" they fill depending on the transaction — that's
    exactly why each participant reports its own role instead of the
    orchestrator guessing it from the institution name.
    """
    by_role = {}
    for institution, payload in participant_features.items():
        role = payload.get("role")
        if role in ("sender", "receiver", "npci"):
            by_role[role] = payload.get("features", {})

    missing = {"sender", "receiver", "npci"} - by_role.keys()
    if missing:
        raise ValueError(f"no participant reported role(s): {sorted(missing)}")

    return {
        "sender": by_role["sender"],
        "receiver": by_role["receiver"],
        "npci": by_role["npci"],
        "gateway": gateway_features,
    }


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

    # Gateway already computed its 15 owned features (and the raw amount)
    # when it first received the payment — pulled here the same way the
    # participants' features were pulled above.
    async with httpx.AsyncClient(timeout=10) as client:
        gw_resp = await client.get(f"{GATEWAY_URL}/features", params={"txn_id": req.txn_id})
    if gw_resp.status_code != 200:
        session.status = SessionStatus.FAILED
        raise HTTPException(status_code=502, detail=f"Gateway features unavailable for {req.txn_id}")
    gateway_features = gw_resp.json()

    session.status = SessionStatus.READY

    session.status = SessionStatus.COMPUTING
    try:
        if compute_risk is None:
            raise NotImplementedError
        mpc_inputs = _build_mpc_inputs(gateway_features, session.participant_features)
        risk = compute_risk(mpc_inputs)
    except NotImplementedError as e:
        log("ORCHESTRATOR", f"Module 4 (MPC) not available yet — falling back to risk=None ({e})")
        risk = None
    except Exception as e:
        # Anything else (subprocess failure, malformed MP-SPDZ output, a
        # participant not reporting the role we expected) is a real bug,
        # not "not implemented yet" — log it distinctly, but still fail
        # safe to REVIEW rather than crash the whole request.
        log("ORCHESTRATOR", f"Module 4 (MPC) computation failed: {e!r} — falling back to risk=None")
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
