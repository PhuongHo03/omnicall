FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential ffmpeg git libsndfile1 sox \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir --retries 10 --timeout 120 --progress-bar off --index-url https://download.pytorch.org/whl/cpu torch==2.7.1 torchaudio==2.7.1
RUN pip install --no-cache-dir --retries 10 --timeout 120 --progress-bar off -r /app/backend/requirements.txt

COPY alembic.ini /app/alembic.ini
COPY backend /app/backend

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
