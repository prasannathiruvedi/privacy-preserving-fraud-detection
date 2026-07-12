# ============================================================
# utils/explanation.py — Explanation Engine
# Responsibility: Generate human-readable fraud explanations.
# Fully decoupled from model, API, and feature engineering.
# ============================================================

import logging
from config import (
    FAILED_ATTEMPT_RISK_MIN, LARGE_TXN_THRESHOLD,
    NEW_ACCOUNT_DAYS, RISK_ACTIONS, RISK_BANDS,
)

logger = logging.getLogger(__name__)


def get_risk_level(score: float) -> str:
    """Map fraud score (0–100) → risk level string."""
    for level, (low, high) in RISK_BANDS.items():
        if low <= score <= high:
            return level
    return "LOW"


def get_action(risk_level: str) -> str:
    """Map risk level → recommended action."""
    return RISK_ACTIONS.get(risk_level, "ALLOW")


def get_emoji(action: str) -> str:
    return {"BLOCK": "🚫", "REVIEW": "⚠️", "MONITOR": "👁️", "ALLOW": "✅"}.get(action, "❓")


def build_explanation(txn: dict, score: float, risk_level: str) -> str:
    """
    Plain-English explanation of why this fraud score was given.
    Reads only validated transaction fields — no model internals.
    """
    signals = []
    amount  = float(txn.get("amount", 0))
    avg_amt = float(txn.get("sender_avg_amount_30d", 1)) + 1
    r_age   = float(txn.get("receiver_account_age_days", 365))
    s_age   = float(txn.get("sender_account_age_days", 365))
    failed  = float(txn.get("failed_attempts_24h", 0))

    if amount / avg_amt > 5:
        signals.append(
            f"amount ₹{amount:,.0f} is {amount/avg_amt:.0f}× sender's 30-day average"
        )
    if r_age < NEW_ACCOUNT_DAYS:
        signals.append(f"receiver account is only {int(r_age)} days old")
    if s_age < NEW_ACCOUNT_DAYS:
        signals.append(f"sender account is only {int(s_age)} days old")
    if txn.get("is_new_device"):
        signals.append("transaction from a new/unrecognised device")
    if txn.get("is_new_beneficiary"):
        signals.append("first-ever transfer to this beneficiary")
    if failed >= FAILED_ATTEMPT_RISK_MIN:
        signals.append(f"{int(failed)} failed UPI attempts in last 24 hours")
    if txn.get("ip_country") != "India":
        signals.append("login from a foreign IP address")
    if txn.get("sender_state") != txn.get("receiver_state"):
        signals.append(
            f"cross-state transfer ({txn.get('sender_state')} → {txn.get('receiver_state')})"
        )
    if amount > LARGE_TXN_THRESHOLD:
        signals.append(f"high-value transaction above ₹{LARGE_TXN_THRESHOLD:,}")

    if not signals:
        signals.append("all transaction parameters within normal range")

    return (
        f"Fraud score {score:.1f}/100 — {risk_level} risk. "
        f"Key signals: " + "; ".join(signals[:4]) + "."
    )


def build_feature_risk_breakdown(txn: dict) -> dict:
    """
    Per-category risk scores (0–100) for UI display.
    Rule-based — independent of model coefficients.
    """
    amount  = float(txn.get("amount", 0))
    avg_amt = float(txn.get("sender_avg_amount_30d", 1)) + 1
    s_age   = float(txn.get("sender_account_age_days", 365))
    r_age   = float(txn.get("receiver_account_age_days", 365))
    return {
        "Amount Risk":      min(100, round((amount / avg_amt) * 20)),
        "Account Age Risk": round(max(0, 100 - min(s_age, r_age) / 3)),
        "Device Risk":      min(100,
                                int(txn.get("is_new_device", 0)) * 50 +
                                int(txn.get("is_new_beneficiary", 0)) * 50),
        "Velocity Risk":    min(100, round(float(txn.get("sender_txn_count_7d", 0)) * 0.5)),
        "Geography Risk":   min(100, round(
                                (40 if txn.get("sender_state") != txn.get("receiver_state") else 0) +
                                (60 if txn.get("ip_country") != "India" else 0)
                            )),
        "Attempt Risk":     min(100, round(float(txn.get("failed_attempts_24h", 0)) * 15)),
    }