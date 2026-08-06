"""
Module 4 — per-transaction script renderer.

fraud_score.mpc is a TEMPLATE: everything the model needs except the
gateway's public, per-transaction constants (hour, amount, device
flags, bank ids, ...) is already baked in from model_constants.py.
This module fills in the remaining __PLACEHOLDER__ tokens for one
transaction and writes the concrete .mpc file MP-SPDZ actually compiles.

Recompiling per transaction costs a couple of seconds (fine for a demo /
research prototype). If that ever becomes a bottleneck, switch the
GATEWAY_* constants to sfix.get_input_from(2) secret inputs instead
(NPCI carrying them) and compile the script exactly once.
"""
from pathlib import Path
from typing import Dict

from mpc_integration import model_constants as C

TEMPLATE_PATH = Path(__file__).parent / "mpc" / "fraud_score.mpc"

# maps the template's GATEWAY_* placeholder name -> the feature name in
# model_constants.FOLDED_WEIGHTS / the key the gateway is expected to
# supply in its features dict.
GATEWAY_PLACEHOLDERS = {
    "__HOUR__": "hour",
    "__DAY_OF_WEEK__": "day_of_week",
    "__IS_WEEKEND__": "is_weekend",
    "__IS_NIGHT__": "is_night",
    "__LOG_AMOUNT__": "log_amount",
    "__IS_LARGE_TXN__": "is_large_txn",
    "__IS_ROUND_AMOUNT__": "is_round_amount",
    "__IS_NEW_DEVICE__": "is_new_device",
    "__DEVICE_CHANGE_30D__": "device_change_30d",
    "__DEVICE_CHANGE_RISK__": "device_change_risk",
    "__FOREIGN_IP__": "foreign_ip",
    "__SENDER_BANK__": "sender_bank",
    "__RECEIVER_BANK__": "receiver_bank",
    "__MERCHANT_CATEGORY__": "merchant_category",
    "__IP_COUNTRY__": "ip_country",
}


def render(gateway_features: Dict[str, float], amount: float) -> str:
    """
    gateway_features: the 15 gateway-owned model columns, already numeric
                       (categoricals pre-encoded via encode_categorical()).
    amount:            the raw transaction amount — needed for
                       amount_vs_avg_ratio but not itself a model column.
    Returns the fully-substituted .mpc source, ready to write to disk
    and hand to MP-SPDZ's compile.py.
    """
    missing = [f for f in GATEWAY_PLACEHOLDERS.values() if f not in gateway_features]
    if missing:
        raise ValueError(f"gateway_features is missing: {missing}")

    src = TEMPLATE_PATH.read_text()

    for placeholder, feature_name in GATEWAY_PLACEHOLDERS.items():
        src = src.replace(placeholder, repr(float(gateway_features[feature_name])))
    src = src.replace("__AMOUNT__", repr(float(amount)))

    weight_decls = "\n".join(
        f"W_{name.upper()} = {C.FOLDED_WEIGHTS[name]!r}" for name in C.FEATURE_ORDER
    )
    src = src.replace("__WEIGHT_DECLS__", weight_decls)
    src = src.replace("__FOLDED_BIAS__", repr(C.FOLDED_BIAS))
    src = src.replace("__LOGIT_THRESHOLD__", repr(C.LOGIT_THRESHOLD))

    remaining = [line for line in src.splitlines() if "__" in line and not line.strip().startswith("#")]
    if remaining:
        raise RuntimeError(f"template still has unfilled placeholders: {remaining}")

    return src


def encode_categorical(column: str, value: str) -> int:
    """Reproduce the exact LabelEncoder integer for `value` in `column`,
    using the classes_ the model was actually trained on. Unknown values
    (not seen during training) fall back to -1, matching FeatureEngineer's
    own behaviour in AI/features/engineer.py."""
    classes = C.ENCODER_CLASSES[column]
    try:
        return classes.index(value)
    except ValueError:
        return -1
