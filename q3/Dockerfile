FROM python:3.11-slim
WORKDIR /app
COPY generate_shards.py .
RUN python generate_shards.py --out-dir shards
COPY validate_shard.py .
CMD ["python", "validate_shard.py"]
