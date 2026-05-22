# AI Blueprint Operations

## Runtime Data

Backups must include these items together because they are not independently useful:

- `ai_blueprint.db`: legacy application database.
- `ai_blueprint_v2.db`: v2 platform database, plus any active SQLite sidecars during a live backup.
- `uploads/`: legacy uploaded files.
- `uploads_v2/`: v2 content-addressed uploaded files.
- `chroma_db/`: local vector index data.
- `.secret_key`: legacy API-key encryption key.
- `.secret_key_v2` or the path configured by `AI_BLUEPRINT_SECRET_KEY_FILE`: v2 secret encryption key.

Do not store backup archives inside the repository. Treat backup archives as confidential client data.

## Consistent SQLite Backup

For a running local SQLite deployment, prefer SQLite's online backup command rather than copying the database file directly:

```bash
sqlite3 ai_blueprint_v2.db ".backup '/secure/backup/ai_blueprint_v2.db'"
sqlite3 ai_blueprint.db ".backup '/secure/backup/ai_blueprint.db'"
```

Then copy the runtime directories and encryption keys into the same backup set:

```bash
rsync -a uploads/ uploads_v2/ chroma_db/ /secure/backup/runtime-files/
cp .secret_key .secret_key_v2 /secure/backup/keys/
```

If `AI_BLUEPRINT_SECRET_KEY_FILE` points outside the repository, copy that configured file instead of `.secret_key_v2`.

## Restore

Restore the database files, runtime directories, and encryption keys before starting the server. A restored database without the matching key files cannot decrypt stored credentials.

After restore, run migrations before accepting users:

```bash
.venv/bin/python -c "from app.core.database import run_migrations; run_migrations()"
```

Verify the deployment:

```bash
curl -s http://127.0.0.1:8004/api/v2/health
```

The health response should report `ok: true`, the expected Alembic revision, upload storage free space, and `secrets.key_configured: true`.

## Monitoring

Monitor `/api/v2/health`, request logs, failed job records, authentication failures, and free disk space on the uploads volume. Every response includes `X-Request-Id`; keep that value in support reports so a request can be traced through logs.
