from typing import Optional

from shared.constants import Decision, RISK_THRESHOLD_REJECT, RISK_THRESHOLD_REVIEW


def decide(risk: Optional[float]) -> Decision:
    """
    Applies static thresholds to a risk score to produce a final decision.
    risk is None when the MPC layer hasn't returned a score yet (e.g. during
    development before Module 4 is implemented) — that case is routed to
    REVIEW rather than silently approved or rejected.
    """
    if risk is None:
        return Decision.REVIEW
    if risk >= RISK_THRESHOLD_REJECT:
        return Decision.REJECT
    if risk >= RISK_THRESHOLD_REVIEW:
        return Decision.REVIEW
    return Decision.APPROVE
