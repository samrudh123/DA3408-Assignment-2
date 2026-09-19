import hashlib
import logging
import os
import time
import joblib
import redis
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

VERSION = "v1"

MODEL_PATH = "model.joblib"
REDIS_HOST = os.environ.get("REDIS_HOST", "cache")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "300"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("spam-api")

_model = None
_cache = None

def _cache_key(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"spam:{VERSION}:{digest}"


app = FastAPI(title="Spam Detection API", version=VERSION)

@app.on_event("startup")
def load_model_cache():
    global _model, _cache

    _model = joblib.load(MODEL_PATH)
    log.info("Loaded model from %s (version=%s)",
             MODEL_PATH, VERSION)

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


@app.on_event("shutdown")
def close_cache():
    if _cache is not None:
        _cache.close()


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
