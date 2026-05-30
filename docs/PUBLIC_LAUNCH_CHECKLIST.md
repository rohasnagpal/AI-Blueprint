# Public Launch Checklist

Use this checklist before exposing AI Blueprint to public users or client data.

## 1. End-to-End Browser QA

Run this from a clean database and clean upload directory:

- Create the first admin from the setup screen.
- Log out and log back in.
- Create a workspace, matter, and member user.
- Upload an allowed document type and confirm indexing completes.
- Try a blocked upload type and confirm it is rejected.
- Create a document-scoped chat.
- Enable and run the council, contract review, and legal research plugins.
- Export plugin outputs.
- Archive, restore, and bulk-delete chats.
- Delete a matter and confirm matter-scoped documents are detached or hidden as designed.
- Confirm member users cannot open admin-only pages.
- Confirm secrets are never displayed after creation or rotation.

## 2. Automated Gates

Before tagging a release, run:

```bash
python -m compileall main.py database.py routes rag app migrations
python -m unittest discover -s tests
AI_BLUEPRINT_DATABASE_URL=sqlite:////tmp/ai_blueprint_v2_hardening.db \
AI_BLUEPRINT_APP_DATABASE_PATH=/tmp/ai_blueprint_application_hardening.db \
AI_BLUEPRINT_UPLOADS_DIR=/tmp/ai_blueprint_v2_hardening_uploads \
AI_BLUEPRINT_SECRET_KEY_FILE=/tmp/ai_blueprint_v2_hardening_secret.key \
AI_BLUEPRINT_APP_SECRET_KEY_FILE=/tmp/ai_blueprint_application_hardening_secret.key \
python scripts/v2_hardening_smoke.py
```

GitHub Actions must pass on Python 3.10, 3.11, and 3.12.

## 3. Production Configuration

Set these explicitly for any public deployment:

```bash
AI_BLUEPRINT_DATABASE_URL=sqlite:////secure/path/ai_blueprint_v2.db
AI_BLUEPRINT_APP_DATABASE_PATH=/secure/path/ai_blueprint.db
AI_BLUEPRINT_UPLOADS_DIR=/secure/path/uploads_v2
AI_BLUEPRINT_SECRET_KEY_FILE=/secure/path/keys/ai_blueprint_v2.key
AI_BLUEPRINT_APP_SECRET_KEY_FILE=/secure/path/keys/ai_blueprint_application.key
AI_BLUEPRINT_SECURE_COOKIES=true
AI_BLUEPRINT_CORS_ORIGINS=https://your-domain.example
AI_BLUEPRINT_AUTH_RATE_LIMIT_ATTEMPTS=10
AI_BLUEPRINT_AUTH_RATE_LIMIT_WINDOW_SECONDS=60
AI_BLUEPRINT_MAX_UPLOAD_BYTES=26214400
```

Keep `AI_BLUEPRINT_BOOTSTRAP_DEFAULT_ADMIN` unset or `false` for public deployments.

## 4. Network and Process Controls

- Serve only through HTTPS.
- Put the app behind a reverse proxy that enforces request body limits matching `AI_BLUEPRINT_MAX_UPLOAD_BYTES`.
- Restrict direct access to SQLite files, upload directories, Chroma indexes, and secret key files.
- Run the app as a non-root user.
- Keep backups outside the repository and outside the web root.

## 5. Privacy and Legal Review

- Tell users which model providers may receive prompts, document snippets, embeddings, and outputs.
- Do not ingest confidential legal material until the user has configured an approved provider and retention policy.
- Confirm deletion, backup retention, and restore procedures with the launch owner.
- Keep the product disclaimer visible in public materials: AI Blueprint supports legal work but does not replace legal judgment.

## 6. Observability

- Monitor `/api/v2/health`.
- Capture structured request logs with `request_id`, method, path, status code, and duration.
- Track failed jobs through the jobs API.
- Review authentication failures and rate-limit responses.
- Alert on low disk space for the uploads volume.

## 7. Release Packaging

- Build from a clean checkout.
- Run all automated gates.
- Start the app against a clean runtime directory and complete the browser QA path.
- Tag the release only after CI passes.
- Record the migration revision, git commit, backup location, and rollback command in the release notes.

