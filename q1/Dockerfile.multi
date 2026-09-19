FROM python:3.11 AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/build/deps -r requirements.txt

COPY generate_dataset.py .
RUN PYTHONPATH=/build/deps python generate_dataset.py

COPY train_model.py .
RUN PYTHONPATH=/build/deps python train_model.py --data spam_dataset.csv --out model.joblib

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /build/deps /usr/local/lib/python3.11/site-packages
COPY --from=builder /build/model.joblib .
COPY app.py .
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "app:app","--host", "0.0.0.0", "--port", "8080"]