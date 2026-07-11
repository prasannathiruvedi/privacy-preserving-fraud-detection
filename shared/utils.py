import uuid
from datetime import datetime, timezone


def generate_txn_id() -> str:
    return f"TX{uuid.uuid4().hex[:10].upper()}"


def generate_session_id() -> str:
    return f"SESSION{uuid.uuid4().hex[:8].upper()}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(tag: str, message: str) -> None:
    print(f"[{now_iso()}] [{tag}] {message}")
