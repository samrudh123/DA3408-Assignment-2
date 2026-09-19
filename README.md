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
| `q3/generate_shards.py` | Writes 8 seeded CSV shards with known invalid-row counts |
| `q3/validate_shard.py` | Validates the shard named by `JOB_COMPLETION_INDEX` |
| `q3/collect_results.py` | Reads per-shard results from pod logs via the Kubernetes API |
| `q3/job.yaml` | The Indexed Job |
| `q4/deployment.yaml`, `q4/service.yaml` | 2-replica Deployment and NodePort Service |
| `requirements.txt` | Pinned dependencies (one copy per question folder) |
| `report.pdf` | The 2-page write-up |

Each question folder is a self-contained Docker build context, so `docker build` and
`docker compose` are run from inside `q1/` or `q2/`.

`spam_dataset.csv` and `model.joblib` are **not committed** — they are build outputs,
regenerated deterministically by the scripts above and by every Docker build.

## Prerequisites

- Docker (tested on 29.1.3) — Questions 1 and 2
- minikube (tested on v1.38.1) and kubectl (v1.37.0) — Questions 3 and 4
- Python 3.11 with `venv`, for the Question 3 results collector

Questions 3 and 4 need a 2-node cluster with 2 allocatable CPUs per node, started with the
`minikube start` command in the Question 3 section. The host needs at least 4 CPUs free;
the docker driver is assumed throughout.

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
| 1st | `MISS` | 3.068 |
| 2nd | `HIT`  | 0.152 |

Both returned `{"label":"spam"}` — about a 20x speedup with an identical answer.

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

`q3/` validates 8 shards of synthetic user-signup records. Each shard contains a known,
seeded number of rows with malformed emails or missing required fields. One pod validates
exactly one shard, selected by its `JOB_COMPLETION_INDEX`.

This workload is independent of the spam-detection API.

### Cluster

The `--cpus 2` alone does not
produce 2 allocatable CPUs, minikube's docker driver leaves the node containers unlimited and kubelet
reports every host CPU as allocatable. Reserving the remainder makes the constraint real:

```bash
minikube start --nodes 2 --cpus 2 --memory 2048 --driver=docker \
  --extra-config=kubelet.system-reserved=cpu=$(( $(nproc) - 2 ))

kubectl get nodes -o custom-columns='NODE:.metadata.name,CPU:.status.allocatable.cpu'
```

`nproc` reports the host's CPU count, so `$(( $(nproc) - 2 ))` reserves everything except
the 2 CPUs per node.

### Build and load the image

minikube cannot pull from the host daemon, so the image is side-loaded and the manifest
uses `imagePullPolicy: IfNotPresent`:

```bash
cd q3
docker build -t signup-validator:latest .
minikube image load signup-validator:latest
```

The shards are generated during the build, so they are reproducible and never committed.
Running `python generate_shards.py` locally prints the expected invalid-row counts.

### Run the Job and watch concurrency

```bash
kubectl apply -f job.yaml
kubectl get pods -o wide -w
```

Each pod holds for `HOLD_SECONDS` (5s) so the concurrent wave is observable — without it
the pods finish faster than the watch can show them running together.

### Collect results through the Kubernetes API

```bash
python3 -m venv kube-q3
source kube-q3/bin/activate
pip install -r requirements.txt

python collect_results.py --job signup-validation
```

If `python3 -m venv` reports that `ensurepip` is unavailable, either install the matching
`python3.x-venv` package or use `uv`:

```bash
uv venv --python 3.11 kube-q3
uv pip install --python kube-q3/bin/python -r requirements.txt
./kube-q3/bin/python collect_results.py --job signup-validation
```

Results are read from pod logs via `read_namespaced_pod_log()`, not from a shared volume —
minikube's default storage provisioner binds a PersistentVolume to one node, and these pods
run on both.

Observed:

```
SHARD  TOTAL   INVALID   NODE                  POD
0      100     8         minikube-m02          signup-validation-0-b4ssn
1      100     12        minikube-m02          signup-validation-1-px6mx
2      100     6         minikube              signup-validation-2-t52tz
3      100     20        minikube-m02          signup-validation-3-j6qsz
4      100     10        minikube-m02          signup-validation-4-nw5tq
5      100     17        minikube-m02          signup-validation-5-zwzgm
6      100     6         minikube              signup-validation-6-vhs2n
7      100     11        minikube-m02          signup-validation-7-zrzld

shards=8  invalid_total=90
```

The counts match what `generate_shards.py` printed at build time.

### Cleanup

```bash
kubectl delete -f job.yaml
```

To tear the cluster down entirely:

```bash
minikube delete --all
```

Question 4 reuses this same cluster, so leave it running if you are continuing.

## Question 4 — Kubernetes Deployment

`q4/` deploys the Question 1 API as a Deployment with 2 replicas behind a NodePort Service.

```bash
minikube start --nodes 2 --cpus 2 --memory 2048 --driver=docker \
  --extra-config=kubelet.system-reserved=cpu=$(( $(nproc) - 2 ))
```

### Build, load and apply

```bash
cd q4
docker build -t spam-api:v1 .
minikube image load spam-api:v1

kubectl apply -f deployment.yaml -f service.yaml
kubectl get pods -o wide -l app=spam-api
```

### Reach the Service

```bash
MK=$(minikube ip)
curl http://$MK:30080/healthz
curl -X POST http://$MK:30080/predict \
  -H 'Content-Type: application/json' \
  -d '{"text":"WIN a FREE iPhone now! Click here: bit.ly/xyz123"}'
```

### Self-healing

```bash
kubectl get pods -l app=spam-api -o wide
kubectl delete pod <one-of-them>
kubectl get pods -l app=spam-api -o wide
```

```
# before
spam-api-74c9f66bb5-mv4sn   1/1   Running   0   65s   10.244.1.2   minikube-m02
spam-api-74c9f66bb5-l2bfp   1/1   Running   0   65s   10.244.0.3   minikube

# after deleting -l2bfp
spam-api-74c9f66bb5-mv4sn   1/1   Running   0   65s   10.244.1.2   minikube-m02
spam-api-74c9f66bb5-wzccl   0/1   Running   0   9s    10.244.0.4   minikube
```

The replacement appears within seconds, keeping the same ReplicaSet name prefix. To see
which controller created it:

```bash
kubectl get events --field-selector reason=SuccessfulCreate --sort-by=.lastTimestamp | tail -2
```

```
82s   Normal   SuccessfulCreate   replicaset/spam-api-74c9f66bb5   Created pod: spam-api-74c9f66bb5-l2bfp
26s   Normal   SuccessfulCreate   replicaset/spam-api-74c9f66bb5   Created pod: spam-api-74c9f66bb5-wzccl
```

`--field-selector` filters server-side so only creation events are returned, and `tail -2`
trims them to the replacement just triggered. The actor is the ReplicaSet, not the
Deployment — the Deployment owns the ReplicaSet and delegates replica count to it.

### Rolling update

Change `VERSION` in `q4/app.py` from `v1` to `v2`, then:

```bash
docker build -t spam-api:v2 .
minikube image load spam-api:v2
```

To show the update completed without downtime, the poll has to be running *while* the
rollout happens — `kubectl rollout status` blocks until it finishes, so polling afterwards
only ever sees the new version.

To do it in one terminal background the probe:

```bash
MK=$(minikube ip)
( for i in $(seq 1 30); do
    curl -s -w '\n' --max-time 2 http://$MK:30080/healthz || echo FAIL
    sleep 1
  done | sort | uniq -c > /tmp/probe.txt ) &

sleep 2
kubectl set image deployment/spam-api api=spam-api:v2
kubectl rollout status deployment/spam-api
wait; cat /tmp/probe.txt
```

Observed:

```
     21 {"status":"ok","version":"v1"}
      9 {"status":"ok","version":"v2"}
```

30 of 30 requests succeeded with no `FAIL` line, and both versions answered during the
same rollout. 30 requests at ~1 s intervals span the 15-20 s rollout, including the final
old-pod termination.

### Rollback

```bash
kubectl rollout undo deployment/spam-api
```

### Cleanup

```bash
kubectl delete -f deployment.yaml -f service.yaml
minikube delete --all
```
