import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import httpx
from fastapi import FastAPI

from shared.constants import ORCHESTRATOR_PORT

app = FastAPI(title="Review Dashboard")
ORCHESTRATOR_URL = f"http://localhost:{ORCHESTRATOR_PORT}"


@app.get("/sessions")
async def sessions():
    """Kept as plain JSON for now — swap for a real frontend later if it's worth the time."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{ORCHESTRATOR_URL}/sessions")
    return resp.json()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8020)
