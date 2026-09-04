from pathlib import Path
from typing import Dict

from mpc_integration import model_constants as C

TEMPLATE_PATH = Path(__file__).parent / "mpc" / "fraud_score.mpc"

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
    classes = C.ENCODER_CLASSES[column]
    try:
        return classes.index(value)
    except ValueError:
        return -1
