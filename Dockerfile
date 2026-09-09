FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential ffmpeg libgomp1 libsndfile1 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN python -m pip install --upgrade pip && pip install -r requirements.txt
COPY . .
RUN useradd --create-home --uid 10001 brain \
    && mkdir -p /app/data/uploads /app/data/storage /app/data/vector_db \
    && chown -R brain:brain /app \
    && chmod +x /app/scripts/docker_entrypoint.sh /app/scripts/validate_environment.py
USER brain
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import os,urllib.request; r=urllib.request.Request('http://localhost:8000/health/ready',headers=dict(Authorization='Bearer '+os.environ['BRAIN_API_KEY'])); urllib.request.urlopen(r,timeout=5)" || exit 1
ENTRYPOINT ["/app/scripts/docker_entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "src.brain.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
