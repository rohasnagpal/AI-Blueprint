import os
import shutil

from fastapi import APIRouter
from sqlalchemy import text

from app.api import admin, audit, auth, blueprints, contract_review, council, documents, escalations, jobs, legal_research, navigation, personas, plugins, realtime, secrets, settings, skills, translation, workspaces
from app.core.config import get_settings
from app.core.database import engine

router = APIRouter(prefix="/api/v2")


@router.get("/health")
async def health():
    settings = get_settings()
    db_ok = False
    migration_revision = None
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            migration_revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
            db_ok = True
    except Exception:
        db_ok = False

    uploads_root = settings.uploads_dir
    disk_path = uploads_root if uploads_root.exists() else uploads_root.parent
    if not disk_path.exists():
        disk_path = "."
    disk = shutil.disk_usage(disk_path)
    secret_key_present = settings.secret_key_file.exists() or bool(os.getenv("AI_BLUEPRINT_SECRET_KEY"))
    return {
        "ok": db_ok,
        "version": "v2",
        "database": {"ok": db_ok, "migration_revision": migration_revision},
        "storage": {
            "uploads_dir": str(settings.uploads_dir),
            "free_bytes": disk.free,
            "total_bytes": disk.total,
        },
        "secrets": {"key_configured": secret_key_present},
    }


router.include_router(auth.router)
router.include_router(admin.router)
router.include_router(navigation.router)
router.include_router(workspaces.router)
router.include_router(audit.router)
router.include_router(plugins.router)
router.include_router(personas.router)
router.include_router(settings.router)
router.include_router(blueprints.router)
router.include_router(documents.router)
router.include_router(escalations.router)
router.include_router(council.router)
router.include_router(jobs.router)
router.include_router(contract_review.router)
router.include_router(legal_research.router)
router.include_router(skills.router)
router.include_router(secrets.router)
router.include_router(translation.router)
router.include_router(realtime.router)
