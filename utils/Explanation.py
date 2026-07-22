# ============================================================
# utils/explanation.py — Explanation Engine
# Responsibility: Generate human-readable fraud explanations.
# Completely decoupled from model and API.
# ============================================================

import logging
from config import (
    NEW_ACCOUNT_DAYS, FAILED_ATTEMPT_RISK_MIN,
    LARGE_TXN_THRESHOLD, RISK_BANDS, RISK_ACTIONS
)

logger = logging.getLogger(__name__)


def get_risk_level(score: float) -> str:
    """Map fraud score (0–100) to risk level string."""
    for level, (low, high) in RISK_BANDS.items():
        if low <= score <= high:
            return level
    return "LOW"


def get_action(risk_level: str) -> str:
    """Map risk level to recommended action."""
    return RISK_ACTIONS.get(risk_level, "ALLOW")


def get_risk_emoji(action: str) -> str:
    return {"BLOCK": "🚫", "REVIEW": "⚠️", "MONITOR": "👁️", "ALLOW": "✅"}.get(action, "❓")


def build_explanation(txn: dict, score: float, risk_level: str) -> str:
    """
    Generate plain-English explanation of fraud score.
    Reads only from validated transaction dict.
    """
    signals = []
    amount  = float(txn.get("amount", 0))
    avg_amt = float(txn.get("sender_avg_amount_30d", 1)) + 1
    r_age   = float(txn.get("receiver_account_age_days", 365))
    s_age   = float(txn.get("sender_account_age_days", 365))
    failed  = float(txn.get("failed_attempts_24h", 0))

    if amount / avg_amt > 5:
        signals.append(f"amount ₹{amount:,.0f} is {amount/avg_amt:.0f}x the sender's 30-day average")
    if r_age < NEW_ACCOUNT_DAYS:
        signals.append(f"receiver account is only {int(r_age)} days old")
    if s_age < NEW_ACCOUNT_DAYS:
        signals.append(f"sender account is only {int(s_age)} days old")
    if txn.get("is_new_device"):
        signals.append("transaction initiated from a new/unrecognised device")
    if txn.get("is_new_beneficiary"):
        signals.append("first-ever transfer to this beneficiary")
    if failed >= FAILED_ATTEMPT_RISK_MIN:
        signals.append(f"{int(failed)} failed UPI attempts in the last 24 hours")
    if txn.get("ip_country") != "India":
        signals.append("login detected from a foreign IP address")
    if txn.get("sender_state") != txn.get("receiver_state"):
        signals.append(f"cross-state transfer ({txn.get('sender_state')} → {txn.get('receiver_state')})")
    if amount > LARGE_TXN_THRESHOLD:
        signals.append(f"high-value transaction above ₹{LARGE_TXN_THRESHOLD:,}")

    if not signals:
        signals.append("all transaction parameters are within normal range")

    explanation = f"Fraud score {score:.1f}/100 — {risk_level} risk. "
    explanation += "Signals detected: " + "; ".join(signals[:4]) + "."
    return explanation


def build_feature_risk_breakdown(txn: dict) -> dict:
    """
    Compute per-category risk scores (0–100) for UI display.
    Independent of model coefficients — rule-based breakdown.
    """
    amount  = float(txn.get("amount", 0))
    avg_amt = float(txn.get("sender_avg_amount_30d", 1)) + 1
    s_age   = float(txn.get("sender_account_age_days", 365))
    r_age   = float(txn.get("receiver_account_age_days", 365))

    return {
        "Amount Risk":      min(100, round((amount / avg_amt) * 20)),
        "Account Age Risk": round(max(0, 100 - min(s_age, r_age) / 3)),
        "Device Risk":      min(100, int(txn.get("is_new_device", 0)) * 50 + int(txn.get("is_new_beneficiary", 0)) * 50),
        "Velocity Risk":    min(100, round(float(txn.get("sender_txn_count_7d", 0)) * 0.5)),
        "Geography Risk":   round(
            (40 if txn.get("sender_state") != txn.get("receiver_state") else 0) +
            (60 if txn.get("ip_country") != "India" else 0)
        ),
        "Attempt Risk":     min(100, round(float(txn.get("failed_attempts_24h", 0)) * 15)),
    }