"""
Module 4 — MPC Integration Layer

Intentionally left empty. This is where MP-SPDZ gets wired in: compile the
secure computation program, launch the parties, feed each participant's
prepared features in as private input, execute, and collect the resulting
risk score.

The orchestrator imports compute_risk() and catches NotImplementedError,
falling back to risk=None (-> REVIEW) so the rest of the pipeline stays
testable while this module is being built out.
"""
from typing import Any, Dict


def compute_risk(participant_inputs: Dict[str, Any]) -> float:
    """
    participant_inputs: {"SBI": {...features}, "HDFC": {...features}, "NPCI": {...features}}
    returns: risk score in [0.0, 1.0]
    """
    raise NotImplementedError("Module 4 (MPC integration) not implemented yet")
