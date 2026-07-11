import asyncio
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import httpx
from fastapi import FastAPI, HTTPException

from shared.constants import ORCHESTRATOR_PORT, PARTICIPANT_PORTS
from shared.models import EvaluateResponse, PaymentRequest, TransactionMessage
from shared.utils import generate_txn_id, log

app = FastAPI(title="Payment Gateway")

PARTICIPANT_URLS = {name.value: f"http://localhost:{port}" for name, port in PARTICIPANT_PORTS.items()}
ORCHESTRATOR_URL = f"http://localhost:{ORCHESTRATOR_PORT}"


@app.post("/payment", response_model=EvaluateResponse)
async def receive_payment(payment: PaymentRequest):
    txn_id = generate_txn_id()
    log("GATEWAY", f"Generated {txn_id} for {payment.from_account} -> {payment.to_account}")

    txn_msg = TransactionMessage(txn_id=txn_id, **payment.model_dump())

    async with httpx.AsyncClient(timeout=10) as client:
        acks = await asyncio.gather(
            *[client.post(f"{url}/transaction", json=txn_msg.model_dump()) for url in PARTICIPANT_URLS.values()],
            return_exceptions=True,
        )

    for name, ack in zip(PARTICIPANT_URLS.keys(), acks):
        if isinstance(ack, Exception) or ack.status_code != 200:
            raise HTTPException(status_code=502, detail=f"{name} failed to acknowledge transaction {txn_id}")

    log("GATEWAY", f"All participants acknowledged {txn_id}, routing to orchestrator")

    async with httpx.AsyncClient(timeout=30) as client:
        eval_resp = await client.post(f"{ORCHESTRATOR_URL}/evaluate", json={"txn_id": txn_id})

    if eval_resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Orchestrator evaluation failed")

    return EvaluateResponse(**eval_resp.json())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
