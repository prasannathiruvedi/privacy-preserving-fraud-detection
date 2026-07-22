import json
import os
from typing import Any, Dict

from fastapi import FastAPI, HTTPException

from shared.models import (
    TransactionMessage,
    TransactionAck,
    PrepareRequest,
    PrepareResponse,
    StatusResponse,
)
from shared.utils import log


def create_participant_app(institution: str, mock_data_path: str) -> FastAPI:
    """
    Builds a participant-node FastAPI app for a single institution.
    Each bank (SBI/HDFC/NPCI) is the same structure with different data,
    so this factory keeps that logic in one place instead of duplicated
    three times.
    """
    app = FastAPI(title=f"{institution} Participant Node")

    pending_transactions: Dict[str, Dict[str, Any]] = {}

    mock_records = []
    if os.path.exists(mock_data_path):
        with open(mock_data_path, "r") as f:
            mock_records = json.load(f)
    mock_by_account: Dict[str, Dict[str, Any]] = {
        r.get("account_id", ""): r for r in mock_records
    }

    def compute_local_features(txn: Dict[str, Any]) -> Dict[str, Any]:
        """
        Placeholder feature computation drawn from the mock dataset.
        Swap this out for real feature engineering against this
        institution's own transaction/device/beneficiary history —
        point mock_data_path at the Module 2 generated JSON, or replace
        this function entirely once real data is wired in.

        A transaction has two account references (from_account, to_account)
        but only one of them belongs to this institution — check both and
        use whichever one this institution actually recognizes.
        """
        from_account = txn.get("from_account")
        to_account = txn.get("to_account")
        account = from_account if from_account in mock_by_account else to_account
        record = mock_by_account.get(account, {})
        return {
            "institution": institution,
            "account_known": account in mock_by_account,
            "historical_avg_amount": record.get("avg_amount", 0),
            "device_match": record.get("device_id") == txn.get("device_id"),
            "flagged_suspicious": record.get("suspicious", False),
        }

    @app.post("/transaction", response_model=TransactionAck)
    def receive_transaction(msg: TransactionMessage):
        pending_transactions[msg.txn_id] = {"message": msg.model_dump(), "status": "PENDING"}
        log(institution, f"Received txn {msg.txn_id}")
        return TransactionAck(txn_id=msg.txn_id, institution=institution)

    @app.post("/prepare", response_model=PrepareResponse)
    def prepare(req: PrepareRequest):
        entry = pending_transactions.get(req.txn_id)
        if entry is None:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown txn_id {req.txn_id} at {institution}",
            )
        features = compute_local_features(entry["message"])
        entry["status"] = "READY"
        entry["features"] = features
        log(institution, f"Prepared features for {req.txn_id} (session {req.session_id})")
        return PrepareResponse(
            txn_id=req.txn_id, institution=institution, ready=True, features=features
        )

    @app.get("/status", response_model=StatusResponse)
    def status(txn_id: str):
        entry = pending_transactions.get(txn_id)
        if entry is None:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown txn_id {txn_id} at {institution}",
            )
        return StatusResponse(txn_id=txn_id, institution=institution, status=entry["status"])

    return app
