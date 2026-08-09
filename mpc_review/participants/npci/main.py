import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import json

from participants.common import create_participant_app, make_npci_feature_fn

MOCK_DATA_PATH = os.path.join(os.path.dirname(__file__), "mock_data.json")

with open(MOCK_DATA_PATH) as f:
    failed_attempts_by_account = json.load(f)  # {account_id: failed_attempts_24h}

app = create_participant_app(
    "NPCI", MOCK_DATA_PATH, compute_fn=make_npci_feature_fn(failed_attempts_by_account)
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
