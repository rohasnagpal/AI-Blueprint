import json
import logging
import time
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import database
from app.api.router import router as v2_router
from app.api.realtime import router as realtime_router
from app.core.bootstrap import ensure_default_admin
from app.core.config import get_settings, validate_runtime_security
from app.core.database import run_migrations
from app.core.secrets import ensure_secret_key_configured
from routes.chats import router as chat_router
from routes.email import router as email_router
from routes.personas import router as persona_router
from routes.settings import router as settings_router

logger = logging.getLogger("ai_blueprint")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def _startup() -> None:
    settings = get_settings()
    validate_runtime_security(settings)
    database.init_db()
    if settings.run_migrations_on_startup:
        run_migrations()
    ensure_secret_key_configured()
    if settings.bootstrap_default_admin:
        ensure_default_admin()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _startup()
    yield


app = FastAPI(title="AI Blueprint", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _error_code(status_code: int, default: str = "REQUEST_ERROR") -> str:
    return {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        500: "INTERNAL_SERVER_ERROR",
    }.get(status_code, default)


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": detail, "code": _error_code(exc.status_code), "details": {}},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": "Validation failed", "code": "VALIDATION_ERROR", "details": {"errors": exc.errors()}},
    )


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.exception(
            json.dumps(
                {
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": 500,
                    "duration_ms": duration_ms,
                },
                sort_keys=True,
            )
        )
        raise
    response.headers["X-Request-Id"] = request_id
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'self'; "
        "script-src-elem 'self'; "
        "script-src-attr 'none'; "
        "style-src 'self'; "
        "style-src-elem 'self'; "
        "style-src-attr 'none'; "
        "font-src 'self'; "
        "img-src 'self' data: blob: https:; "
        "object-src 'none'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'",
    )
    if request.url.path == "/" or request.url.path in APP_ROUTES or request.url.path.endswith(".html"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
    elif request.url.path.endswith((".js", ".css")):
        response.headers["Cache-Control"] = "no-store, max-age=0"
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    logger.info(
        json.dumps(
            {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
            sort_keys=True,
        )
    )
    return response


@app.get("/api/health")
async def health():
    return {"ok": True, "first_run": database.is_first_run()}


app.include_router(chat_router, prefix="/api")
app.include_router(email_router, prefix="/api")
app.include_router(persona_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(realtime_router, prefix="/api")
app.include_router(v2_router)

BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))

APP_ROUTES = {
    "/chat",
    "/personas",
    "/settings",
    "/settings/workspaces",
    "/settings/users",
    "/documents",
    "/documents/add",
    "/email",
    "/translate",
    "/draft",
    "/contract-review",
    "/arbitration-prep",
    "/arbitration-prep/",
    "/litigation-prep",
    "/litigation-prep/",
    "/mediation-prep",
    "/mediation-prep/",
    "/negotiation-prep",
    "/negotiation-prep/",
    "/admin/users",
}


async def app_route_fallback():
    return FileResponse(BASE_DIR / "public" / "index.html")


for route_path in APP_ROUTES:
    app.add_api_route(route_path, app_route_fallback, methods=["GET"], include_in_schema=False)


app.mount("/", StaticFiles(directory=BASE_DIR / "public", html=True), name="static")

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port, reload=False)
