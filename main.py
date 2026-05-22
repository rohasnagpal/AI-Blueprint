import json
import time
import sys
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import database
from app.api.router import router as v2_router
from app.core.bootstrap import ensure_default_admin
from app.core.config import get_settings
from app.core.database import run_migrations
from app.core.secrets import ensure_secret_key_configured
from routes.documents import router as doc_router
from routes.chats import router as chat_router
from routes.councils import router as council_router
from routes.email import router as email_router
from routes.personas import router as persona_router
from routes.settings import router as settings_router

app = FastAPI(title="AI Blueprint")

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
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    print(
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


@app.on_event("startup")
async def startup():
    database.init_db()
    run_migrations()
    ensure_secret_key_configured()
    if get_settings().bootstrap_default_admin:
        ensure_default_admin()


@app.get("/api/health")
async def health():
    return {"ok": True, "first_run": database.is_first_run()}


app.include_router(doc_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(council_router, prefix="/api")
app.include_router(email_router, prefix="/api")
app.include_router(persona_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(v2_router)

BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
app.mount("/", StaticFiles(directory=BASE_DIR / "public", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
