def make_decision(risk: float) -> str:
    if risk > 0.8:
        return "REJECT"
    elif risk > 0.5:
        return "REVIEW"
    else:
        return "APPROVE"