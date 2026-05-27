FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# Cloud Run sets PORT env var — default to 8080
ENV PORT=8080
ENV UVICORN_TIMEOUT_KEEP_ALIVE=300
ENV DB_PATH=/tmp/app.db
ENV INDUSAI_DATA_DIR=/tmp


# Run with Uvicorn — single worker for free tier
CMD exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port ${PORT} \
    --workers 1 \
    --log-level info
