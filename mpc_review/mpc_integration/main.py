"""
Module 4 — MPC Integration Layer

Wires the trained logistic-regression fraud model (AI/model/train.py)
into a real MP-SPDZ secure computation: SBI/HDFC (whichever is sender/
receiver for this transaction) and NPCI each secret-share their own
private features, the risk logit is computed inside the 3-party
replicated-ring protocol, and only the final logit/decision is revealed
— no party ever sees another party's raw feature values.

See mpc_integration/mpc/fraud_score.mpc for the actual secure program,
and mpc_integration/generate_model_constants.py / render_mpc_script.py
for how the model's weights get baked in.

Requires an MP-SPDZ checkout on disk (set MPSPDZ_HOME). If it isn't
configured, compute_risk() raises NotImplementedError — same contract
as the stub this replaces — so the orchestrator's existing fallback to
risk=None / REVIEW keeps working while this is being brought up on a
new machine.
"""
import os
import re
import subprocess
import sys
from math import exp
from pathlib import Path
from typing import Any, Dict

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mpc_integration import model_constants as C
from mpc_integration.render_mpc_script import render, encode_categorical

SCRIPT_NAME = "fraud_score"

# Set this to your MP-SPDZ checkout, e.g. export MPSPDZ_HOME=/home/you/MP-SPDZ
MPSPDZ_HOME = os.environ.get("MPSPDZ_HOME")

# Sequential input order — MUST match the get_input_from(N) call order in
# mpc_integration/mpc/fraud_score.mpc exactly, or values land on the wrong
# feature.
SENDER_ORDER = [
    "sender_account_age_days", "sender_txn_count_7d", "sender_avg_amount_30d",
    "high_sender_velocity", "sender_upi_app", "sender_state",
    "is_new_beneficiary", "is_new_sender_acc",
]
RECEIVER_ORDER = [
    "receiver_account_age_days", "receiver_txn_count_7d", "receiver_upi_app",
    "receiver_state", "is_new_receiver_acc",
]
NPCI_ORDER = ["failed_attempts_24h", "failed_attempt_risk"]

CATEGORICAL_COLUMNS = {
    "sender_upi_app", "receiver_upi_app", "sender_bank", "receiver_bank",
    "merchant_category", "sender_state", "receiver_state", "ip_country",
}


def _encode(name: str, value: Any) -> float:
    if name in CATEGORICAL_COLUMNS:
        return float(encode_categorical(name, value))
    return float(value)


def _write_player_data(mpspdz_home: Path, player: int, feature_names, features: Dict[str, Any]) -> None:
    values = [_encode(name, features[name]) for name in feature_names]
    input_path = mpspdz_home / "Player-Data" / f"Input-P{player}-0"
    input_path.parent.mkdir(parents=True, exist_ok=True)
    input_path.write_text(" ".join(repr(v) for v in values) + "\n")


def compute_risk(participant_inputs: Dict[str, Any]) -> float:
    """
    participant_inputs: {
        "sender":   {...raw features owned by whichever bank is sending},
        "receiver": {...raw features owned by whichever bank is receiving},
        "npci":     {...raw features owned by NPCI},
        "gateway":  {...raw features owned by the gateway, incl. "amount"},
    }
    (the orchestrator is responsible for resolving which physical bank —
    SBI or HDFC — fills "sender" vs "receiver" for THIS transaction; see
    orchestrator/main.py)

    returns: risk score in [0.0, 1.0] (sigmoid of the revealed logit)
    """
    if MPSPDZ_HOME is None:
        raise NotImplementedError(
            "MPSPDZ_HOME is not set — point it at your MP-SPDZ checkout to "
            "enable the real secure computation. Falling back to risk=None."
        )
    mpspdz_home = Path(MPSPDZ_HOME)
    if not mpspdz_home.exists():
        raise NotImplementedError(f"MPSPDZ_HOME={mpspdz_home} does not exist")

    sender = participant_inputs["sender"]
    receiver = participant_inputs["receiver"]
    npci = participant_inputs["npci"]
    gateway = participant_inputs["gateway"]

    gateway_encoded = {
        name: _encode(name, gateway[name])
        for name in C.FEATURE_ORDER
        if C.FEATURE_OWNER[name] == "GATEWAY"
    }

    script_source = render(gateway_encoded, amount=gateway["amount"])
    source_dir = mpspdz_home / "Programs" / "Source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / f"{SCRIPT_NAME}.mpc").write_text(script_source)

    _write_player_data(mpspdz_home, 0, SENDER_ORDER, sender)
    _write_player_data(mpspdz_home, 1, RECEIVER_ORDER, receiver)
    _write_player_data(mpspdz_home, 2, NPCI_ORDER, npci)

    subprocess.run(
        [sys.executable, "compile.py", "-R", "128", SCRIPT_NAME],
        cwd=mpspdz_home, check=True, capture_output=True, text=True,
    )

    # Scripts/ring.sh runs the semi-honest 3-party replicated-ring
    # protocol, spawning all three players as local processes — matches
    # the "3-party replicated secret-sharing" design from the earlier
    # planning session. Swap for another Scripts/*.sh if you move to a
    # different protocol (e.g. malicious-security Rep3, or MASCOT for a
    # non-honest-majority setting).
    result = subprocess.run(
        ["Scripts/ring.sh", SCRIPT_NAME],
        cwd=mpspdz_home, check=True, capture_output=True, text=True,
    )

    logit_match = re.search(r"RISK_LOGIT:(-?[\d.eE+-]+)", result.stdout)
    if not logit_match:
        raise RuntimeError(f"could not find RISK_LOGIT in MP-SPDZ output:\n{result.stdout}")

    logit = float(logit_match.group(1))
    risk = 1.0 / (1.0 + exp(-logit))
    return risk
