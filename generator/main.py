import argparse
import asyncio
import json
import time
from pathlib import Path
import random
from typing import Optional, Any

import httpx
from jinja2 import Template
from faker import Faker

fake = Faker()


def load_payload(source: Optional[str]) -> Any:
    """Load payload content. Supports:
        - Inline JSON string
        - Path to .json file
        - Path to .j2 template (Jinja2) rendered with Faker
        If None, returns a small default dict.
        """
    if not source:
        return {
            "event_type": "page_view",
            "user_id": fake.uuid4(),
            "path": fake.uri_path(),
            "ts": int(time.time() * 1000)
        }

    try:
        return json.loads(source)
    except Exception:
        pass

    # Resolve filesystem path robustly (supports running from repo root or generator/)
    p = Path(source)
    candidates = [
        p,  # as-provided, relative to current working dir
        Path(__file__).parent / p,  # relative to script directory
        Path(__file__).parent / p.name,  # filename-only beside this script
    ]
    for cand in candidates:
        if cand.exists():
            p = cand
            break
    else:
        tried = ", ".join(str(c) for c in candidates)
        raise FileNotFoundError(f"Payload source not found: {source} (tried: {tried})")

    if p.suffix == ".json":
        return json.loads(p.read_text(encoding="utf-8"))
    elif p.suffix == ".j2":
        tpl = Template(p.read_text(encoding="utf-8"))
        # Provide helpers inside the template context (use an RNG instance, plus direct funcs)
        rng = random.random()
        rendered = tpl.render(
            fake=fake,
            rand=rng,  # has .uniform/.randint/etc.
            uniform=random.uniform,  # direct helper
            randint=random.randint,
            choice=random.choice,
            randomf=random.random,
            now_ms=lambda: int(time.time() * 1000),
        )
        return json.loads(rendered)
    else:
        raise ValueError("Unsuppored payload file type. Use .json or .j2")


async def worker(name: str, client: httpx.AsyncClient, url: str, rps: float, duration: float,
                 payload_src: Optional[str], batch: int, jitter_ms: int):
    interval = 1.0 / rps if rps > 0 else 0
    end_t = time.monotonic() + duration if duration > 0 else float("inf")

    sent = 0
    while time.monotonic() < end_t:
        body = load_payload(payload_src)
        data = body
        if batch > 1:
            data = [load_payload(payload_src) for _ in range(batch)]

        try:
            resp = await client.post(url, json=data, timeout=10.0)
            _ = resp.json()
        except Exception as e:
            print("[{}] error: {}".format(name, e))

        sent += batch

        if interval > 0:
            # optional jitter to avoid lockstep
            if jitter_ms > 0:
                j = random.randint(0, jitter_ms) / 1000.0
            else:
                j = 0.0
            await asyncio.sleep(max(0.0, interval + j))
        else:
            await asyncio.sleep(0)

    return sent


async def run(url: str, rps: float, duration: float, concurrency: int, payload_src: Optional[str], batch: int,
              jitter_ms: int):
    async with httpx.AsyncClient() as client:
        per_worker_rps = max(rps / max(concurrency, 1), 0.0)
        tasks = [
            asyncio.create_task(worker(f"w{i}", client, url, per_worker_rps, duration, payload_src, batch, jitter_ms))
            for i in range(concurrency)
        ]
        counts = await asyncio.gather(*tasks)
        total = sum(counts)
        print("\nSent events:{} (batch={}, concurrenty={}, rps={}, duration={}s".format(total, batch, concurrency,
                                                                                        per_worker_rps, duration))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Adjustable async events generator")
    ap.add_argument("--url", default="http://localhost:8000/events", help="Ingest endpoint")
    ap.add_argument("--rps", type=float, default=50.0, help="Total requests per second across all workers")
    ap.add_argument("--duration", type=float, default=10.0, help="How long to run in seconds (0 = forever)")
    ap.add_argument("--concurrency", type=int, default=4, help="Number of async workers")
    ap.add_argument("--payload", help="Inline JSON, or path to .json/.j2 template")
    ap.add_argument("--batch", type=int, default=1, help="Items per request (array size)")
    ap.add_argument("--jitter-ms", type=int, default=50, help="Random sleep jitter per request")
    args = ap.parse_args()

    try:
        asyncio.run(run(args.url, args.rps, args.duration, args.concurrency, args.payload, args.batch, args.jitter_ms))
    except KeyboardInterrupt:
        print("\nCancelled")
