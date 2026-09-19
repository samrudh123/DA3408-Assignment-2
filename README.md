# Spam-Detection API — AIOps Module 3 Assignment

A REST API that classifies a short text message as `spam` or `ham`, packaged with Docker
and deployed on Kubernetes. Everything is CPU-only.

## API contract

| Endpoint | Request | Response |
|---|---|---|
| `POST /predict` | `{"text": "..."}` | `{"label": "spam"}` or `{"label": "ham"}` |
| `GET /healthz` | — | `200` if the model is loaded, `503` if not |


## Repository layout

| Path | Purpose |
|---|---|
| `q1/generate_dataset.py` | Writes `spam_dataset.csv` — 1,000 rows, `random.seed(42)`, deterministic |
| `q1/train_model.py` | Fits the TF-IDF + MultinomialNB pipeline, saves `model.joblib` |
| `q1/app.py` | The API. Used for Q1 (Docker) and Q4 (Kubernetes) |
| `q1/Dockerfile.naive` | Single-stage build on `python:3.11` — the size baseline |
| `q1/Dockerfile.multi` | Two-stage build, ships on `python:3.11-slim` |
| `q2/app.py` | Same API plus the Redis look-aside cache |
| `q2/Dockerfile` | Multi-stage build of the cached API |
| `q2/docker-compose.yml` | The two-service stack: `api` + `cache` |
| `requirements.txt` | Pinned dependencies (one copy per question folder) |
| `report.pdf` | The 2-page write-up |

Each question folder is a self-contained Docker build context, so `docker build` and
`docker compose` are run from inside `q1/` or `q2/`.

`spam_dataset.csv` and `model.joblib` are **not committed** — they are build outputs,
regenerated deterministically by the scripts above and by every Docker build.

## Prerequisites

- Docker (tested on 29.1.3)

## Question 1 — naive vs. multi-stage images

Both Dockerfiles generate the dataset and train the model during the build, so the image
is reproducible from source and the serving code never runs against a stale artefact.

```bash
cd q1
docker build -f Dockerfile.naive -t spam-api:naive .
docker build -f Dockerfile.multi -t spam-api:multi .

docker images | grep spam-api
```

### Run and test

```bash
docker run -d --name naive -p 8080:8080 spam-api:naive
docker run -d --name multi -p 8081:8080 spam-api:multi
```

For single stage build (port = 8080)
```bash
# health — expect {"status":"ok","version":"v1"}
curl http://localhost:8080/healthz

# spam — expect {"label":"spam"}
curl -X POST http://localhost:8080/predict \
  -H 'Content-Type: application/json' \
  -d '{"text":"WIN a FREE iPhone now! Click here: bit.ly/xyz123"}'

# ham — expect {"label":"ham"}
curl -X POST http://localhost:8080/predict \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hey, are we still meeting for lunch on Friday?"}'
```

For multi-stage build (port = 8081)
```bash
# health — expect {"status":"ok","version":"v1"}
curl http://localhost:8081/healthz

# spam — expect {"label":"spam"}
curl -X POST http://localhost:8081/predict \
  -H 'Content-Type: application/json' \
  -d '{"text":"WIN a FREE iPhone now! Click here: bit.ly/xyz123"}'

# ham — expect {"label":"ham"}
curl -X POST http://localhost:8081/predict \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hey, are we still meeting for lunch on Friday?"}'
```

## Question 2 — Docker Compose + Redis

`q2/` holds the cached variant of the API. `q2/app.py` adds a Redis look-aside cache in
front of the model; `q2/docker-compose.yml` runs it alongside `redis:7-alpine`.

The API reaches Redis at hostname `cache` — the Compose service name — because Compose
places both services on a shared user-defined network where names resolve via Docker's
embedded DNS.

```bash
cd q2
docker compose up -d --build
docker compose ps
```

### Cache miss vs. cache hit

Send the *same* text twice. The response body is always `{"label": ...}`; the cache
outcome and server-side latency are reported in headers.

```bash
MSG='{"text":"URGENT: Your account will be suspended. Verify at win-now.co/claim"}'

curl -s -D- -X POST http://localhost:8080/predict \
  -H 'Content-Type: application/json' -d "$MSG" | grep -Ei 'x-cache|x-response-time'

curl -s -D- -X POST http://localhost:8080/predict \
  -H 'Content-Type: application/json' -d "$MSG" | grep -Ei 'x-cache|x-response-time'
```

Observed:

| Call | `X-Cache` | `X-Response-Time-Ms` |
|---|---|---|
| 1st | `MISS` | 7.295 |
| 2nd | `HIT`  | 0.420 |

Both returned `{"label":"spam"}` — about a 17x speedup with an identical answer.

### Confirming the cache and the networking

```bash
# the cached entry and its TTL
docker compose exec cache redis-cli keys '*'
docker compose exec cache redis-cli ttl <key>

# service-name resolution from inside the api container
docker compose exec api getent hosts cache

# server-side view of the miss and the hit
docker compose logs api
```

### Cleanup

```bash
docker compose down
```

## Question 3 — Kubernetes Indexed Job

_Not yet implemented._

## Question 4 — Kubernetes Deployment

_Not yet implemented._
