# Personal AI Brain — Production Dockerfile
FROM python:3.12-slim

WORKDIR /app

# System dependencies for ChromaDB, OpenCV, audio processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure data directories exist
RUN mkdir -p /app/data /app/data/uploads /app/data/.derived

EXPOSE 8000

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5)" || exit 1

CMD ["python", "-m", "uvicorn", "src.brain.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
