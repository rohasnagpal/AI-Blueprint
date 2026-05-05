# DocTalk — Full Build Prompt for Claude Code / Codex

Build a full-stack application called **DocTalk** — a RAG-powered document Q&A platform that runs locally on the user's laptop. Use the attached `doctalk.html` as the exact UI. Implement all functionality behind it. No auth, no accounts — single user, runs locally.

---

## AUDIENCE
Non-technical users. Setup must be:
```
git clone https://github.com/yourname/doctalk
cd doctalk
pip install -r requirements.txt
python main.py
# open http://localhost:8000
```
No .env file editing. No terminal commands beyond the above. All configuration (API keys, settings) is done inside the app's Settings page.

---

## STACK
- **Frontend:** The attached `doctalk.html` served as a static file (no React, no build step)
- **Backend:** Python + FastAPI
- **Metadata storage:** SQLite via `sqlite3` (built into Python, zero setup)
- **RAG mode 1:** OpenAI RAG — OpenAI Files API + Vector Stores + Assistants API
- **RAG mode 2:** Local RAG — LlamaIndex + ChromaDB + sentence-transformers (fully offline)
- **Config storage:** SQLite table called `settings` (key-value pairs, replaces .env)

---

## FILE STRUCTURE
```
doctalk/
├── main.py                  # FastAPI entry point, serves HTML, mounts routes
├── database.py              # SQLite setup, migrations, settings helpers
├── rag/
│   ├── __init__.py
│   ├── base.py              # Abstract RagProvider class
│   ├── openai_rag.py        # OpenAI Files API + Vector Stores implementation
│   └── llamaindex_rag.py    # LlamaIndex + ChromaDB implementation
├── routes/
│   ├── documents.py         # Upload, list, delete documents
│   ├── chats.py             # Create thread, send message, stream response, history
│   └── settings.py          # Get and save all settings
├── public/
│   └── index.html           # The doctalk.html file (rename and place here)
├── chroma_db/               # ChromaDB persists here (auto-created)
├── requirements.txt
└── README.md
```

---

## SETTINGS STORAGE (replaces .env)
All config lives in a SQLite `settings` table (key TEXT, value TEXT).
On first run, insert defaults. Keys include:
- `rag_provider` — "openai" or "llamaindex"
- `openai_api_key` — stored AES-256-gcm encrypted
- `anthropic_api_key`, `groq_api_key`, `gemini_api_key`, `mistral_api_key`, `cohere_api_key`, `xai_api_key`, `cloudflare_api_key`, `together_api_key` — encrypted
- `chat_model` — e.g. "gpt-4o"
- `embedding_model` — e.g. "text-embedding-3-large"
- `local_embedding_model` — e.g. "all-MiniLM-L6-v2"
- `local_llm_provider` — "openai", "groq", or "ollama"
- `temperature` — float, default 0.2
- `max_tokens` — int, default 2048
- `top_k` — int, default 5
- `similarity_threshold` — float, default 0.72
- `chunk_size` — int, default 512
- `chunk_overlap` — int, default 64
- `retrieval_strategy` — "semantic", "keyword", or "hybrid"
- `response_language` — e.g. "English", "Hindi", "Arabic"
- `auto_detect_language` — "true" or "false"
- `response_length` — "concise", "balanced", or "detailed"
- `always_show_sources` — "true" or "false"
- `stream_responses` — "true" or "false"
- `max_file_size_mb` — int, default 25
- `auto_delete_days` — int, default 0 (never)
- `dark_mode` — "true" or "false"
- `font_size` — "13", "14", "16", "18"

The encryption key for API keys is auto-generated on first run and stored in a local file called `.secret_key` (not in SQLite). Never expose raw API keys in any API response.

---

## RAG PROVIDER ABSTRACTION

### base.py
```python
from abc import ABC, abstractmethod

class RagProvider(ABC):
    @abstractmethod
    async def ingest(self, file_path: str, doc_id: str, filename: str) -> dict:
        """Chunk, embed and store a document. Return metadata."""
        pass

    @abstractmethod
    async def retrieve(self, query: str, doc_ids: list[str] | None, top_k: int, threshold: float) -> list[dict]:
        """Return list of {content, source, doc_id, page} dicts."""
        pass

    @abstractmethod
    async def delete(self, doc_id: str) -> None:
        pass

    @abstractmethod
    async def delete_all(self) -> None:
        pass
```

---

## RAG MODE 1 — OpenAI RAG (openai_rag.py)

- On app start, create one OpenAI Vector Store for the user (store the `vector_store_id` in settings)
- **Ingest:** upload file via `openai.files.create()`, add to vector store via `openai.beta.vector_stores.files.create()`
- **Chat:** create one OpenAI Assistant with `file_search` tool pointing to the vector store (store `assistant_id` in settings)
- **Retrieve:** handled automatically by the Assistant — extract citations from `annotations` in the streamed response where `annotation.type == "file_citation"`
- **Delete:** `openai.files.delete(openai_file_id)` + remove from vector store

Apply settings per run:
- `temperature` → run creation
- `max_tokens` → run creation  
- `top_k` → `file_search` tool `max_num_results`
- `chat_model` → assistant model update

---

## RAG MODE 2 — Local RAG (llamaindex_rag.py)

- Uses `llama-index`, `chromadb`, `sentence-transformers`
- ChromaDB persists to `./chroma_db/` folder
- **Ingest:**
  1. Parse file with LlamaIndex `SimpleDirectoryReader`
  2. Split with `SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)`
  3. Embed with `HuggingFaceEmbedding(model_name=local_embedding_model)`
  4. Store in ChromaDB collection named `"doctalk_docs"`
  5. Store doc metadata in SQLite
- **Retrieve:**
  1. Embed query with same model
  2. Query ChromaDB with `top_k` and filter by `doc_ids` if specific docs selected
  3. Filter results below `similarity_threshold`
  4. Return chunks as context
- **Chat:** Feed retrieved chunks as context into the LLM:
  - OpenAI: use `openai.chat.completions.create()` with streaming
  - Groq: use Groq SDK with streaming  
  - Ollama: use `httpx` POST to `http://localhost:11434/api/chat` with streaming
- **Sources:** return chunk metadata (filename, chunk index) as citations

---

## MULTI-LANGUAGE SUPPORT

Inject this as the system prompt on every chat request:
```
You are DocTalk, a helpful document assistant.
Always respond in {response_language}, regardless of the language the documents are written in.
Base your answers only on the provided document context.
If the answer is not found in the documents, say so clearly in {response_language}.
Response length preference: {response_length}.
```

If `auto_detect_language` is true, detect the language of the user's message and override `response_language` for that turn only.

Language options to support:
English, Hindi, Arabic, Spanish, French, German, Portuguese, Japanese, Chinese Simplified, Chinese Traditional, Korean, Italian, Dutch, Russian, Turkish, Polish, Swedish, Indonesian, Malay, Bengali, Tamil, Urdu, Vietnamese, Thai, Greek, Hebrew, Swahili

---

## API ROUTES

### Documents
```
GET    /api/documents                    → list all docs from SQLite
POST   /api/documents/upload             → multipart upload, ingest via active RAG provider
DELETE /api/documents/{doc_id}           → delete from RAG + SQLite
DELETE /api/documents                    → delete all
```

### Chats
```
GET    /api/chats                        → list chat history from SQLite
POST   /api/chats                        → create new chat session, return chat_id
GET    /api/chats/{chat_id}/messages     → return all messages for a chat
POST   /api/chats/{chat_id}/message      → send message, stream response (SSE)
DELETE /api/chats/{chat_id}             → delete chat
```

### Settings
```
GET    /api/settings                     → return all settings (mask API keys as "••••••••")
PUT    /api/settings                     → save one or more settings
GET    /api/settings/test-connection     → test active RAG provider with current API key
```

---

## STREAMING (Server-Sent Events)

`POST /api/chats/{chat_id}/message` must return `text/event-stream`.

Format each event as:
```
data: {"type": "token", "content": "Hello"}\n\n
data: {"type": "source", "filename": "report.pdf", "page": 12, "excerpt": "..."}\n\n
data: {"type": "done"}\n\n
```

Frontend reads the stream with `ReadableStream` and:
- Appends `token` content to the message bubble in real time
- Collects `source` events and populates the Sources panel
- On `done`, finalises the message and saves to SQLite

---

## DOCUMENT METADATA (SQLite)

```sql
CREATE TABLE documents (
  id           TEXT PRIMARY KEY,   -- uuid4
  filename     TEXT NOT NULL,
  original_name TEXT NOT NULL,
  size_bytes   INTEGER,
  page_count   INTEGER,
  file_type    TEXT,
  openai_file_id TEXT,             -- null if using local RAG
  uploaded_at  TEXT                -- ISO datetime
);

CREATE TABLE chats (
  id           TEXT PRIMARY KEY,
  title        TEXT,               -- first 60 chars of first message
  doc_context  TEXT,               -- "all" or comma-separated doc_ids
  created_at   TEXT,
  updated_at   TEXT
);

CREATE TABLE messages (
  id           TEXT PRIMARY KEY,
  chat_id      TEXT REFERENCES chats(id),
  role         TEXT,               -- "user" or "assistant"
  content      TEXT,
  sources      TEXT,               -- JSON array of source objects
  created_at   TEXT
);

CREATE TABLE settings (
  key          TEXT PRIMARY KEY,
  value        TEXT
);
```

---

## IMPORTANT IMPLEMENTATION NOTES

1. **No hardcoded secrets.** All API keys come from the `settings` table, decrypted at runtime.
2. **File uploads:** use `python-multipart`, limit to `max_file_size_mb` from settings.
3. **Accepted file types:** PDF, DOCX, TXT, CSV, XLSX, MD — enforce server-side.
4. **On first run:** if `settings` table is empty, show a first-run banner in the UI pointing users to Settings → API Keys.
5. **RAG provider switch:** when user changes provider in settings, re-index all existing documents automatically in the background and show progress.
6. **ChromaDB + sentence-transformers** install lazily — only import and download when local RAG mode is first activated.
7. **Ollama** — if selected as local LLM, check `http://localhost:11434` is reachable and show a clear error if not.
8. **CORS:** allow `http://localhost:*` in development only.
9. **Static files:** serve `public/index.html` at `/` via FastAPI `StaticFiles`.
10. **Error handling:** all errors must return `{"error": "human-readable message"}` and be displayed in the UI as a toast notification.

---

## requirements.txt
```
fastapi
uvicorn[standard]
python-multipart
openai>=1.30.0
llama-index
llama-index-vector-stores-chroma
llama-index-embeddings-huggingface
chromadb
sentence-transformers
groq
httpx
cryptography
aiofiles
```

---

## README.md (write this exactly)
```markdown
# DocTalk

Chat with your documents using AI. Runs locally on your laptop.

## Setup

1. Download or clone this project
2. Make sure Python 3.10+ is installed (python.org)
3. Open a terminal in the project folder and run:

pip install -r requirements.txt
python main.py

4. Open http://localhost:8000 in your browser
5. Go to Settings → API Keys and enter your OpenAI API key
6. Upload documents and start chatting!

## RAG Modes

- **OpenAI RAG** (default) — uses your OpenAI API key, easiest to set up
- **Local RAG** — free, runs offline, no API key for embeddings. Switch in Settings → RAG Provider.

## Supported File Types
PDF, DOCX, TXT, CSV, XLSX, Markdown

## Supported Languages
27 languages including English, Hindi, Arabic, Spanish, French, German, Japanese, Chinese and more. Change in Settings → Chat Preferences.
```

---

## DELIVERABLES
1. All source files with complete, working code — no TODOs, no stubs
2. `requirements.txt`
3. `README.md` exactly as above
4. The final `public/index.html` with all frontend JS wired up to the `/api/*` routes
