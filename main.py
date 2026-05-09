import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import database
from routes.documents import router as doc_router
from routes.chats import router as chat_router
from routes.councils import router as council_router
from routes.email import router as email_router
from routes.personas import router as persona_router
from routes.settings import router as settings_router

app = FastAPI(title="AI Blueprint")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    database.init_db()


@app.get("/api/health")
async def health():
    return {"ok": True, "first_run": database.is_first_run()}


app.include_router(doc_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(council_router, prefix="/api")
app.include_router(email_router, prefix="/api")
app.include_router(persona_router, prefix="/api")
app.include_router(settings_router, prefix="/api")

BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
app.mount("/", StaticFiles(directory=BASE_DIR / "public", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
