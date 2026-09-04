import asyncio
import json
import math
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import httpx
from fastapi import FastAPI, HTTPException, Request

from shared.constants import ORCHESTRATOR_PORT, PARTICIPANT_PORTS
from shared.models import EvaluateResponse, PaymentRequest, TransactionMessage
from shared.utils import generate_txn_id, log

app = FastAPI(title="Payment Gateway")

PARTICIPANT_URLS = {name.value: f"http://localhost:{port}" for name, port in PARTICIPANT_PORTS.items()}
ORCHESTRATOR_URL = f"http://localhost:{ORCHESTRATOR_PORT}"

MERCHANT_CATEGORIES_PATH = Path(__file__).parent / "merchant_categories.json"

def _load_merchant_categories() -> dict:
    if MERCHANT_CATEGORIES_PATH.exists():
        return json.loads(MERCHANT_CATEGORIES_PATH.read_text())
    return {"_default": "Transfer"}

merchant_categories: dict = _load_merchant_categories()
DEFAULT_MERCHANT_CATEGORY = merchant_categories.get("_default", "Transfer")

DEVICE_HISTORY_PATH = Path(__file__).parent / "device_history.json"

def _load_device_history() -> dict:
    if DEVICE_HISTORY_PATH.exists():
        return json.loads(DEVICE_HISTORY_PATH.read_text())
    return {}

def _save_device_history(history: dict) -> None:
    DEVICE_HISTORY_PATH.write_text(json.dumps(history, indent=2))

device_history: dict = _load_device_history()

gateway_features: dict = {}

LARGE_TXN_THRESHOLD = 50_000
DEVICE_CHANGE_RISK_MIN = 2

def _infer_bank(account_id: str) -> str:
    match = re.match(r"[A-Za-z]+", account_id)
    return match.group(0).upper() if match else "UNKNOWN"

def _infer_ip_country(request: Request) -> str:
    client_ip = request.client.host if request.client else ""
    if client_ip in ("127.0.0.1", "::1") or client_ip.startswith(("10.", "192.168.")):
        return "India"
    return "Foreign"

def compute_gateway_features(payment: PaymentRequest, request: Request) -> dict:
    account = payment.from_account
    record = device_history.setdefault(account, {"known_devices": [], "device_changes_30d": 0})

    is_new_device = int(payment.device_id not in record["known_devices"])
    if is_new_device:
        record["known_devices"].append(payment.device_id)
        record["device_changes_30d"] += 1

    ip_country = _infer_ip_country(request)
    device_change_30d = record["device_changes_30d"]

    ts = datetime.fromisoformat(payment.timestamp.replace("Z", "+00:00"))
    hour = ts.hour
    day_of_week = ts.weekday()

    return {
        "amount": payment.amount,
        "hour": hour,
        "day_of_week": day_of_week,
        "is_weekend": int(day_of_week in (5, 6)),
        "is_night": int(hour < 6 or hour > 22),
        "log_amount": math.log1p(payment.amount),
        "is_large_txn": int(payment.amount > LARGE_TXN_THRESHOLD),
        "is_round_amount": int(payment.amount % 1000 == 0),
        "is_new_device": is_new_device,
        "device_change_30d": device_change_30d,
        "device_change_risk": int(device_change_30d >= DEVICE_CHANGE_RISK_MIN),
        "foreign_ip": int(ip_country != "India"),
        "sender_bank": _infer_bank(payment.from_account),
        "receiver_bank": _infer_bank(payment.to_account),
        "merchant_category": merchant_categories.get(payment.merchant, DEFAULT_MERCHANT_CATEGORY),
        "ip_country": ip_country,
    }

@app.post("/payment", response_model=EvaluateResponse)
async def receive_payment(payment: PaymentRequest, request: Request):
    txn_id = generate_txn_id()
    log("GATEWAY", f"Generated {txn_id} for {payment.from_account} -> {payment.to_account}")

    features = compute_gateway_features(payment, request)
    gateway_features[txn_id] = features
    _save_device_history(device_history)

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

@app.get("/features")
async def get_features(txn_id: str):
    if txn_id not in gateway_features:
        raise HTTPException(status_code=404, detail=f"No gateway features found for {txn_id}")
    return gateway_features[txn_id]

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)