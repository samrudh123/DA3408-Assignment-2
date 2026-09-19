# Spam-Detection API — AIOps Module 3 Assignment

A REST API that classifies a short text message as `spam` or `ham`, packaged with Docker
and deployed on Kubernetes. Everything is CPU-only.

## API contract

| Endpoint | Request | Response |
|---|---|---|
| `POST /predict` | `{"text": "..."}` | `{"label": "spam"}` or `{"label": "ham"}` |
| `GET /healthz` | — | `200` if the model is loaded, `503` if not |


## Repository layout

| File | Purpose |
|---|---|
| `generate_dataset.py` | Writes `spam_dataset.csv` — 1,000 rows, `random.seed(42)`, deterministic |
| `train_model.py` | Fits the TF-IDF + MultinomialNB pipeline, saves `model.joblib` |
| `q1_app.py` | The API. Used for Q1 (Docker) and Q4 (Kubernetes) |
| `app.py` | Same API plus the Redis look-aside cache. Used for Q2 (Compose) |
| `Dockerfile.naive` | Single-stage build on `python:3.11` — the size baseline |
| `Dockerfile.multi` | Two-stage build, ships on `python:3.11-slim` |
| `requirements.txt` | Pinned dependencies, shared by both builds |
| `report.pdf` | The 2-page write-up |

`spam_dataset.csv` and `model.joblib` are **not committed** — they are build outputs,
regenerated deterministically by the scripts above and by every Docker build.

## Prerequisites

- Docker (tested on 29.1.3)

## Question 1 — naive vs. multi-stage images

Both Dockerfiles generate the dataset and train the model during the build, so the image
is reproducible from source and the serving code never runs against a stale artefact.

```bash
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

_Not yet implemented._

## Question 3 — Kubernetes Indexed Job

_Not yet implemented._

## Question 4 — Kubernetes Deployment

_Not yet implemented._
