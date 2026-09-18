"""

A Redis look-aside cache sits in front of the model (Question 2). It is optional at
runtime: if Redis is unreachable -- e.g. this same image run under plain `docker run` for
Question 1 -- every request is simply a cache miss and the API still answers correctly.
That is what lets ONE image satisfy Q1's "identical behaviour" requirement and Q2's
"api service built from your multi-stage Dockerfile" requirement without a rebuild.

The response body is exactly {"label": ...} as specified. Cache outcome and latency are
reported in the X-Cache and X-Response-Time-Ms headers instead, so the Q2 speedup evidence
does not require bending the required contract.

Run locally:
    MODEL_PATH=model.joblib uvicorn app:app --host 0.0.0.0 --port 8080
"""
import hashlib
import logging
import os
import socket
import time
from contextlib import asynccontextmanager

import joblib
import redis
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

VERSION = os.environ.get("APP_VERSION", "v1")

MODEL_PATH = os.environ.get("MODEL_PATH", "model.joblib")
REDIS_HOST = os.environ.get("REDIS_HOST", "cache")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "300"))

POD_NAME = os.environ.get("POD_NAME", socket.gethostname())
NODE_NAME = os.environ.get("NODE_NAME", "unknown")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("spam-api")

_model = None
_cache = None

def _cache_key(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"spam:{VERSION}:{digest}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _model, _cache

    _model = joblib.load(MODEL_PATH)
    log.info("Loaded model from %s (version=%s, pod=%s, node=%s)",
             MODEL_PATH, VERSION, POD_NAME, NODE_NAME)

    client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True,
                         socket_connect_timeout=1, socket_timeout=1)
    try:
        client.ping()
        _cache = client
        log.info("Connected to Redis at %s:%s (TTL=%ss)", REDIS_HOST, REDIS_PORT, CACHE_TTL_SECONDS)
    except redis.RedisError as exc:
        _cache = None
        log.warning("Redis unavailable at %s:%s (%s) -- running without cache",
                    REDIS_HOST, REDIS_PORT, exc)

    yield

    if _cache is not None:
        _cache.close()


app = FastAPI(title="Spam Detection API", version=VERSION, lifespan=lifespan)

class PredictRequest(BaseModel):
    text: str = Field(..., min_length=1, description="The message to classify")


@app.get("/healthz")
def healthz(response: Response):
    if _model is None:
        raise HTTPException(status_code=503, detail="Model not loaded yet")
    return {
        "status": "ok",
        "version": VERSION,
        "cache": "connected" if _cache is not None else "disabled",
        "pod": POD_NAME,
        "node": NODE_NAME,
    }


@app.post("/predict")
def predict(request: PredictRequest, response: Response):
    if _model is None:
        raise HTTPException(status_code=503, detail="Model not loaded yet")

    text = request.text
    key = _cache_key(text)
    started = time.perf_counter()

    if _cache is not None:
        try:
            cached = _cache.get(key)
        except redis.RedisError as exc:
            log.warning("Cache read failed (%s) -- treating as a miss", exc)
            cached = None
        if cached is not None:
            elapsed_ms = (time.perf_counter() - started) * 1000
            response.headers["X-Cache"] = "HIT"
            response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.3f}"
            log.info("HIT  %.3fms  %r", elapsed_ms, text[:60])
            return {"label": cached}

    label = str(_model.predict([text])[0])

    if _cache is not None:
        try:
            _cache.setex(key, CACHE_TTL_SECONDS, label)
        except redis.RedisError as exc:
            log.warning("Cache write failed (%s)", exc)

    elapsed_ms = (time.perf_counter() - started) * 1000
    response.headers["X-Cache"] = "MISS"
    response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.3f}"
    log.info("MISS %.3fms  %r -> %s", elapsed_ms, text[:60], label)
    return {"label": label}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
