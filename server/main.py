import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager

app = FastAPI(title="Events Ingest API", version="0.0.1")


def now_z() -> str:
    # RFC3339 UTC timestamp with 'Z', milliseconds precision
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


# Simple in-memory queue to simulate downstream processing
EVENT_QUEUE: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=10000)


class IngestResponse(BaseModel):
    accepted: int
    queued_size: int
    timestamp: str


@app.get("health")
async def health():
    return {"status": "ok", "time": now_z()}


@app.post("/events", response_model=IngestResponse)
async def ingest_events(request: Request):
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid JSON: {}".format(e))

    # Accept single event (dict) or list of events
    events: List[Dict[str, Any]]
    if isinstance(body, dict):
        events = [body]
    elif isinstance(body, list):
        events = body
    else:
        raise HTTPException(status_code=400, detail="Body must be a JSON object or array pf objects")

    accepted = 0
    for event in events:
        # Add basic metadata if missing
        event.setdefault("_recieved_at", now_z())
        event.setdefault("_source", "events-generator")
        try:
            EVENT_QUEUE.put_nowait(event)
            accepted += 1
        except asyncio.QueueFull:
            # backpressure simulation: reject when queue is full
            break
    return IngestResponse(
        accepted=accepted,
        queued_size=EVENT_QUEUE.qsize(),
        timestamp=now_z(),
    )


# Simple background consumer to show processing
async def consumer():
    while True:
        event = await EVENT_QUEUE.get()
        # Simulate some async work
        await asyncio.sleep(0.001)
        EVENT_QUEUE.task_done()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Launch a few consumer tasks to simulate downstream workers
    app.state.consumer_tasks = [asyncio.create_task(consumer()) for _ in range(4)]
    try:
        yield
    finally:
        # Shutdown: cancel consumers gracefully
        for t in app.state.consumer_tasks:
            t.cancel()
        await asyncio.gather(*app.state.consumer_tasks, return_exceptions=True)


# Tell FastAPI to use the lifespan context (replace deprecated @app.on_event hooks)
app.router.lifespan_context = lifespan

# Run with: uvicorn server.main:app --reload --port 8000