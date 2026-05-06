import os
import base64
import json
import sqlite3
from datetime import datetime, timezone
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
    "app_name": "AI Blueprint",
    "app_intro": "Build, run and chat with AI agents, pipelines and tools. Powered by your documents.",
    "suggested_questions": '["Summarize the key points","What are the main findings?","List all action items","Compare sections across documents","What dates or deadlines are mentioned?","Explain this in simple terms"]',
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

        CREATE TABLE IF NOT EXISTS council_templates (
            id           TEXT PRIMARY KEY,
            name         TEXT NOT NULL,
            description  TEXT,
            config_json  TEXT NOT NULL,
            is_builtin   INTEGER DEFAULT 0,
            created_at   TEXT,
            updated_at   TEXT
        );

        CREATE TABLE IF NOT EXISTS council_runs (
            id           TEXT PRIMARY KEY,
            template_id  TEXT,
            title        TEXT,
            objective    TEXT,
            doc_context  TEXT,
            config_json  TEXT NOT NULL,
            status       TEXT,
            error        TEXT,
            created_at   TEXT,
            started_at   TEXT,
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS council_outputs (
            id            TEXT PRIMARY KEY,
            run_id        TEXT REFERENCES council_runs(id),
            phase_id      TEXT,
            phase_name    TEXT,
            agent_id      TEXT,
            role_name     TEXT,
            content       TEXT,
            sources_json  TEXT,
            metadata_json TEXT,
            created_at    TEXT
        );

        CREATE TABLE IF NOT EXISTS council_evidence (
            id           TEXT PRIMARY KEY,
            run_id       TEXT REFERENCES council_runs(id),
            phase_id     TEXT,
            phase_name   TEXT,
            query        TEXT,
            sources_json TEXT,
            created_at   TEXT
        );

        CREATE TABLE IF NOT EXISTS ai_models (
            id           TEXT PRIMARY KEY,
            provider     TEXT NOT NULL,
            display_name TEXT NOT NULL,
            model_id     TEXT NOT NULL,
            enabled      INTEGER DEFAULT 1,
            is_builtin   INTEGER DEFAULT 0,
            created_at   TEXT,
            updated_at   TEXT
        );
    """)
    chat_cols = [row["name"] for row in conn.execute("PRAGMA table_info(chats)").fetchall()]
    if "archived_at" not in chat_cols:
        conn.execute("ALTER TABLE chats ADD COLUMN archived_at TEXT")
    count = conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0]
    if count == 0:
        for k, v in DEFAULTS.items():
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
    _seed_council_templates(conn)
    _ensure_builtin_template_updates(conn)
    _seed_ai_models(conn)
    _ensure_builtin_ai_models(conn)
    conn.commit()
    conn.close()


def _seed_council_templates(conn: sqlite3.Connection):
    from datetime import datetime, timezone

    seeded = conn.execute("SELECT value FROM settings WHERE key = 'council_templates_seeded'").fetchone()
    if seeded and seeded["value"] == "true":
        return

    now = datetime.now(timezone.utc).isoformat()
    presets = [
        {
            "id": "builtin-arbitration",
            "name": "Arbitration Council",
            "description": "Party advocates, devil's advocate, and a presiding judge produce a document-grounded award.",
            "config": {
                "name": "Arbitration Council",
                "description": "Document-grounded arbitration panel.",
                "document_scope": "run",
                "objective_prompt": "Resolve the dispute based only on the uploaded documents.",
                "output_format": "reasoned_award",
                "agents": [
                    {
                        "id": "claimant",
                        "name": "Claimant Counsel",
                        "instructions": "Argue the strongest case for the claimant using only the provided evidence. Cite sources where available.",
                        "provider": "default",
                        "model": "default",
                        "temperature": 0.2,
                        "max_tokens": 1600,
                        "context_access": ["documents", "user_prompt"],
                        "output_type": "argument",
                        "require_citations": True,
                    },
                    {
                        "id": "respondent",
                        "name": "Respondent Counsel",
                        "instructions": "Argue the strongest case for the respondent using only the provided evidence. Cite sources where available.",
                        "provider": "default",
                        "model": "default",
                        "temperature": 0.2,
                        "max_tokens": 1600,
                        "context_access": ["documents", "user_prompt"],
                        "output_type": "argument",
                        "require_citations": True,
                    },
                    {
                        "id": "devils_advocate",
                        "name": "Devil's Advocate",
                        "instructions": "Identify weaknesses, assumptions, evidentiary gaps, and strongest counterarguments against both sides.",
                        "provider": "default",
                        "model": "default",
                        "temperature": 0.15,
                        "max_tokens": 1400,
                        "context_access": ["documents", "user_prompt", "prior_outputs"],
                        "output_type": "critique",
                        "require_citations": True,
                    },
                    {
                        "id": "judge",
                        "name": "Presiding Judge",
                        "instructions": "Write only the final arbitration award after considering the evidence and prior submissions. Do not repeat party submissions or prompt text. Use clear markdown headings for Findings, Reasons, and Award.",
                        "provider": "default",
                        "model": "default",
                        "temperature": 0.1,
                        "max_tokens": 2200,
                        "context_access": ["documents", "user_prompt", "prior_outputs"],
                        "output_type": "final_decision",
                        "require_citations": True,
                    },
                ],
                "phases": [
                    {"id": "openings", "name": "Opening Arguments", "mode": "parallel", "agents": ["claimant", "respondent"], "instructions": "Present each side's strongest opening position.", "retrieval_query": "objective"},
                    {"id": "challenge", "name": "Challenge", "mode": "sequential", "agents": ["devils_advocate"], "instructions": "Challenge both party positions.", "retrieval_query": "phase"},
                    {"id": "award", "name": "Arbitration Award", "mode": "sequential", "agents": ["judge"], "instructions": "Produce only the final arbitration award. Start with the heading 'Arbitration Award'. Do not include a separate Decision heading or quote prior outputs verbatim.", "retrieval_query": "objective"},
                ],
            },
        },
        {
            "id": "builtin-moot-court",
            "name": "Moot Court Grader",
            "description": "Evaluates a student's argument against a compromis or problem record.",
            "config": {
                "name": "Moot Court Grader",
                "description": "Multi-perspective law student feedback panel.",
                "document_scope": "run",
                "objective_prompt": "Grade the student's argument using the uploaded compromis and record.",
                "output_format": "scorecard",
                "agents": [
                    {
                        "id": "merits_grader",
                        "name": "Legal Merits Grader",
                        "instructions": "Assess legal reasoning, issue spotting, authorities, facts, and use of the record. Provide specific improvements.",
                        "provider": "default",
                        "model": "default",
                        "temperature": 0.15,
                        "max_tokens": 1600,
                        "context_access": ["documents", "user_prompt"],
                        "output_type": "grade",
                        "require_citations": True,
                    },
                    {
                        "id": "advocacy_grader",
                        "name": "Advocacy Grader",
                        "instructions": "Assess structure, persuasion, responsiveness, clarity, and courtroom strategy. Be concrete and fair.",
                        "provider": "default",
                        "model": "default",
                        "temperature": 0.2,
                        "max_tokens": 1400,
                        "context_access": ["documents", "user_prompt"],
                        "output_type": "grade",
                        "require_citations": False,
                    },
                    {
                        "id": "bench_panel",
                        "name": "Bench Panel",
                        "instructions": "Synthesize the graders' feedback into a final scorecard with strengths, weaknesses, and next practice steps.",
                        "provider": "default",
                        "model": "default",
                        "temperature": 0.1,
                        "max_tokens": 1800,
                        "context_access": ["documents", "user_prompt", "prior_outputs"],
                        "output_type": "synthesis",
                        "require_citations": True,
                    },
                ],
                "phases": [
                    {"id": "grading", "name": "Grading", "mode": "parallel", "agents": ["merits_grader", "advocacy_grader"], "instructions": "Grade the student submission.", "retrieval_query": "objective"},
                    {"id": "feedback", "name": "Final Feedback", "mode": "sequential", "agents": ["bench_panel"], "instructions": "Synthesize final feedback.", "retrieval_query": "phase"},
                ],
            },
        },
    ]
    for preset in presets:
        conn.execute(
            """
            INSERT OR IGNORE INTO council_templates
            (id, name, description, config_json, is_builtin, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
            (
                preset["id"],
                preset["name"],
                preset["description"],
                json.dumps(preset["config"]),
                now,
                now,
            ),
        )
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('council_templates_seeded', 'true')")


def _ensure_builtin_template_updates(conn: sqlite3.Connection):
    row = conn.execute("SELECT config_json FROM council_templates WHERE id = 'builtin-arbitration' AND is_builtin = 1").fetchone()
    if not row:
        return
    try:
        config = json.loads(row["config_json"])
    except Exception:
        return
    changed = False
    for agent in config.get("agents", []):
        if agent.get("id") == "judge":
            instructions = (
                "Write only the final arbitration award after considering the evidence and prior submissions. "
                "Do not repeat party submissions or prompt text. Use clear markdown headings for Findings, Reasons, and Award."
            )
            if agent.get("instructions") != instructions:
                agent["instructions"] = instructions
                changed = True
    for phase in config.get("phases", []):
        if phase.get("id") == "decision":
            phase["id"] = "award"
            phase["name"] = "Arbitration Award"
            phase["instructions"] = (
                "Produce only the final arbitration award. Start with the heading 'Arbitration Award'. "
                "Do not include a separate Decision heading or quote prior outputs verbatim."
            )
            changed = True
    if changed:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE council_templates SET config_json = ?, updated_at = ? WHERE id = 'builtin-arbitration'",
            (json.dumps(config), now),
        )


def _seed_ai_models(conn: sqlite3.Connection):
    from datetime import datetime, timezone

    seeded = conn.execute("SELECT value FROM settings WHERE key = 'ai_models_seeded'").fetchone()
    if seeded and seeded["value"] == "true":
        return

    now = datetime.now(timezone.utc).isoformat()
    models = [
        ("openai-gpt-4o", "openai", "GPT-4o", "gpt-4o"),
        ("openai-gpt-4o-mini", "openai", "GPT-4o mini", "gpt-4o-mini"),
        ("openai-gpt-4-turbo", "openai", "GPT-4 Turbo", "gpt-4-turbo"),
        ("openai-gpt-35-turbo", "openai", "GPT-3.5 Turbo", "gpt-3.5-turbo"),
        ("anthropic-claude-35-sonnet", "anthropic", "Claude 3.5 Sonnet", "claude-3-5-sonnet-latest"),
        ("anthropic-claude-35-haiku", "anthropic", "Claude 3.5 Haiku", "claude-3-5-haiku-latest"),
        ("anthropic-claude-3-opus", "anthropic", "Claude 3 Opus", "claude-3-opus-latest"),
        ("groq-llama-31-8b", "groq", "Llama 3.1 8B Instant", "llama-3.1-8b-instant"),
        ("groq-llama-33-70b", "groq", "Llama 3.3 70B Versatile", "llama-3.3-70b-versatile"),
        ("ollama-llama3", "ollama", "Llama 3", "llama3"),
        ("ollama-mistral", "ollama", "Mistral", "mistral"),
        ("ollama-gemma", "ollama", "Gemma", "gemma"),
    ]
    for model in models:
        conn.execute(
            """
            INSERT OR IGNORE INTO ai_models
            (id, provider, display_name, model_id, enabled, is_builtin, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, 1, ?, ?)
            """,
            (*model, now, now),
        )
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('ai_models_seeded', 'true')")


def _ensure_builtin_ai_models(conn: sqlite3.Connection):
    now = datetime.now(timezone.utc).isoformat()
    models = [
        ("anthropic-claude-35-sonnet", "anthropic", "Claude 3.5 Sonnet", "claude-3-5-sonnet-latest"),
        ("anthropic-claude-35-haiku", "anthropic", "Claude 3.5 Haiku", "claude-3-5-haiku-latest"),
        ("anthropic-claude-3-opus", "anthropic", "Claude 3 Opus", "claude-3-opus-latest"),
    ]
    for model in models:
        conn.execute(
            """
            INSERT OR IGNORE INTO ai_models
            (id, provider, display_name, model_id, enabled, is_builtin, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, 1, ?, ?)
            """,
            (*model, now, now),
        )


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
