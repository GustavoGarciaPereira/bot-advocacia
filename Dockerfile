# =============================================================================
# RPA Core — Dockerfile
# =============================================================================
# Build:  docker build -t rpa-core .
# Run:    docker run --rm -e CLIENT_ID=escritorio_alpha rpa-core

FROM python:3.12-slim

WORKDIR /app

# System deps for Chrome + Selenium
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY src/ ./src/

# Data dirs (mounted as volumes in production, but created for dev)
RUN mkdir -p /app/data/output /app/data/logs

ENTRYPOINT ["python", "-m", "src.main"]
CMD ["--client-id", "escritorio_alpha"]
