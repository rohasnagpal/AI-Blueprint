# Deployment Guide

AI Blueprint is local-first, but public deployments need explicit runtime paths and HTTPS controls.

## Runtime Paths

Use absolute paths outside the repository:

```bash
export AI_BLUEPRINT_DATABASE_URL=sqlite:////srv/ai-blueprint/data/ai_blueprint_v2.db
export AI_BLUEPRINT_APP_DATABASE_PATH=/srv/ai-blueprint/data/ai_blueprint.db
export AI_BLUEPRINT_UPLOADS_DIR=/srv/ai-blueprint/uploads_v2
export AI_BLUEPRINT_SECRET_KEY_FILE=/srv/ai-blueprint/keys/ai_blueprint_v2.key
export AI_BLUEPRINT_APP_SECRET_KEY_FILE=/srv/ai-blueprint/keys/ai_blueprint_application.key
```

The database, uploads, Chroma index, and key files are confidential runtime data. Do not commit them or serve them as static files.

## Public Security Settings

```bash
export AI_BLUEPRINT_SECURE_COOKIES=true
export AI_BLUEPRINT_CORS_ORIGINS=https://your-domain.example
export AI_BLUEPRINT_AUTH_RATE_LIMIT_ATTEMPTS=10
export AI_BLUEPRINT_AUTH_RATE_LIMIT_WINDOW_SECONDS=60
export AI_BLUEPRINT_MAX_UPLOAD_BYTES=26214400
export AI_BLUEPRINT_ENV=production
export AI_BLUEPRINT_RUN_MIGRATIONS_ON_STARTUP=false
```

Do not enable `AI_BLUEPRINT_BOOTSTRAP_DEFAULT_ADMIN` on public deployments. Use the first-run setup flow instead.

## Database Migrations

Run migrations as an explicit deployment step before starting or restarting app
workers:

```bash
.venv/bin/python scripts/migrate.py
```

Do not run migrations from every production app process. Keep
`AI_BLUEPRINT_RUN_MIGRATIONS_ON_STARTUP=false` in production so multiple workers
cannot race on startup.

## Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
.venv/bin/python scripts/migrate.py
python main.py
```

For production, run behind a process manager and reverse proxy. The reverse proxy should terminate TLS and enforce an upload body limit consistent with `AI_BLUEPRINT_MAX_UPLOAD_BYTES`.

## Docker Compose Example

Copy the example environment file, edit the domain and secret paths, then run the
one-shot migration service before the app starts:

```bash
cp .env.production.example .env.production
docker compose -f docker-compose.example.yml up --build
```

The compose file stores SQLite data, uploads, and encryption keys in separate
named volumes. Keep reverse proxy TLS termination outside the app container.

## Verify

```bash
curl -s https://your-domain.example/api/v2/health
```

The response should show `ok: true`, the current Alembic migration revision, sufficient upload storage, and `secrets.key_configured: true`.
