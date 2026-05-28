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
    && pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium

COPY . .

RUN mkdir -p /data /uploads /keys \
    && chown -R appuser:appuser /app /data /uploads /keys

USER appuser

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
