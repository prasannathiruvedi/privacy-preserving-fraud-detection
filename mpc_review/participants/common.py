import hashlib
import json
import os
from typing import Any, Callable, Dict, Optional

from fastapi import FastAPI, HTTPException

from mpc_integration.model_constants import ENCODER_CLASSES
from shared.models import (
    TransactionMessage,
    TransactionAck,
    PrepareRequest,
    PrepareResponse,
    StatusResponse,
)
from shared.utils import log

# Business-rule constants also used by AI/fixed/config.py — kept in sync by
# hand for now since the two repos aren't a shared package yet.
NEW_ACCOUNT_DAYS = 30
HIGH_VELOCITY_TXN = 50

ComputeFn = Callable[[Dict[str, Any]], Dict[str, Any]]


def _deterministic_upi_app(account_id: str) -> str:
    """
    mock_data.json has no upi_app field (it wasn't part of the Module 2
    schema). Placeholder: pick a deterministic app per account from a
    hash of the account id, so the same account always reports the same
    app across runs. Swap for a real field once mock_data.json — or a
    real bank's records — actually carries it.
    """
    apps = ENCODER_CLASSES["sender_upi_app"]  # same class list for sender/receiver
    idx = int(hashlib.sha256(account_id.encode()).hexdigest(), 16) % len(apps)
    return apps[idx]


def make_bank_feature_fn(mock_by_account: Dict[str, Dict[str, Any]]) -> ComputeFn:
    """
    Real feature computation for a retail bank (SBI/HDFC) against its own
    account records. A transaction has two account references but only
    one belongs to this institution for a given role — the caller
    (compute_local_features below) figures out sender vs receiver and
    asks for the matching role's feature set.

    "flagged_suspicious" and "device_match" below are NOT model inputs —
    they're not in mpc_integration.model_constants.FEATURE_ORDER, so
    _write_player_data() in mpc_integration/main.py never touches them.
    They exist purely for human inspection via GET /session/<id>, so a
    demo can show that SBI and HDFC each locally flagged an account AND
    that both saw the same (ring) device, without either bank ever
    seeing the other's raw account data — that cross-bank correlation
    is the whole point of running this under MPC in the first place.
    """

    def as_sender(account: str, other_account: str, txn_device_id: str) -> Dict[str, Any]:
        record = mock_by_account.get(account, {})
        account_age_days = record.get("account_age_days", 0)
        return {
            "sender_account_age_days": account_age_days,
            "sender_txn_count_7d": record.get("txn_count_7d", 0),
            "sender_avg_amount_30d": record.get("avg_amount", 0),
            "high_sender_velocity": int(record.get("txn_count_7d", 0) > HIGH_VELOCITY_TXN),
            "sender_upi_app": _deterministic_upi_app(account),
            "sender_state": record.get("state", "Delhi"),
            "is_new_beneficiary": int(other_account not in record.get("known_beneficiaries", [])),
            "is_new_sender_acc": int(account_age_days < NEW_ACCOUNT_DAYS),
            "flagged_suspicious": bool(record.get("suspicious", False)),
            "device_match": int(record.get("device_id") == txn_device_id) if "device_id" in record else False,
        }

    def as_receiver(account: str, txn_device_id: str) -> Dict[str, Any]:
        record = mock_by_account.get(account, {})
        account_age_days = record.get("account_age_days", 0)
        return {
            "receiver_account_age_days": account_age_days,
            "receiver_txn_count_7d": record.get("txn_count_7d", 0),
            "receiver_upi_app": _deterministic_upi_app(account),
            "receiver_state": record.get("state", "Delhi"),
            "is_new_receiver_acc": int(account_age_days < NEW_ACCOUNT_DAYS),
            "flagged_suspicious": bool(record.get("suspicious", False)),
            "device_match": int(record.get("device_id") == txn_device_id) if "device_id" in record else False,
        }

    def compute(txn: Dict[str, Any]) -> Dict[str, Any]:
        from_account = txn.get("from_account")
        to_account = txn.get("to_account")
        device_id = txn.get("device_id")
        result: Dict[str, Any] = {}
        if from_account in mock_by_account:
            result["role"] = "sender"
            result["features"] = as_sender(from_account, to_account, device_id)
        elif to_account in mock_by_account:
            result["role"] = "receiver"
            result["features"] = as_receiver(to_account, device_id)
        else:
            result["role"] = "none"
            result["features"] = {}
        return result

    return compute


def make_npci_feature_fn(failed_attempts_by_account: Dict[str, int]) -> ComputeFn:
    """
    NPCI is the routing/switch node, not an account-holding bank — its
    mock_data.json is shaped as {account_id: failed_attempts_24h}, since
    the UPI switch is the one place that sees failed attempts across
    every bank, not just one institution's own app.
    """

    def compute(txn: Dict[str, Any]) -> Dict[str, Any]:
        sender_account = txn.get("from_account")
        failed = failed_attempts_by_account.get(sender_account, 0)
        return {
            "role": "npci",
            "features": {
                "failed_attempts_24h": failed,
                "failed_attempt_risk": int(failed >= 3),
            },
        }

    return compute


def create_participant_app(
    institution: str,
    mock_data_path: str,
    compute_fn: Optional[ComputeFn] = None,
) -> FastAPI:
    """
    Builds a participant-node FastAPI app for a single institution.
    Retail banks (SBI/HDFC) share make_bank_feature_fn; NPCI passes its
    own compute_fn (its mock data has a different shape entirely — see
    make_npci_feature_fn). Everything else — the HTTP scaffolding, the
    pending-transaction bookkeeping — is identical across institutions,
    so it stays in this shared factory.
    """
    app = FastAPI(title=f"{institution} Participant Node")

    pending_transactions: Dict[str, Dict[str, Any]] = {}

    raw_mock_data: Any = {}
    if os.path.exists(mock_data_path):
        with open(mock_data_path, "r") as f:
            raw_mock_data = json.load(f)

    if compute_fn is not None:
        compute_local_features = compute_fn
    elif isinstance(raw_mock_data, list):
        mock_by_account = {r.get("account_id", ""): r for r in raw_mock_data}
        compute_local_features = make_bank_feature_fn(mock_by_account)
    else:
        raise ValueError(
            f"{institution}: mock_data.json is not a list and no compute_fn "
            "was provided — pass one explicitly (see participants/npci/main.py)"
        )

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
