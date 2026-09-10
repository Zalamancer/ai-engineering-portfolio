"""Local test target for 'external writes' (a stand-in for a team webhook). Stores every POST so
tests can assert that a killed-and-restarted worker delivered exactly once.
    uv run uvicorn agentops.testtarget:app --port 8099"""
from __future__ import annotations

import time

from fastapi import FastAPI, Request

app = FastAPI(title="agentops local test target")
RECEIVED: list[dict] = []


@app.post("/hook")
async def hook(req: Request):
    body = await req.json()
    RECEIVED.append({"ts": time.time(), "body": body})
    return {"ok": True, "received": len(RECEIVED)}


@app.get("/received")
def received():
    return {"count": len(RECEIVED), "items": RECEIVED}


@app.delete("/received")
def clear():
    RECEIVED.clear()
    return {"ok": True}
