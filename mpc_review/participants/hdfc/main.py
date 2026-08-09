import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from participants.common import create_participant_app

MOCK_DATA_PATH = os.path.join(os.path.dirname(__file__), "mock_data.json")
app = create_participant_app("HDFC", MOCK_DATA_PATH)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
