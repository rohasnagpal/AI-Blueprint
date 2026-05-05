import os
import base64
import sqlite3
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

DB_PATH = "ai_blueprint.db"
SECRET_KEY_FILE = ".secret_key"

DEFAULTS = {
    "rag_provider": "openai",
    "openai_api_key": "",
    "anthropic_api_key": "",
    "groq_api_key": "",
    "gemini_api_key": "",
    "mistral_api_key": "",
    "cohere_api_key": "",
    "xai_api_key": "",
    "cloudflare_api_key": "",
    "together_api_key": "",
    "chat_model": "gpt-4o",
    "embedding_model": "text-embedding-3-large",
    "local_embedding_model": "all-MiniLM-L6-v2",
    "local_llm_provider": "openai",
    "temperature": "0.2",
    "max_tokens": "2048",
    "top_k": "5",
    "similarity_threshold": "0.72",
    "chunk_size": "512",
    "chunk_overlap": "64",
    "retrieval_strategy": "semantic",
    "response_language": "English",
    "auto_detect_language": "false",
    "response_length": "balanced",
    "always_show_sources": "false",
    "stream_responses": "true",
    "max_file_size_mb": "25",
    "auto_delete_days": "0",
    "dark_mode": "false",
    "font_size": "14",
    "vector_store_id": "",
    "assistant_id": "",
}

API_KEY_FIELDS = {
    "openai_api_key", "anthropic_api_key", "groq_api_key", "gemini_api_key",
    "mistral_api_key", "cohere_api_key", "xai_api_key", "cloudflare_api_key", "together_api_key",
}


def _get_secret_key() -> bytes:
    if os.path.exists(SECRET_KEY_FILE):
        with open(SECRET_KEY_FILE, "rb") as f:
            return base64.b64decode(f.read().strip())
    key = os.urandom(32)
    with open(SECRET_KEY_FILE, "wb") as f:
        f.write(base64.b64encode(key))
    return key


def _encrypt(value: str) -> str:
    if not value:
        return ""
    key = _get_secret_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, value.encode(), None)
    return base64.b64encode(nonce).decode() + ":" + base64.b64encode(ct).decode()


def _decrypt(value: str) -> str:
    if not value:
        return ""
    try:
        nonce_b64, ct_b64 = value.split(":", 1)
        key = _get_secret_key()
        aesgcm = AESGCM(key)
        pt = aesgcm.decrypt(base64.b64decode(nonce_b64), base64.b64decode(ct_b64), None)
        return pt.decode()
    except Exception:
        return ""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            id            TEXT PRIMARY KEY,
            filename      TEXT NOT NULL,
            original_name TEXT NOT NULL,
            size_bytes    INTEGER,
            page_count    INTEGER,
            file_type     TEXT,
            openai_file_id TEXT,
            uploaded_at   TEXT
        );

        CREATE TABLE IF NOT EXISTS chats (
            id           TEXT PRIMARY KEY,
            title        TEXT,
            doc_context  TEXT,
            thread_id    TEXT,
            created_at   TEXT,
            updated_at   TEXT
        );

        CREATE TABLE IF NOT EXISTS messages (
            id         TEXT PRIMARY KEY,
            chat_id    TEXT REFERENCES chats(id),
            role       TEXT,
            content    TEXT,
            sources    TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    count = conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0]
    if count == 0:
        for k, v in DEFAULTS.items():
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
    conn.commit()
    conn.close()


def get_setting(key: str) -> str:
    conn = get_connection()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    if row is None:
        return DEFAULTS.get(key, "")
    val = row["value"]
    if key in API_KEY_FIELDS:
        return _decrypt(val)
    return val or ""


def set_setting(key: str, value: str):
    conn = get_connection()
    stored = _encrypt(value) if key in API_KEY_FIELDS else value
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, stored))
    conn.commit()
    conn.close()


def get_all_settings() -> dict:
    conn = get_connection()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    result = dict(DEFAULTS)
    for row in rows:
        k, v = row["key"], row["value"]
        if k in API_KEY_FIELDS:
            decrypted = _decrypt(v)
            result[k] = "••••••••" if decrypted else ""
        else:
            result[k] = v or ""
    return result


def is_first_run() -> bool:
    for key in API_KEY_FIELDS:
        if get_setting(key):
            return False
    return True
