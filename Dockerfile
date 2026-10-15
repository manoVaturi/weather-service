# Stage 1: Builder
FROM python:3.12-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /build/wheels -r requirements.txt

# Stage 2: Production Runtime
FROM python:3.12-slim
WORKDIR /app

# Create a non-root user (Best Practice for Security & Trivy)
RUN groupadd -r appgroup && useradd -r -g appgroup -u 10001 appuser

COPY --from=builder /build/wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

COPY app/ ./app/
RUN chown -R appuser:appgroup /app

USER 10001
EXPOSE 8000

# Run Gunicorn with 2 workers and 4 threads
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "8", "app.main:app"]
