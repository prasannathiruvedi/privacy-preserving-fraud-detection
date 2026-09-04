from typing import Optional

from shared.constants import Decision, RISK_THRESHOLD_REJECT, RISK_THRESHOLD_REVIEW

def decide(risk: Optional[float]) -> Decision:
    if risk is None:
        return Decision.REVIEW
    if risk >= RISK_THRESHOLD_REJECT:
        return Decision.REJECT
    if risk >= RISK_THRESHOLD_REVIEW:
        return Decision.REVIEW
    return Decision.APPROVE
