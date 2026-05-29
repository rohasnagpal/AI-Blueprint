FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AI_BLUEPRINT_HOST=0.0.0.0 \
    AI_BLUEPRINT_PORT=8000 \
    AI_BLUEPRINT_ENV=production \
    AI_BLUEPRINT_RUN_MIGRATIONS_ON_STARTUP=false

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin appuser

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data /uploads /keys \
    && chown -R appuser:appuser /app /data /uploads /keys

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import json, urllib.request; data=json.loads(urllib.request.urlopen('http://127.0.0.1:8000/api/v2/health', timeout=5).read()); raise SystemExit(0 if data.get('ok') else 1)"

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
