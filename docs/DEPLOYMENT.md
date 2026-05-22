# Deployment Guide

AI Blueprint is local-first, but public deployments need explicit runtime paths and HTTPS controls.

## Runtime Paths

Use absolute paths outside the repository:

```bash
export AI_BLUEPRINT_DATABASE_URL=sqlite:////srv/ai-blueprint/data/ai_blueprint_v2.db
export AI_BLUEPRINT_LEGACY_DATABASE_PATH=/srv/ai-blueprint/data/ai_blueprint.db
export AI_BLUEPRINT_UPLOADS_DIR=/srv/ai-blueprint/uploads_v2
export AI_BLUEPRINT_SECRET_KEY_FILE=/srv/ai-blueprint/keys/ai_blueprint_v2.key
export AI_BLUEPRINT_LEGACY_SECRET_KEY_FILE=/srv/ai-blueprint/keys/ai_blueprint_legacy.key
```

The database, uploads, Chroma index, and key files are confidential runtime data. Do not commit them or serve them as static files.

## Public Security Settings

```bash
export AI_BLUEPRINT_SECURE_COOKIES=true
export AI_BLUEPRINT_CORS_ORIGINS=https://your-domain.example
export AI_BLUEPRINT_AUTH_RATE_LIMIT_ATTEMPTS=10
export AI_BLUEPRINT_AUTH_RATE_LIMIT_WINDOW_SECONDS=60
export AI_BLUEPRINT_MAX_UPLOAD_BYTES=26214400
```

Do not enable `AI_BLUEPRINT_BOOTSTRAP_DEFAULT_ADMIN` on public deployments. Use the first-run setup flow instead.

## Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

For production, run behind a process manager and reverse proxy. The reverse proxy should terminate TLS and enforce an upload body limit consistent with `AI_BLUEPRINT_MAX_UPLOAD_BYTES`.

## Verify

```bash
curl -s https://your-domain.example/api/v2/health
```

The response should show `ok: true`, migration revision `0015_user_admin_bootstrap`, sufficient upload storage, and `secrets.key_configured: true`.

