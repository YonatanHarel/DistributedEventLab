## Start the API (with Swagger)
```shell
python -m venv .venv && source .venv/bin/activate
pip install -r server/requirements.txt
uvicorn server.main:app --reload --port 8000
```

Open Swagger UI at: http://localhost:8000/docs</br>
Healthcheck: http://localhost:8000/health

## Run the generator
```shell
python -m venv .gvenv && source .gvenv/bin/activate
pip install -r generator/requirements.txt
python generator/main.py --url http://localhost:8000/events --rps 200 --duration 30 --concurrency 8 --batch 5 \
  --payload generator/sample_template.j2
```
Path tip: If you run from the repo root, use --payload generator/sample_template.j2. If you cd generator/, use --payload sample_template.j2. The generator now also auto-resolves filenames relative to the script directory.

### Adjustability knobs:
- --rps: total requests per second (spread across all workers).
- --concurrency: number of async workers.
- --batch: number of items per request (sends an array per POST).
- --duration: run time in seconds (0 = run until Ctrl+C).
- --jitter-ms: random delay added to each interval to avoid thundering herd.

## Try a single curl
```http request
curl -X POST http://localhost:8000/events \
  -H 'Content-Type: application/json' \
  -d '{"event_type":"demo","value":42}'
```

### Notes & next steps
- The API already exposes Swagger (/docs) via FastAPI.
- The in-memory queue + background consumers simulate downstream processing; swap for Kafka/Rabbit/SQS later.
- Add persistence (e.g., Postgres/ClickHouse) and metrics (Prometheus) as your next learning steps.
- Backpressure demo: the API will stop accepting when the queue is full; widen maxsize or add HTTP 429.